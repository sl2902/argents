interface VariantToggleProps {
  selected: 'auction_house' | 'public_gallery';
  onChange: (variant: 'auction_house' | 'public_gallery') => void;
}

export default function VariantToggle({ selected, onChange }: VariantToggleProps) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200 p-0.5 bg-gray-100">
      <button
        onClick={() => onChange('auction_house')}
        className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
          selected === 'auction_house'
            ? 'bg-white text-gray-900 shadow-sm'
            : 'text-gray-500 hover:text-gray-700'
        }`}
      >
        Auction House
      </button>
      <button
        onClick={() => onChange('public_gallery')}
        className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
          selected === 'public_gallery'
            ? 'bg-white text-gray-900 shadow-sm'
            : 'text-gray-500 hover:text-gray-700'
        }`}
      >
        Public Gallery
      </button>
    </div>
  );
}
