import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import { api } from '../api/client';
import type { FootballCompetition, FootballMatch, FootballOverview, FootballStandings } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { BrandPage, BrandPageHeader } from './ScreenPrimitives';
import { dayLabel, isLive, LiveBadge, timeLabel } from './LiveMatchCard';

const REFRESH_MS = 60_000;
type Tab = 'games' | 'tables';

/** Every upcoming game of the covered competitions, by day, plus each league's table. Opened from Explore. */
export function FootballScreen({ onBack }: { onBack: () => void }) {
  const styles = useStyles(makeStyles);
  const [tab, setTab] = useState<Tab>('games');
  const [data, setData] = useState<FootballOverview | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    const load = () => api.football('explore').then(value => { if (active) { setData(value); setFailed(false); } }).catch(() => { if (active) setFailed(true); });
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const competitions = data?.available ? data.competitions ?? [] : [];

  return <BrandPage>
    <BrandPageHeader title="Futebol" subtitle="Próximos jogos e tabelas dos campeonatos." onBack={onBack} />
    <View accessibilityRole="tablist" style={styles.tabs}>
      {([['games', 'Jogos'], ['tables', 'Tabelas']] as [Tab, string][]).map(([value, label]) => <Pressable key={value} accessibilityRole="tab" accessibilityState={{ selected: tab === value }} onPress={() => setTab(value)}
        style={[styles.tab, tab === value && styles.tabActive]}><Text style={[styles.tabText, tab === value && styles.tabTextActive]}>{label}</Text></Pressable>)}
    </View>
    {!data ? failed ? <Text style={styles.empty}>Não foi possível carregar os jogos agora.</Text> : <ActivityIndicator style={{ marginTop: 30 }} />
      : !data.available ? <Text style={styles.empty}>Os jogos estão indisponíveis no momento.</Text>
      : tab === 'games' ? <Games live={data.live ?? []} upcoming={data.upcoming ?? []} competitions={competitions} />
      : <Tables competitions={competitions.filter(item => item.table !== false)} />}
  </BrandPage>;
}

function Chips({ items, selected, onSelect }: { items: { code: string; name: string }[]; selected: string; onSelect: (code: string) => void }) {
  const styles = useStyles(makeStyles);
  return <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} style={styles.chipsScroll}>
    {items.map(item => <Pressable key={item.code} accessibilityRole="button" accessibilityState={{ selected: selected === item.code }} onPress={() => onSelect(item.code)}
      style={[styles.chip, selected === item.code && styles.chipActive]}><Text style={[styles.chipText, selected === item.code && styles.chipTextActive]}>{item.name}</Text></Pressable>)}
  </ScrollView>;
}

function Games({ live, upcoming, competitions }: { live: FootballMatch[]; upcoming: FootballMatch[]; competitions: FootballCompetition[] }) {
  const styles = useStyles(makeStyles);
  const [filter, setFilter] = useState('ALL');
  const keep = (match: FootballMatch) => filter === 'ALL' || match.competition?.code === filter;
  const days = useMemo(() => {
    const groups: { label: string; matches: FootballMatch[] }[] = [];
    upcoming.filter(keep).forEach(match => {
      const label = dayLabel(match.kickoff, true);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.matches.push(match); else groups.push({ label, matches: [match] });
    });
    return groups;
  }, [upcoming, filter]); // eslint-disable-line react-hooks/exhaustive-deps
  const liveNow = live.filter(keep);
  return <View>
    <Chips items={[{ code: 'ALL', name: 'Todos' }, ...competitions]} selected={filter} onSelect={setFilter} />
    {!!liveNow.length && <View style={styles.group}>
      <Text style={styles.groupTitle}>Ao vivo</Text>
      {liveNow.map(match => <MatchRow key={match.id} match={match} showCompetition={filter === 'ALL'} />)}
    </View>}
    {days.map(day => <View key={day.label} style={styles.group}>
      <Text style={styles.groupTitle}>{day.label}</Text>
      {day.matches.map(match => <MatchRow key={match.id} match={match} showCompetition={filter === 'ALL'} />)}
    </View>)}
    {!liveNow.length && !days.length && <Text style={styles.empty}>Nenhum jogo nos próximos dias.</Text>}
  </View>;
}

function MatchRow({ match, showCompetition }: { match: FootballMatch; showCompetition: boolean }) {
  const styles = useStyles(makeStyles);
  const live = isLive(match);
  return <View style={styles.match} accessibilityLabel={live ? `Ao vivo: ${match.home} ${match.home_goals ?? 0}, ${match.away} ${match.away_goals ?? 0}` : `${match.home} contra ${match.away}, ${timeLabel(match.kickoff)}`}>
    <View style={styles.matchWhen}>{live ? <LiveBadge paused={match.status === 'PAUSED'} /> : <Text style={styles.matchTime}>{timeLabel(match.kickoff)}</Text>}</View>
    <View style={styles.matchCopy}>
      <View style={styles.matchLine}><Text numberOfLines={1} style={styles.matchTeam}>{match.home}</Text>{live && <Text style={styles.matchGoals}>{match.home_goals ?? 0}</Text>}</View>
      <View style={styles.matchLine}><Text numberOfLines={1} style={styles.matchTeam}>{match.away}</Text>{live && <Text style={styles.matchGoals}>{match.away_goals ?? 0}</Text>}</View>
      {showCompetition && !!match.competition && <Text style={styles.matchCompetition}>{match.competition.name}</Text>}
    </View>
  </View>;
}

