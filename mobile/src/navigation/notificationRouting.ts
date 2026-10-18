import { Linking } from 'react-native';
import { createNavigationContainerRef } from '@react-navigation/native';

/** Root navigation handle, so a tapped push can open its screen from outside React components. */
export const navigationRef = createNavigationContainerRef<any>();

export type PushData = Record<string, string>;

let pending: PushData | null = null;
let mainFlowReady = false;

// Screens a Firebase-console push (announcement or promotion) may open with the custom data key `screen`.
const OPENABLE_SCREENS = new Set(['Subscription', 'NotificationSettings', 'ContentPreferences', 'DailyBriefing', 'Football', 'History']);

function target(data: PushData): [string, object] | null {
  if (data.type === 'DAILY_BRIEFING' && data.briefing_id) return ['AudioExpanded', { briefingId: data.briefing_id }];
  // Breaking news, and any console push carrying `story_id`, opens that story.
  if (data.story_id) return ['Detail', { storyId: data.story_id }];
  if (data.screen && OPENABLE_SCREENS.has(data.screen)) return [data.screen, {}];
  // Team game alerts (kickoff, goal, final) open Esportes; team news carries a story_id (above).
  if (data.type?.startsWith('TEAM_')) return ['Football', {}];
  return null;
}

/** Open the screen a notification points to now, or as soon as the signed-in app is on screen. */
export function openFromNotification(data: PushData) {
  if (data.url && /^https:\/\//i.test(data.url) && !target(data)) { Linking.openURL(data.url).catch(() => undefined); return; }
  const destination = target(data);
  if (!destination) return;
  if (!mainFlowReady || !navigationRef.isReady()) { pending = data; return; }
  pending = null;
  navigationRef.navigate(...destination);
}

/** Called by the signed-in stack when it mounts (true) and unmounts (false). */
export function setMainFlowReady(ready: boolean) {
  mainFlowReady = ready;
  if (ready && pending) {
    const data = pending;
    // Let the navigator finish its first render before pushing a screen on top of it.
    setTimeout(() => openFromNotification(data), 0);
  }
}
