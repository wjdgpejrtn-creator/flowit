import { render } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { RiskLevel } from '@common/generated';
import CustomNode, { type CustomNodeData } from '../CustomNode';
import type { NodeProps } from '@xyflow/react';

// React Flow Handle 은 ReactFlowProvider 컨텍스트가 필요하므로 래핑해서 렌더한다.
function renderNode(selected = false) {
  const data: CustomNodeData = {
    name: '웹훅 발송',
    node_type: 'webhook',
    risk_level: RiskLevel.MEDIUM,
  };
  const props = {
    id: 'node-1',
    data: data as unknown as Record<string, unknown>,
    selected,
  } as unknown as NodeProps;
  return render(
    <ReactFlowProvider>
      <CustomNode {...props} />
    </ReactFlowProvider>,
  );
}

describe('CustomNode — 4방향 연결 핸들', () => {
  it('상·하·좌·우 4개의 핸들을 렌더링한다', () => {
    const { container } = renderNode();
    const handles = container.querySelectorAll('.react-flow__handle');
    expect(handles).toHaveLength(4);
  });

  it('각 핸들이 top/right/bottom/left 위치를 갖는다', () => {
    const { container } = renderNode();
    const positions = Array.from(container.querySelectorAll('.react-flow__handle'))
      .map((h) => h.getAttribute('data-handlepos'))
      .sort();
    expect(positions).toEqual(['bottom', 'left', 'right', 'top']);
  });
});
