import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, NativeModules, Pressable, SafeAreaView, ScrollView, Text, View } from 'react-native';
import Sound from 'react-native-sound';
import { api } from '../api/client';
import { pauseAudio, syncSelectedBriefingVoice } from '../audio/player';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import type { AudioVoiceCatalog, Briefing, Preferences } from '../types/api';
import { colors, radius, spacing, styles, typography } from '../theme';
import { Icon } from './Icon';

export function VoiceSettingsScreen({ onBack, onSaved }: { onBack: () => void; onSaved?: (id: string) => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [catalog, setCatalog] = useState<AudioVoiceCatalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const sound = useRef<Sound | null>(null);
  const previewRun = useRef(0);
  const mounted = useRef(true);

  const stopPreview = () => {
    previewRun.current++;
    sound.current?.pause();
    sound.current?.release();
    sound.current = null;
    if (mounted.current) { setPreviewing(null); setPreviewLoading(null); }
  };

  useEffect(() => {
    mounted.current = true;
    Promise.all([api.preferences(), api.audioVoices()])
      .then(([saved, voices]) => {
        if (!mounted.current) return;
        setPrefs(saved);
        setCatalog(voices);
        const available = voices.voices.some(voice => voice.id === saved.audio_voice_id);
        setSelected(available ? saved.audio_voice_id! : voices.default_voice_id);
      })
      .catch(() => { if (mounted.current) setMessage('Não foi possível carregar as vozes.'); })
      .finally(() => { if (mounted.current) setLoading(false); });
    return () => { mounted.current = false; previewRun.current++; sound.current?.pause(); sound.current?.release(); sound.current = null; };
  }, []);

  const playPreview = async (id: string, url: string) => {
    if (previewing === id) { stopPreview(); return; }
    stopPreview();
    const run = previewRun.current;
    setPreviewLoading(id);
    setMessage('');
    pauseAudio();
    try {
      const token = await getFirebaseIdToken();
      if (!token) throw new Error('authentication required');
      const cache = NativeModules.NewziAudioCache as { download?: (source: string, auth: string) => Promise<string> } | undefined;
      if (!cache?.download) throw new Error('audio cache unavailable');
      const path = await cache.download(url, token);
      if (previewRun.current !== run || !mounted.current) return;
      const value = await new Promise<Sound>((resolve, reject) => {
        const created = new Sound(path, '', error => error ? reject(error) : resolve(created));
      });
      if (previewRun.current !== run || !mounted.current) { value.release(); return; }
      sound.current = value;
      setPreviewing(id);
      value.play(() => {
        value.release();
        if (sound.current === value) sound.current = null;
        if (mounted.current && previewRun.current === run) setPreviewing(null);
      });
    } catch {
      if (mounted.current && previewRun.current === run) setMessage('Não foi possível reproduzir o exemplo agora.');
    } finally {
      if (mounted.current && previewRun.current === run) setPreviewLoading(null);
    }
  };

  const save = async () => {
    if (!selected || saving) return;
    stopPreview();
    if (selected === prefs?.audio_voice_id) { onBack(); return; }
    setSaving(true);
    setMessage('');
    try {
      const saved = await api.savePreferences({ audio_voice_id: selected });
      if (!mounted.current) return;
      setPrefs(saved);
      setMessage('Voz salva. Atualizando o áudio do seu briefing…');
      void api.home().then(home => {
        const current: Briefing | null = home.today_briefing?.items?.length ? home.today_briefing : home.latest_briefing;
        if (current) syncSelectedBriefingVoice(current, selected);
      }).catch(() => undefined);
      if (onSaved) onSaved(selected);
    } catch {
      if (mounted.current) setMessage('Não foi possível salvar a voz.');
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }}>
    <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xxl, paddingTop: spacing.lg, paddingBottom: spacing.xxxl }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: colors.secondary, fontSize: 13, fontWeight: '800', letterSpacing: 1.3 }}>ÁUDIO NEWZI</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="Fechar seleção de voz" onPress={onBack}
          style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: colors.secondary, fontSize: 28 }}>×</Text></Pressable>
      </View>
      <Text style={[styles.editorial, { fontSize: 34, lineHeight: 40, marginTop: spacing.sm }]}>Escolha a voz do seu briefing</Text>
      <Text style={[styles.subtitle, { marginTop: spacing.sm, marginBottom: spacing.xl }]}>Ouça um exemplo e escolha como prefere acompanhar as notícias.</Text>
      {loading && <ActivityIndicator color={colors.primary} />}
      {!loading && catalog?.voices.length === 0 && <Text style={styles.muted}>As vozes não estão disponíveis agora. Seu briefing em texto continua acessível.</Text>}
      {catalog?.voices.map(voice => {
        const active = selected === voice.id;
        return <View key={voice.id} style={{ backgroundColor: active ? colors.surfaceBlue : colors.surface,
          borderColor: active ? colors.primary : colors.border, borderWidth: active ? 2 : 1,
          borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md }}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Pressable accessibilityRole="radio" accessibilityState={{ selected: active }} accessibilityLabel={`${voice.name}, ${voice.description}`}
              onPress={() => setSelected(voice.id)} style={{ flex: 1, minHeight: 56, justifyContent: 'center' }}>
              <Text style={{ color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '700' }}>{voice.name}</Text>
              <Text style={{ color: colors.secondary, fontSize: 13, marginTop: 3 }}>{voice.description}</Text>
            </Pressable>
            <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ marginRight: spacing.md }}><Icon name={active ? 'radioActive' : 'radio'} color={colors.primary} size={20} /></View>
            <Pressable accessibilityRole="button" accessibilityLabel={`${previewing === voice.id ? 'Parar' : 'Ouvir'} exemplo da voz ${voice.name}`}
              disabled={previewLoading === voice.id} onPress={() => playPreview(voice.id, voice.preview_url)}
              style={{ width: 48, height: 48, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
                alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface }}>
              {previewLoading === voice.id ? <ActivityIndicator color={colors.primary} /> :
                <Icon name={previewing === voice.id ? 'stop' : 'play'} color={colors.primary} size={19} />}
            </Pressable>
          </View>
        </View>;
      })}
      {!!message && <Text accessibilityRole="alert" style={[styles.muted, { marginVertical: spacing.md }]}>{message}</Text>}
      <Pressable accessibilityRole="button" accessibilityLabel="Salvar escolha de voz" disabled={!selected || saving || loading}
        onPress={save} style={{ backgroundColor: colors.primary, minHeight: 56, borderRadius: radius.md,
          justifyContent: 'center', alignItems: 'center', marginTop: spacing.lg, opacity: !selected || saving ? .5 : 1 }}>
        <Text style={{ color: colors.surface, fontSize: 16, fontWeight: '800' }}>{saving ? 'Salvando…' : 'Salvar escolha'}</Text>
      </Pressable>
      {prefs?.audio_voice_id && <Text style={[styles.muted, { textAlign: 'center', marginTop: spacing.md, fontSize: 12 }]}>Sua escolha fica salva na sua conta.</Text>}
    </ScrollView>
  </SafeAreaView>;
}
