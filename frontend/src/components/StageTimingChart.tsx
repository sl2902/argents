import { StageTimings } from '../types/api';

interface StageTimingChartProps {
  timings: StageTimings;
}

export default function StageTimingChart({ timings }: StageTimingChartProps) {
  const maxMs = timings.total_ms || 1;

  const stages = [
    { label: 'Visual Art Historian', ms: timings.visual_analysis_ms, color: 'bg-blue-500', start: 0 },
    { label: 'Provenance/Legal', ms: timings.provenance_ms, color: 'bg-purple-500', start: timings.visual_analysis_ms },
    { label: 'Financial Valuation', ms: timings.valuation_ms, color: 'bg-emerald-500', start: timings.visual_analysis_ms },
    { label: 'Curator (both variants)', ms: timings.curator_ms, color: 'bg-orange-500', start: timings.visual_analysis_ms + timings.stage_2_wall_clock_ms },
  ];

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-700">
        Pipeline Timing
        <span className="ml-2 text-xs font-normal text-gray-400">
          {(timings.total_ms / 1000).toFixed(1)}s total
        </span>
      </h4>

      <div className="space-y-1.5">
        {stages.map((stage, i) => {
          const leftPct = (stage.start / maxMs) * 100;
          const widthPct = Math.max((stage.ms / maxMs) * 100, 2);
          return (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-36 shrink-0 text-right">{stage.label}</span>
              <div className="flex-1 h-5 bg-gray-100 rounded relative">
                <div
                  className={`absolute top-0 h-full rounded ${stage.color} opacity-80`}
                  style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 w-12 shrink-0">
                {(stage.ms / 1000).toFixed(1)}s
              </span>
            </div>
          );
        })}
      </div>

      {/* Concurrency note */}
      <p className="text-xs text-gray-400 italic">
        Stage 2 ran concurrently — wall-clock: {(timings.stage_2_wall_clock_ms / 1000).toFixed(1)}s
        (Provenance: {(timings.provenance_ms / 1000).toFixed(1)}s + Valuation: {(timings.valuation_ms / 1000).toFixed(1)}s ran in parallel)
      </p>
    </div>
  );
}
