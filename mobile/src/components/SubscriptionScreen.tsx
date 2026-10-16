import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Linking, Platform, Pressable, Text, View } from 'react-native';
import DeviceInfo from 'react-native-device-info';
import { api } from '../api/client';
import { STORE_NAME } from '../config/store';
import type { Subscription, SubscriptionPlan } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { BrandPage, BrandPageHeader } from './ScreenPrimitives';

const SOON = `A assinatura pela ${STORE_NAME} será liberada em breve. Avisaremos quando estiver disponível.`;
const RESTORING = `Procurando compras na sua conta ${STORE_NAME}…`;

const dateLabel = (value?: string | null) => {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(date) : '';
};

/**
 * Profile › Assinatura e plano: the reader's plan (Básico or Premium) and, on Básico, the Premium plans
 * to subscribe to, monthly or annual. Everything about the subscription lives on this one screen.
 */
export function SubscriptionScreen({ onBack }: { onBack: () => void }) {
  const styles = useStyles(makeStyles);
  const [data, setData] = useState<Subscription | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => { setFailed(false); api.subscription().then(setData).catch(() => setFailed(true)); }, []);
  useEffect(load, [load]);

  return <BrandPage>
    <BrandPageHeader title="Assinatura e plano" onBack={onBack} />
    {!data ? failed
      ? <Pressable accessibilityRole="button" onPress={load} style={styles.card}><Text style={styles.muted}>Não foi possível carregar seu plano. Toque para tentar de novo.</Text></Pressable>
      : <ActivityIndicator style={{ marginTop: 30 }} />
      : data.tier === 'premium' ? <PremiumPlan data={data} /> : <BasicPlan data={data} />}
  </BrandPage>;
}

function BasicPlan({ data }: { data: Subscription }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const [planId, setPlanId] = useState(data.plans[0]?.id || 'annual');
  const plan = data.plans.find(item => item.id === planId) || data.plans[0];
  const used = data.usage.briefing_times, limit = data.limits.briefing_times;
  const full = used >= limit;
  const subscribe = () => Alert.alert('Newzi Premium', data.purchases_enabled ? `Abrindo a ${STORE_NAME}…` : SOON);

  return <View>
    <View style={styles.card}>
      <View style={styles.planHead}>
        <View><Text style={styles.label}>Seu plano</Text><Text style={styles.planName}>Básico</Text></View>
        <View style={styles.statusPill}><Text style={styles.statusText}>Ativo</Text></View>
      </View>
      <View style={styles.usageLine}><Text style={styles.usageLabel}>Horários de resumo</Text><Text style={[styles.usageCount, full && { color: colors.warning }]}>{used} de {limit}</Text></View>
      <View style={styles.track}><View style={[styles.fill, { width: `${Math.min(100, used / Math.max(limit, 1) * 100)}%`, backgroundColor: full ? colors.warning : colors.primary }]} /></View>
    </View>

    <View style={styles.premiumBadge}><Text style={styles.premiumBadgeText}>NEWZI PREMIUM</Text></View>
    <Text accessibilityRole="header" style={styles.title}>Tenha o Newzi completo</Text>
    <View style={styles.benefits}>
      {data.benefits.map(item => <View key={item.title} style={styles.benefit}>
        <View style={styles.benefitIcon}><Icon name="check" size={17} color={colors.primary} /></View>
        <View style={{ flex: 1 }}><Text style={styles.benefitTitle}>{item.title}</Text><Text style={styles.muted}>{item.detail}</Text></View>
      </View>)}
    </View>

    <View accessibilityRole="radiogroup" style={styles.options}>
      {data.plans.map(item => <PlanOption key={item.id} plan={item} selected={item.id === plan?.id} onPress={() => setPlanId(item.id)} />)}
    </View>

    {!!plan && <Pressable accessibilityRole="button" onPress={subscribe} style={({ pressed }) => [styles.cta, pressed && { opacity: .85 }]}>
      <Text style={styles.ctaText}>Assinar por {plan.price}/{plan.per}</Text>
    </Pressable>}
    <Text style={styles.footnote}>Renovação automática. Cancele quando quiser na {STORE_NAME}.</Text>
    <View style={styles.links}>
      <Pressable accessibilityRole="button" onPress={() => Alert.alert('Restaurar compras', data.purchases_enabled ? RESTORING : SOON)} style={styles.restore}>
        <Text style={styles.restoreText}>Restaurar compras</Text>
      </Pressable>
      {!!data.legal?.terms_url && <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(data.legal!.terms_url!)} style={styles.restore}><Text style={styles.legalText}>Termos de uso</Text></Pressable>}
      {!!data.legal?.privacy_url && <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(data.legal!.privacy_url!)} style={styles.restore}><Text style={styles.legalText}>Privacidade</Text></Pressable>}
    </View>
  </View>;
}

