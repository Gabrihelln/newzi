import React, { useMemo, useRef, useEffect } from 'react';
import { FlatList, Pressable, SafeAreaView, StatusBar, Text, View } from 'react-native';
import type { Briefing, BriefingItem, AudioSegment } from '../types/api';
import { colors, typography } from '../theme';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';
const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;
const labelFor = (segment: AudioSegment, item?: BriefingItem) => segment.type === 'INTRO' ? 'Abertura' : segment.type === 'OUTRO' ? 'Encerramento' : item?.primary_taxonomy_label || item?.category || item?.headline || 'Notícia';

export function AudioChaptersScreen({ briefing, segments, position, playing, onClose, onSeek, onPlayChapter }: {
  briefing: Briefing; segments: AudioSegment[]; position: number; playing: boolean; onClose: () => void; onSeek: (seconds: number) => void; onPlayChapter: (seconds: number) => void;
}) {
  const [tab, setTab] = React.useState<'chapters' | 'transcript'>('chapters');
  const transcriptList = useRef<FlatList<AudioSegment>>(null);
  const currentIndex = useMemo(() => segments.findIndex(segment => segment.segment_start_ms != null && position * 1000 >= segment.segment_start_ms && (segment.segment_end_ms == null || position * 1000 < segment.segment_end_ms)), [segments, position]);
  useEffect(() => { if (tab === 'transcript' && currentIndex >= 0) transcriptList.current?.scrollToIndex({ index: currentIndex, animated: true, viewPosition: .4 }); }, [tab, currentIndex]);
  const itemFor = (segment: AudioSegment) => briefing.items.find(item => item.id === segment.briefing_item_id);
  const timeRange = (segment: AudioSegment) => segment.segment_start_ms == null ? 'Tempo indisponível' : `${clock(segment.segment_start_ms / 1000)}${segment.segment_end_ms == null ? '' : ` - ${clock(segment.segment_end_ms / 1000)}`}`;

  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <View style={s.topBar}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar ao player" onPress={onClose} style={s.back}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.textPrimary} size={20} /></View></Pressable>
      <View style={s.topCopy}><Text style={s.topTitle}>Briefing diário</Text><Text style={s.topDate}>{dateLabel(briefing.date)}</Text></View>
      <View style={s.back} />
    </View>
    <View style={s.tabs}>
      <Pressable accessibilityRole="tab" accessibilityState={{ selected: tab === 'chapters' }} onPress={() => setTab('chapters')} style={[s.tab, tab === 'chapters' && s.activeTab]}><Text style={[s.tabText, tab === 'chapters' && s.activeTabText]}>Capítulos</Text></Pressable>
      <Pressable accessibilityRole="tab" accessibilityState={{ selected: tab === 'transcript' }} onPress={() => setTab('transcript')} style={[s.tab, tab === 'transcript' && s.activeTab]}><Text style={[s.tabText, tab === 'transcript' && s.activeTab && s.activeTabText]}>Transcrição</Text></Pressable>
    </View>
    {tab === 'chapters' ? <FlatList
      data={segments} keyExtractor={segment => segment.id} contentContainerStyle={s.list}
      ListEmptyComponent={<Text style={s.empty}>Os capítulos ainda não estão disponíveis para este áudio.</Text>}
      renderItem={({ item: segment, index }) => {
        const item = itemFor(segment); const start = segment.segment_start_ms; const active = currentIndex === index;
        const description = item?.summary || segment.script_text || '';
        return <View style={[s.chapterRow, active && s.chapterActive]}>
          <ArticleImage uri={item?.image_url} articleId={item?.sources?.find(source => source.article_id)?.article_id || item?.id} accessibilityLabel={item?.headline || labelFor(segment, item)} style={s.thumb} />
          <View style={s.number}><Text style={[s.numberText, active && s.activeText]}>{index + 1}</Text></View>
          <Pressable accessibilityRole="button" accessibilityLabel={`Ir para ${labelFor(segment, item)}, ${timeRange(segment)}`} disabled={start == null} onPress={() => onSeek(start! / 1000)} style={s.chapterCopy}>
            <Text numberOfLines={1} style={[s.chapterTitle, active && s.activeText]}>{labelFor(segment, item)}</Text>
            {!!description && <Text numberOfLines={2} style={s.chapterDescription}>{description}</Text>}
            <Text style={s.chapterTime}>{timeRange(segment)}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={`${active && playing ? 'Tocar' : 'Reproduzir'} capítulo ${index + 1}`} disabled={start == null} onPress={() => onPlayChapter(start! / 1000)} style={s.playButton}>
            <Icon name={active && playing ? 'pause' : 'play'} color={colors.primary} size={17} />
          </Pressable>
        </View>;
      }}
    /> : <FlatList
      ref={transcriptList} data={segments.filter(segment => Boolean(segment.script_text?.trim()))} keyExtractor={segment => segment.id}
      contentContainerStyle={s.list} onScrollToIndexFailed={() => undefined}
      ListEmptyComponent={<Text style={s.empty}>A transcrição ainda não está disponível para este áudio.</Text>}
      renderItem={({ item: segment, index }) => {
        const active = segments[currentIndex]?.id === segment.id; const start = segment.segment_start_ms;
        return <Pressable accessibilityRole="button" accessibilityLabel={`Transcrição em ${timeRange(segment)}`} disabled={start == null} onPress={() => onSeek(start! / 1000)} style={[s.transcriptRow, active && s.transcriptActive]}>
          <Text style={[s.transcriptTime, active && s.activeText]}>{start == null ? '—:—' : clock(start / 1000)}</Text>
          <View style={s.transcriptCopy}><Text style={[s.transcriptHeading, active && s.activeText]}>{labelFor(segment, itemFor(segment))}</Text><Text style={s.transcriptText}>{segment.script_text}</Text></View>
        </Pressable>;
      }}
    />}
  </SafeAreaView>;
}

