"""Unit tests for the Curator agent.

All tests use mocked clients — no real API calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artgents.agents.curator import (
    CuratorInput,
    CuratorOutput,
    _build_prompt,
    curate,
    determine_disclosures,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_visual_mock(attribution: str = "Attributed to Claude Monet") -> MagicMock:
    """Create a minimal VisualAnalysisOutput mock."""
    visual = MagicMock()
    visual.search_keys.primary_artist_attribution = attribution
    visual.search_keys.work_title = None
    visual.search_keys.probable_creation_window = "1900-1910"
    visual.search_keys.style_and_movement = "Impressionism"
    visual.search_keys.detected_signatures_or_marks = []
    visual.composition_analysis = "Loose brushwork..."
    visual.condition_notes = "Minor craquelure"
    visual.stylistic_authenticity_notes = "Moderate confidence"
    return visual


def _make_title_risk_mock(requires_review: bool = True) -> MagicMock:
    """Create a minimal TitleRiskMatrix mock."""
    title_risk = MagicMock()
    title_risk.requires_human_review = requires_review
    title_risk.synthesis_summary = "Sub-agents disagree on risk."
    title_risk.compliance_auditor.risk_level = "moderate"
    title_risk.compliance_auditor.reasoning = "Some compliance concern"
    title_risk.provenance_historian.risk_level = "low"
    title_risk.provenance_historian.contextual_notes = "Limited provenance records"
    return title_risk


def _make_valuation_mock(requires_review: bool = True) -> MagicMock:
    """Create a minimal FinancialValuationResult mock."""
    valuation = MagicMock()
    valuation.requires_human_review = requires_review
    valuation.corridor_summary = "Estimated corridor: $50K-$8M"
    valuation.valuation_corridor.low_estimate_usd = 1_000_000
    valuation.valuation_corridor.high_estimate_usd = 5_000_000
    valuation.conservative_appraiser.floor_estimate_usd = 1_000_000
    valuation.conservative_appraiser.confidence = "moderate"
    valuation.conservative_appraiser.methodology = "Conservative floor estimate"
    valuation.bullish_specialist.ceiling_estimate_usd = 5_000_000
    valuation.bullish_specialist.confidence = "high"
    valuation.bullish_specialist.methodology = "Bullish ceiling estimate"
    return valuation


def _make_curator_input_mock(
    variant_key: str | None = None,
    attribution: str = "Attributed to Claude Monet",
    title_risk_review: bool = True,
    valuation_review: bool = True,
) -> MagicMock:
    """Create a CuratorInput-shaped mock with all upstream outputs."""
    input_mock = MagicMock()
    input_mock.visual_analysis = _make_visual_mock(attribution)
    input_mock.title_risk = _make_title_risk_mock(title_risk_review)
    input_mock.valuation = _make_valuation_mock(valuation_review)
    input_mock.variant_key = variant_key
    return input_mock


# ---------------------------------------------------------------------------
# TestDetermineDisclosures — exhaustive over all combinations
# ---------------------------------------------------------------------------


class TestDetermineDisclosures:
    """Exhaustive tests for determine_disclosures() over all risk flag × variant combos."""

    def test_auction_house_both_flags_true(self):
        """title_risk=True, valuation=True, variant='auction_house' → 2 disclosures."""
        title_risk = _make_title_risk_mock(requires_review=True)
        valuation = _make_valuation_mock(requires_review=True)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert len(disclosures) == 2
        assert any("Provenance" in d for d in disclosures)
        assert any("Valuation" in d for d in disclosures)

    def test_auction_house_title_risk_only(self):
        """title_risk=True, valuation=False, variant='auction_house' → 1 provenance disclosure."""
        title_risk = _make_title_risk_mock(requires_review=True)
        valuation = _make_valuation_mock(requires_review=False)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert len(disclosures) == 1
        assert "Provenance" in disclosures[0]

    def test_auction_house_valuation_only(self):
        """title_risk=False, valuation=True, variant='auction_house' → 1 valuation disclosure."""
        title_risk = _make_title_risk_mock(requires_review=False)
        valuation = _make_valuation_mock(requires_review=True)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert len(disclosures) == 1
        assert "Valuation" in disclosures[0]

    def test_auction_house_no_flags(self):
        """title_risk=False, valuation=False, variant='auction_house' → 0 disclosures."""
        title_risk = _make_title_risk_mock(requires_review=False)
        valuation = _make_valuation_mock(requires_review=False)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert len(disclosures) == 0

    def test_public_gallery_both_flags_true(self):
        """title_risk=True, valuation=True, variant='public_gallery' → 2 disclosures."""
        title_risk = _make_title_risk_mock(requires_review=True)
        valuation = _make_valuation_mock(requires_review=True)

        disclosures = determine_disclosures(title_risk, valuation, "public_gallery")

        assert len(disclosures) == 2
        assert any("further review" in d for d in disclosures)
        assert any("uncertainty" in d for d in disclosures)

    def test_public_gallery_title_risk_only(self):
        """title_risk=True, valuation=False, variant='public_gallery' → 1 disclosure."""
        title_risk = _make_title_risk_mock(requires_review=True)
        valuation = _make_valuation_mock(requires_review=False)

        disclosures = determine_disclosures(title_risk, valuation, "public_gallery")

        assert len(disclosures) == 1
        assert "further review" in disclosures[0]

    def test_public_gallery_valuation_only(self):
        """title_risk=False, valuation=True, variant='public_gallery' → 1 disclosure."""
        title_risk = _make_title_risk_mock(requires_review=False)
        valuation = _make_valuation_mock(requires_review=True)

        disclosures = determine_disclosures(title_risk, valuation, "public_gallery")

        assert len(disclosures) == 1
        assert "uncertainty" in disclosures[0]

    def test_public_gallery_no_flags(self):
        """title_risk=False, valuation=False, variant='public_gallery' → 0 disclosures."""
        title_risk = _make_title_risk_mock(requires_review=False)
        valuation = _make_valuation_mock(requires_review=False)

        disclosures = determine_disclosures(title_risk, valuation, "public_gallery")

        assert len(disclosures) == 0

    def test_auction_house_provenance_contains_synthesis_summary(self):
        """Auction house provenance disclosure includes synthesis_summary text."""
        title_risk = _make_title_risk_mock(requires_review=True)
        valuation = _make_valuation_mock(requires_review=False)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert "Sub-agents disagree on risk." in disclosures[0]

    def test_auction_house_valuation_contains_corridor_summary(self):
        """Auction house valuation disclosure includes corridor_summary text."""
        title_risk = _make_title_risk_mock(requires_review=False)
        valuation = _make_valuation_mock(requires_review=True)

        disclosures = determine_disclosures(title_risk, valuation, "auction_house")

        assert "Estimated corridor: $50K-$8M" in disclosures[0]


# ---------------------------------------------------------------------------
# TestModels — schema validation
# ---------------------------------------------------------------------------


class TestModels:
    """Schema validation tests for CuratorInput and CuratorOutput models."""

    def test_curator_output_valid_construction(self):
        """CuratorOutput can be constructed with all required fields."""
        output = CuratorOutput(
            exhibition_narrative="A rich narrative about the work.",
            wall_label="Test Artist, Test Work, c. 1900",
            suggested_title="Untitled Landscape",
            disclosures=["Provenance: some concern"],
            variant_used="auction_house",
        )
        assert output.exhibition_narrative == "A rich narrative about the work."
        assert output.wall_label == "Test Artist, Test Work, c. 1900"
        assert output.suggested_title == "Untitled Landscape"
        assert len(output.disclosures) == 1
        assert output.variant_used == "auction_house"

    def test_curator_input_valid_construction(self):
        """CuratorInput can be constructed with mocked upstream outputs."""
        visual = _make_visual_mock()
        title_risk = _make_title_risk_mock()
        valuation = _make_valuation_mock()

        # CuratorInput uses Pydantic — upstream objects need to pass validation.
        # Using model_construct to bypass validation with mock objects.
        input_data = CuratorInput.model_construct(
            visual_analysis=visual,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="auction_house",
        )
        assert input_data.variant_key == "auction_house"
        assert input_data.visual_analysis is visual
        assert input_data.title_risk is title_risk
        assert input_data.valuation is valuation

    def test_curator_output_disclosures_empty_list(self):
        """CuratorOutput accepts an empty disclosures list."""
        output = CuratorOutput(
            exhibition_narrative="Narrative text.",
            wall_label="Label text.",
            suggested_title="A Title",
            disclosures=[],
            variant_used="public_gallery",
        )
        assert output.disclosures == []

    def test_curator_output_variant_used_is_required(self):
        """CuratorOutput raises validation error without variant_used."""
        with pytest.raises(Exception):
            CuratorOutput(
                exhibition_narrative="Narrative text.",
                wall_label="Label text.",
                suggested_title="A Title",
                disclosures=[],
                # variant_used intentionally omitted
            )

    def test_curator_output_default_disclosures(self):
        """CuratorOutput defaults disclosures to empty list when not provided."""
        output = CuratorOutput(
            exhibition_narrative="Narrative text.",
            wall_label="Label text.",
            suggested_title="A Title",
            variant_used="auction_house",
        )
        assert output.disclosures == []

    def test_curator_input_variant_key_defaults_to_none(self):
        """CuratorInput.variant_key defaults to None when not provided."""
        input_data = CuratorInput.model_construct(
            visual_analysis=_make_visual_mock(),
            title_risk=_make_title_risk_mock(),
            valuation=_make_valuation_mock(),
        )
        assert input_data.variant_key is None


# ---------------------------------------------------------------------------
# TestCurateMocked — full curate() flow with mocked Vertex
# ---------------------------------------------------------------------------


class TestCurateMocked:
    """Tests for curate() with mocked Vertex AI and config."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def _mock_config(self, default_variant: str = "public_gallery") -> tuple:
        """Create mock config and variant objects."""
        mock_config = MagicMock()
        mock_config.temperature = 0.6
        mock_config.max_output_tokens = 2048
        mock_config.default_variant = default_variant

        mock_variant = MagicMock()
        mock_variant.name = "Public Gallery Docent"
        mock_variant.voice = "Warm and accessible"

        return mock_config, mock_variant

    def _mock_vertex_response(self) -> dict:
        """Create a mock Vertex AI structured response (CuratorModelResponse schema)."""
        return {
            "exhibition_narrative": "A test narrative...",
            "wall_label": "Test Artist, Test Work, c. 1900",
            "suggested_title": "Untitled Landscape",
        }

    async def test_curate_auction_house_variant_used(self):
        """curate() with auction_house variant sets variant_used correctly."""
        input_data = _make_curator_input_mock(
            variant_key="auction_house",
            title_risk_review=False,
            valuation_review=False,
        )

        mock_config, mock_variant = self._mock_config()

        with patch(
            "artgents.agents.curator.generate_structured",
            new_callable=AsyncMock,
            return_value=self._mock_vertex_response(),
        ), patch(
            "artgents.agents.curator.get_selectable_variant_config",
            return_value=(mock_config, mock_variant),
        ):
            result = await curate(input_data)

        assert result.variant_used == "auction_house"

    async def test_curate_public_gallery_default_variant(self):
        """curate() with no variant_key uses default_variant='public_gallery'."""
        input_data = _make_curator_input_mock(
            variant_key=None,
            title_risk_review=False,
            valuation_review=False,
        )

        mock_config, mock_variant = self._mock_config(default_variant="public_gallery")

        with patch(
            "artgents.agents.curator.generate_structured",
            new_callable=AsyncMock,
            return_value=self._mock_vertex_response(),
        ), patch(
            "artgents.agents.curator.get_selectable_variant_config",
            return_value=(mock_config, mock_variant),
        ):
            result = await curate(input_data)

        assert result.variant_used == "public_gallery"

    async def test_curate_disclosures_injected_into_output(self):
        """Computed disclosures appear in final output even when model returns empty."""
        input_data = _make_curator_input_mock(
            variant_key="auction_house",
            title_risk_review=True,
            valuation_review=True,
        )

        mock_config, mock_variant = self._mock_config()

        with patch(
            "artgents.agents.curator.generate_structured",
            new_callable=AsyncMock,
            return_value=self._mock_vertex_response(),
        ), patch(
            "artgents.agents.curator.get_selectable_variant_config",
            return_value=(mock_config, mock_variant),
        ):
            result = await curate(input_data)

        # Model returned empty disclosures, but computed ones are injected
        assert len(result.disclosures) == 2
        assert any("Provenance" in d for d in result.disclosures)
        assert any("Valuation" in d for d in result.disclosures)

    async def test_curate_model_disclosures_preserved_alongside_computed(self):
        """Model-generated disclosures are preserved alongside computed ones."""
        input_data = _make_curator_input_mock(
            variant_key="auction_house",
            title_risk_review=True,
            valuation_review=False,
        )

        mock_config, mock_variant = self._mock_config()
        vertex_response = self._mock_vertex_response()

        with patch(
            "artgents.agents.curator.generate_structured",
            new_callable=AsyncMock,
            return_value=vertex_response,
        ), patch(
            "artgents.agents.curator.get_selectable_variant_config",
            return_value=(mock_config, mock_variant),
        ):
            result = await curate(input_data)

        # Disclosures are EXACTLY what determine_disclosures() computed — nothing more
        # title_risk_review=True → 1 provenance disclosure
        assert len(result.disclosures) == 1
        assert any("Provenance" in d for d in result.disclosures)


