import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Image, Pressable, RefreshControl, SafeAreaView, ScrollView, StatusBar, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView as InsetsView } from 'react-native-safe-area-context';
import { api } from '../api/client';
import { firebaseAuth } from '../services/firebaseAuth';
import { getAudioContext } from '../audio/player';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';
import { colorFor, TopicGlyph } from './ExploreScreen';
import { colors, typography } from '../theme';
import type { Briefing, BriefingItem, SavedArticle, SavedOverview, SavedOverviewItem, SavedTopicSummary } from '../types/api';

const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const fallback = require('../../assets/onboarding/new-waving.png');
const cover = require('../../assets/onboarding/new-sunrise.png');
type SavedScreenProps = { onDetail: (item: BriefingItem, progress?: number) => void; onAudio: (briefing: Briefing) => void; onSearch: () => void; onProfile: () => void; onSeeAll: () => void; onSeeTopics: () => void; onTopic: (topic: SavedTopicSummary) => void; refreshOnFocus?: boolean };

const wordsPerMinute = (item: BriefingItem) => item.reading_time_minutes && item.reading_time_minutes > 0 ? item.reading_time_minutes : Math.max(1, Math.ceil(`${item.headline || ''} ${item.summary || ''}`.trim().split(/\s+/).filter(Boolean).length / 200));
function topicTone(topic: SavedTopicSummary, index: number) {
  const key = `${topic.id} ${topic.name}`.toLocaleLowerCase('pt-BR');
  if (/tech|tecnolog|digital/.test(key)) return { background: '#E6F2FF', color: '#087CF0' };
  if (/econom|finan|mercado/.test(key)) return { background: '#FFF3DF', color: '#F3920B' };
  if (/pol[ií]tic|governo|elei/.test(key)) return { background: '#FDEBF0', color: '#EA3657' };
  if (/sa[uú]de|medicin|bem-estar/.test(key)) return { background: '#FCEAF1', color: '#DB4380' };
  if (/ambiente|clima|natureza/.test(key)) return { background: '#E8F8F0', color: '#11A968' };
  if (topic.id === '__OTHER__') return { background: '#E8F2FF', color: '#46618E' };
  const tones = [{ background: '#EFEAFF', color: '#8355DF' }, { background: '#E7F7F5', color: '#198D88' }, { background: '#FFF0E8', color: '#DB713B' }];
  return tones[index % tones.length];
}

function SavedHeader({ onSearch, onProfile }: { onSearch: () => void; onProfile: () => void }) {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const avatar = firebaseAuth.currentUser?.photoURL;
  return <View style={s.header}>
    <Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={s.logo} />
    <View style={s.headerActions}>
      <Pressable accessibilityRole="button" accessibilityLabel="Buscar notícias" onPress={onSearch} style={s.headerIcon}><Icon name="search" size={24} color="#132950" /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir perfil" onPress={onProfile} style={s.avatarButton}>
        {avatar && !avatarFailed ? <Image source={{ uri: avatar }} onError={() => setAvatarFailed(true)} resizeMode="cover" style={s.avatar} /> : <Image source={fallback} resizeMode="cover" style={s.avatar} />}
      </Pressable>
    </View>
  </View>;
}

function SectionTitle({ title, onAll }: { title: string; onAll?: () => void }) {
  return <View style={s.sectionTitleRow}><Text style={s.sectionTitle}>{title}</Text>{onAll && <Pressable accessibilityRole="button" accessibilityLabel={`Ver todos: ${title}`} onPress={onAll} hitSlop={8} style={s.allLink}><Text style={s.allText}>Ver todos</Text><Icon name="chevron" size={16} color={colors.primary} /></Pressable>}</View>;
}

function SavedImage({ uri, articleId, style }: { uri?: string | null; articleId?: string; style: any }) {
  return <ArticleImage uri={uri} articleId={articleId} style={style} />;
}

