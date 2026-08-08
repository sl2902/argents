import { useMemo, useState } from 'react';
import glossary from '../data/glossary';

interface GlossaryTextProps {
  text: string;
}

interface Segment {
  text: string;
  term: string | null;
}

function Tooltip({ term, definition, children }: { term: string; definition: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="border-b border-dotted border-indigo-400 cursor-help text-indigo-900">
        {children}
      </span>
      {show && (
        <span className="absolute z-[9999] bottom-full left-0 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-xl w-64 text-left leading-relaxed whitespace-normal">
          <span className="font-semibold">{term}:</span> {definition}
          <span className="absolute top-full left-4 border-4 border-transparent border-t-gray-900" />
        </span>
      )}
    </span>
  );
}

/**
 * Renders text with inline glossary tooltips for recognized terms.
 * Case-insensitive whole-word matching; preserves original casing in display.
 */
export default function GlossaryText({ text }: GlossaryTextProps) {
  const segments = useMemo(() => segmentText(text), [text]);

  return (
    <span>
      {segments.map((seg, i) =>
        seg.term ? (
          <Tooltip key={i} term={seg.text} definition={glossary[seg.term]}>
            {seg.text}
          </Tooltip>
        ) : (
          <span key={i}>{seg.text}</span>
        )
      )}
    </span>
  );
}

function segmentText(text: string): Segment[] {
  const terms = Object.keys(glossary);
  if (!terms.length) return [{ text, term: null }];

  const sortedTerms = [...terms].sort((a, b) => b.length - a.length);
  const escaped = sortedTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`\\b(${escaped.join('|')})\\b`, 'gi');

  const segments: Segment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: text.slice(lastIndex, match.index), term: null });
    }
    segments.push({ text: match[0], term: match[0].toLowerCase() });
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    segments.push({ text: text.slice(lastIndex), term: null });
  }

  return segments.length ? segments : [{ text, term: null }];
}
