"""Financial Valuation agent — dual-agent market valuation assessment.

Architecture: retrieval-then-dual-reasoning
1. gather_comps() → ComparableSalesEvidence (one pass, shared)
2. run_conservative_appraiser() + run_bullish_specialist() (concurrent, asyncio.gather)
3. synthesize_valuation() → FinancialValuationResult (plain Python, not LLM)

Consumes: ProvenanceSearchKeys (from Visual Art Historian)
          TitleRiskMatrix (optional, from Provenance & Legal agent)
Produces: FinancialValuationResult (consumed by Curator agent)
"""

from __future__ import annotations

import asyncio
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from artgents.agents.art_historian import ProvenanceSearchKeys
from artgents.agents.provenance_legal import (
    TitleRiskMatrix,
    _filter_search_keywords,
    _is_relevant_parallel_hit,
    _is_specific_artist,
    _is_valid_url,
)


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------


class ComparableSale(BaseModel):
    """A single comparable sale with a cited source."""

    description: str
    price_usd: float | None = Field(
        default=None,
        description="Sale price in USD. None if source doesn't give clear figure",
    )
    sale_date: str | None = Field(
        default=None, description="Date of sale if available"
    )
    source_url: str
    source_entity_id: str | None = Field(
        default=None,
        description="Stable identifier (e.g. Wikidata QID URL) if from a structured source",
    )
    source_type: Literal["wikidata", "parallel_search"]


class ComparableSalesEvidence(BaseModel):
    """All retrieved comparable-sales evidence for a valuation assessment.

    Produced once by gather_comps() and shared identically between
    both sub-agents — they reason over the same data.
    """

    comparable_sales: list[ComparableSale] = Field(default_factory=list)
    query_search_keys: ProvenanceSearchKeys = Field(
        ..., description="The search keys used for retrieval (traceability)"
    )
    evidence_scope: Literal["specific_object", "artist_general"] = Field(
        default="artist_general",
        description=(
            "Whether evidence pertains to one specific identified object "
            "('specific_object' — work_title known AND matched to a single entity) "
            "or spans multiple works by the artist ('artist_general')."
        ),
    )
    rejected_fact_count: int = Field(
        default=0,
        description="Number of facts dropped due to validation failures",
    )
    sources_queried: list[str] = Field(
        default_factory=list,
        description="Which sources were successfully queried",
    )
    sources_failed: list[str] = Field(
        default_factory=list,
        description="Which sources failed or timed out",
    )


# ---------------------------------------------------------------------------
# Sub-agent output models
# ---------------------------------------------------------------------------


class ConservativeAppraiserOutput(BaseModel):
    """Output of the Conservative Appraiser sub-agent (floor estimate)."""

    floor_estimate_usd: float
    methodology: str
    primary_comp: str = Field(
        ...,
        description=(
            "Short, self-contained statement of the specific comp this estimate "
            "is anchored on — suitable for standalone citation without needing "
            "the full methodology paragraph for context."
        ),
    )
    confidence: Literal["low", "moderate", "high"]


class BullishSpecialistOutput(BaseModel):
    """Output of the Bullish Specialist sub-agent (ceiling estimate)."""

    ceiling_estimate_usd: float
    methodology: str
    primary_comp: str = Field(
        ...,
        description=(
            "Short, self-contained statement of the specific comp this estimate "
            "is anchored on — suitable for standalone citation without needing "
            "the full methodology paragraph for context."
        ),
    )
    confidence: Literal["low", "moderate", "high"]


# ---------------------------------------------------------------------------
# Synthesized output
# ---------------------------------------------------------------------------


class ValuationCorridor(BaseModel):
    """The low-to-high estimate range."""

    low_estimate_usd: float
    high_estimate_usd: float


class FinancialValuationResult(BaseModel):
    """Final synthesized output of the Financial Valuation agent.

    Presents both sub-agent estimates plus a synthesis corridor.
    """

    conservative_appraiser: ConservativeAppraiserOutput
    bullish_specialist: BullishSpecialistOutput
    evidence: ComparableSalesEvidence
    valuation_corridor: ValuationCorridor
    corridor_summary: str
    requires_human_review: bool


