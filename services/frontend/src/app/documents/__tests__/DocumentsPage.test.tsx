import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/documents',
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

const mockUpload = jest.fn();
const mockList = jest.fn();
jest.mock('../../../lib/api/documentApi', () => ({
  uploadDocument: (...args: unknown[]) => mockUpload(...args),
  listDocuments: (...args: unknown[]) => mockList(...args),
}));

import DocumentsPage from '../page';

const DOC = {
  document_id: 'doc-1',
  file_name: '2026 Q2 견적_LG.pdf',
  mime_type: 'application/pdf',
  file_size: 2_400_000,
  gcs_uri: 'gs://bucket/doc-1',
  is_analyzed: true,
  analysis_status: 'completed',
};

beforeEach(() => {
  mockPush.mockReset();
  mockUpload.mockReset();
  // 기본값: 서버 미가용 → localStorage 캐시 폴백 경로를 검증 (마운트 시 캐시를 덮어쓰지 않음).
  mockList.mockReset();
  mockList.mockRejectedValue(new Error('server unavailable'));
  localStorage.clear();
});

describe('DocumentsPage — 카드 그리드 + 업로드 패널 (디자인 SSOT)', () => {
  it('저장된 문서를 카드로 렌더링한다', () => {
    localStorage.setItem('wf_documents_list', JSON.stringify([DOC]));
    render(<DocumentsPage />);

    expect(screen.getByText('2026 Q2 견적_LG.pdf')).toBeInTheDocument();
    expect(screen.getByText('문서 보관함')).toBeInTheDocument();
    // 파일타입 태그
    expect(screen.getByText('PDF')).toBeInTheDocument();
  });

  it('카드 클릭 시 상세 페이지로 이동한다', async () => {
    const user = userEvent.setup();
    localStorage.setItem('wf_documents_list', JSON.stringify([DOC]));
    render(<DocumentsPage />);

    await user.click(screen.getByText('2026 Q2 견적_LG.pdf'));
    expect(mockPush).toHaveBeenCalledWith('/documents/doc-1');
  });

  it('미분석 문서의 "분석하기" 클릭 시 상세로 이동하며 분석 신호(?analyze=1)를 붙인다', async () => {
    const user = userEvent.setup();
    // 분석하기 버튼은 미분석(is_analyzed=false) 문서에만 노출된다.
    localStorage.setItem(
      'wf_documents_list',
      JSON.stringify([{ ...DOC, document_id: 'doc-2', is_analyzed: false, analysis_status: 'pending' }]),
    );
    render(<DocumentsPage />);

    await user.click(screen.getByText('분석하기'));
    // 카드 onOpen(plain /documents/doc-2)이 아니라, ?analyze=1로 상세 진입(stopPropagation + 분석 신호).
    expect(mockPush).toHaveBeenCalledWith('/documents/doc-2?analyze=1');
  });

  it('문서가 없으면 빈 상태를 보여주고 업로드 패널을 노출한다', () => {
    render(<DocumentsPage />);

    expect(screen.getByText('문서가 없습니다')).toBeInTheDocument();
    expect(screen.getByText('업로드')).toBeInTheDocument();
    expect(screen.getByText(/파일을 드래그하거나/)).toBeInTheDocument();
  });
});
