/**
 * Hook and UI for selecting demo mode (short-form vs long-form).
 * State is stored in URL search params so it persists across route navigation.
 */

import { useSearchParams } from 'react-router-dom';
import { DemoMode } from '../api/client';

export function useDemoMode(): [DemoMode, (mode: DemoMode) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = (searchParams.get('mode') === 'long' ? 'long' : 'short') as DemoMode;

  const setMode = (newMode: DemoMode) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('mode', newMode);
      return next;
    }, { replace: true });
  };

  return [mode, setMode];
}

export function DemoModeToggle({ mode, onChange }: { mode: DemoMode; onChange: (m: DemoMode) => void }) {
  return (
    <select
      value={mode}
      onChange={(e) => onChange(e.target.value as DemoMode)}
      className="text-xs bg-gray-100 border border-gray-300 rounded px-2 py-1 text-gray-700"
      aria-label="Demo length"
    >
      <option value="short">Short (3 min)</option>
      <option value="long">Full (~5 min)</option>
    </select>
  );
}