# ---------------------------------------------------------------------------
# Retrieval: gather_comps()
# ---------------------------------------------------------------------------


async def gather_comps(search_keys: ProvenanceSearchKeys) -> ComparableSalesEvidence:
    """Query external sources for comparable sales data.

    Calls Wikidata and Parallel Search concurrently, assembles
    ComparableSalesEvidence with evidence_scope determination.

    Args:
        search_keys: From the Visual Art Historian agent.

    Returns:
        ComparableSalesEvidence with all retrieved comparable sales.
    """
    import time

    sales: list[ComparableSale] = []
    sources_queried: list[str] = []
    sources_failed: list[str] = []
    rejected_counts: list[int] = [0]  # mutable container for concurrent tasks

    # Run all retrievals concurrently
    wikidata_task = asyncio.create_task(
        _retrieve_wikidata_sales(
            search_keys, sales, sources_queried, sources_failed, rejected_counts
        )
    )
    parallel_task = asyncio.create_task(
        _retrieve_parallel_sales(
            search_keys, sales, sources_queried, sources_failed
        )
    )

    await asyncio.gather(wikidata_task, parallel_task)

    evidence_scope = _determine_evidence_scope(search_keys, sales)

    logger.info(
        "Comps gathered: {} sales from {} sources (failed: {}, scope: {})",
        len(sales),
        sources_queried,
        sources_failed,
        evidence_scope,
    )

    return ComparableSalesEvidence(
        comparable_sales=sales,
        query_search_keys=search_keys,
        evidence_scope=evidence_scope,
        rejected_fact_count=rejected_counts[0],
        sources_queried=sources_queried,
        sources_failed=sources_failed,
    )


def _determine_evidence_scope(
    search_keys: ProvenanceSearchKeys,
    sales: list[ComparableSale],
) -> str:
    """Determine whether evidence is specific-object or artist-general.

    Returns "specific_object" only if:
    - work_title is present AND
    - All sales with source_entity_id share a single ID

    Otherwise returns "artist_general".
    """
    if not search_keys.work_title:
        return "artist_general"

    # Check if all sales with entity IDs share a single entity
    entity_ids = {
        s.source_entity_id for s in sales if s.source_entity_id is not None
    }

    if len(entity_ids) == 1:
        return "specific_object"

    # Multiple entity IDs or no entity IDs → artist_general
    return "artist_general"


# ---------------------------------------------------------------------------
# Wikidata retrieval
# ---------------------------------------------------------------------------