function PlanOption({ plan, selected, onPress }: { plan: SubscriptionPlan; selected: boolean; onPress: () => void }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const detail = plan.monthly_equivalent ? `${plan.price} por ${plan.per} · ${plan.monthly_equivalent}/mês` : `${plan.price} por ${plan.per}`;
  return <Pressable accessibilityRole="radio" accessibilityState={{ checked: selected }} accessibilityLabel={`${plan.name}, ${detail}`} onPress={onPress}
    style={[styles.option, selected && styles.optionSelected]}>
    <View style={[styles.radio, { borderColor: selected ? colors.primary : colors.secondary }]}>{selected && <View style={styles.radioDot} />}</View>
    <View style={{ flex: 1 }}><Text style={styles.optionName}>{plan.name}</Text><Text style={styles.muted}>{detail}</Text></View>
    {!!plan.savings_percent && <View style={styles.savings}><Text style={styles.savingsText}>Economize {plan.savings_percent}%</Text></View>}
  </Pressable>;
}

function PremiumPlan({ data }: { data: Subscription }) {
  const styles = useStyles(makeStyles);
  const { colors } = useTheme();
  const plan = data.plans.find(item => item.id === data.period);
  const until = dateLabel(data.expires_at);
  const renewal = data.payment_issue ? `Seu acesso continua até ${until} enquanto o pagamento é resolvido.`
    : data.will_renew ? `Renova em ${until}${plan ? ` por ${plan.price}` : ''}.` : `Premium até ${until}. A renovação está desligada.`;
  const manage = () => void Linking.openURL(Platform.OS === 'ios' ? 'https://apps.apple.com/account/subscriptions'
    : `https://play.google.com/store/account/subscriptions?package=${DeviceInfo.getBundleId()}`);

  return <View>
    {data.payment_issue && <View accessibilityRole="alert" style={styles.warning}>
      <Text style={styles.warningTitle}>Não conseguimos renovar</Text>
      <Text style={styles.warningText}>Atualize a forma de pagamento na {STORE_NAME} até {until} para não perder o Premium.</Text>
    </View>}
    <View style={styles.premiumCard}>
      <View style={styles.planHead}>
        <View style={styles.premiumPill}><Text style={styles.premiumPillText}>PREMIUM</Text></View>
        <Text style={styles.premiumStatus}>{data.payment_issue ? 'Pagamento pendente' : 'Ativo'}</Text>
      </View>
      <Text style={styles.premiumName}>Plano {plan?.name.toLocaleLowerCase('pt-BR') || 'Premium'}</Text>
      <Text style={styles.premiumRenewal}>{renewal}</Text>
    </View>

    <View style={[styles.card, { paddingVertical: 0 }]}>
      <Pressable accessibilityRole="link" onPress={manage} style={styles.row}>
        <Text style={styles.rowText}>Gerenciar na {STORE_NAME}</Text><Icon name="arrowUpRight" size={18} color={colors.secondary} />
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => Alert.alert('Restaurar compras', data.purchases_enabled ? RESTORING : SOON)} style={[styles.row, styles.rowBorder]}>
        <Text style={styles.rowText}>Restaurar compras</Text><Icon name="chevron" size={18} color={colors.secondary} />
      </Pressable>
    </View>

    <Text style={styles.sectionTitle}>Seus benefícios</Text>
    <View style={styles.card}>
      {data.benefits.map(item => <View key={item.title} style={styles.perk}><Icon name="check" size={17} color={colors.primary} /><Text style={styles.perkText}>{item.title}</Text></View>)}
    </View>
    <Text style={styles.footnote}>Para cancelar, use a {STORE_NAME}. Você continua com o Premium até o fim do período já pago.</Text>
  </View>;
}

