import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import PipelineExplainer from '../pages/PipelineExplainer';
import ResultsWalkthrough, {
  getProvenancePrimaryCaption,
  getValuationCaption,
} from '../pages/ResultsWalkthrough';
import { AnalyzeResponse } from '../types/api';

// jsdom doesn't implement scrollIntoView — mock it globally for these tests
Element.prototype.scrollIntoView = vi.fn();

// jsdom doesn't implement HTMLMediaElement play/pause properly
// Mock play() to reject (simulates browser autoplay policy blocking)
Object.defineProperty(HTMLMediaElement.prototype, 'play', {
  configurable: true,
  value: vi.fn(() => Promise.reject(new DOMException('NotAllowedError'))),
});
Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
  configurable: true,
  value: vi.fn(),
});

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ---------------------------------------------------------------------------
// PipelineExplainer tests — one-page auto-play
// ---------------------------------------------------------------------------

describe('PipelineExplainer (one-page auto-play)', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function renderExplainer(mode: 'short' | 'long' = 'short') {
    return render(
      <MemoryRouter initialEntries={[`/demo/explainer?mode=${mode}`]}>
        <PipelineExplainer />
      </MemoryRouter>
    );
  }

  it('renders all eight segments on one page (long mode)', () => {
    renderExplainer('long');
    expect(screen.getByText('Introduction')).toBeInTheDocument();
    expect(screen.getByText('Built with Kiro')).toBeInTheDocument();
    expect(screen.getByText('Visual Art Historian')).toBeInTheDocument();
    expect(screen.getByText('Compliance Auditor')).toBeInTheDocument();
    expect(screen.getByText('Provenance Historian')).toBeInTheDocument();
    expect(screen.getByText('Conservative Appraiser')).toBeInTheDocument();
    expect(screen.getByText('Bullish Specialist')).toBeInTheDocument();
    expect(screen.getByText('Curator')).toBeInTheDocument();
  });

  it('renders only short-form segments by default', () => {
    renderExplainer();
    expect(screen.getByText('Introduction')).toBeInTheDocument();
    expect(screen.getByText('Built with Kiro')).toBeInTheDocument();
    expect(screen.getByText('Compliance Auditor')).toBeInTheDocument();
    expect(screen.getByText('Provenance Historian')).toBeInTheDocument();
    expect(screen.queryByText('Visual Art Historian')).not.toBeInTheDocument();
    expect(screen.queryByText('Conservative Appraiser')).not.toBeInTheDocument();
    expect(screen.queryByText('Curator')).not.toBeInTheDocument();
  });

  it('first segment is active on load (highlighted)', () => {
    renderExplainer();
    const firstSegment = screen.getByTestId('segment-intro');
    expect(firstSegment.className).toContain('border-indigo-400');
  });

  it('pending segments are dimmed', () => {
    renderExplainer();
    // In short mode, last segment is provenance_historian — it's pending on load
    const lastSegment = screen.getByTestId('segment-provenance_historian');
    expect(lastSegment.className).toContain('opacity-40');
  });

  it('advances to next segment after fallback timer when audio errors', async () => {
    renderExplainer();
    // play() returns a rejected promise (mocked above), triggering fallback timer
    // Need to flush promise microtasks then advance timer
    await act(async () => { await Promise.resolve(); });
    act(() => { vi.advanceTimersByTime(8200); });
    // Second segment in short mode is built_with_kiro
    const secondSegment = screen.getByTestId('segment-built_with_kiro');
    expect(secondSegment.className).toContain('border-indigo-400');
  });

  it('pause button stops auto-advancement', () => {
    renderExplainer();
    // Click pause
    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    fireEvent.click(pauseBtn);
    // Advance time well past fallback
    act(() => { vi.advanceTimersByTime(20000); });
    // Should still be on first segment (intro)
    const firstSegment = screen.getByTestId('segment-intro');
    expect(firstSegment.className).toContain('border-indigo-400');
  });

  it('play button resumes auto-advancement after pause', async () => {
    renderExplainer();
    // Pause
    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    // Resume
    fireEvent.click(screen.getByRole('button', { name: /resume|play/i }));
    // Flush microtasks (play promise rejection triggers fallback)
    await act(async () => { await Promise.resolve(); });
    // Advance past fallback
    act(() => { vi.advanceTimersByTime(8200); });
    // Should have advanced to built_with_kiro (second in short mode)
    const secondSegment = screen.getByTestId('segment-built_with_kiro');
    expect(secondSegment.className).toContain('border-indigo-400');
  });

  it('manual skip via persona dots changes active segment', () => {
    renderExplainer();
    // In short mode, segments are: Intro, Compliance Auditor, Provenance Historian
    // Click the last dot (Provenance Historian - initials "PH")
    const dots = screen.getAllByRole('button').filter(
      btn => btn.textContent === 'PH'
    );
    fireEvent.click(dots[dots.length - 1]);
    const lastSegment = screen.getByTestId('segment-provenance_historian');
    expect(lastSegment.className).toContain('border-indigo-400');
  });

  it('shows the runtime explanation note', () => {
    renderExplainer();
    expect(screen.getByText(/60–90\+ seconds/)).toBeInTheDocument();
  });

  it('shows real pipeline log entries', () => {
    renderExplainer();
    // Log entries section header should be present (segments with logs show it)
    expect(screen.getAllByText('Real pipeline log entries').length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// ResultsWalkthrough tests — auto-tour + full page
// ---------------------------------------------------------------------------

describe('ResultsWalkthrough (audio-driven tour + full page)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function renderWalkthrough() {
    return render(
      <MemoryRouter>
        <ResultsWalkthrough />
      </MemoryRouter>
    );
  }

  it('renders the Key Insight banner', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // "Key Insight" appears in step nav and banner heading
    expect(screen.getAllByText('Key Insight').length).toBeGreaterThanOrEqual(2);
  });

  it('renders the full ResultsView (all sections present in DOM)', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // Visual analysis (appears in step nav + section heading)
    expect(screen.getAllByText('Visual Analysis').length).toBeGreaterThanOrEqual(1);
    // Provenance card
    expect(screen.getAllByText('Provenance Assessment').length).toBeGreaterThanOrEqual(1);
    // Valuation card
    expect(screen.getAllByText('Financial Valuation').length).toBeGreaterThanOrEqual(1);
    // Curator
    expect(screen.getAllByText('Exhibition Copy').length).toBeGreaterThanOrEqual(1);
    // Evidence
    expect(screen.getAllByText('Evidence Trail').length).toBeGreaterThanOrEqual(1);
  });

  it('renders the static thumbnail image', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    const img = screen.getByAltText('Analyzed artwork');
    expect(img).toBeInTheDocument();
    expect(img.getAttribute('src')).toBe('/golden-result-image.jpg');
  });

  it('starts tour on banner section (first step highlighted)', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // The first tour step button should be active (bg-indigo-600)
    const stepButtons = screen.getAllByRole('button').filter(
      btn => btn.textContent === 'Key Insight'
    );
    expect(stepButtons[0].className).toContain('bg-indigo-600');
  });

  it('tour advances after fallback timer (when audio fails)', async () => {
    renderWalkthrough();
    // Flush the play() promise rejection
    await act(async () => { await Promise.resolve(); });
    // Advance past the first step's fallback duration (12000ms)
    act(() => { vi.advanceTimersByTime(12100); });
    // Second step button (Disclosures) should now be active
    const stepButtons = screen.getAllByRole('button').filter(
      btn => btn.textContent === 'Disclosures'
    );
    expect(stepButtons[0].className).toContain('bg-indigo-600');
  });

  it('pause button stops tour advancement', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // Click pause
    const pauseBtn = screen.getByRole('button', { name: /pause/i });
    fireEvent.click(pauseBtn);
    // Advance well past fallback
    act(() => { vi.advanceTimersByTime(30000); });
    // Should still be on banner (first step)
    const stepButtons = screen.getAllByRole('button').filter(
      btn => btn.textContent === 'Key Insight'
    );
    expect(stepButtons[0].className).toContain('bg-indigo-600');
  });

  it('all results sections are present in DOM at all times', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // Verify actual ResultsView content is rendered (not gated by tour)
    expect(screen.getAllByText('Visual Analysis').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Provenance Assessment').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Financial Valuation').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Evidence Trail').length).toBeGreaterThanOrEqual(1);
  });

  it('shows narration caption for current tour step', async () => {
    renderWalkthrough();
    await act(async () => { await Promise.resolve(); });
    // First step's caption should be visible
    expect(screen.getByText(/key finding/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Caption logic tests (unchanged)
// ---------------------------------------------------------------------------

describe('getProvenancePrimaryCaption', () => {
  function makeResult(overrides: Partial<AnalyzeResponse>): AnalyzeResponse {
    return {
      attribution: '',
      period_style: '',
      composition_analysis: '',
      condition_notes: '',
      stylistic_authenticity_notes: '',
      compliance_auditor: { identified_gaps: [], risk_level: 'low', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'low' },
      provenance_synthesis_summary: '',
      provenance_requires_human_review: false,
      provenance_evidence_scope: 'specific_object',
      conservative_appraiser: { floor_estimate_usd: 10000, methodology: '', primary_comp: '', confidence: 'moderate' },
      bullish_specialist: { ceiling_estimate_usd: 30000, methodology: '', primary_comp: '', confidence: 'moderate' },
      valuation_corridor: { low_estimate_usd: 10000, high_estimate_usd: 30000 },
      corridor_summary: '',
      valuation_requires_human_review: false,
      valuation_evidence_scope: 'specific_object',
      curator_auction_house: { exhibition_narrative: '', wall_label: '', suggested_title: '', disclosures: [] },
      curator_public_gallery: { exhibition_narrative: '', wall_label: '', suggested_title: '', disclosures: [] },
      provenance_evidence_sample: [],
      valuation_evidence_sample: [],
      total_provenance_facts: 0,
      total_valuation_comps: 0,
      timings: { visual_analysis_ms: 0, stage_2_wall_clock_ms: 0, provenance_ms: 0, valuation_ms: 0, curator_ms: 0, total_ms: 0 },
      ...overrides,
    } as AnalyzeResponse;
  }

  it('returns disagreement caption when risk_levels differ (not cannot_determine)', () => {
    const result = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'red_flag', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'moderate' },
    });
    const caption = getProvenancePrimaryCaption(result);
    expect(caption).toContain('disagreement');
    expect(caption).toContain('red_flag');
    expect(caption).toContain('moderate');
  });

  it('returns cannot_determine + artist_general caption when both apply', () => {
    const result = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'cannot_determine_insufficient_object_data', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'cannot_determine_insufficient_object_data' },
      provenance_evidence_scope: 'artist_general',
    });
    const caption = getProvenancePrimaryCaption(result);
    expect(caption).toContain('evidence');
    expect(caption).toContain('artist');
    expect(caption).toContain('AAM/AAMD');
    expect(caption).not.toContain('disagreement');
  });

  it('returns simpler cannot_determine caption when evidence_scope is specific_object', () => {
    const result = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'cannot_determine_insufficient_object_data', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'cannot_determine_insufficient_object_data' },
      provenance_evidence_scope: 'specific_object',
    });
    const caption = getProvenancePrimaryCaption(result);
    expect(caption).toContain('cannot determine');
    expect(caption).toContain('AAM/AAMD');
    expect(caption).not.toContain('disagreement');
  });

  it('returns agreement caption when both sub-agents agree on a completed assessment', () => {
    const result = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'low', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'low' },
    });
    const caption = getProvenancePrimaryCaption(result);
    expect(caption).toContain('agree');
    expect(caption).toContain('low');
    expect(caption).not.toContain('disagreement');
    expect(caption).not.toContain('cannot determine');
  });

  it('produces different captions for disagreement vs cannot_determine', () => {
    const disagreeResult = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'red_flag', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'low' },
    });
    const cannotResult = makeResult({
      compliance_auditor: { identified_gaps: [], risk_level: 'cannot_determine_insufficient_object_data', reasoning: '' },
      provenance_historian: { contextual_notes: '', cited_evidence: [], risk_level: 'cannot_determine_insufficient_object_data' },
      provenance_evidence_scope: 'artist_general',
    });
    const disagreeCaption = getProvenancePrimaryCaption(disagreeResult);
    const cannotCaption = getProvenancePrimaryCaption(cannotResult);
    expect(disagreeCaption).not.toEqual(cannotCaption);
    expect(disagreeCaption).toContain('disagreement');
    expect(cannotCaption).not.toContain('disagreement');
  });
});

describe('getValuationCaption', () => {
  it('returns a caption when spread > 3x', () => {
    const result = { valuation_corridor: { low_estimate_usd: 10000, high_estimate_usd: 50000 } } as unknown as AnalyzeResponse;
    expect(getValuationCaption(result)).toContain('spread');
  });

  it('returns null when spread <= 3x', () => {
    const result = { valuation_corridor: { low_estimate_usd: 10000, high_estimate_usd: 25000 } } as unknown as AnalyzeResponse;
    expect(getValuationCaption(result)).toBeNull();
  });
});
