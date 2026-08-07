"""Curator agent — exhibition narrative synthesis with variant-scoped voice.

Final agent in the pipeline. Consumes outputs from all upstream agents
and produces exhibition-ready narrative content with mandatory disclosures.

Architecture:
1. determine_disclosures() — plain Python, computes mandatory disclosures BEFORE any LLM call
2. _build_prompt() — assembles variant-scoped prompt with all upstream data
3. generate_structured() — Vertex AI call for narrative generation
4. Post-processing — injects computed disclosures and variant_used into output

Consumes: VisualAnalysisOutput, TitleRiskMatrix, FinancialValuationResult
Produces: CuratorOutput (exhibition_narrative, wall_label, suggested_title, disclosures, variant_used)
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from loguru import logger

from artgents.agents.art_historian import VisualAnalysisOutput
from artgents.agents.provenance_legal import TitleRiskMatrix
from artgents.agents.financial_valuation import FinancialValuationResult
from artgents.config_loader import get_selectable_variant_config, SelectableVariant
from artgents.clients.vertex import generate_structured
from artgents.config import settings


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class CuratorInput(BaseModel):
    """Input for the Curator agent.

    Aggregates all upstream agent outputs plus an optional variant selector.
    """

    visual_analysis: VisualAnalysisOutput
    title_risk: TitleRiskMatrix
    valuation: FinancialValuationResult
    variant_key: str | None = Field(
        default=None,
        description="Variant to use. None -> use YAML default_variant",
    )


class CuratorOutput(BaseModel):
    """Output of the Curator agent — exhibition-ready content."""

    exhibition_narrative: str = Field(
        ...,
        description="Full exhibition narrative suitable for catalog or wall text",
    )
    wall_label: str = Field(
        ...,
        description="Concise wall label (typically 50-100 words)",
    )
    suggested_title: str = Field(
        ...,
        description="Display title derived from subject/style if no work_title is known",
    )
    disclosures: list[str] = Field(
        default_factory=list,
        description="Mandatory disclosure statements (set by determine_disclosures, not the model)",
    )
    variant_used: str = Field(
        ...,
        description="Which curator variant was used for this output",
    )


class CuratorModelResponse(BaseModel):
    """Schema for the Vertex AI model call — narrower than CuratorOutput.

    Does NOT include `disclosures` or `variant_used` — those are set
    deterministically in Python code, not by the model. This ensures
    disclosures are a true structural guarantee: the model cannot add,
    drop, or modify them.
    """

    exhibition_narrative: str = Field(
        ...,
        description="Full exhibition narrative suitable for catalog or wall text",
    )
    wall_label: str = Field(
        ...,
        description="Concise wall label (typically 50-100 words)",
    )
    suggested_title: str = Field(
        ...,
        description="Display title derived from subject/style if no work_title is known",
    )


# ---------------------------------------------------------------------------
# Disclosure computation — PLAIN PYTHON, NOT LLM
# ---------------------------------------------------------------------------


def determine_disclosures(
    title_risk: TitleRiskMatrix,
    valuation: FinancialValuationResult,
    variant: str,
) -> list[str]:
    """Compute mandatory disclosures based on upstream risk flags.

    This runs BEFORE any model call — disclosures are deterministic
    and cannot be overridden or softened by the LLM.

    Args:
        title_risk: From the Provenance & Legal agent.
        valuation: From the Financial Valuation agent.
        variant: The selected variant key (e.g. "auction_house" or "public_gallery").

    Returns:
        List of disclosure strings (may be empty if no flags triggered).
    """
    disclosures: list[str] = []

    if title_risk.requires_human_review:
        if variant == "auction_house":
            disclosures.append(
                f"Provenance: {title_risk.synthesis_summary}"
            )
        else:  # public_gallery
            disclosures.append(
                "This work's provenance is undergoing further review."
            )

    if valuation.requires_human_review:
        if variant == "auction_house":
            disclosures.append(
                f"Valuation: {valuation.corridor_summary}"
            )
        else:
            disclosures.append(
                "This work's market valuation carries significant "
                "uncertainty pending further research."
            )

    return disclosures


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(
    input_data: CuratorInput,
    variant: SelectableVariant,
    variant_name: str,
    disclosures: list[str],
) -> str:
    """Build the variant-scoped prompt with all upstream data as context.

    Args:
        input_data: Full CuratorInput with all upstream outputs.
        variant: The selected SelectableVariant (has .name, .voice).
        variant_name: The variant key string (e.g. "auction_house").
        disclosures: Pre-computed mandatory disclosures.

    Returns:
        Complete prompt string for the Vertex AI call.
    """
    va = input_data.visual_analysis
    tr = input_data.title_risk
    val = input_data.valuation

    # --- Upstream context blocks ---
    visual_context = f"""\
