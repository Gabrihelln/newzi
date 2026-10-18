import { getMessaging, subscribeToTopic } from '@react-native-firebase/messaging';

/**
 * Announcements ("Novidades do Newzi") and promotions ("Ofertas e promoções") are sent from the Firebase console
 * to these FCM topics, not by the backend. They have no switch in the app: every install joins both, and only the
 * phone's own notification permission (and each Android channel) decides whether they show.
 */
export const PUSH_TOPICS = ['novidades', 'promocoes'] as const;

/** Join both topics, once per launch; joining again is harmless and covers new installs and token changes. */
export async function joinPushTopics() {
  const messaging = getMessaging();
  await Promise.all(PUSH_TOPICS.map(topic => subscribeToTopic(messaging, topic)));
}
