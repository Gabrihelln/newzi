import { useTheme } from '../theme';

const lightLockup = require('../../assets/onboarding/newzi-lockup-reference.png');
// Same lockup with a light wordmark and a lighter icon square, for dark backgrounds.
const darkLockup = require('../../assets/onboarding/newzi-lockup-dark.png');

/** The Newzi logo that reads on the active theme's background. */
export function useLogo() {
  return useTheme().dark ? darkLockup : lightLockup;
}