function ContinueReadingCard({ item, onContinue }: { item: SavedArticle | null; onContinue: (item: SavedArticle) => void }) {
  if (!item) return <View style={s.continueEmpty}><View style={s.emptyGlyph}><Icon name="bookmark" size={24} color={colors.primary} /></View><View style={{ flex: 1 }}><Text style={s.continueEmptyTitle}>Você ainda não começou nenhum conteúdo salvo.</Text><Text style={s.continueEmptyText}>Quando iniciar uma notícia salva, seu progresso aparecerá aqui.</Text></View></View>;
  const progress = Math.max(0, Math.min(100, item.reading_progress || 0));
  const category = item.primary_taxonomy_label || item.category || 'Notícias';
  return <Pressable accessibilityRole="button" accessibilityLabel={`Continuar lendo ${item.headline}, ${progress}% lido, ${wordsPerMinute(item)} minutos`} onPress={() => onContinue(item)} style={s.continueCard}>
    <SavedImage uri={item.image_url} articleId={item.id} style={s.continueImage} />
    <View style={s.continueCopy}>
      <Text numberOfLines={1} style={s.categoryBadge}>{category.toLocaleUpperCase('pt-BR')}</Text>
      <Text numberOfLines={2} style={s.continueHeadline}>{item.headline}</Text>
      <View style={s.progressLine}><Text style={s.progressPercent}>{Math.round(progress)}%</Text><Text style={s.continueMinutes}>{wordsPerMinute(item)} min</Text></View>
      <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: progress }} style={s.progressTrack}><View style={[s.progressFill, { width: `${progress}%` }]} /></View>
    </View>
    <View style={s.continueButton}><Icon name="play" size={21} color={colors.primary} /></View>
  </Pressable>;
}

function TopicCard({ topic, index, width, onPress }: { topic: SavedTopicSummary; index: number; width: number; onPress: () => void }) {
  const palette = colorFor(index);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${topic.name}, ${topic.count} notícias salvas`} onPress={onPress} style={[s.topicCard, { width, backgroundColor: palette.background }]}>
    <TopicGlyph topic={{ code: topic.id, name: topic.name, order: topic.order }} index={topic.order} size={58} />
    <Text numberOfLines={2} style={s.topicName}>{topic.name}</Text><Text style={s.topicCount}>{topic.count} {topic.count === 1 ? 'notícia' : 'notícias'}</Text>
  </Pressable>;
}

function RecentCard({ entry, width, onDetail, onAudio }: { entry: SavedOverviewItem; width: number; onDetail: (item: BriefingItem, progress?: number) => void; onAudio: (briefing: Briefing) => void }) {
  if (entry.type === 'briefing') {
    const briefing = entry.briefing;
    return <Pressable accessibilityRole="button" accessibilityLabel={`Briefing salvo de ${briefing.date}, ouvir`} onPress={() => onAudio(briefing)} style={[s.recentCard, { width }]}>
      <SavedImage uri={briefing.items.find(item => item.image_url)?.image_url} articleId={briefing.items.find(item => item.image_url)?.sources?.find(source => source.article_id)?.article_id || briefing.items.find(item => item.image_url)?.id} style={s.recentImage} />
      <View style={s.recentCopy}><View style={s.recentMeta}><Text style={s.briefingBadge}>BRIEFING</Text><Text style={s.recentMinutes}>{briefing.audio_duration_ms ? `${Math.round(briefing.audio_duration_ms / 60000)} min` : `${briefing.items.length} notícias`}</Text></View><Text numberOfLines={2} style={s.recentHeadline}>Briefing de {briefing.date}</Text></View>
    </Pressable>;
  }
  const item = entry.item;
  const tone = topicTone({ id: item.primary_taxonomy_id || '', name: item.primary_taxonomy_label || item.category || '' , count: 0, order: 0 }, item.position || 0);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${item.headline}, ${item.primary_taxonomy_label || item.category || 'Notícias'}`} onPress={() => onDetail(item, entry.reading_progress)} style={[s.recentCard, { width }]}>
    <SavedImage uri={item.image_url} articleId={item.id} style={s.recentImage} />
    <View style={s.recentCopy}><View style={s.recentMeta}><Text numberOfLines={1} style={[s.categoryBadge, { backgroundColor: tone.background, color: tone.color }]}>{(item.primary_taxonomy_label || item.category || 'Notícias').toLocaleUpperCase('pt-BR')}</Text><Text style={s.recentMinutes}>{wordsPerMinute(item)} min</Text></View><Text numberOfLines={2} style={s.recentHeadline}>{item.headline}</Text></View>
  </Pressable>;
}

function SavedSkeleton() {
  return <View><View style={s.countSkeleton} /><SectionTitle title="Continuar lendo" /><View style={[s.skeletonCard, { height: 154 }]} /><SectionTitle title="Organizados por assunto" /><View style={s.skeletonGrid}>{Array.from({ length: 6 }, (_, index) => <View key={index} style={[s.skeletonTopic, { width: '31%' }]} />)}</View><SectionTitle title="Salvos recentemente" /><View style={s.skeletonRecent}>{[1, 2].map(value => <View key={value} style={[s.skeletonCard, { width: 190, height: 216 }]} />)}</View></View>;
}