const makeStyles = (colors: Palette) => {
  const ui = typography.fontFamily.ui;
  const gold = colors.tone('#8A5200', '#FFC56B'), goldBg = colors.tone('#FFEFD2', '#3B2A10');
  const promo = colors.tone('#0A2450', '#16294A');
  return {
    card: { borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 16, paddingVertical: 14, marginBottom: 14 },
    planHead: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const },
    label: { color: colors.secondary, fontFamily: ui, fontSize: 12, fontWeight: '700' as const },
    planName: { color: colors.textPrimary, fontFamily: ui, fontSize: 20, fontWeight: '800' as const, marginTop: 2 },
    statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, backgroundColor: colors.surfaceTint },
    statusText: { color: colors.secondary, fontFamily: ui, fontSize: 12, fontWeight: '700' as const },
    usageLine: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, marginTop: 12 },
    usageLabel: { color: colors.textPrimary, fontFamily: ui, fontSize: 13, fontWeight: '600' as const },
    usageCount: { color: colors.secondary, fontFamily: ui, fontSize: 13, fontWeight: '700' as const },
    track: { marginTop: 6, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTint, overflow: 'hidden' as const },
    fill: { height: 6, borderRadius: 3 },
    premiumBadge: { alignSelf: 'flex-start' as const, marginTop: 8, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10, backgroundColor: goldBg },
    premiumBadgeText: { color: gold, fontFamily: ui, fontSize: 11, fontWeight: '800' as const, letterSpacing: 1.2 },
    title: { color: colors.textPrimary, fontFamily: ui, fontSize: 24, lineHeight: 29, fontWeight: '800' as const, letterSpacing: -.6, marginTop: 8 },
    benefits: { gap: 12, marginTop: 14 },
    benefit: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12 },
    benefitIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.surfaceBlue },
    benefitTitle: { color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '700' as const },
    muted: { color: colors.secondary, fontFamily: ui, fontSize: 12, lineHeight: 17, marginTop: 1 },
    options: { gap: 10, marginTop: 20 },
    option: { minHeight: 68, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 18, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface },
    optionSelected: { borderColor: colors.primary, backgroundColor: colors.surfaceTint },
    radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, alignItems: 'center' as const, justifyContent: 'center' as const },
    radioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: colors.primary },
    optionName: { color: colors.textPrimary, fontFamily: ui, fontSize: 15, fontWeight: '800' as const },
    savings: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 9, backgroundColor: goldBg },
    savingsText: { color: gold, fontFamily: ui, fontSize: 11, fontWeight: '800' as const },
    cta: { marginTop: 18, minHeight: 54, borderRadius: 27, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary },
    ctaText: { color: colors.onPrimary, fontFamily: ui, fontSize: 16, fontWeight: '800' as const },
    footnote: { color: colors.secondary, fontFamily: ui, fontSize: 12, lineHeight: 17, textAlign: 'center' as const, marginTop: 10 },
    links: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, justifyContent: 'center' as const, marginTop: 4 },
    restore: { minHeight: 44, justifyContent: 'center' as const, paddingHorizontal: 10 },
    legalText: { color: colors.secondary, fontFamily: ui, fontSize: 12, textDecorationLine: 'underline' as const },
    restoreText: { color: colors.primary, fontFamily: ui, fontSize: 13, fontWeight: '700' as const },
    warning: { borderRadius: 16, padding: 14, marginBottom: 12, backgroundColor: colors.tone('#FFF1E0', '#3A2614') },
    warningTitle: { color: colors.tone('#5C2E00', '#FFD9B0'), fontFamily: ui, fontSize: 14, fontWeight: '800' as const },
    warningText: { color: colors.tone('#5C2E00', '#FFD9B0'), fontFamily: ui, fontSize: 13, lineHeight: 18, marginTop: 2 },
    premiumCard: { borderRadius: 20, padding: 18, marginBottom: 14, backgroundColor: promo },
    premiumPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10, backgroundColor: '#FFC56B' },
    premiumPillText: { color: '#2A1A00', fontFamily: ui, fontSize: 11, fontWeight: '800' as const, letterSpacing: 1.2 },
    premiumStatus: { color: '#C9D8EE', fontFamily: ui, fontSize: 12, fontWeight: '700' as const },
    premiumName: { color: '#FFFFFF', fontFamily: ui, fontSize: 24, fontWeight: '800' as const, marginTop: 12 },
    premiumRenewal: { color: '#C9D8EE', fontFamily: ui, fontSize: 14, lineHeight: 20, marginTop: 4 },
    row: { minHeight: 54, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const },
    rowBorder: { borderTopWidth: 1, borderTopColor: colors.divider },
    rowText: { color: colors.textPrimary, fontFamily: ui, fontSize: 15, fontWeight: '600' as const },
    sectionTitle: { color: colors.textPrimary, fontFamily: ui, fontSize: 16, fontWeight: '800' as const, marginTop: 4, marginBottom: 10 },
    perk: { minHeight: 38, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10 },
    perkText: { flex: 1, color: colors.textPrimary, fontFamily: ui, fontSize: 14, fontWeight: '600' as const },
  };
};
