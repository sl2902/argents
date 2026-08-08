"""Provenance & Legal agent — dual-agent title risk assessment.

Architecture: retrieval-then-dual-reasoning
1. gather_evidence() → EvidenceBundle (one pass, shared)
2. run_compliance_auditor() + run_provenance_historian() (concurrent, asyncio.gather)
3. synthesize_title_risk() → TitleRiskMatrix (plain Python, not LLM)

Consumes: ProvenanceSearchKeys (from Visual Art Historian)
Produces: TitleRiskMatrix (consumed by Curator agent)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from artgents.agents.art_historian import ProvenanceSearchKeys


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------


class RetrievedFact(BaseModel):
    """A single provenance-relevant fact with a cited source.

    Every factual claim must carry a real source_url — no claim is
    asserted without one.
    """

    claim: str = Field(
        ..., description="The factual claim (e.g. 'Owned by X from 1920-1945')"
    )
    source_url: str = Field(
        ..., description="URL where this fact can be verified"
    )
    source_type: Literal["wikidata", "met", "aic", "parallel_search"] = Field(
        ..., description="Which data source produced this fact"
    )
    source_entity_id: str | None = Field(
        default=None,
        description=(
            "Stable identifier of the specific object this fact came from "
            "(Wikidata QID, AIC object ID, Met object ID). None for facts "
            "with no single identifiable object (most Parallel Search hits)."
        ),
    )


class EvidenceBundle(BaseModel):
    """All retrieved evidence for a single provenance assessment.

    Produced once by gather_evidence() and shared identically between
    both sub-agents — they reason over the same facts.
    """

    retrieved_facts: list[RetrievedFact] = Field(default_factory=list)
    query_search_keys: ProvenanceSearchKeys = Field(
        ..., description="The search keys used for retrieval (traceability)"
    )
    sources_queried: list[str] = Field(
        default_factory=list,
        description="Which sources were successfully queried (e.g. ['wikidata', 'met', 'parallel_search'])",
    )
    sources_failed: list[str] = Field(
        default_factory=list,
        description="Which sources failed or timed out",
    )
    evidence_scope: Literal["specific_object", "artist_general"] = Field(
        default="artist_general",
        description=(
            "Whether evidence pertains to one specific identified object "
            "('specific_object' — work_title known AND matched to a single entity) "
            "or spans multiple works by the artist ('artist_general' — no title, "
            "or no confident single-entity match)."
        ),
    )
    rejected_fact_count: int = Field(
        default=0,
        description=(
            "Number of facts dropped during retrieval due to validation failures "
            "(e.g. malformed source_url). Non-zero indicates data quality issues "
            "in upstream sources."
        ),
    )


# ---------------------------------------------------------------------------
# Sub-agent output models
# ---------------------------------------------------------------------------


class OwnershipGap(BaseModel):
    """An identified gap in the ownership history."""

    gap_description: str = Field(
        ..., description="Description of the gap (e.g. 'No documented owner 1938-1950')"
    )
    approximate_window: str = Field(
        ..., description="Date range of the gap (e.g. '1938–1950')"
    )
    is_high_risk_period: bool = Field(
        ...,
        description=(
            "True if the gap falls in a known high-risk period: "
            "WWII-era (1933-1945) or pre-1970 UNESCO export"
        ),
    )


class ComplianceAuditorOutput(BaseModel):
    """Output of the Compliance Auditor sub-agent (skeptic stance).

    Operates like a buyer's title attorney — treats any unverified gap,
    especially in high-risk periods, as a restitution/forfeiture risk.
    """

    identified_gaps: list[OwnershipGap] = Field(default_factory=list)
    risk_level: Literal["low", "moderate", "red_flag"] = Field(
        ..., description="Overall risk assessment from the skeptic perspective"
    )
    reasoning: str = Field(
        ..., description="Explanation of the skeptical risk assessment"
    )


class ProvenanceHistorianOutput(BaseModel):
    """Output of the Provenance Historian sub-agent (advocate stance).

    Contextualizes gaps within historical norms without dismissing
    genuine red flags.
    """

    contextual_notes: str = Field(
        ...,
        description="Historical context for identified gaps (does NOT dismiss red flags)",
    )
    cited_evidence: list[RetrievedFact] = Field(
        default_factory=list,
        description=(
            "Every retrieved fact that the Historian's reasoning references or "
            "relies on in contextual_notes — whether it supports clean ownership "
            "OR documents a risk-relevant finding. This is symmetric: not limited "
            "to exculpatory evidence."
        ),
    )
    risk_level: Literal["low", "moderate", "red_flag"] = Field(
        ..., description="Independent risk assessment from the advocate perspective"
    )


# ---------------------------------------------------------------------------
# Synthesized output
# ---------------------------------------------------------------------------


class TitleRiskMatrix(BaseModel):
    """Final synthesized output of the Provenance & Legal agent.

    Presents both sub-agent readings plus a synthesis — does not average
    them into a single score that erases disagreement.
    """

    compliance_auditor: ComplianceAuditorOutput
    provenance_historian: ProvenanceHistorianOutput
    evidence_bundle: EvidenceBundle
    requires_human_review: bool = Field(
        ...,
        description=(
            "True if the two sub-agents disagree on risk_level, "
            "or if either flags 'red_flag'"
        ),
    )
    synthesis_summary: str = Field(
        ...,
        description=(
            "Short synthesized read stating whether the sub-agents agree "
            "or disagree, and the overall posture — does not average away "
            "a disagreement"
        ),
    )


# ---------------------------------------------------------------------------
# Retrieval: gather_evidence()
# ---------------------------------------------------------------------------


async def gather_evidence(
    search_keys: ProvenanceSearchKeys,
    on_progress: "Callable[[str], None] | None" = None,
) -> EvidenceBundle:
    """Query all external sources and assemble an EvidenceBundle.

    Calls Wikidata, Met/AIC, and Parallel Search ONCE, collecting
    provenance-relevant facts. If any individual source fails, logs at
    ERROR and continues with partial evidence.

    Args:
        search_keys: From the Visual Art Historian agent.

    Returns:
        EvidenceBundle with all retrieved facts and source status.
    """
    import asyncio
    import time

    from loguru import logger

    facts: list[RetrievedFact] = []
    sources_queried: list[str] = []
    sources_failed: list[str] = []
    rejected_counts: list[int] = [0]  # mutable container for concurrent tasks

    # Run all retrievals concurrently
    wikidata_task = asyncio.create_task(
        _retrieve_wikidata(search_keys, facts, sources_queried, sources_failed, rejected_counts)
    )
    met_task = asyncio.create_task(
        _retrieve_met(search_keys, facts, sources_queried, sources_failed)
    )
    aic_task = asyncio.create_task(
        _retrieve_aic(search_keys, facts, sources_queried, sources_failed)
    )
    parallel_task = asyncio.create_task(
        _retrieve_parallel(search_keys, facts, sources_queried, sources_failed)
    )

    await asyncio.gather(wikidata_task, met_task, aic_task, parallel_task)

    logger.info(
        "Evidence gathered: {} facts from {} sources (failed: {})",
        len(facts),
        sources_queried,
        sources_failed,
    )

    if on_progress:
        try:
            on_progress(f"Retrieved {len(facts)} provenance facts from {len(sources_queried)} sources")
        except Exception:
            pass

    return EvidenceBundle(
        retrieved_facts=facts,
        query_search_keys=search_keys,
        sources_queried=sources_queried,
        sources_failed=sources_failed,
        evidence_scope=_determine_evidence_scope(search_keys, facts),
        rejected_fact_count=rejected_counts[0],
    )


def _determine_evidence_scope(
    search_keys: ProvenanceSearchKeys,
    facts: list[RetrievedFact],
) -> str:
    """Determine whether evidence is specific-object or artist-general.

    Returns "specific_object" only if:
    - work_title is present AND
    - At least one fact has a source_entity_id (confident single match)
    - All facts with source_entity_id share the same ID (single entity)

    Otherwise returns "artist_general".
    """
    if not search_keys.work_title:
        return "artist_general"

    # Check if we have a confident single-entity match
    entity_ids = {
        f.source_entity_id for f in facts
        if f.source_entity_id is not None
    }

    if len(entity_ids) == 1:
        return "specific_object"

    # Multiple entity IDs or no entity IDs → artist_general
    return "artist_general"


async def _retrieve_wikidata(
    search_keys: ProvenanceSearchKeys,
    facts: list[RetrievedFact],
    sources_queried: list[str],
    sources_failed: list[str],
    rejected_counts: list[int] | None = None,
) -> None:
    """Query Wikidata for provenance information."""
    import time

    from loguru import logger

    from artgents.clients.wikidata import WikidataClient

    # --- Guard: skip artist-driven query for non-specific attributions ---
    artist = search_keys.primary_artist_attribution
    if not _is_specific_artist(artist):
        logger.info(
            "Wikidata: skipping artist-driven query — attribution '{}' is not "
            "a specific artist name (would produce spurious/unrelated results)",
            artist,
        )
        sources_queried.append("wikidata")  # We "queried" but intentionally got nothing
        return

    start = time.perf_counter()
    try:
        async with WikidataClient() as client:
            result = await client.query_provenance(
                artist=search_keys.primary_artist_attribution,
                creation_window=search_keys.probable_creation_window,
                keywords=search_keys.search_keywords,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("Wikidata query completed in {:.0f}ms", elapsed_ms)

        # Convert ownership history to RetrievedFacts
        for entry in result.ownership_history:
            owner = entry.get("owner", "Unknown")
            start_date = entry.get("start_date", "?")
            end_date = entry.get("end_date", "?")
            source_url = entry.get("source_url", result.entity_url or "")
            if source_url and _is_valid_url(source_url):
                facts.append(RetrievedFact(
                    claim=f"Owned by {owner} ({start_date} to {end_date})",
                    source_url=source_url,
                    source_type="wikidata",
                    source_entity_id=result.entity_url,
                ))
            elif source_url:
                if rejected_counts is not None:
                    rejected_counts[0] += 1
                logger.warning("Rejected fact with malformed URL: {}", source_url)

        # Convert collections
        for entry in result.collections:
            coll = entry.get("collection_name", "")
            source_url = entry.get("source_url", result.entity_url or "")
            if coll and source_url and _is_valid_url(source_url):
                facts.append(RetrievedFact(
                    claim=f"In collection: {coll}",
                    source_url=source_url,
                    source_type="wikidata",
                    source_entity_id=result.entity_url,
                ))
            elif coll and source_url:
                if rejected_counts is not None:
                    rejected_counts[0] += 1
                logger.warning("Rejected fact with malformed URL: {}", source_url)

        # Convert significant events (theft, restitution, etc.)
        for entry in result.significant_events:
            event = entry.get("event_label", "")
            date = entry.get("date", "")
            source_url = entry.get("source_url", result.entity_url or "")
            if event and source_url and _is_valid_url(source_url):
                date_str = f" ({date})" if date else ""
                facts.append(RetrievedFact(
                    claim=f"Significant event: {event}{date_str}",
                    source_url=source_url,
                    source_type="wikidata",
                    source_entity_id=result.entity_url,
                ))
            elif event and source_url:
                if rejected_counts is not None:
                    rejected_counts[0] += 1
                logger.warning("Rejected fact with malformed URL: {}", source_url)

        sources_queried.append("wikidata")

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Wikidata retrieval failed after {:.0f}ms: {}", elapsed_ms, str(exc)
        )
        sources_failed.append("wikidata")


# Names that are NOT specific artist attributions — these should not be
# sent as rdfs:label matches against Wikidata.
_NON_SPECIFIC_ARTISTS = {
    "unknown",
    "unknown artist",
    "unidentified",
    "unidentified artist",
    "anonymous",
    "anonymous artist",
}


def _is_specific_artist(attribution: str) -> bool:
    """Check if an artist attribution is a specific, searchable name.

    Returns False for generic placeholders like "Unknown", "Unknown artist",
    "Anonymous", empty strings, etc. — these should not be used as Wikidata
    label matches since they'd either match nothing or match the wrong entity.
    """
    if not attribution or not attribution.strip():
        return False

    # Strip attribution prefixes before checking
    cleaned = attribution
    for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    return cleaned.strip().lower() not in _NON_SPECIFIC_ARTISTS


def _is_valid_url(url: str) -> bool:
    """Basic URL validation — rejects obviously malformed URLs.

    Checks that the URL starts with http:// or https:// and doesn't
    contain obviously garbled domain names.
    """
    if not url:
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    # Check for garbled domains (digits inserted into TLD, e.g. "wikidata.2org")
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        # TLD should be purely alphabetic (no digits)
        parts = parsed.netloc.split(".")
        tld = parts[-1] if parts else ""
        if not tld.isalpha():
            return False
    except Exception:
        return False
    return True


async def _retrieve_met(
    search_keys: ProvenanceSearchKeys,
    facts: list[RetrievedFact],
    sources_queried: list[str],
    sources_failed: list[str],
) -> None:
    """Query Met Museum for provenance-relevant objects."""
    import time

    from loguru import logger

    from artgents.clients.met import MetClient

    start = time.perf_counter()
    try:
        async with MetClient() as client:
            # Search for the artist
            query = search_keys.primary_artist_attribution
            # Strip attribution phrasing for search
            for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
                if query.startswith(prefix):
                    query = query[len(prefix):]
                    break

            object_ids = await client.search(query)

            # Fetch first few objects for provenance info
            for obj_id in object_ids[:5]:
                try:
                    raw_data = await client.get_object_raw(obj_id)
                    met_url = f"https://www.metmuseum.org/art/collection/search/{obj_id}"
                    if raw_data.title:
                        facts.append(RetrievedFact(
                            claim=(
                                f"Met Museum holds '{raw_data.title}' "
                                f"by {raw_data.artist_display_name} "
                                f"({raw_data.object_date})"
                            ),
                            source_url=met_url,
                            source_type="met",
                            source_entity_id=str(obj_id),
                        ))
                except Exception:
                    continue  # Skip individual object failures

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("Met Museum query completed in {:.0f}ms", elapsed_ms)
        sources_queried.append("met")

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Met Museum retrieval failed after {:.0f}ms: {}", elapsed_ms, str(exc)
        )
        sources_failed.append("met")


async def _retrieve_aic(
    search_keys: ProvenanceSearchKeys,
    facts: list[RetrievedFact],
    sources_queried: list[str],
    sources_failed: list[str],
) -> None:
    """Query Art Institute of Chicago for provenance-relevant objects."""
    import time

    from loguru import logger

    from artgents.clients.aic import AICClient

    start = time.perf_counter()
    try:
        async with AICClient() as client:
            # Search for the artist
            query = search_keys.primary_artist_attribution
            for prefix in ["Attributed to ", "Manner of ", "Circle of ", "School of "]:
                if query.startswith(prefix):
                    query = query[len(prefix):]
                    break

            object_ids = await client.search(query)

            # Fetch first few objects for provenance info
            for obj_id in object_ids[:5]:
                try:
                    obj = await client.get_object_raw(obj_id)
                    aic_url = f"https://www.artic.edu/artworks/{obj_id}"
                    if obj.provenance_text:
                        facts.append(RetrievedFact(
                            claim=(
                                f"AIC provenance for '{obj.title}': "
                                f"{obj.provenance_text[:200]}"
                            ),
                            source_url=aic_url,
                            source_type="aic",
                            source_entity_id=str(obj_id),
                        ))
                    elif obj.title:
                        facts.append(RetrievedFact(
                            claim=(
                                f"AIC holds '{obj.title}' "
                                f"by {obj.artist_display} ({obj.date_display})"
                            ),
                            source_url=aic_url,
                            source_type="aic",
                            source_entity_id=str(obj_id),
                        ))
                except Exception:
                    continue

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("AIC query completed in {:.0f}ms", elapsed_ms)
        sources_queried.append("aic")

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "AIC retrieval failed after {:.0f}ms: {}", elapsed_ms, str(exc)
        )
        sources_failed.append("aic")


async def _retrieve_parallel(
    search_keys: ProvenanceSearchKeys,
    facts: list[RetrievedFact],
    sources_queried: list[str],
    sources_failed: list[str],
) -> None:
    """Query Parallel Search for theft/plunder press coverage."""
    import time

    from loguru import logger

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

    # Filter search_keywords: drop empty, whitespace-only, and non-identifying terms
    filtered_keywords = _filter_search_keywords(search_keys.search_keywords)

    # Build the set of anchor terms for both query construction and relevance filtering
    anchor_terms: list[str] = []
    if _is_specific_artist(search_keys.primary_artist_attribution):
        anchor_terms.append(artist.lower())
    if search_keys.work_title:
        anchor_terms.append(search_keys.work_title.lower())
    anchor_terms.extend(kw.lower() for kw in filtered_keywords)

    # If no usable anchor terms remain, skip Parallel Search entirely
    if not anchor_terms:
        logger.info(
            "Parallel Search: skipping — no artwork-specific anchor terms "
            "available (empty/placeholder search_keywords and no specific artist/title)"
        )
        sources_queried.append("parallel_search")
        return

    # --- 2. Build the query ---
    # Use the artist name (if specific) as the primary quoted term
    if _is_specific_artist(search_keys.primary_artist_attribution):
        query_anchor = f'"{artist}"'
    elif search_keys.work_title:
        query_anchor = f'"{search_keys.work_title}"'
    else:
        # Use the strongest filtered keyword
        query_anchor = f'"{filtered_keywords[0]}"' if filtered_keywords else ""

    query = (
        f'{query_anchor} stolen OR looted OR plunder OR restitution OR confiscated '
        f"site:fbi.gov OR site:archives.gov OR site:wikipedia.org"
    )

    start = time.perf_counter()
    client = ParallelClient(api_key=settings.parallel_web_api_key)
    try:
        result = await client.search(query, max_results=settings.parallel_search_max_results)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Parallel Search completed in {:.0f}ms ({} raw hits)",
            elapsed_ms,
            len(result.hits),
        )

        # --- 3. Relevance filter: only keep hits that overlap with anchor terms ---
        kept = 0
        dropped = 0
        for hit in result.hits:
            if _is_relevant_parallel_hit(hit, anchor_terms):
                excerpt_summary = "; ".join(hit.excerpts[:2]) if hit.excerpts else ""
                title = hit.title or "Untitled page"
                facts.append(RetrievedFact(
                    claim=f"{title}: {excerpt_summary}" if excerpt_summary else title,
                    source_url=hit.url,
                    source_type="parallel_search",
                ))
                kept += 1
            else:
                dropped += 1

        if dropped > 0:
            logger.info(
                "Parallel Search relevance filter: kept {}, dropped {} irrelevant hits",
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
        # Re-raise — credit exhaustion is distinct from "no results"
        raise
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "Parallel Search failed after {:.0f}ms: {}", elapsed_ms, str(exc)
        )
        sources_failed.append("parallel_search")
    finally:
        await client.close()


def _filter_search_keywords(keywords: list[str]) -> list[str]:
    """Filter search_keywords to only usable, artwork-identifying terms.

    Drops empty strings, whitespace-only strings, and overly generic
    placeholders that would not meaningfully narrow a search.
    """
    _GENERIC_PLACEHOLDERS = {
        "unknown", "painting", "artwork", "art", "canvas",
        "oil", "oil painting", "sculpture", "drawing",
    }

    filtered = []
    for kw in keywords:
        cleaned = kw.strip().lower()
        if not cleaned:
            continue
        if cleaned in _GENERIC_PLACEHOLDERS:
            continue
        filtered.append(cleaned)
    return filtered


def _is_relevant_parallel_hit(
    hit: "SearchHit",
    anchor_terms: list[str],
) -> bool:
    """Check if a Parallel Search hit is relevant to the artwork being assessed.

    A hit is considered relevant if its title, URL, or excerpts contain
    at least one of the anchor terms (artist name, work title, or filtered
    search keywords). This is a plain keyword-overlap check, not an LLM call.
    """
    # Build a single searchable text from the hit
    searchable_parts = []
    if hit.title:
        searchable_parts.append(hit.title.lower())
    if hit.url:
        searchable_parts.append(hit.url.lower())
    if hit.excerpts:
        searchable_parts.extend(exc.lower() for exc in hit.excerpts)
    searchable_text = " ".join(searchable_parts)

    # Check if any anchor term appears in the hit
    return any(term in searchable_text for term in anchor_terms)


# ---------------------------------------------------------------------------
# Sub-agent reasoning: Compliance Auditor + Provenance Historian
# ---------------------------------------------------------------------------


async def run_compliance_auditor(bundle: EvidenceBundle) -> ComplianceAuditorOutput:
    """Run the Compliance Auditor sub-agent (skeptic stance).

    Operates like a buyer's title attorney — treats any unverified
    ownership gap, especially in high-risk periods, as a restitution/
    forfeiture risk.

    Args:
        bundle: The shared EvidenceBundle from gather_evidence().

    Returns:
        ComplianceAuditorOutput with identified gaps and risk assessment.
    """
    from loguru import logger

    from artgents.clients.vertex import generate_structured
    from artgents.config import settings
    from artgents.config_loader import get_dual_agent_config

    config = get_dual_agent_config("provenance_legal")
    auditor_variant = config.variants["compliance_auditor"]

    # Format evidence for the prompt
    evidence_text = _format_evidence_for_prompt(bundle)
    scope_instructions = _build_scope_instructions(bundle)

    prompt = f"""\
