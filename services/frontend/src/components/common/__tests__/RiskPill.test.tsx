import { render, screen } from '@testing-library/react';
import RiskPill from '../RiskPill';
import { RiskLevel } from '@common/generated';

describe('RiskPill', () => {
  it.each([
    [RiskLevel.LOW,        'Low'],
    [RiskLevel.MEDIUM,     'Medium'],
    [RiskLevel.HIGH,       'High'],
    [RiskLevel.RESTRICTED, 'Restricted'],
  ])('renders correct label for %s', (level, expectedLabel) => {
    render(<RiskPill level={level} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it('defaults to Low when no level provided', () => {
    render(<RiskPill />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('uses custom label when provided', () => {
    render(<RiskPill level={RiskLevel.HIGH} label="위험" />);
    expect(screen.getByText('위험')).toBeInTheDocument();
  });
});
