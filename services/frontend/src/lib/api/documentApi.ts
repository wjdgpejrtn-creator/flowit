import { apiJson, apiFetch } from '@/lib/apiClient';
import type {
  DocumentResponse,
  DocumentBlocksResponse,
  DocumentDownloadResponse,
  AnalyzeDispatchResponse,
} from '@common/generated';

export type {
  DocumentResponse,
  DocumentBlocksResponse,
  DocumentDownloadResponse,
  AnalyzeDispatchResponse,
};

export async function getDocument(id: string): Promise<DocumentResponse> {
  return apiJson<DocumentResponse>(`/api/v1/documents/${id}`);
}

export async function getDocumentBlocks(id: string): Promise<DocumentBlocksResponse> {
  return apiJson<DocumentBlocksResponse>(`/api/v1/documents/${id}/blocks`);
}

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

export async function getDownloadUrl(id: string): Promise<DocumentDownloadResponse> {
  return apiJson<DocumentDownloadResponse>(`/api/v1/documents/${id}/download`);
}

export async function analyzeDocument(id: string): Promise<AnalyzeDispatchResponse> {
  return apiJson<AnalyzeDispatchResponse>(`/api/v1/documents/${id}/analyze`, {
    method: 'POST',
  });
}