async def _retrieve_wikidata_sales(
    search_keys: ProvenanceSearchKeys,
    sales: list[ComparableSale],
    sources_queried: list[str],
    sources_failed: list[str],
    rejected_counts: list[int],
) -> None:
    """Query Wikidata for sale-price data (P2296 estimated value, P1088 catalog price)."""
    import time

    from artgents.clients.wikidata import WikidataClient

    # --- Guard: skip for non-specific artists ---
    artist = search_keys.primary_artist_attribution
    if not _is_specific_artist(artist):
        logger.info(
            "Wikidata sales: skipping — attribution '{}' is not a specific artist name",
            artist,
        )
        sources_queried.append("wikidata")
        return

    # Strip attribution prefixes for SPARQL label matching
    search_artist = artist
    for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
        if search_artist.startswith(prefix):
            search_artist = search_artist[len(prefix):]
            break

    # Escape quotes for SPARQL
    escaped_artist = search_artist.replace('"', '\\"')

    # Build inline SPARQL query targeting sale-price properties
    sparql = f"""\
SELECT DISTINCT ?item ?itemLabel ?price ?currency ?currencyLabel ?date
WHERE {{
  ?artist rdfs:label "{escaped_artist}"@en .
  ?artist wdt:P106 wd:Q1028181 .
  ?item wdt:P170 ?artist .
  ?item wdt:P31/wdt:P279* wd:Q3305213 .
  OPTIONAL {{
    ?item wdt:P2296 ?price .
  }}
  OPTIONAL {{
    ?item p:P2296 ?priceStatement .
    ?priceStatement pq:P3005 ?currency .
    ?priceStatement pq:P585 ?date .
  }}
  OPTIONAL {{
    ?item wdt:P1088 ?price .
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}"""

    start = time.perf_counter()
    try:
        async with WikidataClient() as client:
            data = await client._execute_sparql(sparql)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("Wikidata sales query completed in {:.0f}ms", elapsed_ms)

        bindings = data.get("results", {}).get("bindings", [])

        for binding in bindings:
            # Extract entity URL
            item_url = binding.get("item", {}).get("value", "")
            if not item_url or not _is_valid_url(item_url):
                rejected_counts[0] += 1
                continue

            item_label = binding.get("itemLabel", {}).get("value", "")

            # Extract price (may be None if OPTIONAL didn't match)
            price_raw = binding.get("price", {}).get("value")
            price_usd: float | None = None
            if price_raw:
                try:
                    price_usd = float(price_raw)
                except (ValueError, TypeError):
                    price_usd = None

            # Extract date
            date_raw = binding.get("date", {}).get("value")
            sale_date: str | None = None
            if date_raw:
                sale_date = date_raw[:10]  # YYYY-MM-DD

            # Extract currency label for description
            currency_label = binding.get("currencyLabel", {}).get("value", "")

            # Build description
            description_parts = []
            if item_label:
                description_parts.append(f"'{item_label}'")
            if price_usd is not None:
                currency_tag = f" {currency_label}" if currency_label else ""
                description_parts.append(f"valued at {price_usd}{currency_tag}")
            if sale_date:
                description_parts.append(f"({sale_date})")

            description = " ".join(description_parts) if description_parts else item_url

            # Extract entity ID from URL for scope determination
            source_entity_id = item_url if item_url.startswith("http") else None

            sales.append(
                ComparableSale(
                    description=description,
                    price_usd=price_usd,
                    sale_date=sale_date,
                    source_url=item_url,
                    source_entity_id=source_entity_id,
                    source_type="wikidata",
                )
            )

        sources_queried.append("wikidata")

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Wikidata sales retrieval failed after {:.0f}ms: {}", elapsed_ms, str(exc)
        )
        sources_failed.append("wikidata")


# ---------------------------------------------------------------------------
# Parallel Search retrieval
# ---------------------------------------------------------------------------


async def _retrieve_parallel_sales(
    search_keys: ProvenanceSearchKeys,
    sales: list[ComparableSale],
    sources_queried: list[str],
    sources_failed: list[str],
) -> None:
    """Query Parallel Search for auction/sale records."""
    import time

    from artgents.clients.parallel import CreditExhaustedError, ParallelClient
    from artgents.config import settings

    if not settings.parallel_web_api_key:
        logger.warning("Parallel Search API key not configured — skipping")
        sources_failed.append("parallel_search")
        return

    # --- 1. Build artwork-specific anchor terms ---
    artist = search_keys.primary_artist_attribution
    for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
        if artist.startswith(prefix):
            artist = artist[len(prefix):]
            break

    # Filter search_keywords: drop empty, whitespace-only, and generic terms
    filtered_keywords = _filter_search_keywords(search_keys.search_keywords)

    # Build anchor terms for query construction and relevance filtering
    anchor_terms: list[str] = []
    if _is_specific_artist(search_keys.primary_artist_attribution):
        anchor_terms.append(artist.lower())
    if search_keys.work_title:
        anchor_terms.append(search_keys.work_title.lower())
    anchor_terms.extend(kw.lower() for kw in filtered_keywords)

    # If no usable anchor terms remain, skip
    if not anchor_terms:
        logger.info(
            "Parallel Search (sales): skipping — no artwork-specific anchor terms available"
        )
        sources_queried.append("parallel_search")
        return

    # --- 2. Build the query ---
    if _is_specific_artist(search_keys.primary_artist_attribution):
        query_anchor = f'"{artist}"'
    elif search_keys.work_title:
        query_anchor = f'"{search_keys.work_title}"'
    else:
        query_anchor = f'"{filtered_keywords[0]}"' if filtered_keywords else ""

    query = f'{query_anchor} sold OR "sale price" OR auction'

    start = time.perf_counter()
    client = ParallelClient(api_key=settings.parallel_web_api_key)
    try:
        result = await client.search(
            query, max_results=settings.parallel_search_max_results
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Parallel Search (sales) completed in {:.0f}ms ({} raw hits)",
            elapsed_ms,
            len(result.hits),
        )

        # --- 3. Relevance filter ---
        kept = 0
        dropped = 0
        for hit in result.hits:
            if _is_relevant_parallel_hit(hit, anchor_terms):
                # Build description from title and excerpts
                excerpt_summary = "; ".join(hit.excerpts[:2]) if hit.excerpts else ""
                title = hit.title or "Untitled page"
                description = (
                    f"{title}: {excerpt_summary}" if excerpt_summary else title
                )

                sales.append(
                    ComparableSale(
                        description=description,
                        price_usd=None,  # Parallel Search doesn't give structured prices
                        sale_date=hit.publish_date,
                        source_url=hit.url,
                        source_entity_id=None,
                        source_type="parallel_search",
                    )
                )
                kept += 1
            else:
                dropped += 1

        if dropped > 0:
            logger.info(
                "Parallel Search (sales) relevance filter: kept {}, dropped {} irrelevant hits",
                kept,
                dropped,
            )

        sources_queried.append("parallel_search")

    except CreditExhaustedError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Parallel Search credit exhausted after {:.0f}ms", elapsed_ms
        )
        sources_failed.append("parallel_search")
        raise
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Parallel Search (sales) failed after {:.0f}ms: {}",
            elapsed_ms,
            str(exc),
        )
        sources_failed.append("parallel_search")
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Sub-agent reasoning: Conservative Appraiser + Bullish Specialist
# ---------------------------------------------------------------------------


