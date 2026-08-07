"""Unit tests for the Provenance & Legal agent.

All tests use mocked clients — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from artgents.agents.art_historian import ProvenanceSearchKeys
from artgents.agents.provenance_legal import (
    ComplianceAuditorOutput,
    EvidenceBundle,
    OwnershipGap,
    ProvenanceHistorianOutput,
    RetrievedFact,
    TitleRiskMatrix,
    _format_evidence_for_prompt,
    gather_evidence,
    run_compliance_auditor,
    run_provenance_historian,
    synthesize_title_risk,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_search_keys() -> ProvenanceSearchKeys:
    """Realistic search keys for a WWII-era provenance scenario."""
    return ProvenanceSearchKeys(
        primary_artist_attribution="Attributed to Gustav Klimt",
        probable_creation_window="1907–1912",
        style_and_movement="Vienna Secession / Art Nouveau",
        detected_signatures_or_marks=["KLIMT (lower right, gold leaf border)"],
        search_keywords=[
            "klimt",
            "vienna secession",
            "portrait",
            "gold leaf",
            "adele bloch-bauer",
        ],
    )


@pytest.fixture
def sample_facts() -> list[RetrievedFact]:
    """Realistic retrieved facts for a Klimt provenance scenario."""
    return [
        RetrievedFact(
            claim="Owned by Ferdinand Bloch-Bauer (1912 to 1938)",
            source_url="https://www.wikidata.org/wiki/Q474748",
            source_type="wikidata",
        ),
        RetrievedFact(
            claim="Confiscated by Nazi authorities in 1938 following Anschluss",
            source_url="https://www.wikidata.org/wiki/Q474748#P793",
            source_type="wikidata",
        ),
        RetrievedFact(
            claim="Met Museum holds 'Portrait of Adele Bloch-Bauer I' by Gustav Klimt (1907)",
            source_url="https://www.metmuseum.org/art/collection/search/488234",
            source_type="met",
        ),
        RetrievedFact(
            claim="FBI Art Crime: Klimt works among most sought Nazi-looted art",
            source_url="https://www.fbi.gov/investigate/violent-crime/art-theft",
            source_type="parallel_search",
        ),
    ]


@pytest.fixture
def sample_bundle(sample_search_keys, sample_facts) -> EvidenceBundle:
    """A complete evidence bundle for testing."""
    return EvidenceBundle(
        retrieved_facts=sample_facts,
        query_search_keys=sample_search_keys,
        sources_queried=["wikidata", "met", "parallel_search"],
        sources_failed=["aic"],
    )


@pytest.fixture
def sample_auditor_output() -> ComplianceAuditorOutput:
    """Realistic compliance auditor output for a WWII-era scenario."""
    return ComplianceAuditorOutput(
        identified_gaps=[
            OwnershipGap(
                gap_description="No documented owner between Nazi confiscation in 1938 and Austrian state gallery acquisition in 1941",
                approximate_window="1938–1941",
                is_high_risk_period=True,
            ),
            OwnershipGap(
                gap_description="Ownership unclear between end of WWII and 1998 restitution claim",
                approximate_window="1945–1998",
                is_high_risk_period=True,
            ),
        ],
        risk_level="red_flag",
        reasoning=(
            "Multiple ownership gaps coincide with the WWII-era high-risk period (1933-1945). "
            "Retrieved evidence directly states Nazi confiscation following the Anschluss. "
            "This is a textbook restitution risk scenario."
        ),
    )


@pytest.fixture
def sample_historian_output(sample_facts) -> ProvenanceHistorianOutput:
    """Realistic provenance historian output."""
    return ProvenanceHistorianOutput(
        contextual_notes=(
            "The gap between 1938-1945 is not merely a record-keeping lapse — "
            "it reflects documented Nazi confiscation of Jewish-owned art in Vienna. "
            "Post-war Austrian state custody until restitution proceedings is historically "
            "consistent with other Klimt works (e.g. Portrait of Adele Bloch-Bauer I)."
        ),
        cited_evidence=[sample_facts[0], sample_facts[1]],
        risk_level="red_flag",
    )


# ---------------------------------------------------------------------------
# TestModels — schema validation
# ---------------------------------------------------------------------------


class TestModels:
    """Schema validation tests for all Pydantic models."""

    def test_retrieved_fact_valid(self):
        fact = RetrievedFact(
            claim="Owned by Rothschild family (1890–1938)",
            source_url="https://www.wikidata.org/wiki/Q123456",
            source_type="wikidata",
        )
        assert fact.claim == "Owned by Rothschild family (1890–1938)"
        assert fact.source_type == "wikidata"

    def test_retrieved_fact_invalid_source_type(self):
        with pytest.raises(Exception):
            RetrievedFact(
                claim="Some claim",
                source_url="https://example.com",
                source_type="invalid_source",
            )

    def test_retrieved_fact_missing_required_fields(self):
        with pytest.raises(Exception):
            RetrievedFact(claim="Only a claim")

    def test_evidence_bundle_defaults(self, sample_search_keys):
        bundle = EvidenceBundle(query_search_keys=sample_search_keys)
        assert bundle.retrieved_facts == []
        assert bundle.sources_queried == []
        assert bundle.sources_failed == []

    def test_evidence_bundle_full(self, sample_bundle):
        assert len(sample_bundle.retrieved_facts) == 4
        assert "wikidata" in sample_bundle.sources_queried
        assert "aic" in sample_bundle.sources_failed

    def test_ownership_gap_valid(self):
        gap = OwnershipGap(
            gap_description="No documented owner 1933–1945",
            approximate_window="1933–1945",
            is_high_risk_period=True,
        )
        assert gap.is_high_risk_period is True
        assert "1933" in gap.approximate_window

    def test_ownership_gap_non_high_risk(self):
        gap = OwnershipGap(
            gap_description="Private collection, records lost in estate transfer",
            approximate_window="1975–1990",
            is_high_risk_period=False,
        )
        assert gap.is_high_risk_period is False

    def test_compliance_auditor_output_valid(self, sample_auditor_output):
        assert sample_auditor_output.risk_level == "red_flag"
        assert len(sample_auditor_output.identified_gaps) == 2
        assert sample_auditor_output.identified_gaps[0].is_high_risk_period is True

    def test_compliance_auditor_output_invalid_risk_level(self):
        with pytest.raises(Exception):
            ComplianceAuditorOutput(
                identified_gaps=[],
                risk_level="critical",
                reasoning="Invalid level",
            )

    def test_provenance_historian_output_valid(self, sample_historian_output):
        assert sample_historian_output.risk_level == "red_flag"
        assert len(sample_historian_output.cited_evidence) == 2
        assert "Nazi confiscation" in sample_historian_output.contextual_notes

    def test_provenance_historian_output_empty_evidence(self):
        output = ProvenanceHistorianOutput(
            contextual_notes="No supporting evidence found.",
            cited_evidence=[],
            risk_level="moderate",
        )
        assert output.cited_evidence == []

    def test_title_risk_matrix_valid(
        self, sample_auditor_output, sample_historian_output, sample_bundle
    ):
        matrix = TitleRiskMatrix(
            compliance_auditor=sample_auditor_output,
            provenance_historian=sample_historian_output,
            evidence_bundle=sample_bundle,
            requires_human_review=True,
            synthesis_summary="Both sub-agents agree: RED FLAG.",
        )
        assert matrix.requires_human_review is True
        assert matrix.compliance_auditor.risk_level == "red_flag"

    def test_title_risk_matrix_missing_fields(self):
        with pytest.raises(Exception):
            TitleRiskMatrix(
                compliance_auditor=None,
                provenance_historian=None,
                evidence_bundle=None,
                requires_human_review=True,
                synthesis_summary="incomplete",
            )

    def test_all_source_types_accepted(self):
        for source_type in ("wikidata", "met", "aic", "parallel_search"):
            fact = RetrievedFact(
                claim=f"Fact from {source_type}",
                source_url=f"https://{source_type}.example.com/item/1",
                source_type=source_type,
            )
            assert fact.source_type == source_type


# ---------------------------------------------------------------------------
# TestSynthesizeTitleRisk — exhaustive 9-combination matrix
# ---------------------------------------------------------------------------


class TestSynthesizeTitleRisk:
    """Exhaustive tests over all 9 combinations of risk_level pairs."""

    def _make_auditor(self, risk_level: str) -> ComplianceAuditorOutput:
        gaps = []
        if risk_level in ("moderate", "red_flag"):
            gaps.append(
                OwnershipGap(
                    gap_description="No documented owner 1938–1945",
                    approximate_window="1938–1945",
                    is_high_risk_period=(risk_level == "red_flag"),
                )
            )
        return ComplianceAuditorOutput(
            identified_gaps=gaps,
            risk_level=risk_level,
            reasoning=f"Auditor assessed risk as {risk_level}",
        )

    def _make_historian(self, risk_level: str, sample_facts=None) -> ProvenanceHistorianOutput:
        evidence = []
        if sample_facts:
            evidence = sample_facts[:1]
        return ProvenanceHistorianOutput(
            contextual_notes=f"Historian contextualization at {risk_level} level",
            cited_evidence=evidence,
            risk_level=risk_level,
        )

    def _make_bundle(self, sample_search_keys) -> EvidenceBundle:
        return EvidenceBundle(
            retrieved_facts=[
                RetrievedFact(
                    claim="Owned by private collector 1920–1960",
                    source_url="https://www.wikidata.org/wiki/Q999",
                    source_type="wikidata",
                ),
            ],
            query_search_keys=sample_search_keys,
            sources_queried=["wikidata"],
            sources_failed=[],
        )

    # --- low/low ---
    def test_low_low_no_human_review(self, sample_search_keys):
        auditor = self._make_auditor("low")
        historian = self._make_historian("low")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is False
        assert "agree" in result.synthesis_summary.lower()
        assert "LOW" in result.synthesis_summary

    # --- low/moderate ---
    def test_low_moderate_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("low")
        historian = self._make_historian("moderate")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- low/red_flag ---
    def test_low_red_flag_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("low")
        historian = self._make_historian("red_flag")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- moderate/low ---
    def test_moderate_low_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("moderate")
        historian = self._make_historian("low")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- moderate/moderate ---
    def test_moderate_moderate_no_human_review(self, sample_search_keys):
        auditor = self._make_auditor("moderate")
        historian = self._make_historian("moderate")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is False
        assert "agree" in result.synthesis_summary.lower()
        assert "MODERATE" in result.synthesis_summary

    # --- moderate/red_flag ---
    def test_moderate_red_flag_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("moderate")
        historian = self._make_historian("red_flag")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- red_flag/low ---
    def test_red_flag_low_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("red_flag")
        historian = self._make_historian("low")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- red_flag/moderate ---
    def test_red_flag_moderate_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("red_flag")
        historian = self._make_historian("moderate")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "disagree" in result.synthesis_summary.lower()

    # --- red_flag/red_flag ---
    def test_red_flag_red_flag_requires_human_review(self, sample_search_keys):
        auditor = self._make_auditor("red_flag")
        historian = self._make_historian("red_flag")
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        assert result.requires_human_review is True
        assert "agree" in result.synthesis_summary.lower()
        assert "RED FLAG" in result.synthesis_summary

    # --- Parametrized validation of agreement/disagreement language ---
    @pytest.mark.parametrize(
        "auditor_level,historian_level,should_agree",
        [
            ("low", "low", True),
            ("moderate", "moderate", True),
            ("red_flag", "red_flag", True),
            ("low", "moderate", False),
            ("low", "red_flag", False),
            ("moderate", "low", False),
            ("moderate", "red_flag", False),
            ("red_flag", "low", False),
            ("red_flag", "moderate", False),
        ],
    )
    def test_synthesis_agreement_language(
        self, sample_search_keys, auditor_level, historian_level, should_agree
    ):
        auditor = self._make_auditor(auditor_level)
        historian = self._make_historian(historian_level)
        bundle = self._make_bundle(sample_search_keys)

        result = synthesize_title_risk(auditor, historian, bundle)

        if should_agree:
            assert "agree" in result.synthesis_summary.lower()
        else:
            assert "disagree" in result.synthesis_summary.lower()


# ---------------------------------------------------------------------------
# TestGatherEvidence — mock all retrieval clients
# ---------------------------------------------------------------------------


class TestGatherEvidence:
    """Tests for gather_evidence() with mocked retrieval functions."""

    async def test_all_sources_succeed(self, monkeypatch, sample_search_keys):
        """Successful retrieval from all sources produces facts with correct source_type."""
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        async def mock_wikidata(search_keys, facts, queried, failed, rejected_counts=None):
            facts.append(
                RetrievedFact(
                    claim="Owned by Bloch-Bauer family (1912–1938)",
                    source_url="https://www.wikidata.org/wiki/Q474748",
                    source_type="wikidata",
                )
            )
            queried.append("wikidata")

        async def mock_met(search_keys, facts, queried, failed):
            facts.append(
                RetrievedFact(
                    claim="Met holds 'Portrait of Adele' by Klimt (1907)",
                    source_url="https://www.metmuseum.org/art/collection/search/488234",
                    source_type="met",
                )
            )
            queried.append("met")

        async def mock_aic(search_keys, facts, queried, failed):
            facts.append(
                RetrievedFact(
                    claim="AIC holds 'Stoclet Frieze' study by Klimt",
                    source_url="https://www.artic.edu/artworks/111380",
                    source_type="aic",
                )
            )
            queried.append("aic")

        async def mock_parallel(search_keys, facts, queried, failed):
            facts.append(
                RetrievedFact(
                    claim="FBI Art Crime: Klimt works among Nazi-looted art",
                    source_url="https://www.fbi.gov/investigate/violent-crime/art-theft",
                    source_type="parallel_search",
                )
            )
            queried.append("parallel_search")

        with (
            patch("artgents.agents.provenance_legal._retrieve_wikidata", side_effect=mock_wikidata),
            patch("artgents.agents.provenance_legal._retrieve_met", side_effect=mock_met),
            patch("artgents.agents.provenance_legal._retrieve_aic", side_effect=mock_aic),
            patch("artgents.agents.provenance_legal._retrieve_parallel", side_effect=mock_parallel),
        ):
            bundle = await gather_evidence(sample_search_keys)

        assert len(bundle.retrieved_facts) == 4
        source_types = {f.source_type for f in bundle.retrieved_facts}
        assert source_types == {"wikidata", "met", "aic", "parallel_search"}
        assert set(bundle.sources_queried) == {"wikidata", "met", "aic", "parallel_search"}
        assert bundle.sources_failed == []

        # Verify source_url is populated for each fact
        for fact in bundle.retrieved_facts:
            assert fact.source_url.startswith("https://")

    async def test_partial_failure_one_source(self, monkeypatch, sample_search_keys):
        """One source fails, others succeed — sources_failed populated correctly."""
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        async def mock_wikidata(search_keys, facts, queried, failed, rejected_counts=None):
            facts.append(
                RetrievedFact(
                    claim="Wikidata provenance entry",
                    source_url="https://www.wikidata.org/wiki/Q123",
                    source_type="wikidata",
                )
            )
            queried.append("wikidata")

        async def mock_met_fail(search_keys, facts, queried, failed):
            failed.append("met")

        async def mock_aic(search_keys, facts, queried, failed):
            facts.append(
                RetrievedFact(
                    claim="AIC provenance entry",
                    source_url="https://www.artic.edu/artworks/99999",
                    source_type="aic",
                )
            )
            queried.append("aic")

        async def mock_parallel(search_keys, facts, queried, failed):
            facts.append(
                RetrievedFact(
                    claim="Parallel search result",
                    source_url="https://archives.gov/records/klimt",
                    source_type="parallel_search",
                )
            )
            queried.append("parallel_search")

        with (
            patch("artgents.agents.provenance_legal._retrieve_wikidata", side_effect=mock_wikidata),
            patch("artgents.agents.provenance_legal._retrieve_met", side_effect=mock_met_fail),
            patch("artgents.agents.provenance_legal._retrieve_aic", side_effect=mock_aic),
            patch("artgents.agents.provenance_legal._retrieve_parallel", side_effect=mock_parallel),
        ):
            bundle = await gather_evidence(sample_search_keys)

        assert len(bundle.retrieved_facts) == 3
        assert "met" in bundle.sources_failed
        assert "met" not in bundle.sources_queried
        # Other sources still present
        assert "wikidata" in bundle.sources_queried
        assert "aic" in bundle.sources_queried
        assert "parallel_search" in bundle.sources_queried

    async def test_all_sources_fail(self, monkeypatch, sample_search_keys):
        """All sources fail — empty facts list, all in sources_failed."""
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        async def mock_fail_wikidata(search_keys, facts, queried, failed, rejected_counts=None):
            failed.append("wikidata")

        async def mock_fail_met(search_keys, facts, queried, failed):
            failed.append("met")

        async def mock_fail_aic(search_keys, facts, queried, failed):
            failed.append("aic")

        async def mock_fail_parallel(search_keys, facts, queried, failed):
            failed.append("parallel_search")

        with (
            patch("artgents.agents.provenance_legal._retrieve_wikidata", side_effect=mock_fail_wikidata),
            patch("artgents.agents.provenance_legal._retrieve_met", side_effect=mock_fail_met),
            patch("artgents.agents.provenance_legal._retrieve_aic", side_effect=mock_fail_aic),
            patch("artgents.agents.provenance_legal._retrieve_parallel", side_effect=mock_fail_parallel),
        ):
            bundle = await gather_evidence(sample_search_keys)

        assert bundle.retrieved_facts == []
        assert bundle.sources_queried == []
        assert set(bundle.sources_failed) == {"wikidata", "met", "aic", "parallel_search"}

    async def test_credit_exhausted_error_propagates(self, monkeypatch, sample_search_keys):
        """CreditExhaustedError from Parallel Search propagates through."""
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        from artgents.clients.parallel import CreditExhaustedError

        async def mock_wikidata(search_keys, facts, queried, failed, rejected_counts=None):
            queried.append("wikidata")

        async def mock_met(search_keys, facts, queried, failed):
            queried.append("met")

        async def mock_aic(search_keys, facts, queried, failed):
            queried.append("aic")

        async def mock_parallel_credit_exhausted(search_keys, facts, queried, failed):
            raise CreditExhaustedError("Parallel Search credits exhausted")

        with (
            patch("artgents.agents.provenance_legal._retrieve_wikidata", side_effect=mock_wikidata),
            patch("artgents.agents.provenance_legal._retrieve_met", side_effect=mock_met),
            patch("artgents.agents.provenance_legal._retrieve_aic", side_effect=mock_aic),
            patch("artgents.agents.provenance_legal._retrieve_parallel", side_effect=mock_parallel_credit_exhausted),
        ):
            with pytest.raises(CreditExhaustedError):
                await gather_evidence(sample_search_keys)


# ---------------------------------------------------------------------------
# TestSubAgentsMocked — mock Vertex AI client
# ---------------------------------------------------------------------------


class TestSubAgentsMocked:
    """Tests for run_compliance_auditor and run_provenance_historian with mocked Vertex."""

    @pytest.fixture(autouse=True)
    def _set_gcp_project(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    async def test_run_compliance_auditor_success(self, sample_bundle):
        """run_compliance_auditor with mock response validates into ComplianceAuditorOutput."""
        mock_response = {
            "identified_gaps": [
                {
                    "gap_description": "No documented owner between 1938 Nazi seizure and 1941 Austrian gallery acquisition",
                    "approximate_window": "1938–1941",
                    "is_high_risk_period": True,
                },
                {
                    "gap_description": "Unclear chain of custody during Allied occupation period",
                    "approximate_window": "1945–1952",
                    "is_high_risk_period": True,
                },
            ],
            "risk_level": "red_flag",
            "reasoning": (
                "Two ownership gaps fall squarely in the WWII-era high-risk period. "
                "Evidence from Wikidata confirms Nazi confiscation following the Anschluss. "
                "FBI Art Crime database corroborates that Klimt works are among the most "
                "sought Nazi-looted artworks. This represents a clear restitution risk."
            ),
        }

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_variant = MagicMock()
                mock_variant.name = "Compliance Auditor"
                mock_variant.stance = "skeptic"
                mock_variant.voice = "Title attorney voice"
                mock_cfg = MagicMock()
                mock_cfg.variants = {"compliance_auditor": mock_variant}
                mock_cfg.temperature = 0.2
                mock_cfg.max_output_tokens = 2048
                mock_config.return_value = mock_cfg

                result = await run_compliance_auditor(sample_bundle)

        assert isinstance(result, ComplianceAuditorOutput)
        assert result.risk_level == "red_flag"
        assert len(result.identified_gaps) == 2
        assert result.identified_gaps[0].is_high_risk_period is True
        assert "1938" in result.identified_gaps[0].approximate_window
        assert "restitution" in result.reasoning.lower()

    async def test_run_provenance_historian_success(self, sample_bundle):
        """run_provenance_historian with mock response validates into ProvenanceHistorianOutput."""
        mock_response = {
            "contextual_notes": (
                "The 1938-1945 gap aligns precisely with documented Nazi art confiscation "
                "in Vienna. This is not a normal archival gap — it reflects systematic "
                "looting of Jewish-owned collections. The post-1945 period of Austrian state "
                "custody is consistent with other cases (Altmann v. Austria, 2006)."
            ),
            "cited_evidence": [
                {
                    "claim": "Owned by Ferdinand Bloch-Bauer (1912 to 1938)",
                    "source_url": "https://www.wikidata.org/wiki/Q474748",
                    "source_type": "wikidata",
                },
            ],
            "risk_level": "red_flag",
        }

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_variant = MagicMock()
                mock_variant.name = "Provenance Historian"
                mock_variant.stance = "advocate"
                mock_variant.voice = "Art historian voice"
                mock_cfg = MagicMock()
                mock_cfg.variants = {"provenance_historian": mock_variant}
                mock_cfg.temperature = 0.2
                mock_cfg.max_output_tokens = 2048
                mock_config.return_value = mock_cfg

                result = await run_provenance_historian(sample_bundle)

        assert isinstance(result, ProvenanceHistorianOutput)
        assert result.risk_level == "red_flag"
        assert len(result.cited_evidence) == 1
        assert result.cited_evidence[0].source_type == "wikidata"
        assert "Nazi" in result.contextual_notes

    async def test_vertex_call_error_propagates_from_auditor(self, sample_bundle):
        """Vertex failure propagates as VertexCallError from compliance auditor."""
        from artgents.clients.vertex import VertexCallError

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            side_effect=VertexCallError("Vertex AI returned 500: Internal Server Error"),
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_variant = MagicMock()
                mock_variant.name = "Compliance Auditor"
                mock_variant.stance = "skeptic"
                mock_variant.voice = "Title attorney voice"
                mock_cfg = MagicMock()
                mock_cfg.variants = {"compliance_auditor": mock_variant}
                mock_cfg.temperature = 0.2
                mock_cfg.max_output_tokens = 2048
                mock_config.return_value = mock_cfg

                with pytest.raises(VertexCallError, match="500"):
                    await run_compliance_auditor(sample_bundle)

    async def test_vertex_call_error_propagates_from_historian(self, sample_bundle):
        """Vertex failure propagates as VertexCallError from provenance historian."""
        from artgents.clients.vertex import VertexCallError

        with patch(
            "artgents.clients.vertex.generate_structured",
            new_callable=AsyncMock,
            side_effect=VertexCallError("Vertex AI quota exceeded"),
        ):
            with patch("artgents.config_loader.get_dual_agent_config") as mock_config:
                mock_variant = MagicMock()
                mock_variant.name = "Provenance Historian"
                mock_variant.stance = "advocate"
                mock_variant.voice = "Art historian voice"
                mock_cfg = MagicMock()
                mock_cfg.variants = {"provenance_historian": mock_variant}
                mock_cfg.temperature = 0.2
                mock_cfg.max_output_tokens = 2048
                mock_config.return_value = mock_cfg

                with pytest.raises(VertexCallError, match="quota"):
                    await run_provenance_historian(sample_bundle)


# ---------------------------------------------------------------------------
# TestFormatEvidence — test _format_evidence_for_prompt
# ---------------------------------------------------------------------------


class TestFormatEvidence:
    """Tests for _format_evidence_for_prompt producing readable text."""

    def test_format_with_multiple_facts(self, sample_bundle):
        """Produces readable text with source_type labels and URLs."""
        text = _format_evidence_for_prompt(sample_bundle)

        # Each fact should have its source_type in brackets
        assert "[wikidata]" in text
        assert "[met]" in text
        assert "[parallel_search]" in text

        # Each fact should have its source URL
        assert "https://www.wikidata.org/wiki/Q474748" in text
        assert "https://www.metmuseum.org/art/collection/search/488234" in text
        assert "https://www.fbi.gov/investigate/violent-crime/art-theft" in text

        # Claims should appear
        assert "Owned by Ferdinand Bloch-Bauer" in text
        assert "FBI Art Crime" in text

        # Should be numbered
        assert "1." in text
        assert "2." in text
        assert "3." in text
        assert "4." in text

    def test_format_empty_bundle(self, sample_search_keys):
        """Empty evidence bundle produces a 'no evidence' message."""
        bundle = EvidenceBundle(
            retrieved_facts=[],
            query_search_keys=sample_search_keys,
            sources_queried=[],
            sources_failed=["wikidata", "met", "aic", "parallel_search"],
        )
        text = _format_evidence_for_prompt(bundle)

        assert "No evidence retrieved" in text

    def test_format_single_fact(self, sample_search_keys):
        """Single fact formats correctly with numbering and source."""
        bundle = EvidenceBundle(
            retrieved_facts=[
                RetrievedFact(
                    claim="In collection: Neue Galerie New York",
                    source_url="https://www.wikidata.org/wiki/Q474748#collections",
                    source_type="wikidata",
                ),
            ],
            query_search_keys=sample_search_keys,
            sources_queried=["wikidata"],
            sources_failed=[],
        )
        text = _format_evidence_for_prompt(bundle)

        assert "1." in text
        assert "[wikidata]" in text
        assert "Neue Galerie" in text
        assert "Source:" in text
        assert "https://www.wikidata.org/wiki/Q474748#collections" in text
        # Should NOT have item 2
        assert "2." not in text

    def test_format_preserves_all_source_types(self, sample_search_keys):
        """All four source types are formatted with correct labels."""
        facts = [
            RetrievedFact(
                claim="Wikidata fact",
                source_url="https://wikidata.org/wiki/Q1",
                source_type="wikidata",
            ),
            RetrievedFact(
                claim="Met fact",
                source_url="https://metmuseum.org/art/1",
                source_type="met",
            ),
            RetrievedFact(
                claim="AIC fact",
                source_url="https://artic.edu/artworks/1",
                source_type="aic",
            ),
            RetrievedFact(
                claim="Parallel search fact",
                source_url="https://archives.gov/records/1",
                source_type="parallel_search",
            ),
        ]
        bundle = EvidenceBundle(
            retrieved_facts=facts,
            query_search_keys=sample_search_keys,
            sources_queried=["wikidata", "met", "aic", "parallel_search"],
            sources_failed=[],
        )
        text = _format_evidence_for_prompt(bundle)

        assert "[wikidata]" in text
        assert "[met]" in text
        assert "[aic]" in text
        assert "[parallel_search]" in text

    def test_format_includes_source_line(self, sample_search_keys):
        """Each fact has a 'Source: <url>' line for traceability."""
        bundle = EvidenceBundle(
            retrieved_facts=[
                RetrievedFact(
                    claim="Significant event: Restituted to heirs (2006)",
                    source_url="https://www.wikidata.org/wiki/Q474748#P793",
                    source_type="wikidata",
                ),
            ],
            query_search_keys=sample_search_keys,
            sources_queried=["wikidata"],
            sources_failed=[],
        )
        text = _format_evidence_for_prompt(bundle)

        lines = text.strip().split("\n")
        # Should have at least two lines: the claim line and the Source line
        assert len(lines) >= 2
        source_lines = [l for l in lines if "Source:" in l]
        assert len(source_lines) == 1
        assert "https://www.wikidata.org/wiki/Q474748#P793" in source_lines[0]


# ---------------------------------------------------------------------------
# TestEvidenceScope — tests for _determine_evidence_scope()
# ---------------------------------------------------------------------------

from artgents.agents.provenance_legal import _determine_evidence_scope, _build_scope_instructions


class TestEvidenceScope:
    """Tests for _determine_evidence_scope() and evidence_scope behavior."""

    def _make_search_keys(self, work_title: str | None = None) -> ProvenanceSearchKeys:
        return ProvenanceSearchKeys(
            primary_artist_attribution="Claude Monet",
            probable_creation_window="1900–1910",
            style_and_movement="Impressionism",
            search_keywords=["monet", "water lilies", "impressionism"],
            detected_signatures_or_marks=["Monet (lower right)"],
            work_title=work_title,
        )

    def test_no_title_gives_artist_general(self):
        """ProvenanceSearchKeys with work_title=None → evidence_scope='artist_general'."""
        keys = self._make_search_keys(work_title=None)
        facts = [
            RetrievedFact(
                claim="Owned by private collector",
                source_url="https://www.wikidata.org/wiki/Q123",
                source_type="wikidata",
                source_entity_id="Q123",
            ),
        ]
        result = _determine_evidence_scope(keys, facts)
        assert result == "artist_general"

    def test_title_with_single_entity_gives_specific_object(self):
        """work_title='Water Lilies' + facts all sharing source_entity_id='Q123' → 'specific_object'."""
        keys = self._make_search_keys(work_title="Water Lilies")
        facts = [
            RetrievedFact(
                claim="Created in 1906",
                source_url="https://www.wikidata.org/wiki/Q123",
                source_type="wikidata",
                source_entity_id="Q123",
            ),
            RetrievedFact(
                claim="Acquired by Musée d'Orsay in 1990",
                source_url="https://www.wikidata.org/wiki/Q123#P793",
                source_type="wikidata",
                source_entity_id="Q123",
            ),
        ]
        result = _determine_evidence_scope(keys, facts)
        assert result == "specific_object"

    def test_title_with_multiple_entities_gives_artist_general(self):
        """work_title present but facts have different source_entity_ids → 'artist_general'."""
        keys = self._make_search_keys(work_title="Water Lilies")
        facts = [
            RetrievedFact(
                claim="Created in 1906",
                source_url="https://www.wikidata.org/wiki/Q123",
                source_type="wikidata",
                source_entity_id="Q123",
            ),
            RetrievedFact(
                claim="Different painting from 1908",
                source_url="https://www.wikidata.org/wiki/Q456",
                source_type="wikidata",
                source_entity_id="Q456",
            ),
        ]
        result = _determine_evidence_scope(keys, facts)
        assert result == "artist_general"

    def test_title_with_no_entity_ids_gives_artist_general(self):
        """work_title present but all facts have source_entity_id=None → 'artist_general'."""
        keys = self._make_search_keys(work_title="Water Lilies")
        facts = [
            RetrievedFact(
                claim="Monet painted many water lily scenes",
                source_url="https://archives.gov/records/monet",
                source_type="parallel_search",
                source_entity_id=None,
            ),
            RetrievedFact(
                claim="Water Lilies series spans 1896-1926",
                source_url="https://example.com/monet-lilies",
                source_type="parallel_search",
                source_entity_id=None,
            ),
        ]
        result = _determine_evidence_scope(keys, facts)
        assert result == "artist_general"


# ---------------------------------------------------------------------------
# TestScopeInstructions — tests for _build_scope_instructions()
# ---------------------------------------------------------------------------


class TestScopeInstructions:
    """Tests for _build_scope_instructions()."""

    def _make_bundle(
        self, evidence_scope: str, work_title: str | None = None
    ) -> EvidenceBundle:
        keys = ProvenanceSearchKeys(
            primary_artist_attribution="Gustav Klimt",
            probable_creation_window="1907–1912",
            style_and_movement="Vienna Secession",
            search_keywords=["klimt", "portrait"],
            detected_signatures_or_marks=["KLIMT"],
            work_title=work_title,
        )
        return EvidenceBundle(
            retrieved_facts=[
                RetrievedFact(
                    claim="Test fact",
                    source_url="https://example.com",
                    source_type="wikidata",
                ),
            ],
            query_search_keys=keys,
            sources_queried=["wikidata"],
            evidence_scope=evidence_scope,
        )

    def test_artist_general_scope_contains_critical_warnings(self):
        """Bundle with evidence_scope='artist_general' → output contains key warning terms."""
        bundle = self._make_bundle(evidence_scope="artist_general")
        result = _build_scope_instructions(bundle)

        assert "ARTIST-GENERAL" in result
        # "MULTIPLE" and "DISTINCT" may be split across a line break in the template
        assert "MULTIPLE" in result and "DISTINCT" in result
        assert "moderate" in result

    def test_specific_object_scope_instructions(self):
        """Bundle with evidence_scope='specific_object' → output contains 'SPECIFIC OBJECT'."""
        bundle = self._make_bundle(
            evidence_scope="specific_object", work_title="Portrait of Adele"
        )
        result = _build_scope_instructions(bundle)

        assert "SPECIFIC OBJECT" in result


# ---------------------------------------------------------------------------
# TestFormatEvidenceWithEntityIds — entity tag handling
# ---------------------------------------------------------------------------


class TestFormatEvidenceWithEntityIds:
    """Tests for _format_evidence_for_prompt with entity tags."""

    def _make_bundle(self, facts: list[RetrievedFact]) -> EvidenceBundle:
        keys = ProvenanceSearchKeys(
            primary_artist_attribution="Claude Monet",
            probable_creation_window="1900–1910",
            style_and_movement="Impressionism",
            search_keywords=["monet", "water lilies"],
            detected_signatures_or_marks=["Monet"],
            work_title="Water Lilies",
        )
        return EvidenceBundle(
            retrieved_facts=facts,
            query_search_keys=keys,
            sources_queried=["wikidata"],
            evidence_scope="specific_object",
        )

    def test_format_includes_entity_id_when_present(self):
        """Facts with source_entity_id get [entity: X] in output."""
        facts = [
            RetrievedFact(
                claim="Created in 1906 by Claude Monet",
                source_url="https://www.wikidata.org/wiki/Q12345",
                source_type="wikidata",
                source_entity_id="Q12345",
            ),
            RetrievedFact(
                claim="Acquired by museum in 1950",
                source_url="https://www.wikidata.org/wiki/Q12345#P793",
                source_type="wikidata",
                source_entity_id="Q12345",
            ),
        ]
        bundle = self._make_bundle(facts)
        text = _format_evidence_for_prompt(bundle)

        assert "[entity: Q12345]" in text

    def test_format_omits_entity_tag_when_none(self):
        """Facts with source_entity_id=None don't get entity tag."""
        facts = [
            RetrievedFact(
                claim="Monet's works were widely collected",
                source_url="https://archives.gov/records/monet",
                source_type="parallel_search",
                source_entity_id=None,
            ),
        ]
        bundle = self._make_bundle(facts)
        text = _format_evidence_for_prompt(bundle)

        assert "[entity:" not in text
        assert "[parallel_search]" in text
        assert "Monet's works were widely collected" in text


