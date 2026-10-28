import { API_BASE_URL, LOGGING_ENABLED, devLog } from '../config/env';
import { firebaseAuth, getFirebaseIdToken } from '../services/firebaseAuth';
import { cachedRead } from '../services/offlineCache';
import type { ApiError, AudioMetadata, BriefingSearchResult, BriefingSlots, Entitlements, ExtraBriefing, FollowedStory, GenerationStatus, KeywordAlert, OnDemandNews, MatchAudio, PremiumFeatureId, SavedAudio, SavedCollection, SavedArticle, AudioVoiceCatalog, Briefing, BriefingHistoryPage, BriefingItem, FootballAlerts, FootballFavorites, FootballOverview, FootballRound, FootballStandings, FootballTeam, HomeData, Subscription, NotificationSettings, NotificationSwitches, SavedOverview, SavedStoryPage } from '../types/api';

/** What users read when the app cannot reach the server: no technical terms. */
export const CONNECTION_ERROR_MESSAGE = 'Sem conexão com o Newzi. Verifique sua internet e tente novamente.';

export class ClientError extends Error {
  code: string;
  status?: number;
  requestId?: string;
  /** PREMIUM_REQUIRED: the Premium feature the request needed. */
  feature?: PremiumFeatureId;
  constructor(message: string, code = 'INTERNAL_ERROR', status?: number, requestId?: string, feature?: PremiumFeatureId) { super(message); this.code = code; this.status = status; this.requestId = requestId; this.feature = feature; }
}

/** A server path (/api/v1/...) becomes a full URL; full URLs are kept. */
export const absoluteUrl = (url: string) => /^https?:\/\//i.test(url) ? url : `${API_BASE_URL}${url}`;

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
      throw new ClientError('Não foi possível confirmar seu acesso. Entre novamente na sua conta.', 'TOKEN_ERROR');
    }
    if (isBootstrapRoute && !token) throw new ClientError('Sua sessão terminou. Entre novamente na sua conta.', 'TOKEN_ERROR');
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
      throw new ClientError(error?.error?.message || 'Não foi possível concluir a operação.', error?.error?.code || fallbackCode, response.status, error?.error?.request_id, error?.error?.feature);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ClientError) { if (LOGGING_ENABLED) devLog(`[HTTP ${requestId}] error=${error.code} status=${error.status ?? 'none'}`); throw error; }
    if (error instanceof Error && error.name === 'AbortError') throw new ClientError('A conexão demorou demais. Tente novamente.', 'TIMEOUT');
    throw new ClientError(CONNECTION_ERROR_MESSAGE, 'BACKEND_UNREACHABLE');
  } finally { clearTimeout(timeout); }
}

// Saved answers are per account: the key starts with the signed-in user's id.
const cached = <T,>(key: unknown[], fetcher: () => Promise<T>) => cachedRead<T>([firebaseAuth.currentUser?.uid || 'anonymous', ...key], fetcher);

