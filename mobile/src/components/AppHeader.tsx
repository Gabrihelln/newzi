import React, { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, View } from 'react-native';
import { firebaseAuth } from '../services/firebaseAuth';
import { useStyles } from '../theme';
import { LOCKUP, useHeaderMarks } from './brand';
import { ProfileAvatar } from './SettingsKit';

/** Horizontal gutter of the four tab screens, so the header (and the content under it) sits in the same place on each. */
export const TAB_GUTTER = 18;

/**
 * The one header of Início, Explorar, Salvos and Perfil: the logo and the person's photo (or initials), at the
 * same size and position on every tab, so switching tabs never makes it jump. Search lives only in Explorar's field.
 * While a screen reloads (pull to refresh), the logo is the progress: the symbol turns and the name breathes.
 */
export function AppHeader({ onAvatar, refreshing = false }: { onAvatar: () => void; refreshing?: boolean }) {
  const s = useStyles(makeStyles);
  const user = firebaseAuth.currentUser;
  return <View style={s.header}>
    <Logo refreshing={refreshing} />
    <Pressable accessibilityRole="button" accessibilityLabel="Abrir dados pessoais" onPress={onAvatar} hitSlop={6}>
      <ProfileAvatar name={user?.displayName || user?.email || 'Newzi'} photo={user?.photoURL} size={42} letters={2} />
    </Pressable>
  </View>;
}

const LOGO_WIDTH = 126, LOGO_HEIGHT = 46;
const SCALE = Math.min(LOGO_WIDTH / LOCKUP.width, LOGO_HEIGHT / LOCKUP.height);
const TOP = (LOGO_HEIGHT - LOCKUP.height * SCALE) / 2;
const place = (part: { x: number; y: number; width: number; height: number }) =>
  ({ position: 'absolute' as const, left: part.x * SCALE, top: TOP + part.y * SCALE, width: part.width * SCALE, height: part.height * SCALE });
const TURN_MS = 900;

/** The lockup drawn as its two parts (looks exactly like the single image when still). */
function Logo({ refreshing }: { refreshing: boolean }) {
  const s = useStyles(makeStyles);
  const marks = useHeaderMarks();
  const turn = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!refreshing) return;
    turn.setValue(0);
    const loop = Animated.loop(Animated.timing(turn, { toValue: 1, duration: TURN_MS, easing: Easing.inOut(Easing.cubic), useNativeDriver: true }));
    loop.start();
    return () => {
      loop.stop();
      // Finish the turn under way instead of snapping back.
      turn.stopAnimation(value => Animated.timing(turn, { toValue: 1, duration: Math.max(150, (1 - value) * TURN_MS), easing: Easing.out(Easing.cubic), useNativeDriver: true })
        .start(() => turn.setValue(0)));
    };
  }, [refreshing, turn]);
  const rotate = turn.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const symbolScale = turn.interpolate({ inputRange: [0, .5, 1], outputRange: [1, .86, 1] });
  const wordOpacity = turn.interpolate({ inputRange: [0, .5, 1], outputRange: [1, .45, 1] });
  return <View accessible accessibilityRole="image" accessibilityLabel="NEWZI" accessibilityState={{ busy: refreshing }} style={s.logo}>
    <Animated.Image source={marks.symbol} resizeMode="stretch" style={[place(LOCKUP.symbol), { transform: [{ rotate }, { scale: symbolScale }] }]} />
    <Animated.Image source={marks.wordmark} resizeMode="stretch" style={[place(LOCKUP.wordmark), { opacity: wordOpacity }]} />
  </View>;
}

const makeStyles = () => StyleSheet.create({
  header: { height: 56, marginTop: 4, marginBottom: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  logo: { width: LOGO_WIDTH, height: LOGO_HEIGHT, marginLeft: -3 },
});
