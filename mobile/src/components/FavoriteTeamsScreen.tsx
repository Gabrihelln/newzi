import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, BackHandler, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { api, ClientError } from '../api/client';
import { PREMIUM_OFFERED } from '../config/store';
import { requestPremium, usePremiumFeature } from '../services/premium';
import type { FootballAlerts, FootballTeam, PremiumFeatureId } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';
import { COMPETITIONS, competitionInfo, TeamCrest } from './FootballParts';
import { SettingSwitch } from './NotificationParts';
import { ScreenState } from './ScreenPrimitives';
import { Badge, Card, IconBox, SaveBar, SectionHeading, SettingsPage, type Tint } from './SettingsKit';

/** Four crests per row that fill the grid exactly (a percentage plus the gaps used to overflow and wrap at three). */
const GRID_COLUMNS = 4, GRID_GAP = 8;
const tileWidth = (width: number) => width > 0 ? Math.floor((width - GRID_GAP * (GRID_COLUMNS - 1)) / GRID_COLUMNS) : '23%';

type AlertRow = { key: keyof FootballAlerts; title: string; text: string; icon: IconName; tint: Tint; premium?: PremiumFeatureId };
const ALERTS: AlertRow[] = [
  { key: 'reminder', title: 'Começa em 15 min', text: 'Um lembrete antes do jogo', icon: 'bell', tint: 'purple', premium: 'team_reminders' },
  { key: 'kickoff', title: 'Início do jogo', text: 'Quando a bola rolar', icon: 'clock', tint: 'blue' },
  { key: 'goals', title: 'Gols', text: 'A cada gol, com o placar', icon: 'ball', tint: 'green' },
  { key: 'final', title: 'Resultado final', text: 'Placar, posição na tabela e, no Premium, o resumo do jogo em áudio', icon: 'article', tint: 'orange' },
  { key: 'news', title: 'Notícias do time', text: 'Quando sair algo importante sobre o seu time', icon: 'bolt', tint: 'red' },
  // The score on the lock screen and Dynamic Island is an iPhone feature (ActivityKit).
  ...(Platform.OS === 'ios' ? [{ key: 'live_activities' as const, title: 'Placar na tela de bloqueio', text: 'O jogo ao vivo na tela de bloqueio e na Dynamic Island', icon: 'phone' as const, tint: 'teal' as const, premium: 'live_activities' as const }] : []),
];

