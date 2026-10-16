import { Platform } from 'react-native';

// App Review rejects a Premium offer that cannot be bought yet (guideline 2.1), so iOS shows
// Premium only once App Store purchases ship. Android keeps showing it.
export const PREMIUM_OFFERED = Platform.OS !== 'ios';

export const STORE_NAME = Platform.OS === 'ios' ? 'App Store' : 'Google Play';
