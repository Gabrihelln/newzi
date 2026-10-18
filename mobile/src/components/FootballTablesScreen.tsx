import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StatusBar, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../api/client';
import type { FootballMatch, FootballRound, FootballStandings } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { COMPETITIONS, CompetitionBadge, competitionInfo, TeamCrest, ZONE_COLORS, ZONE_LABELS } from './FootballParts';
import { dayLabel, isLive, timeLabel } from './LiveMatchCard';

type Tab = 'games' | 'table';

/** Esportes › Tabela: a competition's games by round and its table (zones, last results, your teams). */
export function FootballTablesScreen({ initialCode, onBack }: { initialCode?: string; onBack: () => void }) {
  const s = useStyles(makeStyles);
  const { colors, statusBar } = useTheme();
  const [code, setCode] = useState(initialCode && COMPETITIONS.some(item => item.code === initialCode) ? initialCode : 'BSA');
  const info = competitionInfo(code);
  const [tab, setTab] = useState<Tab>(info.table ? 'table' : 'games');
  const [table, setTable] = useState<FootballStandings | null>(null);
  const [round, setRound] = useState<FootballRound | null>(null);
  const [matchday, setMatchday] = useState<number | undefined>(undefined);
  const [picking, setPicking] = useState(false);
  const [favorites, setFavorites] = useState<Set<number>>(() => new Set());

  useEffect(() => { api.footballFavorites().then(value => setFavorites(new Set(value.teams.map(team => team.id)))).catch(() => undefined); }, []);
  useEffect(() => { if (!competitionInfo(code).table) setTab('games'); setMatchday(undefined); }, [code]);
  useEffect(() => {
    if (tab !== 'table') return;
    let active = true; setTable(null);
    api.footballStandings(code).then(value => { if (active) setTable(value); }).catch(() => { if (active) setTable({ available: false, reason: 'ERROR' }); });
    return () => { active = false; };
  }, [code, tab]);
  useEffect(() => {
    let active = true; setRound(null);
    api.footballRound(code, matchday).then(value => { if (active) setRound(value); }).catch(() => { if (active) setRound({ available: false, reason: 'ERROR' }); });
    return () => { active = false; };
  }, [code, matchday]);

  const roundLabel = round?.available && round.matchday ? `Rodada ${round.matchday}` : table?.available && table.matchday ? `Rodada ${table.matchday}` : 'Rodada';
  const zones = useMemo(() => {
    if (!table?.available) return [];
    return [...new Set(table.groups.flatMap(group => group.rows.map(row => row.zone)).filter(Boolean) as string[])];
  }, [table]);

  return <SafeAreaView style={s.safe} edges={['top']}>
    <StatusBar barStyle={statusBar} backgroundColor={colors.background} />
    <View style={s.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} hitSlop={8} style={s.headerButton}>
        <View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View>
      </Pressable>
      <Text accessibilityRole="header" numberOfLines={1} style={s.title}>{info.name}</Text>
      <View style={s.headerButton} />
    </View>
    <ScrollView contentContainerStyle={s.content}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.pills} style={s.pillsScroll}>
        {COMPETITIONS.map(item => <Pressable key={item.code} accessibilityRole="button" accessibilityState={{ selected: item.code === code }} onPress={() => setCode(item.code)}
          style={[s.pill, item.code === code && s.pillOn]}><Text style={[s.pillText, item.code === code && s.pillTextOn]}>{item.name}</Text></Pressable>)}
      </ScrollView>
      <View accessibilityRole="tablist" style={s.tabs}>
        {([['games', 'Jogos'], ['table', 'Tabela']] as [Tab, string][]).map(([value, label]) => {
          const disabled = value === 'table' && !info.table;
          return <Pressable key={value} accessibilityRole="tab" accessibilityState={{ selected: tab === value, disabled }} disabled={disabled} onPress={() => setTab(value)}
            style={[s.tab, tab === value && s.tabOn, disabled && { opacity: .4 }]}><Text style={[s.tabText, tab === value && s.tabTextOn]}>{label}</Text></Pressable>;
        })}
      </View>
      <View style={s.compHead}>
        <CompetitionBadge code={code} size={52} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={s.compName}>{code === 'BSA' ? 'Brasileirão Série A' : info.name}</Text>
          <Text style={s.compSeason}>{table?.available && table.season ? `Temporada ${table.season}` : 'Temporada atual'}</Text>
        </View>
        {tab === 'games' && round?.available && round.matchdays.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel={`${roundLabel}. Escolher rodada`} onPress={() => setPicking(true)} style={s.roundButton}>
          <Text style={s.roundText}>{roundLabel}</Text><Icon name="chevronDown" color={colors.secondary} size={16} />
        </Pressable>}
        {tab === 'table' && table?.available && !!table.matchday && <View style={s.roundButton}><Text style={s.roundText}>Rodada {table.matchday}</Text></View>}
      </View>

      {tab === 'table' ? !table ? <ActivityIndicator style={{ marginTop: 30 }} color={colors.primary} />
        : !table.available || !table.groups.length ? <Text style={s.empty}>Tabela indisponível para este campeonato.</Text>
        : <>
          {table.groups.map((group, index) => <View key={group.name || index} style={s.tableCard}>
            {!!group.name && <Text style={s.groupName}>{group.name}</Text>}
            <View style={[s.row, s.headRow]}>
              <Text style={[s.pos, s.head]}>#</Text><Text style={[s.team, s.head]}>Time</Text>
              <Text style={[s.num, s.head]}>J</Text><Text style={[s.num, s.head, { width: 38 }]}>SG</Text>
              <Text style={[s.form, s.head]}>Últimos</Text><Text style={[s.pts, s.head]}>P</Text>
            </View>
            {group.rows.map(row => {
              const mine = favorites.has(row.team_id ?? -1);
              return <View key={`${row.position}-${row.team}`} accessibilityLabel={`${row.position}º ${row.team}${mine ? ', seu time' : ''}, ${row.points} pontos em ${row.played} jogos, saldo ${row.goal_difference}`}
                style={[s.row, mine && s.rowMine]}>
                <View style={[s.zone, { backgroundColor: row.zone ? ZONE_COLORS[row.zone] : 'transparent' }]} />
                <Text style={s.pos}>{row.position}</Text>
                <View style={[s.team, s.teamCell]}>
                  <TeamCrest crest={row.crest} tla={row.tla} name={row.team} size={24} />
                  <Text numberOfLines={1} style={[s.teamName, mine && s.teamNameMine]}>{row.team}</Text>
                  {mine && <Icon name="star" color={colors.sun} size={14} />}
                </View>
                <Text style={s.num}>{row.played ?? '–'}</Text>
                <Text style={[s.num, { width: 38 }]}>{row.goal_difference == null ? '–' : row.goal_difference > 0 ? `+${row.goal_difference}` : row.goal_difference}</Text>
                <View style={[s.form, s.formDots]}>{(row.form || []).map((result, i) => <View key={i} style={[s.dot, { backgroundColor: result === 'W' ? '#22C55E' : result === 'L' ? '#EF4444' : colors.borderStrong }]} />)}</View>
                <Text style={s.pts}>{row.points ?? '–'}</Text>
              </View>;
            })}
          </View>)}
          <View style={s.legend}>
            {zones.map(zone => <View key={zone} style={s.legendItem}><View style={[s.legendDot, { backgroundColor: ZONE_COLORS[zone] }]} /><Text style={s.legendText}>{ZONE_LABELS[zone]}</Text></View>)}
            {favorites.size > 0 && <View style={s.legendItem}><Icon name="star" color={colors.sun} size={14} /><Text style={s.legendText}>Seus times</Text></View>}
            <View style={s.legendItem}><View style={[s.dot, { backgroundColor: '#22C55E' }]} /><Text style={s.legendText}>Vitória</Text><View style={[s.dot, { backgroundColor: colors.borderStrong }]} /><Text style={s.legendText}>Empate</Text><View style={[s.dot, { backgroundColor: '#EF4444' }]} /><Text style={s.legendText}>Derrota</Text></View>
          </View>
        </>
        : !round ? <ActivityIndicator style={{ marginTop: 30 }} color={colors.primary} />
        : !round.available || !round.matches.length ? <Text style={s.empty}>Nenhum jogo nesta rodada.</Text>
        : <View style={s.tableCard}>{round.matches.map((match, index) => <RoundGame key={match.id} match={match} favorites={favorites} last={index === round.matches.length - 1} />)}</View>}
    </ScrollView>

    <Modal visible={picking} transparent animationType="fade" onRequestClose={() => setPicking(false)}>
      <Pressable accessibilityLabel="Fechar" onPress={() => setPicking(false)} style={s.scrim}>
        <Pressable onPress={() => undefined} style={s.sheet}>
          <Text accessibilityRole="header" style={s.sheetTitle}>Escolha a rodada</Text>
          <ScrollView style={{ maxHeight: 360 }}>
            {round?.available && [...round.matchdays].reverse().map(value => <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: value === round.matchday }}
              onPress={() => { setMatchday(value); setPicking(false); }} style={s.option}>
              <Text style={[s.optionText, value === round.matchday && { color: colors.primary }]}>Rodada {value}{value === round.current_matchday ? ' · atual' : ''}</Text>
              {value === round.matchday && <Icon name="check" color={colors.primary} size={18} />}
            </Pressable>)}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  </SafeAreaView>;
}

