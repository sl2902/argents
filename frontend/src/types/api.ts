export interface OwnershipGap {
  gap_description: string;
  approximate_window: string;
  is_high_risk_period: boolean;
}

export interface ComplianceAuditorOutput {
  identified_gaps: OwnershipGap[];
  risk_level: 'low' | 'moderate' | 'red_flag' | 'cannot_determine_insufficient_object_data';
  reasoning: string;
}

export interface RetrievedFact {
  claim: string;
  source_url: string;
  source_type: string;
  source_entity_id: string | null;
}

export interface ProvenanceHistorianOutput {
  contextual_notes: string;
  cited_evidence: RetrievedFact[];
  risk_level: 'low' | 'moderate' | 'red_flag' | 'cannot_determine_insufficient_object_data';
}

export interface ConservativeAppraiserOutput {
  floor_estimate_usd: number;
  methodology: string;
  primary_comp: string;
  confidence: 'low' | 'moderate' | 'high';
}

export interface BullishSpecialistOutput {
  ceiling_estimate_usd: number;
  methodology: string;
  primary_comp: string;
  confidence: 'low' | 'moderate' | 'high';
}

export interface ValuationCorridor {
  low_estimate_usd: number;
  high_estimate_usd: number;
}

export interface CuratorVariantOutput {
  exhibition_narrative: string;
  wall_label: string;
  suggested_title: string;
  disclosures: string[];
}

export interface EvidenceItemDisplay {
  description: string;
  source_url: string;
  source_type: string;
}

export interface StageTimings {
  visual_analysis_ms: number;
  stage_2_wall_clock_ms: number;
  provenance_ms: number;
  valuation_ms: number;
  curator_ms: number;
  total_ms: number;
}

export interface AnalyzeResponse {
  attribution: string;
  period_style: string;
  composition_analysis: string;
  condition_notes: string;
  stylistic_authenticity_notes: string;
  compliance_auditor: ComplianceAuditorOutput;
  provenance_historian: ProvenanceHistorianOutput;
  provenance_synthesis_summary: string;
  provenance_requires_human_review: boolean;
  provenance_evidence_scope: 'specific_object' | 'artist_general';
  conservative_appraiser: ConservativeAppraiserOutput;
  bullish_specialist: BullishSpecialistOutput;
  valuation_corridor: ValuationCorridor;
  corridor_summary: string;
  valuation_requires_human_review: boolean;
  valuation_evidence_scope: 'specific_object' | 'artist_general';
  curator_auction_house: CuratorVariantOutput;
  curator_public_gallery: CuratorVariantOutput;
  provenance_evidence_sample: EvidenceItemDisplay[];
  valuation_evidence_sample: EvidenceItemDisplay[];
  total_provenance_facts: number;
  total_valuation_comps: number;
  timings: StageTimings;
}

export interface ErrorResponse {
  error: string;
  stage: string;
}