You are {auditor_variant.name}. Your stance: {auditor_variant.stance}.

Your voice: {auditor_variant.voice}

You are analyzing the provenance evidence below for title risk. Your role is to
identify ownership-history gaps and assess whether they fall in known high-risk
periods:
- WWII-era (1933-1945): Nazi confiscation, looting, forced sales
- Pre-1970 UNESCO Convention: unregulated export from source countries

{scope_instructions}

EVIDENCE RETRIEVED:
{evidence_text}

ARTWORK BEING ASSESSED:
- Artist attribution: {bundle.query_search_keys.primary_artist_attribution}
- Probable creation window: {bundle.query_search_keys.probable_creation_window}
- Style/movement: {bundle.query_search_keys.style_and_movement}

YOUR TASK:
1. Identify any gaps in the ownership timeline where no documented owner exists.
2. For each gap, determine if it falls in a high-risk period (1933-1945 or pre-1970).
3. Assess overall risk_level:
   - "low": No gaps, or gaps outside high-risk periods with reasonable explanations
   - "moderate": Gaps exist in or near high-risk periods, but no direct evidence of
     illicit transfer
   - "red_flag": Gaps coincide with high-risk periods AND retrieved evidence
     suggests possible confiscation, looting, or forced sale
4. Provide your reasoning — be specific about which evidence supports your assessment.
   Do NOT assert a theft/plunder flag unless specific retrieved evidence supports it.

