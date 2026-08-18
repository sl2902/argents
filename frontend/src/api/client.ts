import { AnalyzeResponse } from '../types/api';

// ---------------------------------------------------------------------------
// Demo mode configuration (centralized)
// ---------------------------------------------------------------------------

/**
 * Playback speed for demo narration audio.
 * 1.0 = normal, 0.8 = slower, 1.2 = 20% faster, etc.
 * Applies to both PipelineExplainer and ResultsWalkthrough audio.
 */
export const NARRATION_PLAYBACK_RATE = 1.5;

export type DemoMode = 'short' | 'long';

/**
 * Short-form: only plays intro + compliance auditor + provenance historian
 * in the explainer (skips visual art historian, appraisers, curator, built-with-kiro).
 * Results walkthrough uses shorter durations.
 *
 * Long-form: plays all 8 segments in the explainer, full durations in results.
 */
export const SHORT_FORM_EXPLAINER_SEGMENTS: string[] = [
  'intro',
  'built_with_kiro',
  'compliance_auditor',
  'provenance_historian',
];

export const SHORT_FORM_RESULTS_DURATION_MULTIPLIER = 0.6;

// ---------------------------------------------------------------------------

export class AnalyzeError extends Error {
  status: number;
  stage: string;
  constructor(message: string, status: number, stage: string) {
    super(message);
    this.status = status;
    this.stage = stage;
  }
}

/**
 * Base URL for API calls. In dev, Vite proxies /api to localhost:8000.
 * In production, set VITE_API_URL to the Cloud Run backend URL
 * (e.g. "https://artgents-backend-xxxxx.run.app").
 */
const API_BASE = import.meta.env.VITE_API_URL || '';

interface JobStatusResponse {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  logs: ProgressEntry[];
  result?: AnalyzeResponse;
  error?: string;
  failed_stage?: string;
}

export interface ProgressEntry {
  stage_key: string;
  message: string;
}

/**
 * Submit an analysis job and poll until completion.
 * Calls onProgress with the full logs array from the server on each poll.
 */
export async function analyzeArtwork(
  params: {
    files: File[];
    knownTitle?: string;
    knownArtist?: string;
    knownPeriod?: string;
    medium?: string;
  },
  onProgress?: (logs: ProgressEntry[]) => void,
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  params.files.forEach(f => formData.append('files', f));
  if (params.knownTitle) formData.append('known_title', params.knownTitle);
  if (params.knownArtist) formData.append('known_artist', params.knownArtist);
  if (params.knownPeriod) formData.append('known_period', params.knownPeriod);
  if (params.medium) formData.append('medium', params.medium);

  // 1. Submit job
  const submitResponse = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body: formData });
  if (!submitResponse.ok) {
    const err = await submitResponse.json();
    // FastAPI Pydantic validation errors return {"detail": [...]} not {"error": "..."}
    if (submitResponse.status === 422 && err.detail && Array.isArray(err.detail)) {
      throw new AnalyzeError(
        'One of the fields you entered was too long or invalid. Please check your input and try again.',
        422,
        'validation',
      );
    }
    throw new AnalyzeError(err.error || 'Upload failed', submitResponse.status, err.stage || 'upload');
  }
  const { job_id } = await submitResponse.json();

  // 2. Poll until complete
  while (true) {
    await sleep(2000); // poll every 2 seconds

    const statusResponse = await fetch(`${API_BASE}/api/status/${job_id}`);
    if (!statusResponse.ok) {
      throw new AnalyzeError('Failed to check job status', statusResponse.status, 'polling');
    }

    const status: JobStatusResponse = await statusResponse.json();

    if (onProgress) {
      onProgress(status.logs);
    }

    if (status.status === 'completed' && status.result) {
      return status.result;
    }

    if (status.status === 'failed') {
      throw new AnalyzeError(
        status.error || 'Analysis failed',
        status.failed_stage === 'visual_art_historian' ? 422 : 500,
        status.failed_stage || 'unknown',
      );
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
