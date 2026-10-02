import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Image, ImageBackground, Pressable, RefreshControl, StatusBar, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { firebaseAuth } from '../services/firebaseAuth';
import { api, ClientError } from '../api/client';
import { colors, typography } from '../theme';
import type { BriefingItem, Topic, User } from '../types/api';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import { useContentRevisionTick } from '../services/contentRevision';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';
import type { IconName } from './Icon';

const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const globeMascot = require('../../assets/onboarding/new-globe.png');
const mascotFallback = require('../../assets/onboarding/new-waving.png');
const topicColors = [
  { background: '#E5F2FF', color: '#087CF0' }, { background: '#F0E9FF', color: '#8953E9' },
  { background: '#E5F7EE', color: '#12A965' }, { background: '#FFF2E1', color: '#E99210' },
  { background: '#FFE9ED', color: '#E83E59' }, { background: '#FDE8F1', color: '#E04E8A' },
];
type ExplorePayload = { topics: Topic[]; latest_news: BriefingItem[] };
type SortMode = 'relevant' | 'recent' | 'alpha';
type Trend = { topic: Topic; count: number; newest: number };
type DisplayTopic = Topic & { presentation_depth: number };
const payloadCache = new Map<string, { value: ExplorePayload; at: number }>();

const topicKey = (topic: Topic) => topic.id || topic.code;
const displayName = (topic: Topic) => topic.name || topic.label || topic.code;
export const colorFor = (index: number) => topicColors[index % topicColors.length];

