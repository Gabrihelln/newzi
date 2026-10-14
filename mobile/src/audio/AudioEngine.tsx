import React, { useSyncExternalStore } from 'react';
import Video from 'react-native-video';
import { attachEngine, getEngineSnapshot, onEngineBuffer, onEngineEnd, onEngineError, onEngineLoad, onEnginePlaybackStateChanged, onEngineProgress, subscribeEngine } from './player';

/**
 * The app's single native media player, mounted once at the root and driven by src/audio/player.ts.
 * It renders nothing visible; it exists so playback survives screen changes and the background.
 */
export function AudioEngine() {
  const { source, paused, rate } = useSyncExternalStore(subscribeEngine, getEngineSnapshot);
  if (!source) return null;
  const key = source.key;
  return <Video
    key={key}
    ref={attachEngine}
    source={{ uri: source.uri, headers: source.headers, metadata: { title: source.title, artist: 'Newzi' } }}
    paused={paused}
    rate={rate}
    playInBackground
    playWhenInactive
    ignoreSilentSwitch="ignore"
    showNotificationControls
    preventsDisplaySleepDuringVideoPlayback={false}
    progressUpdateInterval={500}
    onLoad={data => onEngineLoad(key, data)}
    onError={error => onEngineError(key, error)}
    onProgress={data => onEngineProgress(key, data)}
    onEnd={() => onEngineEnd(key)}
    onBuffer={data => onEngineBuffer(key, data)}
    onPlaybackStateChanged={data => onEnginePlaybackStateChanged(key, data)}
    style={{ position: 'absolute', width: 0, height: 0 }}
  />;
}
