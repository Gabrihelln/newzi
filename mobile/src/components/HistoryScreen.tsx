import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Platform, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../api/client';
import { getAudioContext, subscribeAudioContext } from '../audio/player';
import { addToQueue, briefingEntry, getQueue, subscribeQueue } from '../audio/queue';
import { downloadBriefing, isBriefingDownloaded } from '../services/offline';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { Briefing, BriefingItem, BriefingSearchResult } from '../types/api';
import {elevation, radius, spacing, typography, useStyles, useTheme, type Palette } from '../theme';
import { BrandPageHeader, ScreenState } from './ScreenPrimitives';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';
import { briefingTitle } from './OnDemandBriefing';

const dateLabelOf = (value: string) => {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
};

export function HistoryScreen({ onBack, onAudio, onDetail }: {
  onBack: () => void;
  onAudio: (briefing: Briefing) => void;
  onDetail?: (item: BriefingItem) => void;
}) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [items, setItems] = useState<Briefing[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [limited, setLimited] = useState<{ days: number; older_count: number } | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [moreError, setMoreError] = useState('');
  const [activeBriefingId, setActiveBriefingId] = useState(getAudioContext()?.briefing.id);
  const [queued, setQueued] = useState<Set<string>>(new Set());
  const [downloads, setDownloads] = useState<Record<string, 'busy' | 'done' | 'pending'>>({});
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<BriefingSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const search = usePremiumFeature('briefing_search');
  const offline = usePremiumFeature('offline_downloads');
  const queue = usePremiumFeature('audio_queue');

  useEffect(() => subscribeAudioContext(session => setActiveBriefingId(session?.briefing.id)), []);
  useEffect(() => subscribeQueue(entries => setQueued(new Set(entries.map(entry => entry.key)))), []);

  const load = useCallback(async (next?: string, retry = false) => {
    if (next) { setLoadingMore(true); setMoreError(''); }
    else if (items.length && !retry) setRefreshing(true);
    else setInitialLoading(true);
    if (!next) setError('');
    try {
      const result = await api.history(10, next);
      setItems(current => next ? [...current, ...(result.items || [])] : (result.items || []));
      setCursor(result.next_cursor || undefined);
      setLimited(result.limited || null);
      setError('');
      setMoreError('');
    } catch {
      if (next) setMoreError('Não foi possível carregar mais edições.');
      else setError('Não foi possível carregar seu histórico agora.');
    } finally {
      setInitialLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [items.length]);

  useEffect(() => { void load(); }, []);
  // Which briefings are already on the phone (only shown where downloads exist).
  useEffect(() => {
    if (!offline.unlocked) return;
    let active = true;
    items.forEach(item => {
      if (!item.id || downloads[item.id]) return;
      void isBriefingDownloaded(item).then(done => { if (active && done) setDownloads(current => ({ ...current, [item.id!]: 'done' })); });
    });
    return () => { active = false; };
  }, [items, offline.unlocked]); // eslint-disable-line react-hooks/exhaustive-deps

  // Search in the past briefings (Premium), as the reader types.
  useEffect(() => {
    const text = query.trim();
    if (text.length < 2 || !search.unlocked) { setResults(null); return; }
    let active = true; setSearching(true);
    const timer = setTimeout(() => api.searchBriefings(text).then(found => { if (active) setResults(found.items); })
      .catch(cause => { if (active) { handlePremiumError(cause); setResults([]); } })
      .finally(() => { if (active) setSearching(false); }), 350);
    return () => { active = false; clearTimeout(timer); };
  }, [query, search.unlocked]);

  const download = async (item: Briefing) => {
    if (!item.id) return;
    if (!offline.unlocked) { requestPremium('offline_downloads'); return; }
    setDownloads(current => ({ ...current, [item.id!]: 'busy' }));
    try { const done = await downloadBriefing(item); setDownloads(current => ({ ...current, [item.id!]: done ? 'done' : 'pending' })); }
    catch { setDownloads(current => { const next = { ...current }; delete next[item.id!]; return next; }); }
  };

  const renderItem = ({ item, index }: { item: Briefing; index: number }) => {
    const dateLabel = dateLabelOf(item.date);
    const title = briefingTitle(item);
    const duration = item.audio_duration_ms ? `${Math.round(item.audio_duration_ms / 60000)} min` : item.audio_status === 'FAILED' ? 'Áudio indisponível' : 'Áudio sendo preparado';
    const progress = item.listening_duration_seconds ? Math.round(100 * (item.listening_progress_seconds || 0) / item.listening_duration_seconds) : 0;
    const active = Boolean(item.id && item.id === activeBriefingId);
    const status = item.completed_at ? 'Concluído' : progress > 0 ? `${Math.min(progress, 99)}% ouvido` : index === 0 ? 'Mais recente' : 'Disponível';
    const imageStory = item.items?.find((story: BriefingItem) => story.image_url);
    const imageUrl = imageStory?.image_url;
    const downloaded = item.id ? downloads[item.id] : undefined;
    const inQueue = queued.has(briefingEntry(item, title).key);
    return <Pressable accessibilityRole="button" accessibilityLabel={`${title}, ${dateLabel}, ${duration}, ${status}`} onPress={() => onAudio(item)} style={[s.row, active && s.activeRow]}>
      <ArticleImage uri={imageUrl} articleId={imageStory?.sources?.find(source => source.article_id)?.article_id || imageStory?.id} accessibilityLabel={`Resumo de ${dateLabel}`} style={s.thumb} />
      <View style={s.rowCopy}>
        <Text numberOfLines={1} style={s.date}>{dateLabel}{item.delivery_time && item.kind && item.kind !== 'SCHEDULED' ? ` · ${item.delivery_time}` : ''}</Text>
        {item.kind && item.kind !== 'SCHEDULED' || item.narration === 'extended' ? <Text numberOfLines={1} style={s.kind}>{title.replace(/^Seu /, '').replace(/^r/, 'R')}{item.narration === 'extended' ? ' · estendido' : ''}</Text> : null}
        <Text style={s.meta}>{duration} · {status}</Text>
        {(offline.visible || queue.visible) && !!item.audio_duration_ms && <View style={s.tools}>
          {offline.visible && <Pressable accessibilityRole="button" accessibilityLabel={downloaded === 'done' ? 'Baixado no aparelho' : 'Baixar para ouvir offline'} disabled={downloaded === 'busy' || downloaded === 'done'} onPress={() => void download(item)} hitSlop={6} style={s.tool}>
            {downloaded === 'busy' ? <ActivityIndicator size="small" color={colors.primary} /> : <Icon name={downloaded === 'done' ? 'downloaded' : 'download'} color={downloaded === 'done' ? colors.success : colors.primary} size={16} />}
            <Text style={[s.toolText, downloaded === 'done' && { color: colors.success }]}>{downloaded === 'done' ? 'Baixado' : downloaded === 'pending' ? 'Em preparo' : 'Baixar'}</Text>
          </Pressable>}
          {queue.visible && <Pressable accessibilityRole="button" accessibilityLabel={inQueue ? 'Já está na fila' : 'Adicionar à fila de áudio'} disabled={inQueue} onPress={() => addToQueue(briefingEntry(item, title))} hitSlop={6} style={s.tool}>
            <Icon name={inQueue ? 'check' : 'queue'} color={colors.primary} size={16} /><Text style={s.toolText}>{inQueue ? 'Na fila' : 'Fila'}</Text>
          </Pressable>}
        </View>}
      </View>
      <View style={[s.playButton, active && s.playActive]}><Icon name={active ? 'pause' : 'play'} color={active ? colors.surface : colors.primary} size={19} /></View>
    </Pressable>;
  };

  const header = <View>
    <BrandPageHeader title="Outros resumos" subtitle="Acesse suas edições anteriores." onBack={onBack} />
    {search.visible && <Pressable disabled={search.unlocked} onPress={() => requestPremium('briefing_search')} style={s.search}>
      <Icon name="search" color={colors.muted} size={19} />
      {search.unlocked ? <TextInput accessibilityLabel="Buscar nos resumos" value={query} onChangeText={setQuery} placeholder="Buscar nos seus resumos" placeholderTextColor={colors.muted} autoCorrect={false} returnKeyType="search" style={s.searchInput} />
        : <Text style={[s.searchInput, { color: colors.muted }]}>Buscar nos seus resumos</Text>}
      {searching ? <ActivityIndicator size="small" color={colors.primary} /> : !!query && <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" onPress={() => setQuery('')} hitSlop={8}><Icon name="close" color={colors.muted} size={17} /></Pressable>}
      {!search.unlocked && <View style={s.premiumTag}><Text style={s.premiumTagText}>PREMIUM</Text></View>}
    </Pressable>}
  </View>;

  if (results) return <SafeAreaView style={s.list} edges={Platform.OS === 'android' ? [] : ['top']}><FlatList
    style={s.list} contentContainerStyle={s.content} data={results} keyExtractor={(item, index) => `${item.briefing_id}:${item.item.id}:${index}`}
    ListHeaderComponent={header}
    ListEmptyComponent={searching ? null : <ScreenState kind="empty" title="Nada encontrado" message="Nenhuma notícia dos seus resumos tem essas palavras." />}
    renderItem={({ item }) => <Pressable accessibilityRole="button" onPress={() => onDetail ? onDetail(item.item) : onAudio({ id: item.briefing_id, date: item.date, status: 'READY', items: [] })} style={s.result}>
      <Text numberOfLines={1} style={s.resultMeta}>{dateLabelOf(item.date)} · {briefingTitle(item).replace(/^Seu /, '')}</Text>
      <Text numberOfLines={2} style={s.resultTitle}>{item.item.headline}</Text>
    </Pressable>} /></SafeAreaView>;

  // The list is the whole screen: on iOS it must start below the notch/Dynamic Island.
  return <SafeAreaView style={s.list} edges={Platform.OS === 'android' ? [] : ['top']}><FlatList
    style={s.list}
    contentContainerStyle={s.content}
    data={items}
    keyExtractor={item => item.id || item.date}
    renderItem={renderItem}
    ListHeaderComponent={header}
    ListEmptyComponent={initialLoading
      ? <ScreenState kind="loading" title="Carregando seu histórico" />
      : error
        ? <ScreenState kind="error" title="Histórico indisponível" message={error} onRetry={() => void load(undefined, true)} />
        : <ScreenState kind="empty" title="Seu histórico está vazio" message="Quando houver outras edições, elas aparecerão aqui." />}
    ListFooterComponent={items.length ? <View style={s.footer}>
      {!!moreError && <Text accessibilityRole="alert" style={s.moreError}>{moreError}</Text>}
      {!!cursor && <Pressable accessibilityRole="button" disabled={loadingMore} onPress={() => void load(cursor)} style={s.moreButton}>
        <Text style={s.moreText}>{loadingMore ? 'Carregando…' : moreError ? 'Tentar novamente' : 'Carregar mais'}</Text>
      </Pressable>}
      {!cursor && limited && <HistoryLimit days={limited.days} older={limited.older_count} />}
    </View> : <View style={{ height: spacing.xxxl }} />}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load()} tintColor={colors.primary} />}
  /></SafeAreaView>;
}

/** The end of a Básico history: the last days are shown; the full history is Premium (where Premium is offered). */
function HistoryLimit({ days, older }: { days: number; older: number }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const full = usePremiumFeature('full_history');
  return <View style={s.limit}>
    <Icon name="calendar" color={colors.primary} size={20} />
    <Text style={s.limitText}>Seu plano mostra os resumos dos últimos {days} dias{older ? `. Há mais ${older} ${older === 1 ? 'resumo anterior' : 'resumos anteriores'}.` : '.'}</Text>
    {full.offered && !!older && <Pressable accessibilityRole="button" onPress={() => requestPremium('full_history')} style={s.limitButton}><Text style={s.limitButtonText}>Ver histórico completo</Text></Pressable>}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.huge, flexGrow: 1 },
  row: { minHeight: 92, flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.md, marginBottom: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, shadowColor: colors.shadow.color, shadowOpacity: colors.shadow.opacity, shadowRadius: colors.shadow.radius, shadowOffset: colors.shadow.offset, elevation: elevation.card },
  activeRow: { borderColor: colors.primary, backgroundColor: colors.surfaceBlue },
  thumb: { width: 62, height: 66, borderRadius: radius.md, backgroundColor: colors.surfaceSoft },
  rowCopy: { flex: 1, minWidth: 0 },
  date: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, lineHeight: 20, fontWeight: '700' },
  kind: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: typography.caption, fontWeight: '700', marginTop: 1 },
  meta: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: typography.caption, lineHeight: 18, marginTop: spacing.xs },
  tools: { flexDirection: 'row', gap: 14, marginTop: 6 },
  tool: { flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 28 },
  toolText: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', color: colors.primary },
  playButton: { width: 44, height: 44, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  playActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  footer: { alignItems: 'center', paddingTop: spacing.sm },
  moreButton: { minHeight: 46, paddingHorizontal: spacing.xl, justifyContent: 'center', alignItems: 'center' },
  moreText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' },
  moreError: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, textAlign: 'center' },
  search: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, paddingHorizontal: 14, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: spacing.md },
  searchInput: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, color: colors.ink, paddingVertical: 8 },
  premiumTag: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, backgroundColor: colors.tone('#FFEFD2', '#3B2A10') },
  premiumTagText: { color: colors.tone('#8A5200', '#FFC56B'), fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  result: { padding: spacing.md, marginBottom: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  resultMeta: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', color: colors.primary },
  resultTitle: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.ink, marginTop: 4, lineHeight: 20 },
  limit: { alignSelf: 'stretch', alignItems: 'center', gap: 8, padding: spacing.lg, marginTop: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surfaceBlue },
  limitText: { fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, color: colors.secondary, textAlign: 'center' },
  limitButton: { minHeight: 42, paddingHorizontal: 18, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  limitButtonText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.onPrimary },
});
