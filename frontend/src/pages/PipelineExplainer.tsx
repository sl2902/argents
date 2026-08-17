/**
 * PipelineExplainer — ONE continuous scrollable page showing all six persona
 * segments. On load, narration auto-plays through the sequence: each persona's
 * audio plays, and when it ends (or after a fallback duration), auto-advances
 * to the next — auto-scrolling and highlighting the active segment.
 *
 * A pause/play toggle stops/resumes the whole auto-play sequence.
 * Clickable persona dots allow manual skip-to-persona.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ProgressEntry, NARRATION_PLAYBACK_RATE } from '../api/client';
import goldenLogs from '../data/golden-result-logs.json';

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

interface PersonaSegment {
  key: string;
  name: string;
  audioFile: string;
  caption: string;
  logFilter: (entry: ProgressEntry) => boolean;
}

const SEGMENTS: PersonaSegment[] = [
  {
    key: 'intro',
    name: 'Introduction',
    audioFile: '/audio/intro.wav',
    caption:
      "A gallery or auction house can spend hundreds of hours on a single piece — tracing ownership, checking for red flags, defending a price — before they'll commit to a claim. Artgents does that research in 60 to 90 seconds — real calls to Vertex AI, Wikidata, the Met and Art Institute of Chicago APIs, and Parallel Search. Because that's too long to watch live, I'm walking through the architecture first, then showing a completed run. It uses two independently-reasoning agents at each contested step — not one averaged verdict.",
    logFilter: () => false, // No pipeline log entries for intro
  },
  {
    key: 'visual_art_historian',
    name: 'Visual Art Historian',
    audioFile: '/audio/visual_art_historian.wav',
    caption:
      "I'm the first to look at the piece. I study the brushwork, the materials, the composition — and I try to place it in art history. If there's no visible signature, I won't pretend to certainty I don't have. I'll tell you what style and period the evidence supports, and I'll separate that from any guess at who painted it.",
    logFilter: (e) => e.stage_key === 'visual_analysis',
  },
  {
    key: 'compliance_auditor',
    name: 'Compliance Auditor',
    audioFile: '/audio/compliance_auditor.wav',
    caption:
      "I'm the skeptic. I treat every gap in this artwork's ownership history as a risk — especially if it falls during the Second World War, or before international export rules existed in 1970. I don't assume good faith. My job is to ask: what if something's wrong here?",
    logFilter: (e) =>
      e.stage_key === 'concurrent_research' &&
      (e.message.toLowerCase().includes('provenance') ||
        (e.message.toLowerCase().includes('retriev') &&
          e.message.toLowerCase().includes('provenance'))),
  },
  {
    key: 'provenance_historian',
    name: 'Provenance Historian',
    audioFile: '/audio/provenance_historian.wav',
    caption:
      "I look at the same evidence my colleague does, but I ask a different question: is this gap actually unusual? Most art from before the twentieth century has incomplete records — that's normal, not suspicious. I put the gap in context. We don't always agree, and that disagreement is the point.",
    logFilter: (e) =>
      e.stage_key === 'concurrent_research' &&
      (e.message.toLowerCase().includes('provenance') ||
        e.message.toLowerCase().includes('fact')),
  },
  {
    key: 'conservative_appraiser',
    name: 'Conservative Appraiser',
    audioFile: '/audio/conservative_appraiser.wav',
    caption:
      "I set the floor. I look at real comparable sales, and I ask: what's the worst reasonable case? An attribution that isn't certain, a market that's soft, a forced sale — I build all of that into a defensible minimum.",
    logFilter: (e) =>
      e.stage_key === 'concurrent_research' &&
      (e.message.toLowerCase().includes('valuation') ||
        e.message.toLowerCase().includes('comparable') ||
        e.message.toLowerCase().includes('sales')),
  },
  {
    key: 'bullish_specialist',
    name: 'Bullish Specialist',
    audioFile: '/audio/bullish_specialist.wav',
    caption:
      "I set the ceiling. Same evidence as my colleague, different question: what's this worth to the right buyer, under the right conditions? Scarcity, momentum, a museum with real interest — I price the upside they're not accounting for.",
    logFilter: (e) =>
      e.stage_key === 'concurrent_research' &&
      (e.message.toLowerCase().includes('valuation') ||
        e.message.toLowerCase().includes('estimate')),
  },
  {
    key: 'curator',
    name: 'Curator',
    audioFile: '/audio/curator.wav',
    caption:
      "Once everyone else has spoken, I bring it together. I write the exhibition copy — but I don't get to soften what the others found. If there's a real disagreement or a real risk flagged upstream, it shows up in what I write, every time, whether that makes a cleaner story or not.",
    logFilter: (e) => e.stage_key === 'curator',
  },
];

/** Fallback duration (ms) if audio can't play or is missing */
const FALLBACK_DURATION_MS = 8000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PipelineExplainer() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true); // auto-play on by default
  const [audioErrors, setAudioErrors] = useState<Set<number>>(new Set());
  const audioRefs = useRef<(HTMLAudioElement | null)[]>([]);
  const sectionRefs = useRef<(HTMLDivElement | null)[]>([]);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navigate = useNavigate();

  // Clear fallback timer
  const clearFallback = useCallback(() => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  }, []);

  // Advance to next persona (or navigate to results if done)
  const advanceToNext = useCallback(() => {
    clearFallback();
    setActiveIndex((prev) => {
      if (prev < SEGMENTS.length - 1) {
        return prev + 1;
      }
      // Last segment — don't change index, trigger navigation separately
      return prev;
    });
  }, [clearFallback]);

  // Track if last segment finished playing (audio ended or fallback fired)
  const [lastSegmentDone, setLastSegmentDone] = useState(false);

  useEffect(() => {
    if (lastSegmentDone) {
      navigate('/demo/results');
    }
  }, [lastSegmentDone, navigate]);

  // Play audio for a given index
  const playAudio = useCallback(
    (index: number) => {
      // Pause all other audio first
      audioRefs.current.forEach((el, i) => {
        if (el && i !== index) {
          el.pause();
          el.currentTime = 0;
        }
      });

      const audio = audioRefs.current[index];
      if (!audio || audioErrors.has(index)) {
        // No audio available — use fallback timer
        clearFallback();
        const onFallback = index === SEGMENTS.length - 1
          ? () => setLastSegmentDone(true)
          : advanceToNext;
        fallbackTimerRef.current = setTimeout(onFallback, FALLBACK_DURATION_MS);
        return;
      }

      audio.currentTime = 0;
      audio.playbackRate = NARRATION_PLAYBACK_RATE;
      const playPromise = audio.play();
      if (playPromise) {
        playPromise.catch(() => {
          // Autoplay blocked or failed — use fallback timer
          setAudioErrors((prev) => new Set(prev).add(index));
          clearFallback();
          const onFallback = index === SEGMENTS.length - 1
            ? () => setLastSegmentDone(true)
            : advanceToNext;
          fallbackTimerRef.current = setTimeout(onFallback, FALLBACK_DURATION_MS);
        });
      }
    },
    [audioErrors, advanceToNext, clearFallback]
  );

  // When active index changes: scroll into view and start audio if playing
  useEffect(() => {
    const el = sectionRefs.current[activeIndex];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (isPlaying) {
      playAudio(activeIndex);
    }
  }, [activeIndex, isPlaying, playAudio]);

  // Handle audio ending — advance or navigate if last
  const handleAudioEnded = useCallback(
    (index: number) => {
      if (index === activeIndex && isPlaying) {
        if (activeIndex === SEGMENTS.length - 1) {
          setLastSegmentDone(true);
        } else {
          advanceToNext();
        }
      }
    },
    [activeIndex, isPlaying, advanceToNext]
  );

  // Pause/Play toggle
  const togglePlayPause = () => {
    if (isPlaying) {
      // Pause: stop audio and clear timers
      clearFallback();
      const audio = audioRefs.current[activeIndex];
      if (audio) audio.pause();
      setIsPlaying(false);
    } else {
      // Resume: start playing current segment
      setIsPlaying(true);
      playAudio(activeIndex);
    }
  };

  // Manual skip to a persona
  const skipTo = (index: number) => {
    clearFallback();
    const currentAudio = audioRefs.current[activeIndex];
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    setActiveIndex(index);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sticky header with controls */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-20">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-gray-900">
              Artgents <span className="text-sm font-normal text-gray-500">— Pipeline Walkthrough</span>
            </h1>
            <div className="flex items-center gap-3">
              <button
                onClick={togglePlayPause}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  isPlaying
                    ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                }`}
                aria-label={isPlaying ? 'Pause auto-play' : 'Resume auto-play'}
              >
                {isPlaying ? '⏸ Pause' : '▶ Play'}
              </button>
              <Link to="/demo/results" className="text-xs text-gray-500 hover:text-gray-700">
                Skip to Results →
              </Link>
            </div>
          </div>

          {/* Persona navigation dots */}
          <div className="flex items-center justify-center gap-1">
            {SEGMENTS.map((seg, i) => (
              <button
                key={seg.key}
                onClick={() => skipTo(i)}
                className={`px-2 py-1 text-[10px] rounded transition-all ${
                  i === activeIndex
                    ? 'bg-indigo-600 text-white font-semibold'
                    : i < activeIndex
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
                title={seg.name}
              >
                {seg.name.split(' ').map(w => w[0]).join('')}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-8">
        {/* Runtime note */}
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3 text-sm text-indigo-800">
          <strong>Why pre-recorded?</strong> A full live analysis typically takes 60–90+ seconds
          (real model calls, real data retrieval). This walkthrough uses a captured result so you
          can see the process without waiting.
        </div>

        {/* All six segments rendered on one page */}
        {SEGMENTS.map((segment, index) => {
          const isActive = index === activeIndex;
          const isComplete = index < activeIndex;
          const logs = (goldenLogs as ProgressEntry[]).filter(segment.logFilter);

          return (
            <div
              key={segment.key}
              ref={(el) => { sectionRefs.current[index] = el; }}
              data-testid={`segment-${segment.key}`}
              className={`rounded-xl border-2 p-6 transition-all duration-500 ${
                isActive
                  ? 'border-indigo-400 bg-white shadow-lg ring-2 ring-indigo-200'
                  : isComplete
                  ? 'border-green-200 bg-green-50/30 opacity-60'
                  : 'border-gray-200 bg-gray-50/50 opacity-40'
              }`}
            >
              {/* Persona header */}
              <div className="flex items-center gap-3 mb-3">
                <span
                  className={`w-7 h-7 flex items-center justify-center rounded-full text-xs font-bold border-2 ${
                    isActive
                      ? 'bg-indigo-100 border-indigo-500 text-indigo-700'
                      : isComplete
                      ? 'bg-green-100 border-green-500 text-green-700'
                      : 'bg-gray-100 border-gray-300 text-gray-400'
                  }`}
                >
                  {isComplete ? '✓' : index + 1}
                </span>
                <h2 className={`text-lg font-bold ${isActive ? 'text-gray-900' : 'text-gray-500'}`}>
                  {segment.name}
                </h2>
              </div>

              {/* Audio element (hidden — controlled programmatically) */}
              <audio
                ref={(el) => { audioRefs.current[index] = el; }}
                src={segment.audioFile}
                preload="auto"
                onEnded={() => handleAudioEnded(index)}
                onError={() => setAudioErrors((prev) => new Set(prev).add(index))}
              />

              {/* Caption */}
              <blockquote
                className={`border-l-4 pl-4 py-2 italic text-base leading-relaxed mb-3 ${
                  isActive ? 'border-indigo-300 text-gray-700' : 'border-gray-200 text-gray-400'
                }`}
              >
                "{segment.caption}"
              </blockquote>

              {/* Real substep logs */}
              {logs.length > 0 && (
                <div className={`border rounded-lg p-3 ${isActive ? 'border-gray-200 bg-gray-50' : 'border-gray-100 bg-gray-50/50'}`}>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1.5">
                    Real pipeline log entries
                  </h4>
                  <div className="space-y-0.5">
                    {logs.map((entry, i) => (
                      <p key={i} className="text-xs text-gray-600 flex items-start gap-2">
                        <span className="text-green-600 shrink-0">✓</span>
                        <span>{entry.message}</span>
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </main>
    </div>
  );
}
