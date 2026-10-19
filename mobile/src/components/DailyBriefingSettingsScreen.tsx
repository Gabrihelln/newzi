import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, BackHandler, NativeModules, Pressable, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Video from 'react-native-video';
import { api } from '../api/client';
import { pauseAudio } from '../audio/player';
import { isValidBriefingTime } from '../config/time';
import { getDeviceTimezone } from '../config/timezone';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { AudioVoice, BriefingLength, NextBriefing, Preferences } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';
import { SettingSwitch } from './NotificationParts';
import { ExtraBriefingsCard, extraDraftOf, sameExtras, type ExtraDraft } from './ExtraBriefingsCard';
import { ScreenState } from './ScreenPrimitives';
import { Card, Divider, IconBox, SaveBar, SectionHeading, Segmented, SettingsPage } from './SettingsKit';
import { TimeWheel } from './TimeWheel';

type Draft = Pick<Preferences, 'briefing_time' | 'briefing_size' | 'language' | 'country_scope' | 'audio_enabled'> & { briefing_length: BriefingLength };
const SIZES: { value: Preferences['briefing_size']; label: string; minutes: number }[] = [
  { value: 5, label: 'Rápido', minutes: 3 }, { value: 10, label: 'Essencial', minutes: 5 }, { value: 15, label: 'Completo', minutes: 8 },
];
const draftOf = (prefs: Preferences): Draft => ({ briefing_time: prefs.briefing_time, briefing_size: prefs.briefing_size, language: prefs.language, country_scope: prefs.country_scope, audio_enabled: prefs.audio_enabled, briefing_length: prefs.briefing_length || 'standard' });
const sameDraft = (a: Draft, b: Draft) => (Object.keys(a) as (keyof Draft)[]).every(key => a[key] === b[key]);
const minutesOf = (time: string) => { const [hour, minute] = time.split(':').map(Number); return hour * 60 + minute; };

/**
 * When the next briefing arrives with the time being edited. There is one briefing a day: once today's is
 * made (the saved preferences say the next one is tomorrow), any new time starts tomorrow.
 */
function nextDay(time: string, saved: NextBriefing | undefined) {
  const now = new Date();
  const todayDone = saved?.day === 'TOMORROW';
  return !todayDone && minutesOf(time) > now.getHours() * 60 + now.getMinutes() ? 'Hoje' : 'Amanhã';
}