def _format_evidence_for_prompt(evidence: ComparableSalesEvidence) -> str:
    """Format comparable sales evidence as a readable numbered list for prompts."""
    if not evidence.comparable_sales:
        return "(No comparable sales retrieved — all sources failed or returned empty results)"

    lines: list[str] = []
    for i, sale in enumerate(evidence.comparable_sales, 1):
        entity_tag = (
            f" [entity: {sale.source_entity_id}]" if sale.source_entity_id else ""
        )
        price_tag = f"${sale.price_usd:,.0f}" if sale.price_usd is not None else "price unknown"
        date_tag = f", date: {sale.sale_date}" if sale.sale_date else ""
        lines.append(
            f"{i}. [{sale.source_type}]{entity_tag} {sale.description} "
            f"({price_tag}{date_tag})\n"
            f"   Source: {sale.source_url}"
        )
    return "\n".join(lines)


def _build_scope_instructions(evidence: ComparableSalesEvidence) -> str:
    """Build evidence-scope instructions for sub-agent prompts."""
    if evidence.evidence_scope == "specific_object":
        return """\
EVIDENCE SCOPE: SPECIFIC OBJECT
The evidence above has been matched to a single identified artwork via its title.
Sales data sharing the same [entity: ...] tag describe one object's price history.
However, data with a DIFFERENT entity tag or no entity tag (e.g. Parallel Search
results) should be treated as contextual market background only — not direct comps
for this specific piece."""
    else:
        return """\
EVIDENCE SCOPE: ARTIST-GENERAL (CRITICAL)
No specific artwork title was identified, OR the evidence spans multiple distinct
works by this artist. You MUST:
- Do NOT treat any single sale as "this artwork's price" — these are comparable
  sales from the artist's broader market, not the specific piece being valued.
- Frame your estimate as a range based on the artist's general market performance.
- Default to confidence "moderate" or "low" rather than "high" when the estimate
  cannot be tied to the specific object being assessed.
- Explicitly note which comparable sales inform your estimate and why they are
  appropriate reference points (similar period, medium, size, subject, etc.).

COMP SELECTION — AVOID OUTLIER ANCHORING:
- Do NOT anchor your estimate on the artist's single most extreme sale (highest
  record OR lowest clearance) unless you have specific reason to believe this
  piece belongs to that tier. A single record-breaking sale represents ONE
  exceptional object under exceptional circumstances — it is not representative
  of the artist's general market.
- Instead, select from consistently strong (for ceiling) or consistently modest
  (for floor) sales that represent a plausible PERCENTILE of the artist's market
  — e.g. "upper quartile of documented sales" not "literal all-time maximum."
- The ONLY exception: if search_keys or available evidence gives concrete reason
  to believe this specific piece is museum-quality / record-tier (e.g. a known
  masterwork title, exceptional provenance), you may reason toward the extreme
  — but this must be explicitly stated and justified in your methodology, not
  silently assumed."""


