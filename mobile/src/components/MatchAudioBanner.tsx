import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { AudioNotReady, playEntry, matchEntry } from '../audio/queue';
import { handlePremiumError } from '../services/premium';
import type { Briefing } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';

/**
 * Esportes, opened from a final-result push (Premium): the game's narrated summary. It is narrated a few seconds
 * after the game ends, so the banner waits for it.
 */
export function MatchAudioBanner({ matchId, onOpen }: { matchId: number; onOpen: (briefing: Briefing) => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [status, setStatus] = useState<'checking' | 'ready' | 'preparing' | 'unavailable'>('checking');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true; let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = () => api.matchAudio(matchId).then(result => {
      if (!active) return;
      if (result.status === 'READY') setStatus('ready');
      else if (['PENDING', 'GENERATING'].includes(result.status) && attempts++ < 20) { setStatus('preparing'); timer = setTimeout(check, 5000); }
      else setStatus('unavailable');
    }).catch(error => { if (active) { handlePremiumError(error); setStatus('unavailable'); } });
    void check();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [matchId]);
  if (status === 'unavailable') return null;
  const play = async () => {
    setBusy(true);
    try { const briefing = await playEntry(matchEntry(matchId, '')); if (briefing) onOpen(briefing); }
    catch (error) { if (error instanceof AudioNotReady) setStatus('preparing'); }
    finally { setBusy(false); }
  };
  return <Pressable accessibilityRole="button" accessibilityLabel="Ouvir o resumo do jogo" disabled={status !== 'ready' || busy} onPress={() => void play()} style={s.banner}>
    <View style={s.icon}>{status === 'ready' && !busy ? <Icon name="headphones" color="#FFFFFF" size={22} /> : <ActivityIndicator color="#FFFFFF" />}</View>
    <View style={{ flex: 1 }}>
      <Text style={s.title}>Resumo do jogo</Text>
      <Text style={s.text}>{status === 'ready' ? 'Placar, tabela e as notícias do jogo em áudio.' : 'Preparando o áudio do jogo…'}</Text>
    </View>
    {status === 'ready' && <Icon name="play" color="#FFFFFF" size={20} />}
  </Pressable>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  banner: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 20, marginBottom: 14, backgroundColor: colors.tone('#0B6E4F', '#0E5A43') },
  icon: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,.18)' },
  title: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: '#FFFFFF' },
  text: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: 'rgba(255,255,255,.9)', marginTop: 2 },
});
