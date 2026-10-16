import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Image, Keyboard, KeyboardAvoidingView, NativeModules,
  Platform, Pressable, ScrollView, StatusBar, StyleSheet, Text, TextInput,
  useWindowDimensions, View,
} from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import Video from 'react-native-video';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { api, ClientError, CONNECTION_ERROR_MESSAGE } from '../api/client';
import { pauseAudio } from '../audio/player';
import { getDeviceTimezone } from '../config/timezone';
import { requestAndRegisterDevice } from '../push/push';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import type { AudioVoice, AudioVoiceCatalog, ClientConfig, NextBriefing, Preferences, Topic, User } from '../types/api';
import { BrandStack, Glows, Lockup } from './BrandStack';
import { useBrandMarks } from './brand';
import { Icon } from './Icon';
import { TimeWheel } from './TimeWheel';
import { TopicIcon, topicIconFor } from './TopicIcon';
import type { IconName } from './Icon';

const STEPS = 8;
const DONE = STEPS + 1;
const initialPreferences: Preferences = {
  topics: [], language: 'pt-BR', country_scope: 'GLOBAL', briefing_time: '06:30',
  timezone: getDeviceTimezone(), briefing_size: 10, audio_enabled: false,
};
const timePattern = /^([01]\d|2[0-3]):[0-5]\d$/;
const scopeLabel: Record<Preferences['country_scope'], string> = { LOCAL: 'Brasil', GLOBAL: 'Global', BOTH: 'Brasil e Global' };
const scopeDetail: Record<Preferences['country_scope'], string> = { LOCAL: 'Notícias do país', GLOBAL: 'O que acontece no mundo', BOTH: 'O melhor dos dois' };
const scopeIcon: Record<Preferences['country_scope'], IconName> = { LOCAL: 'flag', GLOBAL: 'globe', BOTH: 'layers' };
const scopeOrder: Preferences['country_scope'][] = ['LOCAL', 'GLOBAL', 'BOTH'];
const features: { icon: IconName; title: string; text: string }[] = [
  { icon: 'article', title: 'Resumo personalizado', text: 'As notícias que importam para você, em poucos minutos.' },
  { icon: 'headphones', title: 'Ouça quando quiser', text: 'Escolha a voz e escute seu resumo enquanto faz outras coisas.' },
  { icon: 'clock', title: 'No seu horário', text: 'Tudo pronto na hora que você escolher.' },
];
const sizes: { size: Preferences['briefing_size']; label: string; minutes: number; icon: IconName; bars: number }[] = [
  { size: 5, label: 'Rápido', minutes: 3, icon: 'audio', bars: 2 },
  { size: 10, label: 'Essencial', minutes: 5, icon: 'clock', bars: 4 },
  { size: 15, label: 'Completo', minutes: 8, icon: 'article', bars: 5 },
];
const sizeLabel = (size: number) => sizes.find(item => item.size === size)?.label || `${size} notícias`;
const sizeMinutes = (size: number) => sizes.find(item => item.size === size)?.minutes || 5;
const presets = [{ time: '06:30', label: 'Ao acordar' }, { time: '08:00', label: 'No trajeto' }, { time: '12:00', label: 'No almoço' }, { time: '19:00', label: 'À noite' }];
const languageName = (language: string) => language === 'pt-BR' ? 'Português' : language === 'en' ? 'English' : language;
// Avatar fills: white initials keep at least 4.5:1 on both ends of each gradient.
const avatarColors = [['#2D6BE0', '#1A56C4'], ['#0F8270', '#0B6B5C'], ['#7A4EE0', '#6236C9'], ['#B85E12', '#9C4D0C'], ['#B83A70', '#9C2E5E']];
const voiceDetail = (voice: AudioVoice) => `${voice.gender === 'male' ? 'Masculina' : 'Feminina'} · ${/multil[ií]ngue/i.test(voice.description) ? 'Multilíngue' : voice.language === 'pt-BR' ? 'Português (Brasil)' : 'Inglês'}`;
const voiceWithArticle = (voice: AudioVoice) => `${voice.gender === 'male' ? 'do' : 'da'} ${voice.name}`;
// The backend's sample sentence (PREVIEW_TEXT in audio.py), for servers that do not send `preview_text` yet.
const previewText: Record<string, string> = {
  'pt-BR': 'Bom dia. Este é o seu resumo Newzi, com as histórias mais importantes selecionadas para você acompanhar o dia com clareza.',
  en: 'Good morning. This is your Newzi briefing, with the most important stories selected to help you follow the day clearly.',
};
const fold = (value: string) => value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;
const errorMessage = (error: unknown) => {
  if (error instanceof ClientError) {
    if (error.code === 'BACKEND_UNREACHABLE' || error.code === 'OFFLINE') return CONNECTION_ERROR_MESSAGE;
    if (error.code === 'TIMEOUT') return 'A conexão demorou demais. Tente novamente.';
    if (error.code === 'VALIDATION_ERROR') return 'Confira suas escolhas e tente novamente.';
    return error.message;
  }
  return 'Não foi possível concluir. Tente novamente.';
};

function Action({ label, onPress, ghost = false, disabled = false }: { label: string; onPress: () => void; ghost?: boolean; disabled?: boolean }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [s.action, ghost ? s.actionGhost : s.actionPrimary, (pressed || disabled) && { opacity: .7 }]}>
    <Text style={ghost ? s.actionGhostText : s.actionText}>{label}</Text>
    {!ghost && <View style={s.actionArrow}><Icon name="chevron" color={colors.onPrimary} size={20} /></View>}
  </Pressable>;
}

function Progress({ step }: { step: number }) {
  const s = useStyles(makeStyles);
  return <>
    <View accessible accessibilityLabel={`Etapa ${step} de ${STEPS}`} style={s.progress}>
      {Array.from({ length: STEPS }, (_, index) => <View key={index} style={[s.progressMark, index < step && s.progressActive]} />)}
    </View>
    <Text importantForAccessibility="no" style={s.stepCount}>{step} de {STEPS}</Text>
  </>;
}

function Radio({ on }: { on: boolean }) {
  const s = useStyles(makeStyles);
  return <View style={[s.radio, on && s.radioOn]} />;
}

function Tag({ label }: { label: string }) {
  const s = useStyles(makeStyles);
  return <Text style={s.tag}>{label}</Text>;
}

function Bars({ count }: { count: number }) {
  const s = useStyles(makeStyles);
  return <View style={s.bars}>{[8, 12, 16, 20, 22].map((height, index) => <View key={height} style={[s.bar, { height }, index < count && s.barOn]} />)}</View>;
}