Return structured JSON matching the required schema."""

    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=[],
        response_schema=ComplianceAuditorOutput,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )

    output = ComplianceAuditorOutput.model_validate(result_dict)
    logger.info("Compliance Auditor risk_level: {}", output.risk_level)
    return output


async def run_provenance_historian(bundle: EvidenceBundle) -> ProvenanceHistorianOutput:
    """Run the Provenance Historian sub-agent (advocate stance).

    Contextualizes archival gaps within historical norms without
    dismissing genuine red flags.

    Args:
        bundle: The shared EvidenceBundle from gather_evidence().

    Returns:
        ProvenanceHistorianOutput with contextual analysis.
    """
    from loguru import logger

    from artgents.clients.vertex import generate_structured
    from artgents.config import settings
    from artgents.config_loader import get_dual_agent_config

    config = get_dual_agent_config("provenance_legal")
    historian_variant = config.variants["provenance_historian"]

    # Format evidence for the prompt
    evidence_text = _format_evidence_for_prompt(bundle)
    scope_instructions = _build_scope_instructions(bundle)

    prompt = f"""\
You are {historian_variant.name}. Your stance: {historian_variant.stance}.

Your voice: {historian_variant.voice}

You are analyzing the provenance evidence below. Your role is to contextualize
any identified gaps within historical norms, WITHOUT dismissing genuine red flags.