export function ExploreScreen({ user, onTopic, onDetail, onProfile }: {
  user: User | null;
  onTopic: (topic: Topic) => void;
  onDetail: (story: BriefingItem) => void;
  onProfile: () => void;
}) {
  const bottomSpace = useFloatingTabContentInset(true);
  const contentRevisionTick=useContentRevisionTick();
  const { width } = useWindowDimensions();
  const searchRef = useRef<TextInput>(null);
  const [payload, setPayload] = useState<ExplorePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [remoteMatches, setRemoteMatches] = useState<BriefingItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [sort, setSort] = useState<SortMode>('relevant');
  const [sortOpen, setSortOpen] = useState(false);
  const [allTrending, setAllTrending] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);
  const userId = firebaseAuth.currentUser?.uid || user?.id || 'anonymous';
  const avatarUrl = firebaseAuth.currentUser?.photoURL;
  const topics = payload?.topics || [];
  const stories = payload?.latest_news || [];
  const topicMap = useMemo(() => new Map(topics.map(topic => [topic.code, topic])), [topics]);

  const load = useCallback(async (force = false) => {
    const cached = payloadCache.get(userId);
    if (!force && cached && Date.now() - cached.at < 180_000) {
      setPayload(cached.value);
      setLoading(false);
      return;
    }
    setError('');
    try {
      const [home, news] = await Promise.all([api.home(), api.news(30,{discovery:true}).catch(() => ({ items: [] as BriefingItem[] }))]);
      const uniqueTopics = Array.from(new Map((home.topics || []).map(topic => [topicKey(topic), topic])).values());
      const value: ExplorePayload = { ...home, topics: uniqueTopics, latest_news: news.items || [] };
      payloadCache.set(userId, { value, at: Date.now() });
      setPayload(value);
    } catch (cause) {
      if (cause instanceof ClientError && cause.code === 'AUTH_REQUIRED') setError('Sua sessão expirou. Entre novamente para explorar os assuntos.');
      else setError('Não foi possível carregar os assuntos. Verifique sua conexão e tente novamente.');
    } finally { setLoading(false); setRefreshing(false); }
  }, [userId]);

  useEffect(() => { void load(contentRevisionTick>0); }, [load,contentRevisionTick]);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) { setRemoteMatches([]); setSearching(false); setSearchError(''); return; }
    let active = true;
    setSearching(true);
    setSearchError('');
    const timer = setTimeout(() => {
      api.news(12, { query: term }).then(result => { if (active) setRemoteMatches(result.items || []); })
        .catch(() => { if (active) { setRemoteMatches([]); setSearchError('Não foi possível buscar notícias agora.'); } })
        .finally(() => { if (active) setSearching(false); });
    }, 320);
    return () => { active = false; clearTimeout(timer); };
  }, [query]);

  const trends = useMemo<Trend[]>(() => {
    const ranked = new Map<string, Trend>();
    stories.forEach((story, index) => {
      const code = story.primary_taxonomy_id || '';
      const topic = topicMap.get(code) || topics.find(item => displayName(item).toLocaleLowerCase('pt-BR') === (story.primary_taxonomy_label || story.category || '').toLocaleLowerCase('pt-BR'));
      if (!topic) return;
      const key = topicKey(topic);
      const current = ranked.get(key) || { topic, count: 0, newest: Number.MAX_SAFE_INTEGER };
      current.count += 1;
      current.newest = Math.min(current.newest, index);
      ranked.set(key, current);
    });
    return [...ranked.values()].sort((a, b) => b.count - a.count || a.newest - b.newest || displayName(a.topic).localeCompare(displayName(b.topic), 'pt-BR'));
  }, [stories, topicMap, topics]);

  const recentRank = useMemo(() => {
    const ranks = new Map<string, number>();
    stories.forEach((story, index) => {
      const topic = topicMap.get(story.primary_taxonomy_id || '') || topics.find(item => displayName(item).toLocaleLowerCase('pt-BR') === (story.primary_taxonomy_label || story.category || '').toLocaleLowerCase('pt-BR'));
      if (topic && !ranks.has(topicKey(topic))) ranks.set(topicKey(topic), index);
    });
    return ranks;
  }, [stories, topicMap, topics]);

  const orderedTopics = useMemo<DisplayTopic[]>(() => {
    const byId = new Map(topics.map(topic => [topicKey(topic), topic]));
    const children = new Map<string, Topic[]>();
    const roots: Topic[] = [];
    topics.forEach(topic => {
      const parentId = topic.parent_id;
      if (parentId && byId.has(parentId)) {
        const siblings = children.get(parentId) || [];
        siblings.push(topic);
        children.set(parentId, siblings);
      } else roots.push(topic);
    });
    const compare = (a: Topic, b: Topic) => {
      if (sort === 'alpha') return displayName(a).localeCompare(displayName(b), 'pt-BR') || (a.order ?? 0) - (b.order ?? 0);
      if (sort === 'recent') return (recentRank.get(topicKey(a)) ?? Number.MAX_SAFE_INTEGER) - (recentRank.get(topicKey(b)) ?? Number.MAX_SAFE_INTEGER) || (a.order ?? 0) - (b.order ?? 0);
      return (b.content_count || 0) - (a.content_count || 0) || (a.order ?? 0) - (b.order ?? 0);
    };
    const result: DisplayTopic[] = [];
    const visited = new Set<string>();
    const visit = (topic: Topic, depth: number) => {
      const key = topicKey(topic);
      if (visited.has(key)) return;
      visited.add(key);
      result.push({ ...topic, presentation_depth: depth });
      [...(children.get(key) || [])].sort(compare).forEach(child => visit(child, depth + 1));
    };
    [...roots].sort(compare).forEach(topic => visit(topic, 0));
    topics.forEach(topic => visit(topic, 0));
    return result;
  }, [topics, sort, recentRank]);
  const maxCount = topics.reduce((maximum, topic) => Math.max(maximum, topic.content_count || 0), 1);
  const matchingTopics = query.trim().length >= 2 ? topics.filter(topic => `${displayName(topic)} ${topic.description || ''} ${topic.code}`.toLocaleLowerCase('pt-BR').includes(query.trim().toLocaleLowerCase('pt-BR'))).slice(0, 4) : [];
  const shownTrends = allTrending ? trends : trends.slice(0, 5);
  const focusSearch = () => searchRef.current?.focus();
  const refresh = () => { setRefreshing(true); setLoading(false); void load(true); };
  const openTopic = (topic: Topic) => { setSelectedTopic(topicKey(topic)); onTopic(topic); };

  const intro = <ExploreIntro
    width={width} user={user} avatarUrl={avatarUrl && !avatarFailed ? avatarUrl : undefined}
    onAvatarError={() => setAvatarFailed(true)} onSearch={focusSearch} onProfile={onProfile}
    searchRef={searchRef} query={query} onQuery={setQuery} topics={topics} trends={shownTrends}
    selectedTopic={selectedTopic} onSelectTopic={openTopic} loading={loading} error={error} onRetry={() => { setLoading(true); void load(true); }}
    matchingTopics={matchingTopics} remoteMatches={remoteMatches} searchError={searchError} searching={searching}
    onDetail={onDetail}
    sort={sort} sortOpen={sortOpen} onToggleSort={() => setSortOpen(value => !value)} onSort={value => { setSort(value); setSortOpen(false); }}
    allTrending={allTrending} onShowAllTrending={() => setAllTrending(value => !value)}
    />;

  return <SafeAreaView style={styles.safe} edges={['top']}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <FlatList<DisplayTopic>
      data={orderedTopics}
      keyExtractor={topicKey}
      ListHeaderComponent={intro}
      renderItem={({ item, index }) => <ExploreTopicRow
        topic={item} index={index} maxCount={maxCount} depth={item.presentation_depth} selected={selectedTopic === topicKey(item)} onPress={() => openTopic(item)} />}
      ListEmptyComponent={loading ? <View style={styles.skeletonRows}>{[0, 1, 2, 3].map(key => <TopicRowSkeleton key={key} />)}</View> : error ? null : <EmptyTopics onRetry={() => { setLoading(true); void load(true); }} />}
      ListFooterComponent={<View style={{ height: bottomSpace }} />}
      contentContainerStyle={styles.listContent}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.primary} />}
      initialNumToRender={8} maxToRenderPerBatch={8} windowSize={7} updateCellsBatchingPeriod={40}
      removeClippedSubviews
    />
  </SafeAreaView>;
}