# ---------------------------------------------------------------------------
# TestHedgePreservation — hedge language in prompts
# ---------------------------------------------------------------------------


class TestHedgePreservation:
    """Tests that hedge language is preserved in prompts."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_build_prompt_includes_hedge_instruction_for_attributed_to(self):
        """_build_prompt includes hedge preservation when attribution starts with 'Attributed to'."""
        input_data = _make_curator_input_mock(
            attribution="Attributed to Claude Monet",
        )
        mock_variant = MagicMock()
        mock_variant.name = "Public Gallery Docent"
        mock_variant.voice = "Warm and accessible"

        prompt = _build_prompt(
            input_data, mock_variant, "public_gallery", disclosures=[]
        )

        assert "Attributed to" in prompt
        assert "HEDGE LANGUAGE PRESERVATION" in prompt
        assert "Do NOT upgrade" in prompt

    def test_build_prompt_hedge_with_manner_of_attribution(self):
        """_build_prompt handles 'Manner of' hedged attribution."""
        input_data = _make_curator_input_mock(
            attribution="Manner of Rembrandt van Rijn",
        )
        mock_variant = MagicMock()
        mock_variant.name = "Auction House Specialist"
        mock_variant.voice = "Authoritative and precise"

        prompt = _build_prompt(
            input_data, mock_variant, "auction_house", disclosures=[]
        )

        assert "Manner of Rembrandt van Rijn" in prompt
        assert "HEDGE LANGUAGE PRESERVATION" in prompt
        # The instruction mentions "Attributed to...", "Manner of..." etc.
        assert "Manner of" in prompt

    def test_build_prompt_preserves_uncertain_provenance_in_hedge(self):
        """_build_prompt instructs not to smooth uncertain provenance into confident prose."""
        input_data = _make_curator_input_mock(
            attribution="Attributed to Claude Monet",
            title_risk_review=True,
        )
        mock_variant = MagicMock()
        mock_variant.name = "Public Gallery Docent"
        mock_variant.voice = "Warm and accessible"

        prompt = _build_prompt(
            input_data, mock_variant, "public_gallery", disclosures=[]
        )

        assert "uncertain" in prompt.lower()
        assert "must reflect that uncertainty" in prompt.lower()


# ---------------------------------------------------------------------------
# TestVariantContentScoping — prompt differences by variant
# ---------------------------------------------------------------------------


class TestVariantContentScoping:
    """Tests that prompt content differs correctly between variants."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_auction_house_prompt_includes_valuation_corridor(self):
        """auction_house prompt includes dollar figures from the valuation corridor."""
        input_data = _make_curator_input_mock(variant_key="auction_house")
        mock_variant = MagicMock()
        mock_variant.name = "Auction House Specialist"
        mock_variant.voice = "Authoritative and precise"

        prompt = _build_prompt(
            input_data, mock_variant, "auction_house", disclosures=[]
        )

        # Should include dollar amounts from valuation corridor
        assert "$1,000,000" in prompt or "$1,000,000" in prompt
        assert "$5,000,000" in prompt or "$5,000,000" in prompt
        assert "Include dollar figures" in prompt

    def test_public_gallery_prompt_excludes_dollar_figures(self):
        """public_gallery prompt explicitly instructs no dollar figures."""
        input_data = _make_curator_input_mock(variant_key="public_gallery")
        mock_variant = MagicMock()
        mock_variant.name = "Public Gallery Docent"
        mock_variant.voice = "Warm and accessible"

        prompt = _build_prompt(
            input_data, mock_variant, "public_gallery", disclosures=[]
        )

        assert "Do NOT include any dollar figures" in prompt
        assert "MUST NOT contain any dollar" in prompt

    def test_auction_house_prompt_contains_methodology(self):
        """auction_house prompt includes appraiser methodology details."""
        input_data = _make_curator_input_mock(variant_key="auction_house")
        mock_variant = MagicMock()
        mock_variant.name = "Auction House Specialist"
        mock_variant.voice = "Authoritative and precise"

        prompt = _build_prompt(
            input_data, mock_variant, "auction_house", disclosures=[]
        )

        assert "Conservative appraiser methodology" in prompt or "methodology" in prompt.lower()
        assert "Bullish specialist" in prompt or "bullish" in prompt.lower()


