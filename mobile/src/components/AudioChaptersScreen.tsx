import React, { useEffect, useMemo, useRef } from 'react';
import { FlatList, Pressable, SafeAreaView, StatusBar, StyleSheet, Text, View } from 'react-native';
import type { AudioSegment, Briefing, BriefingItem } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { EditionCover, editionDay, editionPeriodLabel } from './EditionCover';
import { Icon } from './Icon';

const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;
const labelFor = (segment: AudioSegment, item?: BriefingItem) => segment.type === 'INTRO' ? 'Abertura' : segment.type === 'OUTRO' ? 'Encerramento' : item?.primary_taxonomy_label || item?.category || item?.headline || 'Notícia';
const periodTitle = (briefing: Briefing) => { const label = editionPeriodLabel(briefing).toLowerCase(); return label[0].toUpperCase() + label.slice(1); };

/**
 * Chapters and transcript of a briefing. Each chapter card is the button: tapping anywhere on it plays the
 * audio from there. Chapters already heard show a green check, the one playing a blue border with its own
 * progress, the next ones their number. The strip on top shows what is playing and pauses without leaving.
 */
export function AudioChaptersScreen({ briefing, segments, position, duration, playing, onClose, onSeek, onPlayChapter, onTogglePlay }: {
  briefing: Briefing; segments: AudioSegment[]; position: number; duration: number; playing: boolean; onClose: () => void;
  onSeek: (seconds: number) => void; onPlayChapter: (seconds: number) => void; onTogglePlay: () => void;
}) {
  const s = useStyles(makeStyles);
  const { colors, statusBar } = useTheme();
  const [tab, setTab] = React.useState<'chapters' | 'transcript'>('chapters');
  const transcriptList = useRef<FlatList<AudioSegment>>(null);
  const currentIndex = useMemo(() => segments.findIndex(segment => segment.segment_start_ms != null && position * 1000 >= segment.segment_start_ms && (segment.segment_end_ms == null || position * 1000 < segment.segment_end_ms)), [segments, position]);
  useEffect(() => { if (tab === 'transcript' && currentIndex >= 0) transcriptList.current?.scrollToIndex({ index: currentIndex, animated: true, viewPosition: .4 }); }, [tab, currentIndex]);
  const itemFor = (segment: AudioSegment) => briefing.items.find(item => item.id === segment.briefing_item_id);
  const startOf = (segment: AudioSegment) => segment.segment_start_ms == null ? null : segment.segment_start_ms / 1000;
  const endOf = (segment: AudioSegment) => segment.segment_end_ms == null ? null : segment.segment_end_ms / 1000;
  const range = (segment: AudioSegment) => startOf(segment) == null ? '' : `${clock(startOf(segment)!)}${endOf(segment) == null ? '' : ` – ${clock(endOf(segment)!)}`}`;
  const current = currentIndex >= 0 ? segments[currentIndex] : null;
  const progress = duration > 0 ? Math.min(1, position / duration) : 0;

  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle={statusBar} backgroundColor={colors.background} />
    <View style={s.topBar}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar ao player" onPress={onClose} style={s.back}><Icon name="chevronDown" color={colors.secondary} size={24} /></Pressable>
      <View style={s.topCopy}><Text accessibilityRole="header" style={s.topTitle}>Capítulos</Text><Text style={s.topDate}>{periodTitle(briefing)} · {editionDay(briefing, false)}</Text></View>
      <View style={s.back} />
    </View>

    <View style={s.nowCard}>
      <EditionCover briefing={briefing} size={58} compact />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.nowMeta}>{playing ? 'Tocando' : 'Pausado'} · {clock(position)} de {clock(duration)}</Text>
        <Text numberOfLines={1} style={s.nowTitle}>{current ? `${labelFor(current, itemFor(current))} · Capítulo ${currentIndex + 1}` : 'Seu resumo do dia'}</Text>
        <View style={s.track}><View style={[s.fill, { width: `${progress * 100}%` }]} /></View>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel={playing ? 'Pausar resumo' : 'Reproduzir resumo'} onPress={onTogglePlay} style={s.nowButton}>
        <Icon name={playing ? 'pause' : 'play'} color={colors.onPrimary} size={22} />
      </Pressable>
    </View>

    <View style={s.tabs}>
      {(['chapters', 'transcript'] as const).map(value => <Pressable key={value} accessibilityRole="tab" accessibilityState={{ selected: tab === value }} onPress={() => setTab(value)} style={[s.tab, tab === value && s.tabOn]}>
        <Text style={[s.tabText, tab === value && s.tabTextOn]}>{value === 'chapters' ? 'Capítulos' : 'Transcrição'}</Text>
      </Pressable>)}
    </View>

    {tab === 'chapters' ? <FlatList
      data={segments} keyExtractor={segment => segment.id} contentContainerStyle={s.list}
      ListHeaderComponent={segments.length ? <View style={s.listHead}><Text style={s.count}>{segments.length} {segments.length === 1 ? 'CAPÍTULO' : 'CAPÍTULOS'}</Text><Text style={s.hint}>Toque para ouvir a partir dele</Text></View> : null}
      ListEmptyComponent={<Text style={s.empty}>Os capítulos ainda não estão disponíveis para este áudio.</Text>}
      renderItem={({ item: segment, index }) => {
        const item = itemFor(segment); const start = startOf(segment); const end = endOf(segment);
        const active = index === currentIndex; const done = currentIndex >= 0 ? index < currentIndex : end != null && position >= end;
        const subtitle = segment.type === 'ITEM' ? item?.headline || segment.script_text || '' : segment.script_text || item?.headline || '';
        const chapterProgress = active && start != null && end != null && end > start ? Math.min(1, (position - start) / (end - start)) : 0;
        return <Pressable accessibilityRole="button" accessibilityState={{ selected: active }} disabled={start == null}
          accessibilityLabel={`Capítulo ${index + 1}, ${labelFor(segment, item)}${active ? ', tocando agora' : done ? ', já ouvido' : ''}. ${range(segment)}. Ouvir a partir dele`}
          onPress={() => onPlayChapter(start!)} style={({ pressed }) => [s.card, active && s.cardActive, pressed && { opacity: .85 }]}>
          <View style={s.row}>
            <View style={[s.badge, done && s.badgeDone, active && s.badgeActive]}>
              {active ? <Icon name="audio" color={colors.onPrimary} size={20} /> : done ? <Icon name="check" color={colors.success} size={18} /> : <Text style={s.number}>{index + 1}</Text>}
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              {active && <View style={s.nowTag}><Text style={s.nowTagText}>TOCANDO AGORA</Text></View>}
              <Text numberOfLines={1} style={[s.title, active && { color: colors.primary }, done && s.titleDone]}>{labelFor(segment, item)}</Text>
              {!!subtitle && <Text numberOfLines={1} style={s.subtitle}>{subtitle}</Text>}
            </View>
            {!!range(segment) && <Text style={s.range}>{range(segment)}</Text>}
          </View>
          {active && start != null && end != null && <View style={s.chapterProgress}>
            <Text style={s.chapterTime}>{clock(position)}</Text>
            <View style={[s.track, { flex: 1, marginTop: 0 }]}><View style={[s.fill, { width: `${chapterProgress * 100}%` }]} /></View>
            <Text style={s.chapterTime}>{clock(end)}</Text>
          </View>}
        </Pressable>;
      }}
    /> : <FlatList
      ref={transcriptList} data={segments.filter(segment => Boolean(segment.script_text?.trim()))} keyExtractor={segment => segment.id}
      contentContainerStyle={s.list} onScrollToIndexFailed={() => undefined}
      ListEmptyComponent={<Text style={s.empty}>A transcrição ainda não está disponível para este áudio.</Text>}
      renderItem={({ item: segment }) => {
        const active = segments[currentIndex]?.id === segment.id; const start = startOf(segment);
        return <Pressable accessibilityRole="button" accessibilityLabel={`Transcrição em ${range(segment)}`} disabled={start == null} onPress={() => onSeek(start!)} style={[s.transcriptRow, active && s.transcriptActive]}>
          <Text style={[s.transcriptTime, active && { color: colors.primary }]}>{start == null ? '—:—' : clock(start)}</Text>
          <View style={{ flex: 1 }}><Text style={[s.transcriptHeading, active && { color: colors.primary }]}>{labelFor(segment, itemFor(segment))}</Text><Text style={s.transcriptText}>{segment.script_text}</Text></View>
        </Pressable>;
      }}
    />}
  </SafeAreaView>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  topBar: { height: 64, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 },
  back: { width: 44, height: 48, justifyContent: 'center' },
  topCopy: { flex: 1, alignItems: 'center' },
  topTitle: { color: colors.ink, fontFamily: typography.fontFamily.ui, fontWeight: '800', fontSize: 19 },
  topDate: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 2 },
  nowCard: { flexDirection: 'row', alignItems: 'center', gap: 14, marginHorizontal: 18, padding: 12, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    shadowColor: colors.shadow.color, shadowOpacity: .12, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 2 },
  nowMeta: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12.5 },
  nowTitle: { color: colors.ink, fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', marginTop: 2 },
  nowButton: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  track: { height: 4, borderRadius: 2, backgroundColor: colors.track, marginTop: 8, overflow: 'hidden' },
  fill: { height: 4, borderRadius: 2, backgroundColor: colors.primary },
  tabs: { flexDirection: 'row', marginHorizontal: 18, marginTop: 16, padding: 4, borderRadius: 18, backgroundColor: colors.tone('#EAF0F7', colors.surfaceSoft) },
  tab: { flex: 1, minHeight: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  tabOn: { backgroundColor: colors.surface, shadowColor: colors.shadow.color, shadowOpacity: .14, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  tabText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600' },
  tabTextOn: { color: colors.ink, fontWeight: '800' },
  list: { paddingHorizontal: 18, paddingTop: 14, paddingBottom: 36, gap: 10 },
  listHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  count: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '800', letterSpacing: 1 },
  hint: { color: colors.muted, fontFamily: typography.fontFamily.ui, fontSize: 12.5 },
  card: { padding: 14, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  cardActive: { borderColor: colors.primary, borderWidth: 1.5, backgroundColor: colors.tone('#F3F8FF', colors.surfaceTint) },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  badge: { width: 46, height: 46, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tone('#F1F5FA', colors.surfaceSoft) },
  badgeDone: { backgroundColor: colors.topicGreen.background },
  badgeActive: { backgroundColor: colors.primary },
  number: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800' },
  nowTag: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: colors.primary, marginBottom: 4 },
  nowTagText: { color: colors.onPrimary, fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '800', letterSpacing: .6 },
  title: { color: colors.ink, fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800' },
  titleDone: { color: colors.secondary },
  subtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13.5, marginTop: 2 },
  range: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '600' },
  chapterProgress: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 14, marginLeft: 60 },
  chapterTime: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' },
  empty: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 14, textAlign: 'center', marginTop: 30 },
  transcriptRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 12, borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  transcriptActive: { borderColor: colors.primary, backgroundColor: colors.tone('#F3F8FF', colors.surfaceTint) },
  transcriptTime: { width: 42, color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' },
  transcriptHeading: { color: colors.ink, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' },
  transcriptText: { color: colors.body, fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 21, marginTop: 4 },
});
