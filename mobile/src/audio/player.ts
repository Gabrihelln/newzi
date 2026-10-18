import { NativeModules } from 'react-native';
import type { OnBufferData, OnLoadData, OnPlaybackStateChangedData, OnProgressData, VideoRef } from 'react-native-video';
import { api } from '../api/client';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import type { AudioMetadata, Briefing } from '../types/api';
import { editionArtworkUrl, editionDay, editionPeriodLabel } from '../components/EditionCover';

// Playback runs in one native media player (react-native-video: Media3 on Android, AVPlayer on iOS),
// rendered invisibly by <AudioEngine /> at the app root. It shows lock-screen and notification
// controls, answers headset/Bluetooth/car buttons, and keeps playing in the background.
// A briefing already on disk plays from the file (also offline); otherwise it streams with the
// session token, so playback starts before the download finishes, and is cached for next time.

export type PlaybackState = { position: number; duration: number; playing: boolean; paused: boolean; ended: boolean; buffering: boolean; loaded: boolean; started?: boolean; speed?: number };
export type AudioContext = { url: string; briefing: Briefing; metadata: AudioMetadata };
export type EngineSource = { key: number; uri: string; headers?: Record<string, string>; title: string; artwork?: string };
export type EngineSnapshot = { source: EngineSource | null; paused: boolean; rate: number };

type AudioCache = {
  cachedPath?: (url: string) => Promise<string | null>;
  download?: (url: string, token: string) => Promise<string>;
  savePosition?: (url: string, seconds: number) => void;
  getPosition?: (url: string) => Promise<number>;
  clear?: () => void;
};
const cache = (): AudioCache => (NativeModules.NewziAudioCache || {}) as AudioCache;

const LOAD_TIMEOUT_MS = 30000;
// A brief "not playing" also happens while the stream buffers; only a lasting one is a user pause.
const EXTERNAL_PAUSE_DELAY_MS = 700;

