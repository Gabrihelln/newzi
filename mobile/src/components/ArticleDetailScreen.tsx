import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Image, Linking, Pressable, SafeAreaView, ScrollView, Share, StatusBar, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { devLog } from '../config/env';
import { Icon } from './Icon';
import { useLogo } from './brand';
import { ArticleImage } from './ArticleImage';
import { StoryPremiumActions } from './StoryPremiumActions';
import {useStyles, useTheme, type Palette } from '../theme';
import type { Briefing, BriefingItem, Topic } from '../types/api';

const feedbackOptionsFor = (colors: Palette) => [
  { rating: 5, label: 'Ótima', icon: 'ratingGreat' as const, color: colors.topicBlue.icon, tint: colors.surfaceBlue },
  { rating: 4, label: 'Boa', icon: 'ratingGood' as const, color: colors.sun, tint: colors.warningSurface },
  { rating: 3, label: 'Neutra', icon: 'ratingNeutral' as const, color: colors.secondary, tint: colors.surfaceBlue },
  { rating: 2, label: 'Ruim', icon: 'ratingBad' as const, color: colors.tone('#DF6470', colors.danger), tint: colors.dangerSurface },
  { rating: 1, label: 'Péssima', icon: 'ratingPoor' as const, color: colors.tone('#D73A4A', colors.danger), tint: colors.tone('#FFE8E9', colors.dangerSurface) },
];

type Props = {
  item: BriefingItem;
  onBack: () => void;
  onRelated: (item: BriefingItem) => void;
  onTopic: (topic: Topic) => void;
  onBriefing: (briefing: Briefing) => void;
  trackReadingProgress?: boolean;
  readingProgress?: number;
};

const words = (value: string) => value.trim().split(/\s+/).filter(Boolean).length;
const displayMinutes = (item: BriefingItem) => item.reading_time_minutes || Math.max(1, Math.ceil(words([item.summary, item.why_it_matters, ...(item.key_points || [])].filter(Boolean).join(' ')) / 220));
const formatDate = (raw?: string | null) => {
  if (!raw) return '';
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
};

