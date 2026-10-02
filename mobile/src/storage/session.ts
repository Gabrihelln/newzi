import { secureStorage } from './secureStorage';

const SESSION_KEY = 'newzi_session_token';
export const sessionStorage = {
  get: () => secureStorage.getItem(SESSION_KEY),
  set: (token: string) => secureStorage.setItem(SESSION_KEY, token),
  clear: () => secureStorage.removeItem(SESSION_KEY),
};
