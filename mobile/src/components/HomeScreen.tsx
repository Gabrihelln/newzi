import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { ActivityIndicator, AppState, Image, Platform, Pressable, ScrollView, StatusBar, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { firebaseAuth } from '../services/firebaseAuth';
import { api, ClientError } from '../api/client';
import { getAudioProgress, loadAudio, pauseAudio, playAudio, releaseAudio, sameBriefing, seekTo, setAudioContext, subscribeAudio, subscribeAudioContext } from '../audio/player';
import type { AudioContext, PlaybackState } from '../audio/player';
import { colors, radius, spacing, typography } from '../theme';
import type { Briefing, BriefingItem, HomeData, Topic, User } from '../types/api';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import { useContentRevisionTick } from '../services/contentRevision';
import { Icon } from './Icon';
import { ArticleImage, isCanonicalArticleImageUrl } from './ArticleImage';
import { formatHomeDate, greetingForLocalTime, nextBriefingLabel } from '../config/dateTime';

const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const fallbackMascot = require('../../assets/onboarding/new-waving.png');
const FEATURED_LIMIT = 3;
const FEATURED_AUTO_SCROLL_MS = 5000;
const FEATURED_RESUME_AFTER_TOUCH_MS = 8000;
const hasFeaturedImage = (item: BriefingItem) => isCanonicalArticleImageUrl(item.image_url);
/** Merge candidate lists into unique featured stories that have a linked image, preserving priority order. */
function pickFeatured(...sources: (BriefingItem[] | undefined)[]) {
  const seen = new Set<string>();
  const picked: BriefingItem[] = [];
  for (const item of sources.flatMap(source => source || [])) {
    if (picked.length >= FEATURED_LIMIT) break;
    if (seen.has(item.id) || !hasFeaturedImage(item)) continue;
    seen.add(item.id);
    picked.push(item);
  }
  return picked;
}
const initialPlayback: PlaybackState = { position: 0, duration: 0, playing: false, paused: false, ended: false, buffering: false, loaded: false, started: false, speed: 1 };
const palette = [
  { background: '#E8F3FF', icon: '#1674E8' }, { background: '#F1EAFE', icon: '#8953E9' },
  { background: '#E7F8EF', icon: '#16A568' }, { background: '#FFF4E4', icon: '#E99113' },
  { background: '#FFECEF', icon: '#E64E66' }, { background: '#E6F6F8', icon: '#1595A7' },
];
const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;
const firstNameOf = (name?: string) => name?.trim().split(/\s+/)[0] || 'você';

export { Icon };
export type { IconName } from './Icon';

function readingMinutes(item: BriefingItem) {
  if (item.reading_time_minutes && item.reading_time_minutes > 0) return item.reading_time_minutes;
  const wordCount = `${item.headline || ''} ${item.summary || ''}`.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.ceil(wordCount / 200));
}
function publicationAge(item: BriefingItem) {
  const raw=item.published_at || item.sources?.find(source => source.published_at)?.published_at;
  if (!raw) return 'Data indisponível';
  const published=Date.parse(raw);
  if (!Number.isFinite(published)) return 'Data indisponível';
  const minutes=Math.max(0,Math.floor((Date.now()-published)/60000));
  if (minutes<1) return 'agora';
  if (minutes<60) return `há ${minutes} min`;
  const hours=Math.floor(minutes/60);
  if (hours<24) return `há ${hours} h`;
  const days=Math.floor(hours/24);
  return days===1 ? 'ontem' : `há ${days} dias`;
}
function topicPalette(topic: Topic, index: number) {
  const key = `${topic.code} ${topic.name}`.toLocaleLowerCase('pt-BR');
  if (/tech|tecnolog|comput|digital|software/.test(key)) return palette[0];
  if (/intelig|artificial|ciencia|ciência|pesquisa/.test(key)) return palette[1];
  if (/neg[oó]cio|startup|mercado|empresa/.test(key)) return palette[2];
  if (/econom|finan|dinheiro|moeda/.test(key)) return palette[3];
  if (/pol[ií]tic|governo|elei/.test(key)) return palette[4];
  if (/sa[uú]de|bem-estar|medicin/.test(key)) return { background: '#FCEAF1', icon: '#D84983' };
  return palette[index % palette.length];
}
function sectionLabel(label: string, onAll: () => void) {
  return <View style={h.sectionHead}><Text style={h.sectionTitle}>{label}</Text><Pressable accessibilityRole="button" accessibilityLabel={`Ver todos: ${label}`} onPress={onAll} hitSlop={8} style={h.allButton}><Text style={h.allText}>Ver todos</Text><Icon name="chevron" size={15} color={colors.primary} /></Pressable></View>;
}
function SavedButton({ saved, busy, onPress }: { saved: boolean; busy: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={saved ? 'Remover dos salvos' : 'Salvar notícia'} accessibilityState={{ selected: saved, disabled: busy }} disabled={busy} onPress={onPress} hitSlop={8} style={h.bookmarkButton}><Icon name="bookmark" size={21} color={saved ? colors.primary : '#0D244C'} /><View pointerEvents="none" style={saved ? h.bookmarkFill : undefined} /></Pressable>;
}
function TopicCard({ topic, index, width, onPress }: { topic: Topic; index: number; width: number; onPress: () => void }) {
  const tint = topicPalette(topic, index);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${topic.name}, ${topic.content_count ?? 0} notícias`} onPress={onPress} style={[h.topicCard, { width, backgroundColor: tint.background }]}>
    <View style={[h.topicIcon, { backgroundColor: `${tint.icon}20` }]}><Icon name="topic" size={24} color={tint.icon} /></View>
    <Text numberOfLines={2} style={h.topicName}>{topic.name}</Text>
    <Text style={h.topicCount}>{topic.content_count ?? 0} notícias</Text>
  </Pressable>;
}
function FeaturedCard({ item, width, saved, busy, onToggle, onPress }: { item: BriefingItem; width: number; saved: boolean; busy: boolean; onToggle: () => void; onPress: () => void }) {
  const imageHeight = 112;
  const category = item.primary_taxonomy_label || item.category;
  const categoryColor = topicPalette({ code: item.primary_taxonomy_id || '', name: category || '' }, item.position);
  return <View style={[h.featureCard, { width }]}>
    <Pressable accessibilityRole="button" accessibilityLabel={`Destaque: ${item.headline}`} onPress={onPress} style={h.featurePress}>
      <ArticleImage uri={item.image_url} articleId={item.id} accessibilityLabel={item.headline} style={{ width: '100%', height: imageHeight }} />
      {!!category && <Text numberOfLines={1} style={[h.categoryBadge, h.featureBadge, { backgroundColor: categoryColor.background, color: categoryColor.icon }]}>{category.toLocaleUpperCase('pt-BR')}</Text>}
      <View style={h.featureContent}><View style={h.featureMeta}><Icon name="clock" color={colors.secondary} size={16} /><Text style={h.featureTime}>{readingMinutes(item)} min</Text></View><Text numberOfLines={2} style={h.featureHeadline}>{item.headline}</Text></View>
    </Pressable>
    <View style={h.featureSave}><SavedButton saved={saved} busy={busy} onPress={onToggle} /></View>
  </View>;
}
function LatestRow({ item, saved, busy, onToggle, onPress }: { item: BriefingItem; saved: boolean; busy: boolean; onToggle: () => void; onPress: () => void }) {
  const tint = topicPalette({ code: item.primary_taxonomy_id || '', name: item.primary_taxonomy_label || item.category || '' }, item.position);
  return <View style={h.latestRow}>
    <Pressable accessibilityRole="button" accessibilityLabel={item.headline} onPress={onPress} style={h.latestPress}>
      <ArticleImage uri={item.image_url} articleId={item.id} accessibilityLabel={item.headline} style={h.latestImage} />
      <View style={h.latestCopy}><View style={h.latestMeta}><Text numberOfLines={1} style={[h.categoryBadge, { backgroundColor: tint.background, color: tint.icon }]}>{(item.primary_taxonomy_label || item.category || 'Notícias').toLocaleUpperCase('pt-BR')}</Text><Text style={h.readTimeText}>{publicationAge(item)}</Text></View><Text numberOfLines={2} style={h.latestHeadline}>{item.headline}</Text></View>
    </Pressable>
    <SavedButton saved={saved} busy={busy} onPress={onToggle} />
  </View>;
}

function Waveform({ progress, onSeek }: { progress: number; onSeek: (fraction: number) => void }) {
  const bars = useMemo(() => Array.from({ length: 34 }, (_, index) => 7 + ((index * 17 + index * index * 3) % 19)), []);
  const [width, setWidth] = useState(0);
  return <Pressable accessibilityRole="adjustable" accessibilityLabel="Progresso do áudio" accessibilityValue={{ min: 0, max: 100, now: Math.round(progress * 100) }} onPress={event => { if (width) onSeek(Math.max(0, Math.min(1, event.nativeEvent.locationX / width))); }} onLayout={event => setWidth(event.nativeEvent.layout.width)} style={h.waveTouch}>
    <View style={h.waveBars}>{bars.map((height, index) => <View key={index} style={{ width: 2.5, height, borderRadius: 2, backgroundColor: index / bars.length <= progress ? colors.primary : '#B9CBE3' }} />)}</View>
  </Pressable>;
}

function AudioControls({ briefing, audio, loading, regenerating }: { briefing: Briefing | null; audio: any; loading: boolean; regenerating: boolean }) {
  const [playback, setPlayback] = useState(initialPlayback);
  const [context, setContext] = useState<AudioContext | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => subscribeAudio(setPlayback), []);
  useEffect(() => subscribeAudioContext(setContext), []);
  useEffect(() => {
    if (!briefing?.id || !context || !sameBriefing(context.briefing, briefing) || !playback.loaded) return;
    const timer = setInterval(() => getAudioProgress().catch(() => undefined), 500);
    return () => clearInterval(timer);
  }, [briefing?.id, context?.url, playback.loaded]);
  const matching = Boolean(briefing && context && sameBriefing(context.briefing, briefing));
  // Today's briefing was regenerated (same delivery, new edition): drop the stale audio unless it is still being listened to.
  const staleSession = Boolean(briefing?.id && context?.briefing.id === briefing.id && !matching);
  useEffect(() => { if (staleSession && !playback.playing) releaseAudio(); }, [staleSession, playback.playing]);
  const ready = audio?.status === 'READY' && Boolean(audio.audio_url);
  const duration = matching && playback.loaded ? playback.duration : (audio?.duration_ms || 0) / 1000;
  const position = matching && playback.loaded ? playback.position : 0;
  const progress = duration ? position / duration : 0;
  const toggle = async () => {
    if (!briefing) return;
    if (matching && playback.loaded) {
      if (playback.playing) pauseAudio();
      else { setBusy(true); try { await playAudio(); } catch { /* the audio status poll remains authoritative */ } finally { setBusy(false); } }
      return;
    }
    if (!ready) return;
    setBusy(true);
    try {
      await loadAudio(audio.audio_url);
      setAudioContext(audio.audio_url, briefing, audio);
      await playAudio();
    } catch { /* keep the briefing visible and let the next status poll recover */ }
    finally { setBusy(false); }
  };
  const seekFraction = (fraction: number) => { if (matching && playback.loaded) seekTo(duration * fraction); };
  const failed = audio?.status === 'FAILED';
  const pending = !briefing || !audio || ['PENDING', 'GENERATING', 'VALIDATING', 'NOT_AVAILABLE'].includes(audio?.status);
  const stateMessage = regenerating ? 'Preparando seu novo briefing com as novas preferências. Você será notificado quando estiver pronto.' : loading ? 'Carregando seu briefing...' : !briefing ? 'Preparando seu briefing…' : failed ? 'Não foi possível preparar o áudio deste briefing.' : 'Preparando seu áudio…';
  return <View style={h.audioCard}>
    <View style={h.audioCardTop}>
      <View style={h.audioCardIcon}><Icon name="audio" color={colors.primary} size={31} /></View>
      <View style={h.audioCardCopy}><Text style={h.audioCardTitle}>Seu briefing diário</Text><Text style={h.audioCardSubtitle}>As principais notícias do mundo,{`\n`}em um briefing claro e objetivo.</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={playback.playing && matching ? 'Pausar briefing' : matching && playback.loaded ? 'Retomar briefing' : 'Reproduzir briefing'} accessibilityState={{ disabled: !briefing || busy || (!ready && !(matching && playback.loaded)) }} onPress={() => void toggle()} disabled={!briefing || busy || (!ready && !(matching && playback.loaded))} style={h.audioPlay}>
        {busy || playback.buffering && matching ? <ActivityIndicator color="#FFFFFF" size="small" /> : <Icon name={matching && playback.playing ? 'pause' : 'play'} color="#FFFFFF" size={28} />}
      </Pressable>
    </View>
    <View style={h.audioWaveRow}>
      {ready ? <Waveform progress={progress} onSeek={seekFraction} /> : <View style={h.wavePlaceholder}><View style={h.waveBars}>{Array.from({ length: 34 }, (_, index) => <View key={index} style={{ width: 2.5, height: 7 + ((index * 17 + index * index * 3) % 19), borderRadius: 2, backgroundColor: '#C9D9EB' }} />)}</View></View>}
    </View>
    <View style={h.audioTimes}><Text style={h.audioTime}>{clock(position)}</Text><Text style={h.audioTime}>{duration ? clock(duration) : ''}</Text></View>
    {(pending || failed || regenerating) && <View style={h.audioInlineState}><Text numberOfLines={2} style={h.audioState}>{stateMessage}</Text></View>}
  </View>;
}

export type HomeScreenProps = {
  user: User | null;
  onDetail: (item: BriefingItem) => void;
  onAudio: (briefing: Briefing) => void;
  onHistory: () => void;
  onAuthExpired: () => void;
  onSearch: () => void;
  onProfile: () => void;
  onExplore: () => void;
  onSchedule: () => void;
  onTopic: (topic: Topic) => void;
  onLatestBriefing: (briefing: Briefing | null) => void;
};

export function HomeScreen({ user, onDetail, onAuthExpired, onSearch, onProfile, onExplore, onSchedule, onLatestBriefing }: HomeScreenProps) {
  const contentRevisionTick=useContentRevisionTick();
  const { width } = useWindowDimensions();
  const bottomPadding = useFloatingTabContentInset(false);
  const [data, setData] = useState<HomeData | null>(null);
  const [audio, setAudio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [featuredIndex, setFeaturedIndex] = useState(0);
  const [clockNow, setClockNow] = useState(() => new Date());
  const deviceTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Sao_Paulo';
  const scheduleTimezone = data?.preferences.timezone || user?.timezone || deviceTimezone;
  const briefing = data?.today_briefing?.items?.length ? data.today_briefing : data?.latest_briefing || null;
  const playableBriefing = briefing;
  const latest = data?.latest_news || [];
  const [extraFeatured, setExtraFeatured] = useState<BriefingItem[]>([]);
  const featured = useMemo(() => pickFeatured(briefing?.items, latest, extraFeatured), [briefing?.items, latest, extraFeatured]);
  const focused = useIsFocused();
  const featuredScroll = useRef<ScrollView>(null);
  const featuredIndexRef = useRef(0);
  const featuredTouching = useRef(false);
  const featuredTouchedAt = useRef(0);
  const name = firstNameOf(user?.display_name);
  const avatarUrl = firebaseAuth.currentUser?.photoURL;
  const featureCardWidth = Math.max(280, width - 34);
  const load = useCallback(async () => {
    setLoadError('');
    try {
      const value = await api.home();
      setData(value);
      setSavedIds(new Set(value.saved_story_ids || []));
    } catch (error) {
      if (error instanceof ClientError && error.code === 'AUTH_REQUIRED') onAuthExpired();
      else setLoadError(error instanceof ClientError && error.code === 'BACKEND_UNREACHABLE' ? 'Não foi possível conectar ao backend.' : 'Não foi possível carregar a Home.');
    } finally { setLoading(false); }
  }, [onAuthExpired]);
  useEffect(() => { void load(); }, [load,contentRevisionTick]);
  useEffect(() => {
    if (!data || pickFeatured(briefing?.items, data.latest_news).length >= FEATURED_LIMIT) { setExtraFeatured([]); return; }
    let active = true;
    (async () => {
      const collected: BriefingItem[] = [];
      try { collected.push(...(await api.news(30)).items); } catch { /* keep whatever is already available */ }
      if (!active) return;
      // Stories outside the user's topics are only a last resort so the carousel is never empty.
      if (!pickFeatured(briefing?.items, data.latest_news, collected).length) {
        try { collected.push(...(await api.news(30, { discovery: true })).items); } catch { /* keep whatever is already available */ }
        if (!active) return;
      }
      setExtraFeatured(collected.filter(hasFeaturedImage));
    })();
    return () => { active = false; };
  }, [data, briefing?.items]);
  useEffect(() => {
    if (featuredIndexRef.current < featured.length) return;
    featuredIndexRef.current = 0;
    setFeaturedIndex(0);
    featuredScroll.current?.scrollTo({ x: 0, animated: false });
  }, [featured.length]);
  useEffect(() => {
    if (!focused || featured.length < 2) return;
    const timer = setInterval(() => {
      if (featuredTouching.current || Date.now() - featuredTouchedAt.current < FEATURED_RESUME_AFTER_TOUCH_MS) return;
      const next = (featuredIndexRef.current + 1) % featured.length;
      featuredIndexRef.current = next;
      setFeaturedIndex(next);
      featuredScroll.current?.scrollTo({ x: next * (featureCardWidth + 2), animated: true });
    }, FEATURED_AUTO_SCROLL_MS);
    return () => clearInterval(timer);
  }, [focused, featured.length, featureCardWidth]);
  const holdFeatured = () => { featuredTouching.current = true; featuredTouchedAt.current = Date.now(); };
  const releaseFeatured = () => { featuredTouching.current = false; featuredTouchedAt.current = Date.now(); };
  useEffect(() => { onLatestBriefing(playableBriefing); }, [playableBriefing, onLatestBriefing]);
  useEffect(() => {
    const listener=AppState.addEventListener('change', state => { if (state==='active') { setClockNow(new Date()); void load(); } });
    return () => listener.remove();
  },[load]);
  useEffect(() => {
    const timer = setInterval(() => setClockNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const regenerating=Boolean(data?.today_briefing?.profile_stale);
    const pending=['PENDING','AUDIO_QUEUED','GENERATING'].includes(data?.today_briefing?.status || '') || regenerating;
    if (!pending) return;
    // A preference-driven regeneration usually finishes in under a minute, so check more often.
    const interval=regenerating ? 10000 : 45000;
    let active=true; let timer: ReturnType<typeof setTimeout> | undefined;
    const poll=async()=>{ if (!active || AppState.currentState!=='active') return; await load(); if (active && AppState.currentState==='active') timer=setTimeout(poll,interval); };
    timer=setTimeout(poll,interval);
    const listener=AppState.addEventListener('change',state=>{
      if (state==='active') { if (timer) clearTimeout(timer); void poll(); }
      else if (timer) { clearTimeout(timer); timer=undefined; }
    });
    return ()=>{active=false;if(timer)clearTimeout(timer);listener.remove();};
  },[data?.today_briefing?.status,data?.today_briefing?.profile_stale,load]);
  useEffect(() => {
    setAudio(null);
    if (!briefing?.id) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule=(milliseconds:number)=>{ if (active && AppState.currentState==='active') timer=setTimeout(refreshAudio,milliseconds); };
    const refreshAudio = async () => {
      if (AppState.currentState!=='active') return;
      try {
        const result = await api.audio(briefing.id!);
        if (!active) return;
        setAudio(result);
        const activelyPreparing=['PENDING','GENERATING','VALIDATING'].includes(result.status) || (result.status==='NOT_AVAILABLE' && Boolean(result.generation_stage));
        const lastUpdate=result.generation_updated_at ? Date.parse(result.generation_updated_at) : 0;
        if (activelyPreparing && (!lastUpdate || Date.now()-lastUpdate<30*60*1000)) schedule(45000);
      } catch { schedule(60000); }
    };
    void refreshAudio();
    const listener=AppState.addEventListener('change',state=>{
      if (state==='active') { if (timer) clearTimeout(timer); void refreshAudio(); }
      else if (timer) { clearTimeout(timer); timer=undefined; }
    });
    return () => { active = false; if (timer) clearTimeout(timer); listener.remove(); };
  }, [briefing?.id, briefing?.generation_updated_at, briefing?.generation_stage]);
  const toggleSaved = async (story: BriefingItem) => {
    const wasSaved = savedIds.has(story.id);
    setSavingIds(current => new Set(current).add(story.id));
    setSavedIds(current => { const next = new Set(current); wasSaved ? next.delete(story.id) : next.add(story.id); return next; });
    try { if (wasSaved) await api.removeSavedStory(story.id); else await api.saveStory(story); }
    catch { setSavedIds(current => { const next = new Set(current); wasSaved ? next.add(story.id) : next.delete(story.id); return next; }); }
    finally { setSavingIds(current => { const next = new Set(current); next.delete(story.id); return next; }); }
  };
  const nextLabel = data?.preferences.briefing_time ? nextBriefingLabel(data.preferences.briefing_time, scheduleTimezone, clockNow) : loading ? 'Carregando horário...' : 'Horário indisponível';

  return <SafeAreaView style={h.safe} edges={Platform.OS === 'android' ? [] : ['top']}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <ScrollView style={h.scroll} contentContainerStyle={[h.content, { paddingBottom: bottomPadding }]}>
      <View style={h.header}>
        <Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={h.logo} />
        <View style={h.headerActions}>
          <Pressable accessibilityRole="button" accessibilityLabel="Buscar notícias" onPress={onSearch} style={h.headerIcon}><Icon name="search" size={23} /></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Abrir perfil" onPress={onProfile} style={h.avatarButton}>
            <Image source={avatarUrl ? { uri: avatarUrl } : fallbackMascot} resizeMode="cover" style={h.avatar} />
          </Pressable>
        </View>
      </View>

      <View style={h.greetingArea}>
        <View style={h.greetingText}>
          <Text style={h.greeting}>{greetingForLocalTime(clockNow, deviceTimezone)}</Text>
          <View style={h.nameLine}><Text numberOfLines={1} style={h.name}>{name}</Text></View>
          <Text style={h.date}>{formatHomeDate(clockNow, deviceTimezone)}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel={`Próximo briefing ${nextLabel}`} onPress={onSchedule} style={h.nextCard}>
          <Icon name="sun" size={20} color="#E99113" /><View style={h.nextCopy}><Text numberOfLines={1} style={h.nextTitle}>Seu próximo briefing</Text><Text numberOfLines={1} style={h.nextTime}>{nextLabel}</Text></View><Icon name="chevron" size={14} color={colors.text} />
        </Pressable>
      </View>

      {!!loadError && <Pressable accessibilityRole="button" onPress={() => void load()} style={h.homeError}><Text style={h.homeErrorText}>{loadError}  ·  Tentar novamente</Text></Pressable>}


      <AudioControls briefing={briefing} audio={audio} loading={loading} regenerating={Boolean(data?.today_briefing?.profile_stale)} />

      <View style={h.section}>{sectionLabel('Destaques de hoje', onExplore)}
        {featured.length ? <>
          <ScrollView ref={featuredScroll} onTouchStart={holdFeatured} onTouchEnd={releaseFeatured} onTouchCancel={releaseFeatured} onScrollBeginDrag={holdFeatured} onScrollEndDrag={releaseFeatured} horizontal pagingEnabled snapToInterval={featureCardWidth + 2} decelerationRate="fast" showsHorizontalScrollIndicator={false} nestedScrollEnabled contentContainerStyle={h.featureCarousel} onMomentumScrollEnd={event => { const index = Math.round(event.nativeEvent.contentOffset.x / (featureCardWidth + 2)); featuredIndexRef.current = index; setFeaturedIndex(index); }}>
            {featured.map(item => <FeaturedCard key={item.id} item={item} width={featureCardWidth} saved={savedIds.has(item.id)} busy={savingIds.has(item.id)} onToggle={() => void toggleSaved(item)} onPress={() => onDetail(item)} />)}
          </ScrollView>
          <View style={h.carouselDots} accessibilityLabel={`Destaque ${featuredIndex + 1} de ${featured.length}`}>{featured.map((item, index) => <View key={item.id} style={[h.carouselDot, index === featuredIndex && h.carouselDotActive]} />)}</View>
        </> : <View style={[h.featureSkeleton, { width: featureCardWidth }]} />}
      </View>

      <View style={h.section}>{sectionLabel('Últimas notícias', onExplore)}
        {loading ? <View style={h.latestSkeletons}>{[0, 1, 2].map(index => <View key={index} style={h.latestSkeleton} />)}</View> : latest.length ? latest.map(item => <LatestRow key={item.id} item={item} saved={savedIds.has(item.id)} busy={savingIds.has(item.id)} onToggle={() => void toggleSaved(item)} onPress={() => onDetail(item)} />) : <Text style={h.emptyInline}>As notícias mais recentes aparecerão aqui.</Text>}
      </View>
    </ScrollView>
  </SafeAreaView>;
}

export function SearchScreen({ onBack, onDetail }: { onBack: () => void; onDetail: (item: BriefingItem) => void }) {
  const revisionTick=useContentRevisionTick();
  const [query, setQuery] = useState(''); const [submittedQuery,setSubmittedQuery]=useState(''); const [retry,setRetry]=useState(0); const [items, setItems] = useState<BriefingItem[]>([]); const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const search = () => { if (query.trim()) { setSubmittedQuery(query.trim()); setRetry(value=>value+1); } };
  useEffect(()=>{
    if (!submittedQuery) return;
    let active=true;setLoading(true);setError('');
    api.news(20,{query:submittedQuery}).then(result=>{if(active)setItems(result.items);})
      .catch(()=>{if(active)setError('Não foi possível buscar notícias.');})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[submittedQuery,retry,revisionTick]);
  return <SafeAreaView style={h.searchScreen} edges={['top']}><StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <View style={h.searchHeader}><Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={h.searchBack}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.text} size={20} /></View></Pressable><View style={h.searchField}><Icon name="search" color={colors.secondary} /><TextInput accessibilityLabel="Buscar notícias" placeholder="Buscar notícias" placeholderTextColor={colors.muted} value={query} onChangeText={setQuery} onSubmitEditing={() => void search()} returnKeyType="search" autoFocus style={h.searchInput} /><Pressable accessibilityRole="button" accessibilityLabel="Buscar" onPress={() => void search()}><Icon name="chevron" color={colors.primary} /></Pressable></View></View>
    {loading ? <ActivityIndicator accessibilityLabel="Buscando notícias" color={colors.primary} style={{ marginTop: 30 }} /> : <ScrollView contentContainerStyle={h.searchResults}>{error ? <View><Text accessibilityRole="alert" style={h.emptyInline}>{error}</Text><Pressable accessibilityRole="button" onPress={() => void search()}><Text style={h.retryLink}>Tentar novamente</Text></Pressable></View> : items.length ? items.map(item => <Pressable key={item.id} accessibilityRole="button" onPress={() => onDetail(item)} style={h.searchResult}><ArticleImage uri={item.image_url} articleId={item.id} accessibilityLabel={item.headline} style={h.searchResultImage} /><View style={h.searchResultCopy}><Text style={h.searchCategory}>{item.primary_taxonomy_label || 'Notícias'}</Text><Text style={h.searchHeadline}>{item.headline}</Text><Text numberOfLines={2} style={h.searchSummary}>{item.summary}</Text></View></Pressable>) : <Text style={h.emptyInline}>Digite um assunto ou uma palavra para buscar.</Text>}</ScrollView>}
  </SafeAreaView>;
}

export function TopicFeedScreen({ topic, onBack, onDetail }: { topic: Topic; onBack: () => void; onDetail: (item: BriefingItem) => void }) {
  const revisionTick=useContentRevisionTick();
  const [items, setItems] = useState<BriefingItem[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    api.news(30, { topic: topic.code }).then(result => { if (active) setItems(result.items); }).catch(() => { if (active) { setItems([]); setError('Não foi possível carregar este assunto agora.'); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [topic.code, retry,revisionTick]);
  return <SafeAreaView style={h.searchScreen} edges={['top']}><StatusBar barStyle="dark-content" backgroundColor={colors.background} /><View style={h.searchHeader}><Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={h.searchBack}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.text} size={20} /></View></Pressable><Text style={h.topicFeedTitle}>{topic.name}</Text></View><ScrollView contentContainerStyle={h.searchResults}>{loading ? <ActivityIndicator accessibilityLabel="Carregando notícias" color={colors.primary} style={{ marginTop: 30 }} /> : error ? <View><Text accessibilityRole="alert" style={h.emptyInline}>{error}</Text><Pressable accessibilityRole="button" onPress={() => setRetry(value => value + 1)}><Text style={h.retryLink}>Tentar novamente</Text></Pressable></View> : items.length ? items.map(item => <Pressable key={item.id} accessibilityRole="button" onPress={() => onDetail(item)} style={h.searchResult}><ArticleImage uri={item.image_url} articleId={item.id} accessibilityLabel={item.headline} style={h.searchResultImage} /><View style={h.searchResultCopy}><Text style={h.searchCategory}>{item.primary_taxonomy_label || topic.name}</Text><Text style={h.searchHeadline}>{item.headline}</Text><Text numberOfLines={3} style={h.searchSummary}>{item.summary}</Text></View></Pressable>) : <Text style={h.emptyInline}>Ainda não há notícias recentes neste assunto.</Text>}</ScrollView></SafeAreaView>;
}

const h = {
  safe: { flex: 1, backgroundColor: colors.background } as const, scroll: { flex: 1 } as const,
  content: { paddingHorizontal: 16, paddingTop: 4 } as const,
  header: { height: 52, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 6 },
  logo: { width: 130, height: 46, marginLeft: -4 }, headerActions: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12 },
  headerIcon: { width: 34, height: 40, alignItems: 'center' as const, justifyContent: 'center' as const, position: 'relative' as const },
  avatarButton: { width: 40, height: 40, borderRadius: 20, overflow: 'hidden' as const, backgroundColor: colors.surfaceBlue }, avatar: { width: '100%' as const, height: '100%' as const },
  greetingArea: { minHeight: 92, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, gap: 8, marginBottom: 9 }, greetingText: { flex: 1, minWidth: 0 },
  greeting: { fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 19, color: colors.secondary }, nameLine: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 }, name: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 30, lineHeight: 35, flexShrink: 1 }, date: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, lineHeight: 15, marginTop: 2, flexShrink: 1 },
  nextCard: { width: 154, minHeight: 62, borderRadius: 19, backgroundColor: '#E7F2FF', flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 8, gap: 5 }, nextCopy: { flex: 1, minWidth: 0 }, nextTitle: { fontFamily: typography.fontFamily.ui, fontSize: 9, color: colors.secondary }, nextTime: { fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '700' as const, color: colors.textPrimary, marginTop: 3 },
  audioCard: { marginBottom: 15, borderRadius: 25, borderWidth: 1, borderColor: '#E4EEF8', backgroundColor: '#FFFFFFE8', paddingHorizontal: 15, paddingVertical: 12 }, audioCardTop: { minHeight: 57, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10 }, audioCardIcon: { width: 34, alignItems: 'center' as const, justifyContent: 'center' as const }, audioCardCopy: { flex: 1, minWidth: 0 }, audioCardTitle: { color: '#0B1D45', fontFamily: typography.fontFamily.ui, fontSize: 17, lineHeight: 22, fontWeight: '800' as const }, audioCardSubtitle: { color: '#60769A', fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 16, marginTop: 2 }, audioPlay: { width: 54, height: 54, borderRadius: 28, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary, shadowColor: colors.primary, shadowOpacity: .16, shadowRadius: 6, elevation: 2 }, audioWaveRow: { marginTop: 8 }, waveTouch: { height: 22, justifyContent: 'center' as const }, wavePlaceholder: { height: 22, justifyContent: 'center' as const }, waveBars: { height: 23, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, overflow: 'hidden' as const }, audioTimes: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, marginTop: 2 }, audioTime: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 11 }, audioState: { flex: 1, fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 10 }, audioInlineState: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, gap: 8, marginTop: 5 }, audioRetry: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '700' as const },
  homeError: { minHeight: 38, justifyContent: 'center' as const, paddingHorizontal: 12, borderRadius: 13, backgroundColor: '#FFF6F5', marginBottom: 10 }, homeErrorText: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: 11 },
  section: { marginBottom: 12 }, sectionHead: { height: 28, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginHorizontal: 5, marginBottom: 5 }, sectionTitle: { fontFamily: typography.fontFamily.ui, fontSize: 17, lineHeight: 22, color: '#071A42', fontWeight: '800' as const, letterSpacing: -.35 }, allButton: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 1 }, allText: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.primary, fontWeight: '600' as const }, horizontalContent: { gap: 6, paddingHorizontal: 1, paddingBottom: 1 }, topicCard: { minHeight: 73, borderRadius: 17, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 4, paddingVertical: 5 }, topicIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 3 }, topicName: { fontFamily: typography.fontFamily.ui, color: '#11254A', fontSize: 10, fontWeight: '700' as const, textAlign: 'center' as const, lineHeight: 12 }, topicCount: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 9, marginTop: 3 },
  featureCarousel: { gap: 2, paddingHorizontal: 1 }, featureCard: { position: 'relative' as const, borderRadius: 21, backgroundColor: '#FFFFFF', overflow: 'hidden' as const, borderWidth: 1, borderColor: '#DCEAF7', minHeight: 186 }, featurePress: { overflow: 'hidden' as const }, featureBadge: { position: 'absolute' as const, top: 9, left: 10 }, featureContent: { minHeight: 70, paddingLeft: 13, paddingTop: 8, paddingRight: 54, paddingBottom: 9, backgroundColor: '#FFFFFFF0' }, featureMeta: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 5 }, featureTime: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11 }, categoryBadge: { alignSelf: 'flex-start' as const, overflow: 'hidden' as const, maxWidth: '100%' as const, borderRadius: 14, paddingHorizontal: 9, paddingVertical: 4, fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800' as const }, featureHeadline: { fontFamily: typography.fontFamily.ui, fontSize: 17, lineHeight: 21, fontWeight: '700' as const, color: '#091D42', marginTop: 3 }, featureSave: { position: 'absolute' as const, right: 10, bottom: 8, backgroundColor: '#FFFFFFE8', borderRadius: 16 }, carouselDots: { flexDirection: 'row' as const, justifyContent: 'center' as const, alignItems: 'center' as const, gap: 8, paddingTop: 9 }, carouselDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#C8D8EC' }, carouselDotActive: { backgroundColor: colors.primary, width: 9, height: 9 },
  bookmarkButton: { width: 34, height: 34, borderRadius: 17, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: '#FFFFFFE8' }, bookmarkFill: { position: 'absolute' as const, width: 6, height: 9, top: 10, left: 14, backgroundColor: colors.primary },
  latestRow: { minHeight: 66, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 5, marginHorizontal: 2, borderBottomWidth: 1, borderBottomColor: '#E6EFF8', paddingVertical: 5 }, latestPress: { flex: 1, minWidth: 0, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9 }, latestImage: { width: 66, height: 50, borderRadius: 10 }, latestCopy: { flex: 1, minWidth: 0 }, latestMeta: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 7 }, readTimeText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11 }, latestHeadline: { fontFamily: typography.fontFamily.ui, color: '#15294E', fontSize: 13, lineHeight: 17, marginTop: 2 },
  skeletonTopics: { flexDirection: 'row' as const, gap: 6 }, topicSkeleton: { height: 79, borderRadius: 17, backgroundColor: '#E7F1FB' }, featureSkeleton: { height: 186, borderRadius: 21, backgroundColor: '#E7F1FB' }, latestSkeletons: { gap: 8 }, latestSkeleton: { height: 63, borderRadius: 12, backgroundColor: '#E7F1FB' }, emptyInline: { paddingHorizontal: 8, paddingVertical: 12, color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12 },
  searchScreen: { flex: 1, backgroundColor: colors.background }, searchHeader: { minHeight: 58, paddingHorizontal: 16, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 }, searchBack: { width: 36, height: 44, justifyContent: 'center' as const }, searchField: { flex: 1, height: 46, borderRadius: 23, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, paddingHorizontal: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, searchInput: { flex: 1, fontFamily: typography.fontFamily.ui, color: colors.textPrimary, paddingVertical: 0 }, searchResults: { padding: 16, gap: 9 }, searchResult: { flexDirection: 'row' as const, alignItems: 'flex-start' as const, gap: 11, backgroundColor: colors.surface, borderRadius: 15, padding: 10, borderWidth: 1, borderColor: colors.border }, searchResultImage: { width: 82, height: 82, borderRadius: 12 }, searchResultCopy: { flex: 1, minWidth: 0 }, searchCategory: { color: colors.primary, fontSize: 11, fontWeight: '700' as const }, searchHeadline: { color: colors.textPrimary, fontSize: 15, lineHeight: 20, fontWeight: '700' as const, marginTop: 5 }, searchSummary: { color: colors.secondary, fontSize: 13, lineHeight: 18, marginTop: 5 }, retryLink: { color: colors.primary, fontWeight: '700' as const, fontSize: 13, paddingHorizontal: 8, paddingVertical: 10 }, topicFeedTitle: { color: colors.textPrimary, fontSize: 20, fontWeight: '800' as const },
} as const;
