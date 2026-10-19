import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api } from '../api/client';
import { PREMIUM_OFFERED, STORE_NAME } from '../config/store';
import { firebaseAuth, revokeAppleAccessIfLinked } from '../services/firebaseAuth';
import type { User } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon, type IconName } from './Icon';
import { ScreenState } from './ScreenPrimitives';
import { absolutePhotoUrl, Badge, Card, Divider, IconBox, ProfileAvatar, SectionHeading, SettingsPage, type Tint } from './SettingsKit';

/** How the account signs in, for the "Sessão" card: Google, Apple or e-mail and password. */
export function signInMethod(): { label: string; icon: IconName } {
  const providers = (firebaseAuth.currentUser?.providerData || []).map(provider => provider.providerId);
  if (providers.includes('google.com')) return { label: 'Google', icon: 'google' };
  if (providers.includes('apple.com')) return { label: 'Apple', icon: 'apple' };
  return { label: 'E-mail e senha', icon: 'mail' };
}

export function AccountScreen({ onBack, onEditProfile, onAccountDeleted }: { onBack: () => void; onEditProfile: () => void; onAccountDeleted: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [user, setUser] = useState<User | null>(null);
  const [plan, setPlan] = useState<'basic' | 'premium' | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      setUser(await api.me() as User);
      setStatus('loaded');
    } catch {
      setStatus(current => current === 'loaded' ? current : 'error');
    }
    if (PREMIUM_OFFERED) api.subscription().then(subscription => setPlan(subscription.tier)).catch(() => undefined);
  }, []);
  // Coming back from Editar perfil shows the new name and photo.
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const deleteAccount = useCallback(async () => {
    setDeleting(true);
    try {
      // Accounts created with Apple: revoke the app's access first, as Apple requires; cancelling keeps the account.
      await revokeAppleAccessIfLinked();
    } catch (error) {
      setDeleting(false);
      if (!(error instanceof Error && error.message === 'AUTH_CANCELLED')) Alert.alert('Não foi possível excluir sua conta', 'Confirme o acesso com a Apple e tente novamente.');
      return;
    }
    try {
      await api.deleteAccount();
      onAccountDeleted();
    } catch {
      setDeleting(false);
      Alert.alert('Não foi possível excluir sua conta', 'Confira sua conexão e tente novamente.');
    }
  }, [onAccountDeleted]);

  const confirmDelete = () => Alert.alert(
    'Excluir conta?',
    `Sua conta, assuntos, salvos, histórico de resumos e configurações serão apagados para sempre. Não é possível desfazer.

Se você assina o Premium, cancele a assinatura nos ajustes da ${STORE_NAME}: excluir a conta não cancela a cobrança.`,
    [{ text: 'Cancelar', style: 'cancel' }, { text: 'Excluir conta', style: 'destructive', onPress: () => void deleteAccount() }],
  );

  const firebaseUser = firebaseAuth.currentUser;
  const name = user?.display_name || firebaseUser?.displayName || 'Seu nome';
  const email = user?.email || firebaseUser?.email || 'E-mail não informado';
  const photo = firebaseUser?.photoURL || absolutePhotoUrl(user?.photo_url);
  const created = user?.created_at || firebaseUser?.metadata?.creationTime;
  const memberSince = created && !Number.isNaN(new Date(created).getTime())
    ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(created)) : 'Data indisponível';
  const method = signInMethod();

  return <SettingsPage title="Dados pessoais" onBack={onBack}>
    {status === 'loading' && <ScreenState kind="loading" title="Carregando dados da conta" />}
    {status === 'error' && <ScreenState kind="error" title="Não foi possível carregar sua conta" message="Confira sua conexão e tente novamente." onRetry={() => { setStatus('loading'); void load(); }} />}
    {status === 'loaded' && <>
      <Card style={s.profile}>
        <ProfileAvatar name={name} photo={photo} size={110} onCamera={onEditProfile} />
        <Text style={s.name}>{name}</Text>
        <Text style={s.email}>{email}</Text>
        <View style={s.badges}>
          {user?.status !== 'DISABLED' && <Badge label="Conta ativa" tint="green" icon="shield" />}
          {PREMIUM_OFFERED && plan && <Badge label={plan === 'premium' ? 'Plano Premium' : 'Plano Básico'} tint="purple" icon="star" />}
        </View>
        <Pressable accessibilityRole="button" onPress={onEditProfile} style={({ pressed }) => [s.editButton, pressed && { opacity: .8 }]}>
          <Icon name="edit" color={colors.primary} size={18} /><Text style={s.editText}>Editar perfil</Text>
        </Pressable>
      </Card>

      <SectionHeading title="Informações da conta" subtitle="Dados usados para identificar você no Newzi." />
      <Card style={s.list}>
        <Row icon="profile" tint="blue" label="Nome" value={name} onPress={onEditProfile} />
        <Divider />
        <Row icon="mail" tint="purple" label="E-mail" value={email} badge={firebaseUser?.emailVerified ? 'VERIFICADO' : undefined} />
        <Divider />
        <Row icon="calendar" tint="orange" label="Membro desde" value={memberSince} />
      </Card>

      <SectionHeading title="Sessão" subtitle="Como você entra na sua conta." />
      <Card style={s.list}>
        <Row icon={method.icon} tint="plain" label="Conectado com" value={method.label} />
        <Divider />
        <Row icon="phone" tint="green" label="Este aparelho" value={`${Platform.OS === 'ios' ? 'iPhone' : 'Android'} · ativo agora`} />
      </Card>

      <SectionHeading title="Zona de perigo" subtitle="Ações que não podem ser desfeitas." danger />
      <Pressable accessibilityRole="button" accessibilityState={{ disabled: deleting, busy: deleting }} disabled={deleting} onPress={confirmDelete}
        style={({ pressed }) => [s.danger, pressed && { opacity: .85 }]}>
        <IconBox icon="trash" tint="red" />
        <View style={{ flex: 1 }}>
          <Text style={s.dangerTitle}>{deleting ? 'Excluindo conta…' : 'Excluir conta'}</Text>
          <Text style={s.dangerText}>Apaga conta, assuntos, salvos, histórico e configurações.</Text>
        </View>
        {deleting ? <ActivityIndicator color={colors.danger} /> : <Icon name="chevron" color={colors.tone('#E79AA5', colors.danger)} size={20} />}
      </Pressable>
    </>}
  </SettingsPage>;
}

