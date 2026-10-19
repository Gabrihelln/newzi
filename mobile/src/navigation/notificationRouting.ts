import { Linking } from 'react-native';
import { PREMIUM_OFFERED } from '../config/store';
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
  // A final result with a narrated summary (Premium) opens Esportes with the summary ready to play.
  if (data.type === 'TEAM_FINAL' && data.match_audio && Number(data.match_id)) return ['Football', { matchAudio: Number(data.match_id) }];
  // Team game alerts (reminder, kickoff, goal, final) open Esportes; team news carries a story_id (above).
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

/**
 * Links from the iPhone widgets and Live Activities: newzi://story/ID opens the story, newzi://briefing the Home,
 * newzi://football Esportes and newzi://premium the plans (where Premium is offered).
 */
export function openDeepLink(url: string | null) {
  const match = /^newzi:\/\/([^/?#]+)(?:\/([^?#]+))?/i.exec(url || '');
  if (!match) return;
  const [, kind, value] = match;
  if (kind === 'story' && value) openFromNotification({ story_id: decodeURIComponent(value) });
  else if (kind === 'football') openFromNotification({ screen: 'Football' });
  else if (kind === 'premium' && PREMIUM_OFFERED) openFromNotification({ screen: 'Subscription' });
  else if (kind === 'briefing' && navigationRef.isReady()) navigationRef.navigate('Tabs', { screen: 'Inicio' });
}

/** Started by the signed-in app: the link that opened it, and the ones that arrive while it runs. */
export function listenForDeepLinks() {
  Linking.getInitialURL().then(openDeepLink).catch(() => undefined);
  const subscription = Linking.addEventListener('url', event => openDeepLink(event.url));
  return () => subscription.remove();
}