async def run_conservative_appraiser(
    evidence: ComparableSalesEvidence,
    title_risk: TitleRiskMatrix | None = None,
) -> ConservativeAppraiserOutput:
    """Run the Conservative Appraiser sub-agent (floor estimate).

    Operates like a cautious insurance appraiser — emphasizes downside
    risks and conservative comparable selection.

    Args:
        evidence: The shared ComparableSalesEvidence from gather_comps().
        title_risk: Optional TitleRiskMatrix from Provenance & Legal agent.

    Returns:
        ConservativeAppraiserOutput with floor estimate and methodology.
    """
    from artgents.clients.vertex import generate_structured
    from artgents.config import settings
    from artgents.config_loader import get_dual_agent_config

    config = get_dual_agent_config("financial_valuation")
    appraiser_variant = config.variants["conservative_appraiser"]

    # Format evidence for the prompt
    evidence_text = _format_evidence_for_prompt(evidence)
    scope_instructions = _build_scope_instructions(evidence)

    # Title risk discount instruction
    title_risk_instruction = ""
    if title_risk is not None and title_risk.requires_human_review:
        title_risk_instruction = """\

TITLE DISPUTE DISCOUNT:
The provenance assessment flagged this artwork for human review due to title risk
concerns. You MUST apply a title-dispute discount to your floor estimate — reduce
the estimate by 20-40% to account for potential restitution claims, legal costs,
or unmarketability if the title is clouded. State the discount in your methodology."""

    prompt = f"""\
You are {appraiser_variant.name}. Your stance: {appraiser_variant.stance}.

Your voice: {appraiser_variant.voice}

You are estimating the FLOOR value (conservative low estimate) for an artwork
based on the comparable sales evidence below. Your role is to emphasize downside
risks, select the most conservative comparable sales, and provide a defensible
minimum valuation.

{scope_instructions}
{title_risk_instruction}

COMPARABLE SALES EVIDENCE:
{evidence_text}

ARTWORK BEING ASSESSED:
- Artist attribution: {evidence.query_search_keys.primary_artist_attribution}
- Probable creation window: {evidence.query_search_keys.probable_creation_window}
- Style/movement: {evidence.query_search_keys.style_and_movement}

YOUR TASK:
1. Identify the most conservative comparable sales from the evidence above.
   Do NOT simply use the single cheapest/lowest comp regardless of its relevance
   — select comps that are genuinely representative of a conservative valuation
   for this artist's work in a similar medium/period, not an unrelated minor
   object or a different medium entirely (e.g. a print when assessing a painting).
2. Estimate a floor_estimate_usd — the minimum defensible value in USD.
3. Explain your methodology (which comps you relied on and why, any discounts applied).
4. Assess confidence:
   - "high": Multiple strong comps with clear prices for this specific artist/period
   - "moderate": Some relevant comps but gaps in data or uncertain applicability
   - "low": Few or no directly applicable comps; estimate is largely extrapolation
5. State your `primary_comp`: the single most important comparable sale your floor
   estimate is anchored on, in one self-contained sentence suitable for standalone
   citation (e.g. "Oilstick on Paper, $70,000-$140,000 auction estimate, Phillips
   2022"). This must make sense without reading the full methodology paragraph.

If no comparable sales have price data, estimate based on general market knowledge
for the artist's period and style, but set confidence to "low".

Return structured JSON matching the required schema."""

    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=[],
        response_schema=ConservativeAppraiserOutput,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )

    output = ConservativeAppraiserOutput.model_validate(result_dict)
    logger.info(
        "Conservative Appraiser: floor=${:,.0f}, confidence={}",
        output.floor_estimate_usd,
        output.confidence,
    )
    return output


