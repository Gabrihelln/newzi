import { Appearance } from 'react-native';
import { createMMKV } from 'react-native-mmkv';

/** 'system' follows the phone; 'light' and 'dark' are the user's choice in Perfil › Aparência. */
export type ThemePreference = 'system' | 'light' | 'dark';

const storage = createMMKV({ id: 'newzi-settings' });
const KEY = 'theme-preference';

export function getThemePreference(): ThemePreference {
  const saved = storage.getString(KEY);
  return saved === 'light' || saved === 'dark' ? saved : 'system';
}

/**
 * Appearance.setColorScheme makes useColorScheme() - and Android's native DayNight resources -
 * report the chosen scheme, so every themed screen and the system bars follow it.
 */
function apply(preference: ThemePreference) {
  Appearance.setColorScheme(preference === 'system' ? 'unspecified' : preference);
}

export function setThemePreference(preference: ThemePreference) {
  storage.set(KEY, preference);
  apply(preference);
}

/** Apply the saved choice before the first screen renders. */
export function applySavedThemePreference() {
  apply(getThemePreference());
}
