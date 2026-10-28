import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, AppState, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { api, ClientError } from '../api/client';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { Briefing } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';

/** How a briefing is called: the daily one, a themed or extra one of the day, or one made on request. */
export function briefingTitle(briefing: Pick<Briefing, 'id' | 'kind' | 'theme_label' | 'delivery_time'> | null | undefined) {
  if (briefing?.id?.startsWith('saved:')) return 'Suas matérias salvas';
  if (briefing?.id?.startsWith('match:')) return 'Resumo do jogo';
  if (briefing?.kind === 'ON_DEMAND') return 'Seu resumo na hora';
  if (briefing?.kind === 'EXTRA' && briefing.theme_label) return `Seu resumo de ${briefing.theme_label}`;
  if (briefing?.kind === 'EXTRA') {
    const hour = Number((briefing.delivery_time || '12').slice(0, 2));
    return hour < 12 ? 'Seu resumo da manhã' : hour < 18 ? 'Seu resumo da tarde' : 'Seu resumo da noite';
  }
  return 'Seu resumo diário';
}

const POLL_MS = 4000;
// Past SLOW_MS the row says it is taking longer (a note, not an error) and keeps following, more slowly, until
// the briefing is ready or STOP_MS has passed; the push still tells when it is ready after that.
const SLOW_MS = 4 * 60 * 1000;
const SLOW_POLL_MS = 15000;
const STOP_MS = 30 * 60 * 1000;
const READY_NOTE_MS = 10000;
const QUESTION = 'Teve novidade desde o último?';
const SLOW_NOTE = 'Está demorando mais que o normal. Avisaremos quando ficar pronto.';
const READY_NOTE = 'Seu novo resumo está pronto.';

/**
 * Início › "Gerar agora" (Premium): a new briefing right away, with what is new since the day's earlier ones.
 * The pill says whether there is anything new: "Novo resumo", "Em dia" (nothing new: a tap explains why no new
 * briefing is made) or "Gerando…". ``checkKey`` changes on every Home load, which asks again.
 * Polls the generation until it is ready, then ``onReady`` reloads the Home (the new briefing becomes the current one).
 */
