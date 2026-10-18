import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StatusBar, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { api } from '../api/client';
import type { FootballMatch, FootballOverview, FootballTeam } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { CompetitionBadge, TeamCrest } from './FootballParts';
import { dayLabel, isLive, timeLabel } from './LiveMatchCard';

const REFRESH_MS = 60_000;

/**
 * Esportes (opened from Explorar's football card): your teams, the games being played now and the next ones
 * by day and competition, with every team's crest. The star marks your teams; the bell turns on the alerts of
 * one game. Tables and favourites have their own screens.
 */
export function FootballScreen({ onBack, onTables, onFavorites }: { onBack: () => void; onTables: (code?: string) => void; onFavorites: () => void }) {
  const s = useStyles(makeStyles);
  const { colors, statusBar } = useTheme();
  const [data, setData] = useState<FootballOverview | null>(null);
  const [teams, setTeams] = useState<FootballTeam[]>([]);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [followed, setFollowed] = useState<Set<number>>(() => new Set());

  const load = useCallback(async () => {
    try {
      const [overview, favorites] = await Promise.all([api.football('explore'), api.footballFavorites().catch(() => null)]);
      setData(overview); setFailed(false);
      if (favorites) { setTeams(favorites.teams); setFollowed(new Set(favorites.followed_matches)); }
    } catch { setFailed(true); }
    finally { setRefreshing(false); }
  }, []);
  // Coming back from Times favoritos shows the new teams at once.
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  useEffect(() => { const timer = setInterval(() => void load(), REFRESH_MS); return () => clearInterval(timer); }, [load]);

  const favoriteIds = useMemo(() => new Set(teams.map(team => team.id)), [teams]);
  const live = data?.available ? data.live ?? [] : [];
  const upcoming = data?.available ? data.upcoming ?? [] : [];
  const mine = (match: FootballMatch) => favoriteIds.has(match.home_id ?? -1) || favoriteIds.has(match.away_id ?? -1);
  // Day, then competition (Brasileirão first, as the backend orders them), then kickoff.
  const days = useMemo(() => {
    const out: { label: string; competitions: { code: string; name: string; matches: FootballMatch[] }[] }[] = [];
    upcoming.slice(0, 60).forEach(match => {
      const label = dayLabel(match.kickoff, true);
      let day = out.find(item => item.label === label);
      if (!day) { day = { label, competitions: [] }; out.push(day); }
      const code = match.competition?.code || '';
      let group = day.competitions.find(item => item.code === code);
      if (!group) { group = { code, name: match.competition?.name || code, matches: [] }; day.competitions.push(group); }
      group.matches.push(match);
    });
    return out;
  }, [upcoming]);

  const toggleBell = async (match: FootballMatch) => {
    if (mine(match)) { Alert.alert('Jogo do seu time', 'Os avisos dos jogos dos seus times já estão ligados. Ajuste em Times favoritos.'); return; }
    const following = !followed.has(match.id);
    setFollowed(current => { const next = new Set(current); if (following) next.add(match.id); else next.delete(match.id); return next; });
    try { await api.followFootballMatch(match.id, following); }
    catch {
      setFollowed(current => { const next = new Set(current); if (following) next.delete(match.id); else next.add(match.id); return next; });
      Alert.alert('Não foi possível ligar o aviso', 'Verifique sua conexão e tente de novo.');
    }
  };

  const playing = (team: FootballTeam) => live.find(match => match.home_id === team.id || match.away_id === team.id);

  return <SafeAreaView style={s.safe} edges={['top']}>
    <StatusBar barStyle={statusBar} backgroundColor={colors.background} />
    <View style={s.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} hitSlop={8} style={s.headerButton}>
        <View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View>
      </Pressable>
      <Text accessibilityRole="header" style={s.title}>Esportes</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Times favoritos e avisos" onPress={onFavorites} hitSlop={8} style={s.headerButton}>
        <Icon name="settings" color={colors.secondary} size={22} />
      </Pressable>
    </View>
    <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={colors.primary} />}>
      <View style={s.sectionRow}>
        <Text style={s.sectionTitle}>Meus times</Text>
        <Pressable accessibilityRole="button" onPress={onFavorites} hitSlop={8} style={s.link}><Text style={s.linkText}>Editar</Text><Icon name="chevron" color={colors.primary} size={15} /></Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.myTeams}>
        {teams.map(team => {
          const match = playing(team);
          const score = match ? (match.home_id === team.id ? `${match.home_goals ?? 0}–${match.away_goals ?? 0}` : `${match.away_goals ?? 0}–${match.home_goals ?? 0}`) : '';
          return <Pressable key={team.id} accessibilityRole="button" accessibilityLabel={match ? `${team.name}, ao vivo ${score}` : team.name} onPress={() => onTables(team.competitions[0]?.code)} style={s.myTeam}>
            <View style={[s.myCrest, match && s.myCrestLive]}><TeamCrest crest={team.crest} tla={team.tla} name={team.name} size={40} /></View>
            <Text numberOfLines={1} style={[s.myName, match && s.myNameLive]}>{match ? `Ao vivo ${score}` : team.name}</Text>
          </Pressable>;
        })}
        <Pressable accessibilityRole="button" accessibilityLabel="Adicionar time favorito" onPress={onFavorites} style={s.myTeam}>
          <View style={[s.myCrest, s.addCrest]}><Icon name="plus" color={colors.primary} size={26} /></View>
          <Text style={s.myName}>Adicionar</Text>
        </Pressable>
      </ScrollView>

      {!data ? failed ? <Text style={s.empty}>Não foi possível carregar os jogos agora.</Text> : <ActivityIndicator style={{ marginTop: 30 }} color={colors.primary} />
        : !data.available ? <Text style={s.empty}>Os jogos estão indisponíveis no momento.</Text> : <>
          {live.length > 0 && <>
            <View style={s.sectionRow}>
              <View style={s.liveTitle}><View style={s.liveDot} /><Text style={s.sectionTitle}>Ao vivo</Text></View>
              <Text style={s.count}>{live.length} {live.length === 1 ? 'jogo' : 'jogos'}</Text>
            </View>
            {live.map(match => <LiveGame key={match.id} match={match} />)}
          </>}

          <View style={s.sectionRow}>
            <Text style={s.sectionTitle}>Próximos jogos</Text>
            <Pressable accessibilityRole="button" onPress={() => onTables()} hitSlop={8} style={s.link}><Text style={s.linkText}>Tabelas</Text><Icon name="chevron" color={colors.primary} size={15} /></Pressable>
          </View>
          {!days.length && <Text style={s.empty}>Nenhum jogo nos próximos dias.</Text>}
          {days.map(day => <View key={day.label}>
            <Text style={s.dayLabel}>{day.label.toUpperCase()}</Text>
            {day.competitions.map(group => <View key={group.code} style={s.card}>
              <Pressable accessibilityRole="button" accessibilityLabel={`${group.name}: tabela e rodada`} onPress={() => onTables(group.code)} style={s.cardHead}>
                <CompetitionBadge code={group.code} name={group.name} /><Text style={s.cardTitle}>{group.name}</Text>
              </Pressable>
              {group.matches.map((match, index) => <UpcomingGame key={match.id} match={match} last={index === group.matches.length - 1}
                favorites={favoriteIds} bell={followed.has(match.id) || mine(match)} onBell={() => void toggleBell(match)} />)}
            </View>)}
          </View>)}
        </>}
    </ScrollView>
  </SafeAreaView>;
}

