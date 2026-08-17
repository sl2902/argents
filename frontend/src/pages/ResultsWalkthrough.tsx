/**
 * ResultsWalkthrough — renders the FULL ResultsView with an audio-driven
 * tour layered on top. All sections are always present in the DOM.
 * Audio narration plays per section; on audio end (or fallback timer if
 * audio is missing), advances to the next section with auto-scroll and
 * highlighting.
 *
 * Matches the PipelineExplainer pattern but for results sections.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { AnalyzeResponse } from '../types/api';
import { NARRATION_PLAYBACK_RATE } from '../api/client';
import ResultsView from '../components/ResultsView';
import GlossaryText from '../components/GlossaryText';
import goldenResult from '../data/golden-result.json';

// ---------------------------------------------------------------------------
// Caption logic — generic, not hardcoded to one specific golden result
// ---------------------------------------------------------------------------

const CANNOT_DETERMINE = 'cannot_determine_insufficient_object_data';

/**
 * Determines the primary caption for the provenance section based on
 * the actual data, not assumptions.
 */
export function getProvenancePrimaryCaption(result: AnalyzeResponse): string {
  const auditorLevel = result.compliance_auditor.risk_level;
  const historianLevel = result.provenance_historian.risk_level;
  const hasDisagreement = auditorLevel !== historianLevel;
  const eitherCannotDetermine =
    auditorLevel === CANNOT_DETERMINE || historianLevel === CANNOT_DETERMINE;
  const isArtistGeneral = result.provenance_evidence_scope === 'artist_general';

  if (hasDisagreement && !eitherCannotDetermine) {
    return `Watch the disagreement: the Compliance Auditor assessed "${auditorLevel}" while the Provenance Historian assessed "${historianLevel}" — looking at the same evidence, reaching different conclusions. This visible debate is the point of the dual-agent architecture.`;
  }

  if (eitherCannotDetermine && isArtistGeneral) {
    return `Watch what happens when the evidence genuinely isn't enough: the retrieved evidence — including real Führermuseum and Munich Central Collecting Point history — is documented for a different specific work by this artist, not the piece being assessed. Because this evidence can't be tied to this object (evidence scope: artist-general), both agents correctly cannot apply the standard object-specific risk test used in real museum practice (per AAM/AAMD guidelines). Instead of guessing, they say so directly — and explain why. That's the honest answer, not a gap in the system.`;
  }

  if (eitherCannotDetermine) {
    return `Both agents report they cannot determine risk — insufficient object-specific data is available to apply the standard provenance test. This is the honest answer when the standard museum due-diligence test (per AAM/AAMD guidelines) cannot be applied.`;
  }

  return `Both sub-agents agree on risk level: ${auditorLevel}. The synthesis summary captures their shared conclusion.`;
}

/**
 * Determines if the valuation section warrants a special callout.
 */