function ExploreIntro(props: {
  width: number; user: User | null; avatarUrl?: string; onAvatarError: () => void; onSearch: () => void; onProfile: () => void;
  searchRef: React.RefObject<TextInput | null>; query: string; onQuery: (value: string) => void; topics: Topic[]; trends: Trend[]; selectedTopic: string | null; onSelectTopic: (topic: Topic) => void;
  loading: boolean; error: string; onRetry: () => void; matchingTopics: Topic[]; remoteMatches: BriefingItem[]; searchError: string; searching: boolean; onDetail: (story: BriefingItem) => void;
  sort: SortMode; sortOpen: boolean; onToggleSort: () => void; onSort: (value: SortMode) => void; allTrending: boolean; onShowAllTrending: () => void;
}) {
  const topicWidth = Math.max(104, Math.min(126, (props.width - 62) / 5.2));
  return <View>
      <ExploreHeader user={props.user} avatarUrl={props.avatarUrl} onAvatarError={props.onAvatarError} onSearch={props.onSearch} onProfile={props.onProfile} />
    <ExploreHero />
    <ExploreSearch ref={props.searchRef} query={props.query} onChange={props.onQuery} />
    {props.query.trim().length >= 2 && <SearchMatches topics={props.matchingTopics} stories={props.remoteMatches} loading={props.searching} error={props.searchError} onTopic={props.onSelectTopic} onDetail={props.onDetail} />}
    <View style={styles.topicCarousel}>
      {props.loading ? <HorizontalSkeletons cardWidth={topicWidth} /> : props.error ? <InlineRetry message={props.error} onRetry={props.onRetry} /> : props.topics.length ? <FlatList horizontal data={props.topics} keyExtractor={topicKey} showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalContent} renderItem={({ item, index }) => <TopTopicCard topic={item} index={index} width={topicWidth} selected={props.selectedTopic === topicKey(item)} onPress={() => props.onSelectTopic(item)} />} /> : <Text style={styles.emptyText}>Nenhum assunto disponível no momento.</Text>}
    </View>
    <View style={styles.section}>
      <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Em alta no momento</Text><Pressable accessibilityRole="button" onPress={props.onShowAllTrending} style={styles.linkRow}><Text style={styles.linkText}>{props.allTrending ? 'Ver menos' : 'Ver todos'}</Text><Icon name="chevron" color={colors.primary} size={16} /></Pressable></View>
      {props.loading ? <HorizontalSkeletons cardWidth={188} dark /> : props.error ? <Text style={styles.emptyText}>Assuntos em alta indisponíveis.</Text> : props.trends.length ? <FlatList horizontal data={props.trends} keyExtractor={item => topicKey(item.topic)} showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalContent} renderItem={({ item, index }) => <TrendingCard trend={item} rank={index + 1} onPress={() => props.onSelectTopic(item.topic)} />} /> : <Text style={styles.emptyText}>Ainda não há notícias recentes para calcular os assuntos em alta.</Text>}
    </View>
    <View style={styles.allHeader}>
      <Text style={styles.sectionTitle}>Todos os assuntos</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={`Ordenar assuntos: ${sortLabel[props.sort]}`} accessibilityState={{ expanded: props.sortOpen }} onPress={props.onToggleSort} style={styles.sortButton}>
        <Text style={styles.sortText}>{sortLabel[props.sort]}</Text><View style={{ transform: [{ rotate: props.sortOpen ? '-90deg' : '90deg' }] }}><Icon name="chevron" color={colors.secondary} size={16} /></View>
      </Pressable>
    </View>
    {props.sortOpen && <View style={styles.sortMenu}>{(['relevant', 'recent', 'alpha'] as SortMode[]).map(value => <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: props.sort === value }} onPress={() => props.onSort(value)} style={styles.sortOption}><Text style={[styles.sortOptionText, props.sort === value && styles.sortSelected]}>{sortLabel[value]}</Text>{props.sort === value && <Icon name="check" color={colors.primary} size={18} />}</Pressable>)}</View>}
  </View>;
}

