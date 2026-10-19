import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, StyleSheet, Text, View } from 'react-native';
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
const GIVE_UP_MS = 4 * 60 * 1000;

/**
 * Início › "Gerar agora" (Premium): a new briefing right away, with what is new since the day's earlier ones.
 * Polls the generation until it is ready, then ``onReady`` reloads the Home (the new briefing becomes the current one).
 */
export function OnDemandBriefingButton({ onReady }: { onReady: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const feature = usePremiumFeature('on_demand_briefing');
  const [state, setState] = useState<'idle' | 'working' | 'done' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const run = useRef(0);
  useEffect(() => () => { run.current++; }, []);
  if (!feature.visible) return null;

  const follow = async (id: string, current: number, started: number) => {
    while (run.current === current) {
      await new Promise<void>(resolve => setTimeout(resolve, POLL_MS));
      if (run.current !== current) return;
      if (AppState.currentState !== 'active') continue;
      try {
        const status = await api.generation(id);
        if (status.status === 'READY') { setState('done'); setMessage('Seu resumo na hora está pronto.'); onReady(); return; }
        if (status.status === 'FAILED') { setState('error'); setMessage(status.error_code === 'NO_ELIGIBLE_CONTENT' ? 'Ainda não há notícias novas desde o seu último resumo.' : 'Não foi possível gerar agora. Tente de novo em instantes.'); return; }
      } catch { /* a poll that fails is retried */ }
      if (Date.now() - started > GIVE_UP_MS) { setState('error'); setMessage('Está demorando mais que o normal. Avisaremos quando ficar pronto.'); return; }
    }
  };

  const generate = async () => {
    if (!feature.unlocked) { requestPremium('on_demand_briefing'); return; }
    const current = ++run.current;
    setState('working'); setMessage('Gerando um resumo com o que aconteceu desde o último…');
    try {
      const started = await api.briefingNow();
      void follow(started.generation_id, current, Date.now());
    } catch (error) {
      if (handlePremiumError(error)) { setState('idle'); setMessage(''); return; }
      setState('error');
      setMessage(error instanceof ClientError && error.code === 'ON_DEMAND_LIMIT' ? 'Você já gerou os resumos na hora de hoje. Amanhã tem mais.' : 'Não foi possível gerar agora. Verifique sua conexão.');
    }
  };

  // A small line under the player: a short question on the left and a compact pill on the right. Messages about
  // the generation take the question's place, so the row never grows into a big bar.
  const hint = message || 'Teve novidade desde o último?';
  return <View style={s.row}>
    <Text numberOfLines={2} accessibilityRole={state === 'error' ? 'alert' : undefined} style={[s.hint, state === 'error' && { color: colors.danger }]}>{hint}</Text>
    <Pressable accessibilityRole="button" accessibilityLabel={`Gerar um novo resumo agora${feature.unlocked ? '' : '. Recurso Premium'}`} accessibilityState={{ busy: state === 'working' }}
      disabled={state === 'working'} onPress={() => void generate()} hitSlop={6} style={({ pressed }) => [s.pill, pressed && { opacity: .75 }]}>
      {state === 'working' ? <ActivityIndicator color={colors.primary} size="small" /> : <Icon name={feature.unlocked ? 'plus' : 'lock'} color={colors.primary} size={14} />}
      <Text style={s.label}>{state === 'working' ? 'Gerando…' : 'Novo resumo'}</Text>
    </Pressable>
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: -4, marginBottom: 16, paddingHorizontal: 4 },
  hint: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, color: colors.secondary },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 32, paddingHorizontal: 12, borderRadius: 16,
    backgroundColor: colors.tone('#EAF3FF', colors.surfaceTint) },
  label: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: colors.primary },
});