export function OnDemandBriefingButton({ onReady, checkKey }: { onReady: () => void; checkKey?: unknown }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const feature = usePremiumFeature('on_demand_briefing');
  const [working, setWorking] = useState(false);
  // null until the server answers: the pill stays "Novo resumo", as the server checks again on the tap.
  const [upToDate, setUpToDate] = useState<boolean | null>(null);
  const [error, setError] = useState('');
  // A line that is not an error: "taking longer" while it is made, then "ready" for a few seconds.
  const [note, setNote] = useState('');
  const [explaining, setExplaining] = useState(false);
  const run = useRef(0);
  // Set at once on a tap, before the "Gerando…" render, so a quick double tap sends one request.
  const busy = useRef(false);
  const fade = useRef(new Animated.Value(1)).current;
  useEffect(() => () => { run.current++; }, []);

  const mode = working ? 'working' : upToDate ? 'upToDate' : 'new';
  const firstMode = useRef(true);
  useEffect(() => {
    if (firstMode.current) { firstMode.current = false; return; }
    fade.setValue(.35);
    Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: true }).start();
  }, [mode, fade]);

  const follow = async (id: string, current: number, started: number) => {
    busy.current = true; setWorking(true); setError('');
    const finish = () => { busy.current = false; setWorking(false); setNote(''); };
    while (run.current === current) {
      const slow = Date.now() - started > SLOW_MS;
      await new Promise<void>(resolve => setTimeout(resolve, slow ? SLOW_POLL_MS : POLL_MS));
      if (run.current !== current) return;
      if (AppState.currentState !== 'active') continue;
      try {
        const status = await api.generation(id);
        if (status.status === 'READY') {
          finish(); setUpToDate(true); setNote(READY_NOTE); onReady();
          setTimeout(() => setNote(shown => (shown === READY_NOTE ? '' : shown)), READY_NOTE_MS);
          return;
        }
        if (status.status === 'FAILED') {
          finish();
          if (status.error_code === 'NO_ELIGIBLE_CONTENT') { setUpToDate(true); setExplaining(true); }
          else setError('Não foi possível gerar agora. Tente de novo em instantes.');
          return;
        }
      } catch { /* a poll that fails is retried */ }
      if (Date.now() - started > STOP_MS) { finish(); return; }
      if (Date.now() - started > SLOW_MS) setNote(SLOW_NOTE);
    }
  };

  useEffect(() => {
    if (!feature.unlocked || busy.current) return;
    let active = true;
    api.onDemandNews().then(news => {
      if (!active || busy.current) return;
      if (news.generating && news.generation_id) { void follow(news.generation_id, ++run.current, Date.now()); return; }
      // Not being made any more: a "taking longer" line left from an earlier follow is out of date.
      setNote(shown => (shown === SLOW_NOTE ? '' : shown));
      setUpToDate(news.new_count === 0);
    }).catch(() => { /* the pill keeps its last state */ });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feature.unlocked, checkKey]);

  if (!feature.visible) return null;

  const generate = async () => {
    if (!feature.unlocked) { requestPremium('on_demand_briefing'); return; }
    if (busy.current) return;
    if (upToDate) { setExplaining(true); return; }
    busy.current = true;
    const current = ++run.current;
    setWorking(true); setError('');
    try {
      const started = await api.briefingNow();
      void follow(started.generation_id, current, Date.now());
    } catch (cause) {
      busy.current = false; setWorking(false);
      if (handlePremiumError(cause)) return;
      if (cause instanceof ClientError && cause.code === 'NO_NEW_CONTENT') { setUpToDate(true); setExplaining(true); return; }
      setError(cause instanceof ClientError && cause.code === 'ON_DEMAND_LIMIT' ? 'Você já gerou os resumos na hora de hoje. Amanhã tem mais.' : 'Não foi possível gerar agora. Verifique sua conexão.');
    }
  };

  // A small line under the player: the question on the left and a compact pill on the right whose name says
  // what a tap does. Only an error or a note (taking longer, ready) takes the question's place, so the row never
  // grows into a big bar.
  const locked = !feature.unlocked;
  const label = mode === 'working' ? 'Gerando…' : mode === 'upToDate' && !locked ? 'Em dia' : 'Novo resumo';
  const spoken = locked ? 'Gerar um novo resumo agora. Recurso Premium'
    : mode === 'working' ? 'Gerando seu resumo'
    : mode === 'upToDate' ? 'Você está em dia, sem notícias novas'
    : 'Gerar um novo resumo agora';
  const quiet = mode === 'upToDate' && !locked;
  return <View style={s.row}>
    <Text numberOfLines={2} accessibilityRole={error ? 'alert' : undefined} accessibilityLiveRegion="polite"
      style={[s.hint, !!error && { color: colors.danger }, !error && note === READY_NOTE && { color: colors.primary }]}>{error || note || QUESTION}</Text>
    <Pressable accessibilityRole="button" accessibilityLabel={spoken} accessibilityState={{ busy: working, disabled: quiet }}
      disabled={working} onPress={() => void generate()} hitSlop={6} style={({ pressed }) => [s.pill, quiet && s.pillQuiet, pressed && { opacity: .75 }]}>
      <Animated.View style={[s.pillContent, { opacity: fade }]}>
        {working ? <ActivityIndicator color={colors.primary} size="small" />
          : <Icon name={locked ? 'lock' : quiet ? 'check' : 'plus'} color={quiet ? colors.muted : colors.primary} size={14} />}
        <Text style={[s.label, quiet && { color: colors.muted }]}>{label}</Text>
      </Animated.View>
    </Pressable>
    <UpToDateNotice visible={explaining} onClose={() => setExplaining(false)} />
  </View>;
}

/** Tapping "Em dia": why no new briefing is made (it would repeat the last one). */
function UpToDateNotice({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  return <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
    <Pressable accessibilityLabel="Fechar" onPress={onClose} style={s.scrim}>
      <Pressable onPress={() => undefined} style={s.dialog}>
        <View style={s.dialogIcon}><Icon name="checkCircle" color={colors.success} size={28} /></View>
        <Text accessibilityRole="header" style={s.dialogTitle}>Você está em dia</Text>
        <Text style={s.dialogText}>Não há notícias novas desde o seu último resumo. Um novo resumo agora repetiria o mesmo áudio.</Text>
        <Text style={s.dialogText}>Assim que chegarem novidades, o botão volta a ser "Novo resumo".</Text>
        <Pressable accessibilityRole="button" onPress={onClose} style={s.dialogButton}><Text style={s.dialogButtonText}>Entendi</Text></Pressable>
      </Pressable>
    </Pressable>
  </Modal>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: -4, marginBottom: 16, paddingHorizontal: 4 },
  hint: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, color: colors.secondary },
  // One width for every name, so the pill never jumps when it changes.
  pill: { height: 32, minWidth: 132, paddingHorizontal: 12, borderRadius: 16, justifyContent: 'center',
    backgroundColor: colors.tone('#EAF3FF', colors.surfaceTint) },
  pillQuiet: { backgroundColor: colors.tone('#EFF3F8', colors.surfaceSoft) },
  pillContent: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  label: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: colors.primary },
  scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'center', padding: 24 },
  dialog: { backgroundColor: colors.surface, borderRadius: 24, padding: 22, alignItems: 'center' },
  dialogIcon: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.successSurface, marginBottom: 12 },
  dialogTitle: { fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800', color: colors.ink, marginBottom: 8, textAlign: 'center' },
  dialogText: { fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 21, color: colors.body, textAlign: 'center', marginBottom: 6 },
  dialogButton: { alignSelf: 'stretch', minHeight: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 12 },
  dialogButtonText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.onPrimary },
});
