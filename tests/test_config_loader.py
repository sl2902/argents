"""Unit tests for the shared config loader.

Tests all three config shapes, validation errors, and fallback behavior
against the real config/agents.yaml.
"""

from __future__ import annotations

import pytest

from artgents.config_loader import (
    DualAgentConfig,
    ExpertConfig,
    SelectableVariant,
    SelectableVariantConfig,
    SubAgentVariant,
    get_dual_agent_config,
    get_expert_config,
    get_selectable_variant_config,
    reset_config,
)


# ---------------------------------------------------------------------------
# Shape 1: get_expert_config() — single-expert agents
# ---------------------------------------------------------------------------


class TestGetExpertConfig:
    """Test get_expert_config() for shape-1 agents."""

    def test_visual_art_historian_parses(self):
        """visual_art_historian loads correctly as ExpertConfig."""
        config = get_expert_config("visual_art_historian")
        assert isinstance(config, ExpertConfig)
        assert config.name == "Visual Art Historian"
        assert config.domain == "Stylistic and technical analysis of paintings and sculpture"
        assert "epistemically careful" in config.voice
        assert config.temperature == 0.2
        assert config.max_output_tokens == 2048

    def test_wrong_accessor_for_dual_agent_raises(self):
        """get_expert_config() on a dual-agent role raises ValueError."""
        with pytest.raises(ValueError, match="does not have an 'expert' block"):
            get_expert_config("provenance_legal")

    def test_wrong_accessor_for_selectable_raises(self):
        """get_expert_config() on a selectable-variant role raises ValueError."""
        with pytest.raises(ValueError, match="does not have an 'expert' block"):
            get_expert_config("curator")

    def test_nonexistent_agent_raises(self):
        """get_expert_config() with unknown role raises KeyError."""
        with pytest.raises(KeyError, match="not found in config"):
            get_expert_config("nonexistent_agent")


# ---------------------------------------------------------------------------
# Shape 2: get_dual_agent_config() — concurrent dual-agent pairs
# ---------------------------------------------------------------------------


class TestGetDualAgentConfig:
    """Test get_dual_agent_config() for shape-2 agents."""

    def test_provenance_legal_parses(self):
        """provenance_legal loads correctly as DualAgentConfig with 2 variants."""
        config = get_dual_agent_config("provenance_legal")
        assert isinstance(config, DualAgentConfig)
        assert config.temperature == 0.2
        assert config.max_output_tokens == 8192
        assert len(config.variants) == 2
        assert "compliance_auditor" in config.variants
        assert "provenance_historian" in config.variants
        assert config.synthesis_output == "title_risk_matrix"

        # Verify variant content
        auditor = config.variants["compliance_auditor"]
        assert isinstance(auditor, SubAgentVariant)
        assert auditor.name == "Compliance Auditor"
        assert auditor.stance == "skeptic"
        assert "title attorney" in auditor.voice

        historian = config.variants["provenance_historian"]
        assert historian.name == "Provenance Historian"
        assert historian.stance == "advocate"

    def test_financial_valuation_parses(self):
        """financial_valuation loads correctly as DualAgentConfig with 2 variants."""
        config = get_dual_agent_config("financial_valuation")
        assert isinstance(config, DualAgentConfig)
        assert config.temperature == 0.2
        assert config.max_output_tokens == 8192
        assert len(config.variants) == 2
        assert "conservative_appraiser" in config.variants
        assert "bullish_specialist" in config.variants
        assert config.synthesis_output == "valuation_corridor"

    def test_retrieval_description_present(self):
        """Both dual-agent configs have retrieval_description."""
        for role in ["provenance_legal", "financial_valuation"]:
            config = get_dual_agent_config(role)
            assert config.retrieval_description
            assert len(config.retrieval_description) > 50

    def test_wrong_accessor_for_expert_raises(self):
        """get_dual_agent_config() on a single-expert role raises ValueError."""
        with pytest.raises(ValueError, match="does not have a 'variants' block"):
            get_dual_agent_config("visual_art_historian")

    def test_wrong_accessor_for_selectable_raises(self):
        """get_dual_agent_config() on a selectable-variant role raises ValueError."""
        with pytest.raises(ValueError, match="not a dual-agent config"):
            get_dual_agent_config("curator")

    def test_nonexistent_agent_raises(self):
        """get_dual_agent_config() with unknown role raises KeyError."""
        with pytest.raises(KeyError, match="not found in config"):
            get_dual_agent_config("nonexistent_agent")