export function SavedScreen({ onDetail, onAudio, onSearch, onProfile, onSeeAll, onSeeTopics, onTopic, refreshOnFocus = true }: SavedScreenProps) {
  const bottomPadding = useFloatingTabContentInset(true);
  const { width } = useWindowDimensions();
  const [overview, setOverview] = useState<SavedOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { setOverview(await api.savedOverview()); }
    catch { setError('Não foi possível carregar seus salvos.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { if (refreshOnFocus) void load(); }, [refreshOnFocus, load]);
  const refresh = () => { setRefreshing(true); void load(); };
  const stories = overview?.saved_count || 0;
  const topics = useMemo(() => (overview?.topic_summary || []).filter(topic => topic.count > 0).slice(0, 6), [overview?.topic_summary]);
  const topicWidth = Math.floor((width - 44 - 20) / 3);
  const recentWidth = Math.min(216, Math.max(168, (width - 54) * .52));
  const continueItem = overview?.continue_reading as SavedArticle | null | undefined;
  const continueWithAudio = useMemo(() => {
    const session = getAudioContext();
    const saved = overview?.recent_items.find((entry): entry is Extract<SavedOverviewItem, { type: 'briefing' }> => entry.type === 'briefing' && entry.briefing.id === session?.briefing.id);
    return saved?.briefing || null;
  }, [overview]);
  return <InsetsView style={s.safe} edges={['top']}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <ScrollView contentContainerStyle={[s.content, { paddingBottom: bottomPadding }]} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.primary} />}>
      <SavedHeader onSearch={onSearch} onProfile={onProfile} />
      <View style={s.titleRow}><View style={s.titleCopy}><Text style={s.pageTitle}>Seus salvos</Text><Text style={s.pageSubtitle}>Continue de onde parou.</Text></View><View style={s.countPill}><Text style={s.countText}>{stories} {stories === 1 ? 'notícia' : 'notícias'}</Text></View></View>
      {loading ? <SavedSkeleton /> : error ? <View style={s.errorCard}><Text style={s.errorText}>{error}</Text><Pressable accessibilityRole="button" onPress={() => void load()}><Text style={s.retry}>Tentar novamente</Text></Pressable></View> : !stories && !overview?.recent_items.length ? <View style={s.emptyCard}><View style={s.emptyGlyph}><Icon name="bookmark" size={30} color={colors.primary} /></View><Text style={s.emptyTitle}>Você ainda não salvou nada.</Text><Text style={s.emptySubtitle}>Salve notícias e briefings para encontrar tudo aqui depois.</Text></View> : <>
        <SectionTitle title="Continuar lendo" />
        {continueWithAudio && !continueItem ? <Pressable accessibilityRole="button" accessibilityLabel={`Continuar briefing de ${continueWithAudio.date}`} onPress={() => onAudio(continueWithAudio)} style={s.continueEmpty}><View style={s.emptyGlyph}><Icon name="audio" size={24} color={colors.primary} /></View><View style={{ flex: 1 }}><Text style={s.continueEmptyTitle}>Continuar briefing de {continueWithAudio.date}</Text><Text style={s.continueEmptyText}>Retome a reprodução na posição atual.</Text></View><Icon name="play" size={20} color={colors.primary} /></Pressable> : <ContinueReadingCard item={continueItem || null} onContinue={item => onDetail(item, item.reading_progress)} />}
        <SectionTitle title="Organizados por assunto" onAll={onSeeTopics} />
        {topics.length ? <View style={s.topicGrid}>{topics.map((topic, index) => <TopicCard key={topic.id} topic={topic} index={index} width={topicWidth} onPress={() => onTopic(topic)} />)}</View> : <Text style={s.sectionEmpty}>Seus assuntos salvos aparecerão aqui.</Text>}
        <SectionTitle title="Salvos recentemente" onAll={onSeeAll} />
        {overview?.recent_items.length ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.recentList}>{overview.recent_items.slice(0, 8).map((entry, index) => <RecentCard key={entry.type === 'article' ? `article-${entry.item.id}` : `briefing-${entry.briefing.id || entry.briefing.date}-${index}`} entry={entry} width={recentWidth} onDetail={onDetail} onAudio={onAudio} />)}</ScrollView> : <Text style={s.sectionEmpty}>Nenhum item recente.</Text>}
      </>}
    </ScrollView>
  </InsetsView>;
}

