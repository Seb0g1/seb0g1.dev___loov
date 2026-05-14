export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

function buildUrl(path: string) {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
  return new URL(`${API_BASE}${path}`, origin)
}

async function request(path: string, init?: RequestInit, projectId?: number | null) {
  const url = buildUrl(path)
  if (projectId) {
    url.searchParams.set('project_id', String(projectId))
  }
  const response = await fetch(url.toString(), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json()
}

export const api = {
  health: () => request('/health'),
  projects: () => request('/projects'),
  project: (projectId: number) => request(`/projects/${projectId}`),
  updateProject: (projectId: number, payload: Record<string, unknown>) => request(`/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  analytics: (projectId?: number | null) => request('/analytics', undefined, projectId),
  products: (projectId?: number | null) => request('/products', undefined, projectId),
  product: (productId: number, projectId?: number | null) => request(`/products/${productId}`, undefined, projectId),
  drafts: (projectId?: number | null) => request('/drafts', undefined, projectId),
  draft: (draftId: number, projectId?: number | null) => request(`/drafts/${draftId}`, undefined, projectId),
  settings: () => request('/settings'),
  updateSettings: (values: Record<string, string>) => request('/settings', {
    method: 'PUT',
    body: JSON.stringify({ values }),
  }),
  testTelegramToken: () => request('/settings/telegram/test-token', { method: 'POST' }),
  testTelegramAdmin: () => request('/settings/telegram/test-admin', { method: 'POST' }),
  testTelegramChannels: () => request('/settings/telegram/test-channels', { method: 'POST' }),
  testPaymentSettings: () => request('/settings/payments/test', { method: 'POST' }),
  referrals: (projectId?: number | null) => request('/referrals', undefined, projectId),
  published: (projectId?: number | null) => request('/published', undefined, projectId),
  syncStatus: (projectId?: number | null) => request('/sync-status', undefined, projectId),
  generationLogs: (projectId?: number | null) => request('/logs/generation', undefined, projectId),
  publishLogs: (projectId?: number | null) => request('/logs/publish', undefined, projectId),
  adPackages: () => request('/ads/packages'),
  adRequests: () => request('/ads/requests'),
  adRequest: (requestId: number) => request(`/ads/requests/${requestId}`),
  adRequestMediaUrl: (requestId: number) => buildUrl(`/ads/requests/${requestId}/media`).toString(),
  updateAdPackage: (packageId: number, payload: Record<string, unknown>) => request(`/ads/packages/${packageId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  updateAdRequest: (requestId: number, payload: Record<string, unknown>) => request(`/ads/requests/${requestId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  createAdInvoice: (requestId: number, payload: Record<string, unknown>) => request(`/ads/requests/${requestId}/invoice`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  markAdPaid: (requestId: number) => request(`/ads/requests/${requestId}/mark-paid`, { method: 'POST' }),
  publishAd: (requestId: number, payload: Record<string, unknown>) => request(`/ads/requests/${requestId}/publish`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  importProducts: (projectId?: number | null) => request('/products/import', { method: 'POST' }, projectId),
  importAndDraft: (style = 'short', projectId?: number | null) => request(`/import-and-create-drafts?style=${encodeURIComponent(style)}`, { method: 'POST' }, projectId),
  createDraft: (productId: number, style = 'short', projectId?: number | null) => request(`/drafts/from-product/${productId}`, {
    method: 'POST',
    body: JSON.stringify({ style, regenerate_text: true, regenerate_image: true }),
  }, projectId),
  updateProduct: (productId: number, payload: Record<string, unknown>, projectId?: number | null) => request(`/products/${productId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }, projectId),
  updateDraft: (draftId: number, payload: Record<string, unknown>, projectId?: number | null) => request(`/drafts/${draftId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }, projectId),
  approveDraft: (draftId: number, projectId?: number | null) => request(`/drafts/${draftId}/approve`, { method: 'POST' }, projectId),
  decideDraft: (draftId: number, action: 'approve' | 'reject' | 'redo' | 'next', projectId?: number | null) => request(`/drafts/${draftId}/decision`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  }, projectId),
  duplicateDraft: (draftId: number, projectId?: number | null) => request(`/drafts/${draftId}/duplicate`, { method: 'POST' }, projectId),
  publishDraft: (draftId: number, projectId?: number | null) => request(`/drafts/${draftId}/publish`, { method: 'POST' }, projectId),
  regenerateDraft: (draftId: number, projectId?: number | null) => request(`/drafts/${draftId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ style: 'short', regenerate_text: true, regenerate_image: true }),
  }, projectId),
  verifyPublished: (publishedId: number, projectId?: number | null) => request(`/published/${publishedId}/verify`, { method: 'POST' }, projectId),
  scheduleDraft: (draftId: number, runAt: string, projectId?: number | null) => request(`/drafts/${draftId}/schedule`, {
    method: 'POST',
    body: JSON.stringify({ run_at: runAt }),
  }, projectId),
  excludeProduct: (productId: number, projectId?: number | null) => request(`/products/${productId}/exclude`, { method: 'POST' }, projectId),
}
