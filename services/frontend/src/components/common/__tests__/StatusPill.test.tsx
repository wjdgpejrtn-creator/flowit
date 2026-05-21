import { render, screen } from '@testing-library/react';
import StatusPill from '../StatusPill';

describe('StatusPill', () => {
  it.each([
    ['pending',   '대기'],
    ['running',   '실행 중'],
    ['paused',    '일시정지'],
    ['completed', '완료'],
    ['failed',    '실패'],
    ['cancelled', '취소됨'],
    ['succeeded', '성공'],
    ['retrying',  '재시도'],
  ] as const)('renders correct label for %s', (status, expectedLabel) => {
    render(<StatusPill status={status} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it('defaults to 대기 when no status provided', () => {
    render(<StatusPill />);
    expect(screen.getByText('대기')).toBeInTheDocument();
  });

  it('applies animate-pulse-dot only on running', () => {
    const { container: running } = render(<StatusPill status="running" />);
    const { container: pending } = render(<StatusPill status="pending" />);
    expect(running.querySelector('.animate-pulse-dot')).toBeInTheDocument();
    expect(pending.querySelector('.animate-pulse-dot')).not.toBeInTheDocument();
  });

  it('uses custom label when provided', () => {
    render(<StatusPill status="running" label="진행중" />);
    expect(screen.getByText('진행중')).toBeInTheDocument();
  });
});