export function SavedTopicsScreen({ onBack, onSelect }: { onBack: () => void; onSelect: (topic: SavedTopicSummary) => void }) {
  const { width } = useWindowDimensions();
  const [topics, setTopics] = useState<SavedTopicSummary[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const load = useCallback(() => { setLoading(true); api.savedOverview().then(value => setTopics(value.topic_summary)).catch(() => setError('Não foi possível carregar os assuntos salvos.')).finally(() => setLoading(false)); }, []);
  useEffect(() => { load(); }, [load]);
  const cardWidth = Math.floor((width - 52) / 3);
  return <SafeAreaView style={s.safe}><StatusBar barStyle="dark-content" backgroundColor={colors.background} /><ScrollView contentContainerStyle={s.secondaryContent}><SecondaryHeader title="Assuntos salvos" onBack={onBack} />{loading ? <SavedSkeleton /> : error ? <View style={s.errorCard}><Text style={s.errorText}>{error}</Text><Pressable onPress={load}><Text style={s.retry}>Tentar novamente</Text></Pressable></View> : <View style={s.topicGrid}>{topics.filter(topic => topic.count > 0).map((topic, index) => <TopicCard key={topic.id} topic={topic} index={index} width={cardWidth} onPress={() => onSelect(topic)} />)}</View>}</ScrollView></SafeAreaView>;
}

export function SavedContentScreen({ onBack, topic, onDetail, onAudio }: { onBack: () => void; topic?: SavedTopicSummary; onDetail: (item: BriefingItem, progress?: number) => void; onAudio: (briefing: Briefing) => void }) {
  const [items, setItems] = useState<SavedArticle[]>([]); const [briefings, setBriefings] = useState<Briefing[]>([]); const [cursor, setCursor] = useState<string>(); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async (next?: string) => { setLoading(true); try { const [page, saved] = await Promise.all([api.savedStoriesPage(40, next, topic?.id), api.savedBriefings()]); setItems(old => next ? [...old, ...(page.items as SavedArticle[])] : page.items as SavedArticle[]); setCursor(page.next_cursor || undefined); setBriefings(topic ? saved.items.filter(briefing => topic.id === '__OTHER__' ? briefing.items.some(item => !item.primary_taxonomy_id && !item.primary_taxonomy_label) : briefing.items.some(item => item.primary_taxonomy_id === topic.id)) : saved.items); setError(''); } catch { setError('Não foi possível carregar os salvos.'); } finally { setLoading(false); setRefreshing(false); } }, [topic?.id]);
  useEffect(() => { void load(); }, [load]);
  const remove = async (item: BriefingItem) => { setItems(current => current.filter(saved => saved.id !== item.id)); try { await api.removeSavedStory(item.id); } catch { void load(); } };
  return <SafeAreaView style={s.safe}><StatusBar barStyle="dark-content" backgroundColor={colors.background} /><FlatList data={items} keyExtractor={item => item.id} contentContainerStyle={s.secondaryContent} ListHeaderComponent={<><SecondaryHeader title={topic?.name || 'Todos os salvos'} onBack={onBack} />{briefings.length > 0 && <Text style={s.groupLabel}>Briefings salvos</Text>}</>} ListEmptyComponent={loading ? <SavedSkeleton /> : error ? <View style={s.errorCard}><Text style={s.errorText}>{error}</Text><Pressable onPress={() => void load()}><Text style={s.retry}>Tentar novamente</Text></Pressable></View> : !briefings.length ? <View style={s.emptyCard}><Text style={s.emptyTitle}>Nenhum conteúdo salvo.</Text></View> : null} renderItem={({ item }) => <SavedArticleRow item={item} onPress={() => onDetail(item, item.reading_progress)} onRemove={() => void remove(item)} />} ListFooterComponent={<>{briefings.map(briefing => <Pressable key={briefing.id || briefing.date} accessibilityRole="button" onPress={() => onAudio(briefing)} style={s.listBriefing}><Image source={cover} style={s.listThumb} /><View style={{ flex: 1 }}><Text style={s.listHeadline}>Briefing de {briefing.date}</Text><Text style={s.listMeta}>{briefing.items.length} notícias · toque para ouvir</Text></View><Icon name="play" color={colors.primary} /></Pressable>)}{cursor && <Pressable accessibilityRole="button" disabled={loading} onPress={() => void load(cursor)} style={s.loadMore}><Text style={s.allText}>{loading ? 'Carregando…' : 'Carregar mais'}</Text></Pressable>}</>} onRefresh={() => { setRefreshing(true); void load(); }} refreshing={refreshing} /></SafeAreaView>;
}

