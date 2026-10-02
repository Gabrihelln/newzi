import { API_BASE_URL, LOGGING_ENABLED, devLog } from '../config/env';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import { firebaseAuth } from '../services/firebaseAuth';
import { saveUserPreferences } from '../services/firestoreUser';
import type { ApiError, AudioMetadata, AudioVoiceCatalog, Briefing, BriefingHistoryPage, BriefingItem, HomeData, NotificationSettings, SavedOverview, SavedStoryPage } from '../types/api';

export class ClientError extends Error {
  code: string;
  status?: number;
  requestId?: string;
  constructor(message: string, code = 'INTERNAL_ERROR', status?: number, requestId?: string) { super(message); this.code = code; this.status = status; this.requestId = requestId; }
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  const route = path.split('?')[0];
  const isBootstrapRoute = route === '/api/v1/me' || route === '/api/v1/me/onboarding';
  const requestId = LOGGING_ENABLED ? Math.random().toString(36).slice(2, 8) : undefined;
  if (isBootstrapRoute) devLog(`[API] ${route}:start`);
  try {
    let token: string | null;
    try {
      token = await getFirebaseIdToken();
    } catch {
      throw new ClientError('Não foi possível obter a sessão Firebase.', 'TOKEN_ERROR');
    }
    if (isBootstrapRoute && !token) throw new ClientError('Sessão Firebase ausente.', 'TOKEN_ERROR');
    if (isBootstrapRoute) {
      devLog(`[API Auth] authorization_header_present=${Boolean(token)}`);
      devLog(`[API Auth] scheme=${token ? 'Bearer' : 'none'}`);
    }
    const finalHeaders = new Headers(options.headers);
    finalHeaders.set('Accept', 'application/json');
    finalHeaders.set('Content-Type', 'application/json');
    if (token) finalHeaders.set('Authorization', `Bearer ${token}`);
    else finalHeaders.delete('Authorization');
    if (requestId) finalHeaders.set('X-Newzi-Debug-Request-Id', requestId);
    if (LOGGING_ENABLED) {
      devLog(`[HTTP ${requestId}] method=${options.method || 'GET'}`);
      devLog(`[HTTP ${requestId}] path=${route}`);
      devLog(`[HTTP ${requestId}] header_names=${Array.from(finalHeaders.keys()).join(',')}`);
      devLog(`[HTTP ${requestId}] authorization_present_final=${finalHeaders.has('authorization')}`);
      devLog(`[HTTP ${requestId}] url=${API_BASE_URL}${path}`);
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: finalHeaders,
    });
    if (isBootstrapRoute) devLog(`[API] ${route}:status=${response.status}`);
    if (LOGGING_ENABLED) devLog(`[HTTP ${requestId}] redirect=${response.redirected ? 'true' : 'false'}`);
    const payload = await response.json().catch(() => ({}));
    if (LOGGING_ENABLED) devLog(`[HTTP ${requestId}] status=${response.status}`);
    if (!response.ok) {
      const error = payload as ApiError;
      const fallbackCode = response.status === 401 ? 'AUTH_REQUIRED' : response.status >= 500 ? 'SERVER_ERROR' : response.status === 400 || response.status === 422 ? 'VALIDATION_ERROR' : 'INTERNAL_ERROR';
      throw new ClientError(error?.error?.message || 'Não foi possível concluir a operação.', error?.error?.code || fallbackCode, response.status, error?.error?.request_id);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ClientError) { if (LOGGING_ENABLED) devLog(`[HTTP ${requestId}] error=${error.code} status=${error.status ?? 'none'}`); throw error; }
    if (error instanceof Error && error.name === 'AbortError') throw new ClientError('A conexão demorou demais. Tente novamente.', 'TIMEOUT');
    throw new ClientError('Não foi possível alcançar o backend. OFFLINE ou backend indisponível.', 'BACKEND_UNREACHABLE');
  } finally { clearTimeout(timeout); }
}

