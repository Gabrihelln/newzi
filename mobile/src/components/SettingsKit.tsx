import React from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StatusBar, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { API_BASE_URL } from '../config/env';
import { radius, typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';

/**
 * Building blocks of the redesigned Profile screens (design/telas-perfil-explorar.html: Resumo diário,
 * Dados pessoais, Editar perfil): centered header, section headings, cards with icon boxes, segmented
 * buttons and the save bar pinned to the bottom that only shows when something changed.
 */
export function SettingsPage({ title, onBack, children, footer }: { title: string; onBack: () => void; children: React.ReactNode; footer?: React.ReactNode }) {
  const s = useStyles(makeStyles);
  const { colors, statusBar } = useTheme();
  return <SafeAreaView style={s.safe} edges={['top', 'bottom']}>
    <StatusBar barStyle={statusBar} backgroundColor={colors.background} />
    <View style={s.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} hitSlop={8} style={s.back}>
        <View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View>
      </Pressable>
      <Text accessibilityRole="header" numberOfLines={1} style={s.title}>{title}</Text>
      <View style={{ width: 42 }} />
    </View>
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">{children}</ScrollView>
    {footer}
  </SafeAreaView>;
}

export function SectionHeading({ title, subtitle, danger = false }: { title: string; subtitle?: string; danger?: boolean }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <View style={s.section}>
    <Text accessibilityRole="header" style={[s.sectionTitle, danger && { color: colors.danger }]}>{title}</Text>
    {!!subtitle && <Text style={s.sectionText}>{subtitle}</Text>}
  </View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: object }) {
  const s = useStyles(makeStyles);
  return <View style={[s.card, style]}>{children}</View>;
}

export type Tint = 'blue' | 'purple' | 'green' | 'orange' | 'red' | 'teal' | 'plain';
export function useTint(tint: Tint) {
  const { colors } = useTheme();
  return tint === 'plain' ? { background: colors.surface, icon: colors.secondary }
    : { blue: colors.topicBlue, purple: colors.topicPurple, green: colors.topicGreen, orange: colors.topicOrange, red: colors.topicRed, teal: colors.topicTeal }[tint];
}

export function IconBox({ icon, tint, size = 46 }: { icon: IconName; tint: Tint; size?: number }) {
  const { colors } = useTheme();
  const palette = useTint(tint);
  return <View style={{ width: size, height: size, borderRadius: size * .3, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.background,
    borderWidth: tint === 'plain' ? 1 : 0, borderColor: colors.border }}>
    <Icon name={icon} color={palette.icon} size={size * .46} />
  </View>;
}

export function Divider() {
  const s = useStyles(makeStyles);
  return <View style={s.divider} />;
}

export function Badge({ label, tint, icon }: { label: string; tint: 'green' | 'purple' | 'orange'; icon?: IconName }) {
  const s = useStyles(makeStyles);
  const palette = useTint(tint);
  return <View style={[s.badge, { backgroundColor: palette.background }]}>
    {icon && <Icon name={icon} color={palette.icon} size={14} />}
    <Text style={[s.badgeText, { color: palette.icon }]}>{label}</Text>
  </View>;
}

/** Segmented buttons: the chosen one is a raised white pill with blue text. */
export function Segmented<T extends string | number>({ options, value, onChange, label }: {
  options: { value: T; label: string; detail?: string }[]; value: T; onChange: (value: T) => void; label: string;
}) {
  const s = useStyles(makeStyles);
  return <View accessibilityRole="radiogroup" accessibilityLabel={label} style={s.segmented}>
    {options.map(option => {
      const on = option.value === value;
      return <Pressable key={String(option.value)} accessibilityRole="radio" accessibilityState={{ selected: on }} accessibilityLabel={option.detail ? `${option.label}, ${option.detail}` : option.label}
        onPress={() => onChange(option.value)} style={[s.segment, on && s.segmentOn]}>
        <Text numberOfLines={1} style={[s.segmentText, on && s.segmentTextOn]}>{option.label}</Text>
        {!!option.detail && <Text numberOfLines={1} style={[s.segmentDetail, on && s.segmentTextOn]}>{option.detail}</Text>}
      </Pressable>;
    })}
  </View>;
}