/** A single choice shown as a card: icon tile, title (with an optional tag), detail, extra and a radio circle. */
function ChoiceCard({ label, detail, icon, selected, onPress, tag, right }: {
  label: string; detail: string; icon: IconName; selected: boolean; onPress: () => void; tag?: string; right?: React.ReactNode;
}) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <Pressable accessibilityRole="radio" accessibilityState={{ selected }} accessibilityLabel={`${label}${tag ? `, ${tag.toLowerCase()}` : ''}, ${detail}`} onPress={onPress}
    style={({ pressed }) => [s.card, selected && s.cardSelected, pressed && { opacity: .8 }]}>
    <View style={[s.tile, selected && s.tileSelected]}><Icon name={icon} color={selected ? colors.tone('#1872F7', colors.primary) : colors.tone('#507AB8', colors.secondary)} size={21} /></View>
    <View style={s.cardCopy}><View style={s.cardTitleRow}><Text style={s.cardTitle}>{label}</Text>{!!tag && <Tag label={tag} />}</View><Text style={s.cardDetail}>{detail}</Text></View>
    {right}<Radio on={selected} />
  </Pressable>;
}

function Segmented<T extends string>({ options, value, onChange, small = false }: { options: { value: T; label: string }[]; value: T; onChange: (value: T) => void; small?: boolean }) {
  const s = useStyles(makeStyles);
  return <View accessibilityRole="radiogroup" style={s.segment}>{options.map(option => {
    const on = option.value === value;
    return <Pressable key={option.value} accessibilityRole="radio" accessibilityState={{ selected: on }} accessibilityLabel={option.label} onPress={() => onChange(option.value)}
      style={[s.segmentItem, small && s.segmentItemSmall, on && s.segmentItemOn]}><Text style={[s.segmentText, small && s.segmentTextSmall, on && s.segmentTextOn]}>{option.label}</Text></Pressable>;
  })}</View>;
}

function TopicChip({ topic, selected, onPress }: { topic: Topic; selected: boolean; onPress: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: selected }} accessibilityLabel={topic.name} onPress={onPress}
    style={({ pressed }) => [s.chip, selected && s.chipSelected, pressed && { opacity: .8 }]}>
    {selected ? <Icon name="check" color={colors.tone('#FFFFFF', colors.onPrimary)} size={15} /> : <TopicIcon name={topicIconFor(topic)} color={colors.tone('#507AB8', colors.secondary)} size={15} />}
    <Text style={[s.chipText, selected && s.chipTextSelected]}>{topic.name}</Text>
  </Pressable>;
}

/** The topic name with the searched part in bold blue. */
function Highlight({ text, query }: { text: string; query: string }) {
  const s = useStyles(makeStyles);
  const chars = Array.from(text);
  const folded = chars.map(fold);
  const needle = fold(query.trim());
  // Accent folding keeps one letter per letter for Portuguese names; anything else is shown plain.
  const start = needle && folded.every(char => char.length === 1) ? folded.join('').indexOf(needle) : -1;
  if (start < 0) return <Text style={s.resultText}>{text}</Text>;
  const end = start + needle.length;
  return <Text style={s.resultText}>{chars.slice(0, start).join('')}<Text style={s.resultMark}>{chars.slice(start, end).join('')}</Text>{chars.slice(end).join('')}</Text>;
}

function Avatar({ voice, index }: { voice: AudioVoice; index: number }) {
  const s = useStyles(makeStyles);
  const [from, to] = avatarColors[index % avatarColors.length];
  return <View style={s.avatar}>
    <Svg width={42} height={42} style={StyleSheet.absoluteFill}><Defs><LinearGradient id={`avatar-${voice.id}`} x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor={from} /><Stop offset="1" stopColor={to} /></LinearGradient></Defs>
      <Rect width={42} height={42} rx={21} fill={`url(#avatar-${voice.id})`} /></Svg>
    <Text style={s.avatarText}>{voice.name.slice(0, 1).toUpperCase()}</Text>
  </View>;
}

function Wave({ progress }: { progress: number }) {
  const s = useStyles(makeStyles);
  const total = 34, played = Math.round(progress * total);
  return <View style={s.wave}>{Array.from({ length: total }, (_, index) => {
    const height = Math.min(26, 6 + Math.round(Math.abs(Math.sin(index * 1.7 + 3) * 14 + Math.sin(index * .6) * 6)));
    return <View key={index} style={[s.waveBar, { height }, index >= played && s.waveBarOff]} />;
  })}</View>;
}