export const api = {
  logout: (pushToken?: string) => apiRequest('/api/v1/auth/logout', { method: 'POST', ...(pushToken ? { body: JSON.stringify({ push_token: pushToken }) } : {}) }),
  me: () => apiRequest<any>('/api/v1/me'),
  deleteAccount: () => apiRequest<void>('/api/v1/me', { method: 'DELETE' }),
  config: () => apiRequest<any>('/api/v1/client/config'),
  onboarding: () => apiRequest<any>('/api/v1/me/onboarding'),
  // The backend is the only store of preferences; nothing is mirrored to Firestore.
  saveOnboarding: (body: any) => apiRequest<any>('/api/v1/me/onboarding', { method: 'PUT', body: JSON.stringify(body) }),
  preferences: () => apiRequest<any>('/api/v1/me/preferences'),
  contentRevision: () => apiRequest<{ revision: number; updated_at: string | null }>('/api/v1/me/content/revision'),
  home: () => cached(['home'], async () => {
    const result = await apiRequest<HomeData>('/api/v1/me/home');
    const today = result.today_briefing;
    if (today?.audio_url && !/^https?:\/\//i.test(today.audio_url)) {
      return { ...result, today_briefing: { ...today, audio_url: `${API_BASE_URL}${today.audio_url}` } };
    }
    return result;
  }),
  savePreferences: (body: any) => apiRequest<any>('/api/v1/me/preferences', { method: 'PUT', body: JSON.stringify(body) }),
  today: () => cached(['today'], () => apiRequest<any>('/api/v1/me/briefings/today')),
  history: (limit = 20, cursor?: string) => cached(['history', limit, cursor || ''], () => apiRequest<BriefingHistoryPage>(`/api/v1/me/briefings?limit=${limit}${cursor ? `&cursor=${cursor}` : ''}`)),
  news: (limit = 20, filters: { query?: string; topic?: string; discovery?: boolean } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filters.query) params.set('q', filters.query);
    if (filters.topic) params.set('topic', filters.topic);
    if (filters.discovery) params.set('discovery', 'true');
    return cached(['news', params.toString()], () => apiRequest<{ items: BriefingItem[] }>(`/api/v1/me/news?${params.toString()}`));
  },
  // scope 'explore': the Explore card, for everyone; default: only for people who follow football.
  football: (scope?: 'explore') => cached(['football-v2', scope || 'followed'], () => apiRequest<FootballOverview>(`/api/v1/me/football${scope ? `?scope=${scope}` : ''}`)),
  subscription: () => apiRequest<Subscription>('/api/v1/me/subscription'),
  /** After a store purchase or restore: the server reads the plan from RevenueCat and returns it. */
  syncSubscription: () => apiRequest<Subscription>('/api/v1/me/subscription/sync', { method: 'POST' }),
  uploadAvatar: (imageBase64: string) => apiRequest<{ photo_url: string }>('/api/v1/me/avatar', { method: 'POST', body: JSON.stringify({ image_base64: imageBase64 }) }),
  footballStandings: (code: string) => cached(['football-standings', code], () => apiRequest<FootballStandings>(`/api/v1/me/football/standings/${encodeURIComponent(code)}`)),
  footballRound: (code: string, matchday?: number) => apiRequest<FootballRound>(`/api/v1/me/football/rounds/${encodeURIComponent(code)}${matchday ? `?matchday=${matchday}` : ''}`),
  footballTeams: (params: { q?: string; competition?: string }) => apiRequest<{ teams: FootballTeam[] }>(`/api/v1/me/football/teams?q=${encodeURIComponent(params.q || '')}&competition=${encodeURIComponent(params.competition || '')}`),
  footballFavorites: () => apiRequest<FootballFavorites>('/api/v1/me/football/favorites'),
  saveFootballFavorites: (body: { team_ids?: number[]; alerts?: Partial<FootballAlerts> }) => apiRequest<FootballFavorites>('/api/v1/me/football/favorites', { method: 'PUT', body: JSON.stringify(body) }),
  followFootballMatch: (id: number, following: boolean) => apiRequest<{ match_id: number; following: boolean }>(`/api/v1/me/football/matches/${id}/follow`, { method: 'PUT', body: JSON.stringify({ following }) }),
  story: (storyId: string) => cached(['story', storyId], () => apiRequest<{ item: BriefingItem }>(`/api/v1/me/news/${encodeURIComponent(storyId)}`)),
  savedStories: () => apiRequest<{ items: BriefingItem[] }>('/api/v1/me/saved'),
  savedOverview: () => cached(['savedOverview'], () => apiRequest<SavedOverview>('/api/v1/me/saved/overview')),
  // Cached too: with Salvos offline (Premium) the pages read ahead of time open without a connection.
  savedStoriesPage: (limit = 40, cursor?: string, topicId?: string) => { const params = new URLSearchParams({ limit: String(limit) }); if (cursor) params.set('cursor', cursor); if (topicId) params.set('topic', topicId); return cached(['savedPage', params.toString()], () => apiRequest<SavedStoryPage>(`/api/v1/me/saved?${params.toString()}`)); },
  savedBriefings: () => cached(['savedBriefings'], () => apiRequest<{ items: Briefing[] }>('/api/v1/me/saved-briefings')),
  saveReadingProgress: (storyId: string, progress: number) => apiRequest<{ status: string; progress: number }>(`/api/v1/me/saved/${encodeURIComponent(storyId)}/progress`, { method: 'PUT', body: JSON.stringify({ progress }) }),
  saveBriefing: (briefingId: string) => apiRequest<{ status: string }>('/api/v1/me/saved-briefings', { method: 'PUT', body: JSON.stringify({ briefing_id: briefingId }) }),
  removeSavedBriefing: (briefingId: string) => apiRequest<{ status: string }>(`/api/v1/me/saved-briefings/${encodeURIComponent(briefingId)}`, { method: 'DELETE' }),
  saveStory: (story: BriefingItem) => apiRequest<{ item: BriefingItem }>('/api/v1/me/saved', { method: 'PUT', body: JSON.stringify({ story }) }),
  removeSavedStory: (storyId: string) => apiRequest<{ status: string }>(`/api/v1/me/saved/${encodeURIComponent(storyId)}`, { method: 'DELETE' }),
  articleFeedback: (storyId: string, rating?: number) => apiRequest<{ rating: number | null; updated_at: string | null }>(`/api/v1/me/articles/${encodeURIComponent(storyId)}/feedback`, rating === undefined ? undefined : { method: 'PUT', body: JSON.stringify({ rating }) }),
  briefing: (id: string) => cached(['briefing', id], () => apiRequest<any>(`/api/v1/me/briefings/${encodeURIComponent(id)}`)),
  // Cached too: offline, the player still finds the audio URL and plays the file already on disk.
  audio: (id: string) => cached(['audio', id], async () => { const result = await apiRequest<AudioMetadata>(`/api/v1/me/briefings/${encodeURIComponent(id)}/audio`); return result.audio_url && !/^https?:\/\//i.test(result.audio_url) ? { ...result, audio_url: `${API_BASE_URL}${result.audio_url}` } : result; }),
  saveBriefingListeningProgress: (id: string, progressSeconds: number, durationSeconds: number) => apiRequest<{ status: string; completed: boolean }>(`/api/v1/me/briefings/${encodeURIComponent(id)}/progress`, { method: 'PUT', body: JSON.stringify({ progress_seconds: progressSeconds, duration_seconds: durationSeconds }) }),
  retryDeliveryAudio: (id: string) => apiRequest<any>(`/api/v1/me/briefings/${encodeURIComponent(id)}/audio/retry`, { method: 'POST' }),
  // `language` lists the voices of a language not saved yet (onboarding); their previews follow it.
  audioVoices: async (language?: string) => { const query = language ? `language=${encodeURIComponent(language)}` : ''; const catalog = await apiRequest<AudioVoiceCatalog>(`/api/v1/me/audio/voices${query ? `?${query}` : ''}`); return { ...catalog, voices: catalog.voices.map(voice => ({ ...voice, preview_url: `${API_BASE_URL}${voice.preview_url}${query ? `${voice.preview_url.includes('?') ? '&' : '?'}${query}` : ''}` })) }; },
  registerDevice: (body: any) => apiRequest<any>('/api/v1/me/devices', { method: 'POST', body: JSON.stringify(body) }),
  disableDevice: (id: string) => apiRequest<any>(`/api/v1/me/devices/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  notificationSettings: () => apiRequest<NotificationSettings>('/api/v1/me/notification-settings'),
  saveNotificationSettings: (body: Partial<NotificationSwitches>) => apiRequest<NotificationSettings>('/api/v1/me/notification-settings', { method: 'PUT', body: JSON.stringify(body) }),

  // Premium (the server decides what each plan may use; see services/premium.tsx).
  entitlements: () => cached(['entitlements'], () => apiRequest<Entitlements>('/api/v1/me/entitlements')),
  briefingSlots: () => apiRequest<BriefingSlots>('/api/v1/me/briefing-slots'),
  saveBriefingSlots: (extra: Pick<ExtraBriefing, 'time' | 'theme' | 'length' | 'enabled'>[]) => apiRequest<BriefingSlots>('/api/v1/me/briefing-slots', { method: 'PUT', body: JSON.stringify({ extra }) }),
  onDemandNews: () => apiRequest<OnDemandNews>('/api/v1/me/briefings/now'),
  briefingNow: () => apiRequest<GenerationStatus>('/api/v1/me/briefings/now', { method: 'POST' }),
  generation: (id: string) => apiRequest<GenerationStatus>(`/api/v1/me/briefings/generations/${encodeURIComponent(id)}`),
  searchBriefings: (query: string) => apiRequest<{ items: BriefingSearchResult[] }>(`/api/v1/me/briefings/search?q=${encodeURIComponent(query)}`),
  collections: () => cached(['collections'], () => apiRequest<{ items: SavedCollection[] }>('/api/v1/me/collections')),
  createCollection: (name: string) => apiRequest<SavedCollection>('/api/v1/me/collections', { method: 'POST', body: JSON.stringify({ name }) }),
  renameCollection: (id: string, name: string) => apiRequest<SavedCollection>(`/api/v1/me/collections/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteCollection: (id: string) => apiRequest<{ status: string }>(`/api/v1/me/collections/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  collectionStories: (id: string) => cached(['collection', id], () => apiRequest<{ items: SavedArticle[] }>(`/api/v1/me/collections/${encodeURIComponent(id)}/items`)),
  setCollectionMember: (id: string, story: BriefingItem, member: boolean) => apiRequest<{ collections: string[] }>(`/api/v1/me/collections/${encodeURIComponent(id)}/items`, { method: 'PUT', body: JSON.stringify(member ? { story, member } : { story_id: story.id, member }) }),
  storyCollections: (storyId: string) => apiRequest<{ collection_ids: string[] }>(`/api/v1/me/saved/${encodeURIComponent(storyId)}/collections`),
  keywordAlerts: () => apiRequest<{ items: KeywordAlert[] }>('/api/v1/me/alerts/keywords'),
  addKeywordAlert: (keyword: string) => apiRequest<{ items: KeywordAlert[] }>('/api/v1/me/alerts/keywords', { method: 'POST', body: JSON.stringify({ keyword }) }),
  removeKeywordAlert: (id: string) => apiRequest<{ items: KeywordAlert[] }>(`/api/v1/me/alerts/keywords/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  followedStories: () => apiRequest<{ items: FollowedStory[] }>('/api/v1/me/alerts/stories'),
  storyFollow: (storyId: string) => apiRequest<{ following: boolean }>(`/api/v1/me/news/${encodeURIComponent(storyId)}/follow`),
  followStory: (storyId: string, following: boolean) => apiRequest<{ following: boolean; until?: string }>(`/api/v1/me/news/${encodeURIComponent(storyId)}/follow`, { method: 'PUT', body: JSON.stringify({ following }) }),
  savedAudio: (create = false) => apiRequest<SavedAudio>('/api/v1/me/saved/audio', create ? { method: 'POST' } : undefined).then(result => result.audio_url ? { ...result, audio_url: absoluteUrl(result.audio_url) } : result),
  matchAudio: (matchId: number) => apiRequest<MatchAudio>(`/api/v1/me/football/matches/${matchId}/audio`).then(result => result.audio_url ? { ...result, audio_url: absoluteUrl(result.audio_url) } : result),
  registerLiveActivityToken: (body: { kind: 'start' | 'update'; token: string; push_token: string; match_id?: number }) => apiRequest<{ status: string }>('/api/v1/me/live-activities/tokens', { method: 'POST', body: JSON.stringify(body) }),
};
