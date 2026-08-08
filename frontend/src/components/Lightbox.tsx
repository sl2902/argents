interface LightboxProps {
  imageUrl: string;
  onClose: () => void;
}

export default function Lightbox({ imageUrl, onClose }: LightboxProps) {
  return (
    <div
      className="fixed inset-0 z-[10000] bg-black/80 flex items-center justify-center p-8 cursor-pointer"
      onClick={onClose}
    >
      <div className="relative max-w-4xl max-h-full" onClick={e => e.stopPropagation()}>
        <img
          src={imageUrl}
          alt="Full size artwork"
          className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
        />
        <button
          onClick={onClose}
          className="absolute top-2 right-2 w-8 h-8 bg-white/90 rounded-full flex items-center justify-center text-gray-700 hover:bg-white shadow-md"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
