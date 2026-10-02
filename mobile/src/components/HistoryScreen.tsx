import React, { useCallback, useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { getAudioContext, subscribeAudioContext } from '../audio/player';
import type { Briefing, BriefingItem } from '../types/api';
import { colors, elevation, radius, spacing, typography } from '../theme';
import { BrandPageHeader, ScreenState } from './ScreenPrimitives';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';

export function HistoryScreen({ onBack, onAudio }: {
  onBack: () => void;
  onAudio: (briefing: Briefing) => void;
}) {
  const [items, setItems] = useState<Briefing[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [moreError, setMoreError] = useState('');
  const [activeBriefingId, setActiveBriefingId] = useState(getAudioContext()?.briefing.id);

  useEffect(() => subscribeAudioContext(session => setActiveBriefingId(session?.briefing.id)), []);

  const load = useCallback(async (next?: string, retry = false) => {
    if (next) { setLoadingMore(true); setMoreError(''); }
    else if (items.length && !retry) setRefreshing(true);
    else setInitialLoading(true);
    if (!next) setError('');
    try {
      const result = await api.history(10, next);
      setItems(current => next ? [...current, ...(result.items || [])] : (result.items || []));
      setCursor(result.next_cursor || undefined);
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

  const renderItem = ({ item, index }: { item: Briefing; index: number }) => {
    const date = new Date(`${item.date}T12:00:00`);
    const dateLabel = Number.isNaN(date.getTime()) ? item.date : new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
    const duration = item.audio_duration_ms ? `${Math.round(item.audio_duration_ms / 60000)} min` : item.audio_status === 'FAILED' ? 'Áudio indisponível' : 'Áudio sendo preparado';
    const progress = item.listening_duration_seconds ? Math.round(100 * (item.listening_progress_seconds || 0) / item.listening_duration_seconds) : 0;
    const active = Boolean(item.id && item.id === activeBriefingId);
    const status = item.completed_at ? 'Concluído' : progress > 0 ? `${Math.min(progress, 99)}% ouvido` : index === 0 ? 'Mais recente' : 'Disponível';
    const imageStory = item.items?.find((story: BriefingItem) => story.image_url);
    const imageUrl = imageStory?.image_url;
    return <Pressable accessibilityRole="button" accessibilityLabel={`${dateLabel}, ${duration}, ${status}`} onPress={() => onAudio(item)} style={[s.row, active && s.activeRow]}>
      <ArticleImage uri={imageUrl} articleId={imageStory?.sources?.find(source => source.article_id)?.article_id || imageStory?.id} accessibilityLabel={`Briefing de ${dateLabel}`} style={s.thumb} />
      <View style={s.rowCopy}>
        <Text numberOfLines={2} style={s.date}>{dateLabel}</Text>
        <Text style={s.meta}>{duration} · {status}</Text>
      </View>
      <View style={[s.playButton, active && s.playActive]}><Icon name={active ? 'pause' : 'play'} color={active ? colors.surface : colors.primary} size={19} /></View>
    </Pressable>;
  };

  return <FlatList
    style={s.list}
    contentContainerStyle={s.content}
    data={items}
    keyExtractor={item => item.id || item.date}
    renderItem={renderItem}
    ListHeaderComponent={<BrandPageHeader title="Outros briefings" subtitle="Acesse suas edições anteriores." onBack={onBack} />}
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
    </View> : <View style={{ height: spacing.xxxl }} />}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load()} tintColor={colors.primary} />}
  />;
}

const s = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.huge, flexGrow: 1 },
  row: { minHeight: 92, flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.md, marginBottom: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, shadowColor: colors.shadow.color, shadowOpacity: colors.shadow.opacity, shadowRadius: colors.shadow.radius, shadowOffset: colors.shadow.offset, elevation: elevation.card },
  activeRow: { borderColor: colors.primary, backgroundColor: colors.surfaceBlue },
  thumb: { width: 62, height: 66, borderRadius: radius.md, backgroundColor: colors.surfaceSoft },
  rowCopy: { flex: 1, minWidth: 0 },
  date: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, lineHeight: 20, fontWeight: '700' },
  meta: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: typography.caption, lineHeight: 18, marginTop: spacing.xs },
  playButton: { width: 44, height: 44, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  playActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  footer: { alignItems: 'center', paddingTop: spacing.sm },
  moreButton: { minHeight: 46, paddingHorizontal: spacing.xl, justifyContent: 'center', alignItems: 'center' },
  moreText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' },
  moreError: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: typography.bodySmall, textAlign: 'center' },
});
