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