export function ArticleDetailScreen({ item, onBack, onRelated, onTopic, onBriefing, trackReadingProgress = false, readingProgress = 0 }: Props) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [saved, setSaved] = useState(false);
  const [savedReady, setSavedReady] = useState(false);
  const [savedError, setSavedError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [related, setRelated] = useState<BriefingItem[]>([]);
  const [relatedError, setRelatedError] = useState(false);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState('');
  const [sourceError, setSourceError] = useState('');
  const [resourceRetryKey, setResourceRetryKey] = useState(0);
  const scroll = useRef<ScrollView>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewport = useRef(0);
  const contentHeight = useRef(0);
  const restored = useRef(false);
  const category = item.primary_taxonomy_label || item.category || '';
  const source = item.sources?.find(entry => entry.publisher || entry.name || entry.url);
  // The first source is the story shown; the others are outlets that covered the same event.
  const outlets = (item.sources || []).filter((entry, index, all) => (entry.publisher || entry.name) && all.findIndex(other => (other.publisher || other.name) === (entry.publisher || entry.name)) === index);
  const publishedAt = formatDate(item.published_at || source?.published_at);
  const currentContentIds = useMemo(() => new Set([item.id, ...(item.sources || []).map(entry => entry.article_id).filter((id): id is string => Boolean(id))]), [item.id, item.sources]);
  const currentInBriefing = Boolean(briefing?.items?.some(story => story.id === item.id || (story.sources || []).some(entry => entry.article_id && currentContentIds.has(entry.article_id))));

  const restoreProgress = useCallback(() => {
    if (!trackReadingProgress || restored.current || !viewport.current || !contentHeight.current) return;
    const max = Math.max(0, contentHeight.current - viewport.current);
    scroll.current?.scrollTo({ y: max * Math.max(0, Math.min(100, readingProgress)) / 100, animated: false });
    restored.current = true;
  }, [trackReadingProgress, readingProgress]);

  useEffect(() => {
    let active = true;
    restored.current = false;
    setSavedReady(false); setSavedError(false); setRelatedError(false);
    api.savedStories().then(result => { if (active) { setSaved((result.items || []).some(story => story.id === item.id)); setSavedReady(true); } }).catch(() => { if (active) { setSavedError(true); devLog(`[ArticleDetail] saved-status unavailable item=${item.id}`); } });
    api.articleFeedback(item.id).then(result => { if (active) setRating(result.rating ?? null); }).catch(() => { if (active) devLog(`[ArticleDetail] feedback unavailable item=${item.id}`); });
    api.news(5, category ? { topic: item.primary_taxonomy_id || category } : {}).then(result => {
      if (active) setRelated((result.items || []).filter(story => story.id !== item.id && !(story.sources || []).some(entry => entry.article_id && currentContentIds.has(entry.article_id))).filter((story, index, all) => all.findIndex(candidate => candidate.id === story.id) === index).slice(0, 2));
    }).catch(() => { if (active) { setRelated([]); setRelatedError(true); devLog(`[ArticleDetail] related-stories unavailable item=${item.id}`); } });
    api.today().then(result => { if (active) setBriefing(result as Briefing); }).catch(() => { if (active) { setBriefing(null); devLog(`[ArticleDetail] current-briefing unavailable item=${item.id}`); } });
    return () => { active = false; if (timer.current) clearTimeout(timer.current); };
  }, [item.id, item.primary_taxonomy_id, category, currentContentIds, resourceRetryKey]);

  const saveProgress = (y: number) => {
    if (!trackReadingProgress || !restored.current) return;
    const max = Math.max(0, contentHeight.current - viewport.current);
    if (max < 1) return;
    const progress = Math.max(0, Math.min(100, y / max * 100));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void api.saveReadingProgress(item.id, progress).catch(() => devLog(`[ArticleDetail] reading-progress sync failed item=${item.id}`)); }, 650);
  };

  const toggleSaved = async () => {
    if (saving || !savedReady) return;
    const previous = saved;
    setSaving(true); setSaved(!previous);
    try { if (previous) await api.removeSavedStory(item.id); else await api.saveStory(item); }
    catch { setSaved(previous); Alert.alert('Não foi possível salvar', 'Tente novamente quando a conexão estiver disponível.'); }
    finally { setSaving(false); }
  };
  const share = async () => {
    try { await Share.share({ message: [item.headline, source?.url].filter(Boolean).join('\n') }); }
    catch { Alert.alert('Compartilhamento indisponível', 'Não foi possível abrir o menu de compartilhamento.'); }
  };
  const openSource = async (url?: string) => {
    if (!url) { setSourceError('O link da fonte original não está disponível.'); return; }
    try { await Linking.openURL(url); } catch { setSourceError('Não foi possível abrir esta fonte.'); }
  };
  const openMore = () => Alert.alert('Opções da notícia', undefined, [
    ...(source?.url ? [{ text: 'Abrir fonte original', onPress: () => { void openSource(source.url); } }] : []),
    { text: saved ? 'Remover dos salvos' : 'Salvar notícia', onPress: () => { void toggleSaved(); } },
    { text: 'Compartilhar', onPress: () => { void share(); } },
    { text: 'Cancelar', style: 'cancel' },
  ]);
  const sendFeedback = async (next: number) => {
    const previous = rating;
    setRating(next); setFeedbackStatus('Salvando…');
    try { await api.articleFeedback(item.id, next); setFeedbackStatus('Opinião salva.'); }
    catch { setRating(previous); setFeedbackStatus('Não foi possível salvar sua opinião.'); }
  };
  const topic: Topic = { id: item.primary_taxonomy_id || undefined, code: item.primary_taxonomy_id || category, name: category || 'Notícias' };

  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle={theme.statusBar} backgroundColor={colors.readerBackground} />
    <ScrollView ref={scroll} style={s.scroll} contentContainerStyle={s.content} onLayout={event => { viewport.current = event.nativeEvent.layout.height; restoreProgress(); }} onContentSizeChange={(_width, height) => { contentHeight.current = height; restoreProgress(); }} onScroll={event => saveProgress(event.nativeEvent.contentOffset.y)} scrollEventThrottle={250}>
      <ReaderHeader onBack={onBack} saved={saved} saving={saving} savedReady={savedReady} onBookmark={() => { void toggleSaved(); }} onShare={() => { void share(); }} onMore={openMore} />
      {savedError && <View accessibilityRole="alert" style={s.resourceNotice}><Text style={s.resourceNoticeText}>Não foi possível verificar os itens salvos.</Text><Pressable accessibilityRole="button" onPress={() => setResourceRetryKey(value => value + 1)}><Text style={s.resourceRetry}>Tentar novamente</Text></Pressable></View>}
      <ArticleImage uri={item.image_url} articleId={item.sources?.find(source => source.article_id)?.article_id || item.id} accessibilityLabel={item.headline} style={s.hero} />
      <View style={s.article}>
        <View style={s.metaRow}>
          {category ? <Text numberOfLines={1} style={s.category}>{category.toLocaleUpperCase('pt-BR')}</Text> : <View />}
          <View style={s.readMeta}><Icon name="clock" size={16} color={colors.secondary} /><Text style={s.readTime}>{displayMinutes(item)} min de leitura</Text></View>
        </View>
        <Text accessibilityRole="header" style={s.headline}>{item.headline}</Text>
        {!!item.summary && <Text style={s.deck}>{item.summary}</Text>}
        <View style={s.authorRow}>
          <View style={s.sourceAvatar}><Text style={s.sourceGlyph}>{(source?.publisher || source?.name || 'N').slice(0, 1).toLocaleUpperCase('pt-BR')}</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={s.sourceName}>{source?.publisher || source?.name ? `Fonte: ${source.publisher || source.name}${outlets.length > 1 ? ` e mais ${outlets.length - 1}` : ''}` : 'Fonte não informada'}</Text>
            <Text style={s.date}>{publishedAt || 'Data de publicação indisponível'}</Text>
          </View>
        </View>
        <StoryPremiumActions story={item} onSaved={() => setSaved(true)} />
        {!!item.why_it_matters?.trim() && item.why_it_matters.trim() !== item.summary.trim() && <Text style={s.body}>{item.why_it_matters}</Text>}
        {!!(item.key_points || []).length && <View style={s.keyCard}>
          <View style={s.keyTitleRow}><Icon name="article" color={colors.primary} size={20} /><Text accessibilityRole="header" style={s.keyTitle}>Principais pontos</Text></View>
          {(item.key_points || []).map((point, index) => <View key={`${index}-${point}`} style={s.keyRow}><Icon name="checkCircle" color={colors.primary} size={18} /><Text style={s.keyText}>{point}</Text></View>)}
        </View>}
        {outlets.length > 1 && <View style={s.keyCard}>
          <View style={s.keyTitleRow}><Icon name="explore" color={colors.primary} size={20} /><Text accessibilityRole="header" style={s.keyTitle}>Coberto por {outlets.length} veículos</Text></View>
          {outlets.map(outlet => <Pressable key={outlet.url} accessibilityRole="link" accessibilityLabel={`Abrir matéria de ${outlet.publisher || outlet.name}`} onPress={() => { void openSource(outlet.url); }} style={({ pressed }) => [s.keyRow, { alignItems: 'center', opacity: pressed ? .7 : 1 }]}>
            <View style={[s.sourceAvatar, { width: 28, height: 28, borderRadius: 14 }]}><Text style={[s.sourceGlyph, { fontSize: 13 }]}>{(outlet.publisher || outlet.name || 'N').slice(0, 1).toLocaleUpperCase('pt-BR')}</Text></View>
            <Text style={[s.keyText, { flex: 1 }]}>{outlet.publisher || outlet.name}</Text>
            <Icon name="chevron" color={colors.primary} size={16} />
          </Pressable>)}
        </View>}
        {!!sourceError && <Text accessibilityRole="alert" style={s.error}>{sourceError}</Text>}
        {related.length > 0 && <RelatedStories items={related} onMore={() => onTopic(topic)} onOpen={onRelated} />}
        {relatedError && <View accessibilityRole="alert" style={s.resourceNotice}><Text style={s.resourceNoticeText}>Não foi possível carregar notícias relacionadas.</Text><Pressable accessibilityRole="button" onPress={() => setResourceRetryKey(value => value + 1)}><Text style={s.resourceRetry}>Tentar novamente</Text></Pressable></View>}
        {!!briefing && <Pressable accessibilityRole="button" accessibilityLabel={currentInBriefing ? 'Ouça este tema no resumo de hoje. Esta notícia está entre as escolhidas para você hoje.' : 'Ouça o resumo de hoje'} onPress={() => onBriefing(briefing)} style={s.briefingCard}>
          <Icon name="sun" color={colors.sun} size={25} /><View style={{ flex: 1 }}><Text style={s.briefingTitle}>{currentInBriefing ? 'Ouça este tema no resumo de hoje' : 'Ouça o resumo de hoje'}</Text><Text style={s.briefingSub}>{currentInBriefing ? 'Esta notícia está entre as escolhidas para você hoje' : 'Acesse seu resumo diário personalizado'}</Text></View><Icon name="chevron" color={colors.primary} size={18} />
        </Pressable>}
        <ArticleFeedback rating={rating} status={feedbackStatus} onChoose={sendFeedback} />
      </View>
      <View style={{ height: 34 }} />
    </ScrollView>
  </SafeAreaView>;
}

