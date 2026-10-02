import { NativeModules } from 'react-native';
import Sound from 'react-native-sound';
import { api } from '../api/client';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import type { AudioMetadata, Briefing } from '../types/api';

export type PlaybackState = { position: number; duration: number; playing: boolean; paused: boolean; ended: boolean; buffering: boolean; loaded: boolean; started?: boolean; speed?: number };
export type AudioContext = { url: string; briefing: Briefing; metadata: AudioMetadata };

let current: Sound | null = null;
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

function briefingKey(briefing: Briefing) { return briefing.delivery_id || briefing.id || briefing.edition_id || ''; }

function update(patch: Partial<PlaybackState>) {
  state = { ...state, ...patch };
  listeners.forEach(listener => listener(state));
}

function persistBriefingProgress(position: number, duration: number, force = false) {
  const briefingId=audioContext?.briefing?.delivery_id || audioContext?.briefing?.id;
  if (!briefingId || !Number.isFinite(position) || !Number.isFinite(duration) || duration<=0) return Promise.resolve();
  if (!force && Date.now()-lastProgressSyncAt<15000) return Promise.resolve();
  lastProgressSyncAt=Date.now();
  return api.saveBriefingListeningProgress(briefingId,Math.max(0,Math.min(position,duration)),duration).catch(()=>undefined);
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
  if (readyVariant && readyVariant.briefingId === briefingKey(briefing) && metadata.voice !== readyVariant.voice) {
    audioContext = { url, briefing, metadata };
    contextListeners.forEach(listener => listener(audioContext));
    void switchAudioVariant(readyVariant.url, readyVariant.briefing, readyVariant.metadata);
    return;
  }
  audioContext = { url, briefing, metadata };
  contextListeners.forEach(listener => listener(audioContext));
}

