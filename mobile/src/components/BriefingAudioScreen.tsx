import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, ImageBackground, Modal, PanResponder, Pressable, SafeAreaView, ScrollView, Share, StatusBar, Switch, Text, View, useWindowDimensions } from 'react-native';
import { api } from '../api/client';
import { getAudioContext, getAudioProgress, loadAudio, pauseAudio, playAudio, seekAudio, seekTo, setAudioContext, setPlaybackSpeed, subscribeAudio, subscribeAudioContext } from '../audio/player';
import type { AudioContext, PlaybackState } from '../audio/player';
import type { AudioMetadata, Briefing, BriefingItem, Preferences } from '../types/api';
import { colors, typography } from '../theme';
import { Icon } from './Icon';
import type { IconName } from './Icon';
import { AudioChaptersScreen } from './AudioChaptersScreen';

const coverArt = require('../../assets/onboarding/new-sunrise.png');
const readingMascot = require('../../assets/onboarding/new-reading.png');
const celebrationMascot = require('../../assets/onboarding/new-celebrate.png');
const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const initialPlayback: PlaybackState = { position: 0, duration: 0, playing: false, paused: false, ended: false, buffering: false, loaded: false, started: false, speed: 1 };
const speeds = [0.75, 1, 1.25, 1.5, 2];
const speedDescription: Record<number, string> = { 0.75: 'Mais lento', 1: 'Normal', 1.25: 'Mais rápido', 1.5: 'Mais rápido', 2: 'Muito mais rápido' };
const clock = (seconds: number) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.floor(Math.max(0, seconds) % 60)).padStart(2, '0')}`;

function formatEditionDate(briefing: Briefing, timezone?: string) {
  const value = briefing.generated_at || `${briefing.date}T12:00:00`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return briefing.date;
  const parts = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', ...(briefing.generated_at ? { hour: '2-digit', minute: '2-digit' } : {}), ...(timezone ? { timeZone: timezone } : {}) }).format(date);
  return parts.replace('.', '');
}

function nextBriefingLabel(time: string, timezone: string) {
  const now = new Date();
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now).map(part => [part.type, part.value]));
  const [hour, minute] = (time || '06:30').split(':').map(Number);
  const today = Number(parts.hour) * 60 + Number(parts.minute) < hour * 60 + minute;
  return `${today ? 'Hoje' : 'Amanhã'} às ${time || '06:30'}`;
}

function Waveform({ progress, duration, position, onSeek, disabled }: { progress: number; duration: number; position: number; onSeek: (x: number) => void; disabled: boolean }) {
  const [width, setWidth] = useState(0);
  return <View>
    <Pressable accessibilityRole="adjustable" accessibilityLabel="Progresso do áudio" accessibilityValue={{ min: 0, max: Math.max(1, Math.ceil(duration)), now: Math.floor(position) }} accessibilityActions={[{ name: 'increment', label: 'Avançar 15 segundos' }, { name: 'decrement', label: 'Voltar 15 segundos' }]}
      onAccessibilityAction={event => seekAudio(event.nativeEvent.actionName === 'increment' ? 15 : -15)} onLayout={event => setWidth(event.nativeEvent.layout.width)}
      onPress={event => { if (!disabled && width > 0 && duration > 0) onSeek(event.nativeEvent.locationX / width); }} style={a.waveHit}>
      <View style={a.wave}>
        {Array.from({ length: 50 }, (_, index) => {
          const height = 9 + Math.round((Math.abs(Math.sin(index * 1.71) * Math.cos(index * .43)) * 21));
          return <View key={index} style={{ width: 2.5, height, borderRadius: 2, backgroundColor: index / 50 <= progress ? colors.primary : '#C9D7EA' }} />;
        })}
        <View style={[a.scrubber, { left: `${Math.max(0, Math.min(100, progress * 100))}%` }]} />
      </View>
    </Pressable>
    <View style={a.times}><Text style={a.timeText}>{clock(position)}</Text><Text style={a.timeText}>-{clock(Math.max(0, duration - position))}</Text></View>
  </View>;
}

function RoundControl({ label, icon, onPress, primary = false, disabled = false }: { label: string; icon: IconName; onPress: () => void; primary?: boolean; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [a.roundControl, primary && a.roundPrimary, disabled && a.disabled, pressed && !disabled && a.pressed]}>
    <Icon name={icon} color={primary ? '#FFFFFF' : '#0A1E44'} size={primary ? 25 : 21} />
  </Pressable>;
}

function PlaybackOptionsSheet({ visible, speed, onSpeed, onClose }: { visible: boolean; speed: number; onSpeed: (value: number) => void; onClose: () => void }) {
  const responder = useRef(PanResponder.create({ onMoveShouldSetPanResponder: (_event, gesture) => gesture.dy > 8, onPanResponderRelease: (_event, gesture) => { if (gesture.dy > 90) onClose(); } })).current;
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
    <View style={a.modalRoot}>
      <Pressable accessibilityRole="button" accessibilityLabel="Fechar opções de reprodução" onPress={onClose} style={a.scrim} />
      <View style={a.sheet}>
        <View {...responder.panHandlers} style={a.handleArea}><View style={a.handle} /></View>
        <Text style={a.sheetTitle}>Velocidade de reprodução</Text>
        <View style={a.speedList}>{speeds.map(value => <Pressable key={value} accessibilityRole="radio" accessibilityLabel={`${String(value).replace('.', ',')}x, ${speedDescription[value]}`} accessibilityState={{ selected: speed === value }} onPress={() => onSpeed(value)} style={[a.speedOption, speed === value && a.speedSelected]}>
          <View style={a.speedIcon}><Icon name="speed" color={colors.secondary} size={20} /></View><View style={a.speedCopy}><Text style={[a.speedValue, speed === value && a.selectedText]}>{String(value).replace('.', ',')}x</Text><Text style={a.speedHint}>{speedDescription[value]}</Text></View>{speed === value && <Icon name="checkCircle" color={colors.primary} size={19} />}
        </Pressable>)}</View>
      </View>
    </View>
  </Modal>;
}

function NextBriefingCard({ timeLabel, onPress }: { timeLabel: string; onPress?: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`Seu próximo briefing: ${timeLabel}`} onPress={onPress} style={a.nextCard}>
    <Icon name="sun" color="#E99113" size={25} /><View style={{ flex: 1 }}><Text style={a.nextLabel}>Seu próximo briefing</Text><Text style={a.nextTime}>{timeLabel}</Text></View><Icon name="chevron" color={colors.secondary} size={18} />
  </Pressable>;
}

function BriefingCover({ briefing, size, timezone }: { briefing: Briefing; size: number; timezone: string }) {
  return <ImageBackground source={coverArt} resizeMode="cover" imageStyle={a.coverImage} style={[a.cover, { width: size, height: size }]}>
    <View style={a.coverTint} /><Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={a.coverLogo} />
    <View style={a.coverTitle}><Text style={a.coverLabel}>BRIEFING</Text><Text style={a.coverHeading}>Diário</Text></View>
    <Image source={readingMascot} resizeMode="contain" accessibilityLabel="Mascote NEWZI lendo notícias" style={a.coverMascot} />
    <View style={a.coverDate}><Text style={a.coverDateText}>{formatEditionDate(briefing, timezone)}</Text></View>
  </ImageBackground>;
}

function CompletionView({ briefing, timeLabel, onHome, onReplay, onSchedule }: { briefing: Briefing; timeLabel: string; onHome: () => void; onReplay: () => void; onSchedule?: () => void }) {
  const share = () => Share.share({ message: 'Conheça o NEWZI e comece seu dia com um briefing claro e personalizado.' }).catch(() => undefined);
  return <ScrollView contentContainerStyle={a.completionPage}>
    <View style={a.completionHero}><View style={a.completionCheck}><Icon name="check" color={colors.primary} size={32} /></View><Image source={celebrationMascot} resizeMode="contain" accessibilityLabel="Mascote NEWZI comemorando" style={a.celebration} /></View>
    <Text style={a.completionTitle}>Briefing concluído!</Text><Text style={a.completionSubtitle}>Você chegou ao fim do seu resumo do dia.</Text>
    <Pressable accessibilityRole="button" onPress={onHome} style={a.primaryAction}><Text style={a.primaryActionText}>Ver principais notícias</Text><Icon name="chevron" color="#FFFFFF" size={18} /></Pressable>
    <Pressable accessibilityRole="button" onPress={onReplay} style={a.secondaryAction}><Icon name="headphones" color={colors.textPrimary} size={19} /><Text style={a.secondaryActionText}>Ouvir novamente</Text></Pressable>
    <NextBriefingCard timeLabel={timeLabel} onPress={onSchedule} />
    <Pressable accessibilityRole="button" accessibilityLabel="Compartilhar NEWZI" onPress={() => void share()} style={a.shareCard}><View style={a.shareIcon}><Icon name="arrowUpRight" color={colors.primary} size={20} /></View><View style={{ flex: 1 }}><Text style={a.shareTitle}>Gostou do briefing de hoje?</Text><Text style={a.shareSubtitle}>Compartilhe o Newzi com outras pessoas.</Text></View><Icon name="share" color={colors.textPrimary} size={19} /></Pressable>
  </ScrollView>;
}

export function BriefingAudioScreen({ briefing, onBack, onDetail, onHome, onSchedule }: {
  briefing: Briefing; onBack: () => void; onDetail: (item: BriefingItem) => void; onHome: () => void; onSchedule?: () => void;
}) {
  const { width } = useWindowDimensions();
  const [audio, setAudio] = useState<AudioMetadata | null>(null);
  const [activeAudio, setActiveAudio] = useState<AudioMetadata | null>(() => { const session = getAudioContext(); return session && session.briefing.id === briefing.id ? session.metadata : null; });
  const [session, setSession] = useState<AudioContext | null>(() => getAudioContext());
  const [playback, setPlayback] = useState<PlaybackState>(initialPlayback);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const [sheet, setSheet] = useState<'chapters' | 'speed' | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const sessionMatches = Boolean(session?.briefing.id && session.briefing.id === briefing.id);
  const duration = sessionMatches ? playback.duration || ((activeAudio || audio)?.duration_ms || 0) / 1000 : (audio?.duration_ms || 0) / 1000;
  const position = sessionMatches ? playback.position : 0;
  const segments = useMemo(() => (activeAudio?.segments || []).filter(segment => ['INTRO', 'ITEM', 'OUTRO'].includes(segment.type)), [activeAudio?.segments]);
  const currentIndex = segments.findIndex((segment, index) => segment.segment_start_ms != null && position * 1000 >= segment.segment_start_ms && (segment.segment_end_ms == null || position * 1000 < segment.segment_end_ms));
  const currentSegment = currentIndex >= 0 ? segments[currentIndex] : null;
  const currentItem = briefing.items.find(item => item.id === currentSegment?.briefing_item_id);
  const canControl = sessionMatches && playback.loaded && Boolean((activeAudio || audio)?.audio_url);
  const timezone = preferences?.timezone || 'America/Sao_Paulo';
  const nextTime = nextBriefingLabel(preferences?.briefing_time || '06:30', timezone);
  const coverSize = Math.min(width - 56, 380);
  const realDuration = duration > 0 ? `${Math.round(duration / 60)} min` : 'A duração será exibida quando o áudio estiver pronto';

  useEffect(() => subscribeAudio(setPlayback), []);
  useEffect(() => subscribeAudioContext(value => {
    setSession(value);
    if (value && value.briefing.id === briefing.id) {
      setAudio(value.metadata);
      setActiveAudio(value.metadata);
    }
  }), [briefing.id]);
  useEffect(() => { api.preferences().then(setPreferences).catch(() => undefined); }, []);
  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout> | undefined;
    const current = getAudioContext();
    if (current && current.briefing.id === briefing.id) { setAudio(current.metadata); setActiveAudio(current.metadata); setLoading(false); return () => { active = false; }; }
    setActiveAudio(null);
    const refresh = async () => {
      try {
        const value = await api.audio(briefing.id!);
        if (!active) return;
        setAudio(value);
        const pending=['PENDING','GENERATING','VALIDATING'].includes(value.status) || (value.status==='NOT_AVAILABLE' && Boolean(value.generation_stage));
        const lastUpdate=value.generation_updated_at ? Date.parse(value.generation_updated_at) : 0;
        if (pending && (!lastUpdate || Date.now()-lastUpdate<30*60*1000)) timer = setTimeout(refresh, 20000);
      } catch { if (active) setAudio({ status: 'OFFLINE' }); }
    };
    void refresh();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [briefing.id, retryKey]);
  useEffect(() => {
    if (audio?.status !== 'READY' || !audio.audio_url) return;
    let active = true;
    setLoading(true); setError('');
    const current = getAudioContext();
    const load = current?.url === audio.audio_url && current.briefing.id === briefing.id ? Promise.resolve() : loadAudio(audio.audio_url);
    load.then(() => {
      if (!active) return;
      setActiveAudio(audio);
      setAudioContext(audio.audio_url!, briefing, audio);
    }).catch(cause => {
      if (__DEV__) console.warn('[Audio] falha no carregamento:', cause instanceof Error ? cause.stack : String(cause));
      if (active) setError('Não foi possível carregar o áudio.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [audio?.status, audio?.audio_url, briefing.id]);
  useEffect(() => {
    const timer = setInterval(() => getAudioProgress().catch(() => undefined), 500);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let active = true;
    api.savedBriefings().then(({ items }) => { if (active) setSaved(items.some(savedBriefing => savedBriefing.id === briefing.id)); }).catch(() => undefined);
    return () => { active = false; };
  }, [briefing.id]);

  const toggle = async () => {
    try { setError(''); if (playback.playing) pauseAudio(); else await playAudio(); }
    catch { setError('Não foi possível reproduzir o áudio.'); }
  };
  const previousChapter = () => {
    if (currentIndex < 0 || !segments.length) return;
    const currentStart = (currentSegment?.segment_start_ms || 0) / 1000;
    const target = position > currentStart + 3 ? segments[currentIndex] : segments[Math.max(0, currentIndex - 1)];
    if (target.segment_start_ms != null) seekTo(target.segment_start_ms / 1000);
  };
  const nextChapter = () => { const target = segments[currentIndex + 1]; if (target?.segment_start_ms != null) seekTo(target.segment_start_ms / 1000); };
  const playChapter = (seconds: number) => { seekTo(seconds); if (!playback.playing) void playAudio().catch(() => setError('Não foi possível reproduzir o áudio.')); };
  const retry = () => { setError(''); setRetryKey(value => value + 1); };
  const replay = async () => { seekTo(0); try { await playAudio(); } catch { setError('Não foi possível reproduzir o áudio.'); } };
  const saveBriefing = async () => {
    if (!briefing.items.length || saving) return;
    setSaving(true); setSaveError('');
    try {
      if (saved) await api.removeSavedBriefing(briefing.id!);
      else await api.saveBriefing(briefing.id!);
      setSaved(!saved);
    } catch { setSaveError('Não foi possível atualizar os salvos.'); }
    finally { setSaving(false); }
  };
  const share = () => Share.share({ message: 'Conheça o NEWZI e comece seu dia com um briefing claro e personalizado.' }).catch(() => undefined);
  const isCompleted = Boolean(sessionMatches && playback.ended);
  const statusMessage = loading || playback.buffering ? 'Carregando áudio…' : !audio || ['PENDING', 'GENERATING', 'VALIDATING', 'NOT_AVAILABLE'].includes(audio.status) ? 'Preparando seu áudio…' : audio.status === 'FAILED' ? 'Não foi possível preparar o áudio deste briefing.' : audio.status === 'OFFLINE' ? 'Não foi possível carregar o áudio.' : '';

  return <SafeAreaView style={a.safe}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <View style={a.topBar}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={a.back}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={20} /></View></Pressable>
      <Text style={a.topTitle}>Briefing diário</Text><View style={a.back} />
    </View>
    {isCompleted ? <CompletionView briefing={briefing} timeLabel={nextTime} onHome={onHome} onReplay={() => void replay()} onSchedule={onSchedule} /> : <ScrollView contentContainerStyle={a.playerContent} showsVerticalScrollIndicator={false}>
      <BriefingCover briefing={briefing} size={coverSize} timezone={timezone} />
      <Text style={a.title}>Seu resumo do dia</Text>
      <Text style={a.description}>As principais notícias do mundo, em um briefing claro e objetivo.</Text>
      {!!currentItem && <Text numberOfLines={1} style={a.currentChapter}>Agora: {currentItem.primary_taxonomy_label || currentItem.category || currentItem.headline}</Text>}
      <View style={a.metadata}>
        <View style={a.metadataItem}><Icon name="calendar" color="#071A42" size={21} /><View><Text style={a.metadataLabel}>Último briefing</Text><Text style={a.metadataValue}>{formatEditionDate(briefing, timezone)}</Text></View></View>
        <View style={a.metadataItem}><Icon name="clock" color="#071A42" size={21} /><View><Text style={a.metadataLabel}>Duração</Text><Text style={a.metadataValue}>{realDuration}</Text></View></View>
      </View>
      <View style={a.progressBlock}>
        {canControl ? <Waveform progress={duration ? position / duration : 0} duration={duration} position={position} disabled={!canControl} onSeek={fraction => { if (duration) seekTo(duration * fraction); }} /> : <View style={a.wavePlaceholder}><Text style={a.statusLine}>{statusMessage}</Text></View>}
        {!!error && audio?.status === 'READY' && <Pressable accessibilityRole="button" onPress={retry} style={a.inlineRetry}><Text style={a.errorText}>{error}</Text><Text style={a.retryText}>Tentar novamente</Text></Pressable>}
        {audio?.status === 'FAILED' && <Text accessibilityRole="alert" style={a.errorText}>Não foi possível preparar o áudio deste briefing.</Text>}
      </View>
      <View style={a.controls}>
        <RoundControl label="Voltar 15 segundos" icon="rewind" onPress={() => void seekAudio(-15)} disabled={!canControl} />
        <RoundControl label="Capítulo anterior" icon="previous" onPress={previousChapter} disabled={!canControl || !segments.length} />
        <RoundControl label={playback.playing ? 'Pausar briefing' : 'Reproduzir briefing'} icon={playback.playing ? 'pause' : 'play'} onPress={() => void toggle()} primary disabled={!canControl || loading} />
        <RoundControl label="Próximo capítulo" icon="next" onPress={nextChapter} disabled={!canControl || currentIndex < 0 || currentIndex >= segments.length - 1} />
        <RoundControl label="Avançar 15 segundos" icon="forward" onPress={() => void seekAudio(15)} disabled={!canControl} />
      </View>
      {playback.buffering && <Text style={a.buffering}>Carregando trecho…</Text>}
      {!!error && audio?.status !== 'READY' && <Text accessibilityRole="alert" style={a.errorText}>{error}</Text>}
      <View style={a.actions}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Velocidade ${String(playback.speed || 1).replace('.', ',')} vezes`} onPress={() => setSheet('speed')} style={a.actionButton}><Text style={a.actionValue}>{String(playback.speed || 1).replace('.', ',')}x</Text><Text style={a.actionLabel}>Velocidade</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Abrir capítulos e transcrição" onPress={() => setSheet('chapters')} style={a.actionButton}><Icon name="article" color="#0A1E44" size={21} /><Text style={a.actionLabel}>Capítulos</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={saved ? 'Remover briefing dos salvos' : 'Salvar briefing'} accessibilityState={{ selected: saved, disabled: saving || !briefing.items.length }} disabled={saving || !briefing.items.length} onPress={() => void saveBriefing()} style={a.actionButton}><Icon name="bookmark" color={saved ? colors.primary : '#0A1E44'} size={21} /><Text style={a.actionLabel}>{saved ? 'Salvo' : 'Salvar'}</Text></Pressable>
      </View>
      {!!saveError && <Text accessibilityRole="alert" style={a.saveError}>{saveError}</Text>}
      {briefing.items[0] && !canControl && <Pressable accessibilityRole="button" onPress={() => onDetail(briefing.items[0])} style={a.readFallback}><Text style={a.readFallbackText}>Ler as notícias deste briefing</Text><Icon name="chevron" color={colors.primary} size={17} /></Pressable>}
      <NextBriefingCard timeLabel={nextTime} onPress={onSchedule} />
    </ScrollView>}
    <Modal visible={sheet === 'chapters'} animationType="slide" onRequestClose={() => setSheet(null)}>
      <AudioChaptersScreen briefing={briefing} segments={segments} position={position} playing={playback.playing} onClose={() => setSheet(null)} onSeek={seconds => seekTo(seconds)} onPlayChapter={playChapter} />
    </Modal>
    <PlaybackOptionsSheet visible={sheet === 'speed'} speed={playback.speed || 1} onSpeed={value => { setPlaybackSpeed(value); setSheet(null); }} onClose={() => setSheet(null)} />
  </SafeAreaView>;
}