/** Step 6: the voices with a playable sample. The sample stops when another voice is chosen or the step closes. */
function VoiceStep({ catalog, language, loading, failed, selected, onSelect, onRetry }: {
  catalog: AudioVoiceCatalog | null; language: string; loading: boolean; failed: boolean; selected?: string | null; onSelect: (id: string) => void; onRetry: () => void;
}) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [filter, setFilter] = useState<'all' | 'female' | 'male'>('all');
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [previewSource, setPreviewSource] = useState<{ id: string; uri: string } | null>(null);
  const [position, setPosition] = useState({ current: 0, duration: 0 });
  const [message, setMessage] = useState('');
  const previewRun = useRef(0);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; previewRun.current++; }, []);

  const stopPreview = () => {
    previewRun.current++;
    if (mounted.current) { setPreviewSource(null); setPreviewing(null); setPreviewLoading(null); setPosition({ current: 0, duration: 0 }); }
  };
  // Same download-then-play path as VoiceSettingsScreen: the sample needs the session token.
  const playPreview = async (voice: AudioVoice) => {
    if (previewing === voice.id) { stopPreview(); return; }
    stopPreview();
    const run = previewRun.current;
    setPreviewLoading(voice.id); setMessage(''); pauseAudio();
    try {
      const token = await getFirebaseIdToken();
      if (!token) throw new Error('authentication required');
      const cache = NativeModules.NewziAudioCache as { download?: (source: string, auth: string) => Promise<string> } | undefined;
      if (!cache?.download) throw new Error('audio cache unavailable');
      const path = await cache.download(voice.preview_url, token);
      if (previewRun.current !== run || !mounted.current) return;
      setPreviewSource({ id: voice.id, uri: path.startsWith('file://') ? path : `file://${path}` });
      setPreviewing(voice.id);
    } catch {
      if (mounted.current && previewRun.current === run) setMessage('Não foi possível reproduzir o exemplo agora.');
    } finally {
      if (mounted.current && previewRun.current === run) setPreviewLoading(null);
    }
  };
  const choose = (id: string) => { if (previewing && previewing !== id) stopPreview(); onSelect(id); };
  const voices = (catalog?.voices || []).filter(voice => filter === 'all' || voice.gender === filter);

  return <>
    <View style={s.voiceFilter}><Segmented small value={filter} onChange={value => setFilter(value)} options={[{ value: 'all', label: 'Todas' }, { value: 'female', label: 'Femininas' }, { value: 'male', label: 'Masculinas' }]} /></View>
    {loading && <ActivityIndicator color={colors.primary} style={s.voiceLoading} />}
    {!loading && failed && <View style={s.notice}><Icon name="mic" color={colors.tone('#087CF0', colors.primary)} size={22} />
      <Text style={s.noticeText}>Não foi possível carregar as vozes agora. Você pode seguir e escolher depois em Perfil › Voz do resumo.</Text>
      <Pressable accessibilityRole="button" onPress={onRetry} hitSlop={8}><Text style={s.noticeAction}>Tentar de novo</Text></Pressable></View>}
    <View style={s.voiceList}>{voices.map(voice => {
      const index = catalog!.voices.indexOf(voice), active = selected === voice.id, playing = previewing === voice.id;
      return <Pressable key={voice.id} accessibilityRole="radio" accessibilityState={{ selected: active }} accessibilityLabel={`${voice.name}, ${voiceDetail(voice)}`} onPress={() => choose(voice.id)}
        style={[s.voiceCard, active && s.cardSelected]}>
        <View style={s.voiceTop}>
          <Avatar voice={voice} index={index} />
          <View style={s.cardCopy}><Text style={s.cardTitle}>{voice.name}</Text><Text style={s.voiceDetail}>{voiceDetail(voice)}</Text></View>
          <Pressable accessibilityRole="button" accessibilityLabel={`${playing ? 'Parar' : 'Ouvir'} exemplo da voz ${voice.name}`} disabled={previewLoading === voice.id} onPress={() => void playPreview(voice)} hitSlop={6}
            style={[s.play, playing && s.playOn]}>
            {previewLoading === voice.id ? <ActivityIndicator size="small" color={colors.primary} /> : <Icon name={playing ? 'pause' : 'play'} color={playing ? colors.tone('#FFFFFF', colors.onPrimary) : colors.tone('#2778F5', colors.primary)} size={17} />}
          </Pressable>
          <View style={s.voiceRadio}><Radio on={active} /></View>
        </View>
        {playing && <View style={s.player}>
          <Text style={s.quote}>“{catalog?.preview_text || previewText[language] || previewText['pt-BR']}”</Text>
          <View style={s.playerRow}><Text style={s.playerTime}>{clock(position.current)}</Text><Wave progress={position.duration ? position.current / position.duration : 0} /><Text style={s.playerTime}>{clock(position.duration)}</Text></View>
        </View>}
      </Pressable>;
    })}</View>
    {!!message && <Text accessibilityRole="alert" style={s.error}>{message}</Text>}
    {previewSource && <Video key={previewSource.id} source={{ uri: previewSource.uri }} paused={false} disableFocus={false} progressUpdateInterval={250}
      onLoad={event => { if (mounted.current) setPosition({ current: 0, duration: event.duration }); }}
      onProgress={event => { if (mounted.current) setPosition(current => ({ current: event.currentTime, duration: current.duration || event.seekableDuration })); }}
      onEnd={() => { if (mounted.current) { setPreviewSource(null); setPreviewing(null); } }}
      onError={() => { if (mounted.current) { setPreviewSource(null); setPreviewing(null); setMessage('Não foi possível reproduzir o exemplo agora.'); } }}
      style={s.hiddenVideo} />}
  </>;
}

function SummaryRow({ icon, label, value, onPress, last = false }: { icon: IconName; label: string; value: string; onPress: () => void; last?: boolean }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <Pressable accessibilityRole="button" accessibilityLabel={`${label}: ${value}. Ajustar`} onPress={onPress} style={({ pressed }) => [s.summaryRow, !last && s.summaryBorder, pressed && { opacity: .7 }]}>
    <Icon name={icon} color={colors.tone('#1872F7', colors.primary)} size={17} /><Text style={s.summaryLabel}>{label}</Text>
    <Text numberOfLines={2} style={s.summaryValue}>{value}</Text><Icon name="chevron" color={colors.tone('#7E92B5', colors.muted)} size={15} />
  </Pressable>;
}

