import { ReactNode } from 'react';

interface DualAgentCardProps {
  title: string;
  leftLabel: string;
  leftContent: ReactNode;
  leftVerdict: string;
  rightLabel: string;
  rightContent: ReactNode;
  rightVerdict: string;
  disagreement: boolean;
  disagreementLabel?: string;
  synthesisSummary: string;
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const colors: Record<string, string> = {
    low: 'bg-green-100 text-green-800 border-green-200',
    moderate: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    red_flag: 'bg-red-100 text-red-800 border-red-200',
    cannot_determine_insufficient_object_data: 'bg-slate-100 text-slate-700 border-slate-300',
    high: 'bg-green-100 text-green-800 border-green-200',
  };

  const displayLabels: Record<string, string> = {
    low: 'low',
    moderate: 'moderate',
    red_flag: 'red flag',
    cannot_determine_insufficient_object_data: 'cannot determine',
    high: 'high',
  };

  const colorClass = colors[verdict] || 'bg-gray-100 text-gray-800 border-gray-200';
  const label = displayLabels[verdict] || verdict.replace('_', ' ');
  const isCannotDetermine = verdict === 'cannot_determine_insufficient_object_data';

  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <span className={`inline-block px-2.5 py-1 text-xs font-semibold rounded-full border ${colorClass}`}>
        {label}
      </span>
      {isCannotDetermine && (
        <span className="text-[10px] text-slate-500 max-w-[160px] text-right leading-tight">
          Needs object-specific research
        </span>
      )}
    </span>
  );
}

export default function DualAgentCard({
  title, leftLabel, leftContent, leftVerdict,
  rightLabel, rightContent, rightVerdict,
  disagreement, disagreementLabel, synthesisSummary,
}: DualAgentCardProps) {
  return (
    <div className={`rounded-xl border-2 p-6 ${
      disagreement ? 'border-amber-400 bg-amber-50/30' : 'border-gray-200 bg-white'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
        {disagreement && (
          <span className="px-3 py-1 text-xs font-bold bg-amber-200 text-amber-900 rounded-full">
            ⚠ {disagreementLabel || 'Sub-agents disagree'}
          </span>
        )}
      </div>

      {/* Two sub-agents side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Left sub-agent */}
        <div className="border border-gray-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-gray-700">{leftLabel}</h4>
            <VerdictBadge verdict={leftVerdict} />
          </div>
          <div className="text-sm text-gray-600 space-y-2">{leftContent}</div>
        </div>

        {/* Right sub-agent */}
        <div className="border border-gray-200 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-gray-700">{rightLabel}</h4>
            <VerdictBadge verdict={rightVerdict} />
          </div>
          <div className="text-sm text-gray-600 space-y-2">{rightContent}</div>
        </div>
      </div>

      {/* Synthesis */}
      <div className="mt-3 px-4 py-3 bg-gray-50 rounded-lg border border-gray-100">
        <p className="text-sm text-gray-700">
          <span className="font-semibold">Synthesis: </span>
          {synthesisSummary}
        </p>
      </div>
    </div>
  );
}