/** The live card's background (design: 150° gradient, navy to blue; more muted at half-time). */
const LIVE_GRADIENT = { live: ['#0F2C5C', '#163E80'], paused: ['#13284F', '#1B3566'] };

/** A game being played: dark gradient card, big crests, score and the live / half-time badge. */
function LiveGame({ match }: { match: FootballMatch }) {
  const s = useStyles(makeStyles);
  const paused = match.status === 'PAUSED';
  const [from, to] = LIVE_GRADIENT[paused ? 'paused' : 'live'];
  const team = (name: string, crest?: string | null, tla?: string) => <View style={s.liveTeam}>
    <View style={s.liveCrest}><TeamCrest crest={crest} tla={tla} name={name} size={48} /></View>
    <Text numberOfLines={2} adjustsFontSizeToFit minimumFontScale={.85} style={s.liveName}>{name}</Text>
  </View>;
  return <View accessible accessibilityLabel={`${paused ? 'Intervalo' : 'Ao vivo'}: ${match.home} ${match.home_goals ?? 0}, ${match.away} ${match.away_goals ?? 0}`} style={s.live}>
    <Svg style={StyleSheet.absoluteFill} width="100%" height="100%" preserveAspectRatio="none">
      <Defs><LinearGradient id="live" x1="0.25" y1="0" x2="0.75" y2="1"><Stop offset="0" stopColor={from} /><Stop offset="1" stopColor={to} /></LinearGradient></Defs>
      <Rect width="100%" height="100%" fill="url(#live)" />
    </Svg>
    <View style={s.liveTop}>
      <Text numberOfLines={1} style={s.liveCompetition}>{match.competition?.name}{match.matchday ? ` · Rodada ${match.matchday}` : ''}</Text>
      <View style={[s.liveBadge, paused && s.liveBadgePaused]}><View style={[s.liveBadgeDot, paused && { backgroundColor: '#E2E8F0' }]} /><Text style={s.liveBadgeText}>{paused ? 'INTERVALO' : 'AO VIVO'}</Text></View>
    </View>
    <View style={s.liveScore}>
      {team(match.home, match.home_crest, match.home_tla)}
      <Text style={s.liveGoals}>{match.home_goals ?? 0}<Text style={s.liveSep}> – </Text>{match.away_goals ?? 0}</Text>
      {team(match.away, match.away_crest, match.away_tla)}
    </View>
  </View>;
}

