import type { ForegroundPush } from '../push/push';

/** App-wide notices shown on top of every signed-in screen (see components/AppNotices). */
export type AppNoticeState = { push: ForegroundPush | null; offline: boolean };

let notices: AppNoticeState = { push: null, offline: false };
const listeners = new Set<(state: AppNoticeState) => void>();

function set(patch: Partial<AppNoticeState>) {
  notices = { ...notices, ...patch };
  listeners.forEach(listener => listener(notices));
}

export function subscribeAppNotices(listener: (state: AppNoticeState) => void) {
  listeners.add(listener);
  listener(notices);
  return () => { listeners.delete(listener); };
}

export function showPushNotice(push: ForegroundPush) { set({ push }); }
export function dismissPushNotice() { set({ push: null }); }

/** True while screens show saved data because the backend cannot be reached. */
export function setOffline(offline: boolean) { if (notices.offline !== offline) set({ offline }); }
