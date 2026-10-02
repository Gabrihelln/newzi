import { Platform } from 'react-native';
import { AuthorizationStatus, getInitialNotification, getMessaging, getToken, onNotificationOpenedApp, onTokenRefresh, requestPermission, type RemoteMessage } from '@react-native-firebase/messaging';
import { api } from '../api/client';

export type PushPermissionState = 'AUTHORIZED' | 'PROVISIONAL' | 'DENIED' | 'NOT_DETERMINED';

export async function requestPushPermission(): Promise<PushPermissionState> {
  const status = await requestPermission(getMessaging());
  if (status === AuthorizationStatus.AUTHORIZED) return 'AUTHORIZED';
  if (status === AuthorizationStatus.PROVISIONAL) return 'PROVISIONAL';
  if (status === AuthorizationStatus.DENIED) return 'DENIED';
  return 'NOT_DETERMINED';
}

export async function registerCurrentDevice() {
  const token = await getToken(getMessaging());
  return api.registerDevice({ platform: Platform.OS === 'ios' ? 'IOS' : 'ANDROID', push_token: token, app_version: '1.0.0', locale: 'pt-BR', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
}

export async function requestAndRegisterDevice() {
  const permission = await requestPushPermission();
  if (permission !== 'AUTHORIZED' && permission !== 'PROVISIONAL') return { permission };
  return { permission, device: await registerCurrentDevice() };
}

export function listenForPushEvents(onOpened: (data: Record<string, string>) => void) {
  const messagingInstance = getMessaging();
  const unsubscribeRefresh = onTokenRefresh(messagingInstance, () => { registerCurrentDevice().catch(() => undefined); });
  const unsubscribeOpened = onNotificationOpenedApp(messagingInstance, (message: RemoteMessage) => { if (message.data) onOpened(message.data as Record<string, string>); });
  getInitialNotification(messagingInstance).then((message: RemoteMessage | null) => { if (message?.data) onOpened(message.data as Record<string, string>); }).catch(() => undefined);
  return () => { unsubscribeRefresh(); unsubscribeOpened(); };
}