function ExploreHeader({ user, avatarUrl, onAvatarError, onSearch, onProfile }: { user: User | null; avatarUrl?: string; onAvatarError: () => void; onSearch: () => void; onProfile: () => void }) {
  const initials = user?.display_name?.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'N';
  return <View style={styles.header}>
    <Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={styles.logo} />
    <View style={styles.headerActions}>
      <Pressable accessibilityRole="button" accessibilityLabel="Buscar assuntos e notícias" onPress={onSearch} style={styles.headerIcon}><Icon name="search" size={24} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir perfil" onPress={onProfile} style={styles.avatarButton}>
        {avatarUrl ? <Image source={{ uri: avatarUrl }} onError={onAvatarError} style={styles.avatar} /> : <View style={styles.avatarFallback}><Text style={styles.avatarInitials}>{initials}</Text></View>}
      </Pressable>
    </View>
  </View>;
}

function ExploreHero() {
  return <View style={styles.hero}>
    <View style={styles.heroCopy}>
      <Text style={styles.eyebrow}>EXPLORAR</Text>
      <Text style={styles.heroTitle}>Descubra{ '\n' }seu interesse</Text>
      <Text style={styles.heroSubtitle}>Explore as principais notícias do mundo organizadas por assuntos.</Text>
    </View>
    <Image source={globeMascot} resizeMode="contain" accessibilityLabel="Mascote NEWZI explorando o mundo" style={styles.heroMascot} />
    <View pointerEvents="none" style={styles.heroGlow} />
  </View>;
}

