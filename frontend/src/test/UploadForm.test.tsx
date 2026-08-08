import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import UploadForm from '../components/UploadForm';

describe('UploadForm maxLength constraints', () => {
  const defaultProps = {
    onSubmit: vi.fn(),
    imageUrl: null,
  };

  it('known_title input has maxLength=200', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known title');
    expect(input).toHaveAttribute('maxLength', '200');
  });

  it('known_artist input has maxLength=200', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known artist');
    expect(input).toHaveAttribute('maxLength', '200');
  });

  it('known_period input has maxLength=100 (tighter than other fields)', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    expect(input).toHaveAttribute('maxLength', '100');
  });

  it('medium input has maxLength=200', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Medium (e.g. oil on canvas)');
    expect(input).toHaveAttribute('maxLength', '200');
  });
});

describe('UploadForm character counter', () => {
  const defaultProps = {
    onSubmit: vi.fn(),
    imageUrl: null,
  };

  it('does not show counter when field is empty', () => {
    render(<UploadForm {...defaultProps} />);
    // No "0/200" or "0/100" counters visible
    expect(screen.queryByText(/\/200/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/100/)).not.toBeInTheDocument();
  });

  it('shows counter with current length when field has content', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known title');
    fireEvent.change(input, { target: { value: 'Starry Night' } });
    expect(screen.getByText('12/200')).toBeInTheDocument();
  });

  it('counter renders as a sibling below the input, not inside it', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known title');
    fireEvent.change(input, { target: { value: 'Test' } });
    const counter = screen.getByText('4/200');
    // Counter should NOT be absolutely positioned (no overlap)
    expect(counter.className).not.toContain('absolute');
    // Counter is a sibling of the input (both children of same parent div)
    expect(counter.parentElement).toBe(input.parentElement);
  });

  it('counter has grey/default styling under 90% of max', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    // 50 chars = 50% of 100 → default grey
    fireEvent.change(input, { target: { value: 'x'.repeat(50) } });
    const counter = screen.getByText('50/100');
    expect(counter.className).toContain('text-gray-400');
  });

  it('counter has amber/warning styling at 90% of max', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    // 90 chars = 90% of 100 → warning amber
    fireEvent.change(input, { target: { value: 'x'.repeat(90) } });
    const counter = screen.getByText('90/100');
    expect(counter.className).toContain('text-amber-600');
  });

  it('counter has red/error styling at exactly the max', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    // 100 chars = 100% of 100 → at-limit red
    fireEvent.change(input, { target: { value: 'x'.repeat(100) } });
    const counter = screen.getByText('100/100');
    expect(counter.className).toContain('text-red-600');
  });

  it('input border changes to amber at 90% threshold', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    fireEvent.change(input, { target: { value: 'x'.repeat(90) } });
    expect(input.className).toContain('border-amber-400');
  });

  it('input border changes to red at max', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known period (e.g. 1880-1890)');
    fireEvent.change(input, { target: { value: 'x'.repeat(100) } });
    expect(input.className).toContain('border-red-400');
  });

  it('200-char field shows amber at 180 chars (90%)', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known title');
    fireEvent.change(input, { target: { value: 'x'.repeat(180) } });
    const counter = screen.getByText('180/200');
    expect(counter.className).toContain('text-amber-600');
  });

  it('200-char field shows red at 200 chars', () => {
    render(<UploadForm {...defaultProps} />);
    const input = screen.getByPlaceholderText('Known title');
    fireEvent.change(input, { target: { value: 'x'.repeat(200) } });
    const counter = screen.getByText('200/200');
    expect(counter.className).toContain('text-red-600');
  });
});