/** Esportes › Times favoritos: search, your teams, a crest grid per competition, the team alerts. Saves at once. */
export function FavoriteTeamsScreen({ onBack }: { onBack: () => void; onSubscription?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [saved, setSaved] = useState<{ ids: number[]; alerts: FootballAlerts } | null>(null);
  const [selected, setSelected] = useState<FootballTeam[]>([]);
  const [alerts, setAlerts] = useState<FootballAlerts>({ kickoff: true, goals: true, final: true, news: true });
  const [limit, setLimit] = useState(1);
  const [competition, setCompetition] = useState('BSA');
  const [grid, setGrid] = useState<FootballTeam[] | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FootballTeam[]>([]);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [gridWidth, setGridWidth] = useState(0);
  const reminders = usePremiumFeature('team_reminders');
  const live = usePremiumFeature('live_activities');
  const rowFeature = (row: AlertRow) => row.premium === 'live_activities' ? live : row.premium ? reminders : null;
  const alertRows = ALERTS.filter(row => !row.premium || rowFeature(row)?.visible);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const favorites = await api.footballFavorites();
      setSelected(favorites.teams); setAlerts(favorites.alerts); setLimit(favorites.limit);
      setSaved({ ids: favorites.teams.map(team => team.id), alerts: favorites.alerts });
      setStatus('loaded');
    } catch { setStatus('error'); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    let active = true; setGrid(null);
    api.footballTeams({ competition }).then(value => { if (active) setGrid(value.teams); }).catch(() => { if (active) setGrid([]); });
    return () => { active = false; };
  }, [competition]);
  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return; }
    let active = true;
    const timer = setTimeout(() => api.footballTeams({ q: query.trim() }).then(value => { if (active) setResults(value.teams); }).catch(() => undefined), 250);
    return () => { active = false; clearTimeout(timer); };
  }, [query]);

  const ids = useMemo(() => selected.map(team => team.id), [selected]);
  const dirty = Boolean(saved && (ids.join(',') !== saved.ids.join(',') || (Object.keys(alerts) as (keyof FootballAlerts)[]).some(key => Boolean(alerts[key]) !== Boolean(saved.alerts[key]))));
  const toggle = (team: FootballTeam) => {
    setError('');
    if (ids.includes(team.id)) { setSelected(current => current.filter(item => item.id !== team.id)); return; }
    if (selected.length >= limit) {
      // Básico follows one team: picking another swaps it; more than one is a Premium feature.
      if (limit === 1) { setSelected([team]); if (PREMIUM_OFFERED) requestPremium('favorite_teams'); return; }
      setError(`Seu plano permite até ${limit} times.`); return;
    }
    setSelected(current => [...current, team]);
  };

  const save = async () => {
    setBusy(true); setError('');
    try {
      const result = await api.saveFootballFavorites({ team_ids: ids, alerts });
      setSelected(result.teams); setAlerts(result.alerts);
      setSaved({ ids: result.teams.map(team => team.id), alerts: result.alerts });
    } catch (cause) {
      setError(cause instanceof ClientError && cause.code === 'FAVORITES_LIMIT' ? 'Seu plano permite só um time favorito.' : 'Não foi possível salvar. Verifique sua conexão e tente de novo.');
    } finally { setBusy(false); }
  };

  const leave = useCallback(() => {
    if (!dirty || busy) { if (!busy) onBack(); return true; }
    Alert.alert('Descartar alterações?', 'Seus times e avisos continuarão como estavam.', [
      { text: 'Continuar editando', style: 'cancel' }, { text: 'Descartar', style: 'destructive', onPress: onBack }]);
    return true;
  }, [dirty, busy, onBack]);
  useEffect(() => { const sub = BackHandler.addEventListener('hardwareBackPress', leave); return () => sub.remove(); }, [leave]);

  const summary = `${selected.length} ${selected.length === 1 ? 'time' : 'times'}`;
  const footer = <SaveBar visible={dirty} busy={busy} onSave={() => void save()} error={error} label="Salvar favoritos" pending={summary} />;
  if (status !== 'loaded') return <SettingsPage title="Times favoritos" onBack={onBack}>
    {status === 'error' ? <ScreenState kind="error" title="Times indisponíveis" message="Não foi possível carregar seus times." onRetry={() => void load()} /> : <ScreenState kind="loading" title="Carregando seus times" />}
  </SettingsPage>;

  const searching = query.trim().length >= 2;
  return <SettingsPage title="Times favoritos" onBack={leave} footer={footer}>
    <View style={s.search}>
      <Icon name="search" color={colors.muted} size={20} />
      <TextInput accessibilityLabel="Buscar time" value={query} onChangeText={setQuery} placeholder="Buscar time" placeholderTextColor={colors.muted} autoCorrect={false} style={s.searchInput} />
      {!!query && <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" onPress={() => setQuery('')} hitSlop={8}><Icon name="close" color={colors.muted} size={18} /></Pressable>}
    </View>
    {searching ? <Card style={{ paddingVertical: 4 }}>
      {!results.length && <Text style={s.empty}>Nenhum time encontrado. Abra um campeonato abaixo para carregar os times dele.</Text>}
      {results.map((team, index) => <TeamRow key={team.id} team={team} last={index === results.length - 1}
        right={<Pressable accessibilityRole="checkbox" accessibilityState={{ checked: ids.includes(team.id) }} accessibilityLabel={team.name} onPress={() => toggle(team)} style={[s.check, ids.includes(team.id) && s.checkOn]}>
          {ids.includes(team.id) && <Icon name="check" color={colors.onPrimary} size={16} />}</Pressable>} />)}
    </Card> : <>
      <SectionHeading title="Seus times" subtitle={PREMIUM_OFFERED && limit === 1 ? 'No plano Básico você acompanha 1 time. Mais times com o Premium.' : undefined} />
      <Card style={{ paddingVertical: 4 }}>
        {!selected.length && <Text style={s.empty}>Escolha um time abaixo para acompanhar jogos, gols e notícias.</Text>}
        {selected.map((team, index) => <TeamRow key={team.id} team={team} last={index === selected.length - 1}
          right={<Pressable accessibilityRole="button" accessibilityLabel={`Remover ${team.name}`} onPress={() => toggle(team)} style={s.remove}><Icon name="close" color={colors.danger} size={16} /></Pressable>} />)}
      </Card>

      <View style={s.gridHead}>
        <Text accessibilityRole="header" style={s.gridTitle}>{competitionInfo(competition).name}</Text>
        <Pressable accessibilityRole="button" onPress={() => setPicking(true)} hitSlop={8} style={s.other}><Text style={s.otherText}>Outros campeonatos</Text><Icon name="chevronDown" color={colors.primary} size={16} /></Pressable>
      </View>
      {!grid ? <ActivityIndicator color={colors.primary} style={{ marginVertical: 20 }} />
        : !grid.length ? <Text style={s.empty}>Times indisponíveis para este campeonato agora.</Text>
        : <View style={s.grid} onLayout={event => setGridWidth(event.nativeEvent.layout.width)}>{grid.map(team => {
          const on = ids.includes(team.id);
          return <Pressable key={team.id} accessibilityRole="checkbox" accessibilityState={{ checked: on }} accessibilityLabel={team.name} onPress={() => toggle(team)}
            style={[s.tile, { width: tileWidth(gridWidth) }, on && s.tileOn]}>
            {on && <View style={s.tileCheck}><Icon name="check" color={colors.onPrimary} size={12} /></View>}
            <TeamCrest crest={team.crest} tla={team.tla} name={team.name} size={40} />
            <Text numberOfLines={1} style={[s.tileName, on && { color: colors.primary }]}>{team.name}</Text>
          </Pressable>;
        })}</View>}
    </>}

    <SectionHeading title="Avisos dos seus times" subtitle="Também valem para os jogos em que você tocar no sino." />
    <Card style={{ paddingVertical: 4 }}>
      {alertRows.map((item, index) => {
        const locked = item.premium && !rowFeature(item)?.unlocked;
        return <View key={item.key} style={[s.alert, index < alertRows.length - 1 && s.alertDivider]}>
          <IconBox icon={item.icon} tint={item.tint} size={44} />
          <View style={{ flex: 1 }}><Text style={s.alertTitle}>{item.title}</Text><Text style={s.alertText}>{item.text}</Text></View>
          {locked ? <Pressable accessibilityRole="button" accessibilityLabel={`${item.title}. Recurso Premium`} onPress={() => requestPremium(item.premium!)} hitSlop={8}><Badge label="PREMIUM" tint="orange" /></Pressable>
            : <SettingSwitch label={item.title} value={alerts[item.key] !== false} onChange={value => setAlerts(current => ({ ...current, [item.key]: value }))} />}
        </View>;
      })}
    </Card>
    <Text style={s.note}>Os avisos chegam se as notificações do Newzi estiverem ligadas (Perfil › Notificações).</Text>

    <Modal visible={picking} transparent animationType="fade" onRequestClose={() => setPicking(false)}>
      <Pressable accessibilityLabel="Fechar" onPress={() => setPicking(false)} style={s.scrim}>
        <Pressable onPress={() => undefined} style={s.sheet}>
          <Text accessibilityRole="header" style={s.sheetTitle}>Campeonatos</Text>
          <ScrollView style={{ maxHeight: 420 }}>{COMPETITIONS.map(item => <Pressable key={item.code} accessibilityRole="radio" accessibilityState={{ checked: item.code === competition }}
            onPress={() => { setCompetition(item.code); setPicking(false); }} style={s.option}>
            <Text style={[s.optionText, item.code === competition && { color: colors.primary }]}>{item.name}</Text>
            {item.code === competition && <Icon name="check" color={colors.primary} size={18} />}
          </Pressable>)}</ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  </SettingsPage>;
}