# ---------------------------------------------------------------------------
# Shape 3: get_selectable_variant_config() — selectable-variant agents
# ---------------------------------------------------------------------------


class TestGetSelectableVariantConfig:
    """Test get_selectable_variant_config() for shape-3 agents."""

    def test_curator_default_variant(self):
        """curator with no variant_key selects default_variant from YAML."""
        config, variant = get_selectable_variant_config("curator")
        assert isinstance(config, SelectableVariantConfig)
        assert config.temperature == 0.6
        assert config.max_output_tokens == 2048
        assert config.default_variant == "public_gallery"
        assert isinstance(variant, SelectableVariant)
        assert variant.name == "Public Gallery Docent"
        assert "accessible" in variant.voice

    def test_curator_explicit_variant(self):
        """curator with explicit variant_key selects that variant."""
        config, variant = get_selectable_variant_config("curator", "auction_house")
        assert variant.name == "Auction House Cataloguer"
        assert "precise" in variant.voice.lower() or "formal" in variant.voice.lower()

    def test_curator_explicit_default_variant(self):
        """Explicitly passing the default variant key works the same."""
        config, variant = get_selectable_variant_config("curator", "public_gallery")
        assert variant.name == "Public Gallery Docent"

    def test_invalid_variant_key_raises(self):
        """An explicitly invalid variant_key raises KeyError, not silent fallback."""
        with pytest.raises(KeyError, match="not found for agent 'curator'"):
            get_selectable_variant_config("curator", "nonexistent_variant")

    def test_none_variant_key_uses_default(self):
        """None variant_key is the ONLY way to trigger default fallback."""
        _, variant = get_selectable_variant_config("curator", None)
        assert variant.name == "Public Gallery Docent"

    def test_all_variants_present(self):
        """Both curator variants are accessible."""
        config, _ = get_selectable_variant_config("curator")
        assert "auction_house" in config.variants
        assert "public_gallery" in config.variants
        assert len(config.variants) == 2

    def test_wrong_accessor_for_expert_raises(self):
        """get_selectable_variant_config() on a single-expert role raises ValueError."""
        with pytest.raises(ValueError, match="does not have a 'variants' block"):
            get_selectable_variant_config("visual_art_historian")

    def test_wrong_accessor_for_dual_raises(self):
        """get_selectable_variant_config() on a dual-agent role raises ValueError."""
        with pytest.raises(ValueError, match="not a selectable-variant config"):
            get_selectable_variant_config("provenance_legal")

    def test_nonexistent_agent_raises(self):
        """get_selectable_variant_config() with unknown role raises KeyError."""
        with pytest.raises(KeyError, match="not found in config"):
            get_selectable_variant_config("nonexistent_agent")


# ---------------------------------------------------------------------------
# Cross-cutting: config caching and reset
# ---------------------------------------------------------------------------


class TestConfigCaching:
    """Test that config is loaded once and can be reset."""

    def test_repeated_calls_return_same_values(self):
        """Multiple calls return consistent values (cached)."""
        c1 = get_expert_config("visual_art_historian")
        c2 = get_expert_config("visual_art_historian")
        assert c1.temperature == c2.temperature
        assert c1.voice == c2.voice

    def test_reset_config_works(self):
        """reset_config() clears the cache without breaking subsequent loads."""
        _ = get_expert_config("visual_art_historian")
        reset_config()
        config = get_expert_config("visual_art_historian")
        assert config.name == "Visual Art Historian"
