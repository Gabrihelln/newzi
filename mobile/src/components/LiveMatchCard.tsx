import React, { useEffect, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { createMMKV } from 'react-native-mmkv';
import { api } from '../api/client';
import type { FootballMatch, FootballOverview } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { TeamCrest } from './FootballParts';

const REFRESH_MS = 60_000;
const PREVIEW = 4;
const storage = createMMKV({ id: 'newzi-settings' });
const FOLLOWED_MATCH = 'followed-match';

export const timeLabel = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date);
};
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
/** "Hoje", "Amanhã" or the weekday ("qui., 16/10") of a kickoff, in the phone's time zone. */
export const dayLabel = (value: string, withDate = false) => {
  const date = new Date(value), today = new Date(), tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (Number.isNaN(date.getTime())) return '';
  if (sameDay(date, today)) return 'Hoje';
  if (sameDay(date, tomorrow)) return 'Amanhã';
  const weekday = new Intl.DateTimeFormat('pt-BR', { weekday: 'short' }).format(date);
  return withDate ? `${weekday} ${new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit' }).format(date)}` : weekday;
};
export const tla = (name: string, code?: string) => (code || name.replace(/[^A-Za-zÀ-ÿ]/g, '').slice(0, 3)).toUpperCase();
export const isLive = (match: FootballMatch) => match.status === 'IN_PLAY' || match.status === 'PAUSED';

/**
 * Explore's football card: the next games of every covered competition (Brasileirão, Libertadores, the big
 * European leagues...), soonest first. A live scoreboard appears on top only while a game is actually on.
 * Tapping it opens the full fixture list and the tables.
 */
export function LiveMatchCard({ onOpen }: { onOpen: () => void }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const [data, setData] = useState<FootballOverview | null>(null);
  const [followed, setFollowed] = useState<number | null>(() => storage.getNumber(FOLLOWED_MATCH) ?? null);
  const [picking, setPicking] = useState(false);
  useEffect(() => {
    let active = true;
    const load = () => api.football('explore').then(value => { if (active) setData(value); }).catch(() => undefined);
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => { active = false; clearInterval(timer); };
  }, []);
  if (!data || !data.available) return null;

  // An older backend (or a cached response from one) may leave lists out; treat them as empty.
  const live = data.live ?? [], upcoming = data.upcoming ?? [];
  const match = live.find(item => item.id === followed) || live[0];
  const follow = (item: FootballMatch) => { setFollowed(item.id); storage.set(FOLLOWED_MATCH, item.id); setPicking(false); };
  const next = upcoming.slice(0, match ? PREVIEW - 1 : PREVIEW);
  if (!match && !next.length) return null;

  return <Pressable accessibilityRole="button" accessibilityLabel="Futebol. Ver todos os jogos e tabelas" onPress={onOpen}
    style={({ pressed }) => [styles.card, pressed && { opacity: .85 }]}>
    <View style={styles.header}>
      <View style={styles.headerIcon}><Icon name="ball" size={15} color={colors.topicGreen.icon} /></View>
      <Text style={styles.title}>Futebol</Text>
      <Text style={styles.meta}>· {match ? `${live.length} ao vivo` : 'Próximos jogos'}</Text>
      <View style={styles.more}><Text style={styles.moreText}>Jogos e tabelas</Text><Icon name="chevron" size={14} color={colors.primary} /></View>
    </View>

    {match && <View style={styles.liveBox}>
      <View style={styles.liveTop}>
        <Text numberOfLines={1} style={styles.liveCompetition}>{match.competition?.name}</Text>
        {live.length > 1 && <Pressable accessibilityRole="button" accessibilityLabel={`${live.length} jogos ao vivo. Trocar jogo`} onPress={() => setPicking(true)} hitSlop={8} style={styles.switch}>
          <Text style={styles.switchText}>trocar jogo</Text>
          <View style={{ transform: [{ rotate: '90deg' }] }}><Icon name="chevron" size={12} color={colors.primary} /></View>
        </Pressable>}
      </View>
      <View accessibilityLabel={`${match.status === 'PAUSED' ? 'Intervalo' : 'Ao vivo'}: ${match.home} ${match.home_goals ?? 0}, ${match.away} ${match.away_goals ?? 0}`} style={styles.score}>
        <Team name={match.home} code={match.home_tla} crest={match.home_crest} />
        <View style={styles.scoreCenter}>
          <Text style={styles.goals}>{match.home_goals ?? 0}<Text style={styles.goalsSep}>  –  </Text>{match.away_goals ?? 0}</Text>
          <LiveBadge paused={match.status === 'PAUSED'} />
        </View>
        <Team name={match.away} code={match.away_tla} crest={match.away_crest} />
      </View>
    </View>}

    {next.map(item => <View key={item.id} style={styles.row}>
      <View style={styles.when}>
        <Text style={styles.whenDay}>{dayLabel(item.kickoff)}</Text>
        <Text style={styles.whenTime}>{timeLabel(item.kickoff)}</Text>
      </View>
      <View style={styles.rowCopy}>
        <View style={styles.rowLine}><TeamCrest crest={item.home_crest} tla={item.home_tla} name={item.home} size={18} /><Text numberOfLines={1} style={styles.rowTeams}>{item.home} × {item.away}</Text><TeamCrest crest={item.away_crest} tla={item.away_tla} name={item.away} size={18} /></View>
        {!!item.competition && <Text numberOfLines={1} style={styles.rowCompetition}>{item.competition.name}</Text>}
      </View>
    </View>)}

    <Modal visible={picking} transparent animationType="fade" onRequestClose={() => setPicking(false)}>
      <Pressable accessibilityLabel="Fechar" onPress={() => setPicking(false)} style={styles.scrim}>
        <Pressable onPress={() => undefined} style={styles.sheet}>
          <Text accessibilityRole="header" style={styles.sheetTitle}>Qual jogo acompanhar?</Text>
          {live.map(item => <Pressable key={item.id} accessibilityRole="radio" accessibilityState={{ checked: item.id === match?.id }} onPress={() => follow(item)}
            style={({ pressed }) => [styles.option, pressed && { opacity: .7 }]}>
            <View style={{ flex: 1 }}>
              <Text numberOfLines={1} style={styles.optionText}>{item.home} {item.home_goals ?? 0} – {item.away_goals ?? 0} {item.away}</Text>
              {!!item.competition && <Text style={styles.rowCompetition}>{item.competition.name}</Text>}
            </View>
            {item.id === match?.id && <Icon name="check" size={18} color={colors.primary} />}
          </Pressable>)}
        </Pressable>
      </Pressable>
    </Modal>
  </Pressable>;
}