/** Switch a loaded briefing to a validated voice variant without losing its global playback position. */
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
  let replacement: Sound | null = null;
  try {
    const token = await getFirebaseIdToken();
    if (!token) throw new Error('authentication required for audio');
    const cache = NativeModules.NewziAudioCache as { download: (url: string, token: string) => Promise<string> } | undefined;
    if (!cache?.download) throw new Error('native audio cache unavailable; rebuild the app');
    const localPath = await cache.download(url, token);
    replacement = await new Promise<Sound>((resolve, reject) => {
      const value = new Sound(localPath, '', error => error ? reject(error) : resolve(value));
    });
    if (run !== variantSwitchRun || currentUrl !== oldUrl || audioContext !== existingContext) {
      replacement.release();
      return;
    }
    const before = await getAudioProgress();
    if (run !== variantSwitchRun || currentUrl !== oldUrl || audioContext !== existingContext) {
      replacement.release();
      return;
    }
    const normalizedProgress = before.duration > 0 ? Math.max(0, Math.min(1, before.position / before.duration)) : 0;
    const wasPlaying = before.playing;
    const wasPaused = before.paused;
    const wasStarted = Boolean(before.started);
    const speed = before.speed || 1;
    const old = current;
    const duration = replacement.getDuration();
    const position = Math.max(0, Math.min(duration, duration * normalizedProgress));
    replacement.setSpeed(speed);
    if (position) replacement.setCurrentTime(position);
    current = replacement;
    currentUrl = url;
    audioContext = { url, briefing, metadata };
    readyVoiceVariant = null;
    old?.pause();
    old?.release();
    contextListeners.forEach(listener => listener(audioContext));
    update({ position, duration, playing: false, paused: wasPaused || (!wasPlaying && wasStarted), ended: normalizedProgress >= 1,
      buffering: false, loaded: true, started: wasStarted, speed });
    NativeModules.NewziAudioCache?.savePosition?.(url, position);
    persistBriefingProgress(position, duration, true);
    if (wasPlaying && normalizedProgress < 1) {
      update({ playing: true, paused: false, ended: false, started: true });
      replacement.play(success => {
        if (current !== replacement) return;
        update({ playing: false, paused: !success, ended: success, started: false, position: success ? duration : state.position });
        if (success) persistBriefingProgress(duration, duration, true);
        if (success) NativeModules.NewziAudioCache?.savePosition?.(url, 0);
      });
    }
  } catch {
    replacement?.release();
    // Keep the old valid artifact and playback session if downloading/loading the variant fails.
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

export async function loadAudio(url: string) {
  if (!/^https?:\/\//i.test(url)) throw new Error('invalid audio URL');
  if (current && currentUrl === url) return;
  if (loadingUrl === url && loadingPromise) return loadingPromise;
  loadingUrl = url;
  update({ buffering: true });
  loadingPromise = (async () => {
    const token = await getFirebaseIdToken();
    if (!token) throw new Error('authentication required for audio');
    const cache = NativeModules.NewziAudioCache as { download: (url: string, token: string) => Promise<string> } | undefined;
    if (!cache?.download) throw new Error('native audio cache unavailable; rebuild the app');
    const localPath = await cache.download(url, token);
    const sound = await new Promise<Sound>((resolve, reject) => {
      const value = new Sound(localPath, '', error => error ? reject(error) : resolve(value));
    });
    if (currentUrl !== url) {
      current?.pause();
      current?.release();
      current = sound;
      currentUrl = url;
      audioContext = null;
      contextListeners.forEach(listener => listener(null));
      sound.setSpeed(state.speed || 1);
      const saved = await (NativeModules.NewziAudioCache as { getPosition?: (url: string) => Promise<number> })
        .getPosition?.(url).catch(() => 0) || 0;
      const position = saved < sound.getDuration() - 1 ? saved : 0;
      if (position) sound.setCurrentTime(position);
      update({ position, duration: sound.getDuration(), playing: false, paused: false,
        ended: false, buffering: false, loaded: true, started: false });
    } else {
      sound.release();
    }
  })();
  try { await loadingPromise; }
  catch (error) { update({ buffering: false, loaded: Boolean(current) }); throw error; }
  finally { loadingUrl = null; loadingPromise = null; }
}

export function playAudio(): Promise<void> {
  if (!current) return Promise.reject(new Error('audio not loaded'));
  const sound = current;
  if (state.ended) sound.setCurrentTime(0);
  update({ playing: true, paused: false, ended: false, started: true });
  sound.play(success => {
    if (current !== sound) return;
    update({ playing: false, paused: !success, ended: success,
      started: false, position: success ? state.duration : state.position });
    if (success) persistBriefingProgress(state.duration,state.duration,true);
    if (success && currentUrl) NativeModules.NewziAudioCache?.savePosition?.(currentUrl, 0);
  });
  return Promise.resolve();
}

export function pauseAudio() {
  current?.pause();
  update({ playing: false, paused: true });
  persistBriefingProgress(state.position,state.duration,true);
  if (currentUrl) NativeModules.NewziAudioCache?.savePosition?.(currentUrl, state.position);
}

/** Dismiss the mini player while keeping the same briefing and resume position. */
export async function dismissMiniAudio() {
  const progress=await getAudioProgress();
  current?.pause();
  update({ playing:false,paused:true,started:false,ended:false });
  await Promise.all([
    persistBriefingProgress(progress.position,progress.duration,true),
    currentUrl ? Promise.resolve(NativeModules.NewziAudioCache?.savePosition?.(currentUrl,progress.position)).catch(()=>undefined) : Promise.resolve(),
  ]);
}

export function setPlaybackSpeed(speed: number) {
  if (![0.75, 1, 1.25, 1.5, 2].includes(speed)) return;
  current?.setSpeed(speed);
  update({ speed });
}

export function seekTo(seconds: number) {
  if (!current) return;
  const position = Math.max(0, Math.min(seconds, state.duration || current.getDuration()));
  current.setCurrentTime(position);
  update({ position, ended: false });
  if (currentUrl) NativeModules.NewziAudioCache?.savePosition?.(currentUrl, position);
}

export async function seekAudio(offset: number) {
  const progress = await getAudioProgress();
  seekTo(progress.position + offset);
}

export function restartAudio() { seekTo(0); }

export function getAudioProgress(): Promise<PlaybackState> {
  if (!current) return Promise.resolve(state);
  return new Promise(resolve => current?.getCurrentTime(position => {
    update({ position, duration: current?.getDuration() || state.duration });
    persistBriefingProgress(position,current?.getDuration() || state.duration);
    if (currentUrl && Date.now() - lastSavedAt > 5000) {
      NativeModules.NewziAudioCache?.savePosition?.(currentUrl, position);
      lastSavedAt = Date.now();
    }
    resolve(state);
  }));
}

export const isPlaying = async () => state.playing;

export function releaseAudio() {
  current?.pause();
  current?.release();
  current = null;
  currentUrl = null;
  audioContext = null;
  lastProgressSyncAt = 0;
  contextListeners.forEach(listener => listener(null));
  update({ position: 0, duration: 0, playing: false, paused: false, ended: false, buffering: false, loaded: false, started: false, speed: 1 });
}

export function clearCachedAudio() {
  releaseAudio();
  NativeModules.NewziAudioCache?.clear?.();
}