export function OnboardingScreen({ onDone }: { onDone: (user: User) => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const marks = useBrandMarks();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const compact = height < 730;
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [prefs, setPrefs] = useState<Preferences>(initialPreferences);
  const [step, setStep] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [catalog, setCatalog] = useState<AudioVoiceCatalog | null>(null);
  const [catalogLanguage, setCatalogLanguage] = useState('');
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voicesFailed, setVoicesFailed] = useState(false);
  const [notifications, setNotifications] = useState<boolean | null>(null);
  const [nextBriefing, setNextBriefing] = useState<NextBriefing | null>(null);
  const [completedUser, setCompletedUser] = useState<User | null>(null);
  const searchInput = useRef<TextInput>(null);

  const load = () => Promise.all([api.config(), api.onboarding().catch(() => null)])
    .then(([configuration, onboarding]) => { if (onboarding?.preferences) setPrefs(current => ({ ...current, ...onboarding.preferences })); setConfig(configuration); });
  const started = useRef(false);
  useEffect(() => {
    // Load once: a re-run (Fast Refresh in development) must not overwrite choices already made.
    if (started.current) return;
    started.current = true;
    let mounted = true;
    Promise.all([api.config(), api.onboarding().catch(() => null)])
      .then(([configuration, onboarding]) => {
        if (!mounted) return;
        if (onboarding?.preferences) setPrefs(current => ({ ...current, ...onboarding.preferences }));
        setConfig(configuration);
      })
      .catch(cause => { if (mounted) setError(errorMessage(cause)); });
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    const shown = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow', () => setKeyboardOpen(true));
    const hidden = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide', () => setKeyboardOpen(false));
    return () => { shown.remove(); hidden.remove(); };
  }, []);

  const loadVoices = (language: string) => {
    setVoicesLoading(true); setVoicesFailed(false);
    api.audioVoices(language).then(result => {
      // The default voice leads the list and is the first one marked.
      const voices = [...result.voices].sort((a, b) => Number(b.id === result.default_voice_id) - Number(a.id === result.default_voice_id));
      setCatalog({ ...result, voices }); setCatalogLanguage(language);
      setPrefs(current => voices.some(voice => voice.id === current.audio_voice_id) ? current : { ...current, audio_voice_id: result.default_voice_id || voices[0]?.id || null });
    }).catch(() => setVoicesFailed(true)).finally(() => setVoicesLoading(false));
  };
  // Voices depend on the language chosen in step 3, which is saved only at the end.
  useEffect(() => { if (step === 6 && catalogLanguage !== prefs.language && !voicesLoading) loadVoices(prefs.language); }, [step, prefs.language]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (change: Partial<Preferences>) => setPrefs(current => ({ ...current, ...change }));
  const toggleTopic = (code: string) => setPrefs(current => ({ ...current, topics: current.topics.includes(code) ? current.topics.filter(item => item !== code) : [...current.topics, code] }));
  // ~250 topics: build, rank and index them once per config, never on every render (each tap re-renders).
  const topics = useMemo(() => config?.topics.filter(topic => topic.enabled !== false) || [], [config]);
  // Popular: the broad topics first, by exact name (a loose match also pulled "Tecnologia médica" and such),
  // then the other top-level topics in their configured order.
  const rankedTopics = useMemo(() => {
    const desired = ['tecnologia', 'inteligencia artificial', 'economia', 'negocios', 'politica', 'esportes', 'saude', 'meio ambiente'];
    const rank = (topic: Topic) => { const index = desired.indexOf(fold(topic.name)); return index >= 0 ? index : topic.parent_id ? 200 : 100; };
    return topics.map(topic => ({ topic, rank: rank(topic) })).sort((a, b) => a.rank - b.rank).map(item => item.topic);
  }, [topics]);
  const searchable = useMemo(() => topics.map(topic => ({ topic, name: fold(topic.name), key: fold([topic.name, topic.code, ...(topic.aliases || [])].join(' ')) })), [topics]);
  const popular = useMemo(() => rankedTopics.slice(0, 8), [rankedTopics]);
  const moreTopics = useMemo(() => {
    const chosenElsewhere = topics.filter(topic => prefs.topics.includes(topic.code) && !popular.includes(topic));
    const otherRoots = rankedTopics.slice(8).filter(topic => !topic.parent_id && !chosenElsewhere.includes(topic)).slice(0, 8);
    return [...chosenElsewhere, ...otherRoots];
  }, [topics, rankedTopics, popular, prefs.topics]);
  const results = useMemo(() => {
    const needle = fold(query.trim());
    if (!needle) return [];
    return searchable.filter(item => item.key.includes(needle))
      .sort((a, b) => Number(b.name.startsWith(needle)) - Number(a.name.startsWith(needle)) || a.name.localeCompare(b.name))
      .slice(0, 40).map(item => item.topic);
  }, [searchable, query]);
  const topicName = (code: string) => topics.find(topic => topic.code === code)?.name || code;
  const selectedNames = prefs.topics.map(topicName);
  // One line in the review: two names when they fit, otherwise one name and the count of the rest.
  const shown = selectedNames.length > 1 && selectedNames.slice(0, 2).join(', ').length > 22 ? 1 : 2;
  const shortTopics = selectedNames.length > shown ? `${selectedNames.slice(0, shown).join(', ')} e +${selectedNames.length - shown}` : selectedNames.join(' e ');
  const voice = catalog?.voices.find(item => item.id === prefs.audio_voice_id);
  // Android keeps the field focused after the keyboard closes; an empty search then falls back to the topic lists.
  const searching = step === 2 && (query.trim().length > 0 || (searchFocused && keyboardOpen));

  const validate = (target: number) => {
    if (target === 2 && prefs.topics.length === 0) { setError('Selecione pelo menos um tema.'); return false; }
    if (target === 4 && !timePattern.test(prefs.briefing_time)) { setError('Escolha um horário válido no formato HH:MM.'); return false; }
    return true;
  };
  const go = (target: number) => { setError(''); Keyboard.dismiss(); setSearchFocused(false); setStep(target); };
  const next = async () => {
    setError('');
    if (!validate(step)) return;
    if (step === 7) {
      setBusy(true);
      try { const result = await requestAndRegisterDevice(); setNotifications(result.permission === 'AUTHORIZED' || result.permission === 'PROVISIONAL'); }
      catch { setNotifications(false); /* A permissão ou o registro não impedem o onboarding. */ }
      finally { setBusy(false); setReviewing(false); go(8); }
      return;
    }
    if (reviewing) { setReviewing(false); go(8); return; }
    go(step + 1);
  };
  const back = () => { if (reviewing) { setReviewing(false); go(8); return; } go(step - 1); };
  const edit = (target: number) => { setReviewing(true); go(target); };

  const finish = async () => {
    if (!config) return;
    if (!prefs.topics.length || !prefs.topics.every(code => topics.some(topic => topic.code === code))) { setStep(2); setError('Selecione pelo menos um tema válido.'); return; }
    if (!config.supported_languages.includes(prefs.language) || !config.country_scopes.includes(prefs.country_scope)) { setStep(3); setError('Confira o idioma e a cobertura.'); return; }
    if (!timePattern.test(prefs.briefing_time)) { setStep(4); setError('Escolha um horário válido.'); return; }
    if (!config.supported_briefing_sizes.includes(prefs.briefing_size)) { setStep(5); setError('Escolha um tamanho válido.'); return; }
    setBusy(true); setError('');
    try {
      // Everything, the voice included, is saved at once.
      await api.saveOnboarding({ ...prefs, audio_voice_id: prefs.audio_voice_id || null });
      const user = await api.me();
      setNextBriefing((await api.preferences().catch(() => null))?.next_briefing || null);
      setCompletedUser(user);
      setStep(DONE);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };

  const statusBar = <StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} />;
  const bottomPad = { paddingBottom: Math.max(12, 30 - insets.bottom) };

  if (!config) return <SafeAreaView style={s.root} edges={['top', 'bottom']}>{statusBar}
    <View style={s.loading}><ActivityIndicator color={colors.primary} />{!!error && <><Text style={s.error}>{error}</Text><View style={s.retryRow}><Action label="Tentar novamente" onPress={() => {
      setError('');
      load().catch(cause => setError(errorMessage(cause)));
    }} /></View></>}</View>
  </SafeAreaView>;

  if (step === 0 || step === DONE) {
    const done = step === DONE;
    const day = nextBriefing?.day === 'TODAY' ? 'hoje' : 'amanhã';
    return <SafeAreaView style={s.root} edges={['top', 'bottom']}>{statusBar}
      <View style={s.hero}>
        <BrandStack size={compact ? 110 : 132} badge={done} />
        {done ? <View style={[s.heroCopy, { marginTop: compact ? 44 : 58 }]}>
          <Text style={s.doneTitle}>Grandes dias começam{'\n'}com boas informações.</Text><View style={s.dash} />
          <Text style={s.doneText}>Seu primeiro resumo chega{'\n'}{day} às {prefs.briefing_time}{voice ? `, na voz ${voiceWithArticle(voice)}` : ''}.</Text>
        </View> : <Text style={[s.startTagline, { marginTop: compact ? 44 : 60 }]}>Seu resumo diário,{'\n'}sem complicação.</Text>}
      </View>
      <View style={[s.heroActions, { paddingBottom: Math.max(16, 40 - insets.bottom) }]}>
        {done ? <Action label="Começar agora" onPress={() => { if (completedUser) onDone(completedUser); }} disabled={!completedUser} />
          : <Action label="Começar" onPress={() => go(1)} />}
      </View>
    </SafeAreaView>;
  }

  const titles = ['', 'Bem-vindo\nao Newzi', 'Escolha o que\nimporta para você', 'Defina seu idioma\ne escopo', 'Escolha o melhor\nhorário', 'Escolha o tamanho\ndo seu resumo', 'Escolha a voz\ndo seu resumo', 'Ative as notificações', 'Tudo certo!'];
  const subtitles = ['', 'Notícias importantes, todos os dias,\nde forma clara, rápida e no seu ritmo.', 'Selecione quantos temas quiser.', 'Receba notícias em português,\nno cenário global ou nos dois.', 'Receba seu resumo diário\nno momento ideal.', 'Você decide quanto tempo\ntem hoje. A gente se adapta.', 'Toque em ▶ para ouvir uma prévia.', 'Receba um aviso quando seu\nresumo do dia estiver pronto.', 'Confira suas escolhas. Toque em\num item para ajustar.'];
  const primaryLabel = step === 8 ? busy ? 'Salvando…' : 'Salvar tudo' : busy ? 'Aguarde…' : step === 7 ? 'Ativar' : reviewing ? 'Revisar' : 'Próximo';
  const centered = step === 1 || step === 5 || step === 7 || step === 8;
  const today = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());

  return <SafeAreaView style={s.root} edges={['top', 'bottom']}>{statusBar}
    <Glows />
    <View style={s.top}><Lockup height={30} /><Progress step={step} /></View>
    <KeyboardAvoidingView style={s.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView style={s.fill} contentContainerStyle={[s.content, searching && s.contentSearching, compact && s.contentCompact]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {!searching && <>
          <Text style={[s.title, compact && s.titleCompact]}>{titles[step]}</Text>
          <Text style={[s.subtitle, (step === 2 || step === 6) && s.subtitleTight, compact && s.subtitleCompact]}>{subtitles[step]}</Text>
        </>}
        <View style={[s.stage, centered ? s.stageCentered : s.stageTop, compact && s.stageCompact]}>
          {step === 1 && features.map(feature => <View key={feature.icon} style={s.feature}>
            <View style={s.featureIcon}><Icon name={feature.icon} color={colors.tone('#2778F5', colors.primary)} size={22} /></View>
            <View style={s.cardCopy}><Text style={s.featureTitle}>{feature.title}</Text><Text style={s.featureText}>{feature.text}</Text></View>
          </View>)}

          {step === 2 && <>
            <View style={[s.searchRing, searching && s.searchRingActive]}><View style={[s.search, searching && s.searchActive]}>
              <Icon name="search" color={searching ? colors.tone('#2778F5', colors.primary) : colors.tone('#59719B', colors.muted)} size={19} />
              <TextInput ref={searchInput} value={query} onChangeText={setQuery} placeholder="Buscar temas" placeholderTextColor={colors.tone('#59719B', colors.muted)} accessibilityLabel="Buscar temas"
                style={s.searchInput} autoCapitalize="none" autoCorrect={false} returnKeyType="search" onFocus={() => setSearchFocused(true)} onBlur={() => setSearchFocused(false)} onSubmitEditing={() => Keyboard.dismiss()} />
              {!!query && <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" hitSlop={10} onPress={() => setQuery('')} style={s.searchClear}><Icon name="close" color={colors.tone('#FFFFFF', colors.background)} size={12} /></Pressable>}
            </View></View>
            {searching ? <>
              {prefs.topics.length > 0 && <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" style={s.strip} contentContainerStyle={s.stripContent}>
                {prefs.topics.map(code => <View key={code} style={s.miniChip}><Text style={s.miniChipText}>{topicName(code)}</Text>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Remover ${topicName(code)}`} hitSlop={8} onPress={() => toggleTopic(code)} style={s.miniChipX}><Icon name="close" color={colors.tone('#0D5FD8', colors.primary)} size={10} /></Pressable></View>)}
              </ScrollView>}
              {!!query.trim() && <>
                <Text style={[s.sectionLabel, s.resultsLabel]}>{results.length} {results.length === 1 ? 'resultado' : 'resultados'}</Text>
                {results.length > 0 ? <View style={s.resultCard}>{results.map((topic, index) => {
                  const on = prefs.topics.includes(topic.code);
                  const detail = topic.description || (topic.path && topic.path.length > 1 ? topic.path.slice(0, -1).map(topicName).join(' › ') : '');
                  return <Pressable key={topic.code} accessibilityRole="checkbox" accessibilityState={{ checked: on }} accessibilityLabel={topic.name} onPress={() => toggleTopic(topic.code)}
                    style={[s.result, index === results.length - 1 && s.resultLast]}>
                    <View style={s.cardCopy}><Highlight text={topic.name} query={query} />{!!detail && <Text numberOfLines={1} style={s.resultDetail}>{detail}</Text>}</View>
                    <View style={[s.checkbox, on && s.checkboxOn]}>{on && <Icon name="check" color={colors.tone('#FFFFFF', colors.onPrimary)} size={13} />}</View>
                  </Pressable>;
                })}</View> : <Text style={s.empty}>Nenhum tema encontrado.</Text>}
              </>}
            </> : <>
              <View style={[s.sectionHead, s.sectionFirst]}><Text style={s.sectionLabel}>Populares</Text>{prefs.topics.length > 0 && <Text style={s.count}>{prefs.topics.length} {prefs.topics.length === 1 ? 'selecionado' : 'selecionados'}</Text>}</View>
              <View style={s.chips}>{popular.map(topic => <TopicChip key={topic.code} topic={topic} selected={prefs.topics.includes(topic.code)} onPress={() => toggleTopic(topic.code)} />)}</View>
              {moreTopics.length > 0 && <><View style={[s.sectionHead, s.sectionGap]}><Text style={s.sectionLabel}>Mais temas</Text></View>
                <View style={s.chips}>{moreTopics.map(topic => <TopicChip key={topic.code} topic={topic} selected={prefs.topics.includes(topic.code)} onPress={() => toggleTopic(topic.code)} />)}</View></>}
            </>}
          </>}

          {step === 3 && <>
            <Text style={s.sectionLabel}>Idioma</Text>
            <Segmented value={prefs.language} onChange={language => update({ language })} options={config.supported_languages.map(language => ({ value: language, label: languageName(language) }))} />
            <Text style={[s.sectionLabel, s.sectionGap]}>Cobertura</Text>
            {scopeOrder.filter(scope => config.country_scopes.includes(scope)).map(scope => <ChoiceCard key={scope} label={scopeLabel[scope]} detail={scopeDetail[scope]} icon={scopeIcon[scope]}
              tag={scope === 'BOTH' ? 'RECOMENDADO' : undefined} selected={prefs.country_scope === scope} onPress={() => update({ country_scope: scope })} />)}
          </>}

          {step === 4 && <>
            <Text style={s.sectionLabel}>Sugestões</Text>
            <View accessibilityRole="radiogroup" style={s.presets}>{presets.map(preset => {
              const on = prefs.briefing_time === preset.time;
              return <Pressable key={preset.time} accessibilityRole="radio" accessibilityState={{ selected: on }} accessibilityLabel={`${preset.time}, ${preset.label}`} onPress={() => { update({ briefing_time: preset.time }); setError(''); }}
                style={[s.preset, on && s.presetOn]}><Text style={[s.presetTime, on && s.presetTimeOn]}>{preset.time}</Text><Text style={[s.presetLabel, on && s.presetLabelOn]}>{preset.label}</Text></Pressable>;
            })}</View>
            <Text style={[s.sectionLabel, s.sectionGapSmall]}>Ou escolha outro horário</Text>
            <View style={s.timeCard}>
              <TimeWheel large value={prefs.briefing_time} onChange={briefing_time => { update({ briefing_time }); setError(''); }} />
              <View style={s.timeHint}><Icon name="bell" color={colors.tone('#2878F4', colors.primary)} size={14} /><Text style={s.timeHintText}>Seu resumo fica pronto às <Text style={s.timeHintStrong}>{prefs.briefing_time}</Text></Text></View>
            </View>
          </>}

          {step === 5 && sizes.filter(item => config.supported_briefing_sizes.includes(item.size)).map(item => <ChoiceCard key={item.size} label={item.label} detail={`${item.size} notícias · cerca de ${item.minutes} min`}
            icon={item.icon} tag={item.size === 10 ? 'RECOMENDADO' : undefined} right={<Bars count={item.bars} />} selected={prefs.briefing_size === item.size} onPress={() => update({ briefing_size: item.size })} />)}

          {step === 6 && <VoiceStep catalog={catalog} language={prefs.language} loading={voicesLoading} failed={voicesFailed} selected={prefs.audio_voice_id} onSelect={audio_voice_id => update({ audio_voice_id })} onRetry={() => loadVoices(prefs.language)} />}

          {step === 7 && <>
            <View style={s.lockScreen}><Text style={s.lockDate}>{today}</Text><Text style={s.lockTime}>{prefs.briefing_time}</Text></View>
            <View accessible accessibilityLabel={`Exemplo de notificação: Seu resumo de hoje está pronto. ${prefs.briefing_size} notícias, ${sizeMinutes(prefs.briefing_size)} minutos${voice ? `, narrado ${voice.gender === 'male' ? 'pelo' : 'pela'} ${voice.name}` : ''}.`} style={s.notification}>
              <Image source={marks.symbol} resizeMode="contain" style={s.notificationIcon} />
              <View style={s.cardCopy}>
                <View style={s.notificationMeta}><Text style={s.notificationApp}>NEWZI</Text><Text style={s.notificationWhen}>agora</Text></View>
                <Text style={s.notificationTitle}>Seu resumo de hoje está pronto</Text>
                <Text style={s.notificationText}>{prefs.briefing_size} notícias · {sizeMinutes(prefs.briefing_size)} min{voice ? ` · narrado ${voice.gender === 'male' ? 'pelo' : 'pela'} ${voice.name}` : ''}</Text>
              </View>
            </View>
          </>}

          {step === 8 && <>
            <View style={s.summary}>
              <SummaryRow icon="explore" label="Temas" value={shortTopics || 'Nenhum'} onPress={() => edit(2)} />
              <SummaryRow icon="globe" label="Idioma" value={`${languageName(prefs.language)} · ${scopeLabel[prefs.country_scope]}`} onPress={() => edit(3)} />
              <SummaryRow icon="clock" label="Horário" value={prefs.briefing_time} onPress={() => edit(4)} />
              <SummaryRow icon="article" label="Tamanho" value={`${sizeLabel(prefs.briefing_size)} · ${prefs.briefing_size} notícias`} onPress={() => edit(5)} />
              <SummaryRow icon="mic" label="Voz" value={voice?.name || 'Voz padrão'} onPress={() => edit(6)} />
              <SummaryRow icon="bell" label="Avisos" value={notifications ? 'Ativados' : 'Desativados'} onPress={() => edit(7)} last />
            </View>
            <View style={s.savedHint}><Icon name="checkCircle" color={colors.tone('#16A568', colors.success)} size={14} /><Text style={s.savedHintText}>Tudo fica salvo na sua conta de uma vez.</Text></View>
          </>}
        </View>
        {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      </ScrollView>
      {!(step === 2 && keyboardOpen) && <View style={[s.bottom, bottomPad]}>
        <Action label="Voltar" ghost onPress={back} disabled={busy} />
        <Action label={primaryLabel} onPress={step === 8 ? finish : next} disabled={busy} />
      </View>}
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

// Light values are the prototype's (design/onboarding); the few whose text fell under 4.5:1 are a shade darker.
const makeStyles = (colors: Palette) => StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background }, fill: { flex: 1 }, loading: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 }, retryRow: { flexDirection: 'row', width: '100%' },
  hero: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 }, heroCopy: { alignItems: 'center' }, heroActions: { flexDirection: 'row', paddingHorizontal: 22 },
  startTagline: { textAlign: 'center', fontFamily: typography.fontFamily.ui, color: colors.tone('#405D93', colors.secondary), fontSize: 20, lineHeight: 27 },
  doneTitle: { fontFamily: typography.fontFamily.ui, fontSize: 22, lineHeight: 29, fontWeight: '600', letterSpacing: -.4, color: colors.tone('#24427A', colors.ink), textAlign: 'center' },
  dash: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.tone('#2778F5', colors.primary), marginTop: 18 },
  doneText: { marginTop: 20, textAlign: 'center', color: colors.tone('#54709D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 14.5, lineHeight: 21 },
  top: { paddingHorizontal: 22, paddingTop: 8, alignItems: 'center', gap: 16 },
  progress: { flexDirection: 'row', gap: 6, alignSelf: 'stretch' }, progressMark: { flex: 1, height: 4, borderRadius: 4, backgroundColor: colors.tone('#DCE7F3', colors.placeholder) }, progressActive: { backgroundColor: colors.tone('#2778F5', colors.primary) },
  stepCount: { alignSelf: 'stretch', textAlign: 'right', marginTop: -8, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600', letterSpacing: .3, color: colors.tone('#58709A', colors.muted) },
  content: { flexGrow: 1, paddingHorizontal: 22, paddingTop: 22 }, contentSearching: { paddingTop: 16 }, contentCompact: { paddingTop: 10 },
  title: { fontFamily: typography.fontFamily.ui, fontSize: 27, lineHeight: 32, fontWeight: '800', letterSpacing: -1.1, color: colors.tone('#071A42', colors.ink), textAlign: 'center' }, titleCompact: { fontSize: 24, lineHeight: 28 },
  subtitle: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, lineHeight: 22, color: colors.tone('#56709F', colors.secondary), textAlign: 'center', marginTop: 12 }, subtitleTight: { marginTop: 8 }, subtitleCompact: { fontSize: 14, lineHeight: 19, marginTop: 7 },
  stage: { flexGrow: 1, gap: 10, paddingVertical: 18 }, stageCentered: { justifyContent: 'center' }, stageTop: { justifyContent: 'flex-start', gap: 8, paddingTop: 18 }, stageCompact: { paddingVertical: 10 },
  feature: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, borderRadius: 18, borderWidth: 1, borderColor: colors.divider, backgroundColor: colors.surface },
  featureIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: colors.surfaceTint, alignItems: 'center', justifyContent: 'center' },
  featureTitle: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.tone('#142953', colors.ink) }, featureText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 17, color: colors.tone('#58709A', colors.secondary), marginTop: 3 },
  sectionLabel: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', letterSpacing: .6, textTransform: 'uppercase', color: colors.tone('#58709A', colors.secondary), marginHorizontal: 2 },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 2 }, sectionFirst: { marginTop: 10 }, sectionGap: { marginTop: 16 }, sectionGapSmall: { marginTop: 12 },
  count: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600', color: colors.tone('#0868F7', colors.primary) },
  // The focus halo around the field: a 4pt rounded border outside it, transparent until the search is active.
  searchRing: { borderRadius: 20, borderWidth: 4, borderColor: 'transparent', margin: -4 }, searchRingActive: { borderColor: colors.tone('#E3EEFE', colors.surfaceBlue) },
  search: { height: 50, borderRadius: 16, borderWidth: 1, borderColor: colors.tone('#D8E6F6', colors.border), backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14 },
  searchActive: { borderWidth: 1.5, borderColor: colors.tone('#2778F5', colors.primary), paddingHorizontal: 13.5 },
  searchInput: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, color: colors.tone('#071A42', colors.ink), paddingVertical: 0 },
  searchClear: { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.tone('#8FA3BF', colors.muted), alignItems: 'center', justifyContent: 'center' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  chip: { height: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.tone('#DCE7F3', colors.border), backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 7, paddingLeft: 12, paddingRight: 14 },
  chipSelected: { backgroundColor: colors.tone('#0868F7', colors.primary), borderColor: colors.tone('#0868F7', colors.primary) },
  chipText: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, fontWeight: '600', color: colors.tone('#142953', colors.ink) }, chipTextSelected: { color: colors.tone('#FFFFFF', colors.onPrimary) },
  strip: { marginTop: 12, flexGrow: 0 }, stripContent: { gap: 6 },
  miniChip: { height: 32, borderRadius: 16, backgroundColor: colors.tone('#E6F0FD', colors.surfaceBlue), flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 12, paddingRight: 7 },
  miniChipText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, fontWeight: '600', color: colors.tone('#0D5FD8', colors.primary) },
  miniChipX: { width: 18, height: 18, borderRadius: 9, backgroundColor: colors.tone('#CFE0FA', colors.placeholder), alignItems: 'center', justifyContent: 'center' },
  resultsLabel: { marginTop: 16, marginBottom: 2 },
  resultCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider, borderRadius: 18 },
  result: { minHeight: 54, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: 1, borderColor: colors.divider }, resultLast: { borderBottomWidth: 0 },
  resultText: { fontFamily: typography.fontFamily.ui, fontSize: 14.5, color: colors.tone('#142953', colors.ink) }, resultMark: { fontWeight: '700', color: colors.tone('#0D5FD8', colors.primary) },
  resultDetail: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.tone('#58709A', colors.muted), marginTop: 1 },
  checkbox: { width: 22, height: 22, borderRadius: 7, borderWidth: 2, borderColor: colors.tone('#C5D5E8', colors.borderStrong), backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  checkboxOn: { backgroundColor: colors.tone('#0868F7', colors.primary), borderColor: colors.tone('#0868F7', colors.primary) },
  empty: { textAlign: 'center', fontFamily: typography.fontFamily.ui, color: colors.tone('#58709A', colors.secondary), padding: 20 },
  segment: { flexDirection: 'row', padding: 4, borderRadius: 16, backgroundColor: colors.tone('#E6EEF7', colors.surfaceTint), gap: 4 },
  segmentItem: { flex: 1, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }, segmentItemSmall: { height: 34, borderRadius: 10 },
  segmentItemOn: { backgroundColor: colors.tone('#FFFFFF', colors.primary), shadowColor: '#102B57', shadowOpacity: .14, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  segmentText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '600', color: colors.tone('#4F6A93', colors.secondary) }, segmentTextSmall: { fontSize: 13 }, segmentTextOn: { color: colors.tone('#071A42', colors.onPrimary) },
  card: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingVertical: 13, paddingHorizontal: 14, borderRadius: 18, borderWidth: 1.5, borderColor: colors.tone('#E2EBF5', colors.border), backgroundColor: colors.surface },
  cardSelected: { borderColor: colors.tone('#2778F5', colors.primary), backgroundColor: colors.tone('#F2F7FF', colors.surfaceBlue) },
  tile: { width: 44, height: 44, borderRadius: 14, backgroundColor: colors.surfaceTint, alignItems: 'center', justifyContent: 'center' }, tileSelected: { backgroundColor: colors.tone('#DDEBFF', colors.selected) },
  cardCopy: { flex: 1 }, cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  cardTitle: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.tone('#142953', colors.ink) },
  cardDetail: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 17, color: colors.tone('#58709A', colors.secondary), marginTop: 3 },
  tag: { fontFamily: typography.fontFamily.ui, fontSize: 10.5, fontWeight: '700', letterSpacing: .3, color: colors.tone('#0E7C56', colors.success), backgroundColor: colors.tone('#E2F6EC', colors.successSurface), paddingHorizontal: 7, paddingVertical: 3, borderRadius: 6, overflow: 'hidden' },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.tone('#C5D5E8', colors.borderStrong), backgroundColor: colors.surface }, radioOn: { borderWidth: 7, borderColor: colors.tone('#2778F5', colors.primary) },
  bars: { flexDirection: 'row', gap: 3, alignItems: 'flex-end', height: 22 }, bar: { width: 4, borderRadius: 2, backgroundColor: colors.tone('#C8D9EE', colors.waveInactive) }, barOn: { backgroundColor: colors.tone('#2778F5', colors.primary) },
  presets: { flexDirection: 'row', gap: 8 },
  preset: { flex: 1, height: 50, borderRadius: 14, borderWidth: 1, borderColor: colors.tone('#DCE7F3', colors.border), backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  presetOn: { backgroundColor: colors.tone('#0868F7', colors.primary), borderColor: colors.tone('#0868F7', colors.primary) },
  presetTime: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.tone('#142953', colors.ink) }, presetTimeOn: { color: colors.tone('#FFFFFF', colors.onPrimary) },
  presetLabel: { fontFamily: typography.fontFamily.ui, fontSize: 10.5, fontWeight: '500', color: colors.tone('#58709A', colors.muted), marginTop: 2 }, presetLabelOn: { color: colors.tone('#FFFFFF', colors.onPrimary) },
  timeCard: { backgroundColor: colors.surface, borderRadius: 22, borderWidth: 1, borderColor: colors.tone('#E0ECF8', colors.border), paddingTop: 6, paddingHorizontal: 16, paddingBottom: 12 },
  timeHint: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, marginTop: 4 },
  timeHintText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.tone('#58709A', colors.secondary) }, timeHintStrong: { fontWeight: '700', color: colors.tone('#10264E', colors.ink) },
  voiceFilter: { marginTop: -2 }, voiceLoading: { marginTop: 24 }, voiceList: { gap: 8, marginTop: 4 },
  voiceCard: { borderRadius: 18, borderWidth: 1.5, borderColor: colors.tone('#E2EBF5', colors.border), backgroundColor: colors.surface, paddingVertical: 11, paddingLeft: 13, paddingRight: 12 },
  voiceTop: { flexDirection: 'row', alignItems: 'center', gap: 12 }, voiceDetail: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.tone('#58709A', colors.secondary), marginTop: 2 }, voiceRadio: { marginLeft: 4 },
  avatar: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }, avatarText: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: '#FFFFFF' },
  play: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.tone('#E6F0FD', colors.selected), alignItems: 'center', justifyContent: 'center' },
  playOn: { backgroundColor: colors.tone('#2778F5', colors.primary), borderWidth: 5, borderColor: colors.tone('#DCEAFE', colors.selected), width: 50, height: 50, borderRadius: 25, margin: -5 },
  player: { marginTop: 11, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.tone('#DDE9F8', colors.border) },
  quote: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 18, fontStyle: 'italic', color: colors.tone('#3B5480', colors.body) },
  playerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 }, playerTime: { fontFamily: typography.fontFamily.ui, fontSize: 11, color: colors.tone('#58709A', colors.muted), fontVariant: ['tabular-nums'] },
  wave: { flex: 1, height: 28, flexDirection: 'row', alignItems: 'center', gap: 2.5, overflow: 'hidden' }, waveBar: { width: 3, borderRadius: 2, backgroundColor: colors.tone('#2778F5', colors.primary) }, waveBarOff: { backgroundColor: colors.tone('#C8D9EE', colors.waveInactive) },
  hiddenVideo: { position: 'absolute', width: 0, height: 0 },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: 14, borderRadius: 18, backgroundColor: colors.surfaceTint, marginTop: 8 },
  noticeText: { flex: 1, minWidth: 200, fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 19, color: colors.tone('#4F6A93', colors.secondary) },
  noticeAction: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: colors.tone('#0868F7', colors.primary) },
  lockScreen: { alignItems: 'center', marginBottom: 12 }, lockDate: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.tone('#55719A', colors.secondary) },
  lockTime: { fontFamily: typography.fontFamily.ui, fontSize: 64, lineHeight: 70, fontWeight: '700', letterSpacing: -2, color: colors.tone('#0F1E33', colors.ink) },
  notification: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14, borderRadius: 22, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider, shadowColor: '#102B57', shadowOpacity: .2, shadowRadius: 15, shadowOffset: { width: 0, height: 14 }, elevation: 3 },
  notificationIcon: { width: 40, height: 40 * 429 / 447, borderRadius: 10 },
  notificationMeta: { flexDirection: 'row', justifyContent: 'space-between' }, notificationApp: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, fontWeight: '600', letterSpacing: .3, color: colors.tone('#58709A', colors.secondary) }, notificationWhen: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.tone('#58709A', colors.secondary) },
  notificationTitle: { fontFamily: typography.fontFamily.ui, fontSize: 14.5, fontWeight: '700', color: colors.tone('#142953', colors.ink), marginTop: 3 },
  notificationText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 17, color: colors.tone('#58709A', colors.secondary), marginTop: 2 },
  summary: { backgroundColor: colors.surface, borderRadius: 22, borderWidth: 1, borderColor: colors.divider },
  summaryRow: { minHeight: 50, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16 }, summaryBorder: { borderBottomWidth: 1, borderColor: colors.divider },
  summaryLabel: { width: 70, fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.tone('#5F769B', colors.secondary) },
  summaryValue: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: colors.tone('#19305A', colors.ink), textAlign: 'right' },
  savedHint: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 6 }, savedHintText: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.tone('#58709A', colors.muted) },
  bottom: { flexDirection: 'row', gap: 10, paddingHorizontal: 22, paddingTop: 10 },
  action: { height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  actionPrimary: { flex: 1, backgroundColor: colors.tone('#0868F7', colors.primary), shadowColor: '#0868F7', shadowOpacity: .45, shadowRadius: 11, shadowOffset: { width: 0, height: 10 } },
  actionGhost: { width: 120, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.tone('#E2ECF6', colors.border) },
  actionText: { fontFamily: typography.fontFamily.ui, fontSize: 17, fontWeight: '600', color: colors.onPrimary }, actionGhostText: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, fontWeight: '500', color: colors.tone('#5A75A4', colors.secondary) },
  actionArrow: { position: 'absolute', right: 20 },
  error: { fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 19, color: colors.tone('#BC3D4E', colors.topicRed.icon), textAlign: 'center', marginTop: 10, marginBottom: 8 },
});
