import React from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import type { PremiumFeatureId } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';

export type PremiumFeature = PremiumFeatureId | 'briefing_times' | 'favorite_teams';
type Copy = { icon: IconName; title: string; body: string; perks: string[] };

const BRIEFINGS: Copy = {
  icon: 'headphones',
  title: 'Mais resumos no dia é Premium',
  body: 'No plano Básico você recebe 1 resumo por dia. Com o Premium, receba até 3, cada um no seu horário, com todos os seus assuntos ou só um tema.',
  perks: ['Até 3 resumos por dia', 'Um resumo só de Esportes, Economia ou outro tema', 'Resumo na hora e versão estendida'],
};
const TEAMS: Copy = {
  icon: 'ball',
  title: 'Mais de um time é Premium',
  body: 'No plano Básico você acompanha 1 time. Com o Premium, siga até 10 times e receba os jogos, gols e notícias de todos.',
  perks: ['Até 10 times favoritos', 'Lembrete 15 minutos antes do jogo', 'Resumo do jogo em áudio no fim'],
};
const ALERTS: Copy = {
  icon: 'bell',
  title: 'Alertas personalizados são Premium',
  body: 'Receba um aviso quando sair notícia sobre o que importa para você, e acompanhe as histórias que quer ver até o fim.',
  perks: ['Alertas por palavra-chave: empresas, pessoas, cidades', 'Novidades das histórias que você acompanha', 'Sem repetir o que você já recebeu'],
};
const LIBRARY: Copy = {
  icon: 'folder',
  title: 'Salvos sem limite é Premium',
  body: 'Organize suas matérias em coleções, leia e ouça sem internet e reveja todos os seus resumos.',
  perks: ['Coleções para organizar os salvos', 'Matérias e resumos offline', 'Histórico completo e busca nos resumos'],
};
const AUDIO: Copy = {
  icon: 'queue',
  title: 'Ouvir em sequência é Premium',
  body: 'Monte uma fila com seus resumos e ouça também as matérias que você salvou, uma atrás da outra, como um podcast.',
  perks: ['Fila contínua de resumos', 'Ouvir as matérias salvas', 'Baixar para ouvir sem internet'],
};
const IPHONE: Copy = {
  icon: 'phone',
  title: 'Widgets e placar ao vivo são Premium',
  body: 'Coloque seus assuntos e seu time na tela de início e acompanhe o jogo na tela de bloqueio e na Dynamic Island.',
  perks: ['Widgets por assunto ou por time', 'Tamanhos médio e grande', 'Placar ao vivo na tela de bloqueio'],
};

const COPY: Record<PremiumFeature, Copy> = {
  briefing_times: BRIEFINGS, extra_briefings: BRIEFINGS, themed_briefings: BRIEFINGS,
  on_demand_briefing: { ...BRIEFINGS, icon: 'bolt', title: 'Resumo na hora é Premium', body: 'Gere um resumo novo quando quiser, só com o que aconteceu desde o seu último resumo.' },
  extended_briefing: { ...BRIEFINGS, icon: 'layers', title: 'Resumo estendido é Premium', body: 'Ouça cada notícia com mais detalhes e com o que outros veículos acrescentaram, em até 15 minutos.' },
  favorite_teams: TEAMS, team_reminders: TEAMS, match_audio: { ...TEAMS, icon: 'headphones', title: 'Resumo do jogo é Premium' },
  keyword_alerts: ALERTS, story_follow: { ...ALERTS, title: 'Acompanhar histórias é Premium' },
  collections: LIBRARY, offline_downloads: { ...LIBRARY, icon: 'download', title: 'Baixar para ouvir offline é Premium' },
  full_history: { ...LIBRARY, icon: 'calendar', title: 'Histórico completo é Premium', body: 'No plano Básico você vê os resumos dos últimos 7 dias. Com o Premium, reveja e busque todos.' },
  briefing_search: { ...LIBRARY, icon: 'search', title: 'Busca nos resumos é Premium' },
  audio_queue: AUDIO,
  premium_widgets: IPHONE, live_activities: { ...IPHONE, icon: 'ball', title: 'Placar ao vivo é Premium' },
};

/** Bottom sheet shown when a Básico reader taps a Premium feature; it leads to Profile › Assinatura e plano. */
export function PremiumSheet({ feature, visible, onClose, onSeePlans }: { feature: PremiumFeature; visible: boolean; onClose: () => void; onSeePlans: () => void }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const copy = COPY[feature] || BRIEFINGS;
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
    <Pressable accessibilityLabel="Fechar" onPress={onClose} style={styles.scrim}>
      <Pressable accessibilityViewIsModal onPress={() => undefined} style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.head}>
          <View style={styles.icon}><Icon name={copy.icon} size={24} color={colors.primary} /></View>
          <View style={styles.badge}><Text style={styles.badgeText}>PREMIUM</Text></View>
        </View>
        <Text accessibilityRole="header" style={styles.title}>{copy.title}</Text>
        <Text style={styles.body}>{copy.body}</Text>
        <View style={styles.perks}>
          {copy.perks.map(perk => <View key={perk} style={styles.perk}><Icon name="check" size={18} color={colors.primary} /><Text style={styles.perkText}>{perk}</Text></View>)}
        </View>
        <Pressable accessibilityRole="button" onPress={() => { onClose(); onSeePlans(); }} style={({ pressed }) => [styles.cta, pressed && { opacity: .85 }]}>
          <Text style={styles.ctaText}>Ver Assinatura e plano</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={onClose} style={styles.dismiss}><Text style={styles.dismissText}>Agora não</Text></Pressable>
      </Pressable>
    </Pressable>
  </Modal>;
}

const makeStyles = (colors: Palette) => {
  const ui = typography.fontFamily.ui;
  return {
    scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' as const },
    sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 26, borderTopRightRadius: 26, paddingHorizontal: 22, paddingTop: 12, paddingBottom: 30 },
    handle: { alignSelf: 'center' as const, width: 42, height: 4, borderRadius: 2, backgroundColor: colors.divider, marginBottom: 18 },
    head: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10 },
    icon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.surfaceBlue },
    badge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10, backgroundColor: colors.tone('#FFEFD2', '#3B2A10') },
    badgeText: { color: colors.tone('#8A5200', '#FFC56B'), fontFamily: ui, fontSize: 11, fontWeight: '800' as const, letterSpacing: 1.2 },
    title: { color: colors.textPrimary, fontFamily: ui, fontSize: 22, lineHeight: 27, fontWeight: '800' as const, letterSpacing: -.5, marginTop: 14 },
    body: { color: colors.secondary, fontFamily: ui, fontSize: 15, lineHeight: 22, marginTop: 8 },
    perks: { marginTop: 16, gap: 8, padding: 14, borderRadius: 16, backgroundColor: colors.surfaceTint },
    perk: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10 },
    perkText: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '600' as const, flex: 1 },
    cta: { marginTop: 20, minHeight: 54, borderRadius: 27, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary },
    ctaText: { color: colors.onPrimary, fontFamily: ui, fontSize: 16, fontWeight: '800' as const },
    dismiss: { marginTop: 6, minHeight: 48, alignItems: 'center' as const, justifyContent: 'center' as const },
    dismissText: { color: colors.secondary, fontFamily: ui, fontSize: 15, fontWeight: '700' as const },
  };
};
