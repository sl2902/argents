"""Unit tests for the Financial Valuation agent.

All tests use mocked clients — no real API calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artgents.agents.art_historian import ProvenanceSearchKeys
from artgents.agents.financial_valuation import (
    BullishSpecialistOutput,
    ComparableSale,
    ComparableSalesEvidence,
    ConservativeAppraiserOutput,
    FinancialValuationResult,
    ValuationCorridor,
    _determine_evidence_scope,
    gather_comps,
    run_bullish_specialist,
    run_conservative_appraiser,
    synthesize_valuation,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_search_keys() -> ProvenanceSearchKeys:
    """Realistic search keys for a Monet valuation scenario."""
    return ProvenanceSearchKeys(
        primary_artist_attribution="Claude Monet",
        probable_creation_window="1899–1905",
        style_and_movement="Impressionism",
        detected_signatures_or_marks=["Claude Monet (lower right)"],
        search_keywords=["monet", "water lilies", "nymphéas", "impressionism"],
        work_title="Nymphéas",
    )


@pytest.fixture
def sample_search_keys_no_title() -> ProvenanceSearchKeys:
    """Search keys without a work title — triggers artist_general scope."""
    return ProvenanceSearchKeys(
        primary_artist_attribution="Claude Monet",
        probable_creation_window="1899–1905",
        style_and_movement="Impressionism",
        detected_signatures_or_marks=["Claude Monet (lower right)"],
        search_keywords=["monet", "water lilies", "impressionism"],
    )


@pytest.fixture
def sample_comps() -> list[ComparableSale]:
    """Realistic comparable sales for a Monet Water Lilies painting."""
    return [
        ComparableSale(
            description="'Nymphéas en fleur' valued at 84687500 USD",
            price_usd=84_687_500.0,
            sale_date="2018-05-08",
            source_url="http://www.wikidata.org/entity/Q64768365",
            source_entity_id="http://www.wikidata.org/entity/Q64768365",
            source_type="wikidata",
        ),
        ComparableSale(
            description="'Le Bassin aux nymphéas' valued at 80451178 USD",
            price_usd=80_451_178.0,
            sale_date="2008-06-24",
            source_url="http://www.wikidata.org/entity/Q19925277",
            source_entity_id="http://www.wikidata.org/entity/Q64768365",
            source_type="wikidata",
        ),
        ComparableSale(
            description="Christie's: Monet Water Lilies sells for $54M at evening sale",
            price_usd=None,
            sale_date="2014-11-12",
            source_url="https://www.christies.com/lot/lot-monet-5849231",
            source_entity_id=None,
            source_type="parallel_search",
        ),
        ComparableSale(
            description="Sotheby's: Rare Monet Nymphéas achieves $27M",
            price_usd=None,
            sale_date="2019-05-14",
            source_url="https://www.sothebys.com/en/auctions/ecatalogue/2019/monet",
            source_entity_id=None,
            source_type="parallel_search",
        ),
    ]


@pytest.fixture
def sample_evidence(sample_search_keys, sample_comps) -> ComparableSalesEvidence:
    """A complete evidence bundle for testing."""
    return ComparableSalesEvidence(
        comparable_sales=sample_comps,
        query_search_keys=sample_search_keys,
        evidence_scope="specific_object",
        rejected_fact_count=1,
        sources_queried=["wikidata", "parallel_search"],
        sources_failed=[],
    )


@pytest.fixture
def sample_conservative() -> ConservativeAppraiserOutput:
    """Realistic conservative appraiser output for a Monet."""
    return ConservativeAppraiserOutput(
        floor_estimate_usd=15_000_000.0,
        methodology=(
            "Based on the lower range of Monet Nymphéas sales. Applied a 30% "
            "discount to the $27M Sotheby's 2019 sale to account for size uncertainty "
            "and condition unknowns. Conservative floor estimate of $15M."
        ),
        primary_comp="Nymphéas, $27M, Sotheby's 2019 (with 30% discount applied)",
        confidence="moderate",
    )


@pytest.fixture
def sample_bullish() -> BullishSpecialistOutput:
    """Realistic bullish specialist output for a Monet."""
    return BullishSpecialistOutput(
        ceiling_estimate_usd=50_000_000.0,
        methodology=(
            "The top Nymphéas sales (2018: $84.7M, 2008: $80.5M) suggest a strong "
            "ceiling for exceptional examples. Adjusting for market conditions and "
            "assuming favorable provenance, a ceiling of $50M is achievable at a "
            "major evening sale."
        ),
        primary_comp="Nymphéas, $84.7M, Christie's 2018",
        confidence="high",
    )


# ---------------------------------------------------------------------------
# TestModels — schema validation
# ---------------------------------------------------------------------------


class TestModels:
    """Schema validation tests for all Pydantic models."""

    def test_comparable_sale_with_price(self):
        sale = ComparableSale(
            description="'Nymphéas en fleur' valued at 84687500 USD",
            price_usd=84_687_500.0,
            sale_date="2018-05-08",
            source_url="http://www.wikidata.org/entity/Q64768365",
            source_entity_id="http://www.wikidata.org/entity/Q64768365",
            source_type="wikidata",
        )
        assert sale.price_usd == 84_687_500.0
        assert sale.source_type == "wikidata"
        assert sale.source_entity_id is not None

    def test_comparable_sale_without_price(self):
        sale = ComparableSale(
            description="Christie's: Monet Water Lilies sells at evening sale",
            price_usd=None,
            sale_date="2014-11-12",
            source_url="https://www.christies.com/lot/lot-monet-5849231",
            source_entity_id=None,
            source_type="parallel_search",
        )
        assert sale.price_usd is None
        assert sale.source_entity_id is None
        assert sale.source_type == "parallel_search"

    def test_comparable_sale_minimal_fields(self):
        sale = ComparableSale(
            description="A Monet painting",
            source_url="https://example.com/sale",
            source_type="wikidata",
        )
        assert sale.price_usd is None
        assert sale.sale_date is None
        assert sale.source_entity_id is None

    def test_comparable_sales_evidence_specific_object(self, sample_search_keys):
        evidence = ComparableSalesEvidence(
            comparable_sales=[],
            query_search_keys=sample_search_keys,
            evidence_scope="specific_object",
            sources_queried=["wikidata"],
        )
        assert evidence.evidence_scope == "specific_object"
        assert evidence.rejected_fact_count == 0

    def test_comparable_sales_evidence_artist_general(self, sample_search_keys):
        evidence = ComparableSalesEvidence(
            comparable_sales=[],
            query_search_keys=sample_search_keys,
            evidence_scope="artist_general",
            sources_queried=["wikidata", "parallel_search"],
            sources_failed=[],
        )
        assert evidence.evidence_scope == "artist_general"

    def test_comparable_sales_evidence_defaults(self, sample_search_keys):
        evidence = ComparableSalesEvidence(query_search_keys=sample_search_keys)
        assert evidence.comparable_sales == []
        assert evidence.evidence_scope == "artist_general"
        assert evidence.rejected_fact_count == 0
        assert evidence.sources_queried == []
        assert evidence.sources_failed == []

    def test_conservative_appraiser_output_valid(self):
        output = ConservativeAppraiserOutput(
            floor_estimate_usd=500_000.0,
            methodology="Based on lower-range sales for the artist's period.",
            primary_comp="Small landscape, $450K, Sotheby's 2021",
            confidence="moderate",
        )
        assert output.floor_estimate_usd == 500_000.0
        assert output.confidence == "moderate"

    def test_conservative_appraiser_output_invalid_confidence(self):
        with pytest.raises(Exception):
            ConservativeAppraiserOutput(
                floor_estimate_usd=500_000.0,
                methodology="Some methodology",
                primary_comp="Some comp",
                confidence="very_high",
            )

    def test_bullish_specialist_output_valid(self):
        output = BullishSpecialistOutput(
            ceiling_estimate_usd=50_000_000.0,
            methodology="Based on record auction results for comparable works.",
            primary_comp="Major canvas, $48M, Christie's 2022",
            confidence="high",
        )
        assert output.ceiling_estimate_usd == 50_000_000.0
        assert output.confidence == "high"

    def test_bullish_specialist_output_invalid_confidence(self):
        with pytest.raises(Exception):
            BullishSpecialistOutput(
                ceiling_estimate_usd=50_000_000.0,
                methodology="Some methodology",
                primary_comp="Some comp",
                confidence="extreme",
            )

    def test_valuation_corridor_valid(self):
        corridor = ValuationCorridor(
            low_estimate_usd=5_000_000.0,
            high_estimate_usd=25_000_000.0,
        )
        assert corridor.low_estimate_usd == 5_000_000.0
        assert corridor.high_estimate_usd == 25_000_000.0

    def test_financial_valuation_result_valid(self, sample_evidence):
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=10_000_000.0,
            methodology="Conservative approach.",
            primary_comp="Minor work, $9M, Phillips 2021",
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=40_000_000.0,
            methodology="Bullish approach.",
            primary_comp="Major canvas, $38M, Sotheby's 2022",
            confidence="high",
        )
        corridor = ValuationCorridor(
            low_estimate_usd=10_000_000.0,
            high_estimate_usd=40_000_000.0,
        )
        result = FinancialValuationResult(
            conservative_appraiser=conservative,
            bullish_specialist=bullish,
            evidence=sample_evidence,
            valuation_corridor=corridor,
            corridor_summary="Estimated valuation corridor: $10,000,000 – $40,000,000 USD.",
            requires_human_review=False,
        )
        assert result.requires_human_review is False
        assert result.valuation_corridor.low_estimate_usd == 10_000_000.0
        assert result.valuation_corridor.high_estimate_usd == 40_000_000.0


# ---------------------------------------------------------------------------
# TestSynthesizeValuation — exhaustive combination tests
# ---------------------------------------------------------------------------


class TestSynthesizeValuation:
    """Exhaustive tests over all combinations of synthesize_valuation() logic."""

    def _make_conservative(
        self, floor: float = 10_000_000.0, confidence: str = "moderate"
    ) -> ConservativeAppraiserOutput:
        return ConservativeAppraiserOutput(
            floor_estimate_usd=floor,
            methodology=f"Conservative methodology at {confidence} confidence.",
            primary_comp=f"Representative low-tier comp, ${floor:,.0f} estimate",
            confidence=confidence,
        )

    def _make_bullish(
        self, ceiling: float = 25_000_000.0, confidence: str = "high"
    ) -> BullishSpecialistOutput:
        return BullishSpecialistOutput(
            ceiling_estimate_usd=ceiling,
            methodology=f"Bullish methodology at {confidence} confidence.",
            primary_comp=f"Strong upper-tier comp, ${ceiling:,.0f} estimate",
            confidence=confidence,
        )

    def _make_evidence(
        self,
        sample_search_keys,
        num_comps: int = 5,
        evidence_scope: str = "specific_object",
    ) -> ComparableSalesEvidence:
        comps = [
            ComparableSale(
                description=f"Monet painting #{i+1}",
                price_usd=float((i + 1) * 10_000_000),
                sale_date="2020-01-01",
                source_url=f"http://www.wikidata.org/entity/Q{i+1}",
                source_entity_id="http://www.wikidata.org/entity/Q1",
                source_type="wikidata",
            )
            for i in range(num_comps)
        ]
        return ComparableSalesEvidence(
            comparable_sales=comps,
            query_search_keys=sample_search_keys,
            evidence_scope=evidence_scope,
            sources_queried=["wikidata", "parallel_search"],
        )

    # --- Both confidence high ---
    def test_both_high_confidence_no_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="high")
        bullish = self._make_bullish(confidence="high")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is False

    # --- Both confidence moderate ---
    def test_both_moderate_confidence_no_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="moderate")
        bullish = self._make_bullish(confidence="moderate")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is False

    # --- Both confidence low → requires human review ---
    def test_both_low_confidence_requires_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="low")
        bullish = self._make_bullish(confidence="low")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is True

    # --- artist_general with <3 comps → requires review ---
    def test_artist_general_sparse_comps_requires_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="high")
        bullish = self._make_bullish(confidence="high")
        evidence = self._make_evidence(
            sample_search_keys, num_comps=2, evidence_scope="artist_general"
        )

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is True

    # --- artist_general with exactly 0 comps → requires review ---
    def test_artist_general_zero_comps_requires_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="moderate")
        bullish = self._make_bullish(confidence="moderate")
        evidence = self._make_evidence(
            sample_search_keys, num_comps=0, evidence_scope="artist_general"
        )

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is True

    # --- specific_object with 5 comps, both high → no review ---
    def test_specific_object_5_comps_both_high_no_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="high")
        bullish = self._make_bullish(confidence="high")
        evidence = self._make_evidence(
            sample_search_keys, num_comps=5, evidence_scope="specific_object"
        )

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is False

    # --- specific_object with 5 comps, both low → requires review (both_low_confidence rule) ---
    def test_specific_object_5_comps_both_low_requires_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="low")
        bullish = self._make_bullish(confidence="low")
        evidence = self._make_evidence(
            sample_search_keys, num_comps=5, evidence_scope="specific_object"
        )

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is True

    # --- Wide spread: ceiling > 3x floor → flagged in corridor_summary ---
    def test_wide_spread_flagged_in_summary(self, sample_search_keys):
        conservative = self._make_conservative(floor=5_000_000.0, confidence="moderate")
        bullish = self._make_bullish(ceiling=20_000_000.0, confidence="moderate")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        # 20M / 5M = 4.0 > 3.0 → should be flagged
        assert "wide spread" in result.corridor_summary.lower() or "4.0x" in result.corridor_summary

    # --- Normal spread: ceiling < 3x floor → NOT flagged ---
    def test_normal_spread_not_flagged(self, sample_search_keys):
        conservative = self._make_conservative(floor=10_000_000.0, confidence="high")
        bullish = self._make_bullish(ceiling=25_000_000.0, confidence="high")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        # 25M / 10M = 2.5 < 3.0 → should NOT be flagged
        assert "wide spread" not in result.corridor_summary.lower()
        assert "uncertainty" not in result.corridor_summary.lower()

    # --- Corridor values always match floor/ceiling from sub-agents ---
    def test_corridor_matches_sub_agent_values(self, sample_search_keys):
        conservative = self._make_conservative(floor=7_500_000.0, confidence="moderate")
        bullish = self._make_bullish(ceiling=35_000_000.0, confidence="high")
        evidence = self._make_evidence(sample_search_keys, num_comps=4)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.valuation_corridor.low_estimate_usd == 7_500_000.0
        assert result.valuation_corridor.high_estimate_usd == 35_000_000.0

    # --- Mixed confidence: one low, one high → no review (only BOTH low triggers) ---
    def test_mixed_confidence_one_low_one_high_no_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="low")
        bullish = self._make_bullish(confidence="high")
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is False

    # --- artist_general with 3+ comps, moderate confidence → no review ---
    def test_artist_general_3_comps_moderate_no_review(self, sample_search_keys):
        conservative = self._make_conservative(confidence="moderate")
        bullish = self._make_bullish(confidence="moderate")
        evidence = self._make_evidence(
            sample_search_keys, num_comps=3, evidence_scope="artist_general"
        )

        result = synthesize_valuation(conservative, bullish, evidence)

        assert result.requires_human_review is False

    # --- Corridor summary contains dollar amounts ---
    def test_corridor_summary_contains_amounts(self, sample_search_keys):
        conservative = self._make_conservative(floor=12_000_000.0)
        bullish = self._make_bullish(ceiling=30_000_000.0)
        evidence = self._make_evidence(sample_search_keys, num_comps=5)

        result = synthesize_valuation(conservative, bullish, evidence)

        assert "$12,000,000" in result.corridor_summary
        assert "$30,000,000" in result.corridor_summary


# ---------------------------------------------------------------------------
# TestGatherComps — mock retrieval functions
# ---------------------------------------------------------------------------


class TestGatherComps:
    """Tests for gather_comps() with mocked retrieval functions."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("PARALLEL_WEB_API_KEY", "fake-key-for-testing")

    async def test_both_sources_succeed(self, sample_search_keys):
        """Successful retrieval from both sources produces comps from both."""

        async def mock_wikidata(search_keys, sales, sources_queried, sources_failed, rejected_counts):
            sales.append(
                ComparableSale(
                    description="'Nymphéas en fleur' valued at 84687500 USD",
                    price_usd=84_687_500.0,
                    sale_date="2018-05-08",
                    source_url="http://www.wikidata.org/entity/Q64768365",
                    source_entity_id="http://www.wikidata.org/entity/Q64768365",
                    source_type="wikidata",
                )
            )
            sources_queried.append("wikidata")

        async def mock_parallel(search_keys, sales, sources_queried, sources_failed):
            sales.append(
                ComparableSale(
                    description="Christie's: Monet Water Lilies sells for $54M",
                    price_usd=None,
                    sale_date="2014-11-12",
                    source_url="https://www.christies.com/lot/lot-monet-5849231",
                    source_entity_id=None,
                    source_type="parallel_search",
                )
            )
            sources_queried.append("parallel_search")

        with (
            patch(
                "artgents.agents.financial_valuation._retrieve_wikidata_sales",
                side_effect=mock_wikidata,
            ),
            patch(
                "artgents.agents.financial_valuation._retrieve_parallel_sales",
                side_effect=mock_parallel,
            ),
        ):
            evidence = await gather_comps(sample_search_keys)

        assert len(evidence.comparable_sales) == 2
        source_types = {s.source_type for s in evidence.comparable_sales}
        assert source_types == {"wikidata", "parallel_search"}
        assert set(evidence.sources_queried) == {"wikidata", "parallel_search"}
        assert evidence.sources_failed == []

    async def test_one_source_fails_partial_evidence(self, sample_search_keys):
        """One source fails, other succeeds — partial evidence with sources_failed."""

        async def mock_wikidata(search_keys, sales, sources_queried, sources_failed, rejected_counts):
            sales.append(
                ComparableSale(
                    description="'Le Bassin aux nymphéas' valued at 80451178 USD",
                    price_usd=80_451_178.0,
                    sale_date="2008-06-24",
                    source_url="http://www.wikidata.org/entity/Q19925277",
                    source_entity_id="http://www.wikidata.org/entity/Q19925277",
                    source_type="wikidata",
                )
            )
            sources_queried.append("wikidata")

        async def mock_parallel_fail(search_keys, sales, sources_queried, sources_failed):
            sources_failed.append("parallel_search")

        with (
            patch(
                "artgents.agents.financial_valuation._retrieve_wikidata_sales",
                side_effect=mock_wikidata,
            ),
            patch(
                "artgents.agents.financial_valuation._retrieve_parallel_sales",
                side_effect=mock_parallel_fail,
            ),
        ):
            evidence = await gather_comps(sample_search_keys)

        assert len(evidence.comparable_sales) == 1
        assert evidence.comparable_sales[0].source_type == "wikidata"
        assert "parallel_search" in evidence.sources_failed
        assert "wikidata" in evidence.sources_queried

    async def test_all_sources_fail_empty_comps(self, sample_search_keys):
        """All sources fail — empty comparable_sales list."""

        async def mock_wikidata_fail(search_keys, sales, sources_queried, sources_failed, rejected_counts):
            sources_failed.append("wikidata")

        async def mock_parallel_fail(search_keys, sales, sources_queried, sources_failed):
            sources_failed.append("parallel_search")

        with (
            patch(
                "artgents.agents.financial_valuation._retrieve_wikidata_sales",
                side_effect=mock_wikidata_fail,
            ),
            patch(
                "artgents.agents.financial_valuation._retrieve_parallel_sales",
                side_effect=mock_parallel_fail,
            ),
        ):
            evidence = await gather_comps(sample_search_keys)

        assert evidence.comparable_sales == []
        assert evidence.sources_queried == []
        assert set(evidence.sources_failed) == {"wikidata", "parallel_search"}

    async def test_evidence_scope_no_title_artist_general(self, sample_search_keys_no_title):
        """No work_title → evidence_scope='artist_general'."""

        async def mock_wikidata(search_keys, sales, sources_queried, sources_failed, rejected_counts):
            sales.append(
                ComparableSale(
                    description="'Impression, Sunrise' valued at 12000000 USD",
                    price_usd=12_000_000.0,
                    sale_date="2010-03-15",
                    source_url="http://www.wikidata.org/entity/Q208230",
                    source_entity_id="http://www.wikidata.org/entity/Q208230",
                    source_type="wikidata",
                )
            )
            sources_queried.append("wikidata")

        async def mock_parallel(search_keys, sales, sources_queried, sources_failed):
            sources_queried.append("parallel_search")

        with (
            patch(
                "artgents.agents.financial_valuation._retrieve_wikidata_sales",
                side_effect=mock_wikidata,
            ),
            patch(
                "artgents.agents.financial_valuation._retrieve_parallel_sales",
                side_effect=mock_parallel,
            ),
        ):
            evidence = await gather_comps(sample_search_keys_no_title)

        assert evidence.evidence_scope == "artist_general"

    async def test_evidence_scope_title_single_entity_specific_object(self, sample_search_keys):
        """work_title + single entity_id → evidence_scope='specific_object'."""

        async def mock_wikidata(search_keys, sales, sources_queried, sources_failed, rejected_counts):
            # All wikidata sales share the same entity_id
            sales.append(
                ComparableSale(
                    description="'Nymphéas' valued at 40000000 USD",
                    price_usd=40_000_000.0,
                    sale_date="2015-06-01",
                    source_url="http://www.wikidata.org/entity/Q64768365",
                    source_entity_id="http://www.wikidata.org/entity/Q64768365",
                    source_type="wikidata",
                )
            )
            sales.append(
                ComparableSale(
                    description="'Nymphéas' provenance record",
                    price_usd=None,
                    sale_date=None,
                    source_url="http://www.wikidata.org/entity/Q64768365#P793",
                    source_entity_id="http://www.wikidata.org/entity/Q64768365",
                    source_type="wikidata",
                )
            )
            sources_queried.append("wikidata")

        async def mock_parallel(search_keys, sales, sources_queried, sources_failed):
            # Parallel results have no entity_id (ignored in scope determination)
            sales.append(
                ComparableSale(
                    description="Monet Nymphéas auction context",
                    price_usd=None,
                    sale_date=None,
                    source_url="https://www.artnet.com/monet-nympheas",
                    source_entity_id=None,
                    source_type="parallel_search",
                )
            )
            sources_queried.append("parallel_search")

        with (
            patch(
                "artgents.agents.financial_valuation._retrieve_wikidata_sales",
                side_effect=mock_wikidata,
            ),
            patch(
                "artgents.agents.financial_valuation._retrieve_parallel_sales",
                side_effect=mock_parallel,
            ),
        ):
            evidence = await gather_comps(sample_search_keys)

        assert evidence.evidence_scope == "specific_object"


