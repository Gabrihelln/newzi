import { Platform } from 'react-native';

// Premium is offered on both platforms. iOS shows it since App Store purchases ship (RevenueCat,
// services/purchases.ts): App Review rejects an offer that cannot be bought (guideline 2.1), so turn
// BILLING_ENABLED on in the server before sending a build for review.
export const PREMIUM_OFFERED = true;

export const STORE_NAME = Platform.OS === 'ios' ? 'App Store' : 'Google Play';