{scope_instructions}

EVIDENCE RETRIEVED:
{evidence_text}

ARTWORK BEING ASSESSED:
- Artist attribution: {bundle.query_search_keys.primary_artist_attribution}
- Probable creation window: {bundle.query_search_keys.probable_creation_window}
- Style/movement: {bundle.query_search_keys.style_and_movement}

YOUR TASK:
1. Provide historical context for any gaps in the ownership timeline — are they
   consistent with ordinary record-keeping norms of the period (e.g. uncatalogued
   family inheritance in interwar Europe, private collections not documented until
   later)?
2. Identify any retrieved evidence that supports uninterrupted or well-documented
   ownership — cite specific facts from the evidence above (include their source_url).
3. Assess overall risk_level independently:
   - "low": Gaps, if any, are well-explained by historical norms and no evidence
     contradicts clean ownership
   - "moderate": Some gaps are harder to explain by norms alone, but no direct
     evidence of illicit transfer
   - "red_flag": Evidence directly suggests confiscation, looting, or forced sale
     that cannot be explained away by historical norms
4. Do NOT dismiss a genuine red flag just to provide a hopeful reading — your role
   is to contextualize, not to exonerate.

For cited_evidence, include EVERY fact from the evidence bundle that your reasoning
references or relies on in contextual_notes — whether it supports clean ownership
OR documents a risk-relevant finding. This list must be symmetric: if you discuss
a fact in your notes (even a damaging one like a documented confiscation), include
it in cited_evidence with its original source_url.