function dateLabel(value: string) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}

const s = {
  safe: { flex: 1, backgroundColor: colors.background } as const,
  topBar: { height: 66, flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 18 },
  back: { width: 44, height: 48, justifyContent: 'center' as const }, backGlyph: { fontSize: 33, color: colors.textPrimary, lineHeight: 36 },
  topCopy: { flex: 1, alignItems: 'center' as const }, topTitle: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 15 }, topDate: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 3 },
  tabs: { height: 48, flexDirection: 'row' as const, marginHorizontal: 22, borderBottomWidth: 1, borderColor: '#E4EDF7' }, tab: { flex: 1, alignItems: 'center' as const, justifyContent: 'center' as const, borderBottomWidth: 2, borderBottomColor: 'transparent' }, activeTab: { borderBottomColor: colors.primary }, tabText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12 }, activeTabText: { color: colors.primary, fontWeight: '800' as const },
  list: { paddingHorizontal: 17, paddingTop: 8, paddingBottom: 36 }, chapterRow: { minHeight: 98, flexDirection: 'row' as const, alignItems: 'center' as const, borderBottomWidth: 1, borderColor: '#E4EDF7', paddingVertical: 8, gap: 8 }, chapterActive: { backgroundColor: '#EEF7FF', borderRadius: 14, paddingHorizontal: 7 }, thumb: { width: 54, height: 62, borderRadius: 9, backgroundColor: '#EAF3FB' }, number: { width: 20, height: 20, borderRadius: 12, backgroundColor: '#E9F2FC', alignItems: 'center' as const, justifyContent: 'center' as const }, numberText: { color: colors.secondary, fontSize: 10, fontWeight: '800' as const }, chapterCopy: { flex: 1, minWidth: 0, justifyContent: 'center' as const, paddingVertical: 2 }, chapterTitle: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700' as const }, chapterDescription: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, lineHeight: 15, marginTop: 3 }, chapterTime: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 10, marginTop: 3 }, activeText: { color: colors.primary, fontWeight: '800' as const }, playButton: { width: 40, height: 44, borderRadius: 24, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary }, playGlyph: { color: '#FFFFFF', fontSize: 15, fontWeight: '800' as const }, empty: { textAlign: 'center' as const, color: colors.secondary, padding: 28, fontFamily: typography.fontFamily.ui },
  transcriptRow: { flexDirection: 'row' as const, alignItems: 'flex-start' as const, gap: 12, paddingHorizontal: 10, paddingVertical: 14, borderBottomWidth: 1, borderColor: '#E5EFF8', borderRadius: 13 }, transcriptActive: { backgroundColor: '#EDF7FF' }, transcriptTime: { color: colors.secondary, width: 42, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 11, paddingTop: 2 }, transcriptCopy: { flex: 1, gap: 4 }, transcriptHeading: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 12 }, transcriptText: { color: '#526B90', fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 20 },
};
