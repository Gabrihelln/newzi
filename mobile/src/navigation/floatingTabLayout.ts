import { useEffect, useState } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { subscribeAudio, subscribeAudioContext } from '../audio/player';

const TAB_BAR_HEIGHT = 66;
// Card (94) + close-button overlap (13) + bottom margin (4).
const MINI_PLAYER_HEIGHT = 111;
const CONTENT_BREATHING_SPACE = 12;

export function useFloatingTabContentInset(showMiniPlayer: boolean) {
  const insets = useSafeAreaInsets();
  const [miniPlayerVisible, setMiniPlayerVisible] = useState(false);

  useEffect(() => {
    if (!showMiniPlayer) {
      setMiniPlayerVisible(false);
      return;
    }
    let hasContext = false;
    let hasStartedPlayback = false;
    const update = () => setMiniPlayerVisible(hasContext && hasStartedPlayback);
    const stopContext = subscribeAudioContext(context => { hasContext = Boolean(context); update(); });
    const stopPlayback = subscribeAudio(state => { hasStartedPlayback = state.loaded && Boolean(state.started); update(); });
    return () => { stopContext(); stopPlayback(); };
  }, [showMiniPlayer]);

  return TAB_BAR_HEIGHT + Math.max(insets.bottom, 8) + CONTENT_BREATHING_SPACE + (miniPlayerVisible ? MINI_PLAYER_HEIGHT : 0);
}