VISUAL ANALYSIS:
- Artist attribution: {va.search_keys.primary_artist_attribution}
- Work title: {va.search_keys.work_title or "(unknown)"}
- Probable creation window: {va.search_keys.probable_creation_window}
- Style/movement: {va.search_keys.style_and_movement}
- Detected signatures/marks: {', '.join(va.search_keys.detected_signatures_or_marks) or "(none)"}
- Composition analysis: {va.composition_analysis}
- Condition notes: {va.condition_notes}
- Stylistic authenticity notes: {va.stylistic_authenticity_notes}"""

    provenance_context = f"""\
PROVENANCE & LEGAL ASSESSMENT:
- Compliance Auditor risk level: {tr.compliance_auditor.risk_level}
- Compliance Auditor reasoning: {tr.compliance_auditor.reasoning}
- Provenance Historian risk level: {tr.provenance_historian.risk_level}
- Provenance Historian contextual notes: {tr.provenance_historian.contextual_notes}
- Requires human review: {tr.requires_human_review}
- Synthesis summary: {tr.synthesis_summary}"""

    # --- Variant-specific valuation instructions ---
    if variant_name == "auction_house":
        valuation_context = f"""\
FINANCIAL VALUATION:
- Valuation corridor: ${val.valuation_corridor.low_estimate_usd:,.0f} – ${val.valuation_corridor.high_estimate_usd:,.0f} USD
- Corridor summary: {val.corridor_summary}
- Conservative appraiser floor: ${val.conservative_appraiser.floor_estimate_usd:,.0f} (confidence: {val.conservative_appraiser.confidence})
- Conservative appraiser methodology: {val.conservative_appraiser.methodology}
- Bullish specialist ceiling: ${val.bullish_specialist.ceiling_estimate_usd:,.0f} (confidence: {val.bullish_specialist.confidence})
- Bullish specialist methodology: {val.bullish_specialist.methodology}
- Requires human review: {val.requires_human_review}

VALUATION INSTRUCTION: You MAY weave the valuation corridor and market context
into the exhibition_narrative. Include dollar figures where appropriate for an
auction catalog audience."""
        dollar_instruction = ""
    else:  # public_gallery
        valuation_context = f"""\
FINANCIAL VALUATION:
- Requires human review: {val.requires_human_review}
- Corridor summary: {val.corridor_summary}

VALUATION INSTRUCTION: Do NOT include any dollar figures, price estimates, or
monetary values in the exhibition_narrative or wall_label. This is a public
gallery context — financial information is inappropriate for the audience."""
        dollar_instruction = """
CRITICAL: The exhibition_narrative and wall_label MUST NOT contain any dollar
figures, price ranges, or monetary values. This is a strict requirement for
the public_gallery variant."""

    # --- Disclosure block ---
    if disclosures:
        disclosure_block = f"""\
MANDATORY DISCLOSURES (REQUIRED CONTENT):
The following disclosures have been computed from upstream risk assessments.
They MUST appear verbatim in the output's `disclosures` field. You may add
additional disclosures if warranted, but these are non-negotiable:
{chr(10).join(f'  - {d}' for d in disclosures)}"""
    else:
        disclosure_block = """\
DISCLOSURES:
No mandatory disclosures were triggered by upstream risk assessments.
You may include optional disclosures if you identify concerns, but none
are required."""

    # --- Hedge language preservation ---
    hedge_instruction = f"""\
HEDGE LANGUAGE PRESERVATION (CRITICAL):
- The primary artist attribution is: "{va.search_keys.primary_artist_attribution}"
  If this is phrased as "Attributed to...", "Manner of...", "Circle of...", or
  "School of..." — you MUST preserve that hedged phrasing in ALL output fields.
  Do NOT upgrade it to a confident attribution (e.g. do NOT write "by [Artist]"
  when the upstream says "Attributed to [Artist]").
- Any provenance claim that was flagged as uncertain or requiring human review
  MUST NOT be smoothed into confident prose. If the provenance is uncertain,
  your narrative must reflect that uncertainty.
