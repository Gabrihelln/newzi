import React from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';

export type PremiumFeature = 'briefing_times' | 'favorite_teams';

const COPY: Record<PremiumFeature, { icon: IconName; title: string; body: string; perks: string[] }> = {
  briefing_times: {
    icon: 'headphones',
    title: 'Mais horários de resumo é Premium',
    body: 'No plano Básico você tem 1 horário de resumo por dia. Com o Premium, escolha até 4 horários, do jeito que for melhor para você.',
    perks: ['Até 4 resumos por dia', 'Você escolhe cada horário', 'Todas as vozes e velocidades'],
  },
  favorite_teams: {
    icon: 'ball',
    title: 'Mais de um time é Premium',
    body: 'No plano Básico você acompanha 1 time. Com o Premium, siga vários times e receba os jogos, gols e notícias de todos.',
    perks: ['Até 10 times favoritos', 'Avisos de jogos, gols e resultados', 'Notícias de cada time'],
  },
};

/** Bottom sheet shown when a Básico reader taps a Premium feature; it leads to Profile › Assinatura e plano. */
export function PremiumSheet({ feature, visible, onClose, onSeePlans }: { feature: PremiumFeature; visible: boolean; onClose: () => void; onSeePlans: () => void }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const copy = COPY[feature];
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
    perkText: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '600' as const },
    cta: { marginTop: 20, minHeight: 54, borderRadius: 27, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary },
    ctaText: { color: colors.onPrimary, fontFamily: ui, fontSize: 16, fontWeight: '800' as const },
    dismiss: { marginTop: 6, minHeight: 48, alignItems: 'center' as const, justifyContent: 'center' as const },
    dismissText: { color: colors.secondary, fontFamily: ui, fontSize: 15, fontWeight: '700' as const },
  };
};
