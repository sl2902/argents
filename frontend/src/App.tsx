import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnalyzeResponse } from './types/api';
import { AnalyzeError, ProgressEntry, analyzeArtwork } from './api/client';
import UploadForm from './components/UploadForm';
import LoadingView from './components/LoadingView';
import ResultsView from './components/ResultsView';
import ErrorView from './components/ErrorView';

type AppState = 'upload' | 'loading' | 'results' | 'error';

export default function App() {
  const [state, setState] = useState<AppState>('upload');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressEntry[]>([]);

  const handleSubmit = async (params: {
    files: File[];
    knownTitle?: string;
    knownArtist?: string;
    knownPeriod?: string;
    medium?: string;
  }) => {
    // Generate thumbnail URL from first file
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    const url = URL.createObjectURL(params.files[0]);
    setImageUrl(url);

    setState('loading');
    setProgress([]);
    setError(null);
    try {
      const response = await analyzeArtwork(params, (logs) => setProgress(logs));
      setResult(response);
      setState('results');
    } catch (err) {
      if (err instanceof AnalyzeError) {
        setError(err);
      } else {
        setError(new AnalyzeError('An unexpected error occurred', 500, 'unknown'));
      }
      setState('error');
    }
  };

  const handleReset = () => {
    setState('upload');
    setResult(null);
    setError(null);
    setProgress([]);
    if (imageUrl) {
      URL.revokeObjectURL(imageUrl);
      setImageUrl(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">
            Artgents
            <span className="ml-2 text-sm font-normal text-gray-500">
              Multi-Agent Fine Art Provenance & Curation Studio
            </span>
          </h1>
          <Link
            to="/demo/explainer"
            className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
          >
            View Pipeline Demo →
          </Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {state === 'upload' && <UploadForm onSubmit={handleSubmit} imageUrl={imageUrl} />}
        {state === 'loading' && <LoadingView imageUrl={imageUrl} logs={progress} />}
        {state === 'results' && result && (
          <ResultsView result={result} onReset={handleReset} imageUrl={imageUrl} />
        )}
        {state === 'error' && error && (
          <ErrorView error={error} onRetry={handleReset} />
        )}
      </main>
    </div>
  );
}