function TeamRow({ team, right, last }: { team: FootballTeam; right: React.ReactNode; last: boolean }) {
  const s = useStyles(makeStyles);
  return <View style={[s.teamRow, !last && s.alertDivider]}>
    <TeamCrest crest={team.crest} tla={team.tla} name={team.name} size={36} />
    <View style={{ flex: 1, minWidth: 0 }}>
      <Text numberOfLines={1} style={s.teamName}>{team.name}</Text>
      {!!team.competitions.length && <Text numberOfLines={1} style={s.teamMeta}>{team.competitions.map(item => item.name).join(' · ')}</Text>}
    </View>
    {right}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  search: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 54, paddingHorizontal: 16, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  searchInput: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, color: colors.ink, paddingVertical: 10 },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: colors.secondary, paddingVertical: 14, textAlign: 'center' },
  teamRow: { flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 64, paddingVertical: 8 },
  teamName: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  teamMeta: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary, marginTop: 2 },
  remove: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.dangerSurface },
  check: { width: 26, height: 26, borderRadius: 8, borderWidth: 1.6, borderColor: colors.borderStrong, alignItems: 'center', justifyContent: 'center' },
  checkOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  gridHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 24, marginBottom: 12 },
  gridTitle: { fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800', color: colors.ink },
  other: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  otherText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.primary },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: GRID_GAP },
  tile: { minHeight: 96, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 4 },
  tileOn: { borderColor: colors.primary, borderWidth: 2, backgroundColor: colors.tone('#F2F8FF', colors.surfaceTint) },
  tileCheck: { position: 'absolute', top: 6, right: 6, width: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  tileName: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', color: colors.ink },
  alert: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 12 },
  alertDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  alertTitle: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  alertText: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary, marginTop: 2 },
  note: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.muted, marginTop: 10 },
  scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, paddingBottom: 30 },
  sheetTitle: { fontFamily: typography.fontFamily.ui, fontSize: 17, fontWeight: '800', color: colors.ink, marginBottom: 8 },
  option: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: colors.divider },
  optionText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.ink },
});
