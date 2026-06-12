import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

import DocumentAnalysisSidebar from '../DocumentAnalysisSidebar';

beforeEach(() => {
  mockPush.mockReset();
});

describe('DocumentAnalysisSidebar — 스킬빌더 핸드오프 (REQ-010)', () => {
  it('"이 문서로 스킬 만들기" 클릭 시 source_document_id 와 함께 빌더로 이동한다', async () => {
    const user = userEvent.setup();
    render(<DocumentAnalysisSidebar analyzed documentId="doc-42" />);

    await user.click(screen.getByRole('button', { name: /이 문서로 스킬 만들기/ }));
    expect(mockPush).toHaveBeenCalledWith('/documents?build=1&source_document_id=doc-42');
  });

  it('분석 전에도 핸드오프 버튼은 활성화돼 있다 (분석 여부와 무관)', () => {
    render(<DocumentAnalysisSidebar analyzed={false} documentId="doc-42" />);
    expect(screen.getByRole('button', { name: /이 문서로 스킬 만들기/ })).toBeEnabled();
  });
});