export function DailyBriefingSettingsScreen({ onBack, onVoice }: { onBack: () => void; onVoice: () => void; onSubscription?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const timezone = getDeviceTimezone();
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [saved, setSaved] = useState<Preferences | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [voices, setVoices] = useState<AudioVoice[]>([]);
  const [extras, setExtras] = useState<ExtraDraft[]>([]);
  const [savedExtras, setSavedExtras] = useState<ExtraDraft[]>([]);
  const [slotLimit, setSlotLimit] = useState(1);
  const extended = usePremiumFeature('extended_briefing');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const preview = useVoicePreview();

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const [prefs, catalog, slots] = await Promise.all([api.preferences(), api.audioVoices().catch(() => ({ voices: [] as AudioVoice[] })), api.briefingSlots().catch(() => null)]);
      setSaved(prefs); setDraft(draftOf(prefs)); setVoices(catalog.voices);
      if (slots) { const drafts = extraDraftOf(slots.extra); setExtras(drafts); setSavedExtras(drafts); setSlotLimit(slots.limit); }
      setStatus('loaded');
    } catch { setStatus('error'); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  // The voice is chosen on its own screen: show it when coming back, without touching the other unsaved choices.
  useFocusEffect(useCallback(() => {
    api.preferences().then(prefs => setSaved(current => current ? { ...current, audio_voice_id: prefs.audio_voice_id } : current)).catch(() => undefined);
    return () => preview.stop();
  }, [])); // eslint-disable-line react-hooks/exhaustive-deps

  const prefsDirty = Boolean(saved && draft && !sameDraft(draftOf(saved), draft));
  const extrasDirty = !sameExtras(extras, savedExtras);
  const dirty = prefsDirty || extrasDirty;
  const update = (change: Partial<Draft>) => { setDraft(current => current && { ...current, ...change }); setError(''); };

  const save = async () => {
    if (!draft || !saved) return;
    if (!isValidBriefingTime(draft.briefing_time)) { setError('Use um horário válido entre 00:00 e 23:59.'); return; }
    const times = [draft.briefing_time, ...extras.filter(item => item.enabled).map(item => item.time)];
    if (new Set(times).size !== times.length) { setError('Cada resumo precisa de um horário diferente.'); return; }
    setBusy(true); setError('');
    try {
      if (prefsDirty) {
        const result = await api.savePreferences({ ...draft, timezone });
        setSaved({ ...saved, ...draft, timezone, next_briefing: result?.next_briefing });
      }
      if (extrasDirty) {
        const slots = await api.saveBriefingSlots(extras);
        const drafts = extraDraftOf(slots.extra); setExtras(drafts); setSavedExtras(drafts);
        const prefs = await api.preferences().catch(() => null);
        if (prefs) setSaved(current => current && { ...current, next_briefing: prefs.next_briefing });
      }
    } catch (cause) {
      if (!handlePremiumError(cause)) setError('Não foi possível salvar as alterações. Verifique sua conexão e tente novamente.');
    }
    finally { setBusy(false); }
  };

  const leave = useCallback(() => {
    if (!dirty || busy) { if (!busy) onBack(); return true; }
    Alert.alert('Descartar alterações?', 'Seu resumo continuará como estava.', [
      { text: 'Continuar editando', style: 'cancel' }, { text: 'Descartar', style: 'destructive', onPress: onBack }]);
    return true;
  }, [dirty, busy, onBack]);
  useEffect(() => { const sub = BackHandler.addEventListener('hardwareBackPress', leave); return () => sub.remove(); }, [leave]);

  const footer = <SaveBar visible={dirty} busy={busy} onSave={() => void save()} error={error} />;
  if (status !== 'loaded' || !draft || !saved) return <SettingsPage title="Resumo diário" onBack={onBack}>
    {status === 'error' ? <ScreenState kind="error" title="Configurações indisponíveis" message="Não foi possível carregar seu resumo. Verifique sua internet." onRetry={() => void load()} />
      : <ScreenState kind="loading" title="Carregando configurações" />}
  </SettingsPage>;

  const voice = voices.find(item => item.id === saved.audio_voice_id) || voices[0];
  const size = SIZES.find(item => item.value === draft.briefing_size) || SIZES[1];
  const summary = [`${draft.briefing_size} notícias`, `cerca de ${size.minutes} min`, draft.audio_enabled ? (voice ? `voz ${voice.gender === 'male' ? 'do' : 'da'} ${voice.name}` : 'com áudio') : 'sem áudio'].join(' · ');

  return <SettingsPage title="Resumo diário" onBack={leave} footer={footer}>
    <View accessible accessibilityLabel={`Próximo resumo: ${nextDay(draft.briefing_time, saved.next_briefing)} às ${draft.briefing_time}. ${summary}`} style={s.next}>
      <View style={s.nextGlow} />
      <View style={s.nextIcon}><Icon name="sun" color="#FFFFFF" size={26} /></View>
      <View style={{ flex: 1 }}>
        <Text style={s.nextLabel}>PRÓXIMO RESUMO</Text>
        <Text style={s.nextTitle}>{nextDay(draft.briefing_time, saved.next_briefing)} às {draft.briefing_time}</Text>
        <Text style={s.nextText}>{summary}</Text>
      </View>
    </View>

    <SectionHeading title="Quando chega" subtitle="Escolha o horário em que seu resumo fica pronto." />
    <Card>
      <View style={s.headRow}>
        <IconBox icon="clock" tint="orange" />
        <View style={{ flex: 1 }}><Text style={s.rowTitle}>Horário de entrega</Text><Text style={s.rowText}>Todos os dias · deslize para ajustar</Text></View>
      </View>
      <View style={s.wheel}><TimeWheel large value={draft.briefing_time} onChange={briefing_time => update({ briefing_time })} /></View>
      <View style={s.timezone}><Icon name="pin" color={colors.muted} size={16} /><Text style={s.timezoneText}>Fuso automático pelo aparelho · {timezone}</Text></View>
    </Card>
    <ExtraHeading />
    <ExtraBriefingsCard value={extras} onChange={value => { setExtras(value); setError(''); }} mainTime={draft.briefing_time} limit={slotLimit} />

    <SectionHeading title="Conteúdo" subtitle="Quanto e o que entra no seu resumo." />
    <Card>
      {extended.visible && <>
        <Label icon="layers" text="Duração" />
        <Segmented label="Duração do resumo" value={draft.briefing_length} onChange={briefing_length => extended.unlocked || briefing_length === 'standard' ? update({ briefing_length }) : requestPremium('extended_briefing')}
          options={[{ value: 'standard', label: 'Padrão', detail: 'Os destaques' }, { value: 'extended', label: extended.unlocked ? 'Estendido' : 'Estendido ★', detail: 'Mais contexto' }]} />
        <Divider />
      </>}
      <Label icon="article" text="Tamanho" />
      <Segmented label="Tamanho do resumo" value={draft.briefing_size} onChange={briefing_size => update({ briefing_size })}
        options={SIZES.map(item => ({ value: item.value, label: item.label, detail: `${item.value} · ${item.minutes} min` }))} />
      <Divider />
      <Label icon="globe" text="Idioma" />
      <Segmented label="Idioma do resumo" value={draft.language} onChange={language => update({ language })}
        options={[{ value: 'pt-BR', label: 'Português' }, { value: 'en', label: 'English' }]} />
      <Divider />
      <Label icon="explore" text="Cobertura" />
      <Segmented label="Cobertura das notícias" value={draft.country_scope} onChange={country_scope => update({ country_scope })}
        options={[{ value: 'LOCAL', label: 'Brasil' }, { value: 'GLOBAL', label: 'Global' }, { value: 'BOTH', label: 'Brasil e global' }]} />
    </Card>

    <SectionHeading title="Áudio" subtitle="Ouça o resumo narrado enquanto faz outras coisas." />
    <Card>
      <View style={s.headRow}>
        <IconBox icon="headphones" tint="purple" />
        <View style={{ flex: 1 }}><Text style={s.rowTitle}>Áudio do resumo</Text><Text style={s.rowText}>Gerar a versão narrada todo dia</Text></View>
        <SettingSwitch label="Áudio do resumo" value={draft.audio_enabled} onChange={audio_enabled => update({ audio_enabled })} />
      </View>
      <Divider />
      <View style={[s.headRow, !draft.audio_enabled && { opacity: .45 }]} pointerEvents={draft.audio_enabled ? 'auto' : 'none'}>
        <View style={s.voiceAvatar}><Text style={s.voiceInitial}>{(voice?.name || 'V')[0].toUpperCase()}</Text></View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={s.rowTitle}>{voice?.name || 'Voz padrão'}</Text>
          <Text numberOfLines={1} style={s.rowText}>{voice ? `${voice.gender === 'male' ? 'Voz masculina' : 'Voz feminina'} · ${voice.language.startsWith('en') ? 'English' : 'Português'}` : 'Escolha a voz do seu resumo'}</Text>
        </View>
        {voice && <Pressable accessibilityRole="button" accessibilityLabel={`${preview.playing === voice.id ? 'Parar' : 'Ouvir'} exemplo da voz ${voice.name}`} disabled={!draft.audio_enabled || preview.loading === voice.id}
          onPress={() => preview.toggle(voice.id, voice.preview_url)} style={s.play}>
          {preview.loading === voice.id ? <ActivityIndicator color={colors.primary} /> : <Icon name={preview.playing === voice.id ? 'stop' : 'play'} color={colors.primary} size={17} />}
        </Pressable>}
        <Pressable accessibilityRole="button" accessibilityLabel="Alterar a voz do resumo" disabled={!draft.audio_enabled} onPress={onVoice} hitSlop={6} style={s.change}>
          <Text style={s.changeText}>Alterar</Text><Icon name="chevron" color={colors.primary} size={16} />
        </Pressable>
      </View>
      {!!preview.error && <Text accessibilityRole="alert" style={s.previewError}>{preview.error}</Text>}
    </Card>
    {preview.element}
  </SettingsPage>;
}

function ExtraHeading() {
  const extras = usePremiumFeature('extra_briefings');
  if (!extras.visible) return null;
  return <SectionHeading title="Mais resumos no dia" subtitle="Receba até 3 resumos por dia, cada um com seu horário. Escolha um tema para um resumo só de Esportes, Economia ou outro assunto." />;
}

function Label({ icon, text }: { icon: IconName; text: string }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <View style={s.label}><Icon name={icon} color={colors.primary} size={19} /><Text style={s.labelText}>{text}</Text></View>;
}

/** Plays a voice sample in its own short-lived player, separate from the briefing player. */
function useVoicePreview() {
  const [source, setSource] = useState<{ id: string; uri: string } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState('');
  const run = useRef(0);
  const stop = useCallback(() => { run.current++; setSource(null); setLoading(null); }, []);
  useEffect(() => () => { run.current++; }, []);
  const toggle = async (id: string, url: string) => {
    if (source?.id === id) { stop(); return; }
    stop();
    const current = run.current;
    setLoading(id); setError('');
    pauseAudio();
    try {
      const token = await getFirebaseIdToken();
      const cache = NativeModules.NewziAudioCache as { download?: (source: string, auth: string) => Promise<string> } | undefined;
      if (!token || !cache?.download) throw new Error('preview unavailable');
      const path = await cache.download(url, token);
      if (run.current === current) setSource({ id, uri: path.startsWith('file://') ? path : `file://${path}` });
    } catch {
      if (run.current === current) setError('Não foi possível reproduzir o exemplo agora.');
    } finally {
      if (run.current === current) setLoading(null);
    }
  };
  const element = source ? <Video key={source.id} source={{ uri: source.uri }} paused={false} disableFocus={false}
    onEnd={() => setSource(null)} onError={() => { setSource(null); setError('Não foi possível reproduzir o exemplo agora.'); }}
    style={{ position: 'absolute', width: 0, height: 0 }} /> : null;
  return { toggle, stop, playing: source?.id || null, loading, error, element };
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  next: { flexDirection: 'row', alignItems: 'center', gap: 16, padding: 20, borderRadius: 26, overflow: 'hidden', backgroundColor: colors.tone('#1F7FEA', colors.inverse),
    shadowColor: '#1F7FEA', shadowOpacity: .25, shadowRadius: 16, shadowOffset: { width: 0, height: 8 }, elevation: 4 },
  nextGlow: { position: 'absolute', right: -60, top: -40, width: 220, height: 220, borderRadius: 110, backgroundColor: 'rgba(255,255,255,.08)' },
  nextIcon: { width: 54, height: 54, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,.18)' },
  nextLabel: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', letterSpacing: .6, color: 'rgba(255,255,255,.85)' },
  nextTitle: { fontFamily: typography.fontFamily.ui, fontSize: 22, fontWeight: '800', color: '#FFFFFF', marginTop: 2 },
  nextText: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: 'rgba(255,255,255,.92)', marginTop: 3 },
  headRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  rowTitle: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  rowText: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary, marginTop: 2 },
  wheel: { marginTop: 14, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.tone('#F7FAFE', colors.surfaceSoft), overflow: 'hidden' },
  timezone: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 12 },
  timezoneText: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary },
  label: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  labelText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.ink },
  voiceAvatar: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.tone('#2F7FE8', colors.primary) },
  voiceInitial: { fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800', color: '#FFFFFF' },
  play: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceBlue },
  change: { flexDirection: 'row', alignItems: 'center', gap: 2, minHeight: 42 },
  changeText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.primary },
  previewError: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.danger, marginTop: 10 },
});