function RoundGame({ match, favorites, last }: { match: FootballMatch; favorites: Set<number>; last: boolean }) {
  const s = useStyles(makeStyles);
  const done = match.status === 'FINISHED' || isLive(match);
  const side = (name: string, id?: number | null, crest?: string | null, tla?: string, goals?: number | null) => <View style={s.gameLine}>
    <TeamCrest crest={crest} tla={tla} name={name} size={22} />
    <Text numberOfLines={1} style={[s.gameTeam, favorites.has(id ?? -1) && { fontWeight: '800' }]}>{name}</Text>
    {done && <Text style={s.gameGoals}>{goals ?? 0}</Text>}
  </View>;
  return <View style={[s.game, !last && s.gameDivider]}>
    <View style={s.gameWhen}>
      <Text style={[s.gameTime, isLive(match) && { color: '#E11D48' }]}>{isLive(match) ? 'AO VIVO' : match.status === 'FINISHED' ? 'FIM' : timeLabel(match.kickoff)}</Text>
      <Text style={s.gameDay}>{dayLabel(match.kickoff, true).toLowerCase()}</Text>
    </View>
    <View style={{ flex: 1, minWidth: 0, gap: 8 }}>
      {side(match.home, match.home_id, match.home_crest, match.home_tla, match.home_goals)}
      {side(match.away, match.away_id, match.away_crest, match.away_tla, match.away_goals)}
    </View>
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { height: 56, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12 },
  headerButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800', color: colors.ink },
  content: { paddingHorizontal: 18, paddingBottom: 40 },
  pillsScroll: { marginHorizontal: -18 },
  pills: { gap: 8, paddingHorizontal: 18, paddingVertical: 6 },
  pill: { minHeight: 40, paddingHorizontal: 16, borderRadius: 999, justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillOn: { backgroundColor: colors.surfaceBlue, borderColor: colors.tone('#9CC9FF', colors.primary) },
  pillText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '600', color: colors.body },
  pillTextOn: { color: colors.primary, fontWeight: '800' },
  tabs: { flexDirection: 'row', padding: 4, borderRadius: 18, backgroundColor: colors.tone('#EAF0F7', colors.surfaceSoft), marginTop: 10 },
  tab: { flex: 1, minHeight: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  tabOn: { backgroundColor: colors.surface, shadowColor: colors.shadow.color, shadowOpacity: .14, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  tabText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.secondary },
  tabTextOn: { color: colors.ink, fontWeight: '800' },
  compHead: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 16, marginBottom: 12 },
  compName: { fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800', color: colors.ink },
  compSeason: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: colors.secondary, marginTop: 2 },
  roundButton: { flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 40, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  roundText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.ink },
  tableCard: { borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 6 },
  groupName: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.ink, marginTop: 8, marginBottom: 4 },
  row: { flexDirection: 'row', alignItems: 'center', minHeight: 46, borderTopWidth: 1, borderTopColor: colors.divider },
  headRow: { borderTopWidth: 0, minHeight: 34 },
  rowMine: { backgroundColor: colors.tone('#F2F8FF', colors.surfaceTint) },
  head: { color: colors.muted, fontWeight: '700', fontSize: 12 },
  zone: { position: 'absolute', left: -12, top: 8, bottom: 8, width: 3, borderRadius: 2 },
  pos: { width: 26, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.ink, textAlign: 'center' },
  team: { flex: 1, minWidth: 0 },
  teamCell: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 6 },
  teamName: { flexShrink: 1, fontFamily: typography.fontFamily.ui, fontSize: 14.5, color: colors.ink },
  teamNameMine: { color: colors.primary, fontWeight: '800' },
  num: { width: 28, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary },
  form: { width: 54, textAlign: 'center' },
  formDots: { flexDirection: 'row', justifyContent: 'center', gap: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  pts: { width: 30, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.ink },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: 14 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 12, height: 12, borderRadius: 3 },
  legendText: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary },
  game: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  gameDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  gameWhen: { width: 66, alignItems: 'center' },
  gameTime: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.ink },
  gameDay: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.muted, marginTop: 1 },
  gameLine: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  gameTeam: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, color: colors.ink },
  gameGoals: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.ink },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 14, color: colors.secondary, textAlign: 'center', marginTop: 24 },
  scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, paddingBottom: 30 },
  sheetTitle: { fontFamily: typography.fontFamily.ui, fontSize: 17, fontWeight: '800', color: colors.ink, marginBottom: 8 },
  option: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: colors.divider },
  optionText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.ink },
});