async def run_bullish_specialist(
    evidence: ComparableSalesEvidence,
) -> BullishSpecialistOutput:
    """Run the Bullish Specialist sub-agent (ceiling estimate).

    Operates like an optimistic auction specialist — emphasizes upside
    potential and premium comparable selection.

    Args:
        evidence: The shared ComparableSalesEvidence from gather_comps().

    Returns:
        BullishSpecialistOutput with ceiling estimate and methodology.
    """
    from artgents.clients.vertex import generate_structured
    from artgents.config import settings
    from artgents.config_loader import get_dual_agent_config

    config = get_dual_agent_config("financial_valuation")
    specialist_variant = config.variants["bullish_specialist"]

    # Format evidence for the prompt
    evidence_text = _format_evidence_for_prompt(evidence)
    scope_instructions = _build_scope_instructions(evidence)

    prompt = f"""\
You are {specialist_variant.name}. Your stance: {specialist_variant.stance}.

Your voice: {specialist_variant.voice}

You are estimating the CEILING value (optimistic high estimate) for an artwork
based on the comparable sales evidence below. Your role is to identify upside
potential, premium comparable sales, and factors that could drive the price higher
at auction.

{scope_instructions}

COMPARABLE SALES EVIDENCE:
{evidence_text}

ARTWORK BEING ASSESSED:
- Artist attribution: {evidence.query_search_keys.primary_artist_attribution}
- Probable creation window: {evidence.query_search_keys.probable_creation_window}
- Style/movement: {evidence.query_search_keys.style_and_movement}

YOUR TASK:
1. Identify the highest-value comparable sales from the evidence above.
   Do NOT simply anchor on the artist's single all-time record sale — that
   represents one exceptional object under exceptional circumstances (unique
   provenance, unique bidding competition, unique cultural moment). Instead,
   select from consistently strong sales that represent a plausible upper
   percentile of the artist's market for a representative piece in this
   medium/period. Only use a record-tier comp if you have concrete evidence
   this specific piece has record-tier characteristics — and if so, state
   that explicitly in your methodology.
2. Estimate a ceiling_estimate_usd — the maximum reasonable value in USD if the
   artwork were sold under favorable conditions (major auction house, good provenance,
   competitive bidding).
3. Explain your methodology (which comps you relied on, premium factors considered,
   and WHY the selected comps are representative rather than outliers).
4. Assess confidence:
   - "high": Multiple strong comps with clear prices for this specific artist/period
   - "moderate": Some relevant comps but gaps in data or uncertain applicability
   - "low": Few or no directly applicable comps; estimate is largely extrapolation
5. State your `primary_comp`: the single most important comparable sale your ceiling
   estimate is anchored on, in one self-contained sentence suitable for standalone
   citation (e.g. "Nymphéas, $84.7M, Christie's 2018"). This must make sense
   without reading the full methodology paragraph.

If no comparable sales have price data, estimate based on general market knowledge
for the artist's period and style, but set confidence to "low".

Return structured JSON matching the required schema."""

    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=[],
        response_schema=BullishSpecialistOutput,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )

    output = BullishSpecialistOutput.model_validate(result_dict)
    logger.info(
        "Bullish Specialist: ceiling=${:,.0f}, confidence={}",
        output.ceiling_estimate_usd,
        output.confidence,
    )
    return output


# ---------------------------------------------------------------------------
# Synthesis: plain Python logic, not LLM
# ---------------------------------------------------------------------------


