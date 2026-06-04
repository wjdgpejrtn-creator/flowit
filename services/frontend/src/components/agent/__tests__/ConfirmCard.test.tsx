import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import ConfirmCard from '../ConfirmCard';

const explanation: WorkflowExplanation = {
  intent_restatement: '매주 월요일 광고 시트를 요약해 Slack으로 보낸다',
  summary: '매주 광고 데이터를 요약해 Slack에 전송합니다.',
  steps: [
    { order: 1, node_name: 'Google Sheets 읽기', description: '시트 데이터 로드', risk_level: RiskLevel.LOW },
    { order: 2, node_name: 'Slack 전송', description: '채널에 메시지 전송', risk_level: RiskLevel.MEDIUM },
  ],
  permissions: [
    { connection: 'google_sheets', node_name: 'Google Sheets 읽기', risk_level: RiskLevel.LOW },
    { connection: 'slack', node_name: 'Slack 전송', risk_level: RiskLevel.MEDIUM },
  ],
  assumptions: ['전송 시각: 09:00 (기본값)'],
};

describe('ConfirmCard', () => {
  it('explanation 있으면 본문 문장에 요약 + 권한(인라인 강조)을 렌더한다', () => {
    render(
      <ConfirmCard message="fallback" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} />,
    );
    // 요약은 본문 문장으로 노출
    expect(screen.getByText(/매주 광고 데이터를 요약/)).toBeInTheDocument();
    // 권한은 본문 문장 안 인라인 강조(.em-perm)로 노출
    expect(screen.getByText('slack')).toBeInTheDocument();
    // 구조화 상세 패널은 기본 접힘 — 펼치기 전엔 안 보인다
    expect(screen.queryByText('이 워크플로우가 접근하는 것')).not.toBeInTheDocument();
  });

  it('explanation 없으면 fallback 메시지로 graceful degrade', () => {
    render(<ConfirmCard message="워크플로우가 완성됐습니다." onSave={jest.fn()} onEdit={jest.fn()} />);
    expect(screen.getByText('워크플로우가 완성됐습니다.')).toBeInTheDocument();
    expect(screen.queryByText('이 워크플로우가 접근하는 것')).not.toBeInTheDocument();
    // 상세가 없으면 토글도 없다
    expect(screen.queryByText('상세 보기')).not.toBeInTheDocument();
  });

  it('"상세 보기" 토글로 권한 매니페스트·가정이 펼쳐진다', async () => {
    const user = userEvent.setup();
    render(<ConfirmCard message="f" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} />);
    expect(screen.queryByText('이 워크플로우가 접근하는 것')).not.toBeInTheDocument();
    expect(screen.queryByText('전송 시각: 09:00 (기본값)')).not.toBeInTheDocument();
    await user.click(screen.getByText('상세 보기'));
    expect(screen.getByText('이 워크플로우가 접근하는 것')).toBeInTheDocument();
    expect(screen.getByText('전송 시각: 09:00 (기본값)')).toBeInTheDocument();
  });

  it('저장/편집 버튼이 콜백을 호출한다', async () => {
    const user = userEvent.setup();
    const onSave = jest.fn();
    const onEdit = jest.fn();
    render(<ConfirmCard message="f" explanation={explanation} onSave={onSave} onEdit={onEdit} />);
    await user.click(screen.getByText('저장하고 활성화'));
    await user.click(screen.getByText('편집'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it('loading 중에는 저장 버튼이 비활성화된다', () => {
    render(
      <ConfirmCard message="f" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} loading />,
    );
    expect(screen.getByText('저장 중…').closest('button')).toBeDisabled();
  });
});
