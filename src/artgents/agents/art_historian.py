"""Visual Art Historian agent — visual/stylistic analysis of physical artworks.

Produces structured output consumed by two downstream agents:
- Provenance/Legal agent (via `search_keys`)
- Curator agent (via composition_analysis, condition_notes, stylistic_authenticity_notes)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VisualAnalysisInput(BaseModel):
    """Input for the Visual Art Historian agent.

    Requires at minimum one base64-encoded image (1–N supported).
    Multiple images are treated as multiple views of the same physical
    work (e.g. full view, signature close-up, back/condition).
    Optional metadata fields determine which prompt branch is taken:
    - If all metadata fields are None → blind discovery
    - If any metadata field is provided → verification mode
    """

    images: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more base64-encoded image strings (or GCS URI / URL references). "
            "Multiple images represent different views of the same artwork."
        ),
    )
    known_title: str | None = Field(
        default=None,
        description="Claimed title of the artwork, if available",
    )
    known_artist: str | None = Field(
        default=None,
        description="Claimed artist attribution, if available",
    )
    known_period: str | None = Field(
        default=None,
        description="Claimed period or date range, if available",
    )
    medium: str | None = Field(
        default=None,
        description="Claimed medium (e.g. 'oil on canvas'), if available",
    )


class ProvenanceSearchKeys(BaseModel):
    """Structured search keys consumed by the Provenance/Legal agent.

    These fields are optimized for downstream query construction against
    Wikidata, Met/AIC APIs, and Parallel Search.
    """

    work_title: str | None = Field(
        default=None,
        description=(
            "Title of the work. ONLY populated from user-supplied known_title "
            "or text legibly visible in the image (label, plaque, inscription). "
            "NEVER inferred from style/subject matter. None if unknown."
        ),
    )
    primary_artist_attribution: str = Field(
        ...,
        description=(
            "Artist attribution. Must be phrased as 'Attributed to...' or "
            "'Manner of...' unless a legible signature is visible in the image."
        ),
    )
    probable_creation_window: str = Field(
        ...,
        description="Estimated date range, e.g. '1910–1914'",
    )
    style_and_movement: str = Field(
        ...,
        description="Identified style/movement, e.g. 'Analytic Cubism'",
    )
    detected_signatures_or_marks: list[str] = Field(
        default_factory=list,
        description="Any legible signatures, stamps, gallery marks, or inscriptions detected",
    )
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords optimized for Wikidata/Parallel Search query construction",
    )


class VisualAnalysisOutput(BaseModel):
    """Complete output of the Visual Art Historian agent.

    Split into two groups matching the two downstream consumers:
    - search_keys: consumed by Provenance/Legal agent (runs next)
    - composition/condition/authenticity fields: consumed by Curator agent (runs last)
    """

    # Gate check: is this actually an artwork?
    is_artwork: bool = Field(
        ...,
        description=(
            "Whether the image depicts a physical artwork (painting, sculpture, etc.). "
            "Must be decided independently of style/attribution confidence."
        ),
    )
    is_artwork_reasoning: str = Field(
        ...,
        description=(
            "Brief explanation of why the image is or is not considered an artwork. "
            "E.g. 'Image shows a framed oil painting on canvas' or "
            "'Image shows a person/document/landscape photo, not an artwork'."
        ),
    )

    # Downstream Handoff 1: Provenance/Legal agent (consumed first)
    search_keys: ProvenanceSearchKeys

    # Downstream Handoff 2: Curator agent (consumed after Provenance/Legal)
    composition_analysis: str = Field(
        ...,
        description="Spatial layout, brushwork, palette, and compositional features",
    )
    condition_notes: str = Field(
        ...,
        description="Visible damage, craquelure, wear, or restoration evidence",
    )
    stylistic_authenticity_notes: str = Field(
        ...,
        description=(
            "For verification mode: states whether visual features support or conflict "
            "with the claimed attribution, flagging anomalies. "
            "For blind discovery: states stylistic confidence level."
        ),
    )


# ---------------------------------------------------------------------------
# Prompt branches
# ---------------------------------------------------------------------------

_ATTRIBUTION_CONSTRAINT = """\
CRITICAL CONSTRAINT on `primary_artist_attribution`:
- You MUST phrase the attribution as "Attributed to [Artist]", "Manner of [Artist]",
  "Circle of [Artist]", "School of [Artist]", or "Unknown artist" UNLESS you can
  clearly see a legible signature in the image.