function Tables({ competitions }: { competitions: FootballCompetition[] }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const [code, setCode] = useState(() => competitions.find(item => item.code === 'BSA')?.code || competitions[0]?.code || 'BSA');
  const [table, setTable] = useState<FootballStandings | null>(null);
  useEffect(() => {
    let active = true;
    setTable(null);
    api.footballStandings(code).then(value => { if (active) setTable(value); }).catch(() => { if (active) setTable({ available: false, reason: 'ERROR' }); });
    return () => { active = false; };
  }, [code]);
  const options = competitions.length ? competitions : [{ code: 'BSA', name: 'Brasileirão' }];
  return <View>
    <Chips items={options} selected={code} onSelect={setCode} />
    {!table ? <ActivityIndicator style={{ marginTop: 30 }} />
      : !table.available || !table.groups.length ? <Text style={styles.empty}>Tabela indisponível para este campeonato.</Text>
      : <>
        {!!table.matchday && <Text style={styles.matchday}>Rodada {table.matchday}</Text>}
        {table.groups.map((group, index) => <View key={group.name || index} style={styles.tableCard}>
          {!!group.name && <Text style={styles.groupTitle}>{group.name}</Text>}
          <View style={[styles.tableRow, styles.tableHead]}>
            <Text style={[styles.cellPos, styles.headText]}>#</Text><Text style={[styles.cellTeam, styles.headText]}>Time</Text>
            {['J', 'V', 'E', 'D', 'SG'].map(label => <Text key={label} style={[styles.cell, styles.headText]}>{label}</Text>)}
            <Text style={[styles.cellPts, styles.headText]}>P</Text>
          </View>
          {group.rows.map(row => <View key={`${row.position}-${row.team}`} style={styles.tableRow} accessibilityLabel={`${row.position}º ${row.team}, ${row.points} pontos em ${row.played} jogos`}>
            <Text style={[styles.cellPos, row.position <= 4 && { color: colors.primary }]}>{row.position}</Text>
            <Text numberOfLines={1} style={styles.cellTeam}>{row.team}</Text>
            {[row.played, row.won, row.draw, row.lost, row.goal_difference].map((value, cell) => <Text key={cell} style={styles.cell}>{value ?? '–'}</Text>)}
            <Text style={styles.cellPts}>{row.points ?? '–'}</Text>
          </View>)}
        </View>)}
      </>}
  </View>;
}

const makeStyles = (colors: Palette) => {
  const ui = typography.fontFamily.ui;
  const cell = { width: 26, textAlign: 'center' as const, color: colors.secondary, fontFamily: ui, fontSize: 12 };
  return {
    tabs: { flexDirection: 'row' as const, padding: 4, borderRadius: 14, backgroundColor: colors.surfaceTint, marginBottom: 12 },
    tab: { flex: 1, minHeight: 38, borderRadius: 11, alignItems: 'center' as const, justifyContent: 'center' as const },
    tabActive: { backgroundColor: colors.surface, shadowColor: colors.shadow.color, shadowOpacity: .08, shadowRadius: 4, elevation: 1 },
    tabText: { color: colors.secondary, fontFamily: ui, fontSize: 14, fontWeight: '600' as const },
    tabTextActive: { color: colors.textPrimary, fontWeight: '800' as const },
    chipsScroll: { marginBottom: 6, marginHorizontal: -4 },
    chips: { gap: 8, paddingHorizontal: 4, paddingBottom: 6 },
    chip: { paddingHorizontal: 14, minHeight: 34, justifyContent: 'center' as const, borderRadius: 17, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
    chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
    chipText: { color: colors.textPrimary, fontFamily: ui, fontSize: 13, fontWeight: '600' as const },
    chipTextActive: { color: colors.onPrimary },
    group: { marginTop: 10, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14, paddingTop: 10, paddingBottom: 4 },
    groupTitle: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '800' as const, textTransform: 'capitalize' as const, marginBottom: 4 },
    match: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.divider },
    matchWhen: { width: 68 },
    matchTime: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '800' as const },
    matchCopy: { flex: 1, minWidth: 0, gap: 2 },
    matchLine: { flexDirection: 'row' as const, alignItems: 'center' as const },
    matchTeam: { flex: 1, color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '600' as const },
    matchGoals: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '800' as const, marginLeft: 8 },
    matchCompetition: { color: colors.secondary, fontFamily: ui, fontSize: 11, marginTop: 2 },
    matchday: { color: colors.secondary, fontFamily: ui, fontSize: 12, fontWeight: '600' as const, marginTop: 4 },
    tableCard: { marginTop: 10, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8 },
    tableRow: { flexDirection: 'row' as const, alignItems: 'center' as const, minHeight: 34, borderTopWidth: 1, borderTopColor: colors.divider },
    tableHead: { borderTopWidth: 0, minHeight: 28 },
    headText: { color: colors.muted, fontWeight: '700' as const, fontSize: 11 },
    cellPos: { width: 24, color: colors.secondary, fontFamily: ui, fontSize: 12, fontWeight: '800' as const },
    cellTeam: { flex: 1, minWidth: 0, color: colors.textPrimary, fontFamily: ui, fontSize: 13, fontWeight: '600' as const },
    cell,
    cellPts: { ...cell, width: 30, color: colors.textPrimary, fontWeight: '800' as const },
    empty: { color: colors.secondary, fontFamily: ui, fontSize: 13, textAlign: 'center' as const, marginTop: 24 },
  };
};