function UpcomingGame({ match, last, favorites, bell, onBell }: { match: FootballMatch; last: boolean; favorites: Set<number>; bell: boolean; onBell: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const line = (name: string, id?: number | null, crest?: string | null, tla?: string) => <View style={s.gameLine}>
    <TeamCrest crest={crest} tla={tla} name={name} size={22} />
    <Text numberOfLines={1} style={[s.gameTeam, favorites.has(id ?? -1) && s.gameTeamMine]}>{name}</Text>
    {favorites.has(id ?? -1) && <Icon name="star" color={colors.sun} size={14} />}
  </View>;
  return <View style={[s.game, !last && s.gameDivider]}>
    <View style={s.gameWhen}><Text style={s.gameTime}>{isLive(match) ? 'AO VIVO' : timeLabel(match.kickoff)}</Text><Text style={s.gameDay}>{dayLabel(match.kickoff).toLowerCase()}</Text></View>
    <View style={{ flex: 1, minWidth: 0, gap: 8 }}>
      {line(match.home, match.home_id, match.home_crest, match.home_tla)}
      {line(match.away, match.away_id, match.away_crest, match.away_tla)}
    </View>
    <Pressable accessibilityRole="switch" accessibilityState={{ checked: bell }} accessibilityLabel={`Avisos do jogo ${match.home} x ${match.away}`} onPress={onBell} hitSlop={6}
      style={[s.bell, bell && s.bellOn]}><Icon name="bell" color={bell ? colors.primary : colors.muted} size={20} /></Pressable>
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { height: 56, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12 },
  headerButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800', color: colors.ink },
  content: { paddingHorizontal: 18, paddingBottom: 40 },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 18, marginBottom: 10 },
  sectionTitle: { fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800', color: colors.ink },
  link: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  linkText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.primary },
  count: { fontFamily: typography.fontFamily.ui, fontSize: 14, color: colors.secondary },
  myTeams: { gap: 14, paddingRight: 6 },
  myTeam: { width: 72, alignItems: 'center', gap: 6 },
  myCrest: { width: 62, height: 62, borderRadius: 31, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.border },
  myCrestLive: { borderColor: '#E11D48', borderWidth: 2.5 },
  addCrest: { borderStyle: 'dashed', borderColor: colors.primary, backgroundColor: colors.surfaceBlue },
  myName: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary, maxWidth: 76, textAlign: 'center' },
  myNameLive: { color: '#E11D48', fontWeight: '800' },
  liveTitle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  liveDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#E11D48' },
  live: { borderRadius: 24, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 16, marginBottom: 12, overflow: 'hidden', backgroundColor: '#0F2C5C',
    shadowColor: '#102B57', shadowOpacity: .45, shadowRadius: 16, shadowOffset: { width: 0, height: 10 }, elevation: 4 },
  liveTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  liveCompetition: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 12.5, fontWeight: '600', color: '#B9CDE6' },
  liveBadge: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: '#E11D48' },
  liveBadgePaused: { backgroundColor: '#55719A' },
  liveBadgeDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#FFFFFF' },
  liveBadgeText: { fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '800', color: '#FFFFFF', letterSpacing: .4 },
  liveScore: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginTop: 14 },
  liveTeam: { width: 108, alignItems: 'center', gap: 8 },
  liveCrest: { width: 52, height: 52, alignItems: 'center', justifyContent: 'center' },
  liveName: { width: '100%', textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 13.5, lineHeight: 17, fontWeight: '700', color: '#FFFFFF' },
  liveGoals: { flex: 1, textAlign: 'center', marginTop: 4, fontFamily: typography.fontFamily.ui, fontSize: 38, fontWeight: '800', letterSpacing: -1, color: '#FFFFFF', fontVariant: ['tabular-nums'] },
  liveSep: { color: '#6F8DB8', fontSize: 28 },
  dayLabel: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '800', letterSpacing: 1, color: colors.secondary, marginTop: 6, marginBottom: 8 },
  card: { borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, paddingTop: 12, paddingBottom: 4, marginBottom: 12 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 34 },
  cardTitle: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.body },
  game: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  gameDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  gameWhen: { width: 56, alignItems: 'center' },
  gameTime: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.ink },
  gameDay: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.muted, marginTop: 1 },
  gameLine: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  gameTeam: { flexShrink: 1, fontFamily: typography.fontFamily.ui, fontSize: 16, color: colors.ink },
  gameTeamMine: { fontWeight: '800' },
  bell: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  bellOn: { backgroundColor: colors.surfaceBlue },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 14, color: colors.secondary, textAlign: 'center', marginTop: 20 },
});
