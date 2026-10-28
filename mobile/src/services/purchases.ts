import { Platform } from 'react-native';
import Purchases, { PACKAGE_TYPE, PURCHASES_ERROR_CODE, type PurchasesPackage } from 'react-native-purchases';
import { api } from '../api/client';
import type { Subscription } from '../types/api';
import { refreshEntitlements } from './premium';

/**
 * Store purchases through RevenueCat (App Store now; Google Play once its key is set). RevenueCat knows each
 * reader by the backend user id, so its webhook finds the account; after a purchase or a restore the app asks the
 * server to read the plan at once (POST /me/subscription/sync), and the server stays the one that grants Premium.
 */
const API_KEYS: Partial<Record<typeof Platform.OS, string>> = {
  ios: 'appl_qGTdzaKLeUsNEaXNpitrpsRAjRk',   // public SDK key of the "Newzi iOS" App Store app
};
const KEY = API_KEYS[Platform.OS];
const ENTITLEMENT = 'premium';

export type StorePlan = { id: 'annual' | 'monthly'; price: string; perMonth: string | null; amount: number; pkg: PurchasesPackage };
export type PurchaseOutcome = { status: 'premium' | 'cancelled' | 'pending' | 'none'; subscription?: Subscription };

let configuredFor: string | null = null;

/** Whether this build can buy in the store at all. */
export const purchasesAvailable = Boolean(KEY);

/** Called once the reader is signed in: RevenueCat follows the backend account. */
export async function startPurchases(userId: string) {
  if (!KEY || !userId || configuredFor === userId) return;
  try {
    if (configuredFor === null) Purchases.configure({ apiKey: KEY, appUserID: userId });
    else await Purchases.logIn(userId);
    configuredFor = userId;
  } catch { /* the plan screen retries through ensureConfigured */ }
}

/** On logout: RevenueCat forgets the account, so the next one never sees its purchases. */
export async function stopPurchases() {
  if (!configuredFor) return;
  try { await Purchases.logOut(); } catch { /* already anonymous */ }
  configuredFor = null;
}

/** The plans on sale, with the price the store will charge in the reader's currency. */
export async function storePlans(): Promise<StorePlan[]> {
  if (!KEY || !configuredFor) return [];
  const offering = (await Purchases.getOfferings()).current;
  const plans: StorePlan[] = [];
  for (const pkg of offering?.availablePackages || []) {
    const id = pkg.packageType === PACKAGE_TYPE.ANNUAL ? 'annual' : pkg.packageType === PACKAGE_TYPE.MONTHLY ? 'monthly' : null;
    if (id) plans.push({ id, price: pkg.product.priceString, perMonth: pkg.product.pricePerMonthString, amount: pkg.product.price, pkg });
  }
  return plans;
}

async function settle(active: boolean): Promise<PurchaseOutcome> {
  const subscription = await api.syncSubscription().catch(() => undefined);
  void refreshEntitlements();
  // The store may approve later (Ask to Buy, a pending payment): the webhook makes the account Premium then.
  return { status: active || subscription?.tier === 'premium' ? 'premium' : 'pending', subscription };
}

/** Buy a plan. Throws on a store error; a purchase the reader backed out of is ``cancelled``. */
export async function buy(plan: StorePlan): Promise<PurchaseOutcome> {
  try {
    const { customerInfo } = await Purchases.purchasePackage(plan.pkg);
    return settle(Boolean(customerInfo.entitlements.active[ENTITLEMENT]));
  } catch (error) {
    const code = (error as { code?: string; userCancelled?: boolean | null }) || {};
    if (code.userCancelled || code.code === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR) return { status: 'cancelled' };
    throw error;
  }
}

/** "Restaurar compras": Premium bought earlier with this store account comes back. */
export async function restore(): Promise<PurchaseOutcome> {
  const info = await Purchases.restorePurchases();
  const outcome = await settle(Boolean(info.entitlements.active[ENTITLEMENT]));
  return outcome.status === 'premium' ? outcome : { ...outcome, status: 'none' };
}