const a = {
  safe: { flex: 1, backgroundColor: colors.background } as const,
  topBar: { height: 49, paddingHorizontal: 12, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const }, back: { width: 48, height: 46, justifyContent: 'center' as const }, backGlyph: { color: colors.secondary, fontSize: 32, lineHeight: 36 }, topTitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13 },
  playerContent: { alignItems: 'center' as const, paddingHorizontal: 20, paddingTop: 5, paddingBottom: 30 }, cover: { borderRadius: 25, overflow: 'hidden' as const, backgroundColor: '#D9E9F8', position: 'relative' as const }, coverImage: { borderRadius: 25 }, coverTint: { position: 'absolute' as const, left: 0, right: 0, top: 0, height: 130, backgroundColor: '#FFFFFF29' }, coverLogo: { position: 'absolute' as const, top: 14, left: 15, width: 86, height: 33 }, coverTitle: { position: 'absolute' as const, top: 53, left: 18 }, coverLabel: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 11, letterSpacing: 1.1 }, coverHeading: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 25, lineHeight: 29 }, coverMascot: { position: 'absolute' as const, width: '76%' as const, height: '76%' as const, right: -13, bottom: 6 }, coverDate: { position: 'absolute' as const, left: 0, right: 0, bottom: 0, height: 38, justifyContent: 'center' as const, alignItems: 'center' as const, backgroundColor: '#071A4270' }, coverDateText: { color: '#FFFFFF', fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 12 },
  title: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 23, textAlign: 'center' as const, marginTop: 16 }, description: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20, textAlign: 'center' as const, marginTop: 3, maxWidth: 320 }, currentChapter: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '700' as const, marginTop: 5, maxWidth: '100%' as const },
  metadata: { alignSelf: 'stretch' as const, flexDirection: 'row' as const, justifyContent: 'space-between' as const, marginTop: 16, marginBottom: 8, paddingHorizontal: 8 }, metadataItem: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9, maxWidth: '60%' as const }, metadataIcon: { fontSize: 22, color: '#071A42' }, metadataLabel: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 10 }, metadataValue: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 12, marginTop: 2 },
  progressBlock: { width: '100%' as const, marginTop: 2 }, waveHit: { height: 42, justifyContent: 'center' as const, width: '100%' as const }, wave: { height: 34, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, overflow: 'visible' as const }, scrubber: { position: 'absolute' as const, width: 13, height: 13, marginLeft: -7, borderRadius: 7, borderWidth: 2, borderColor: '#FFFFFF', backgroundColor: colors.primary, shadowColor: colors.primary, shadowOpacity: .35, shadowRadius: 3, elevation: 2 }, times: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, paddingHorizontal: 2 }, timeText: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11 }, wavePlaceholder: { height: 42, justifyContent: 'center' as const, alignItems: 'center' as const }, statusLine: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 12 }, inlineRetry: { alignItems: 'center' as const, paddingVertical: 3 }, retryText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 12, paddingVertical: 4 },
  controls: { width: '100%' as const, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginTop: 12 }, roundControl: { width: 42, height: 46, alignItems: 'center' as const, justifyContent: 'center' as const, borderRadius: 24 }, roundPrimary: { width: 72, height: 72, borderRadius: 38, backgroundColor: colors.primary, shadowColor: colors.primary, shadowOpacity: .25, shadowRadius: 9, elevation: 4 }, roundGlyph: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, primaryGlyph: { color: '#FFFFFF', fontSize: 27 }, disabled: { opacity: .36 }, pressed: { opacity: .7 }, buffering: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 4 }, errorText: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: 11, textAlign: 'center' as const, marginTop: 4 },
  actions: { alignSelf: 'stretch' as const, flexDirection: 'row' as const, justifyContent: 'space-between' as const, gap: 8, marginTop: 12 }, actionButton: { flex: 1, minHeight: 58, borderRadius: 17, backgroundColor: '#EAF3FC', alignItems: 'center' as const, justifyContent: 'center' as const }, actionValue: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800' as const }, actionIcon: { color: '#0A1E44', fontSize: 21, fontWeight: '700' as const }, savedIcon: { color: colors.primary }, actionLabel: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }, saveError: { color: colors.danger, fontSize: 11, marginTop: 5 }, readFallback: { alignSelf: 'stretch' as const, minHeight: 40, justifyContent: 'center' as const }, readFallbackText: { color: colors.primary, fontWeight: '700' as const, fontSize: 12, textAlign: 'center' as const },
  nextCard: { alignSelf: 'stretch' as const, minHeight: 70, flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 13, borderRadius: 19, backgroundColor: '#E9F3FD', marginTop: 13, gap: 10 }, sun: { fontSize: 24 }, nextLabel: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 11 }, nextTime: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' as const, marginTop: 2 }, nextArrow: { color: colors.secondary, fontSize: 27 },
  modalRoot: { flex: 1, justifyContent: 'flex-end' as const }, scrim: { flex: 1, backgroundColor: 'rgba(7,26,66,.33)' }, sheet: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 16, paddingBottom: 22, maxHeight: '88%' as const }, handleArea: { height: 34, alignItems: 'center' as const, justifyContent: 'center' as const }, handle: { width: 42, height: 4, borderRadius: 4, backgroundColor: '#D4DFEB' }, sheetTitle: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800' as const, marginHorizontal: 4, marginBottom: 12 }, speedList: { gap: 5 }, speedOption: { minHeight: 53, flexDirection: 'row' as const, alignItems: 'center' as const, borderRadius: 15, borderWidth: 1, borderColor: 'transparent', paddingHorizontal: 10, gap: 10 }, speedSelected: { borderColor: '#6AA8FF', backgroundColor: '#EFF7FF' }, speedIcon: { width: 34, height: 34, borderRadius: 18, backgroundColor: '#F0F5FB', alignItems: 'center' as const, justifyContent: 'center' as const }, speedIconText: { color: colors.secondary, fontSize: 18 }, speedCopy: { flex: 1 }, speedValue: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 13 }, selectedText: { color: colors.primary }, speedHint: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 10, marginTop: 1 }, check: { color: colors.primary, fontSize: 19, fontWeight: '800' as const },
  optionRow: { minHeight: 63, borderTopWidth: 1, borderColor: '#E7EFF7', flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, paddingHorizontal: 4 }, optionGlyph: { width: 34, height: 34, borderRadius: 18, backgroundColor: '#F0F5FB', alignItems: 'center' as const, justifyContent: 'center' as const }, optionGlyphText: { color: colors.secondary, fontSize: 16 }, optionCopy: { flex: 1 }, optionTitle: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 12 }, optionSubtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 9, marginTop: 3 },
  completionPage: { flexGrow: 1, paddingHorizontal: 20, paddingTop: 14, paddingBottom: 28, alignItems: 'center' as const, justifyContent: 'center' as const }, completionHero: { width: 224, height: 224, alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 8 }, celebration: { width: 224, height: 224 }, completionCheck: { position: 'absolute' as const, top: 0, width: 58, height: 58, borderRadius: 30, backgroundColor: '#DDEEFF', alignItems: 'center' as const, justifyContent: 'center' as const, zIndex: 2 }, completionCheckText: { color: colors.primary, fontSize: 32, fontWeight: '800' as const }, completionTitle: { color: '#071A42', fontFamily: typography.fontFamily.ui, fontWeight: '800' as const, fontSize: 24, textAlign: 'center' as const, marginTop: 2 }, completionSubtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20, textAlign: 'center' as const, maxWidth: 280, marginTop: 5, marginBottom: 14 }, primaryAction: { alignSelf: 'stretch' as const, minHeight: 52, borderRadius: 28, backgroundColor: colors.primary, alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 9 }, primaryActionText: { color: '#FFFFFF', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' as const }, secondaryAction: { alignSelf: 'stretch' as const, minHeight: 49, borderRadius: 26, backgroundColor: '#FFFFFF', flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 8, borderWidth: 1, borderColor: '#E5EFF8' }, headphone: { color: colors.textPrimary, fontSize: 19 }, secondaryActionText: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontWeight: '700' as const, fontSize: 13 }, shareCard: { alignSelf: 'stretch' as const, minHeight: 76, backgroundColor: '#FFFFFF', borderRadius: 18, paddingHorizontal: 11, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 9, marginTop: 12, borderWidth: 1, borderColor: '#EDF3F9' }, shareIcon: { width: 38, height: 42, borderRadius: 12, backgroundColor: '#E9F3FD', alignItems: 'center' as const, justifyContent: 'center' as const }, shareTitle: { color: '#0A1E44', fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '800' as const }, shareSubtitle: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 10, marginTop: 4 }, shareAction: { color: colors.textPrimary, fontSize: 20, paddingHorizontal: 5 },
};
