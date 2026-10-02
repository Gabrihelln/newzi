import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Image, Linking, Pressable, SafeAreaView, ScrollView, Share, StatusBar, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { devLog } from '../config/env';
import { Icon } from './Icon';
import { ArticleImage } from './ArticleImage';
import { colors } from '../theme';
import type { Briefing, BriefingItem, Topic } from '../types/api';

const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const feedbackOptions = [
  { rating: 5, label: 'Ótima', icon: 'ratingGreat' as const, color: '#1674E8', tint: '#EAF4FF' },
  { rating: 4, label: 'Boa', icon: 'ratingGood' as const, color: '#E99113', tint: '#FFF5E8' },
  { rating: 3, label: 'Neutra', icon: 'ratingNeutral' as const, color: '#59739D', tint: '#EDF5FF' },
  { rating: 2, label: 'Ruim', icon: 'ratingBad' as const, color: '#DF6470', tint: '#FFF0F1' },
  { rating: 1, label: 'Péssima', icon: 'ratingPoor' as const, color: '#D73A4A', tint: '#FFE8E9' },
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
    <StatusBar barStyle="dark-content" backgroundColor="#F5FAFF" />
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
            <Text style={s.sourceName}>{source?.publisher || source?.name ? `Fonte: ${source.publisher || source.name}` : 'Fonte não informada'}</Text>
            <Text style={s.date}>{publishedAt || 'Data de publicação indisponível'}</Text>
          </View>
        </View>
        {!!item.why_it_matters?.trim() && item.why_it_matters.trim() !== item.summary.trim() && <Text style={s.body}>{item.why_it_matters}</Text>}
        {!!(item.key_points || []).length && <View style={s.keyCard}>
          <View style={s.keyTitleRow}><Icon name="article" color={colors.primary} size={20} /><Text accessibilityRole="header" style={s.keyTitle}>Principais pontos</Text></View>
          {(item.key_points || []).map((point, index) => <View key={`${index}-${point}`} style={s.keyRow}><Icon name="checkCircle" color={colors.primary} size={18} /><Text style={s.keyText}>{point}</Text></View>)}
        </View>}
        {!!sourceError && <Text accessibilityRole="alert" style={s.error}>{sourceError}</Text>}
        {related.length > 0 && <RelatedStories items={related} onMore={() => onTopic(topic)} onOpen={onRelated} />}
        {relatedError && <View accessibilityRole="alert" style={s.resourceNotice}><Text style={s.resourceNoticeText}>Não foi possível carregar notícias relacionadas.</Text><Pressable accessibilityRole="button" onPress={() => setResourceRetryKey(value => value + 1)}><Text style={s.resourceRetry}>Tentar novamente</Text></Pressable></View>}
        {!!briefing && <Pressable accessibilityRole="button" accessibilityLabel={currentInBriefing ? 'Ouça este tema no briefing de hoje. Esta notícia faz parte do seu resumo diário.' : 'Ouça o briefing de hoje'} onPress={() => onBriefing(briefing)} style={s.briefingCard}>
          <Icon name="sun" color="#E99113" size={25} /><View style={{ flex: 1 }}><Text style={s.briefingTitle}>{currentInBriefing ? 'Ouça este tema no briefing de hoje' : 'Ouça o briefing de hoje'}</Text><Text style={s.briefingSub}>{currentInBriefing ? 'Esta notícia faz parte do seu resumo diário' : 'Acesse seu resumo diário personalizado'}</Text></View><Icon name="chevron" color={colors.primary} size={18} />
        </Pressable>}
        <ArticleFeedback rating={rating} status={feedbackStatus} onChoose={sendFeedback} />
      </View>
      <View style={{ height: 34 }} />
    </ScrollView>
  </SafeAreaView>;
}

export function ArticleLoadState({ onBack, onRetry, loading, error }: { onBack: () => void; onRetry: () => void; loading: boolean; error: string }) {
  return <SafeAreaView style={s.safe}>
    <StatusBar barStyle="dark-content" backgroundColor="#F5FAFF" />
    <ScrollView style={s.scroll} contentContainerStyle={s.content}>
      <ReaderHeader onBack={onBack} saved={false} saving savedReady={false} onBookmark={() => undefined} onShare={() => undefined} onMore={() => undefined} />
      <View style={[s.hero, { backgroundColor: '#E6F0FA' }]} />
      <View style={s.article}>
        {loading ? <><View style={{ height: 28, width: '42%', borderRadius: 15, backgroundColor: '#E6F0FA', marginBottom: 20 }} /><View style={{ height: 38, borderRadius: 8, backgroundColor: '#E6F0FA', marginBottom: 8 }} /><View style={{ height: 38, width: '76%', borderRadius: 8, backgroundColor: '#E6F0FA', marginBottom: 18 }} /><View style={{ height: 94, borderRadius: 16, backgroundColor: '#E6F0FA', marginBottom: 18 }} /><View style={{ height: 20, borderRadius: 8, backgroundColor: '#E6F0FA', marginBottom: 9 }} /><View style={{ height: 20, width: '82%', borderRadius: 8, backgroundColor: '#E6F0FA' }} /></> : <>
          <Text accessibilityRole="header" style={s.headline}>Não foi possível carregar esta notícia.</Text>
          <Text style={s.deck}>{error || 'Verifique sua conexão e tente novamente.'}</Text>
          <Pressable accessibilityRole="button" onPress={onRetry} style={{ marginTop: 18, alignSelf: 'flex-start', borderRadius: 24, backgroundColor: colors.primary, paddingHorizontal: 22, paddingVertical: 13 }}><Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 14 }}>Tentar novamente</Text></Pressable>
        </>}
      </View>
    </ScrollView>
  </SafeAreaView>;
}

