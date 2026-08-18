import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import EvidenceList from '../components/EvidenceList';

const LONG_DESCRIPTION = 'A'.repeat(200); // 200 chars — longer than compact limit (100)
const SHORT_DESCRIPTION = 'Short text.';

const mockItems = [
  { description: LONG_DESCRIPTION, source_url: 'https://example.com/1', source_type: 'wikidata' },
  { description: SHORT_DESCRIPTION, source_url: 'https://example.com/2', source_type: 'met' },
];

describe('EvidenceList compact mode', () => {
  it('renders full-length descriptions when compact is false (default)', () => {
    render(<EvidenceList title="Test" items={mockItems} totalCount={10} />);
    expect(screen.getByText(LONG_DESCRIPTION)).toBeInTheDocument();
    expect(screen.getByText(SHORT_DESCRIPTION)).toBeInTheDocument();
  });

  it('renders full-length descriptions when compact is explicitly false', () => {
    render(<EvidenceList title="Test" items={mockItems} totalCount={10} compact={false} />);
    expect(screen.getByText(LONG_DESCRIPTION)).toBeInTheDocument();
  });

  it('truncates long descriptions to ~100 chars when compact is true', () => {
    render(<EvidenceList title="Test" items={mockItems} totalCount={10} compact={true} />);
    // Long description should be truncated
    expect(screen.queryByText(LONG_DESCRIPTION)).not.toBeInTheDocument();
    // Should end with ellipsis and be ~100 chars
    const truncated = screen.getByText(/^A+…$/);
    expect(truncated.textContent!.length).toBeLessThanOrEqual(101); // 99 chars + "…"
  });

  it('does not truncate short descriptions even in compact mode', () => {
    render(<EvidenceList title="Test" items={mockItems} totalCount={10} compact={true} />);
    expect(screen.getByText(SHORT_DESCRIPTION)).toBeInTheDocument();
  });

  it('source_url links are NOT shortened in compact mode', () => {
    render(<EvidenceList title="Test" items={mockItems} totalCount={10} compact={true} />);
    const links = screen.getAllByText('source ↗');
    expect(links.length).toBe(2);
    expect(links[0].getAttribute('href')).toBe('https://example.com/1');
    expect(links[1].getAttribute('href')).toBe('https://example.com/2');
  });
});
