import React from 'react';
import { ActivityIndicator, Platform, StyleSheet, Switch, Text, View } from 'react-native';
import type { NotificationSettings, NotificationSwitches } from '../types/api';
import { radius, spacing, typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';

export const platformName = Platform.OS === 'ios' ? 'iPhone' : 'Android';

/**
 * The one switch used by every notification control, so the four states read the same on Android and iOS:
 * on, off, inactive (its kind is kept but paused by the main switch: shown off and faded) and busy (saving).
 * iOS ignores the "false" track color, so the off track also goes through `ios_backgroundColor`.
 */
export function SettingSwitch({ value, onChange, label, inactive = false, busy = false, disabled = false }: {
  value: boolean; onChange: (value: boolean) => void; label: string; inactive?: boolean; busy?: boolean; disabled?: boolean;
}) {
  const { colors } = useTheme();
  const on = value && !inactive;
  const locked = inactive || busy || disabled;
  return <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
    {busy && <ActivityIndicator size="small" color={colors.primary} accessibilityLabel="Salvando" />}
    <Switch accessibilityLabel={label} accessibilityState={{ checked: on, disabled: locked, busy }} disabled={locked} value={on} onValueChange={onChange}
      trackColor={{ false: colors.switchTrackOff, true: colors.switchTrackOn }} ios_backgroundColor={colors.switchTrackOff}
      thumbColor={on ? colors.primary : colors.switchThumbOff} style={{ opacity: inactive ? .55 : 1 }} />
  </View>;
}

export type NoticeKind = 'all' | 'daily' | 'breaking';
const noticeIcons: Record<NoticeKind, { icon: IconName; tint: (c: Palette) => { background: string; icon: string } }> = {
  all: { icon: 'bell', tint: c => c.topicBlue },
  daily: { icon: 'sun', tint: c => c.topicOrange },
  breaking: { icon: 'bolt', tint: c => c.topicRed },
};

/** One notice: its icon in the notice's color, title, explanation, optional rule chips and its switch. */
export function NoticeRow({ kind, title, description, chips = [], value, onChange, label, inactive = false, busy = false, last = false }: {
  kind: NoticeKind; title: string; description: React.ReactNode; chips?: { icon: IconName; label: string }[];
  value: boolean; onChange: (value: boolean) => void; label: string; inactive?: boolean; busy?: boolean; last?: boolean;
}) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const tint = noticeIcons[kind].tint(colors);
  return <View style={[s.row, !last && s.rowDivider]}>
    <View style={[s.rowBody, inactive && s.faded]}>
      <View style={[s.rowIcon, { backgroundColor: tint.background }]}><Icon name={noticeIcons[kind].icon} color={tint.icon} size={21} /></View>
      <View style={s.rowCopy}>
        <Text style={s.rowTitle}>{title}</Text>
        <Text style={s.rowText}>{description}</Text>
        {chips.length > 0 && <View style={s.chips}>{chips.map(chip => <View key={chip.label} style={s.chip}>
          <Icon name={chip.icon} color={colors.secondary} size={13} /><Text style={s.chipText}>{chip.label}</Text>
        </View>)}</View>}
      </View>
    </View>
    <SettingSwitch label={label} value={value} onChange={onChange} inactive={inactive} busy={busy} />
  </View>;
}

/** The three notice switches, shared by the Notifications screen and onboarding. */
export function NoticeSwitches({ settings, onChange, busy = {}, rules }: {
  settings: NotificationSwitches & Pick<NotificationSettings, 'briefing_time'>; onChange: (field: keyof NotificationSwitches, value: boolean) => void;
  busy?: Partial<Record<keyof NotificationSwitches, boolean>>; rules?: NotificationSettings['breaking_news_rules'];
}) {
  const s = useStyles(makeStyles);
  const paused = !settings.notifications_enabled;
  const minSources = rules?.min_sources ?? 3;
  const quiet = rules === undefined ? { start: 22, end: 7 } : rules.quiet_hours;
  const chips: { icon: IconName; label: string }[] = [{ icon: 'layers', label: `${minSources} veículos ou mais` }];
  if (quiet) chips.push({ icon: 'moon', label: `Silêncio ${quiet.start}h–${quiet.end}h` });
  return <>
    <NoticeRow kind="all" title="Receber notificações" description="Desligue para pausar todos os avisos do Newzi." label="Receber notificações"
      value={settings.notifications_enabled} busy={busy.notifications_enabled} onChange={value => onChange('notifications_enabled', value)} />
    <NoticeRow kind="daily" title="Resumo diário" label="Notificação do resumo diário" inactive={paused} busy={busy.daily_briefing_enabled}
      description={settings.briefing_time ? <>Quando seu resumo ficar pronto, por volta das <Text style={s.strong}>{settings.briefing_time}</Text>.</> : 'Quando seu resumo do dia ficar pronto.'}
      value={settings.daily_briefing_enabled} onChange={value => onChange('daily_briefing_enabled', value)} />
    <NoticeRow kind="breaking" title="Notícias urgentes" label="Notificação de notícias urgentes" inactive={paused} busy={busy.breaking_news_enabled} last
      description="Quando algo importante acontece nos seus temas, com um resumo curto da notícia." chips={chips}
      value={settings.breaking_news_enabled} onChange={value => onChange('breaking_news_enabled', value)} />
  </>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md, paddingVertical: spacing.lg },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowBody: { flex: 1, flexDirection: 'row', gap: spacing.md },
  faded: { opacity: .45 },
  rowIcon: { width: 44, height: 44, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontWeight: '800', fontSize: 16 },
  rowText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 13, lineHeight: 19, marginTop: 3 },
  strong: { fontWeight: '800', color: colors.textPrimary },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: spacing.sm },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: colors.surfaceSoft, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 },
  chipText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 12, fontWeight: '600' },
});
