import { useState, useEffect } from 'react';
import { ProgressEntry } from '../api/client';

interface LoadingViewProps {
  imageUrl: string | null;
  logs: ProgressEntry[];
}

const STAGE_LABELS: Record<string, string> = {
  start: 'Initializing',
  visual_analysis: 'Visual Art Historian',
  concurrent_research: 'Provenance & Valuation Research',
  curator: 'Writing Exhibition Copy',
};

const STAGE_ORDER = ['start', 'visual_analysis', 'concurrent_research', 'curator'];

export default function LoadingView({ imageUrl, logs }: LoadingViewProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  // Group entries by stage_key
  const grouped: Record<string, string[]> = {};
  for (const entry of logs) {
    if (!grouped[entry.stage_key]) grouped[entry.stage_key] = [];
    grouped[entry.stage_key].push(entry.message);
  }

  // Determine active stage (the stage of the last log entry)
  const lastStageKey = logs.length > 0 ? logs[logs.length - 1].stage_key : null;

  return (
    <div className="max-w-lg mx-auto text-center space-y-8 py-12">
      {imageUrl && (
        <img src={imageUrl} alt="Uploaded artwork" className="max-h-32 mx-auto rounded-lg shadow-sm object-contain opacity-70" />
      )}

      <div className="inline-block w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />

      {/* Grouped stage list */}
      <div className="space-y-3 text-left max-w-sm mx-auto">
        {STAGE_ORDER.map((stageKey) => {
          const entries = grouped[stageKey] || [];
          const hasEntries = entries.length > 0;
          const isActive = stageKey === lastStageKey;
          const activeIdx = STAGE_ORDER.indexOf(lastStageKey || '');
          const stageIdx = STAGE_ORDER.indexOf(stageKey);
          const isComplete = hasEntries && stageIdx < activeIdx;
          const isPending = !hasEntries && stageIdx > activeIdx;

          return (
            <div key={stageKey}>
              {/* Parent stage */}
              <div className="flex items-center gap-3">
                <span className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-bold border-2 ${
                  isComplete ? 'bg-green-100 border-green-500 text-green-700' :
                  isActive ? 'bg-indigo-100 border-indigo-500 text-indigo-700 animate-pulse' :
                  'bg-gray-100 border-gray-300 text-gray-400'
                }`}>
                  {isComplete ? '✓' : stageIdx + 1}
                </span>
                <span className={`text-sm font-medium ${
                  isComplete ? 'text-green-700' :
                  isActive ? 'text-indigo-700' :
                  'text-gray-400'
                }`}>
                  {STAGE_LABELS[stageKey] || stageKey}
                </span>
              </div>

              {/* Substeps (indented) */}
              {hasEntries && (
                <div className="ml-9 mt-1 space-y-0.5">
                  {entries.map((msg, i) => (
                    <p key={i} className={`text-xs ${
                      isComplete || i < entries.length - 1 ? 'text-gray-500' : 'text-indigo-600'
                    }`}>
                      {isComplete || i < entries.length - 1 ? '✓ ' : '› '}{msg}
                    </p>
                  ))}
                </div>
              )}

              {/* Connector */}
              {stageIdx < STAGE_ORDER.length - 1 && !isPending && (
                <div className="ml-3 h-3 border-l-2 border-gray-200" />
              )}
            </div>
          );
        })}
      </div>

      <div className="text-gray-500 text-sm space-y-1">
        <p className="font-mono">{elapsed}s elapsed</p>
        <p>This analysis typically takes 60–90 seconds.</p>
      </div>
    </div>
  );
}
