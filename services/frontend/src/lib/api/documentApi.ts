import { apiJson, apiFetch } from '@/lib/apiClient';

export interface DocumentMeta {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  status: 'pending' | 'processing' | 'done' | 'failed';
}

// 문서 목록 조회
export async function listDocuments(): Promise<DocumentMeta[]> {
  return apiJson<DocumentMeta[]>('/api/v1/documents');
}

// 문서 상세 + 분석 결과 조회
export async function getDocument(id: string): Promise<DocumentMeta> {
  return apiJson<DocumentMeta>(`/api/v1/documents/${id}`);
}

// 문서 업로드 (multipart/form-data)
export async function uploadDocument(file: File): Promise<DocumentMeta> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch('/api/v1/documents', {
    method: 'POST',
    headers: {},  // Content-Type은 fetch가 boundary 포함해서 자동 설정
    body: form,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<DocumentMeta>;
}

// 문서 삭제
export async function deleteDocument(id: string): Promise<void> {
  await apiFetch(`/api/v1/documents/${id}`, { method: 'DELETE' });
}
