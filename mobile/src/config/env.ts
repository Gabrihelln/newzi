import { Platform } from 'react-native';
import { DEV_API_URL } from './devApi';

export type AppEnvironment = 'development' | 'staging' | 'production';

const runtimeConfig = globalThis as typeof globalThis & {
  __NEWS_ENGINE_ENV__?: AppEnvironment;
  __NEWS_ENGINE_API_URL__?: string;
};
const configuredEnvironment = runtimeConfig.__NEWS_ENGINE_ENV__;
const environment: AppEnvironment = configuredEnvironment || (__DEV__ ? 'development' : 'production');
const configuredApiUrl = runtimeConfig.__NEWS_ENGINE_API_URL__?.trim() || (environment === 'development' ? DEV_API_URL.trim() : '');
const hosts: Record<AppEnvironment, string> = {
  development: Platform.OS === 'android' ? 'http://10.0.2.2:8090' : 'http://localhost:8090',
  staging: 'https://staging-api.news-engine.example.com',
  production: 'https://api.news-engine.example.com',
};

// One native-RN boundary. Physical devices can override this at build time
// through a generated native config in a future environment-specific target.
export const APP_ENV: AppEnvironment = environment;
export const API_BASE_URL = configuredApiUrl || hosts[APP_ENV];

if (APP_ENV === 'production' && (!API_BASE_URL || /localhost|127\.0\.0\.1|10\.0\.2\.2|example\.com/i.test(API_BASE_URL))) {
  throw new Error('Production mobile builds require a configured non-local API_BASE_URL');
}

export const LOGGING_ENABLED = APP_ENV !== 'production';

export function devLog(message: string) {
  if (LOGGING_ENABLED) console.log(message);
}

if (LOGGING_ENABLED) devLog(`[Newzi] API_BASE_URL=${API_BASE_URL}`);

// Development-only QA credentials. They are intentionally local defaults, not production secrets.
