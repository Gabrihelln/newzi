import React, { useEffect, useState } from 'react';
import { Alert, AppState } from 'react-native';
import { api, ClientError } from '../api/client';
import { PREMIUM_OFFERED } from '../config/store';
import { navigationRef } from '../navigation/notificationRouting';
import { PremiumSheet, type PremiumFeature } from '../components/PremiumSheet';
import type { Entitlements, PremiumFeatureId } from '../types/api';

/**
 * What the signed-in account may use (Newzi Premium), as the server decides it (GET /me/entitlements).
 * While the server does not enforce the limits (PREMIUM_ENFORCED off) every feature is open to everyone.
 *
 * A locked feature shows its Premium sheet only where Premium can be offered (PREMIUM_OFFERED; iOS too since
 * App Store purchases ship); elsewhere its entry points are simply hidden.
 */
let current: Entitlements | null = null;
const listeners = new Set<(value: Entitlements | null) => void>();
let loading: Promise<void> | null = null;

function publish(value: Entitlements | null) {
  current = value;
  listeners.forEach(listener => listener(value));
}

export function refreshEntitlements() {
  if (loading) return loading;
  loading = api.entitlements().then(publish).catch(() => undefined).finally(() => { loading = null; });
  return loading;
}

export function clearEntitlements() { publish(null); }

/** Keeps the entitlements fresh while the signed-in app runs (start, return to foreground). */
export function startEntitlementsMonitor() {
  void refreshEntitlements();
  const subscription = AppState.addEventListener('change', state => { if (state === 'active') void refreshEntitlements(); });
  return () => subscription.remove();
}

export function getEntitlements() { return current; }

export function useEntitlements() {
  const [value, setValue] = useState(current);
  useEffect(() => { listeners.add(setValue); setValue(current); return () => { listeners.delete(setValue); }; }, []);
  return value;
}

/** ``unlocked``: the account may use it; ``offered``: locked, but Premium can be offered here (show it with a badge). */
export function usePremiumFeature(feature: PremiumFeatureId) {
  const entitlements = useEntitlements();
  const unlocked = Boolean(entitlements?.features[feature]);
  return { unlocked, offered: Boolean(entitlements) && !unlocked && PREMIUM_OFFERED, visible: unlocked || (Boolean(entitlements) && PREMIUM_OFFERED), limits: entitlements?.limits };
}

// ---------------------------------------------------------------- the Premium sheet, from anywhere
let sheetListener: ((feature: PremiumFeature | null) => void) | null = null;

/** Show what Premium offers for ``feature`` (or nothing where Premium is not offered yet). */
export function requestPremium(feature: PremiumFeature) {
  if (!PREMIUM_OFFERED) {
    Alert.alert('Recurso indisponível', 'Este recurso não está disponível no seu plano.');
    return;
  }
  sheetListener?.(feature);
}

/** A PREMIUM_REQUIRED answer opens the feature's Premium sheet; returns whether it was one. */
export function handlePremiumError(error: unknown) {
  if (error instanceof ClientError && error.code === 'PREMIUM_REQUIRED') {
    void refreshEntitlements();
    requestPremium((error.feature as PremiumFeature) || 'extra_briefings');
    return true;
  }
  return false;
}

/** Rendered once in the signed-in app: the sheet ``requestPremium`` opens. */
export function PremiumHost() {
  const [feature, setFeature] = useState<PremiumFeature | null>(null);
  useEffect(() => { sheetListener = setFeature; return () => { sheetListener = null; }; }, []);
  if (!feature) return null;
  return <PremiumSheet feature={feature} visible onClose={() => setFeature(null)}
    onSeePlans={() => { if (navigationRef.isReady()) navigationRef.navigate('Subscription' as never); }} />;
}
