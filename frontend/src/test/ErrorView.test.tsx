import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ErrorView from '../components/ErrorView';
import { AnalyzeError } from '../api/client';

describe('ErrorView error type rendering', () => {
  const onRetry = vi.fn();

  it('renders "Not an Artwork" for 422 + visual_art_historian stage', () => {
    const error = new AnalyzeError('The image shows a person, not artwork', 422, 'visual_art_historian');
    render(<ErrorView error={error} onRetry={onRetry} />);

    expect(screen.getByText('Not an Artwork')).toBeInTheDocument();
    expect(screen.getByText(/person, not artwork/)).toBeInTheDocument();
  });

  it('renders "Invalid Input" for 422 + validation stage (Pydantic error)', () => {
    const error = new AnalyzeError(
      'One of the fields you entered was too long or invalid. Please check your input and try again.',
      422,
      'validation',
    );
    render(<ErrorView error={error} onRetry={onRetry} />);

    expect(screen.getByText('Invalid Input')).toBeInTheDocument();
    expect(screen.getByText(/too long or invalid/)).toBeInTheDocument();
    // Should NOT show "Not an Artwork"
    expect(screen.queryByText('Not an Artwork')).not.toBeInTheDocument();
  });

  it('renders generic "Analysis Failed" for 500 errors', () => {
    const error = new AnalyzeError('Vertex timeout', 500, 'model_call');
    render(<ErrorView error={error} onRetry={onRetry} />);

    expect(screen.getByText('Analysis Failed')).toBeInTheDocument();
    expect(screen.getByText(/Vertex timeout/)).toBeInTheDocument();
    expect(screen.getByText(/model_call/)).toBeInTheDocument();
  });

  it('does not crash on unexpected 422 with unknown stage', () => {
    const error = new AnalyzeError('Something odd', 422, 'upload');
    render(<ErrorView error={error} onRetry={onRetry} />);

    // Falls through to generic error display
    expect(screen.getByText('Analysis Failed')).toBeInTheDocument();
    expect(screen.getByText(/Something odd/)).toBeInTheDocument();
  });

  it('shows Try Again button for all error types', () => {
    const error = new AnalyzeError('test', 422, 'validation');
    render(<ErrorView error={error} onRetry={onRetry} />);

    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});
