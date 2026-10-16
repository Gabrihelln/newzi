import React from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { darkColors as darkPaletteMarker, useStyles, useTheme, type Palette } from '../theme';
import { useBrandMarks, useLogo } from './brand';
import { Icon } from './Icon';

// The lockup PNGs carry empty margins: the drawing spans 1490×422 of their 2103×748 pixels.
const LOCKUP = { width: 2103, height: 748, inkWidth: 1490, inkHeight: 422 };

/** The horizontal logo, sized by the height of the drawing itself (not of the padded PNG). */
export function Lockup({ height, style }: { height: number; style?: object }) {
  const scale = height / LOCKUP.inkHeight;
  const imageHeight = LOCKUP.height * scale, imageWidth = LOCKUP.width * scale;
  return <View style={[{ height, width: LOCKUP.inkWidth * scale, alignSelf: 'center', alignItems: 'center', justifyContent: 'center' }, style]}>
    <Image source={useLogo()} resizeMode="contain" accessibilityLabel="newzi" style={{ width: imageWidth, height: imageHeight }} />
  </View>;
}

/** The stacked logo: the large symbol over the "newzi" wordmark, on soft rings; `badge` adds a ✓ seal. */
export function BrandStack({ size = 132, badge = false }: { size?: number; badge?: boolean }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const marks = useBrandMarks();
  const ring = size / 132;
  const rings = [530, 410, 300, 200];
  return <View style={s.stack} accessible accessibilityLabel={badge ? 'newzi, configuração concluída' : 'newzi'}>
    <View pointerEvents="none" style={[s.rings, { top: size * .5 }]}>
      {rings.map((diameter, index) => <View key={diameter} style={[s.ring, index === 3 && s.ringInner, index === 0 && s.ringOuter, index === 1 && s.ringThird,
        { width: diameter * ring, height: diameter * ring, borderRadius: diameter * ring / 2, left: -diameter * ring / 2, top: -diameter * ring / 2 }]} />)}
    </View>
    <View style={[s.symbolShadow, { width: size, height: size * 429 / 447, borderRadius: size * .27 }]}>
      <Image source={marks.symbol} resizeMode="contain" style={{ width: size, height: size * 429 / 447 }} />
      {badge && <View style={s.badge}><Icon name="check" color={colors.tone('#FFFFFF', colors.onPrimary)} size={20} /></View>}
    </View>
    <Image source={marks.wordmark} resizeMode="contain" style={{ height: size * 60 / 132, width: size * 60 / 132 * 982 / 312, marginTop: size / 6 }} />
  </View>;
}

/** Two soft tinted circles behind the content, top-left and bottom-right. */
export function Glows() {
  const s = useStyles(makeStyles);
  return <><View pointerEvents="none" style={s.glowTop} /><View pointerEvents="none" style={s.glowBottom} /></>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  stack: { alignItems: 'center' },
  // A zero-size anchor: the stack's alignItems centers it horizontally; each ring is offset by half its size.
  rings: { position: 'absolute', alignSelf: 'center', width: 0, height: 0 },
  ring: { position: 'absolute', borderWidth: 1, borderColor: colors.tone('#DCE9F7', colors.border) },
  ringInner: { backgroundColor: colors.tone('#EEF5FD', colors.surfaceTint), borderColor: colors.tone('#E2EEFA', colors.border) },
  ringThird: { borderColor: colors.tone('#E6EFF9', colors.divider) },
  ringOuter: { borderColor: colors.tone('#EBF2FA', colors.divider) },
  // iOS only: an Android elevation shadow would follow a box, not the symbol's own rounded square.
  symbolShadow: { shadowColor: '#0F1E33', shadowOpacity: colors === darkPaletteMarker ? .5 : .22, shadowRadius: 13, shadowOffset: { width: 0, height: 18 } },
  badge: { position: 'absolute', right: -8, bottom: -8, width: 40, height: 40, borderRadius: 20, backgroundColor: colors.tone('#16A568', colors.success), borderWidth: 4, borderColor: colors.background, alignItems: 'center', justifyContent: 'center' },
  glowTop: { position: 'absolute', width: 300, height: 300, borderRadius: 150, top: -150, left: -110, opacity: .7, backgroundColor: colors.surfaceTint },
  glowBottom: { position: 'absolute', width: 420, height: 420, borderRadius: 210, bottom: -230, right: -170, opacity: .75, backgroundColor: colors.surfaceTint },
});
