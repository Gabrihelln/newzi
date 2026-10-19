import { api } from '../api/client';
import { getEntitlements, requestPremium } from '../services/premium';
import type { AudioMetadata, Briefing, BriefingItem } from '../types/api';
import { briefingArtwork, briefingAudioTitle, loadAudio, onPlaybackEnded, playAudio, setAudioContext } from './player';

/**
 * The listening queue (Premium): briefings, the saved stories narrated, a game's summary, one after the other like
 * a podcast. When the audio playing ends, the next entry starts on its own.
 */
export type QueueEntry = { key: string; kind: 'briefing' | 'saved' | 'match'; title: string; subtitle?: string; briefing?: Briefing; matchId?: number };

let queue: QueueEntry[] = [];
const listeners = new Set<(entries: QueueEntry[]) => void>();
const advanceListeners = new Set<(briefing: Briefing) => void>();

function publish(next: QueueEntry[]) {
  queue = next;
  listeners.forEach(listener => listener(queue));
}

export function getQueue() { return queue; }

export function subscribeQueue(listener: (entries: QueueEntry[]) => void) {
  listeners.add(listener); listener(queue);
  return () => { listeners.delete(listener); };
}

/** Told when the queue starts its next entry (the open player follows it). */
export function subscribeQueueAdvance(listener: (briefing: Briefing) => void) {
  advanceListeners.add(listener);
  return () => { advanceListeners.delete(listener); };
}

export const briefingEntry = (briefing: Briefing, title: string): QueueEntry => ({ key: `briefing:${briefing.delivery_id || briefing.id}`, kind: 'briefing', title, briefing });
export const savedEntry = (): QueueEntry => ({ key: 'saved', kind: 'saved', title: 'Suas matérias salvas', subtitle: 'As mais recentes que você ainda não leu' });
export const matchEntry = (matchId: number, title: string): QueueEntry => ({ key: `match:${matchId}`, kind: 'match', title: `Resumo do jogo: ${title}`, matchId });

/** Add to the end of the queue (Premium); an entry already queued is not added twice. */
export function addToQueue(entry: QueueEntry) {
  if (!getEntitlements()?.features.audio_queue) { requestPremium('audio_queue'); return false; }
  if (!queue.some(item => item.key === entry.key)) publish([...queue, entry]);
  return true;
}

export function removeFromQueue(key: string) { publish(queue.filter(item => item.key !== key)); }
export function clearQueue() { publish([]); }

/** A briefing-shaped wrapper for audio that is not a delivered briefing, so the player and mini player can show it. */
function externalBriefing(id: string, items: BriefingItem[] = []): Briefing {
  const now = new Date();
  return { id, date: now.toISOString().slice(0, 10), status: 'READY', generated_at: now.toISOString(), items };
}

export class AudioNotReady extends Error {}

/** Load and start one entry now. Saved stories and game summaries may still be narrating: AudioNotReady. */
export async function playEntry(entry: QueueEntry) {
  let url: string | undefined; let briefing: Briefing; let metadata: AudioMetadata; let title = entry.title; let artwork: string | undefined;
  if (entry.kind === 'briefing' && entry.briefing?.id) {
    briefing = entry.briefing;
    metadata = await api.audio(briefing.id!);
    url = metadata.status === 'READY' ? metadata.audio_url : undefined;
    title = briefingAudioTitle(briefing); artwork = briefingArtwork(briefing);
  } else if (entry.kind === 'saved') {
    const saved = await api.savedAudio(true);
    url = saved.status === 'READY' ? saved.audio_url : undefined;
    briefing = externalBriefing(`saved:${saved.edition_id || 'list'}`, (saved.stories || []).map((story, index) => ({ id: story.id, position: index + 1, headline: story.headline, summary: '', key_points: [], sources: [] })));
    metadata = { status: saved.status === 'READY' ? 'READY' : 'PENDING', audio_url: url, duration_ms: saved.duration_ms || undefined };
  } else if (entry.kind === 'match' && entry.matchId) {
    const match = await api.matchAudio(entry.matchId);
    url = match.status === 'READY' ? match.audio_url : undefined;
    briefing = externalBriefing(`match:${entry.matchId}`);
    metadata = { status: match.status === 'READY' ? 'READY' : 'PENDING', audio_url: url, duration_ms: match.duration_ms || undefined };
  } else return;
  if (!url) throw new AudioNotReady(entry.key);
  await loadAudio(url, title, artwork);
  setAudioContext(url, briefing, metadata);
  await playAudio();
  return briefing;
}

async function playNext() {
  while (queue.length) {
    const [next, ...rest] = queue;
    publish(rest);
    try {
      const briefing = await playEntry(next);
      if (briefing) advanceListeners.forEach(listener => listener(briefing));
      return;
    } catch { /* not ready or offline: try the following entry */ }
  }
}

onPlaybackEnded(() => { if (queue.length) void playNext(); });
