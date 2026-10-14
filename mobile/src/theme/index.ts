import { StyleSheet, useColorScheme } from 'react-native';

// Semantic colors. The light values are the app's original colors; the dark ones follow the approved
// dark-mode proposal (navy, not black; every text/background pair at least 4.5:1).
export const lightColors = {
  /** A screen's own light color, kept exactly in light mode; in dark mode the given theme token is used. */
  tone: (light: string, _dark: string) => light,
  primary: '#087CF0', primaryDark: '#071A63', onPrimary: '#FFFFFF', background: '#F7FBFF', readerBackground: '#F5FAFF',
  surface: '#FFFFFF', surfaceBlue: '#EDF7FF', surfaceSoft: '#F2F8FD', surfaceTint: '#EAF3FC', placeholder: '#E6F0FA',
  border: '#D8EAF7', divider: '#E7EFF8', text: '#071A63', textPrimary: '#071A63', ink: '#071A42', body: '#354B70',
  secondary: '#55719A', textSecondary: '#55719A', muted: '#7F98B8', tabIdle: '#7183A2', accent: '#087CF0', newziBlue: '#69B7F4',
  inverse: '#102B57', onInverse: '#D7E7F7', borderStrong: '#BBD3E7', selected: '#D9EEFF',
  waveInactive: '#B9CBE3', track: '#DBE7F4', handle: '#D4DFEB', overlay: '#FFFFFFE8', scrim: 'rgba(7,26,66,.33)', coverTint: '#FFFFFF29',
  sun: '#E99113', danger: '#CF6570', dangerSurface: '#FFF0F2', success: '#138A62', successSurface: '#EAF8F2',
  warning: '#A86D12', warningSurface: '#FFF6E7', switchTrackOff: '#CBD7E7', switchTrackOn: '#9CC9FF', switchThumbOff: '#FFFFFF',
  topicBlue: { background: '#E8F3FF', icon: '#1674E8' }, topicPurple: { background: '#F1EAFE', icon: '#8953E9' },
  topicGreen: { background: '#E7F8EF', icon: '#16A568' }, topicOrange: { background: '#FFF4E4', icon: '#E99113' },
  topicRed: { background: '#FFECEF', icon: '#E64E66' }, topicTeal: { background: '#E6F6F8', icon: '#1595A7' },
  topicPink: { background: '#FCEAF1', icon: '#D84983' },
  shadow: { color: '#496B99', opacity: 0.1, radius: 12, offset: { width: 0, height: 4 } },
};

export type Palette = typeof lightColors;

export const darkColors: Palette = {
  tone: (_light: string, dark: string) => dark,
  primary: '#5AABFF', primaryDark: '#EAF1FB', onPrimary: '#04132B', background: '#0B1426', readerBackground: '#0B1426',
  surface: '#131F37', surfaceBlue: '#16294A', surfaceSoft: '#0F1A2F', surfaceTint: '#16233D', placeholder: '#1B2B47',
  border: '#24365A', divider: '#1E2E4C', text: '#EAF1FB', textPrimary: '#EAF1FB', ink: '#EAF1FB', body: '#C9D6EA',
  secondary: '#A6B8D4', textSecondary: '#A6B8D4', muted: '#8195B5', tabIdle: '#8195B5', accent: '#5AABFF', newziBlue: '#69B7F4',
  inverse: '#1E3A66', onInverse: '#D7E7F7', borderStrong: '#33497A', selected: '#1F3A66',
  waveInactive: '#2E4469', track: '#24365A', handle: '#2E4469', overlay: 'rgba(19,31,55,.9)', scrim: 'rgba(0,0,0,.55)', coverTint: '#FFFFFF29',
  sun: '#F4B65A', danger: '#F28B95', dangerSurface: '#3A1D24', success: '#45D19E', successSurface: '#123A2E',
  warning: '#F2B54B', warningSurface: '#3A2A10', switchTrackOff: '#2E4469', switchTrackOn: '#2F6FB3', switchThumbOff: '#A6B8D4',
  topicBlue: { background: '#132C4D', icon: '#7DBBFF' }, topicPurple: { background: '#2A2050', icon: '#B99AF5' },
  topicGreen: { background: '#123A2E', icon: '#5FD7A0' }, topicOrange: { background: '#3A2A10', icon: '#F4B65A' },
  topicRed: { background: '#41202A', icon: '#FF8FA2' }, topicTeal: { background: '#10353A', icon: '#5FD0DE' },
  topicPink: { background: '#3D1E31', icon: '#F28DB8' },
  shadow: { color: '#000000', opacity: 0.3, radius: 12, offset: { width: 0, height: 4 } },
};

/** Light palette, for screens not yet converted to the theme hooks below. */
export const colors = lightColors;

export type Theme = { colors: Palette; dark: boolean; statusBar: 'light-content' | 'dark-content' };
const lightTheme: Theme = { colors: lightColors, dark: false, statusBar: 'dark-content' };
const darkTheme: Theme = { colors: darkColors, dark: true, statusBar: 'light-content' };