export function ArticleLoadState({ onBack, onRetry, loading, error }: { onBack: () => void; onRetry: () => void; loading: boolean; error: string }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle={theme.statusBar} backgroundColor={colors.readerBackground} />
    <ScrollView style={s.scroll} contentContainerStyle={s.content}>
      <ReaderHeader onBack={onBack} saved={false} saving savedReady={false} onBookmark={() => undefined} onShare={() => undefined} onMore={() => undefined} />
      <View style={[s.hero, { backgroundColor: colors.placeholder }]} />
      <View style={s.article}>
        {loading ? <><View style={{ height: 28, width: '42%', borderRadius: 15, backgroundColor: colors.placeholder, marginBottom: 20 }} /><View style={{ height: 38, borderRadius: 8, backgroundColor: colors.placeholder, marginBottom: 8 }} /><View style={{ height: 38, width: '76%', borderRadius: 8, backgroundColor: colors.placeholder, marginBottom: 18 }} /><View style={{ height: 94, borderRadius: 16, backgroundColor: colors.placeholder, marginBottom: 18 }} /><View style={{ height: 20, borderRadius: 8, backgroundColor: colors.placeholder, marginBottom: 9 }} /><View style={{ height: 20, width: '82%', borderRadius: 8, backgroundColor: colors.placeholder }} /></> : <>
          <Text accessibilityRole="header" style={s.headline}>Não foi possível carregar esta notícia.</Text>
          <Text style={s.deck}>{error || 'Verifique sua conexão e tente novamente.'}</Text>
          <Pressable accessibilityRole="button" onPress={onRetry} style={{ marginTop: 18, alignSelf: 'flex-start', borderRadius: 24, backgroundColor: colors.primary, paddingHorizontal: 22, paddingVertical: 13 }}><Text style={{ color: colors.onPrimary, fontWeight: '700', fontSize: 14 }}>Tentar novamente</Text></Pressable>
        </>}
      </View>
    </ScrollView>
  </SafeAreaView>;
}