class TestCategoryPrecision:
    """Test that the prompt prevents provenance/authenticity category conflation."""

    def test_prompt_contains_category_precision_instruction(self):
        """_build_prompt includes explicit instruction not to conflate provenance with authenticity."""
        from unittest.mock import MagicMock

        from artgents.agents.curator import CuratorInput, _build_prompt
        from artgents.config_loader import SelectableVariant

        visual = MagicMock()
        visual.search_keys.primary_artist_attribution = "Attributed to Basquiat"
        visual.search_keys.work_title = None
        visual.search_keys.probable_creation_window = "1982"
        visual.search_keys.style_and_movement = "Neo-Expressionism"
        visual.search_keys.detected_signatures_or_marks = []
        visual.composition_analysis = "Bold brushwork"
        visual.condition_notes = "Good condition"
        visual.stylistic_authenticity_notes = "Moderate confidence in attribution"

        title_risk = MagicMock()
        title_risk.requires_human_review = True
        title_risk.synthesis_summary = "Sub-agents disagree: moderate vs red_flag"
        title_risk.compliance_auditor.risk_level = "moderate"
        title_risk.compliance_auditor.reasoning = "Ownership gap in 1990s"
        title_risk.provenance_historian.risk_level = "red_flag"
        title_risk.provenance_historian.contextual_notes = "Gap is unusual"

        valuation = MagicMock()
        valuation.requires_human_review = False
        valuation.corridor_summary = "Normal corridor"
        valuation.valuation_corridor.low_estimate_usd = 1_000_000
        valuation.valuation_corridor.high_estimate_usd = 2_000_000
        valuation.conservative_appraiser.floor_estimate_usd = 1_000_000
        valuation.conservative_appraiser.confidence = "moderate"
        valuation.conservative_appraiser.methodology = "Test"
        valuation.bullish_specialist.ceiling_estimate_usd = 2_000_000
        valuation.bullish_specialist.confidence = "moderate"
        valuation.bullish_specialist.methodology = "Test"

        input_data = CuratorInput.model_construct(
            visual_analysis=visual,
            title_risk=title_risk,
            valuation=valuation,
            variant_key="auction_house",
        )

        variant = SelectableVariant(name="Auction House Cataloguer", voice="Formal")
        prompt = _build_prompt(input_data, variant, "auction_house", [])

        # Must contain the category precision instruction
        assert "CATEGORY PRECISION" in prompt
        assert "NEVER use" in prompt
        assert "authenticity" in prompt.lower()
        assert "provenance" in prompt.lower()
        # The specific guardrail language
        assert "categorically different" in prompt.lower() or "categorically different concerns" in prompt


