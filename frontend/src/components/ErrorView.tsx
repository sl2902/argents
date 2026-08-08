import { AnalyzeError } from '../api/client';

interface ErrorViewProps {
  error: AnalyzeError;
  onRetry: () => void;
}

export default function ErrorView({ error, onRetry }: ErrorViewProps) {
  const isNotArtwork = error.status === 422 && error.stage === 'visual_art_historian';
  const isValidationError = error.status === 422 && error.stage === 'validation';

  return (
    <div className="max-w-lg mx-auto text-center py-12">
      <div className={`rounded-xl p-8 ${
        isNotArtwork ? 'bg-orange-50 border-2 border-orange-200' :
        isValidationError ? 'bg-yellow-50 border-2 border-yellow-200' :
        'bg-red-50 border-2 border-red-200'
      }`}>
        {isNotArtwork ? (
          <>
            <h2 className="text-xl font-bold text-orange-800 mb-3">Not an Artwork</h2>
            <p className="text-orange-700 mb-4">{error.message}</p>
            <p className="text-sm text-orange-600">
              This doesn't appear to be a physical artwork (painting, sculpture, etc.).
              Please upload a photo of an artwork to analyze.
            </p>
          </>
        ) : isValidationError ? (
          <>
            <h2 className="text-xl font-bold text-yellow-800 mb-3">Invalid Input</h2>
            <p className="text-yellow-700 mb-2">{error.message}</p>
          </>
        ) : (
          <>
            <h2 className="text-xl font-bold text-red-800 mb-3">Analysis Failed</h2>
            <p className="text-red-700 mb-2">{error.message}</p>
            <p className="text-sm text-red-500">
              Stage: {error.stage} · Status: {error.status}
            </p>
          </>
        )}
      </div>

      <button
        onClick={onRetry}
        className="mt-6 px-6 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}
