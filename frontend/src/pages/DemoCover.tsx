/**
 * DemoCover — the entry screen for the guided demo flow.
 *
 * Pure HTML/CSS/SVG illustration matching the app's indigo/violet identity.
 * No AI-generated imagery. Text is real HTML, not baked into an image.
 */

interface DemoCoverProps {
  onEnter: () => void;
}

export default function DemoCover({ onEnter }: DemoCoverProps) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-violet-50 px-4">
      {/* SVG illustration — 6 bot agents in a semi-circle viewing a painting */}
      <div className="mb-8">
        <svg
          width="360"
          height="240"
          viewBox="0 0 360 240"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          className="drop-shadow-lg"
        >
          {/* Gallery wall */}
          <rect x="0" y="0" width="360" height="130" fill="#F8FAFC" />
          <rect x="0" y="130" width="360" height="110" fill="#E2E8F0" />
          <line x1="0" y1="130" x2="360" y2="130" stroke="#CBD5E1" strokeWidth="1" />

          {/* Painting on wall */}
          <rect x="120" y="12" width="120" height="95" rx="3" fill="#1E1B4B" stroke="#7C3AED" strokeWidth="3" />
          <rect x="127" y="19" width="106" height="81" rx="2" fill="#312E81" />
          <circle cx="155" cy="48" r="13" fill="#A78BFA" opacity="0.7" />
          <circle cx="200" cy="60" r="9" fill="#6366F1" opacity="0.6" />
          <path d="M140 78 Q165 50 190 72 T225 65" stroke="#C4B5FD" strokeWidth="2" fill="none" strokeLinecap="round" />
          <path d="M135 90 Q170 78 195 88" stroke="#818CF8" strokeWidth="1.5" fill="none" strokeLinecap="round" />

          {/* 6 Bot agents in a semi-circle (from behind) */}

          {/* Agent 1 - Visual Art Historian — symbol: magnifying glass */}
          <g transform="translate(55, 155)">
            <rect x="3" y="20" width="24" height="32" rx="7" fill="#4338CA" />
            <circle cx="15" cy="14" r="11" fill="#4338CA" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#A5B4FC" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#A5B4FC" />
            {/* Symbol: magnifying glass */}
            <circle cx="13" cy="-16" r="6" fill="none" stroke="#A5B4FC" strokeWidth="2" />
            <line x1="17" y1="-12" x2="21" y2="-8" stroke="#A5B4FC" strokeWidth="2" strokeLinecap="round" />
          </g>

          {/* Agent 2 - Compliance Auditor — symbol: warning triangle */}
          <g transform="translate(110, 165)">
            <rect x="3" y="20" width="24" height="30" rx="7" fill="#334155" />
            <circle cx="15" cy="14" r="11" fill="#334155" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#94A3B8" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#94A3B8" />
            {/* Symbol: warning triangle */}
            <path d="M15 -22 L7 -9 L23 -9 Z" fill="none" stroke="#94A3B8" strokeWidth="2" strokeLinejoin="round" />
            <line x1="15" y1="-19" x2="15" y2="-14" stroke="#94A3B8" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-11" r="1" fill="#94A3B8" />
          </g>

          {/* Agent 3 - Provenance Historian — symbol: clock/history */}
          <g transform="translate(155, 170)">
            <rect x="3" y="20" width="24" height="28" rx="7" fill="#7E22CE" />
            <circle cx="15" cy="14" r="11" fill="#7E22CE" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#D8B4FE" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#D8B4FE" />
            {/* Symbol: clock */}
            <circle cx="15" cy="-15" r="7" fill="none" stroke="#D8B4FE" strokeWidth="2" />
            <line x1="15" y1="-15" x2="15" y2="-19" stroke="#D8B4FE" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="15" y1="-15" x2="18" y2="-13" stroke="#D8B4FE" strokeWidth="1.5" strokeLinecap="round" />
          </g>

          {/* Agent 4 - Conservative Appraiser — symbol: dollar with down arrow */}
          <g transform="translate(200, 170)">
            <rect x="3" y="20" width="24" height="28" rx="7" fill="#115E59" />
            <circle cx="15" cy="14" r="11" fill="#115E59" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#5EEAD4" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#5EEAD4" />
            {/* Symbol: dollar sign with floor line */}
            <text x="15" y="-12" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#5EEAD4" fontFamily="monospace">$</text>
            <line x1="9" y1="-7" x2="21" y2="-7" stroke="#5EEAD4" strokeWidth="2" strokeLinecap="round" />
          </g>

          {/* Agent 5 - Bullish Specialist — symbol: dollar with up arrow */}
          <g transform="translate(245, 165)">
            <rect x="3" y="20" width="24" height="30" rx="7" fill="#B45309" />
            <circle cx="15" cy="14" r="11" fill="#B45309" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#FCD34D" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#FCD34D" />
            {/* Symbol: dollar sign with ceiling line */}
            <text x="15" y="-12" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#FCD34D" fontFamily="monospace">$</text>
            <line x1="9" y1="-21" x2="21" y2="-21" stroke="#FCD34D" strokeWidth="2" strokeLinecap="round" />
          </g>

          {/* Agent 6 - Curator — symbol: document/page */}
          <g transform="translate(295, 155)">
            <rect x="3" y="20" width="24" height="32" rx="7" fill="#5B21B6" />
            <circle cx="15" cy="14" r="11" fill="#5B21B6" />
            <line x1="15" y1="3" x2="15" y2="-1" stroke="#C4B5FD" strokeWidth="2" strokeLinecap="round" />
            <circle cx="15" cy="-2" r="2.5" fill="#C4B5FD" />
            {/* Symbol: document/page with lines */}
            <rect x="9" y="-23" width="12" height="15" rx="1.5" fill="none" stroke="#C4B5FD" strokeWidth="2" />
            <line x1="12" y1="-18" x2="18" y2="-18" stroke="#C4B5FD" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="12" y1="-14" x2="18" y2="-14" stroke="#C4B5FD" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="12" y1="-10" x2="16" y2="-10" stroke="#C4B5FD" strokeWidth="1.5" strokeLinecap="round" />
          </g>
        </svg>
      </div>

      {/* Title and tagline */}
      <h1 className="text-5xl font-bold text-gray-900 mb-3 tracking-tight">
        Artgents
      </h1>
      <p className="text-lg text-gray-600 mb-2 text-center max-w-md">
        Multi-Agent Fine Art Provenance &amp; Curation Studio
      </p>
      <p className="text-sm text-gray-500 mb-10 text-center max-w-lg">
        Six AI agents research an artwork the way a real gallery team would —
        then debate each other's findings in the open.
      </p>

      {/* Enter button */}
      <button
        onClick={onEnter}
        className="px-8 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all text-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      >
        Enter Demo
      </button>

      <p className="mt-6 text-xs text-gray-400 text-center max-w-sm">
        This guided walkthrough uses a pre-recorded analysis — no live API calls, no wait time.
      </p>
    </div>
  );
}