class TestDisclosureStructuralGuarantee:
    """Test that disclosures come from determine_disclosures() only, not the model."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_curator_model_response_has_no_disclosures_field(self):
        """CuratorModelResponse schema does NOT include disclosures — structural guarantee."""
        from artgents.agents.curator import CuratorModelResponse

        assert "disclosures" not in CuratorModelResponse.model_fields
        assert "variant_used" not in CuratorModelResponse.model_fields
        # It only has the three narrative fields
        assert "exhibition_narrative" in CuratorModelResponse.model_fields
        assert "wall_label" in CuratorModelResponse.model_fields
        assert "suggested_title" in CuratorModelResponse.model_fields

    async def test_output_disclosures_exactly_match_computed(self):
        """CuratorOutput.disclosures equals determine_disclosures() return — no more, no less."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from artgents.agents.curator import curate, CuratorInput

        input_data = MagicMock(spec=CuratorInput)
        input_data.variant_key = "public_gallery"
        input_data.visual_analysis = MagicMock()
        input_data.visual_analysis.search_keys.primary_artist_attribution = "Attributed to Monet"
        input_data.visual_analysis.search_keys.work_title = None
        input_data.visual_analysis.search_keys.probable_creation_window = "1900"
        input_data.visual_analysis.search_keys.style_and_movement = "Impressionism"
        input_data.visual_analysis.search_keys.detected_signatures_or_marks = []
        input_data.visual_analysis.composition_analysis = "Test"
        input_data.visual_analysis.condition_notes = "Good"
        input_data.visual_analysis.stylistic_authenticity_notes = "Moderate"

        input_data.title_risk = MagicMock()
        input_data.title_risk.requires_human_review = False
        input_data.title_risk.synthesis_summary = "Both agree: low"
        input_data.title_risk.compliance_auditor.risk_level = "low"
        input_data.title_risk.compliance_auditor.reasoning = "Clean"
        input_data.title_risk.provenance_historian.risk_level = "low"
        input_data.title_risk.provenance_historian.contextual_notes = "Clean"

        input_data.valuation = MagicMock()
        input_data.valuation.requires_human_review = True  # This one triggers
        input_data.valuation.corridor_summary = "Wide spread: $50K-$8M"
        input_data.valuation.valuation_corridor.low_estimate_usd = 50_000
        input_data.valuation.valuation_corridor.high_estimate_usd = 8_000_000
        input_data.valuation.conservative_appraiser.floor_estimate_usd = 50_000
        input_data.valuation.conservative_appraiser.confidence = "low"
        input_data.valuation.conservative_appraiser.methodology = "Test"
        input_data.valuation.bullish_specialist.ceiling_estimate_usd = 8_000_000
        input_data.valuation.bullish_specialist.confidence = "low"
        input_data.valuation.bullish_specialist.methodology = "Test"

        # Model response has NO disclosures field (CuratorModelResponse schema)
        mock_model_response = {
            "exhibition_narrative": "A narrative about the work.",
            "wall_label": "Attributed to Monet, c. 1900",
            "suggested_title": "Untitled Landscape",
        }

        mock_config = MagicMock()
        mock_config.temperature = 0.6
        mock_config.max_output_tokens = 4096
        mock_config.default_variant = "public_gallery"
        mock_variant = MagicMock()
        mock_variant.name = "Public Gallery Docent"
        mock_variant.voice = "Warm"

        with patch(
            "artgents.agents.curator.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_model_response,
        ), patch(
            "artgents.agents.curator.get_selectable_variant_config",
            return_value=(mock_config, mock_variant),
        ):
            result = await curate(input_data)

        # Disclosures should be EXACTLY what determine_disclosures computed:
        # title_risk.requires_human_review=False → no provenance disclosure
        # valuation.requires_human_review=True → 1 valuation disclosure
        assert len(result.disclosures) == 1
        assert "uncertainty" in result.disclosures[0]
        # The model cannot have added anything extra
        assert all("uncertainty" in d or "further" in d for d in result.disclosures)