let engine: VideoRef | null = null;
let snapshot: EngineSnapshot = { source: null, paused: true, rate: 1 };
const engineListeners = new Set<() => void>();
let sourceSeq = 0;
let pendingLoad: { key: number; startAt: number; startRatio?: number; resumePlaying?: boolean; resolve: () => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | null = null;
let nativeBuffering = false;
let nativePlaying = false;
let externalPauseTimer: ReturnType<typeof setTimeout> | undefined;

let currentUrl: string | null = null;
let loadingUrl: string | null = null;
let loadingPromise: Promise<void> | null = null;
let lastSavedAt = 0;
let lastProgressSyncAt = 0;
let state: PlaybackState = { position: 0, duration: 0, playing: false, paused: false, ended: false, buffering: false, loaded: false, started: false, speed: 1 };
const listeners = new Set<(state: PlaybackState) => void>();
let audioContext: AudioContext | null = null;
const contextListeners = new Set<(context: AudioContext | null) => void>();
let variantSwitchRun = 0;
let voiceSyncRun = 0;
let voiceSyncTimer: ReturnType<typeof setTimeout> | undefined;
let readyVoiceVariant: { briefingId: string; voice: string; url: string; briefing: Briefing; metadata: AudioMetadata } | null = null;

/**
 * A delivery keeps its id when the same day's briefing is regenerated (e.g. after new content preferences),
 * so the edition must also match before a loaded audio session is reused.
 */
export function sameBriefing(a: Briefing | null | undefined, b: Briefing | null | undefined) {
  if (!a?.id || !b?.id || a.id !== b.id) return false;
  return !a.edition_id || !b.edition_id || a.edition_id === b.edition_id;
}

function briefingKey(briefing: Briefing) { return briefing.delivery_id || briefing.id || briefing.edition_id || ''; }

/** Title of the media notification: "Resumo da tarde · 18 out". */
export function briefingAudioTitle(briefing: Briefing | null | undefined) {
  if (!briefing?.date) return 'Resumo do dia';
  const period = editionPeriodLabel(briefing).toLowerCase();
  return `${period[0].toUpperCase()}${period.slice(1)} · ${editionDay(briefing, false)}`;
}

/** Album-style artwork of the notification: the edition's cover. */
export const briefingArtwork = (briefing: Briefing | null | undefined) => briefing?.date ? editionArtworkUrl(briefing) : undefined;

function update(patch: Partial<PlaybackState>) {
  state = { ...state, ...patch };
  listeners.forEach(listener => listener(state));
}

// ---------------------------------------------------------------- engine bridge (used by <AudioEngine />)
function setEngine(patch: Partial<EngineSnapshot>) {
  snapshot = { ...snapshot, ...patch };
  engineListeners.forEach(listener => listener());
}
export function subscribeEngine(listener: () => void) { engineListeners.add(listener); return () => { engineListeners.delete(listener); }; }
export function getEngineSnapshot() { return snapshot; }
export function attachEngine(ref: VideoRef | null) { engine = ref; }

function isCurrent(key: number) { return snapshot.source?.key === key; }

export function onEngineLoad(key: number, data: OnLoadData) {
  if (!isCurrent(key)) return;
  const duration = data.duration || 0;
  const load = pendingLoad && pendingLoad.key === key ? pendingLoad : null;
  let position = load?.startRatio != null ? duration * load.startRatio : load?.startAt || 0;
  position = position > 0 && position < duration - 1 ? position : 0;
  if (position) engine?.seek(position);
  nativeBuffering = false;
  update({ position, duration, buffering: false, loaded: true, ended: false });
  if (load) {
    clearTimeout(load.timer);
    pendingLoad = null;
    if (load.resumePlaying) startPlayback();
    load.resolve();
  }
}

export function onEngineError(key: number, error: unknown) {
  if (!isCurrent(key)) return;
  const message = typeof error === 'object' && error ? JSON.stringify(error).slice(0, 200) : String(error);
  if (pendingLoad && pendingLoad.key === key) {
    clearTimeout(pendingLoad.timer);
    pendingLoad.reject(new Error(`audio failed to load: ${message}`));
    pendingLoad = null;
    return;
  }
  setEngine({ paused: true });
  update({ playing: false, paused: true, buffering: false });
}

export function onEngineProgress(key: number, data: OnProgressData) {
  if (!isCurrent(key) || pendingLoad) return;
  const duration = state.duration || data.seekableDuration || 0;
  update({ position: data.currentTime, duration });
  persistBriefingProgress(data.currentTime, duration);
  if (currentUrl && Date.now() - lastSavedAt > 5000) {
    cache().savePosition?.(currentUrl, data.currentTime);
    lastSavedAt = Date.now();
  }
}

export function onEngineEnd(key: number) {
  if (!isCurrent(key)) return;
  finishPlayback();
}

export function onEngineBuffer(key: number, data: OnBufferData) {
  if (!isCurrent(key)) return;
  nativeBuffering = data.isBuffering;
  update({ buffering: data.isBuffering });
}

/** Reconcile pauses and plays issued outside the app: lock screen, notification, headset, car. */
export function onEnginePlaybackStateChanged(key: number, data: OnPlaybackStateChangedData) {
  if (!isCurrent(key) || pendingLoad) return;
  nativePlaying = data.isPlaying;
  if (externalPauseTimer) { clearTimeout(externalPauseTimer); externalPauseTimer = undefined; }
  if (data.isSeeking) return;
  if (data.isPlaying && !state.playing && state.loaded) {
    setEngine({ paused: false });
    update({ playing: true, paused: false, ended: false, started: true });
  } else if (!data.isPlaying && state.playing) {
    externalPauseTimer = setTimeout(() => {
      externalPauseTimer = undefined;
      if (!isCurrent(key) || nativePlaying || nativeBuffering || !state.playing) return;
      if (state.duration > 0 && state.position >= state.duration - 1) { finishPlayback(); return; }
      pauseAudio();
    }, EXTERNAL_PAUSE_DELAY_MS);
  }
}

// ---------------------------------------------------------------- playback
function finishPlayback() {
  if (externalPauseTimer) { clearTimeout(externalPauseTimer); externalPauseTimer = undefined; }
  setEngine({ paused: true });
  update({ playing: false, paused: false, ended: true, started: false, position: state.duration });
  persistBriefingProgress(state.duration, state.duration, true);
  if (currentUrl) cache().savePosition?.(currentUrl, 0);
}

function persistBriefingProgress(position: number, duration: number, force = false) {
  const briefingId = audioContext?.briefing?.delivery_id || audioContext?.briefing?.id;
  if (!briefingId || !Number.isFinite(position) || !Number.isFinite(duration) || duration <= 0) return Promise.resolve();
  if (!force && Date.now() - lastProgressSyncAt < 15000) return Promise.resolve();
  lastProgressSyncAt = Date.now();
  return api.saveBriefingListeningProgress(briefingId, Math.max(0, Math.min(position, duration)), duration).catch(() => undefined);
}

export function subscribeAudio(listener: (state: PlaybackState) => void) {
  listeners.add(listener);
  listener(state);
  return () => { listeners.delete(listener); };
}

export function subscribeAudioContext(listener: (context: AudioContext | null) => void) {
  contextListeners.add(listener);
  listener(audioContext);
  return () => { contextListeners.delete(listener); };
}

export function getAudioContext() { return audioContext; }

export function setAudioContext(url: string, briefing: Briefing, metadata: AudioMetadata) {
  if (currentUrl !== url) return;
  const readyVariant = readyVoiceVariant;
  audioContext = { url, briefing, metadata };
  contextListeners.forEach(listener => listener(audioContext));
  if (readyVariant && readyVariant.briefingId === briefingKey(briefing) && metadata.voice !== readyVariant.voice) {
    void switchAudioVariant(readyVariant.url, readyVariant.briefing, readyVariant.metadata);
  }
}

/** Source for a briefing URL: the downloaded file when there is one, else the authenticated stream. */
async function resolveSource(url: string) {
  const local = await cache().cachedPath?.(url).catch(() => null);
  if (local) return { uri: local.startsWith('file://') ? local : `file://${local}` };
  const token = await getFirebaseIdToken();
  if (!token) throw new Error('authentication required for audio');
  // Download in the background so the next play (or one without network) comes from disk.
  cache().download?.(url, token).catch(() => undefined);
  return { uri: url, headers: { Authorization: `Bearer ${token}` } };
}

function openSource(url: string, resolved: { uri: string; headers?: Record<string, string> }, title: string,
  options: { startAt?: number; startRatio?: number; resumePlaying?: boolean } = {}, artwork?: string) {
  if (pendingLoad) { clearTimeout(pendingLoad.timer); pendingLoad.reject(new Error('audio load superseded')); pendingLoad = null; }
  const key = ++sourceSeq;
  nativeBuffering = true; nativePlaying = false;
  currentUrl = url;
  const loaded = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      if (pendingLoad?.key !== key) return;
      pendingLoad = null;
      reject(new Error('audio load timed out'));
    }, LOAD_TIMEOUT_MS);
    pendingLoad = { key, startAt: options.startAt || 0, startRatio: options.startRatio, resumePlaying: options.resumePlaying, resolve, reject, timer };
  });
  setEngine({ source: { key, ...resolved, title, artwork }, paused: true });
  return loaded;
}