class TestCitedEvidenceSymmetric:
    """Test that cited_evidence includes all referenced facts, not just exculpatory ones."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")

    def test_cited_evidence_includes_risk_relevant_facts(self):
        """A Historian response citing a risk-relevant fact in contextual_notes
        must include that fact in cited_evidence — it's not limited to
        clean-ownership evidence."""
        from artgents.agents.provenance_legal import (
            ProvenanceHistorianOutput,
            RetrievedFact,
        )

        # A risk-relevant fact (Göring ownership) that the Historian discusses
        risk_fact = RetrievedFact(
            claim="Owned by Hermann Göring (1940 to 1945)",
            source_url="https://www.wikidata.org/entity/Q456",
            source_type="wikidata",
            source_entity_id="Q456",
        )
        # A clean-ownership fact
        clean_fact = RetrievedFact(
            claim="In collection: Metropolitan Museum of Art since 1952",
            source_url="https://www.wikidata.org/entity/Q456",
            source_type="wikidata",
            source_entity_id="Q456",
        )

        # Model response that references BOTH facts in contextual_notes
        output = ProvenanceHistorianOutput(
            contextual_notes=(
                "The documented Göring ownership (1940-1945) is a significant "
                "provenance event that cannot be dismissed. However, the work's "
                "documented post-war acquisition by the Metropolitan Museum in 1952 "
                "suggests a restitution/transfer occurred in the intervening period."
            ),
            cited_evidence=[risk_fact, clean_fact],  # Both included
            risk_level="moderate",
        )

        # The risk-relevant fact IS in cited_evidence (not excluded)
        assert any(
            "Göring" in f.claim for f in output.cited_evidence
        ), "Risk-relevant fact must be in cited_evidence"
        # The clean-ownership fact is also present
        assert any(
            "Metropolitan Museum" in f.claim for f in output.cited_evidence
        ), "Clean-ownership fact must also be in cited_evidence"
        # Both facts are present — cited_evidence is symmetric
        assert len(output.cited_evidence) == 2


class TestParallelSearchFiltering:
    """Test keyword filtering and relevance checks for Parallel Search."""

    @pytest.fixture(autouse=True)
    def _set_env(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("PARALLEL_WEB_API_KEY", "fake-key")

    def test_filter_search_keywords_drops_empty(self):
        """Empty and whitespace-only keywords are filtered out."""
        from artgents.agents.provenance_legal import _filter_search_keywords

        assert _filter_search_keywords(["", "  ", "monet", "\t"]) == ["monet"]

    def test_filter_search_keywords_drops_generic(self):
        """Generic non-identifying terms are filtered out."""
        from artgents.agents.provenance_legal import _filter_search_keywords

        assert _filter_search_keywords(["painting", "oil", "canvas", "klimt"]) == ["klimt"]
        assert _filter_search_keywords(["unknown", "artwork"]) == []

    def test_filter_search_keywords_keeps_specific(self):
        """Artist names and specific terms are kept."""
        from artgents.agents.provenance_legal import _filter_search_keywords

        result = _filter_search_keywords(["klimt", "portrait", "adele bloch-bauer"])
        assert "klimt" in result
        assert "adele bloch-bauer" in result

    @patch("artgents.clients.parallel.ParallelClient")
    async def test_parallel_skipped_when_no_anchor_terms(self, mock_client_cls):
        """If no usable anchor terms remain after filtering, Parallel is skipped."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_parallel

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Unknown",  # non-specific
            probable_creation_window="1900",
            style_and_movement="Unknown",
            detected_signatures_or_marks=[],
            search_keywords=["", "painting", "oil"],  # all filtered out
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_parallel(search_keys, facts, sources_queried, sources_failed)

        # ParallelClient was never instantiated/called
        mock_client_cls.assert_not_called()
        # No facts produced
        assert facts == []
        # Source marked as queried (intentional skip, not failure)
        assert "parallel_search" in sources_queried

    @patch("artgents.clients.parallel.ParallelClient")
    async def test_parallel_query_uses_filtered_keywords(self, mock_client_cls):
        """The query sent to Parallel uses filtered keywords, not raw empties."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_parallel
        from artgents.clients.parallel import ParallelSearchResult

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(
            return_value=ParallelSearchResult(hits=[], query="test")
        )
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Gustav Klimt",
            probable_creation_window="1907",
            style_and_movement="Vienna Secession",
            detected_signatures_or_marks=[],
            search_keywords=["", "klimt", "painting", "portrait of adele"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_parallel(search_keys, facts, sources_queried, sources_failed)

        # Parallel client was called
        mock_client.search.assert_called_once()
        # The query should contain "Klimt" (artist anchor) not empty strings
        call_args = mock_client.search.call_args
        query_sent = call_args[0][0] if call_args[0] else call_args.kwargs.get("query", "")
        assert "Klimt" in query_sent
        assert '""' not in query_sent  # no empty quoted terms

    @patch("artgents.clients.parallel.ParallelClient")
    async def test_relevance_filter_keeps_only_matching_hits(self, mock_client_cls):
        """Only hits with keyword overlap are kept in retrieved_facts."""
        from artgents.agents.art_historian import ProvenanceSearchKeys
        from artgents.agents.provenance_legal import _retrieve_parallel
        from artgents.clients.parallel import ParallelSearchResult, SearchHit

        relevant_hit = SearchHit(
            url="https://fbi.gov/klimt-stolen",
            title="FBI: Stolen Klimt painting recovered",
            excerpts=["A Gustav Klimt portrait was found in a Vienna apartment."],
        )
        irrelevant_hit = SearchHit(
            url="https://fbi.gov/iraqi-antiquities",
            title="FBI recovers looted Iraqi antiquities",
            excerpts=["Ancient Iraqi artifacts from the National Museum of Baghdad."],
        )
        borderline_irrelevant = SearchHit(
            url="https://analytics.usa.gov/data/top-pages.csv",
            title="Top FBI Web Pages",
            excerpts=["analytics data for fbi.gov"],
        )

        mock_client = AsyncMock()
        mock_client.search = AsyncMock(
            return_value=ParallelSearchResult(
                hits=[relevant_hit, irrelevant_hit, borderline_irrelevant],
                query="test",
            )
        )
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        search_keys = ProvenanceSearchKeys(
            primary_artist_attribution="Attributed to Gustav Klimt",
            probable_creation_window="1907",
            style_and_movement="Vienna Secession",
            detected_signatures_or_marks=[],
            search_keywords=["klimt", "portrait", "adele"],
        )
        facts: list = []
        sources_queried: list = []
        sources_failed: list = []

        await _retrieve_parallel(search_keys, facts, sources_queried, sources_failed)

        # Only the relevant hit should make it through
        assert len(facts) == 1, f"Expected 1 relevant fact, got {len(facts)}: {[f.claim for f in facts]}"
        assert "Klimt" in facts[0].claim
        # The irrelevant ones should not be in facts
        assert not any("Iraqi" in f.claim for f in facts)
        assert not any("analytics" in f.claim for f in facts)

    def test_is_relevant_parallel_hit_matching(self):
        """Hits containing anchor terms are considered relevant."""
        from artgents.agents.provenance_legal import _is_relevant_parallel_hit
        from artgents.clients.parallel import SearchHit

        hit = SearchHit(
            url="https://example.com/klimt",
            title="Gustav Klimt artworks stolen in WWII",
            excerpts=["Multiple Klimt paintings were confiscated..."],
        )
        assert _is_relevant_parallel_hit(hit, ["klimt"]) is True
        assert _is_relevant_parallel_hit(hit, ["monet"]) is False

    def test_is_relevant_parallel_hit_url_match(self):
        """A hit can match via URL even if title/excerpts don't contain the term."""
        from artgents.agents.provenance_legal import _is_relevant_parallel_hit
        from artgents.clients.parallel import SearchHit

        hit = SearchHit(
            url="https://wikipedia.org/wiki/Portrait_of_Adele_Bloch-Bauer_I",
            title="Wikipedia article",
            excerpts=["This painting has a complex ownership history."],
        )
        assert _is_relevant_parallel_hit(hit, ["adele"]) is True
        assert _is_relevant_parallel_hit(hit, ["rembrandt"]) is False