# ---------------------------------------------------------------------------
# TestSubAgentsMocked — mock Vertex AI client
# ---------------------------------------------------------------------------


class TestSubAgentsMocked:
    """Tests for run_conservative_appraiser and run_bullish_specialist with mocked Vertex."""

    @pytest.fixture(autouse=True)
    def _set_gcp_project(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def _mock_config(self):
        """Create a mock DualAgentConfig for financial_valuation."""
        mock_conservative_variant = MagicMock()
        mock_conservative_variant.name = "Conservative Appraiser"
        mock_conservative_variant.stance = "floor"
        mock_conservative_variant.voice = (
            "Cautious insurance appraiser who emphasizes downside risks "
            "and conservative comparable selection."
        )

        mock_bullish_variant = MagicMock()
        mock_bullish_variant.name = "Bullish Market Specialist"
        mock_bullish_variant.stance = "ceiling"
        mock_bullish_variant.voice = (
            "Optimistic auction specialist who emphasizes upside potential "
            "and premium comparable selection."
        )

        mock_cfg = MagicMock()
        mock_cfg.temperature = 0.2
        mock_cfg.max_output_tokens = 3072
        mock_cfg.variants = {
            "conservative_appraiser": mock_conservative_variant,
            "bullish_specialist": mock_bullish_variant,
        }
        return mock_cfg

    async def test_run_conservative_appraiser_success(self, sample_evidence):
        """run_conservative_appraiser with mock response validates into output."""
        mock_response = {
            "floor_estimate_usd": 15_000_000.0,
            "methodology": (
                "Based on the lower range of Monet Nymphéas sales at auction. "
                "Applied a 30% discount for condition uncertainty. Floor of $15M."
            ),
            "primary_comp": "Nymphéas, $21M, Sotheby's 2019 (with 30% discount)",
            "confidence": "moderate",
        }

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_config.return_value = self._mock_config()
                result = await run_conservative_appraiser(sample_evidence)

        assert isinstance(result, ConservativeAppraiserOutput)
        assert result.floor_estimate_usd == 15_000_000.0
        assert result.confidence == "moderate"
        assert "Monet" in result.methodology

    async def test_run_bullish_specialist_success(self, sample_evidence):
        """run_bullish_specialist with mock response validates into output."""
        mock_response = {
            "ceiling_estimate_usd": 50_000_000.0,
            "methodology": (
                "Top Nymphéas sales ($84.7M in 2018, $80.5M in 2008) indicate "
                "strong ceiling potential. Adjusting for current market, $50M is "
                "achievable at a major evening sale with competitive bidding."
            ),
            "primary_comp": "Nymphéas, $84.7M, Christie's 2018",
            "confidence": "high",
        }

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_config.return_value = self._mock_config()
                result = await run_bullish_specialist(sample_evidence)

        assert isinstance(result, BullishSpecialistOutput)
        assert result.ceiling_estimate_usd == 50_000_000.0
        assert result.confidence == "high"
        assert "Nymphéas" in result.methodology

    async def test_vertex_error_propagates_from_conservative(self, sample_evidence):
        """VertexCallError propagates from run_conservative_appraiser."""
        from artgents.clients.vertex import VertexCallError

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            side_effect=VertexCallError("Vertex AI returned 500: Internal Server Error"),
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_config.return_value = self._mock_config()
                with pytest.raises(VertexCallError, match="500"):
                    await run_conservative_appraiser(sample_evidence)

    async def test_vertex_error_propagates_from_bullish(self, sample_evidence):
        """VertexCallError propagates from run_bullish_specialist."""
        from artgents.clients.vertex import VertexCallError

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            side_effect=VertexCallError("Vertex AI quota exceeded"),
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_config.return_value = self._mock_config()
                with pytest.raises(VertexCallError, match="quota"):
                    await run_bullish_specialist(sample_evidence)

    async def test_conservative_appraiser_with_title_risk(self, sample_evidence):
        """Conservative appraiser accepts optional title_risk parameter."""
        from artgents.agents.provenance_legal import TitleRiskMatrix

        mock_response = {
            "floor_estimate_usd": 9_000_000.0,
            "methodology": (
                "Applied 40% title-dispute discount to $15M base estimate "
                "due to provenance concerns flagged by title risk assessment."
            ),
            "primary_comp": "Nymphéas, $15M base (with 40% title-dispute discount)",
            "confidence": "low",
        }

        # Create a minimal TitleRiskMatrix mock
        title_risk = MagicMock(spec=TitleRiskMatrix)
        title_risk.requires_human_review = True

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_config.return_value = self._mock_config()
                result = await run_conservative_appraiser(sample_evidence, title_risk)

        assert isinstance(result, ConservativeAppraiserOutput)
        assert result.floor_estimate_usd == 9_000_000.0
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# TestEvidenceScope — test _determine_evidence_scope logic
# ---------------------------------------------------------------------------


class TestEvidenceScope:
    """Tests for _determine_evidence_scope() logic."""

    def _make_search_keys(self, work_title: str | None = None) -> ProvenanceSearchKeys:
        return ProvenanceSearchKeys(
            primary_artist_attribution="Claude Monet",
            probable_creation_window="1899–1905",
            style_and_movement="Impressionism",
            search_keywords=["monet", "water lilies", "impressionism"],
            detected_signatures_or_marks=["Claude Monet (lower right)"],
            work_title=work_title,
        )

    def test_no_title_returns_artist_general(self):
        """work_title=None → always 'artist_general' regardless of sales."""
        keys = self._make_search_keys(work_title=None)
        sales = [
            ComparableSale(
                description="A Monet painting",
                price_usd=10_000_000.0,
                source_url="http://www.wikidata.org/entity/Q123",
                source_entity_id="http://www.wikidata.org/entity/Q123",
                source_type="wikidata",
            ),
        ]
        result = _determine_evidence_scope(keys, sales)
        assert result == "artist_general"

    def test_title_single_entity_returns_specific_object(self):
        """work_title present + all sales share one entity_id → 'specific_object'."""
        keys = self._make_search_keys(work_title="Nymphéas")
        sales = [
            ComparableSale(
                description="'Nymphéas' first sale",
                price_usd=40_000_000.0,
                source_url="http://www.wikidata.org/entity/Q64768365",
                source_entity_id="http://www.wikidata.org/entity/Q64768365",
                source_type="wikidata",
            ),
            ComparableSale(
                description="'Nymphéas' second sale",
                price_usd=50_000_000.0,
                source_url="http://www.wikidata.org/entity/Q64768365#sale2",
                source_entity_id="http://www.wikidata.org/entity/Q64768365",
                source_type="wikidata",
            ),
            ComparableSale(
                description="Parallel context on Nymphéas",
                price_usd=None,
                source_url="https://www.christies.com/monet",
                source_entity_id=None,  # None is ignored in scope determination
                source_type="parallel_search",
            ),
        ]
        result = _determine_evidence_scope(keys, sales)
        assert result == "specific_object"

    def test_title_multiple_entities_returns_artist_general(self):
        """work_title present + sales have different entity_ids → 'artist_general'."""
        keys = self._make_search_keys(work_title="Water Lilies")
        sales = [
            ComparableSale(
                description="'Water Lilies (1906)' painting A",
                price_usd=30_000_000.0,
                source_url="http://www.wikidata.org/entity/Q123",
                source_entity_id="http://www.wikidata.org/entity/Q123",
                source_type="wikidata",
            ),
            ComparableSale(
                description="'Water Lilies (1916)' painting B",
                price_usd=45_000_000.0,
                source_url="http://www.wikidata.org/entity/Q456",
                source_entity_id="http://www.wikidata.org/entity/Q456",
                source_type="wikidata",
            ),
        ]
        result = _determine_evidence_scope(keys, sales)
        assert result == "artist_general"

    def test_title_no_entity_ids_returns_artist_general(self):
        """work_title present but all entity_ids are None → 'artist_general'."""
        keys = self._make_search_keys(work_title="Nymphéas")
        sales = [
            ComparableSale(
                description="Auction record for Monet",
                price_usd=None,
                source_url="https://www.sothebys.com/monet-lot-1",
                source_entity_id=None,
                source_type="parallel_search",
            ),
            ComparableSale(
                description="Another auction reference",
                price_usd=None,
                source_url="https://www.christies.com/monet-lot-2",
                source_entity_id=None,
                source_type="parallel_search",
            ),
        ]
        result = _determine_evidence_scope(keys, sales)
        assert result == "artist_general"

    def test_title_empty_sales_returns_artist_general(self):
        """work_title present but no sales at all → 'artist_general' (no entity IDs to check)."""
        keys = self._make_search_keys(work_title="Nymphéas")
        sales: list[ComparableSale] = []
        result = _determine_evidence_scope(keys, sales)
        assert result == "artist_general"


class TestOutlierAvoidanceInstructions:
    """Test that prompts contain symmetric outlier-avoidance guidance."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_artist_general_scope_contains_outlier_avoidance(self):
        """artist_general scope instructions include outlier-avoidance guidance."""
        from artgents.agents.financial_valuation import (
            ComparableSalesEvidence,
            _build_scope_instructions,
        )
        from artgents.agents.art_historian import ProvenanceSearchKeys

        keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Basquiat",
            probable_creation_window="1982",
            style_and_movement="Neo-Expressionism",
            search_keywords=["basquiat"],
        )
        evidence = ComparableSalesEvidence(
            comparable_sales=[],
            query_search_keys=keys,
            evidence_scope="artist_general",
            sources_queried=["wikidata"],
        )

        instructions = _build_scope_instructions(evidence)
        # Must contain explicit outlier-avoidance language
        assert "outlier" in instructions.lower() or "OUTLIER" in instructions
        assert "record" in instructions.lower()
        assert "percentile" in instructions.lower() or "representative" in instructions.lower()
        assert "all-time maximum" in instructions.lower() or "literal maximum" in instructions.lower()

    def test_specific_object_scope_no_outlier_warning(self):
        """specific_object scope doesn't need the outlier warning (direct comps available)."""
        from artgents.agents.financial_valuation import (
            ComparableSalesEvidence,
            _build_scope_instructions,
        )
        from artgents.agents.art_historian import ProvenanceSearchKeys

        keys = ProvenanceSearchKeys(
            work_title="Untitled (1982)",
            primary_artist_attribution="Attributed to Basquiat",
            probable_creation_window="1982",
            style_and_movement="Neo-Expressionism",
            search_keywords=["basquiat"],
        )
        evidence = ComparableSalesEvidence(
            comparable_sales=[],
            query_search_keys=keys,
            evidence_scope="specific_object",
            sources_queried=["wikidata"],
        )

        instructions = _build_scope_instructions(evidence)
        assert "SPECIFIC OBJECT" in instructions
        # Outlier guidance is not needed for specific-object mode
        assert "OUTLIER ANCHORING" not in instructions

    def test_bullish_prompt_has_outlier_avoidance_task_instruction(self):
        """The bullish specialist prompt contains task-level outlier-avoidance."""
        # We can verify by reading the source — the instruction should mention
        # not anchoring on the single all-time record
        import inspect
        from artgents.agents.financial_valuation import run_bullish_specialist

        source = inspect.getsource(run_bullish_specialist)
        assert "all-time record" in source.lower() or "record sale" in source.lower()
        assert "exceptional" in source.lower()
        assert "representative" in source.lower()

    def test_conservative_prompt_has_relevance_instruction(self):
        """The conservative appraiser prompt warns against using irrelevant low comps."""
        import inspect
        from artgents.agents.financial_valuation import run_conservative_appraiser

        source = inspect.getsource(run_conservative_appraiser)
        assert "cheapest" in source.lower() or "lowest comp" in source.lower()
        assert "representative" in source.lower()


class TestWideSpreadReview:
    """Test that wide corridor spread triggers requires_human_review and cites comps."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def _make_evidence(self, scope="specific_object", n_comps=5):
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.financial_valuation import (
            ComparableSale,
            ComparableSalesEvidence,
        )

        keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Basquiat",
            probable_creation_window="1982",
            style_and_movement="Neo-Expressionism",
            search_keywords=["basquiat"],
        )
        sales = [
            ComparableSale(
                description=f"Sale {i}",
                price_usd=float(i * 1000000),
                sale_date="2023",
                source_url=f"https://example.com/{i}",
                source_entity_id=f"Q{i}",
                source_type="wikidata",
            )
            for i in range(1, n_comps + 1)
        ]
        return ComparableSalesEvidence(
            comparable_sales=sales,
            query_search_keys=keys,
            evidence_scope=scope,
            sources_queried=["wikidata"],
        )

    def test_wide_spread_triggers_human_review(self):
        """A spread > 3x triggers requires_human_review even with good comps."""
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            synthesize_valuation,
        )

        evidence = self._make_evidence(scope="specific_object", n_comps=5)
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=100_000,
            methodology="Based on a minor Basquiat drawing sold for $120,000 at Phillips 2022.",
            primary_comp="Minor drawing, $120K, Phillips 2022",
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=5_000_000,  # 50x floor
            methodology="Based on prime-period Basquiat canvases selling for $4-8M at Christie's 2023.",
            primary_comp="Prime-period canvas, $4.8M, Christie's 2023",
            confidence="moderate",
        )

        result = synthesize_valuation(conservative, bullish, evidence)
        assert result.requires_human_review is True

    def test_normal_spread_no_review_from_spread_alone(self):
        """A spread <= 3x does not trigger review from spread alone."""
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            synthesize_valuation,
        )

        evidence = self._make_evidence(scope="specific_object", n_comps=5)
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=1_000_000,
            methodology="Based on mid-range Basquiat works at $800K-1.2M.",
            primary_comp="Mid-range Basquiat, $1M, Sotheby's 2022",
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=2_500_000,  # 2.5x floor — within threshold
            methodology="Based on strong Basquiat canvases at $2-3M.",
            primary_comp="Strong canvas, $2.5M, Christie's 2023",
            confidence="moderate",
        )

        result = synthesize_valuation(conservative, bullish, evidence)
        # Not triggered by spread (2.5x < 3x), and not by other conditions
        assert result.requires_human_review is False

    def test_wide_spread_corridor_summary_cites_comps(self):
        """Wide-spread corridor_summary contains both primary_comp values verbatim."""
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            synthesize_valuation,
        )

        evidence = self._make_evidence(scope="artist_general", n_comps=5)
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=50_000,
            methodology="Anchored on a 2019 Phillips sale of a small Basquiat drawing at $65,000 hammer price, with 25% illiquidity discount applied.",
            primary_comp="Small drawing on paper, $65K hammer, Phillips 2019",
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=8_000_000,  # 160x floor
            methodology="Referenced prime-period Basquiat canvases selling at $4-8M at Christie's and Sotheby's in 2022-2023.",
            primary_comp="Prime-period acrylic on canvas, $7.2M, Sotheby's 2023",
            confidence="moderate",
        )

        result = synthesize_valuation(conservative, bullish, evidence)
        assert result.requires_human_review is True
        # corridor_summary should contain both primary_comp values VERBATIM
        assert "Small drawing on paper, $65K hammer, Phillips 2019" in result.corridor_summary
        assert "Prime-period acrylic on canvas, $7.2M, Sotheby's 2023" in result.corridor_summary


class TestDoublePeriodFix:
    """Test that corridor_summary never has double periods from primary_comp."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def _make_evidence(self):
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.financial_valuation import (
            ComparableSale,
            ComparableSalesEvidence,
        )

        keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Test",
            probable_creation_window="2000",
            style_and_movement="Modern",
            search_keywords=["test"],
        )
        return ComparableSalesEvidence(
            comparable_sales=[
                ComparableSale(
                    description="Sale",
                    price_usd=100_000.0,
                    sale_date="2023",
                    source_url="https://example.com",
                    source_entity_id="Q1",
                    source_type="wikidata",
                )
            ] * 5,
            query_search_keys=keys,
            evidence_scope="specific_object",
            sources_queried=["wikidata"],
        )

    def test_primary_comp_with_trailing_period_no_double_period(self):
        """primary_comp ending in '.' does not produce '..' in corridor_summary."""
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            synthesize_valuation,
        )

        evidence = self._make_evidence()
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=10_000,
            methodology="Test",
            primary_comp="Small work sold at auction for $12,000.",  # trailing period
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=500_000,  # >3x, triggers wide spread
            methodology="Test",
            primary_comp="Large canvas sold for $480,000 at Christie's.",  # trailing period
            confidence="moderate",
        )

        result = synthesize_valuation(conservative, bullish, evidence)
        assert ".." not in result.corridor_summary

    def test_primary_comp_without_trailing_period_single_period(self):
        """primary_comp NOT ending in '.' still produces exactly one period."""
        from artgents.agents.financial_valuation import (
            BullishSpecialistOutput,
            ConservativeAppraiserOutput,
            synthesize_valuation,
        )

        evidence = self._make_evidence()
        conservative = ConservativeAppraiserOutput(
            floor_estimate_usd=10_000,
            methodology="Test",
            primary_comp="Small work, $12K, Phillips 2022",  # no trailing period
            confidence="moderate",
        )
        bullish = BullishSpecialistOutput(
            ceiling_estimate_usd=500_000,
            methodology="Test",
            primary_comp="Large canvas, $480K, Christie's 2023",  # no trailing period
            confidence="moderate",
        )

        result = synthesize_valuation(conservative, bullish, evidence)
        assert ".." not in result.corridor_summary
        # Each comp citation ends with exactly one period
        assert "Phillips 2022." in result.corridor_summary
        assert "Christie's 2023." in result.corridor_summary
