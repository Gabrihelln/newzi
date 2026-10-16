import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, SafeAreaView, Text, View } from 'react-native';
import { api, ClientError } from './src/api/client';
import { firebaseAuth, isAuthOperationInProgress, logoutFromFirebase, observeFirebaseUser } from './src/services/firebaseAuth';
import { clearCachedAudio } from './src/audio/player';
import { AudioEngine } from './src/audio/AudioEngine';
import { clearOfflineCache } from './src/services/offlineCache';
import { useBaseStyles, useTheme } from './src/theme';
import { applySavedThemePreference } from './src/theme/appearance';
import { RootNavigator, type RootAuthState } from './src/navigation/RootNavigator';
import type { User } from './src/types/api';
import { currentPushToken, listenForPushEvents, registerDeviceIfPermitted } from './src/push/push';
import { openFromNotification } from './src/navigation/notificationRouting';
import { showPushNotice } from './src/services/appNotices';
import { devLog } from './src/config/env';
import { getDeviceTimezone } from './src/config/timezone';

// The saved light/dark choice applies before the first screen renders.
applySavedThemePreference();

export default function App() {
  const theme = useTheme();
  const styles = useBaseStyles();
  const [authState, setAuthState] = useState<RootAuthState>('BOOTING');
  const [user, setUser] = useState<User | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [bootstrapError, setBootstrapError] = useState('');
  const bootstrappingUid = useRef<string | null>(null);
  const bootstrapTask = useRef<Promise<void> | null>(null);
  const timezoneSyncTask = useRef<Promise<void> | null>(null);

  const syncDeviceTimezone = useCallback(() => {
    if (timezoneSyncTask.current) return timezoneSyncTask.current;
    const task = (async () => {
      try {
        const preferences = await api.preferences();
        const timezone = getDeviceTimezone();
        if (preferences.timezone !== timezone) await api.savePreferences({ timezone });
      } catch {
        devLog('[Preferences] device-timezone-sync:failed');
      } finally {
        timezoneSyncTask.current = null;
      }
    })();
    timezoneSyncTask.current = task;
    return task;
  }, []);

  useEffect(() => {
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active' && firebaseAuth.currentUser) void syncDeviceTimezone();
    });
    return () => listener.remove();
  }, [syncDeviceTimezone]);

  useEffect(() => { try { return listenForPushEvents(openFromNotification, showPushNotice); } catch { return undefined; } }, []);

  const signedInUid = authState === 'AUTHENTICATED' ? user?.id : undefined;
  useEffect(() => {
    if (signedInUid) registerDeviceIfPermitted().catch(() => devLog('[Push] device-registration:failed'));
  }, [signedInUid]);

  const acceptSession = useCallback(async (nextUser: User) => {
    if (bootstrappingUid.current === nextUser.id && bootstrapTask.current) return bootstrapTask.current;
    bootstrappingUid.current = nextUser.id;
    setBootstrapError('');
    const task = (async () => { try {
      const profile = await api.me();
      const onboarding = await api.onboarding();
      await syncDeviceTimezone();
      setUser(profile);
      setNeedsOnboarding(onboarding.status !== 'COMPLETED');
      setAuthState('AUTHENTICATED');
      devLog('[Auth] bootstrap:complete');
      devLog(`[Auth] navigation:${onboarding.status === 'COMPLETED' ? 'Today' : 'Onboarding'}`);
    } catch (error) {
      bootstrappingUid.current = null;
      devLog(`[Auth] bootstrap:error=${error instanceof ClientError ? error.code : 'UNKNOWN'}`);
      setUser(null);
      setBootstrapError(error instanceof ClientError && error.code === 'AUTH_REQUIRED' ? 'Não foi possível validar sua sessão. Tente novamente ou entre na sua conta.' : 'Não foi possível carregar sua conta. Verifique sua internet e tente novamente.');
      setAuthState('UNAUTHENTICATED');
      throw error;
    } finally { bootstrapTask.current = null; } })();
    bootstrapTask.current = task;
    return task;
  }, [syncDeviceTimezone]);

  useEffect(() => observeFirebaseUser(async (firebaseUser) => {
    if (!firebaseUser) { setUser(null); setNeedsOnboarding(false); setBootstrapError(''); setAuthState('UNAUTHENTICATED'); return; }
    if (isAuthOperationInProgress()) { devLog('[Auth] observer:deferred'); return; }
    try {
      await acceptSession({ id: firebaseUser.uid, email: firebaseUser.email || '', display_name: firebaseUser.displayName || '', onboarding_status: 'NOT_STARTED' });
    } catch {
      setUser(null);
      setNeedsOnboarding(false);
      setAuthState('UNAUTHENTICATED');
    }
  }), [acceptSession]);

  const logout = useCallback(async () => {
    clearCachedAudio();
    clearOfflineCache();
    try { await api.logout(await currentPushToken()); } catch { /* local logout must always complete */ }
    await logoutFromFirebase().catch(() => undefined);
    bootstrappingUid.current = null;
    setUser(null);
    setNeedsOnboarding(false);
    setBootstrapError('');
    setAuthState('UNAUTHENTICATED');
  }, []);

  const retrySession = useCallback(async () => {
    const firebaseUser = firebaseAuth.currentUser;
    if (!firebaseUser) return;
    setAuthState('BOOTING');
    try { await acceptSession({ id: firebaseUser.uid, email: firebaseUser.email || '', display_name: firebaseUser.displayName || '', onboarding_status: 'NOT_STARTED' }); }
    catch { /* acceptSession exposes the recoverable error on the auth entry screen */ }
  }, [acceptSession]);

  if (authState === 'BOOTING') return <SafeAreaView style={styles.safe}><View style={styles.centered}><ActivityIndicator color={theme.colors.accent} /><Text style={styles.muted}>Carregando…</Text></View></SafeAreaView>;
  return <><AudioEngine /><RootNavigator authState={authState} needsOnboarding={needsOnboarding} user={user} bootstrapError={bootstrapError} onRetrySession={retrySession} onAuthenticated={acceptSession} onOnboardingDone={(nextUser) => { setUser(nextUser); setNeedsOnboarding(false); }} onLogout={logout} onAuthExpired={logout} onUserUpdated={setUser} /></>;
}