function SecondaryHeader({ title, onBack }: { title: string; onBack: () => void }) { return <View style={s.secondaryHeader}><Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={s.backButton}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" size={21} color={colors.textPrimary} /></View></Pressable><Text numberOfLines={1} style={s.secondaryTitle}>{title}</Text><View style={{ width: 42 }} /></View>; }
function SavedArticleRow({ item, onPress, onRemove }: { item: SavedArticle; onPress: () => void; onRemove: () => void }) { const category=item.primary_taxonomy_label || item.category || 'Notícias'; return <View style={s.articleRow}><Pressable accessibilityRole="button" accessibilityLabel={item.headline} onPress={onPress} style={s.articlePress}><SavedImage uri={item.image_url} articleId={item.id} style={s.listThumb} /><View style={{ flex: 1 }}><Text style={s.categoryBadge}>{category.toLocaleUpperCase('pt-BR')}</Text><Text numberOfLines={2} style={s.listHeadline}>{item.headline}</Text>{!!item.reading_progress && <Text style={s.listMeta}>{Math.round(item.reading_progress)}% lido</Text>}</View></Pressable><Pressable accessibilityRole="button" accessibilityLabel="Remover dos salvos" onPress={onRemove} style={s.removeButton}><Icon name="bookmark" color={colors.primary} size={19} /></Pressable></View>; }

const s = {
  safe: { flex: 1, backgroundColor: colors.background } as const, content: { paddingHorizontal: 17, paddingTop: 6, gap: 0 } as const, header: { height: 54, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 15 }, logo: { width: 126, height: 46, marginLeft: -3 }, headerActions: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9 }, headerIcon: { width: 36, height: 42, alignItems: 'center' as const, justifyContent: 'center' as const, position: 'relative' as const }, avatarButton: { width: 42, height: 42, borderRadius: 22, overflow: 'hidden' as const, backgroundColor: '#E5F2FF' }, avatar: { width: '100%' as const, height: '100%' as const },
  titleRow: { minHeight: 87, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, gap: 8, marginBottom: 13 }, titleCopy: { flex: 1 }, pageTitle: { color: '#10131C', fontFamily: typography.fontFamily.ui, fontSize: 32, lineHeight: 38, fontWeight: '800' as const, letterSpacing: -.9 }, pageSubtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 17, marginTop: 2 }, countPill: { paddingHorizontal: 14, paddingVertical: 11, borderRadius: 28, backgroundColor: '#E6F2FF', flexShrink: 0 }, countText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '600' as const }, countSkeleton: { width: 100, height: 20, borderRadius: 12, backgroundColor: '#E3EEF8', alignSelf: 'flex-end' as const, marginBottom: 12 },
  sectionTitleRow: { minHeight: 39, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginTop: 5, marginBottom: 9 }, sectionTitle: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 20, lineHeight: 25, fontWeight: '800' as const, letterSpacing: -.5 }, allLink: { minHeight: 38, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 1 }, allText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 14 },
  continueCard: { minHeight: 150, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, padding: 12, borderRadius: 25, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E7F0F8', marginBottom: 16 }, continueImage: { width: 100, height: 126, borderRadius: 16, backgroundColor: '#DFEAF4' }, continueCopy: { flex: 1, minWidth: 0, justifyContent: 'center' as const }, categoryBadge: { alignSelf: 'flex-start' as const, maxWidth: '100%' as const, overflow: 'hidden' as const, borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: '#E5F0FF', color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800' as const }, continueHeadline: { color: '#111B48', fontFamily: typography.fontFamily.ui, fontSize: 16, lineHeight: 21, fontWeight: '800' as const, marginTop: 7 }, progressLine: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginTop: 7 }, progressPercent: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800' as const }, continueMinutes: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700' as const }, progressTrack: { height: 7, borderRadius: 5, backgroundColor: '#DDEAF6', overflow: 'hidden' as const, marginTop: 3 }, progressFill: { height: 7, borderRadius: 5, backgroundColor: colors.primary }, continueButton: { width: 48, height: 48, borderRadius: 25, backgroundColor: '#FFFFFF', alignItems: 'center' as const, justifyContent: 'center' as const, elevation: 3, shadowColor: '#5779A7', shadowOpacity: .16, shadowRadius: 8 }, continueEmpty: { minHeight: 112, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, padding: 15, borderRadius: 24, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E7F0F8', marginBottom: 16 }, emptyGlyph: { width: 48, height: 48, borderRadius: 25, backgroundColor: '#E7F2FF', alignItems: 'center' as const, justifyContent: 'center' as const }, continueEmptyTitle: { color: '#15224B', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' as const }, continueEmptyText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, lineHeight: 15, marginTop: 3 },
  topicGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, justifyContent: 'space-between' as const, rowGap: 10, marginBottom: 13 }, topicCard: { minHeight: 126, borderRadius: 22, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 6, paddingVertical: 8 }, topicIcon: { width: 58, height: 58, borderRadius: 30, alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 3 }, topicName: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 13, lineHeight: 16, textAlign: 'center' as const }, topicCount: { color: '#7389AA', fontFamily: typography.fontFamily.ui, fontSize: 12, marginTop: 3, textAlign: 'center' as const }, sectionEmpty: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginBottom: 17, paddingHorizontal: 3 }, recentList: { gap: 10, paddingBottom: 8 }, recentCard: { borderRadius: 20, backgroundColor: '#FFFFFF', overflow: 'hidden' as const, borderWidth: 1, borderColor: '#E8F0F8', marginBottom: 4 }, recentImage: { width: '100%' as const, height: 104, backgroundColor: '#E5F0FB' }, recentCopy: { minHeight: 85, paddingHorizontal: 11, paddingTop: 8, paddingBottom: 10 }, recentMeta: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, gap: 6 }, recentMinutes: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600' as const }, recentHeadline: { color: '#111B48', fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 19, fontWeight: '700' as const, marginTop: 7 }, briefingBadge: { overflow: 'hidden' as const, color: '#087CF0', backgroundColor: '#E5F0FF', fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800' as const, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 5 },
  emptyCard: { minHeight: 300, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 28, borderRadius: 26, backgroundColor: '#FFFFFF', marginTop: 28, borderWidth: 1, borderColor: '#E9F1F9' }, emptyTitle: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 19, lineHeight: 25, fontWeight: '800' as const, textAlign: 'center' as const, marginTop: 14 }, emptySubtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 21, textAlign: 'center' as const, marginTop: 7 }, errorCard: { padding: 18, marginTop: 22, borderRadius: 20, backgroundColor: '#FFFFFF', alignItems: 'center' as const }, errorText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, textAlign: 'center' as const }, retry: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, paddingVertical: 12 },
  skeletonCard: { backgroundColor: '#E5EFF8', borderRadius: 20, marginBottom: 12 }, skeletonGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, justifyContent: 'space-between' as const, gap: 8, marginBottom: 15 }, skeletonTopic: { height: 118, backgroundColor: '#E5EFF8', borderRadius: 20 }, skeletonRecent: { flexDirection: 'row' as const, gap: 10 },
  secondaryContent: { paddingHorizontal: 18, paddingTop: 8, paddingBottom: 35 }, secondaryHeader: { height: 53, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 12 }, backButton: { width: 42, height: 46, justifyContent: 'center' as const }, backGlyph: { color: colors.secondary, fontSize: 34 }, secondaryTitle: { flex: 1, textAlign: 'center' as const, color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800' as const }, groupLabel: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 16, marginBottom: 10 }, articleRow: { minHeight: 104, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 7, padding: 9, backgroundColor: '#FFFFFF', borderRadius: 18, marginBottom: 9, borderWidth: 1, borderColor: '#E7F0F8' }, articlePress: { flex: 1, minWidth: 0, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10 }, listThumb: { width: 74, height: 78, borderRadius: 11, backgroundColor: '#E5F0FB' }, listHeadline: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 14, lineHeight: 19, marginTop: 5 }, listMeta: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 3 }, removeButton: { width: 42, height: 48, alignItems: 'center' as const, justifyContent: 'center' as const }, listBriefing: { minHeight: 85, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 11, padding: 9, borderRadius: 16, backgroundColor: '#FFFFFF', marginBottom: 8 }, loadMore: { minHeight: 48, alignItems: 'center' as const, justifyContent: 'center' as const },
};