export function getValuationCaption(result: AnalyzeResponse): string | null {
  const spread =
    result.valuation_corridor.high_estimate_usd /
    result.valuation_corridor.low_estimate_usd;
  if (spread > 3) {
    return `Notice the wide valuation spread (${spread.toFixed(1)}x): the Conservative Appraiser and Bullish Specialist see very different scenarios for this work. That visible range is more honest than a single fabricated number.`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Tour configuration — audio-driven
// ---------------------------------------------------------------------------

interface TourStep {
  key: string;
  label: string;
  audioFile: string;
  caption: string;
  fallbackDurationMs: number;
}

const TOUR_STEPS: TourStep[] = [
  {
    key: 'banner',
    label: 'Key Insight',
    audioFile: '/audio/results_banner.wav',
    caption:
      "Here's the key finding. The system retrieved real, documented history — including Führermuseum and Munich Central Collecting Point records — but that evidence is tied to a different specific work by this artist, not the piece being assessed. Because it can't be connected to this object, both agents correctly say the standard provenance test cannot be applied. That's the honest answer.",
    fallbackDurationMs: 12000,
  },
  {
    key: 'disclosures',
    label: 'Disclosures',
    audioFile: '/audio/results_disclosures.wav',
    caption:
      "The disclosure floor is structural. Because the provenance stage flagged 'requires human review,' that fact appears in the final exhibition copy automatically — the Curator cannot drop it. This is enforced by code, not by asking the model nicely.",
    fallbackDurationMs: 10000,
  },
  {
    key: 'visual',
    label: 'Visual Analysis',
    audioFile: '/audio/results_visual.wav',
    caption:
      "The Visual Art Historian identified this as an early fifteenth-century International Gothic painting. The attribution to Gentile da Fabriano is based on strong stylistic similarity — but no signature is visible, so it remains 'attributed to,' not confirmed. That hedge language is preserved throughout.",
    fallbackDurationMs: 10000,
  },
  {
    key: 'provenance',
    label: 'Provenance',
    audioFile: '/audio/results_provenance.wav',
    caption:
      "Both the Compliance Auditor and the Provenance Historian reached the same conclusion independently: cannot determine. The evidence scope is artist-general — retrieval found facts about the artist's body of work, not this specific piece. Without object-specific data, the standard museum due-diligence test cannot be applied. Neither agent guessed.",
    fallbackDurationMs: 12000,
  },
  {
    key: 'valuation',
    label: 'Valuation',
    audioFile: '/audio/results_valuation.wav',
    caption:
      "The valuation corridor runs from $50,000 to $125,000. Both appraisers anchor on the same Sotheby's comparable — two authenticated panels estimated at $250,000–$350,000 — but discount heavily for the unconfirmed attribution. Confidence is low on both sides, which is itself an honest signal.",
    fallbackDurationMs: 10000,
  },
  {
    key: 'evidence',
    label: 'Evidence Trail',
    audioFile: '/audio/results_evidence.wav',
    caption:
      "Every factual claim carries a real, clickable source URL. The provenance sources come from Wikidata — real ownership records for documented works by this artist. Nothing is asserted without a citation.",
    fallbackDurationMs: 8000,
  },
  {
    key: 'curator',
    label: 'Exhibition Copy',
    audioFile: '/audio/results_curator.wav',
    caption:
      "The Curator wrote exhibition copy in two variants: auction house and public gallery. Both correctly state that object-specific provenance research is still needed — that language wasn't optional. The disclosure floor guarantees it appears regardless of how the narrative reads.",
    fallbackDurationMs: 10000,
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const GOLDEN_IMAGE_URL = '/golden-result-image.jpg';

export default function ResultsWalkthrough() {
  const result = goldenResult as unknown as AnalyzeResponse;
  const provenanceCaption = getProvenancePrimaryCaption(result);
  const valuationCaption = getValuationCaption(result);

  // Scroll to top on mount (browser may restore scroll from previous page)
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  // Audio-driven tour state
  const [tourIndex, setTourIndex] = useState(0);
  const [tourPlaying, setTourPlaying] = useState(true);
  const [audioErrors, setAudioErrors] = useState<Set<number>>(new Set());
  const audioRefs = useRef<(HTMLAudioElement | null)[]>([]);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFallback = useCallback(() => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, []);

  // Advance to next tour step
  const advanceToNext = useCallback(() => {
    clearFallback();
    setTourIndex((prev) => (prev < TOUR_STEPS.length - 1 ? prev + 1 : prev));
  }, [clearFallback]);

  // Play audio for a given step index
  const playAudio = useCallback(
    (index: number) => {
      // Pause all other audio
      audioRefs.current.forEach((el, i) => {
        if (el && i !== index) {
          el.pause();
          el.currentTime = 0;
        }
      });

      const audio = audioRefs.current[index];
      if (!audio || audioErrors.has(index)) {
        // No audio — use fallback timer
        clearFallback();
        fallbackTimerRef.current = setTimeout(
          advanceToNext,
          TOUR_STEPS[index].fallbackDurationMs
        );
        return;
      }

      audio.currentTime = 0;
      audio.playbackRate = NARRATION_PLAYBACK_RATE;
      const playPromise = audio.play();
      if (playPromise) {
        playPromise.catch(() => {
          setAudioErrors((prev) => new Set(prev).add(index));
          clearFallback();
          fallbackTimerRef.current = setTimeout(
            advanceToNext,
            TOUR_STEPS[index].fallbackDurationMs
          );
        });
      }
    },
    [audioErrors, advanceToNext, clearFallback]
  );

  // When tour index changes: scroll to the ACTUAL rendered section (except banner) and play audio
  useEffect(() => {
    const step = TOUR_STEPS[tourIndex];
    if (tourIndex > 1) {
      // Query the DOM for the actual section heading inside ResultsView
      const headingMap: Record<string, string> = {
        visual: 'Visual Analysis',
        provenance: 'Provenance Assessment',
        valuation: 'Financial Valuation',
        curator: 'Exhibition Copy',
        evidence: 'Evidence Trail',
        disclosures: 'Disclosures',
      };
      const headingText = headingMap[step.key];
      if (headingText) {
        const headings = document.querySelectorAll('h3');
        for (const h of headings) {
          if (h.textContent?.includes(headingText)) {
            h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            break;
          }
        }
      }
    }
    if (tourPlaying) {
      playAudio(tourIndex);
    }
  }, [tourIndex, tourPlaying, playAudio]);

  // Handle audio ended — advance if still playing
  const handleAudioEnded = useCallback(
    (index: number) => {
      if (index === tourIndex && tourPlaying) {
        advanceToNext();
      }
    },
    [tourIndex, tourPlaying, advanceToNext]
  );

  // Pause/play toggle
  const toggleTour = () => {
    if (tourPlaying) {
      clearFallback();
      const audio = audioRefs.current[tourIndex];
      if (audio) audio.pause();
      setTourPlaying(false);
    } else {
      setTourPlaying(true);
      playAudio(tourIndex);
    }
  };

  // Manual skip
  const skipTo = (index: number) => {
    clearFallback();
    const currentAudio = audioRefs.current[tourIndex];
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    setTourIndex(index);
  };

  const currentStep = TOUR_STEPS[tourIndex];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sticky header with tour controls */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-20">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold text-gray-900">
              Artgents <span className="text-sm font-normal text-gray-500">— Demo Results</span>
            </h1>
            <div className="flex items-center gap-3">
              <button
                onClick={toggleTour}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  tourPlaying
                    ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                }`}
                aria-label={tourPlaying ? 'Pause tour' : 'Resume tour'}
              >
                {tourPlaying ? '⏸ Pause' : '▶ Play'}
              </button>
              <Link to="/demo/explainer" className="text-xs text-gray-500 hover:text-gray-700">
                ← Explainer
              </Link>
              <Link to="/app" className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                Try Live →
              </Link>
            </div>
          </div>

          {/* Tour progress dots */}
          <div className="mt-2 flex items-center justify-center gap-1">
            {TOUR_STEPS.map((step, i) => (
              <button
                key={step.key}
                onClick={() => skipTo(i)}
                className={`px-2 py-0.5 text-[10px] rounded transition-all ${
                  i === tourIndex
                    ? 'bg-indigo-600 text-white font-semibold'
                    : i < tourIndex
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
                title={step.label}
              >
                {step.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Hidden audio elements for each tour step */}
      {TOUR_STEPS.map((step, i) => (
        <audio
          key={step.key}
          ref={(el) => { audioRefs.current[i] = el; }}
          src={step.audioFile}
          preload="auto"
          onEnded={() => handleAudioEnded(i)}
          onError={() => setAudioErrors((prev) => new Set(prev).add(i))}
        />
      ))}

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Current section caption */}
        <div
          ref={(el) => { sectionRefs.current['banner'] = el; }}
          data-testid="tour-section-banner"
          className={`transition-all duration-500 ${
            currentStep.key === 'banner' ? 'ring-2 ring-indigo-400 ring-offset-2 rounded-xl' : ''
          }`}
        >
          <div className="bg-indigo-50 border-2 border-indigo-300 rounded-xl p-5">
            <h2 className="text-sm font-bold text-indigo-900 uppercase tracking-wide mb-2">
              Key Insight
            </h2>
            <p className="text-sm text-indigo-800 leading-relaxed">
              <GlossaryText text={provenanceCaption} />
            </p>
            {valuationCaption && (
              <p className="text-sm text-indigo-700 leading-relaxed mt-3 pt-3 border-t border-indigo-200">
                <GlossaryText text={valuationCaption} />
              </p>
            )}
          </div>
        </div>

        {/* Narration caption for current step (below banner, above results) */}
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm">
          <p className="text-sm text-gray-700 italic leading-relaxed">
            "<GlossaryText text={currentStep.caption} />"
          </p>
        </div>

        {/* Full ResultsView — always fully rendered */}
        <ResultsView
          result={result}
          onReset={() => {}}
          imageUrl={GOLDEN_IMAGE_URL}
        />
      </main>
    </div>
  );
}