export function LiveBadge({ paused }: { paused: boolean }) {
  const styles = useStyles(makeStyles);
  return <View style={[styles.badge, paused && styles.badgePaused]}>
    {!paused && <View style={styles.liveDot} />}
    <Text style={[styles.badgeText, paused && styles.badgePausedText]}>{paused ? 'INTERVALO' : 'AO VIVO'}</Text>
  </View>;
}

function Team({ name, code, crest }: { name: string; code?: string; crest?: string | null }) {
  const styles = useStyles(makeStyles);
  return <View style={styles.team}>
    {crest ? <TeamCrest crest={crest} tla={code} name={name} size={40} /> : <View style={styles.crest}><Text style={styles.crestText}>{tla(name, code)}</Text></View>}
    <Text numberOfLines={1} style={styles.teamName}>{name}</Text>
  </View>;
}

const makeStyles = (colors: Palette) => {
  const ui = typography.fontFamily.ui;
  return {
    card: { marginBottom: 20, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14, paddingTop: 12, paddingBottom: 6 },
    header: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6, marginBottom: 4 },
    headerIcon: { width: 26, height: 26, borderRadius: 13, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.topicGreen.background },
    title: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '800' as const },
    meta: { color: colors.secondary, fontFamily: ui, fontSize: 12 },
    more: { marginLeft: 'auto' as const, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 1 },
    moreText: { color: colors.primary, fontFamily: ui, fontSize: 12, fontWeight: '700' as const },
    liveBox: { marginTop: 8, marginBottom: 4, borderRadius: 14, padding: 10, backgroundColor: colors.surfaceTint },
    liveTop: { flexDirection: 'row' as const, alignItems: 'center' as const },
    liveCompetition: { flex: 1, color: colors.secondary, fontFamily: ui, fontSize: 11, fontWeight: '700' as const },
    switch: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 2, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, backgroundColor: colors.surface },
    switchText: { color: colors.primary, fontFamily: ui, fontSize: 11, fontWeight: '700' as const },
    score: { flexDirection: 'row' as const, alignItems: 'center' as const, marginTop: 8 },
    team: { flex: 1, alignItems: 'center' as const, gap: 5 },
    crest: { width: 40, height: 40, borderRadius: 20, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider },
    crestText: { color: colors.textPrimary, fontFamily: ui, fontSize: 11, fontWeight: '800' as const, letterSpacing: .3 },
    teamName: { color: colors.secondary, fontFamily: ui, fontSize: 12, fontWeight: '600' as const, maxWidth: '100%' as const },
    scoreCenter: { alignItems: 'center' as const, gap: 5, paddingHorizontal: 6 },
    goals: { color: colors.textPrimary, fontFamily: ui, fontSize: 28, lineHeight: 32, fontWeight: '800' as const },
    goalsSep: { color: colors.muted, fontSize: 20, fontWeight: '500' as const },
    badge: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 5, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 9, backgroundColor: colors.topicRed.background },
    badgePaused: { backgroundColor: colors.surface },
    liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.topicRed.icon },
    badgeText: { color: colors.topicRed.icon, fontFamily: ui, fontSize: 10, fontWeight: '800' as const, letterSpacing: .4 },
    badgePausedText: { color: colors.secondary },
    row: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, minHeight: 48, borderTopWidth: 1, borderTopColor: colors.divider },
    when: { width: 46 },
    whenDay: { color: colors.secondary, fontFamily: ui, fontSize: 11, fontWeight: '600' as const },
    whenTime: { color: colors.textPrimary, fontFamily: ui, fontSize: 13, fontWeight: '800' as const },
    rowCopy: { flex: 1, minWidth: 0 },
    rowTeams: { flexShrink: 1, color: colors.textPrimary, fontFamily: ui, fontSize: 13, fontWeight: '700' as const },
    rowLine: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
    rowCompetition: { color: colors.secondary, fontFamily: ui, fontSize: 11, marginTop: 1 },
    scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' as const },
    sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, paddingBottom: 30 },
    sheetTitle: { color: colors.textPrimary, fontFamily: ui, fontSize: 17, fontWeight: '800' as const, marginBottom: 8 },
    option: { minHeight: 56, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, borderTopWidth: 1, borderTopColor: colors.divider },
    optionText: { color: colors.textPrimary, fontFamily: ui, fontSize: 15, fontWeight: '700' as const },
  };
};
