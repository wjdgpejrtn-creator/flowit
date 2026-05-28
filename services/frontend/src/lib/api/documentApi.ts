import { apiJson, apiFetch } from '@/lib/apiClient';

// 백엔드 DocumentResponse (GET /{id}, POST /upload 공통 응답)
export interface DocumentResponse {
  document_id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  gcs_uri: string;
  is_analyzed: boolean;
}

export interface DocumentDownloadResponse {
  document_id: string;
  download_url: string;
  expires_in: number;
}

export interface AnalyzeDispatchResponse {
  document_id: string;
  task_id: string;
  action: string;
}

// 문서 단건 조회
export async function getDocument(id: string): Promise<DocumentResponse> {
  return apiJson<DocumentResponse>(`/api/v1/documents/${id}`);
}

// 문서 업로드 (multipart/form-data) — POST /upload
export async function uploadDocument(file: File): Promise<DocumentResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch('/api/v1/documents/upload', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<DocumentResponse>;
}

// 다운로드 presigned URL 발급
export async function getDownloadUrl(id: string): Promise<DocumentDownloadResponse> {
  return apiJson<DocumentDownloadResponse>(`/api/v1/documents/${id}/download`);
}

// 분석 Celery task dispatch (202 Accepted)
export async function analyzeDocument(id: string): Promise<AnalyzeDispatchResponse> {
  return apiJson<AnalyzeDispatchResponse>(`/api/v1/documents/${id}/analyze`, {
    method: 'POST',
  });
}
