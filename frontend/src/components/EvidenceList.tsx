import { EvidenceItemDisplay } from '../types/api';

interface EvidenceListProps {
  title: string;
  items: EvidenceItemDisplay[];
  totalCount: number;
  compact?: boolean;
}

const COMPACT_MAX_LENGTH = 100;

function truncateDescription(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1).trimEnd() + '…';
}

export default function EvidenceList({ title, items, totalCount, compact = false }: EvidenceListProps) {
  if (!items.length) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-gray-700">
        {title}
        <span className="ml-2 text-xs font-normal text-gray-400">
          ({items.length} of {totalCount} shown)
        </span>
      </h4>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-xs">
            <span className="inline-block px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-mono shrink-0">
              {item.source_type}
            </span>
            <span className="text-gray-600 flex-1">
              {compact ? truncateDescription(item.description, COMPACT_MAX_LENGTH) : item.description}
            </span>
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 hover:text-indigo-800 underline shrink-0"
            >
              source ↗
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