- ONLY if a legible, readable signature is visible in the image may you state the
  artist's name as an unqualified fact (e.g. "Georges Braque").
- If no signature is visible, NEVER state the artist name as unqualified fact,
  even if the style is highly recognizable. Use "Attributed to..." phrasing."""

_CONFIDENCE_CALIBRATION = """\
CONFIDENCE CALIBRATION — you must treat these as TWO SEPARATE confidence judgments:
1. Period/style/movement confidence: CAN be high when visual evidence (technique,
   materials, iconography, palette) is strong and characteristic of a well-defined
   period or movement.
2. Specific named-artist attribution confidence: MUST default to moderate-to-low
   unless there is direct corroborating evidence (a legible signature, or known
   metadata passed in that you are verifying against). A well-reasoned stylistic
   argument for a specific artist is NOT the same as certainty — workshop/follower
   attributions are inherently contestable scholarship. Do NOT let the fluency of
   your own reasoning inflate your stated confidence in a named-artist attribution.

In `stylistic_authenticity_notes`, explicitly separate these two confidence levels
when reporting. For example: "High confidence this is a Post-Impressionist landscape
(c. 1885–1895). Moderate-low confidence in specific attribution to [Artist] — no
signature visible, attribution based on stylistic similarity to documented works."
"""

_OUTPUT_INSTRUCTIONS = """\
Return your analysis as structured JSON matching the required schema. Be specific
and evidence-based. For search_keywords, provide 5-10 terms optimized for querying
art databases (Wikidata, museum APIs, auction records).

ARTWORK GATE (decide this FIRST, before any other analysis):
- `is_artwork`: Is the photographed subject a physical artwork (painting, sculpture,
  drawing, print, etc.)? Answer true/false.
- This is NOT about confidence in attribution or style — a genuine but obscure or
  poorly photographed artwork is still an artwork (true). A clear photo of a person,
  document, landscape photo, or random object is not an artwork (false).
- `is_artwork_reasoning`: Brief explanation of your decision.
- If is_artwork is false, still fill in all other fields with best-effort values
  (the schema requires them), but downstream systems will not use them.

CRITICAL: For `work_title` in search_keys:
- Set it ONLY if you have a genuine title from: (1) the user-supplied known_title
  metadata, or (2) text you can clearly read in the image (a label, plaque, title
  card, or inscription naming the work).
- If NEITHER of those sources gives you a title, set work_title to null.
- NEVER guess or infer a title from the subject matter, style, or composition.
  "Water Lilies" is not a valid work_title just because you see water lilies —
  it must be read from a visible label or supplied as metadata."""


def _build_blind_discovery_prompt(voice: str, domain: str) -> str:
    """Build prompt for blind discovery mode (no metadata supplied).

    The model must identify visual characteristics from the image alone,
    without any prior claims to anchor on.

    Args:
        voice: Expert voice description from config.
        domain: Expert domain description from config.
    """
    return f"""\
You are a {domain} expert performing a visual analysis of a physical artwork
from photographs alone. No metadata about this work has been provided — you must
rely entirely on visual evidence.

Your voice and epistemic stance: {voice}

Your task:
1. Analyze the composition, technique, palette, brushwork, and spatial arrangement.
2. Identify the most probable artist attribution, creation period, and style/movement
   based solely on visual evidence.
3. Note any visible signatures, stamps, gallery marks, or inscriptions.
4. Assess the physical condition (craquelure, damage, wear, restoration evidence).
5. State your confidence level in the stylistic identification in
   `stylistic_authenticity_notes` — be honest about uncertainty.

{_ATTRIBUTION_CONSTRAINT}

{_CONFIDENCE_CALIBRATION}