const ExploreSearch = React.forwardRef<TextInput, { query: string; onChange: (value: string) => void }>(({ query, onChange }, ref) => <View style={styles.searchBox}>
  <Icon name="search" size={23} color="#738AAF" />
  <TextInput ref={ref} value={query} onChangeText={onChange} placeholder="Buscar por assunto, tema ou palavra-chave..." placeholderTextColor="#7186A8" accessibilityLabel="Buscar por assunto, tema ou palavra-chave" returnKeyType="search" style={styles.searchInput} autoCapitalize="none" />
  {!!query && <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" onPress={() => onChange('')} style={styles.clearButton}><Text style={styles.clearText}>×</Text></Pressable>}
</View>);
ExploreSearch.displayName = 'ExploreSearch';

function SearchMatches({ topics, stories, loading, error, onTopic, onDetail }: { topics: Topic[]; stories: BriefingItem[]; loading: boolean; error: string; onTopic: (topic: Topic) => void; onDetail: (story: BriefingItem) => void }) {
  if (loading && !topics.length && !stories.length) return <View style={styles.searchMatches}><ActivityIndicator size="small" color={colors.primary} /></View>;
  if (error && !topics.length && !stories.length) return <Text style={styles.searchError}>{error}</Text>;
  if (!topics.length && !stories.length && !loading) return <Text style={styles.searchEmpty}>Nenhum resultado encontrado. Tente outro assunto ou palavra-chave.</Text>;
  return <View style={styles.searchMatches}>
    {!!error && <Text style={styles.searchError}>{error}</Text>}
    {topics.map(topic => <Pressable key={topicKey(topic)} accessibilityRole="button" onPress={() => onTopic(topic)} style={styles.matchRow}><TopicGlyph topic={topic} index={0} size={28} /><View style={styles.matchCopy}><Text numberOfLines={1} style={styles.matchTitle}>{displayName(topic)}</Text><Text style={styles.matchMeta}>{topic.content_count || 0} notícias · assunto</Text></View><Icon name="chevron" color={colors.secondary} size={17} /></Pressable>)}
    {stories.slice(0, 4).map(story => <Pressable key={story.id} accessibilityRole="button" onPress={() => onDetail(story)} style={styles.storyMatch}><ArticleImage uri={story.image_url} articleId={story.id} accessibilityLabel={story.headline} style={styles.storyMatchImage} /><View style={styles.storyMatchCopy}><Text style={styles.matchCategory}>{story.primary_taxonomy_label || story.category || 'Notícias'}</Text><Text numberOfLines={2} style={styles.matchTitle}>{story.headline}</Text></View></Pressable>)}
    {loading && <ActivityIndicator size="small" color={colors.primary} style={{ marginVertical: 8 }} />}
  </View>;
}

function TopTopicCard({ topic, index, width, selected, onPress }: { topic: Topic; index: number; width: number; selected: boolean; onPress: () => void }) {
  const palette = colorFor(index);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${displayName(topic)}, ${topic.content_count || 0} notícias`} accessibilityState={{ selected }} onPress={onPress} style={[styles.topCard, { width, backgroundColor: palette.background }, selected && styles.topCardSelected]}>
    <TopicGlyph topic={topic} index={index} size={52} />
    <Text numberOfLines={2} style={styles.topCardName}>{displayName(topic)}</Text>
    <Text style={styles.topCardCount}>{topic.content_count || 0} notícias</Text>
  </Pressable>;
}

export function TopicGlyph({ topic, index, size }: { topic: Pick<Topic, 'code' | 'name' | 'order'>; index: number; size: number }) {
  const palette = colorFor(index);
  const name = displayName(topic).toLocaleLowerCase('pt-BR');
  const glyph: IconName = name.includes('inteligência') || name.includes('artificial') ? 'brain' : name.includes('negócio') ? 'growth' : name.includes('economia') ? 'coins' : name.includes('política') ? 'landmark' : name.includes('saúde') ? 'heart' : name.includes('meio ambiente') || name.includes('clima') ? 'leaf' : name.includes('tecnologia') ? 'cpu' : 'sparkles';
  return <View style={[styles.glyph, { width: size, height: size, borderRadius: size / 2, backgroundColor: palette.background }]}>
    <Icon name={glyph} color={palette.color} size={size * .54} />
  </View>;
}

function TrendingCard({ trend, rank, onPress }: { trend: Trend; rank: number; onPress: () => void }) {
  const palette = colorFor((trend.topic.order || rank - 1) % topicColors.length);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${displayName(trend.topic)}, em alta número ${rank}, ${trend.count} notícias recentes`} onPress={onPress} style={styles.trendCard}>
    <ImageBackground source={mascotFallback} resizeMode="contain" imageStyle={styles.trendMascot} style={[styles.trendBackground, { backgroundColor: '#102B57' }]}>
      <View style={[styles.rankBadge, { backgroundColor: palette.background }]}><Text style={[styles.rankText, { color: palette.color }]}>{rank}</Text></View>
      <View style={styles.trendCopy}><Text numberOfLines={2} style={styles.trendName}>{displayName(trend.topic)}</Text><Text style={styles.trendCount}>{trend.count} {trend.count === 1 ? 'notícia recente' : 'notícias recentes'}</Text></View>
      <View style={styles.trendArrow}><Icon name="chevron" color="#0A2450" size={16} /></View>
    </ImageBackground>
  </Pressable>;
}

