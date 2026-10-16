import { Platform } from 'react-native';
import DeviceInfo from 'react-native-device-info';
import { AuthorizationStatus, getInitialNotification, getMessaging, getToken, hasPermission, onMessage, onNotificationOpenedApp, onTokenRefresh, requestPermission, type RemoteMessage } from '@react-native-firebase/messaging';
import { api } from '../api/client';

export type PushPermissionState = 'AUTHORIZED' | 'PROVISIONAL' | 'DENIED' | 'NOT_DETERMINED';
export type ForegroundPush = { title: string; body: string; data: Record<string, string> };

export async function requestPushPermission(): Promise<PushPermissionState> {
  const status = await requestPermission(getMessaging());
  if (status === AuthorizationStatus.AUTHORIZED) return 'AUTHORIZED';
  if (status === AuthorizationStatus.PROVISIONAL) return 'PROVISIONAL';
  if (status === AuthorizationStatus.DENIED) return 'DENIED';
  return 'NOT_DETERMINED';
}

function deviceLocale() {
  try { return Intl.DateTimeFormat().resolvedOptions().locale || 'pt-BR'; } catch { return 'pt-BR'; }
}

export async function registerCurrentDevice() {
  const token = await getToken(getMessaging());
  return api.registerDevice({ platform: Platform.OS === 'ios' ? 'IOS' : 'ANDROID', push_token: token,
    app_version: `${DeviceInfo.getVersion()} (${DeviceInfo.getBuildNumber()})`, locale: deviceLocale(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
}

/** Keeps this install registered for the signed-in account (new phone, reinstall, another account), without asking again. */
export async function registerDeviceIfPermitted() {
  const status = await hasPermission(getMessaging());
  if (status === AuthorizationStatus.AUTHORIZED || status === AuthorizationStatus.PROVISIONAL) await registerCurrentDevice();
}

export async function requestAndRegisterDevice() {
  const permission = await requestPushPermission();
  if (permission !== 'AUTHORIZED' && permission !== 'PROVISIONAL') return { permission };
  return { permission, device: await registerCurrentDevice() };
}

/**
 * Taps on a notification (app in the background or closed) go to `onOpened`. A push that arrives
 * while the app is open is not shown by the system, so it goes to `onForeground` for an in-app notice.
 */
export function listenForPushEvents(onOpened: (data: Record<string, string>) => void, onForeground?: (push: ForegroundPush) => void) {
  const messagingInstance = getMessaging();
  const unsubscribeRefresh = onTokenRefresh(messagingInstance, () => { registerCurrentDevice().catch(() => undefined); });
  const unsubscribeOpened = onNotificationOpenedApp(messagingInstance, (message: RemoteMessage) => { if (message.data) onOpened(message.data as Record<string, string>); });
  const unsubscribeForeground = onMessage(messagingInstance, async (message: RemoteMessage) => {
    const title = message.notification?.title;
    if (title && onForeground) onForeground({ title, body: message.notification?.body || '', data: (message.data || {}) as Record<string, string> });
  });
  getInitialNotification(messagingInstance).then((message: RemoteMessage | null) => { if (message?.data) onOpened(message.data as Record<string, string>); }).catch(() => undefined);
  return () => { unsubscribeRefresh(); unsubscribeOpened(); unsubscribeForeground(); };
}
