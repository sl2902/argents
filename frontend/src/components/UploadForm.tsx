import { useState, useRef, DragEvent } from 'react';

interface UploadFormProps {
  onSubmit: (params: {
    files: File[];
    knownTitle?: string;
    knownArtist?: string;
    knownPeriod?: string;
    medium?: string;
  }) => void;
  imageUrl: string | null;
}

export default function UploadForm({ onSubmit, imageUrl }: UploadFormProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [knownTitle, setKnownTitle] = useState('');
  const [knownArtist, setKnownArtist] = useState('');
  const [knownPeriod, setKnownPeriod] = useState('');
  const [medium, setMedium] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(imageUrl);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (newFiles: File[]) => {
    const imageFiles = newFiles.filter(f => f.type.startsWith('image/'));
    if (!imageFiles.length) return;
    setFiles(imageFiles);
    // Generate preview
    if (previewUrl && previewUrl !== imageUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(imageFiles[0]));
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(Array.from(e.dataTransfer.files));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!files.length) return;
    onSubmit({
      files,
      knownTitle: knownTitle || undefined,
      knownArtist: knownArtist || undefined,
      knownPeriod: knownPeriod || undefined,
      medium: medium || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(Array.from(e.target.files || []))}
        />

        {previewUrl ? (
          <div className="flex flex-col items-center gap-3">
            <img src={previewUrl} alt="Preview" className="max-h-48 rounded-lg shadow-sm object-contain" />
            <p className="text-gray-600 text-sm">{files.map(f => f.name).join(', ') || 'Image selected'}</p>
            <p className="text-xs text-gray-400">Click or drop to replace</p>
          </div>
        ) : (
          <div>
            <p className="text-gray-600 text-lg">Drop artwork photo(s) here or click to browse</p>
            <p className="text-gray-400 text-sm mt-2">JPEG, PNG, or WebP — multiple views supported</p>
          </div>
        )}
      </div>

      {/* Optional metadata */}
      <details className="bg-white rounded-lg border border-gray-200 p-4">
        <summary className="cursor-pointer text-gray-600 font-medium">
          Optional: provide known metadata
        </summary>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <input placeholder="Known title" value={knownTitle} onChange={e => setKnownTitle(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input placeholder="Known artist" value={knownArtist} onChange={e => setKnownArtist(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input placeholder="Known period (e.g. 1880-1890)" value={knownPeriod} onChange={e => setKnownPeriod(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <input placeholder="Medium (e.g. oil on canvas)" value={medium} onChange={e => setMedium(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
      </details>

      <button
        type="submit"
        disabled={!files.length}
        className="w-full py-3 px-6 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Analyze Artwork
      </button>
    </form>
  );
}