function ExploreTopicRow({ topic, index, maxCount, depth, selected, onPress }: { topic: Topic; index: number; maxCount: number; depth: number; selected: boolean; onPress: () => void }) {
  const palette = colorFor(index);
  const coverage = Math.max(0, Math.min(1, (topic.content_count || 0) / maxCount));
  return <Pressable accessibilityRole="button" accessibilityLabel={`${displayName(topic)}, ${topic.content_count || 0} notícias`} accessibilityState={{ selected }} onPress={onPress} style={[styles.topicRow, selected && styles.topicRowSelected, depth > 0 && { marginLeft: Math.min(depth * 12, 36) }]}>
    <TopicGlyph topic={topic} index={index} size={60} />
    <View style={styles.topicDescription}>
      <Text numberOfLines={1} style={styles.topicName}>{displayName(topic)}</Text>
      {!!topic.description && <Text numberOfLines={2} style={styles.topicSub}>{topic.description}</Text>}
    </View>
    <View style={styles.topicMetric}><Text style={styles.topicCount}>{topic.content_count || 0} notícias</Text><View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${coverage * 100}%`, backgroundColor: palette.color }]} /></View></View>
    <Icon name="chevron" color="#6C83A6" size={19} />
  </Pressable>;
}

function HorizontalSkeletons({ cardWidth, dark = false }: { cardWidth: number; dark?: boolean }) {
  return <View style={styles.skeletonCarousel}>{[0, 1, 2, 3].map(index => <View key={index} style={[styles.horizontalSkeleton, { width: cardWidth }, dark && styles.darkSkeleton]} />)}</View>;
}
function TopicRowSkeleton() { return <View style={styles.rowSkeleton}><View style={styles.rowSkeletonGlyph} /><View style={styles.rowSkeletonCopy}><View style={styles.rowSkeletonLine} /><View style={[styles.rowSkeletonLine, { width: '72%' }]} /></View><View style={styles.rowSkeletonMetric} /></View>; }
function EmptyTopics({ onRetry }: { onRetry: () => void }) { return <Pressable accessibilityRole="button" onPress={onRetry} style={styles.emptyTopics}><Text style={styles.emptyTopicsTitle}>Nenhum assunto disponível</Text><Text style={styles.emptyText}>Toque para tentar carregar novamente.</Text></Pressable>; }
function InlineRetry({ message, onRetry }: { message: string; onRetry: () => void }) { return <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retryCard}><Text style={styles.retryText}>{message}</Text><Text style={styles.linkText}>Tentar novamente</Text></Pressable>; }

const sortLabel: Record<SortMode, string> = { relevant: 'Mais relevantes', recent: 'Mais recentes', alpha: 'A–Z' };
const styles = {
  safe: { flex: 1, backgroundColor: colors.background } as const,
  listContent: { paddingHorizontal: 18, paddingTop: 2 } as const,
  header: { height: 56, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 13 },
  logo: { width: 126, height: 46, marginLeft: -3 }, headerActions: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9 },
  headerIcon: { width: 36, height: 42, alignItems: 'center' as const, justifyContent: 'center' as const, position: 'relative' as const },
  avatarButton: { width: 42, height: 42, borderRadius: 21, overflow: 'hidden' as const, backgroundColor: '#E5F2FF', alignItems: 'center' as const, justifyContent: 'center' as const }, avatar: { width: 42, height: 42, borderRadius: 21 }, avatarFallback: { width: 42, height: 42, borderRadius: 21, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: '#DDEEFF' }, avatarInitials: { color: colors.primaryDark, fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 14 },
  hero: { minHeight: 196, marginBottom: 9, position: 'relative' as const, justifyContent: 'center' as const, overflow: 'hidden' as const },
  heroCopy: { width: '69%' as const, zIndex: 2, paddingLeft: 2 }, eyebrow: { color: '#7489AB', letterSpacing: 3, fontSize: 12, lineHeight: 17, fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, marginBottom: 3 },
  heroTitle: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 34, lineHeight: 37, letterSpacing: -1.1 }, heroSubtitle: { color: '#61789E', fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 20, marginTop: 8, maxWidth: 300 },
  heroMascot: { position: 'absolute' as const, width: 198, height: 198, right: -20, bottom: -21, zIndex: 1 }, heroGlow: { position: 'absolute' as const, width: 176, height: 176, right: 2, bottom: -13, borderRadius: 90, backgroundColor: '#DCEEFF66' },
  searchBox: { height: 58, borderRadius: 32, paddingHorizontal: 16, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, backgroundColor: '#EAF3FC', marginBottom: 16, borderWidth: 1, borderColor: '#E7F1FB' }, searchInput: { flex: 1, minWidth: 0, fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontSize: 15, paddingVertical: 0 }, clearButton: { width: 30, height: 38, alignItems: 'center' as const, justifyContent: 'center' as const }, clearText: { color: colors.secondary, fontSize: 25 },
  searchMatches: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2EFFB', borderRadius: 18, paddingHorizontal: 12, paddingVertical: 8, marginTop: -7, marginBottom: 12 }, matchRow: { minHeight: 50, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9, borderBottomWidth: 1, borderBottomColor: '#EFF4FA' }, matchCopy: { flex: 1 }, matchTitle: { color: '#10254A', fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 13 }, matchMeta: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }, matchCategory: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 10, marginBottom: 3 }, storyMatch: { minHeight: 74, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#EFF4FA' }, storyMatchImage: { width: 62, height: 56, borderRadius: 9 }, storyMatchCopy: { flex: 1, minWidth: 0 }, searchError: { color: colors.danger, fontSize: 12, marginTop: -6, marginBottom: 12, paddingHorizontal: 8 }, searchEmpty: { color: colors.secondary, fontSize: 12, padding: 12, marginTop: -7, marginBottom: 12 },
  topicCarousel: { height: 126, marginBottom: 15 }, horizontalContent: { gap: 8, paddingBottom: 3 }, topCard: { height: 122, borderRadius: 20, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 7, paddingVertical: 8 }, topCardSelected: { borderWidth: 2, borderColor: colors.primary, shadowColor: colors.primary, shadowOpacity: .17, shadowRadius: 8, elevation: 2 }, glyph: { alignItems: 'center' as const, justifyContent: 'center' as const, flexShrink: 0 }, topCardName: { textAlign: 'center' as const, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, color: '#071A42', fontSize: 12, lineHeight: 15, marginTop: 3 }, topCardCount: { color: '#6E83A3', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 3 },
  section: { marginBottom: 20 }, sectionHeader: { height: 32, marginBottom: 6, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 1 }, sectionTitle: { fontFamily: typography.fontFamily.ui, fontSize: 19, lineHeight: 25, color: '#071A42', fontWeight: '800' as const, letterSpacing: -.45 }, linkRow: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 0 }, linkText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 12 }, trendCard: { width: 184, height: 146, borderRadius: 18, overflow: 'hidden' as const, marginRight: 1 }, trendBackground: { flex: 1, justifyContent: 'space-between' as const, padding: 12 }, trendMascot: { opacity: .18, width: 130, height: 130, left: 54, top: 14 }, rankBadge: { width: 32, height: 32, borderRadius: 17, justifyContent: 'center' as const, alignItems: 'center' as const }, rankText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800' as const }, trendCopy: { marginTop: 'auto' as const, paddingRight: 25 }, trendName: { color: '#FFFFFF', fontFamily: typography.fontFamily.ui, fontSize: 16, lineHeight: 19, fontWeight: '800' as const }, trendCount: { color: '#D7E7F7', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 4 }, trendArrow: { position: 'absolute' as const, right: 10, bottom: 10, width: 30, height: 30, borderRadius: 16, backgroundColor: '#FFFFFF', alignItems: 'center' as const, justifyContent: 'center' as const },
  allHeader: { minHeight: 34, marginBottom: 6, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const }, sortButton: { minHeight: 40, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, paddingHorizontal: 3 }, sortText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '600' as const }, sortChevron: { color: colors.primary, fontSize: 19, marginTop: -2 }, sortMenu: { alignSelf: 'flex-end' as const, minWidth: 164, marginBottom: 9, padding: 5, borderRadius: 14, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E3EEF8', shadowColor: '#395E8C', shadowOpacity: .12, shadowRadius: 12, elevation: 4 }, sortOption: { minHeight: 42, paddingHorizontal: 10, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const }, sortOptionText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13 }, sortSelected: { color: colors.primary, fontWeight: '700' as const },
  topicRow: { minHeight: 78, marginBottom: 3, paddingHorizontal: 11, paddingVertical: 8, borderRadius: 26, backgroundColor: '#FFFFFFD9', flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, borderWidth: 1, borderColor: '#F0F5FB' }, topicRowSelected: { borderColor: colors.primary, backgroundColor: '#F4FAFF' }, childTopicRow: { marginLeft: 15 }, topicDescription: { flex: 1, minWidth: 0 }, topicName: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' as const, lineHeight: 18 }, topicSub: { color: '#667D9E', fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 15, marginTop: 1 }, topicMetric: { width: 102, justifyContent: 'center' as const, gap: 7 }, topicCount: { color: '#657D9F', fontFamily: typography.fontFamily.ui, fontSize: 11 }, progressTrack: { height: 5, width: '100%' as const, borderRadius: 3, backgroundColor: '#E1EBF7', overflow: 'hidden' as const }, progressFill: { height: 5, borderRadius: 3 },
  skeletonCarousel: { flexDirection: 'row' as const, gap: 8, paddingBottom: 4 }, horizontalSkeleton: { height: 122, borderRadius: 18, backgroundColor: '#E5F0FA' }, darkSkeleton: { height: 146, backgroundColor: '#D8E7F6' }, skeletonRows: { gap: 4 }, rowSkeleton: { minHeight: 78, marginBottom: 3, borderRadius: 25, backgroundColor: '#EDF4FB', flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 14, gap: 12 }, rowSkeletonGlyph: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#E0ECF8' }, rowSkeletonCopy: { flex: 1, gap: 8 }, rowSkeletonLine: { width: '88%' as const, height: 9, borderRadius: 5, backgroundColor: '#E0ECF8' }, rowSkeletonMetric: { width: 78, height: 20, borderRadius: 6, backgroundColor: '#E0ECF8' }, emptyText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 18, paddingVertical: 12 }, emptyTopics: { backgroundColor: '#FFFFFF', padding: 18, borderRadius: 18, alignItems: 'center' as const, marginTop: 8 }, emptyTopicsTitle: { color: colors.text, fontWeight: '700' as const, marginBottom: 5 }, retryCard: { padding: 12, backgroundColor: '#FFFFFF', borderRadius: 14, gap: 6 }, retryText: { color: colors.secondary, fontSize: 12 },
};