{_OUTPUT_INSTRUCTIONS}"""


def _build_verification_prompt(
    *,
    voice: str,
    domain: str,
    known_artist: str | None = None,
    known_title: str | None = None,
    known_period: str | None = None,
    medium: str | None = None,
) -> str:
    """Build prompt for verification mode (metadata supplied).

    The model must explicitly assess whether visual evidence is CONSISTENT
    with the claimed metadata, and flag anomalies rather than echoing claims.

    Args:
        voice: Expert voice description from config.
        domain: Expert domain description from config.
        known_artist: Claimed artist, if available.
        known_title: Claimed title, if available.
        known_period: Claimed period, if available.
        medium: Claimed medium, if available.
    """
    claims: list[str] = []
    if known_artist:
        claims.append(f"- Claimed artist: {known_artist}")
    if known_title:
        claims.append(f"- Claimed title: {known_title}")
    if known_period:
        claims.append(f"- Claimed period: {known_period}")
    if medium:
        claims.append(f"- Claimed medium: {medium}")

    claims_block = "\n".join(claims)

    return f"""\
You are a {domain} expert performing a VERIFICATION analysis of a physical
artwork. The following metadata has been claimed about this work:

{claims_block}

Your voice and epistemic stance: {voice}

Your task is NOT to simply confirm these claims. Instead:
1. Analyze the visual evidence in the image independently.
2. For EACH claimed attribute, explicitly state whether the visual evidence
   SUPPORTS or CONFLICTS with the claim, citing specific visual features.
3. Flag any anomalies — stylistic inconsistencies, anachronistic techniques,
   material mismatches, or anything that does not align with what you would
   expect given the claims.
4. In `stylistic_authenticity_notes`, provide a clear verdict: are the visual
   features consistent with the claimed attribution, or are there red flags?
   Be specific about what supports or contradicts the claims.
5. Note any visible signatures, stamps, gallery marks, or inscriptions and
   whether they are consistent with the claimed artist.
6. Assess physical condition (craquelure, damage, wear, restoration evidence).

{_ATTRIBUTION_CONSTRAINT}

IMPORTANT: Do NOT simply echo the claimed metadata back as confirmed fact.
Your role is critical verification — if you cannot confirm a claim from visual
evidence, say so explicitly. An honest "insufficient visual evidence to confirm"
is far more valuable than a false confirmation.

{_CONFIDENCE_CALIBRATION}

