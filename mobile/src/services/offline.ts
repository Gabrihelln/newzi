import { Image, NativeModules } from 'react-native';
import { createMMKV } from 'react-native-mmkv';
import { api } from '../api/client';
import type { Briefing } from '../types/api';
import { getFirebaseIdToken } from './firebaseAuth';
import { getEntitlements, requestPremium } from './premium';

/**
 * Offline (Premium): download a briefing's audio ahead of time, and keep the saved stories (with their pictures)
 * and the saved briefings' audio on the phone. Every played briefing is already cached as it plays, for everyone;
 * this is choosing what to have before going offline (metro, plane).
 */
type AudioCache = { cachedPath?: (url: string) => Promise<string | null>; download?: (url: string, token: string) => Promise<string> };
const cache = (): AudioCache => (NativeModules.NewziAudioCache || {}) as AudioCache;
const storage = createMMKV({ id: 'newzi-offline-downloads' });
const SAVED_OFFLINE_KEY = 'saved-offline';

const allowed = () => {
  if (getEntitlements()?.features.offline_downloads) return true;
  requestPremium('offline_downloads');
  return false;
};

async function downloadUrl(url: string) {
  const token = await getFirebaseIdToken();
  if (!token || !cache().download) throw new Error('download unavailable');
  return cache().download!(url, token);
}

/** Whether this briefing's audio is on the phone. */
export async function isBriefingDownloaded(briefing: Briefing) {
  if (!briefing.id) return false;
  try {
    const audio = await api.audio(briefing.id);
    return Boolean(audio.audio_url && await cache().cachedPath?.(audio.audio_url).catch(() => null));
  } catch { return false; }
}

/** Download a briefing's audio (Premium). Resolves false when its audio is not ready yet. */
export async function downloadBriefing(briefing: Briefing) {
  if (!briefing.id || !allowed()) return false;
  const audio = await api.audio(briefing.id);
  if (audio.status !== 'READY' || !audio.audio_url) return false;
  await downloadUrl(audio.audio_url);
  return true;
}

export const savedOfflineEnabled = () => storage.getBoolean(SAVED_OFFLINE_KEY) === true;

/**
 * Keep the saved stories readable offline: every page of them is read once (the offline cache keeps the answers),
 * their pictures are fetched, and the saved briefings' audio is downloaded. Run when turned on and when the
 * Salvos tab opens while it is on.
 */
export async function syncSavedOffline(force = false) {
  if (!force && !savedOfflineEnabled()) return { stories: 0, briefings: 0 };
  if (!getEntitlements()?.features.offline_downloads) return { stories: 0, briefings: 0 };
  let stories = 0; let briefings = 0; let cursor: string | undefined;
  const pictures: string[] = [];
  for (let page = 0; page < 10; page++) {
    const result = await api.savedStoriesPage(40, cursor);
    stories += result.items.length;
    result.items.forEach(item => { if (item.image_url) pictures.push(item.image_url); });
    if (!result.next_cursor) break;
    cursor = result.next_cursor;
  }
  await Promise.all(pictures.slice(0, 200).map(url => Image.prefetch(url).catch(() => false)));
  await api.savedOverview().catch(() => undefined);
  const saved = await api.savedBriefings().catch(() => ({ items: [] as Briefing[] }));
  for (const briefing of saved.items.slice(0, 20)) {
    try { if (await downloadBriefing(briefing)) briefings++; } catch { /* the next sync retries */ }
  }
  return { stories, briefings };
}

export async function setSavedOffline(enabled: boolean) {
  if (enabled && !allowed()) return false;
  storage.set(SAVED_OFFLINE_KEY, enabled);
  if (enabled) await syncSavedOffline(true);
  return enabled;
}