- Do NOT introduce new factual claims not present in the upstream data above.
  You are synthesizing and narrating, not researching or speculating."""

    # --- Category precision: provenance vs. authenticity ---
    category_precision = """\
CATEGORY PRECISION (CRITICAL — do NOT conflate these):
- "Provenance" / "title" concerns = ownership history, documented gaps, restitution
  risk, legal title disputes. These come from the PROVENANCE & LEGAL ASSESSMENT above.
  Use ONLY "provenance," "title," "ownership," or "legal" language to describe them.
- "Authenticity" / "attribution" concerns = whether the work is genuinely by the
  attributed artist. These come ONLY from the VISUAL ANALYSIS section above
  (specifically `stylistic_authenticity_notes` and hedged attributions).
- NEVER use "authenticity," "genuine," "attribution risk," or "forgery" language
  to describe a provenance/title finding. A disputed ownership chain does NOT imply
  the work is inauthentic — these are categorically different concerns.
- Only use authenticity/attribution language when Visual Art Historian's own output
  actually raised such a concern."""

    # --- Suggested title instruction ---
    work_title = va.search_keys.work_title
    if work_title:
        title_instruction = f"""\
SUGGESTED TITLE:
The work has a known title: "{work_title}". Use this as the suggested_title.
If you believe a more evocative display title is warranted, you may propose one
but clearly indicate the historical title is known."""
    else:
        title_instruction = """\
SUGGESTED TITLE:
No historical title is known for this work. Derive a display title from the
subject matter, style, composition, or period visible in the analysis. This
MUST be clearly framed as a suggested/descriptive title — NOT as a historical
claim. For example: "Untitled (Harbor Scene at Dusk)" or "Study in Blue and Gold"
— forms that signal the title is a curatorial convenience, not a documented fact."""

    # --- Assemble full prompt ---
    prompt = f"""\
You are {variant.name}. Your voice: {variant.voice}

You are writing exhibition content for an artwork based on the comprehensive
analysis below. Your output must include:
1. exhibition_narrative: A rich, engaging narrative suitable for a catalog entry
   or extended wall text (200-400 words).
2. wall_label: A concise label for display beside the work (50-100 words).
3. suggested_title: A display title for the work.
4. disclosures: Any mandatory or advisory disclosure statements.

{visual_context}

{provenance_context}

{valuation_context}
{dollar_instruction}

{disclosure_block}

{hedge_instruction}

{category_precision}

{title_instruction}

Return structured JSON matching the required schema."""

    return prompt


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


async def curate(input_data: CuratorInput) -> CuratorOutput:
    """Produce exhibition-ready narrative content from upstream analyses.

    This is the single entrypoint for the Curator agent, consumed by pipeline.py.

    Architecture:
    1. Load config and select variant
    2. Compute disclosures (plain Python, deterministic, before any LLM call)
    3. Build variant-scoped prompt with all upstream data
    4. Call Vertex AI for narrative generation
    5. Inject computed disclosures and variant_used into output

    Args:
        input_data: Aggregated upstream outputs plus optional variant selector.

    Returns:
        CuratorOutput with exhibition content and disclosures.

    Raises:
        KeyError: If variant_key is invalid.
        VertexCallError: If the Vertex AI call fails.
    """
    # 1. Load config
    config, variant = get_selectable_variant_config("curator", input_data.variant_key)
    variant_name = input_data.variant_key or config.default_variant

    logger.info("Curator agent: variant={}", variant_name)

    # 2. Compute disclosures (plain Python, before prompt)
    disclosures = determine_disclosures(
        input_data.title_risk, input_data.valuation, variant_name
    )

    logger.info(
        "Disclosure floor triggered: {} disclosures computed", len(disclosures)
    )

    # 3. Build variant-scoped prompt
    prompt = _build_prompt(input_data, variant, variant_name, disclosures)

    # 4. Call Vertex AI (uses narrow schema — no disclosures/variant_used)
    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=[],
        response_schema=CuratorModelResponse,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )

    # 5. Construct final output: model's prose + computed disclosures + variant
    model_response = CuratorModelResponse.model_validate(result_dict)

    output = CuratorOutput(
        exhibition_narrative=model_response.exhibition_narrative,
        wall_label=model_response.wall_label,
        suggested_title=model_response.suggested_title,
        disclosures=disclosures,
        variant_used=variant_name,
    )

    return output