Return structured JSON matching the required schema."""

    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=[],
        response_schema=ProvenanceHistorianOutput,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )

    output = ProvenanceHistorianOutput.model_validate(result_dict)
    logger.info("Provenance Historian risk_level: {}", output.risk_level)
    return output


def _format_evidence_for_prompt(bundle: EvidenceBundle) -> str:
    """Format the EvidenceBundle as a readable text block for prompts."""
    if not bundle.retrieved_facts:
        return "(No evidence retrieved — all sources failed or returned empty results)"

    lines: list[str] = []
    for i, fact in enumerate(bundle.retrieved_facts, 1):
        entity_tag = f" [entity: {fact.source_entity_id}]" if fact.source_entity_id else ""
        lines.append(
            f"{i}. [{fact.source_type}]{entity_tag} {fact.claim}\n"
            f"   Source: {fact.source_url}"
        )
    return "\n".join(lines)


def _build_scope_instructions(bundle: EvidenceBundle) -> str:
    """Build evidence-scope instructions for sub-agent prompts."""
    if bundle.evidence_scope == "specific_object":
        return """\
EVIDENCE SCOPE: SPECIFIC OBJECT
The evidence above has been matched to a single identified artwork via its title.
Facts sharing the same [entity: ...] tag describe one object's history and may be
reasoned over as a continuous ownership chain. However, facts with a DIFFERENT
entity tag or no entity tag (e.g. Parallel Search results) should NOT be merged
into that object's narrative — treat them as contextual background only."""
    else:
        return """\
EVIDENCE SCOPE: ARTIST-GENERAL (CRITICAL)
No specific artwork title was identified. The evidence above may span MULTIPLE
DISTINCT works by this artist, not one object's provenance. You MUST:
- Do NOT synthesize a single continuous ownership narrative from facts with
  different [entity: ...] tags — those describe DIFFERENT artworks.
- Frame ALL reasoning as general artist-level risk context: "this artist has
  documented instances of..." NOT "this artwork was..."
- Default to risk_level "moderate" rather than "red_flag" when the assessment
  cannot be tied to the specific object being assessed. Only use "red_flag"
  if essentially every retrieved work by this artist has plunder/theft history,
  making it genuinely impossible to express appropriate uncertainty otherwise.
- If you see ownership records, collection histories, or events: state which
  specific entity they came from, and explicitly note they may not apply to
  the artwork in question."""