export const api = {
  logout: () => apiRequest('/api/v1/auth/logout', { method: 'POST' }),
  me: () => apiRequest<any>('/api/v1/me'),
  config: () => apiRequest<any>('/api/v1/client/config'),
  onboarding: () => apiRequest<any>('/api/v1/me/onboarding'),
  saveOnboarding: async (body: any) => { const result = await apiRequest<any>('/api/v1/me/onboarding', { method: 'PUT', body: JSON.stringify(body) }); if (firebaseAuth.currentUser) await saveUserPreferences(firebaseAuth.currentUser, body); return result; },
  preferences: () => apiRequest<any>('/api/v1/me/preferences'),
  contentRevision: () => apiRequest<{ revision: number; updated_at: string | null }>('/api/v1/me/content/revision'),
  home: async () => {
    const result = await apiRequest<HomeData>('/api/v1/me/home');
    const today = result.today_briefing;
    if (today?.audio_url && !/^https?:\/\//i.test(today.audio_url)) {
      return { ...result, today_briefing: { ...today, audio_url: `${API_BASE_URL}${today.audio_url}` } };
    }
    return result;
  },
  savePreferences: async (body: any) => { const result = await apiRequest<any>('/api/v1/me/preferences', { method: 'PUT', body: JSON.stringify(body) }); if (firebaseAuth.currentUser) await saveUserPreferences(firebaseAuth.currentUser, body).catch(() => undefined); return result; },
  today: () => apiRequest<any>('/api/v1/me/briefings/today'),
  history: (limit = 20, cursor?: string) => apiRequest<BriefingHistoryPage>(`/api/v1/me/briefings?limit=${limit}${cursor ? `&cursor=${cursor}` : ''}`),
  news: (limit = 20, filters: { query?: string; topic?: string; discovery?: boolean } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filters.query) params.set('q', filters.query);
    if (filters.topic) params.set('topic', filters.topic);
    if (filters.discovery) params.set('discovery', 'true');
    return apiRequest<{ items: BriefingItem[] }>(`/api/v1/me/news?${params.toString()}`);
  },
  savedStories: () => apiRequest<{ items: BriefingItem[] }>('/api/v1/me/saved'),
  savedOverview: () => apiRequest<SavedOverview>('/api/v1/me/saved/overview'),
  savedStoriesPage: (limit = 40, cursor?: string, topicId?: string) => { const params = new URLSearchParams({ limit: String(limit) }); if (cursor) params.set('cursor', cursor); if (topicId) params.set('topic', topicId); return apiRequest<SavedStoryPage>(`/api/v1/me/saved?${params.toString()}`); },
  saveReadingProgress: (storyId: string, progress: number) => apiRequest<{ status: string; progress: number }>(`/api/v1/me/saved/${encodeURIComponent(storyId)}/progress`, { method: 'PUT', body: JSON.stringify({ progress }) }),
  savedBriefings: () => apiRequest<{ items: Briefing[] }>('/api/v1/me/saved-briefings'),
  saveBriefing: (briefingId: string) => apiRequest<{ status: string }>('/api/v1/me/saved-briefings', { method: 'PUT', body: JSON.stringify({ briefing_id: briefingId }) }),
  removeSavedBriefing: (briefingId: string) => apiRequest<{ status: string }>(`/api/v1/me/saved-briefings/${encodeURIComponent(briefingId)}`, { method: 'DELETE' }),
  saveStory: (story: BriefingItem) => apiRequest<{ item: BriefingItem }>('/api/v1/me/saved', { method: 'PUT', body: JSON.stringify({ story }) }),
  removeSavedStory: (storyId: string) => apiRequest<{ status: string }>(`/api/v1/me/saved/${encodeURIComponent(storyId)}`, { method: 'DELETE' }),
  articleFeedback: (storyId: string, rating?: number) => apiRequest<{ rating: number | null; updated_at: string | null }>(`/api/v1/me/articles/${encodeURIComponent(storyId)}/feedback`, rating === undefined ? undefined : { method: 'PUT', body: JSON.stringify({ rating }) }),
  briefing: (id: string) => apiRequest<any>(`/api/v1/me/briefings/${encodeURIComponent(id)}`),
  audio: async (id: string) => { const result = await apiRequest<AudioMetadata>(`/api/v1/me/briefings/${encodeURIComponent(id)}/audio`); return result.audio_url && !/^https?:\/\//i.test(result.audio_url) ? { ...result, audio_url: `${API_BASE_URL}${result.audio_url}` } : result; },
  saveBriefingListeningProgress: (id: string, progressSeconds: number, durationSeconds: number) => apiRequest<{ status: string; completed: boolean }>(`/api/v1/me/briefings/${encodeURIComponent(id)}/progress`, { method: 'PUT', body: JSON.stringify({ progress_seconds: progressSeconds, duration_seconds: durationSeconds }) }),
  retryDeliveryAudio: (id: string) => apiRequest<any>(`/api/v1/me/briefings/${encodeURIComponent(id)}/audio/retry`, { method: 'POST' }),
  audioVoices: async () => { const catalog = await apiRequest<AudioVoiceCatalog>('/api/v1/me/audio/voices'); return { ...catalog, voices: catalog.voices.map(voice => ({ ...voice, preview_url: `${API_BASE_URL}${voice.preview_url}` })) }; },
  registerDevice: (body: any) => apiRequest<any>('/api/v1/me/devices', { method: 'POST', body: JSON.stringify(body) }),
  disableDevice: (id: string) => apiRequest<any>(`/api/v1/me/devices/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  notificationSettings: () => apiRequest<NotificationSettings>('/api/v1/me/notification-settings'),
  saveNotificationSettings: (body: Partial<NotificationSettings>) => apiRequest<NotificationSettings>('/api/v1/me/notification-settings', { method: 'PUT', body: JSON.stringify(body) }),
};
