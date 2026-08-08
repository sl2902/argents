interface DisclosuresBannerProps {
  disclosures: string[];
}

export default function DisclosuresBanner({ disclosures }: DisclosuresBannerProps) {
  if (!disclosures.length) return null;

  return (
    <div className="bg-amber-50 border-2 border-amber-300 rounded-xl p-4">
      <h3 className="text-sm font-bold text-amber-900 mb-2 flex items-center gap-2">
        <span>⚠</span> Disclosures
      </h3>
      <ul className="space-y-1">
        {disclosures.map((d, i) => (
          <li key={i} className="text-sm text-amber-800">{d}</li>
        ))}
      </ul>
    </div>
  );
}
