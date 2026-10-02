import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, SafeAreaView, Text, View } from 'react-native';
import { api, ClientError } from './src/api/client';
import { firebaseAuth, isAuthOperationInProgress, logoutFromFirebase, observeFirebaseUser } from './src/services/firebaseAuth';
import { clearCachedAudio } from './src/audio/player';
import { styles, colors } from './src/theme';
import { RootNavigator, type RootAuthState } from './src/navigation/RootNavigator';
import type { User } from './src/types/api';
import { listenForPushEvents } from './src/push/push';
import { devLog } from './src/config/env';
import { getDeviceTimezone } from './src/config/timezone';

export default function App() {
  const [authState, setAuthState] = useState<RootAuthState>('BOOTING');
  const [user, setUser] = useState<User | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [pendingBriefingId, setPendingBriefingId] = useState<string | undefined>();
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

  useEffect(() => { try { return listenForPushEvents(data => { if (data.type === 'DAILY_BRIEFING' && data.briefing_id) setPendingBriefingId(data.briefing_id); }); } catch { return undefined; } }, []);

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
      setBootstrapError(error instanceof ClientError && error.code === 'AUTH_REQUIRED' ? 'Não foi possível validar sua sessão. Tente novamente ou entre na sua conta.' : 'Não foi possível carregar sua conta. Verifique a conexão com o backend e tente novamente.');
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
    try { await api.logout(); } catch { /* local logout must always complete */ }
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

  if (authState === 'BOOTING') return <SafeAreaView style={styles.safe}><View style={styles.centered}><ActivityIndicator color={colors.accent} /><Text style={styles.muted}>Carregando…</Text></View></SafeAreaView>;
  return <RootNavigator authState={authState} needsOnboarding={needsOnboarding} user={user} pendingBriefingId={pendingBriefingId} bootstrapError={bootstrapError} onRetrySession={retrySession} onAuthenticated={acceptSession} onOnboardingDone={(nextUser) => { setUser(nextUser); setNeedsOnboarding(false); }} onLogout={logout} onAuthExpired={logout} onUserUpdated={setUser} />;
}
