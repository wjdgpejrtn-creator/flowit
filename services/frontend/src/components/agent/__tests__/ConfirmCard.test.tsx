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
  it('explanation 있으면 의도/단계/권한 매니페스트를 렌더한다', () => {
    render(
      <ConfirmCard message="fallback" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} />,
    );
    expect(screen.getByText(/매주 월요일 광고 시트/)).toBeInTheDocument();
    // node_name은 단계 + 권한 양쪽에 나타날 수 있어 getAllByText로 확인
    expect(screen.getAllByText('Google Sheets 읽기').length).toBeGreaterThan(0);
    expect(screen.getByText('이 워크플로우가 접근하는 것')).toBeInTheDocument();
    expect(screen.getByText('slack')).toBeInTheDocument();
  });

  it('explanation 없으면 fallback 메시지로 graceful degrade', () => {
    render(<ConfirmCard message="워크플로우가 완성됐습니다." onSave={jest.fn()} onEdit={jest.fn()} />);
    expect(screen.getByText('워크플로우가 완성됐습니다.')).toBeInTheDocument();
    expect(screen.queryByText('이 워크플로우가 접근하는 것')).not.toBeInTheDocument();
  });

  it('가정 섹션은 토글로 펼쳐진다', async () => {
    const user = userEvent.setup();
    render(<ConfirmCard message="f" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} />);
    expect(screen.queryByText('전송 시각: 09:00 (기본값)')).not.toBeInTheDocument();
    await user.click(screen.getByText(/가정한 항목 1개/));
    expect(screen.getByText('전송 시각: 09:00 (기본값)')).toBeInTheDocument();
  });

  it('저장/편집 버튼이 콜백을 호출한다', async () => {
    const user = userEvent.setup();
    const onSave = jest.fn();
    const onEdit = jest.fn();
    render(<ConfirmCard message="f" explanation={explanation} onSave={onSave} onEdit={onEdit} />);
    await user.click(screen.getByText('💾 저장'));
    await user.click(screen.getByText('✏️ 편집'));
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