/** Pinned to the bottom, only while there are unsaved changes. */
export function SaveBar({ visible, busy, onSave, error }: { visible: boolean; busy: boolean; onSave: () => void; error?: string }) {
  const s = useStyles(makeStyles);
  if (!visible && !error) return null;
  return <View style={s.saveBar}>
    {!!error && <Text accessibilityRole="alert" style={s.saveError}>{error}</Text>}
    {visible && <>
      <View style={s.pending}><View style={s.pendingDot} /><Text style={s.pendingText}>Alterações não salvas</Text></View>
      <Pressable accessibilityRole="button" accessibilityState={{ busy, disabled: busy }} disabled={busy} onPress={onSave} style={({ pressed }) => [s.save, (pressed || busy) && { opacity: .85 }]}>
        {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={s.saveText}>Salvar alterações</Text>}
      </Pressable>
    </>}
  </View>;
}

/** Up to two initials of a name ("Ana Souza" → "AS"; a single name keeps its first letter). */
export function initials(name: string, max = 2) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? [words[0], words[words.length - 1]] : words).slice(0, max).map(word => word[0]?.toUpperCase() || '').join('') || 'N';
}

/** A server path (/api/v1/avatars/…) becomes a full URL; other URLs are kept. */
export const absolutePhotoUrl = (url?: string | null) => !url ? null : url.startsWith('/') ? `${API_BASE_URL}${url}` : url;

/** The profile photo, or the initials on a blue circle, with the camera badge that changes it. */
export function ProfileAvatar({ name, photo, size = 96, letters = 1, onCamera }: { name: string; photo?: string | null; size?: number; letters?: number; onCamera?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => setFailed(false), [photo]);
  const badge = size * .34;
  return <View style={{ width: size, height: size }}>
    <View style={[s.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      {photo && !failed ? <Image source={{ uri: photo }} onError={() => setFailed(true)} style={{ width: size, height: size }} />
        : <Text style={[s.avatarText, { fontSize: size * (letters > 1 ? .36 : .42) }]}>{initials(name, letters)}</Text>}
    </View>
    {onCamera && <Pressable accessibilityRole="button" accessibilityLabel="Trocar foto" onPress={onCamera} hitSlop={6}
      style={[s.cameraBadge, { width: badge, height: badge, borderRadius: badge / 2 }]}>
      <Icon name="camera" color={colors.primary} size={badge * .5} />
    </Pressable>}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { height: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14 },
  back: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800', color: colors.ink },
  content: { paddingHorizontal: 18, paddingTop: 8, paddingBottom: 28 },
  section: { marginTop: 22, marginBottom: 12 },
  sectionTitle: { fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800', color: colors.ink },
  sectionText: { fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 19, color: colors.secondary, marginTop: 3 },
  card: { backgroundColor: colors.surface, borderRadius: 22, borderWidth: 1, borderColor: colors.tone('#E8EFF8', colors.border), padding: 16,
    shadowColor: colors.shadow.color, shadowOpacity: colors.shadow.opacity * .7, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 1 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: 14 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 11, paddingVertical: 6, borderRadius: radius.pill },
  badgeText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, fontWeight: '700' },
  segmented: { flexDirection: 'row', padding: 4, borderRadius: 16, backgroundColor: colors.tone('#EDF2F8', colors.surfaceSoft), gap: 4 },
  segment: { flex: 1, minHeight: 46, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4, paddingVertical: 6 },
  segmentOn: { backgroundColor: colors.surface, shadowColor: colors.shadow.color, shadowOpacity: .14, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  segmentText: { fontFamily: typography.fontFamily.ui, fontSize: 14.5, fontWeight: '600', color: colors.secondary },
  segmentDetail: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.muted, marginTop: 1 },
  segmentTextOn: { color: colors.primary, fontWeight: '800' },
  saveBar: { paddingHorizontal: 18, paddingTop: 10, paddingBottom: 12, backgroundColor: colors.background },
  saveError: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.danger, textAlign: 'center', marginBottom: 8 },
  pending: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, marginBottom: 9 },
  pendingDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.sun },
  pendingText: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary },
  save: { minHeight: 54, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary,
    shadowColor: colors.primary, shadowOpacity: .25, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 3 },
  saveText: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.onPrimary },
  avatar: { overflow: 'hidden', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tone('#3F8CEB', colors.primary) },
  avatarText: { fontFamily: typography.fontFamily.ui, fontWeight: '800', color: '#FFFFFF' },
  cameraBadge: { position: 'absolute', right: 0, bottom: 2, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface,
    shadowColor: colors.shadow.color, shadowOpacity: .25, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
});