def synthesize_valuation(
    conservative: ConservativeAppraiserOutput,
    bullish: BullishSpecialistOutput,
    evidence: ComparableSalesEvidence,
) -> FinancialValuationResult:
    """Synthesize the two sub-agent outputs into a FinancialValuationResult.

    This is deliberately NOT an LLM call — it's plain Python logic that
    constructs the valuation corridor from both estimates.

    Rules:
    - low_estimate_usd = conservative.floor_estimate_usd
    - high_estimate_usd = bullish.ceiling_estimate_usd
    - requires_human_review = True if:
      - evidence_scope == 'artist_general' AND < 3 comparable sales, OR
      - both confidence == 'low', OR
      - spread ratio exceeds 3x (unusually wide corridor)
    - corridor_summary: states range, flags wide spread with comp citations

    Args:
        conservative: Output from the Conservative Appraiser.
        bullish: Output from the Bullish Specialist.
        evidence: The shared comparable sales evidence.

    Returns:
        FinancialValuationResult combining both assessments and corridor.
    """
    low = conservative.floor_estimate_usd
    high = bullish.ceiling_estimate_usd

    corridor = ValuationCorridor(
        low_estimate_usd=low,
        high_estimate_usd=high,
    )

    # Determine if human review is required
    sparse_artist_general = (
        evidence.evidence_scope == "artist_general"
        and len(evidence.comparable_sales) < 3
    )
    both_low_confidence = (
        conservative.confidence == "low" and bullish.confidence == "low"
    )
    spread_ratio = high / low if low > 0 else float("inf")
    wide_spread = spread_ratio > 3.0

    requires_human_review = sparse_artist_general or both_low_confidence or wide_spread

    # Build corridor summary
    corridor_summary = (
        f"Estimated valuation corridor: ${low:,.0f} – ${high:,.0f} USD."
    )
    if wide_spread:
        floor_comp = conservative.primary_comp.strip().rstrip(".")
        ceiling_comp = bullish.primary_comp.strip().rstrip(".")
        corridor_summary += (
            f" Note: unusually wide spread (ceiling is {spread_ratio:.1f}x floor) "
            f"— indicates high market uncertainty for this piece."
            f" Floor anchored on: {floor_comp}."
            f" Ceiling anchored on: {ceiling_comp}."
        )

    if requires_human_review:
        logger.warning(
            "Valuation requires human review: sparse_general={}, both_low={}, wide_spread={}",
            sparse_artist_general,
            both_low_confidence,
            wide_spread,
        )

    return FinancialValuationResult(
        conservative_appraiser=conservative,
        bullish_specialist=bullish,
        evidence=evidence,
        valuation_corridor=corridor,
        corridor_summary=corridor_summary,
        requires_human_review=requires_human_review,
    )


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


async def assess_valuation(
    search_keys: ProvenanceSearchKeys,
    title_risk: TitleRiskMatrix | None = None,
) -> FinancialValuationResult:
    """Full financial valuation: retrieval → dual reasoning → synthesis.

    This is the single entrypoint for the Financial Valuation agent,
    consumed by pipeline.py.

    Architecture:
    1. gather_comps() — single retrieval pass across Wikidata + Parallel Search
    2. asyncio.gather(run_conservative_appraiser, run_bullish_specialist) — concurrent
    3. synthesize_valuation() — plain Python, no LLM

    Args:
        search_keys: From the Visual Art Historian agent.
        title_risk: Optional TitleRiskMatrix from Provenance & Legal agent.
            If provided and requires_human_review is True, the conservative
            appraiser applies a title-dispute discount.

    Returns:
        FinancialValuationResult with both sub-agent estimates and corridor.

    Raises:
        CreditExhaustedError: If Parallel Search credits are exhausted
            (propagated from gather_comps).
        VertexCallError: If either sub-agent's Vertex AI call fails.
    """
    logger.info(
        "Starting financial valuation for: {}",
        search_keys.primary_artist_attribution,
    )

    # Stage 1: Retrieval (shared, single pass)
    evidence = await gather_comps(search_keys)

    # Stage 2: Dual reasoning (concurrent)
    conservative_result, bullish_result = await asyncio.gather(
        run_conservative_appraiser(evidence, title_risk),
        run_bullish_specialist(evidence),
    )

    # Stage 3: Synthesis (plain Python)
    result = synthesize_valuation(conservative_result, bullish_result, evidence)

    logger.info(
        "Financial valuation complete: corridor=${:,.0f}–${:,.0f}, "
        "requires_human_review={}",
        result.valuation_corridor.low_estimate_usd,
        result.valuation_corridor.high_estimate_usd,
        result.requires_human_review,
    )

    return result
