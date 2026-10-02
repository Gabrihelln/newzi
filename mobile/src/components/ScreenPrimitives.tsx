import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StatusBar, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, elevation, radius, spacing, typography } from '../theme';
import { Icon } from './Icon';

export function BrandPage({ children, contentStyle }: { children: React.ReactNode; contentStyle?: object }) {
  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <ScrollView contentContainerStyle={[s.content, contentStyle]} keyboardShouldPersistTaps="handled">{children}</ScrollView>
  </SafeAreaView>;
}

export function BrandPageHeader({ title, subtitle, onBack }: { title: string; subtitle?: string; onBack: () => void }) {
  return <View style={s.header}>
    <Pressable accessibilityRole="button" accessibilityLabel="Voltar" hitSlop={8} onPress={onBack} style={s.back}>
      <View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.textPrimary} size={21} /></View>
    </Pressable>
    <View style={s.headerCopy}>
      <Text accessibilityRole="header" style={s.title}>{title}</Text>
      {!!subtitle && <Text style={s.subtitle}>{subtitle}</Text>}
    </View>
  </View>;
}

export function SettingsCard({ children, style }: { children: React.ReactNode; style?: object }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>{title}</Text>{children}</View>;
}

export function ScreenState({ kind, title, message, onRetry }: {
  kind: 'loading' | 'empty' | 'error'; title: string; message?: string; onRetry?: () => void;
}) {
  return <View style={s.state}>
    {kind === 'loading' && <ActivityIndicator accessibilityLabel={title} color={colors.primary} size="large" />}
    {kind !== 'loading' && <Text accessibilityRole={kind === 'error' ? 'alert' : undefined} style={s.stateTitle}>{title}</Text>}
    {!!message && <Text style={s.stateMessage}>{message}</Text>}
    {kind === 'error' && onRetry && <Pressable accessibilityRole="button" onPress={onRetry} style={s.retry}>
      <Text style={s.retryText}>Tentar novamente</Text>
    </Pressable>}
  </View>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.xxxl },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.xl, minHeight: 56 },
  back: { width: 46, height: 46, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  headerCopy: { flex: 1, minWidth: 0 },
  title: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.h2, lineHeight: 30, fontWeight: '800' },
  subtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, lineHeight: 20, marginTop: spacing.xs },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius.lg, padding: spacing.lg, shadowColor: colors.shadow.color, shadowOpacity: colors.shadow.opacity, shadowRadius: colors.shadow.radius, shadowOffset: colors.shadow.offset, elevation: elevation.card },
  section: { gap: spacing.sm, marginBottom: spacing.lg },
  sectionTitle: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.h3, lineHeight: 24, fontWeight: '800', marginBottom: spacing.xs },
  state: { alignItems: 'center', justifyContent: 'center', gap: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.xxxl, minHeight: 180, backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius.lg },
  stateTitle: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.h3, lineHeight: 24, fontWeight: '800', textAlign: 'center' },
  stateMessage: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, lineHeight: 20, textAlign: 'center' },
  retry: { minHeight: 46, minWidth: 150, borderRadius: radius.pill, backgroundColor: colors.primary, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg },
  retryText: { color: colors.surface, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, fontWeight: '700' },
});
