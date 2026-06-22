import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { WorkflowExplanation } from '@common/generated';
import { RiskLevel } from '@common/generated';
import type { VerifyData } from '@/stores/agentStore';
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

const verify: VerifyData = {
  intentType: 'draft',
  intentEntities: { 트리거: '매주 월 09:00', 대상: '#ad-report' },
  qaScore: 10,
  qaPassed: true,
  draftNodeCount: 3,
  draftConnCount: 2,
};

describe('ConfirmCard', () => {
  it('explanation 있으면 본문 문장에 요약 + 권한(인라인 강조)을 렌더한다', () => {
    render(
      <ConfirmCard message="fallback" explanation={explanation} onSave={jest.fn()} onEdit={jest.fn()} />,
    );
    // 요약은 본문 문장으로 노출(verify 없으면 통과 문장 대신 요약)
    expect(screen.getByText(/매주 광고 데이터를 요약/)).toBeInTheDocument();
    // 권한은 본문 문장 안 인라인 강조(.em-perm)로 노출
    expect(screen.getByText('slack')).toBeInTheDocument();
    // 검증 상세 보기는 기본 접힘 — 펼치기 전엔 단계 기록이 안 보인다
    expect(screen.queryByText('원문 요청')).not.toBeInTheDocument();
  });

  it('verify.qaScore가 있으면 "검증을 모두 통과" 통과 문장 + 점수를 강조한다', () => {
    render(
      <ConfirmCard message="f" explanation={explanation} verify={verify} onSave={jest.fn()} onEdit={jest.fn()} />,
    );
    expect(screen.getByText(/검증을 모두 통과했어요/)).toBeInTheDocument();
    expect(screen.getByText('10.0 / 10')).toBeInTheDocument();
  });

  it('explanation 없으면 fallback 메시지로 graceful degrade', () => {
    render(<ConfirmCard message="워크플로우가 완성됐습니다." onSave={jest.fn()} onEdit={jest.fn()} />);
    expect(screen.getByText('워크플로우가 완성됐습니다.')).toBeInTheDocument();
    // 상세 기록이 없으면 토글도 없다
    expect(screen.queryByText('검증 상세 보기')).not.toBeInTheDocument();
  });

  it('"검증 상세 보기" 토글로 단계별 기록(원문 요청 · 선정 노드 · 안전성)이 펼쳐진다', async () => {
    const user = userEvent.setup();
    render(
      <ConfirmCard message="f" explanation={explanation} verify={verify} onSave={jest.fn()} onEdit={jest.fn()} />,
    );
    expect(screen.queryByText('원문 요청')).not.toBeInTheDocument();
    await user.click(screen.getByText('검증 상세 보기'));
    // 의도 분석 단계 — 원문 요청 + 추출 정보
    expect(screen.getByText('원문 요청')).toBeInTheDocument();
    expect(screen.getByText('매주 월요일 광고 시트를 요약해 Slack으로 보낸다')).toBeInTheDocument();
    // 노드 선출 단계 — 선정 노드 목록
    expect(screen.getByText(/Google Sheets 읽기 · Slack 전송 \(2개\)/)).toBeInTheDocument();
    // 워크플로우 작성 단계 — verify.draftNodeCount/ConnCount 우선
    expect(screen.getByText('노드 3 · 연결 2')).toBeInTheDocument();
    // 품질 평가 단계 — 점수 + 안전성
    expect(screen.getByText('안전성')).toBeInTheDocument();
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
