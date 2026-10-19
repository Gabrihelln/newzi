import React, { useEffect, useRef } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, StatusBar, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { useTheme } from '../theme';

/**
 * The app's opening screen (design/splash): the Newzi symbol appears, the name rises in under it, and the three
 * pages keep swaying like paper in a light breeze for as long as the account is loading (a slow connection just
 * means more sways). Backgrounds match the Android window colours (values/colors.xml), so nothing flashes.
 */
const SIZE = 132;
const UNIT = SIZE / 100;
const CYCLE_MS = 2600;
const INTRO_MS = CYCLE_MS * .26;
const easeInOut = Easing.bezier(.42, 0, .58, 1);

/** Keyframes like the design's CSS ([% of the cycle, rotate°, skewY°]), each step eased in and out. */
function sway(progress: Animated.Value, frames: [number, number, number][]) {
  const input: number[] = [frames[0][0] / 100];
  const rotate: string[] = [`${frames[0][1]}deg`];
  const skew: string[] = [`${frames[0][2]}deg`];
  for (let index = 1; index < frames.length; index++) {
    const [p0, r0, s0] = frames[index - 1], [p1, r1, s1] = frames[index];
    for (let step = 1; step <= 6; step++) {
      const eased = easeInOut(step / 6);
      input.push((p0 + (p1 - p0) * step / 6) / 100);
      rotate.push(`${r0 + (r1 - r0) * eased}deg`);
      skew.push(`${s0 + (s1 - s0) * eased}deg`);
    }
  }
  return [{ rotate: progress.interpolate({ inputRange: input, outputRange: rotate }) }, { skewY: progress.interpolate({ inputRange: input, outputRange: skew }) }];
}

// Each page turns around its bottom-left corner (in the design's 100×100 grid).
const PAGES = [
  { d: 'M24 83.5 L80 83.5 Q88 83.5 88 75.5 L88 41 Q88 35.5 82.5 36 L45 39.5 Z', fill: '#8DB4DF', origin: [24, 83.5],
    frames: [[0, 0, 0], [22, 0, 0], [38, -4, 1.2], [54, 2.8, -.7], [68, -1.5, 0], [80, .7, 0], [90, 0, 0], [100, 0, 0]] },
  { d: 'M22 83 L66.5 70.5 Q75 68 75 59 L75 31.5 Q75 26 69.5 27.2 L33 35 Z', fill: '#2167CC', origin: [22, 83],
    frames: [[0, 0, 0], [18, 0, 0], [34, -3.4, 1], [50, 2.3, -.6], [64, -1.3, 0], [76, .6, 0], [86, 0, 0], [100, 0, 0]] },
  { d: 'M17 38.5 Q17 33.5 21.8 31.8 L56.5 19 Q62 17 62 22.8 L62 56.5 Q62 63.6 55.4 66.5 L21.6 82.6 Q17 84.6 17 79.8 Z', fill: '#F7F8FA', origin: [17, 83.5],
    frames: [[0, 0, 0], [14, 0, 0], [30, -2.6, .8], [46, 1.8, -.5], [60, -1.1, 0], [72, .5, 0], [82, 0, 0], [100, 0, 0]] },
] as const;

export function SplashScreen() {
  const { dark } = useTheme();
  const cycle = useRef(new Animated.Value(0)).current;
  const intro = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    let loop: Animated.CompositeAnimation | undefined;
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().catch(() => false).then(reduce => {
      if (!active) return;
      if (reduce) { intro.setValue(1); return; }
      // The native driver interpolates linearly, so the opening's ease-out is on the timing itself.
      Animated.timing(intro, { toValue: 1, duration: INTRO_MS, easing: Easing.bezier(.22, .8, .3, 1), useNativeDriver: true }).start();
      loop = Animated.loop(Animated.timing(cycle, { toValue: 1, duration: CYCLE_MS, easing: Easing.linear, useNativeDriver: true }));
      loop.start();
    });
    return () => { active = false; loop?.stop(); };
  }, [cycle, intro]);

  const logoIn = intro.interpolate({ inputRange: [0, .54, 1], outputRange: [0, 1, 1] });
  const logoScale = intro.interpolate({ inputRange: [0, .54, 1], outputRange: [.9, 1, 1] });
  const nameIn = intro.interpolate({ inputRange: [0, .46, 1], outputRange: [0, 0, 1] });
  const nameRise = intro.interpolate({ inputRange: [0, .46, 1], outputRange: [6, 6, 0] });
  const background = dark ? '#0B1426' : '#F7FBFF';
  return <View accessible accessibilityRole="progressbar" accessibilityLabel="Carregando o Newzi" style={[styles.screen, { backgroundColor: background }]}>
    <StatusBar barStyle={dark ? 'light-content' : 'dark-content'} backgroundColor={background} />
    <Animated.View style={[styles.logo, { opacity: logoIn, transform: [{ scale: logoScale }] }]}>
      <View style={styles.inside}>
        {PAGES.map(page => <Animated.View key={page.fill} style={[styles.page, { transformOrigin: [page.origin[0] * UNIT, page.origin[1] * UNIT, 0], transform: sway(cycle, page.frames as unknown as [number, number, number][]) }]}>
          <Svg width={SIZE} height={SIZE} viewBox="0 0 100 100"><Path d={page.d} fill={page.fill} /></Svg>
        </Animated.View>)}
      </View>
    </Animated.View>
    <Animated.View style={{ opacity: nameIn, transform: [{ translateY: nameRise }] }}>
      <Image source={dark ? require('../../assets/splash/wordmark-dark.png') : require('../../assets/splash/wordmark-light.png')} resizeMode="contain" style={styles.name} />
    </Animated.View>
  </View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 26 },
  logo: { width: SIZE, height: SIZE, borderRadius: 23 * UNIT, backgroundColor: '#0F1D33' },
  // The design clips the pages to the inner rounded square (5 units in, radius 19).
  inside: { position: 'absolute', left: 5 * UNIT, top: 5 * UNIT, width: 90 * UNIT, height: 90 * UNIT, borderRadius: 19 * UNIT, overflow: 'hidden' },
  page: { position: 'absolute', left: -5 * UNIT, top: -5 * UNIT, width: SIZE, height: SIZE },
  name: { width: 140, height: 140 * 312 / 982 },
});
