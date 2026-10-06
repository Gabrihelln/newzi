import { AppState } from 'react-native';
import { useEffect, useState } from 'react';
import { api } from '../api/client';

const REFRESH_INTERVAL_MS = 60_000;
let updateTick = 0;
let latestRevision: number | null = null;
const listeners = new Set<(tick: number) => void>();

export function subscribeContentRevision(listener: (tick: number) => void) {
  listeners.add(listener);
  listener(updateTick);
  return () => { listeners.delete(listener); };
}

export function getContentRevisionTick() { return updateTick; }

/** Refresh every screen that follows content revisions (Home, Explore) after a local change such as new preferences. */
export function notifyContentChanged() {
  updateTick += 1;
  listeners.forEach(listener => listener(updateTick));
}

export function useContentRevisionTick() {
  const [tick,setTick]=useState(updateTick);
  useEffect(()=>subscribeContentRevision(setTick),[]);
  return tick;
}

export function startContentRevisionMonitor() {
  let active = true;
  let inFlight = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const check = async () => {
    if (!active || AppState.currentState !== 'active' || inFlight) return;
    inFlight = true;
    try {
      const state = await api.contentRevision();
      if (latestRevision === null) latestRevision = state.revision;
      else if (state.revision > latestRevision) {
        latestRevision = state.revision;
        updateTick += 1;
        listeners.forEach(listener => listener(updateTick));
      } else if (state.revision >= 0) latestRevision = state.revision;
    } catch { /* the next foreground or periodic check will retry */ }
    finally {
      inFlight = false;
      if (active && AppState.currentState === 'active') timer = setTimeout(check, REFRESH_INTERVAL_MS);
    }
  };
  const listener = AppState.addEventListener('change', state => {
    if (state === 'active') {
      if (timer) clearTimeout(timer);
      void check();
    } else if (timer) {
      clearTimeout(timer);
      timer = undefined;
    }
  });
  if (AppState.currentState === 'active') void check();
  return () => {
    active = false;
    if (timer) clearTimeout(timer);
    listener.remove();
  };
}