/** The active theme: the system's, or the user's choice applied through Appearance (see appearance.ts). */
export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? darkTheme : lightTheme;
}

const styleCache = new WeakMap<object, Map<Palette, unknown>>();

/** Styles built from the active palette, computed once per palette however many components use them. */
export function useStyles<T>(factory: (colors: Palette) => T): T {
  const palette = useTheme().colors;
  let byPalette = styleCache.get(factory);
  if (!byPalette) { byPalette = new Map(); styleCache.set(factory, byPalette); }
  if (!byPalette.has(palette)) byPalette.set(palette, factory(palette));
  return byPalette.get(palette) as T;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32, huge: 40 };
export const radius = { sm: 10, md: 14, lg: 20, pill: 999 };
export const iconSize = { sm: 16, md: 20, lg: 24, xl: 28 };
export const typography = { display: 36, h1: 32, h2: 24, h3: 18, body: 16, bodySmall: 14, caption: 12, button: 16, lineHeight: 24, fontFamily: { ui: 'Inter', editorial: 'Newsreader' } };
export const elevation = { card: 1 };
/** Shared base styles (ui.tsx and simple screens), built per palette. */
export const makeBaseStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, screen: { flex: 1, backgroundColor: colors.background }, content: { paddingHorizontal: spacing.xxl, paddingTop: spacing.lg, paddingBottom: 48 }, centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  logo: { fontFamily: typography.fontFamily.ui, fontSize: 38, letterSpacing: -2.4, fontWeight: '800', color: colors.primaryDark, marginBottom: spacing.xxxl }, title: { fontFamily: typography.fontFamily.ui, fontSize: typography.h2, lineHeight: 30, fontWeight: '700', color: colors.textPrimary, marginBottom: spacing.sm }, editorial: { fontFamily: typography.fontFamily.editorial, fontSize: typography.display, lineHeight: 43, fontWeight: '500', color: colors.textPrimary }, subtitle: { fontFamily: typography.fontFamily.ui, fontSize: typography.body, lineHeight: 25, color: colors.secondary, marginBottom: spacing.xxl }, label: { fontFamily: typography.fontFamily.ui, fontSize: typography.caption, fontWeight: '800', letterSpacing: 1.2, color: colors.secondary, marginBottom: spacing.sm, marginTop: spacing.xxl, textTransform: 'uppercase' },
  input: { fontFamily: typography.fontFamily.ui, backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing.lg, fontSize: typography.body, color: colors.textPrimary, minHeight: 54 }, button: { backgroundColor: colors.primary, borderRadius: radius.md, paddingHorizontal: spacing.lg, minHeight: 54, alignItems: 'center', justifyContent: 'center', marginTop: spacing.lg }, buttonText: { fontFamily: typography.fontFamily.ui, color: colors.onPrimary, fontSize: typography.button, fontWeight: '700' }, secondaryButton: { borderColor: colors.borderStrong, borderWidth: 1, backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.lg, minHeight: 54, alignItems: 'center', justifyContent: 'center', marginTop: spacing.sm }, secondaryText: { fontFamily: typography.fontFamily.ui, color: colors.primary, fontSize: typography.button, fontWeight: '700' }, card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg, borderWidth: 1, borderColor: colors.border }, error: { fontFamily: typography.fontFamily.ui, color: colors.danger, marginTop: spacing.sm, lineHeight: 20 }, muted: { fontFamily: typography.fontFamily.ui, color: colors.secondary },
  chip: { borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingVertical: 11, paddingHorizontal: 15, marginRight: 8, marginBottom: 8, minHeight: 44 }, chipSelected: { backgroundColor: colors.selected, borderColor: colors.primary }, chipText: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontSize: 15 }, chipSelectedText: { fontFamily: typography.fontFamily.ui, color: colors.primaryDark, fontWeight: '700', fontSize: 15 }, nav: { flexDirection: 'row', borderTopWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 8, paddingTop: 8, paddingBottom: 10 }, navItem: { flex: 1, alignItems: 'center', padding: 8, minHeight: 60 }, navText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 12, fontWeight: '600' }, navActive: { color: colors.primary, fontWeight: '800' }, row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, badge: { color: colors.success, fontWeight: '800', fontSize: typography.caption }, skeleton: { height: 80, backgroundColor: colors.placeholder, borderRadius: radius.md, marginBottom: spacing.lg }, link: { fontFamily: typography.fontFamily.ui, color: colors.primary, fontWeight: '700', paddingVertical: 8, minHeight: 44 }, bullet: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, lineHeight: typography.lineHeight, marginBottom: 6 }, small: { fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, color: colors.secondary }
});

/** Light base styles, for code that runs outside components. */
export const styles = makeBaseStyles(lightColors);

export function useBaseStyles() {
  return useStyles(makeBaseStyles);
}
