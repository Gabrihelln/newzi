import { QueryClient } from '@tanstack/react-query';
import { persistQueryClient } from '@tanstack/react-query-persist-client';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { createMMKV } from 'react-native-mmkv';

// The last answer of each main read (home, history, saved items, briefings and their audio metadata)
// is kept on the device, so the app still opens with the latest briefing - and its downloaded audio -
// without a connection. Network first: saved data is only used when the backend cannot be reached.
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const storage = createMMKV({ id: 'newzi-offline-cache' });

export const queryClient = new QueryClient({
  defaultOptions: { queries: { gcTime: MAX_AGE_MS, staleTime: 0, retry: 0, networkMode: 'always' } },
});

const persister = createAsyncStoragePersister({
  storage: {
    getItem: key => storage.getString(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => { storage.remove(key); },
  },
  throttleTime: 2000,
});

// Bump `buster` when a cached response shape changes, so stale shapes are dropped on update.
const [, restored] = persistQueryClient({ queryClient, persister, maxAge: MAX_AGE_MS, buster: 'v1' });
const ready = restored.catch(() => undefined);

const CONNECTIVITY_ERRORS = new Set(['BACKEND_UNREACHABLE', 'TIMEOUT']);

/** Fetch fresh data, falling back to the saved copy when the network fails. */
export async function cachedRead<T>(key: readonly unknown[], fetcher: () => Promise<T>): Promise<T> {
  await ready;
  try {
    return await queryClient.fetchQuery({ queryKey: key, queryFn: fetcher, staleTime: 0 });
  } catch (error) {
    const code = (error as { code?: string } | null)?.code;
    const saved = code && CONNECTIVITY_ERRORS.has(code) ? queryClient.getQueryData<T>(key) : undefined;
    if (saved === undefined) throw error;
    return saved;
  }
}

/** Forget every saved answer, e.g. on logout, so another account never sees them. */
export function clearOfflineCache() {
  queryClient.clear();
  storage.clearAll();
}