function Row({ icon, tint, label, value, badge, onPress }: { icon: IconName; tint: Tint; label: string; value: string; badge?: string; onPress?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const content = <>
    <IconBox icon={icon} tint={tint} />
    <View style={{ flex: 1, minWidth: 0 }}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text numberOfLines={1} style={s.rowValue}>{value}</Text>
    </View>
    {badge && <View style={s.verified}><Text style={s.verifiedText}>{badge}</Text></View>}
    {onPress && <Icon name="chevron" color={colors.muted} size={20} />}
  </>;
  return onPress
    ? <Pressable accessibilityRole="button" accessibilityLabel={`${label}: ${value}. Editar`} onPress={onPress} style={({ pressed }) => [s.row, pressed && { opacity: .7 }]}>{content}</Pressable>
    : <View accessible accessibilityLabel={`${label}: ${value}`} style={s.row}>{content}</View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  profile: { alignItems: 'center', paddingVertical: 26 },
  name: { fontFamily: typography.fontFamily.ui, fontSize: 23, fontWeight: '800', color: colors.ink, marginTop: 14, textAlign: 'center' },
  email: { fontFamily: typography.fontFamily.ui, fontSize: 14.5, color: colors.secondary, marginTop: 3, textAlign: 'center' },
  badges: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginTop: 14 },
  editButton: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48, paddingHorizontal: 24, marginTop: 18, borderRadius: 16, borderWidth: 1.5, borderColor: colors.primary },
  editText: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, fontWeight: '800', color: colors.primary },
  list: { paddingVertical: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 50 },
  rowLabel: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary },
  rowValue: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '700', color: colors.ink, marginTop: 2 },
  verified: { paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8, backgroundColor: colors.topicGreen.background },
  verifiedText: { fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '800', letterSpacing: .4, color: colors.success },
  danger: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, borderRadius: 22, borderWidth: 1.5,
    borderColor: colors.tone('#F6CDD3', colors.dangerSurface), backgroundColor: colors.surface },
  dangerTitle: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.danger },
  dangerText: { fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, color: colors.secondary, marginTop: 2 },
});