# ---------------------------------------------------------------------------
# Synthesis: plain Python logic, not LLM
# ---------------------------------------------------------------------------


def synthesize_title_risk(
    auditor: ComplianceAuditorOutput,
    historian: ProvenanceHistorianOutput,
    bundle: EvidenceBundle,
) -> TitleRiskMatrix:
    """Synthesize the two sub-agent outputs into a TitleRiskMatrix.

    This is deliberately NOT an LLM call — it's plain Python logic that
    preserves the two-agent contrast rather than averaging it away.

    Rules:
    - requires_human_review = True if risk_levels differ OR either is "red_flag"
    - synthesis_summary states explicitly whether sub-agents agree or disagree

    Args:
        auditor: Output from the Compliance Auditor.
        historian: Output from the Provenance Historian.
        bundle: The shared evidence bundle.

    Returns:
        TitleRiskMatrix combining both assessments.
    """
    from loguru import logger

    # Determine if human review is required
    levels_disagree = auditor.risk_level != historian.risk_level
    either_red_flag = (
        auditor.risk_level == "red_flag" or historian.risk_level == "red_flag"
    )
    requires_human_review = levels_disagree or either_red_flag

    # Build synthesis summary
    if auditor.risk_level == historian.risk_level:
        if auditor.risk_level == "low":
            synthesis_summary = (
                "Both sub-agents agree: LOW risk. No significant ownership gaps "
                "or red flags identified. Clean provenance within the limits of "
                "available public records."
            )
        elif auditor.risk_level == "moderate":
            synthesis_summary = (
                "Both sub-agents agree: MODERATE risk. Some ownership gaps or "
                "uncertainties exist, but neither sub-agent identifies direct "
                "evidence of illicit transfer. Further due diligence recommended."
            )
        else:  # both red_flag
            synthesis_summary = (
                "Both sub-agents agree: RED FLAG. Significant provenance concerns "
                "identified by both the compliance auditor and the historian. "
                "Formal Art Loss Register / Interpol check strongly recommended "
                "before proceeding."
            )
    else:
        # Disagreement — state both positions
        synthesis_summary = (
            f"Sub-agents DISAGREE on risk level. "
            f"Compliance Auditor assessed: {auditor.risk_level.upper()}. "
            f"Provenance Historian assessed: {historian.risk_level.upper()}. "
            f"This disagreement itself warrants human expert review — "
            f"the auditor's skeptical reading and the historian's contextual "
            f"reading should both be considered before a decision."
        )

    if requires_human_review:
        logger.warning(
            "Title risk requires human review: auditor={}, historian={}, disagree={}",
            auditor.risk_level,
            historian.risk_level,
            levels_disagree,
        )

    return TitleRiskMatrix(
        compliance_auditor=auditor,
        provenance_historian=historian,
        evidence_bundle=bundle,
        requires_human_review=requires_human_review,
        synthesis_summary=synthesis_summary,
    )


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