function ReaderHeader({ onBack, saved, saving, savedReady, onBookmark, onShare, onMore }: { onBack: () => void; saved: boolean; saving: boolean; savedReady: boolean; onBookmark: () => void; onShare: () => void; onMore: () => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={s.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={s.headerButton}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.textPrimary} size={21} /></View></Pressable>
    <Image source={useLogo()} resizeMode="contain" accessibilityLabel="NEWZI" style={s.logo} />
    <View style={s.headerActions}>
      <Pressable accessibilityRole="button" accessibilityLabel={saved ? 'Remover notícia dos salvos' : 'Salvar notícia'} accessibilityState={{ selected: saved, disabled: saving || !savedReady }} disabled={saving || !savedReady} onPress={onBookmark} style={s.headerButton}><Icon name="bookmark" filled={saved} color={saved ? colors.primary : colors.tone('#1D3767', colors.body)} size={22} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Compartilhar notícia" onPress={onShare} style={s.headerButton}><Icon name="share" color={colors.tone('#1D3767', colors.body)} size={20} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Mais opções da notícia" onPress={onMore} style={s.headerButton}><Icon name="more" color={colors.tone('#1D3767', colors.body)} size={22} /></Pressable>
    </View>
  </View>;
}

function RelatedStories({ items, onMore, onOpen }: { items: BriefingItem[]; onMore: () => void; onOpen: (item: BriefingItem) => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={s.relatedSection}>
    <View style={s.relatedHeading}><Text accessibilityRole="header" style={s.relatedTitle}>Leia também</Text><Pressable accessibilityRole="button" onPress={onMore} style={s.moreButton}><Text style={s.moreText}>Ver mais</Text><Icon name="chevron" color={colors.primary} size={17} /></Pressable></View>
    {items.map(story => <Pressable key={story.id} accessibilityRole="button" accessibilityLabel={`${story.headline}, ${story.primary_taxonomy_label || story.category || 'Notícias'}`} onPress={() => onOpen(story)} style={s.relatedRow}>
      <ArticleImage uri={story.image_url} articleId={story.id} accessibilityLabel={story.headline} style={s.relatedImage} />
      <View style={s.relatedCopy}>{!!(story.primary_taxonomy_label || story.category) && <Text numberOfLines={1} style={s.relatedCategory}>{(story.primary_taxonomy_label || story.category)?.toLocaleUpperCase('pt-BR')}</Text>}<Text numberOfLines={2} style={s.relatedHeadline}>{story.headline}</Text><Text style={s.relatedTime}>{displayMinutes(story)} min de leitura</Text></View>
      <Icon name="chevron" color={colors.primary} size={18} />
    </Pressable>)}
  </View>;
}

function ArticleFeedback({ rating, status, onChoose }: { rating: number | null; status: string; onChoose: (rating: number) => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={s.feedbackCard}>
    <Text accessibilityRole="header" style={s.feedbackTitle}>O que você achou desta notícia?</Text>
    <Text style={s.feedbackSub}>Sua opinião nos ajuda a trazer conteúdos cada vez melhores.</Text>
    <View style={s.feedbackChoices}>{feedbackOptionsFor(colors).map(option => <Pressable key={option.rating} accessibilityRole="button" accessibilityLabel={option.label} accessibilityState={{ selected: rating === option.rating }} onPress={() => onChoose(option.rating)} style={[s.feedbackChoice, rating === option.rating && s.feedbackSelected]}>
      <View style={[s.face, { backgroundColor: option.tint }, rating === option.rating && { borderColor: colors.primary }]}><Icon name={option.icon} color={option.color} size={24} /></View><Text style={[s.feedbackLabel, rating === option.rating && { color: colors.primary, fontWeight: '700' }]}>{option.label}</Text>
    </Pressable>)}</View>
    {!!status && <Text accessibilityLiveRegion="polite" style={s.feedbackStatus}>{status}</Text>}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.readerBackground }, scroll: { flex: 1 }, content: { paddingBottom: 12 },
  header: { minHeight: 62, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.background },
  headerButton: { width: 38, height: 44, alignItems: 'center', justifyContent: 'center' }, back: { color: colors.tone('#203A69', colors.body), fontSize: 35, lineHeight: 38, marginTop: -4 },
  logo: { position: 'absolute', width: 105, height: 36, left: '50%', marginLeft: -52, top: 13 }, headerActions: { marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 1 }, actionGlyph: { color: colors.tone('#1D3767', colors.body), fontSize: 27, fontWeight: '700' }, dots: { color: colors.tone('#1D3767', colors.body), fontSize: 15, letterSpacing: 2 },
  hero: { width: '100%', height: 250, backgroundColor: colors.border }, article: { marginTop: -22, borderTopLeftRadius: 24, borderTopRightRadius: 24, backgroundColor: colors.surface, paddingHorizontal: 20, paddingTop: 19, paddingBottom: 22 },
  metaRow: { minHeight: 32, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }, category: { overflow: 'hidden', maxWidth: '64%', borderRadius: 18, backgroundColor: colors.tone('#E6F0FF', colors.surfaceBlue), color: colors.tone('#1268E8', colors.primary), paddingHorizontal: 13, paddingVertical: 7, fontSize: 11, fontWeight: '800', letterSpacing: .3 }, readMeta: { flexDirection: 'row', alignItems: 'center', gap: 5 }, readTime: { color: colors.tone('#596F93', colors.secondary), fontSize: 12 },
  headline: { color: colors.ink, fontSize: 30, lineHeight: 37, fontWeight: '800', letterSpacing: -.7, marginTop: 14 }, deck: { color: colors.tone('#52698F', colors.secondary), fontSize: 17, lineHeight: 25, marginTop: 9 },
  authorRow: { flexDirection: 'row', alignItems: 'center', gap: 11, marginTop: 18, marginBottom: 18 }, sourceAvatar: { width: 46, height: 46, borderRadius: 24, backgroundColor: colors.surfaceTint, alignItems: 'center', justifyContent: 'center' }, sourceGlyph: { color: colors.tone('#1976F8', colors.primary), fontWeight: '800', fontSize: 19 }, sourceName: { color: colors.tone('#101F42', colors.ink), fontSize: 14, fontWeight: '700' }, date: { color: colors.tone('#60769A', colors.secondary), fontSize: 12, marginTop: 3 },
  audioCard: { minHeight: 72, borderRadius: 18, borderWidth: 1, borderColor: colors.divider, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 12, marginBottom: 18 }, audioIcon: { width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tone('#E7F1FF', colors.surfaceBlue) }, audioGlyph: { color: colors.tone('#1873F8', colors.primary), fontSize: 25 }, audioTitle: { color: colors.tone('#102047', colors.ink), fontSize: 15, fontWeight: '700' }, audioSub: { color: colors.tabIdle, fontSize: 12, marginTop: 3 }, audioUnavailable: { width: 42, height: 42, borderRadius: 22, backgroundColor: colors.divider, alignItems: 'center', justifyContent: 'center' }, disabledPlay: { color: colors.tone('#8192AC', colors.muted), fontSize: 15 },
  body: { color: colors.body, fontSize: 16, lineHeight: 25, marginBottom: 15 }, keyCard: { borderRadius: 20, borderWidth: 1, borderColor: colors.tone('#E2EDF9', colors.border), backgroundColor: colors.surfaceSoft, padding: 17, marginTop: 4, marginBottom: 18 }, keyTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 }, keyTitle: { color: colors.ink, fontSize: 18, fontWeight: '800', marginBottom: 14 }, keyRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 9, marginTop: 8 }, check: { width: 20, height: 20, overflow: 'hidden', textAlign: 'center', textAlignVertical: 'center', borderRadius: 11, backgroundColor: colors.tone('#1675F8', colors.primary), color: colors.onPrimary, fontWeight: '800', fontSize: 13 }, keyText: { flex: 1, color: colors.tone('#50678D', colors.secondary), fontSize: 14, lineHeight: 20 },
  relatedSection: { borderTopWidth: 1, borderColor: colors.divider, paddingTop: 17, marginTop: 12, marginBottom: 18 }, relatedHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }, relatedTitle: { color: colors.ink, fontSize: 21, fontWeight: '800' }, moreButton: { paddingVertical: 7, paddingHorizontal: 2 }, moreText: { color: colors.tone('#0868F4', colors.primary), fontSize: 13, fontWeight: '700' }, relatedRow: { minHeight: 94, flexDirection: 'row', alignItems: 'center', gap: 11, borderBottomWidth: 1, borderColor: colors.divider, paddingVertical: 9 }, relatedImage: { width: 94, height: 76, borderRadius: 11, backgroundColor: colors.surfaceTint }, relatedCopy: { flex: 1 }, relatedCategory: { color: colors.tone('#126AE7', colors.primary), backgroundColor: colors.tone('#EAF2FF', colors.surfaceBlue), alignSelf: 'flex-start', borderRadius: 9, overflow: 'hidden', paddingHorizontal: 7, paddingVertical: 3, fontSize: 9, fontWeight: '800', marginBottom: 4 }, relatedHeadline: { color: colors.tone('#102047', colors.ink), fontSize: 13, lineHeight: 17, fontWeight: '700' }, relatedTime: { color: colors.tone('#657B9E', colors.secondary), fontSize: 11, marginTop: 4 }, chevron: { color: colors.tone('#0868F4', colors.primary), fontSize: 26, paddingHorizontal: 3 },
  briefingCard: { minHeight: 80, borderRadius: 20, backgroundColor: colors.surfaceBlue, borderWidth: 1, borderColor: colors.tone('#E0EDFC', colors.surfaceBlue), flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 14, paddingVertical: 12, marginTop: 2, marginBottom: 18 }, briefingTitle: { color: colors.tone('#102047', colors.ink), fontSize: 14, lineHeight: 19, fontWeight: '800' }, briefingSub: { color: colors.tone('#62799C', colors.secondary), fontSize: 12, lineHeight: 17, marginTop: 3 },
  feedbackCard: { borderRadius: 20, borderWidth: 1, borderColor: colors.divider, backgroundColor: colors.surface, padding: 16, marginTop: 2 }, feedbackTitle: { color: colors.tone('#0B1D42', colors.ink), fontSize: 18, lineHeight: 24, fontWeight: '800' }, feedbackSub: { color: colors.tone('#60769A', colors.secondary), fontSize: 13, lineHeight: 19, marginTop: 4 }, feedbackChoices: { flexDirection: 'row', justifyContent: 'space-between', gap: 2, marginTop: 14 }, feedbackChoice: { flex: 1, alignItems: 'center', paddingVertical: 3, borderRadius: 14 }, feedbackSelected: { backgroundColor: colors.surfaceSoft }, face: { width: 44, height: 44, borderRadius: 23, borderWidth: 1, borderColor: 'transparent', alignItems: 'center', justifyContent: 'center' }, feedbackLabel: { color: colors.tone('#62799D', colors.secondary), fontSize: 10, marginTop: 6 }, feedbackStatus: { minHeight: 17, color: colors.tone('#60769A', colors.secondary), fontSize: 11, marginTop: 9 }, resourceNotice: { marginHorizontal: 14, marginTop: 8, marginBottom: 10, padding: 11, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderRadius: 12, backgroundColor: colors.warningSurface }, resourceNoticeText: { flex: 1, color: colors.tone('#66552F', colors.warning), fontSize: 12 }, resourceRetry: { color: colors.primary, fontSize: 12, fontWeight: '700' }, error: { color: colors.tone('#BB343F', colors.danger), fontSize: 12, marginBottom: 10 },
});
