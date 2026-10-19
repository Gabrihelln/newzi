import { useTheme } from '../theme';

const lightLockup = require('../../assets/onboarding/newzi-lockup-reference.png');
// Same lockup with a light wordmark and a lighter icon square, for dark backgrounds.
const darkLockup = require('../../assets/onboarding/newzi-lockup-dark.png');
// The lockup's symbol and wordmark on their own, cut from the PNGs above, for the stacked logo.
const lightMarks = { symbol: require('../../assets/onboarding/newzi-symbol.png'), wordmark: require('../../assets/onboarding/newzi-wordmark.png') };
const darkMarks = { symbol: require('../../assets/onboarding/newzi-symbol-dark.png'), wordmark: require('../../assets/onboarding/newzi-wordmark-dark.png') };

/** The Newzi logo that reads on the active theme's background. */
export function useLogo() {
  return useTheme().dark ? darkLockup : lightLockup;
}

/** The symbol and the "newzi" wordmark, for the stacked logo, in the active theme's version. */
export function useBrandMarks() {
  return useTheme().dark ? darkMarks : lightMarks;
}

// The header lockup's symbol and wordmark cut from the PNGs above (same pixels), so they can move on their own.
const lightHeader = { symbol: require('../../assets/onboarding/header-symbol.png'), wordmark: require('../../assets/onboarding/header-wordmark.png') };
const darkHeader = { symbol: require('../../assets/onboarding/header-symbol-dark.png'), wordmark: require('../../assets/onboarding/header-wordmark-dark.png') };

/** Where each part sits in the 2103×748 lockup, in its pixels. */
export const LOCKUP = { width: 2103, height: 748, symbol: { x: 208, y: 173, width: 581, height: 459 }, wordmark: { x: 838, y: 164, width: 1076, height: 430 } };

/** The header's symbol and wordmark in the active theme's version. */
export function useHeaderMarks() {
  return useTheme().dark ? darkHeader : lightHeader;
}
