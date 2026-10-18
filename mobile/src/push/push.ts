import { Linking, PermissionsAndroid, Platform } from 'react-native';
import DeviceInfo from 'react-native-device-info';
import { AuthorizationStatus, getInitialNotification, getMessaging, getToken, hasPermission, onNotificationOpenedApp, onTokenRefresh, requestPermission, type RemoteMessage } from '@react-native-firebase/messaging';
import { api } from '../api/client';

export type PushPermissionState = 'AUTHORIZED' | 'PROVISIONAL' | 'DENIED' | 'NOT_DETERMINED';

export const isPushAllowed = (permission: PushPermissionState) => permission === 'AUTHORIZED' || permission === 'PROVISIONAL';

/** What the system allows today, without asking. On Android it reflects the app's notification switch (and, on 13+, the runtime permission). */
export async function checkPushPermission(): Promise<PushPermissionState> {
  const status = await hasPermission(getMessaging());
  if (status === AuthorizationStatus.AUTHORIZED) return 'AUTHORIZED';
  if (status === AuthorizationStatus.PROVISIONAL) return 'PROVISIONAL';
  if (status === AuthorizationStatus.DENIED) return 'DENIED';
  return 'NOT_DETERMINED';
}

/**
 * Shows the system prompt when the system still lets the app ask. Firebase's requestPermission never asks on
 * Android (it just answers "authorized"), so Android 13+ asks for POST_NOTIFICATIONS itself. When the prompt is
 * no longer allowed (refused for good on Android, refused once on iOS), the app's system settings open instead
 * and the caller re-checks when the app comes back to the foreground.
 */
export async function requestPushPermission(): Promise<PushPermissionState> {
  const current = await checkPushPermission();
  if (isPushAllowed(current)) return current;
  if (Platform.OS === 'android') {
    if (Number(Platform.Version) >= 33) {
      const result = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS);
      if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) await Linking.openSettings();
    } else {
      // Before Android 13 notifications are on unless the person switched them off in the settings.
      await Linking.openSettings();
    }
    return checkPushPermission();
  }
  if (current === 'DENIED') { await Linking.openSettings(); return current; }
  const status = await requestPermission(getMessaging());
  if (status === AuthorizationStatus.AUTHORIZED) return 'AUTHORIZED';
  if (status === AuthorizationStatus.PROVISIONAL) return 'PROVISIONAL';
  if (status === AuthorizationStatus.DENIED) return 'DENIED';
  return 'NOT_DETERMINED';
}

function deviceLocale() {
  try { return Intl.DateTimeFormat().resolvedOptions().locale || 'pt-BR'; } catch { return 'pt-BR'; }
}

let lastSync = '';

/**
 * Links this install to the signed-in account and tells the backend whether the system lets it show pushes.
 * A blocked phone stays linked but receives nothing until the permission comes back. Skips the request when
 * nothing changed since the last sync, so it can run on every return to the foreground.
 */
export async function syncCurrentDevice(permission?: PushPermissionState, force = false) {
  const state = permission || await checkPushPermission();
  const token = await getToken(getMessaging());
  const key = `${token}|${state}`;
  if (!force && key === lastSync) return null;
  const device = await api.registerDevice({ platform: Platform.OS === 'ios' ? 'IOS' : 'ANDROID', push_token: token, permission: state,
    device_identifier: await DeviceInfo.getUniqueId().catch(() => undefined),
    app_version: `${DeviceInfo.getVersion()} (${DeviceInfo.getBuildNumber()})`, locale: deviceLocale(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
  lastSync = key;
  return device;
}

/** Forget what was synced, so the next sign-in (maybe another account) registers this install again. */
export function resetDeviceSync() { lastSync = ''; }

/** This install's push token, sent on logout so only this phone stops receiving the account's pushes. */
export async function currentPushToken() {
  try { return await getToken(getMessaging()); } catch { return undefined; }
}

export async function requestAndRegisterDevice() {
  const permission = await requestPushPermission();
  const device = await syncCurrentDevice(permission, true).catch(() => null);
  return { permission, device };
}

/**
 * Taps on a notification (app in the background or closed) go to `onOpened`. A push that arrives while
 * the app is open is not shown by the system, and the app shows nothing for it either.
 */
export function listenForPushEvents(onOpened: (data: Record<string, string>) => void) {
  const messagingInstance = getMessaging();
  const unsubscribeRefresh = onTokenRefresh(messagingInstance, () => { syncCurrentDevice(undefined, true).catch(() => undefined); });
  const unsubscribeOpened = onNotificationOpenedApp(messagingInstance, (message: RemoteMessage) => { if (message.data) onOpened(message.data as Record<string, string>); });
  getInitialNotification(messagingInstance).then((message: RemoteMessage | null) => { if (message?.data) onOpened(message.data as Record<string, string>); }).catch(() => undefined);
  return () => { unsubscribeRefresh(); unsubscribeOpened(); };
}