export async function loadAudio(url: string, title = 'Resumo do dia', artwork?: string) {
  if (!/^https?:\/\//i.test(url)) throw new Error('invalid audio URL');
  if (currentUrl === url && snapshot.source && state.loaded) return;
  if (loadingUrl === url && loadingPromise) return loadingPromise;
  loadingUrl = url;
  update({ buffering: true });
  loadingPromise = (async () => {
    const resolved = await resolveSource(url);
    const saved = await cache().getPosition?.(url).catch(() => 0) || 0;
    audioContext = null;
    contextListeners.forEach(listener => listener(null));
    update({ position: 0, duration: 0, playing: false, paused: false, ended: false, loaded: false, started: false });
    await openSource(url, resolved, title, { startAt: saved }, artwork);
  })();
  try { await loadingPromise; }
  catch (error) { update({ buffering: false, loaded: false }); throw error; }
  finally { loadingUrl = null; loadingPromise = null; }
}

function startPlayback() {
  if (state.ended) { engine?.seek(0); update({ position: 0 }); }
  setEngine({ paused: false });
  update({ playing: true, paused: false, ended: false, started: true });
}

export function playAudio(): Promise<void> {
  if (!snapshot.source || !state.loaded) return Promise.reject(new Error('audio not loaded'));
  startPlayback();
  return Promise.resolve();
}

export function pauseAudio() {
  if (externalPauseTimer) { clearTimeout(externalPauseTimer); externalPauseTimer = undefined; }
  setEngine({ paused: true });
  update({ playing: false, paused: true });
  persistBriefingProgress(state.position, state.duration, true);
  if (currentUrl) cache().savePosition?.(currentUrl, state.position);
}

/** Dismiss the mini player while keeping the same briefing and resume position. */
export async function dismissMiniAudio() {
  setEngine({ paused: true });
  update({ playing: false, paused: true, started: false, ended: false });
  await Promise.all([
    persistBriefingProgress(state.position, state.duration, true),
    currentUrl ? Promise.resolve(cache().savePosition?.(currentUrl, state.position)).catch(() => undefined) : Promise.resolve(),
  ]);
}

export function setPlaybackSpeed(speed: number) {
  if (![0.75, 1, 1.25, 1.5, 2].includes(speed)) return;
  setEngine({ rate: speed });
  update({ speed });
}

export function seekTo(seconds: number) {
  if (!snapshot.source) return;
  const position = Math.max(0, Math.min(seconds, state.duration || seconds));
  engine?.seek(position);
  update({ position, ended: false });
  if (currentUrl) cache().savePosition?.(currentUrl, position);
}

export async function seekAudio(offset: number) { seekTo(state.position + offset); }

export function restartAudio() { seekTo(0); }

/** Current playback state; the native player reports position through progress events. */
export function getAudioProgress(): Promise<PlaybackState> { return Promise.resolve(state); }

export const isPlaying = async () => state.playing;

/** Switch a loaded briefing to a validated voice variant without losing its relative playback position. */
export async function switchAudioVariant(url: string, briefing: Briefing, metadata: AudioMetadata) {
  const existingContext = audioContext;
  const key = briefingKey(briefing);
  if (!existingContext || !key || briefingKey(existingContext.briefing) !== key || !/^https?:\/\//i.test(url)) return;
  if (currentUrl === url) {
    audioContext = { url, briefing, metadata };
    readyVoiceVariant = null;
    contextListeners.forEach(listener => listener(audioContext));
    return;
  }
  const run = ++variantSwitchRun;
  const oldUrl = currentUrl;
  try {
    const resolved = await resolveSource(url);
    if (run !== variantSwitchRun || currentUrl !== oldUrl || audioContext !== existingContext) return;
    const ratio = state.duration > 0 ? Math.max(0, Math.min(1, state.position / state.duration)) : 0;
    const wasPlaying = state.playing;
    audioContext = { url, briefing, metadata };
    readyVoiceVariant = null;
    contextListeners.forEach(listener => listener(audioContext));
    update({ playing: false, buffering: true });
    await openSource(url, resolved, briefingAudioTitle(briefing), { startRatio: ratio, resumePlaying: wasPlaying && ratio < 1 }, briefingArtwork(briefing));
    persistBriefingProgress(state.position, state.duration, true);
  } catch {
    // Keep the previous context when the variant cannot be loaded; the user can retry from the player.
  }
}

/** Poll the current delivery until its persisted voice variant is active and READY. */
export function syncSelectedBriefingVoice(briefing: Briefing, voice: string) {
  voiceSyncRun++;
  variantSwitchRun++;
  const run = voiceSyncRun;
  if (voiceSyncTimer) clearTimeout(voiceSyncTimer);
  readyVoiceVariant = null;
  const id = briefing.delivery_id || briefing.id;
  const key = briefingKey(briefing);
  if (!id || !key || !voice) return;
  let attempts = 0;
  const poll = async () => {
    if (run !== voiceSyncRun) return;
    try {
      const metadata = await api.audio(id);
      if (run !== voiceSyncRun) return;
      const activeVoice = metadata.active_voice_id || metadata.voice;
      if (metadata.status === 'READY' && activeVoice === voice && metadata.audio_url) {
        const variant = { briefingId: key, voice, url: metadata.audio_url, briefing, metadata };
        readyVoiceVariant = variant;
        const context = audioContext;
        if (context && briefingKey(context.briefing) === key) await switchAudioVariant(variant.url, briefing, metadata);
        return;
      }
      if (metadata.audio_status === 'FAILED' || (metadata.status === 'FAILED' && metadata.audio_status !== 'PENDING')) return;
    } catch { /* transient network errors are retried with backoff */ }
    attempts++;
    if (attempts >= 45) return;
    voiceSyncTimer = setTimeout(poll, Math.min(20000, 5000 + attempts * 1000));
  };
  void poll();
}

export function releaseAudio() {
  if (pendingLoad) { clearTimeout(pendingLoad.timer); pendingLoad.reject(new Error('audio released')); pendingLoad = null; }
  if (externalPauseTimer) { clearTimeout(externalPauseTimer); externalPauseTimer = undefined; }
  setEngine({ source: null, paused: true, rate: 1 });
  currentUrl = null;
  audioContext = null;
  lastProgressSyncAt = 0;
  contextListeners.forEach(listener => listener(null));
  update({ position: 0, duration: 0, playing: false, paused: false, ended: false, buffering: false, loaded: false, started: false, speed: 1 });
}

export function clearCachedAudio() {
  releaseAudio();
  cache().clear?.();
}