{_OUTPUT_INSTRUCTIONS}"""


def build_prompt(input_data: "VisualAnalysisInput") -> tuple[str, str]:
    """Select and build the appropriate prompt branch.

    Loads voice/domain from config/agents.yaml via the shared config loader.

    Args:
        input_data: The analysis input (image + optional metadata).

    Returns:
        A tuple of (prompt_text, branch_name) where branch_name is one of
        "blind_discovery" or "verification".
    """
    from artgents.config_loader import get_expert_config

    config = get_expert_config("visual_art_historian")

    has_metadata = any([
        input_data.known_artist,
        input_data.known_title,
        input_data.known_period,
        input_data.medium,
    ])

    if has_metadata:
        prompt = _build_verification_prompt(
            voice=config.voice,
            domain=config.domain,
            known_artist=input_data.known_artist,
            known_title=input_data.known_title,
            known_period=input_data.known_period,
            medium=input_data.medium,
        )
        return prompt, "verification"
    else:
        prompt = _build_blind_discovery_prompt(
            voice=config.voice,
            domain=config.domain,
        )
        return prompt, "blind_discovery"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_VALID_IMAGE_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
    b"RIFF": "image/webp",  # WebP starts with RIFF....WEBP
}


class InvalidImageError(Exception):
    """Raised when image_bytes cannot be decoded or is not a valid image."""

    pass


def _validate_and_detect_mime(image_b64: str) -> tuple[bytes, str]:
    """Validate base64 image data and detect MIME type from magic bytes.

    Args:
        image_b64: Base64-encoded image string.

    Returns:
        Tuple of (raw_bytes, detected_mime_type).

    Raises:
        InvalidImageError: If the data is not valid base64 or not a
            recognized image format.
    """
    import base64
    import binascii

    # Strip optional data URI prefix (e.g. "data:image/jpeg;base64,...")
    if "," in image_b64 and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]

    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageError(f"Invalid base64 encoding: {exc}") from exc

    if len(raw) < 8:
        raise InvalidImageError(
            f"Image data too small ({len(raw)} bytes) — likely not a valid image"
        )

    # Check magic bytes
    for magic, mime in _VALID_IMAGE_MAGIC_BYTES.items():
        if raw[:len(magic)] == magic:
            return raw, mime

    raise InvalidImageError(
        "Unrecognized image format — expected JPEG, PNG, GIF, or WebP"
    )


def _validate_images(images: list[str]) -> list[tuple[str, str]]:
    """Validate all images in the list and return (b64_data, mime_type) pairs.

    Args:
        images: List of base64-encoded image strings.

    Returns:
        List of (original_b64_string, detected_mime_type) tuples, one per image.

    Raises:
        InvalidImageError: If the list is empty or any image is invalid.
    """
    if not images:
        raise InvalidImageError(
            "At least one image is required — received an empty list"
        )

    results: list[tuple[str, str]] = []
    for i, img_b64 in enumerate(images):
        try:
            _raw_bytes, mime_type = _validate_and_detect_mime(img_b64)
        except InvalidImageError as exc:
            raise InvalidImageError(
                f"Image {i + 1}/{len(images)} is invalid: {exc}"
            ) from exc
        results.append((img_b64, mime_type))

    return results


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

_LOW_CONFIDENCE_MARKERS = [
    "low confidence",
    "insufficient visual evidence",
    "cannot determine",
    "uncertain",
    "unclear",
    "unable to confirm",
    "indeterminate",
]

_ANOMALY_MARKERS = [
    "anomal",
    "inconsisten",
    "conflict",
    "red flag",
    "does not align",
    "mismatch",
    "contradict",
]


async def analyze_artwork(input_data: VisualAnalysisInput) -> VisualAnalysisOutput:
    """Analyze an artwork image and produce structured visual analysis.

    This is the single entrypoint for the Visual Art Historian agent,
    consumed by pipeline.py.

    Args:
        input_data: Images (base64 list) and optional metadata for verification.

    Returns:
        Structured analysis with search_keys for Provenance/Legal agent
        and descriptive fields for the Curator agent.

    Raises:
        InvalidImageError: If any image cannot be decoded or is not a valid format.
        VertexCallError: If the Vertex AI model call fails.
    """
    from loguru import logger

    from artgents.clients.vertex import (
        VertexCallError,  # noqa: F811 — re-export for caller convenience
        generate_structured,
        image_part_from_base64,
    )
    from artgents.config import settings
    from artgents.config_loader import get_expert_config

    # Load agent config (temperature, max_output_tokens, voice, domain)
    agent_config = get_expert_config("visual_art_historian")

    # --- 1. Input validation (pre-call, avoids wasted API calls) ---
    validated_images = _validate_images(input_data.images)
    logger.debug(
        "Validated {} image(s): {}",
        len(validated_images),
        [mime for _, mime in validated_images],
    )

    # --- 2. Build prompt (select branch) ---
    prompt, branch = build_prompt(input_data)
    logger.info("Prompt branch selected: {}", branch)

    # --- 3. Prepare image parts (all go in one call for cross-referencing) ---
    image_parts = [
        image_part_from_base64(b64_data, mime_type=mime)
        for b64_data, mime in validated_images
    ]

    # --- 4. Call Vertex AI ---
    result_dict = await generate_structured(
        model=settings.model_fast,
        prompt=prompt,
        image_parts=image_parts,
        response_schema=VisualAnalysisOutput,
        temperature=agent_config.temperature,
        max_output_tokens=agent_config.max_output_tokens,
    )

    # --- 5. Parse and validate response ---
    output = VisualAnalysisOutput.model_validate(result_dict)

    # --- 6. Log low-confidence or anomaly-flagged output ---
    authenticity_lower = output.stylistic_authenticity_notes.lower()

    is_low_confidence = any(
        marker in authenticity_lower for marker in _LOW_CONFIDENCE_MARKERS
    )
    is_anomaly_flagged = any(
        marker in authenticity_lower for marker in _ANOMALY_MARKERS
    )

    if is_low_confidence:
        logger.warning(
            "Low-confidence output detected (branch={}): {}",
            branch,
            output.stylistic_authenticity_notes[:200],
        )
    if is_anomaly_flagged:
        logger.warning(
            "Anomaly flagged in output (branch={}): {}",
            branch,
            output.stylistic_authenticity_notes[:200],
        )

    return output
