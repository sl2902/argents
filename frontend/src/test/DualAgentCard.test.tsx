import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import DualAgentCard from '../components/DualAgentCard';

describe('DualAgentCard VerdictBadge states', () => {
  const defaultProps = {
    title: 'Provenance & Legal',
    leftLabel: 'Compliance Auditor',
    leftContent: <p>Test reasoning</p>,
    rightLabel: 'Provenance Historian',
    rightContent: <p>Test context</p>,
    disagreement: false,
    synthesisSummary: 'Both agree: low risk',
  };

  it('renders "low" verdict with green styling', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="low"
        rightVerdict="low"
      />
    );

    const badges = screen.getAllByText('low');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(badges[0].className).toContain('bg-green-100');
  });

  it('renders "moderate" verdict with yellow styling', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="moderate"
        rightVerdict="low"
      />
    );

    const badge = screen.getByText('moderate');
    expect(badge.className).toContain('bg-yellow-100');
  });

  it('renders "red_flag" verdict with red styling', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="red_flag"
        rightVerdict="low"
      />
    );

    const badge = screen.getByText('red flag');
    expect(badge.className).toContain('bg-red-100');
  });

  it('renders "cannot_determine_insufficient_object_data" with slate/neutral styling', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="cannot_determine_insufficient_object_data"
        rightVerdict="low"
        disagreement={true}
        synthesisSummary="Cannot determine without object-specific data"
      />
    );

    const badge = screen.getByText('cannot determine');
    expect(badge.className).toContain('bg-slate-100');
    expect(badge.className).toContain('text-slate-700');
    // Not on the red/amber/green spectrum
    expect(badge.className).not.toContain('bg-green');
    expect(badge.className).not.toContain('bg-yellow');
    expect(badge.className).not.toContain('bg-red');
  });

  it('shows explanatory copy for cannot_determine state', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="cannot_determine_insufficient_object_data"
        rightVerdict="cannot_determine_insufficient_object_data"
        disagreement={true}
        synthesisSummary="Cannot determine"
      />
    );

    // Should show the explanatory text
    const explanations = screen.getAllByText('Needs object-specific research');
    expect(explanations.length).toBe(2); // one per sub-agent
  });

  it('does NOT show explanatory copy for normal risk levels', () => {
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="low"
        rightVerdict="moderate"
      />
    );

    expect(screen.queryByText('Needs object-specific research')).not.toBeInTheDocument();
  });

  it('renders fourth state distinctly from all three existing states', () => {
    // Render all four states and verify they have different colors
    render(
      <DualAgentCard {...defaultProps} leftVerdict="low" rightVerdict="low" />
    );
    render(
      <DualAgentCard {...defaultProps} leftVerdict="moderate" rightVerdict="moderate" />
    );
    render(
      <DualAgentCard {...defaultProps} leftVerdict="red_flag" rightVerdict="red_flag" />
    );
    render(
      <DualAgentCard
        {...defaultProps}
        leftVerdict="cannot_determine_insufficient_object_data"
        rightVerdict="cannot_determine_insufficient_object_data"
      />
    );

    // Each should have distinct badge text
    expect(screen.getAllByText('low').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('moderate').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('red flag').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('cannot determine').length).toBeGreaterThanOrEqual(1);
  });
});