function ReaderHeader({ onBack, saved, saving, savedReady, onBookmark, onShare, onMore }: { onBack: () => void; saved: boolean; saving: boolean; savedReady: boolean; onBookmark: () => void; onShare: () => void; onMore: () => void }) {
  return <View style={s.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={s.headerButton}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.textPrimary} size={21} /></View></Pressable>
    <Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={s.logo} />
    <View style={s.headerActions}>
      <Pressable accessibilityRole="button" accessibilityLabel={saved ? 'Remover notícia dos salvos' : 'Salvar notícia'} accessibilityState={{ selected: saved, disabled: saving || !savedReady }} disabled={saving || !savedReady} onPress={onBookmark} style={s.headerButton}><Icon name="bookmark" color={saved ? colors.primary : '#1D3767'} size={22} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Compartilhar notícia" onPress={onShare} style={s.headerButton}><Icon name="share" color="#1D3767" size={20} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Mais opções da notícia" onPress={onMore} style={s.headerButton}><Icon name="more" color="#1D3767" size={22} /></Pressable>
    </View>
  </View>;
}

function RelatedStories({ items, onMore, onOpen }: { items: BriefingItem[]; onMore: () => void; onOpen: (item: BriefingItem) => void }) {
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
  return <View style={s.feedbackCard}>
    <Text accessibilityRole="header" style={s.feedbackTitle}>O que você achou desta notícia?</Text>
    <Text style={s.feedbackSub}>Sua opinião nos ajuda a trazer conteúdos cada vez melhores.</Text>
    <View style={s.feedbackChoices}>{feedbackOptions.map(option => <Pressable key={option.rating} accessibilityRole="button" accessibilityLabel={option.label} accessibilityState={{ selected: rating === option.rating }} onPress={() => onChoose(option.rating)} style={[s.feedbackChoice, rating === option.rating && s.feedbackSelected]}>
      <View style={[s.face, { backgroundColor: option.tint }, rating === option.rating && { borderColor: colors.primary }]}><Icon name={option.icon} color={option.color} size={24} /></View><Text style={[s.feedbackLabel, rating === option.rating && { color: colors.primary, fontWeight: '700' }]}>{option.label}</Text>
    </Pressable>)}</View>
    {!!status && <Text accessibilityLiveRegion="polite" style={s.feedbackStatus}>{status}</Text>}
  </View>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F5FAFF' }, scroll: { flex: 1 }, content: { paddingBottom: 12 },
  header: { minHeight: 62, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#F8FBFF' },
  headerButton: { width: 38, height: 44, alignItems: 'center', justifyContent: 'center' }, back: { color: '#203A69', fontSize: 35, lineHeight: 38, marginTop: -4 },
  logo: { position: 'absolute', width: 105, height: 36, left: '50%', marginLeft: -52, top: 13 }, headerActions: { marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 1 }, actionGlyph: { color: '#1D3767', fontSize: 27, fontWeight: '700' }, dots: { color: '#1D3767', fontSize: 15, letterSpacing: 2 },
  hero: { width: '100%', height: 250, backgroundColor: '#DFECF9' }, article: { marginTop: -22, borderTopLeftRadius: 24, borderTopRightRadius: 24, backgroundColor: '#FBFDFF', paddingHorizontal: 20, paddingTop: 19, paddingBottom: 22 },
  metaRow: { minHeight: 32, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }, category: { overflow: 'hidden', maxWidth: '64%', borderRadius: 18, backgroundColor: '#E6F0FF', color: '#1268E8', paddingHorizontal: 13, paddingVertical: 7, fontSize: 11, fontWeight: '800', letterSpacing: .3 }, readMeta: { flexDirection: 'row', alignItems: 'center', gap: 5 }, readTime: { color: '#596F93', fontSize: 12 },
  headline: { color: '#091940', fontSize: 30, lineHeight: 37, fontWeight: '800', letterSpacing: -.7, marginTop: 14 }, deck: { color: '#52698F', fontSize: 17, lineHeight: 25, marginTop: 9 },
  authorRow: { flexDirection: 'row', alignItems: 'center', gap: 11, marginTop: 18, marginBottom: 18 }, sourceAvatar: { width: 46, height: 46, borderRadius: 24, backgroundColor: '#E7F1FC', alignItems: 'center', justifyContent: 'center' }, sourceGlyph: { color: '#1976F8', fontWeight: '800', fontSize: 19 }, sourceName: { color: '#101F42', fontSize: 14, fontWeight: '700' }, date: { color: '#60769A', fontSize: 12, marginTop: 3 },
  audioCard: { minHeight: 72, borderRadius: 18, borderWidth: 1, borderColor: '#E3EDF8', backgroundColor: '#F9FCFF', flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 12, marginBottom: 18 }, audioIcon: { width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#E7F1FF' }, audioGlyph: { color: '#1873F8', fontSize: 25 }, audioTitle: { color: '#102047', fontSize: 15, fontWeight: '700' }, audioSub: { color: '#7385A2', fontSize: 12, marginTop: 3 }, audioUnavailable: { width: 42, height: 42, borderRadius: 22, backgroundColor: '#E2EAF5', alignItems: 'center', justifyContent: 'center' }, disabledPlay: { color: '#8192AC', fontSize: 15 },
  body: { color: '#354B70', fontSize: 16, lineHeight: 25, marginBottom: 15 }, keyCard: { borderRadius: 20, borderWidth: 1, borderColor: '#E2EDF9', backgroundColor: '#F6FAFF', padding: 17, marginTop: 4, marginBottom: 18 }, keyTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 }, keyTitle: { color: '#0A1C43', fontSize: 18, fontWeight: '800', marginBottom: 14 }, keyRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 9, marginTop: 8 }, check: { width: 20, height: 20, overflow: 'hidden', textAlign: 'center', textAlignVertical: 'center', borderRadius: 11, backgroundColor: '#1675F8', color: '#FFFFFF', fontWeight: '800', fontSize: 13 }, keyText: { flex: 1, color: '#50678D', fontSize: 14, lineHeight: 20 },
  relatedSection: { borderTopWidth: 1, borderColor: '#E3ECF7', paddingTop: 17, marginTop: 12, marginBottom: 18 }, relatedHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }, relatedTitle: { color: '#0B1B40', fontSize: 21, fontWeight: '800' }, moreButton: { paddingVertical: 7, paddingHorizontal: 2 }, moreText: { color: '#0868F4', fontSize: 13, fontWeight: '700' }, relatedRow: { minHeight: 94, flexDirection: 'row', alignItems: 'center', gap: 11, borderBottomWidth: 1, borderColor: '#E7EEF7', paddingVertical: 9 }, relatedImage: { width: 94, height: 76, borderRadius: 11, backgroundColor: '#E8F2FD' }, relatedCopy: { flex: 1 }, relatedCategory: { color: '#126AE7', backgroundColor: '#EAF2FF', alignSelf: 'flex-start', borderRadius: 9, overflow: 'hidden', paddingHorizontal: 7, paddingVertical: 3, fontSize: 9, fontWeight: '800', marginBottom: 4 }, relatedHeadline: { color: '#102047', fontSize: 13, lineHeight: 17, fontWeight: '700' }, relatedTime: { color: '#657B9E', fontSize: 11, marginTop: 4 }, chevron: { color: '#0868F4', fontSize: 26, paddingHorizontal: 3 },
  briefingCard: { minHeight: 80, borderRadius: 20, backgroundColor: '#EAF4FF', borderWidth: 1, borderColor: '#E0EDFC', flexDirection: 'row', alignItems: 'center', gap: 11, paddingHorizontal: 14, paddingVertical: 12, marginTop: 2, marginBottom: 18 }, briefingTitle: { color: '#102047', fontSize: 14, lineHeight: 19, fontWeight: '800' }, briefingSub: { color: '#62799C', fontSize: 12, lineHeight: 17, marginTop: 3 },
  feedbackCard: { borderRadius: 20, borderWidth: 1, borderColor: '#E7EFF8', backgroundColor: '#FFFFFF', padding: 16, marginTop: 2 }, feedbackTitle: { color: '#0B1D42', fontSize: 18, lineHeight: 24, fontWeight: '800' }, feedbackSub: { color: '#60769A', fontSize: 13, lineHeight: 19, marginTop: 4 }, feedbackChoices: { flexDirection: 'row', justifyContent: 'space-between', gap: 2, marginTop: 14 }, feedbackChoice: { flex: 1, alignItems: 'center', paddingVertical: 3, borderRadius: 14 }, feedbackSelected: { backgroundColor: '#F2F8FF' }, face: { width: 44, height: 44, borderRadius: 23, borderWidth: 1, borderColor: 'transparent', alignItems: 'center', justifyContent: 'center' }, feedbackLabel: { color: '#62799D', fontSize: 10, marginTop: 6 }, feedbackStatus: { minHeight: 17, color: '#60769A', fontSize: 11, marginTop: 9 }, resourceNotice: { marginHorizontal: 14, marginTop: 8, marginBottom: 10, padding: 11, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderRadius: 12, backgroundColor: '#FFF7E8' }, resourceNoticeText: { flex: 1, color: '#66552F', fontSize: 12 }, resourceRetry: { color: colors.primary, fontSize: 12, fontWeight: '700' }, error: { color: '#BB343F', fontSize: 12, marginBottom: 10 },
});