async def assess_provenance(
    search_keys: ProvenanceSearchKeys,
    on_progress: "Callable[[str], None] | None" = None,
) -> TitleRiskMatrix:
    """Full provenance assessment: retrieval → dual reasoning → synthesis.

    This is the single entrypoint for the Provenance & Legal agent,
    consumed by pipeline.py.

    Architecture:
    1. gather_evidence() — single retrieval pass across all sources
    2. asyncio.gather(run_compliance_auditor, run_provenance_historian) — concurrent
    3. synthesize_title_risk() — plain Python, no LLM

    Args:
        search_keys: From the Visual Art Historian agent.
        on_progress: Optional progress callback.

    Returns:
        TitleRiskMatrix with both sub-agent assessments and synthesis.

    Raises:
        CreditExhaustedError: If Parallel Search credits are exhausted
            (propagated from gather_evidence).
        VertexCallError: If either sub-agent's Vertex AI call fails.
    """
    import asyncio
    from typing import Callable

    from loguru import logger

    def _progress(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    logger.info(
        "Starting provenance assessment for: {}",
        search_keys.primary_artist_attribution,
    )

    # Stage 1: Retrieval (shared, single pass)
    bundle = await gather_evidence(search_keys, on_progress=_progress)

    # Stage 2: Dual reasoning (concurrent)
    auditor_result, historian_result = await asyncio.gather(
        run_compliance_auditor(bundle),
        run_provenance_historian(bundle),
    )
    _progress("Provenance sub-agents completed their assessments")

    # Stage 3: Synthesis (plain Python)
    result = synthesize_title_risk(auditor_result, historian_result, bundle)

    logger.info(
        "Provenance assessment complete: requires_human_review={}",
        result.requires_human_review,
    )

    return result
