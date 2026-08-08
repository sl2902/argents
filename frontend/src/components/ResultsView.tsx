import { useState } from 'react';
import { AnalyzeResponse } from '../types/api';
import DualAgentCard from './DualAgentCard';
import EvidenceList from './EvidenceList';
import DisclosuresBanner from './DisclosuresBanner';
import StageTimingChart from './StageTimingChart';
import VariantToggle from './VariantToggle';
import GlossaryText from './GlossaryText';
import Lightbox from './Lightbox';

interface ResultsViewProps {
  result: AnalyzeResponse;
  onReset: () => void;
  imageUrl: string | null;
}

export default function ResultsView({ result, onReset, imageUrl }: ResultsViewProps) {
  const [variant, setVariant] = useState<'auction_house' | 'public_gallery'>('public_gallery');
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const curatorOutput = variant === 'auction_house' ? result.curator_auction_house : result.curator_public_gallery;

  const provenanceDisagreement = result.compliance_auditor.risk_level !== result.provenance_historian.risk_level;
  const valuationSpread = result.valuation_corridor.high_estimate_usd / result.valuation_corridor.low_estimate_usd;
  const valuationWideSpread = valuationSpread > 3;

  return (
    <div className="space-y-6">
      {/* Header with thumbnail */}
      <div className="flex items-start gap-6">
        {imageUrl && (
          <img
            src={imageUrl}
            alt="Analyzed artwork"
            className="w-32 h-32 rounded-lg shadow-md object-cover shrink-0 cursor-pointer hover:ring-2 hover:ring-indigo-400 transition-all"
            onClick={() => setLightboxOpen(true)}
          />
        )}
        <div className="flex-1">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">{curatorOutput.suggested_title}</h2>
              <p className="text-lg text-gray-600 mt-1">{result.attribution}</p>
              <p className="text-sm text-gray-500">{result.period_style}</p>
            </div>
            <button onClick={onReset} className="text-sm text-indigo-600 hover:text-indigo-800 underline">
              New Analysis
            </button>
          </div>
        </div>
      </div>

      {/* Disclosures - prominent, always visible */}
      <DisclosuresBanner disclosures={curatorOutput.disclosures} />

      {/* Visual Analysis Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-3">Visual Analysis</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-gray-600">
          <div>
            <h4 className="font-semibold text-gray-700 mb-1">Composition</h4>
            <p><GlossaryText text={result.composition_analysis} /></p>
          </div>
          <div>
            <h4 className="font-semibold text-gray-700 mb-1">Condition</h4>
            <p><GlossaryText text={result.condition_notes} /></p>
          </div>
          <div>
            <h4 className="font-semibold text-gray-700 mb-1">Stylistic Authentication</h4>
            <p><GlossaryText text={result.stylistic_authenticity_notes} /></p>
          </div>
        </div>
      </div>

      {/* Provenance - Dual Agent Card */}
      <DualAgentCard
        title="Provenance Assessment"
        leftLabel="Compliance Auditor"
        leftContent={
          <div className="space-y-2">
            <p><GlossaryText text={result.compliance_auditor.reasoning} /></p>
            {result.compliance_auditor.identified_gaps.length > 0 && (
              <div className="mt-2">
                <p className="font-semibold text-xs text-gray-500">Identified gaps:</p>
                {result.compliance_auditor.identified_gaps.map((gap, i) => (
                  <p key={i} className="text-xs">
                    • {gap.gap_description} ({gap.approximate_window})
                    {gap.is_high_risk_period && <span className="text-red-600 font-semibold"> [HIGH RISK PERIOD]</span>}
                  </p>
                ))}
              </div>
            )}
          </div>
        }
        leftVerdict={result.compliance_auditor.risk_level}
        rightLabel="Provenance Historian"
        rightContent={<p><GlossaryText text={result.provenance_historian.contextual_notes} /></p>}
        rightVerdict={result.provenance_historian.risk_level}
        disagreement={provenanceDisagreement}
        synthesisSummary={result.provenance_synthesis_summary}
      />

      {/* Valuation - Dual Agent Card */}
      <DualAgentCard
        title="Financial Valuation"
        leftLabel="Conservative Appraiser"
        leftContent={
          <div className="space-y-1">
            <p className="text-lg font-bold text-gray-800">
              ${result.conservative_appraiser.floor_estimate_usd.toLocaleString()}
            </p>
            <p className="text-xs text-gray-500">Primary comp: <GlossaryText text={result.conservative_appraiser.primary_comp} /></p>
            <p><GlossaryText text={result.conservative_appraiser.methodology} /></p>
          </div>
        }
        leftVerdict={result.conservative_appraiser.confidence}
        rightLabel="Bullish Specialist"
        rightContent={
          <div className="space-y-1">
            <p className="text-lg font-bold text-gray-800">
              ${result.bullish_specialist.ceiling_estimate_usd.toLocaleString()}
            </p>
            <p className="text-xs text-gray-500">Primary comp: <GlossaryText text={result.bullish_specialist.primary_comp} /></p>
            <p><GlossaryText text={result.bullish_specialist.methodology} /></p>
          </div>
        }
        rightVerdict={result.bullish_specialist.confidence}
        disagreement={valuationWideSpread}
        disagreementLabel={valuationWideSpread ? `Wide valuation spread ($${result.valuation_corridor.low_estimate_usd.toLocaleString()} vs $${result.valuation_corridor.high_estimate_usd.toLocaleString()})` : undefined}
        synthesisSummary={result.corridor_summary}
      />

      {/* Evidence */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <h3 className="text-lg font-bold text-gray-900">Evidence Trail</h3>
        <EvidenceList
          title="Provenance Sources"
          items={result.provenance_evidence_sample}
          totalCount={result.total_provenance_facts}
        />
        <EvidenceList
          title="Valuation Comparables"
          items={result.valuation_evidence_sample}
          totalCount={result.total_valuation_comps}
        />
      </div>

      {/* Curator Output with Variant Toggle */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">Exhibition Copy</h3>
          <VariantToggle selected={variant} onChange={setVariant} />
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Exhibition Narrative</h4>
          <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
            <GlossaryText text={curatorOutput.exhibition_narrative} />
          </p>
        </div>

        <div className="border-t border-gray-100 pt-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Wall Label</h4>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 italic text-sm text-gray-700">
            <GlossaryText text={curatorOutput.wall_label} />
          </div>
        </div>
      </div>

      {/* Stage Timing */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <StageTimingChart timings={result.timings} />
      </div>

      {/* Lightbox */}
      {lightboxOpen && imageUrl && (
        <Lightbox imageUrl={imageUrl} onClose={() => setLightboxOpen(false)} />
      )}
    </div>
  );
}
