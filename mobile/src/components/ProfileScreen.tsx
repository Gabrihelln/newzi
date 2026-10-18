import React, { useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StatusBar, Text, TextInput, View } from 'react-native';
import { firebaseAuth } from '../services/firebaseAuth';
import { changePasswordWithFirebase, friendlyFirebaseAuthError, hasPasswordSignIn } from '../services/firebaseAuth';
import { isStrongEnough, passwordChecks } from '../services/passwordRules';
import {typography, useStyles, useTheme, type Palette } from '../theme';
import { AppHeader, TAB_GUTTER } from './AppHeader';
import { absolutePhotoUrl, ProfileAvatar } from './SettingsKit';
import { Icon } from './Icon';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import type { User } from '../types/api';
import { PREMIUM_OFFERED } from '../config/store';

type ProfileRoute = 'EditProfile' | 'ContentPreferences' | 'NotificationSettings' | 'Appearance' | 'DailyBriefing' | 'SecurityPrivacy' | 'Account' | 'Subscription';
type ProfileScreenProps = { user: User | null; onNavigate: (route: ProfileRoute) => void; onLogout: () => void };

function memberSince(user?: User | null) {
  const value = firebaseAuth.currentUser?.metadata?.creationTime || user?.created_at;
  if (!value) return 'Data de cadastro indisponível';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Data de cadastro indisponível' : `Membro desde ${new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(date)}`;
}

function ProfileHero() {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={st.hero}>
    <View style={st.heroCopy}><Text style={st.heroTitle}>Seu perfil</Text><Text style={st.heroSub}>Gerencie suas preferências{ '\n' }e personalize sua experiência.</Text></View>
  </View>;
}

function ProfileCard({ user, onEdit }: { user: User | null; onEdit: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const name = user?.display_name?.trim() || firebaseAuth.currentUser?.displayName?.trim() || 'Sua conta';
  return <View style={st.profileCard}>
    <View style={st.profileAvatarWrap}>
      <ProfileAvatar name={name} photo={firebaseAuth.currentUser?.photoURL || absolutePhotoUrl(user?.photo_url)} size={88} letters={2} />
      <Pressable accessibilityRole="button" accessibilityLabel="Editar foto do perfil" onPress={onEdit} style={st.cameraBadge}><Icon name="camera" color={colors.primary} size={22} /></Pressable>
    </View>
    <View style={st.profileCopy}><Text numberOfLines={1} style={st.profileName}>{name}</Text><Text numberOfLines={1} style={st.profileEmail}>{user?.email || firebaseAuth.currentUser?.email || 'E-mail indisponível'}</Text><Text numberOfLines={1} style={st.memberSince}>{memberSince(user)}</Text></View>
    <Pressable accessibilityRole="button" accessibilityLabel="Editar perfil" onPress={onEdit} style={st.editButton}><Icon name="edit" color={colors.primary} size={19} /><Text style={st.editText}>Editar perfil</Text></Pressable>
  </View>;
}

function ProfileMenuRow({ title, subtitle, icon, tint, background, onPress, last = false }: { title: string; subtitle: string; icon: 'settings' | 'bell' | 'sun' | 'moon' | 'lock' | 'profile' | 'card'; tint: string; background: string; onPress: () => void; last?: boolean }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Pressable accessibilityRole="button" accessibilityLabel={`${title}. ${subtitle}`} onPress={onPress} style={[st.menuRow, !last && st.menuRowBorder]}>
    <View style={[st.menuIconBox, { backgroundColor: background }]}><Icon name={icon} color={tint} size={25} /></View>
    <View style={st.menuCopy}><Text style={st.menuTitle}>{title}</Text><Text numberOfLines={2} style={st.menuSubtitle}>{subtitle}</Text></View>
    <Icon name="chevron" color={colors.tone('#64789C', colors.secondary)} size={20} />
  </Pressable>;
}

function ProfileSection({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={st.section}><Text style={st.sectionTitle}>{title}</Text><Text style={st.sectionSubtitle}>{subtitle}</Text><View style={st.menuCard}>{children}</View></View>;
}

export function ProfileScreen({ user, onNavigate, onLogout }: ProfileScreenProps) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const bottomPadding = useFloatingTabContentInset(true);
  return <SafeAreaView style={st.safe}>
    <StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} />
    <ScrollView contentContainerStyle={[st.scrollContent, { paddingBottom: bottomPadding }]}>
      <AppHeader onAvatar={() => onNavigate('Account')} />
      <ProfileHero />
      <ProfileCard user={user} onEdit={() => onNavigate('EditProfile')} />
      <ProfileSection title="Meu Newzi" subtitle="Personalize sua experiência e receba conteúdos mais relevantes.">
        <ProfileMenuRow title="Preferências de conteúdo" subtitle="Escolha os assuntos que mais te interessam" icon="settings" tint={colors.primary} background={colors.tone('#E4F1FF', colors.surfaceTint)} onPress={() => onNavigate('ContentPreferences')} />
        <ProfileMenuRow title="Notificações" subtitle="Gerencie seus alertas e lembretes" icon="bell" tint={colors.tone('#8548E6', colors.topicPurple.icon)} background={colors.topicPurple.background} onPress={() => onNavigate('NotificationSettings')} />
        <ProfileMenuRow title="Aparência" subtitle="Tema claro, escuro ou igual ao do celular" icon="moon" tint={colors.tone('#3D5A8C', colors.secondary)} background={colors.surfaceTint} onPress={() => onNavigate('Appearance')} />
        <ProfileMenuRow title="Resumo diário" subtitle="Configure horário, voz e formato do seu resumo" icon="sun" tint={colors.tone('#F39711', colors.topicOrange.icon)} background={colors.tone('#FFF1D9', colors.topicOrange.background)} onPress={() => onNavigate('DailyBriefing')} last />
      </ProfileSection>
      <ProfileSection title="Minha conta" subtitle="Segurança, privacidade e dados da sua conta.">
        <ProfileMenuRow title="Segurança e privacidade" subtitle="Senha, autenticação e dados" icon="lock" tint={colors.tone('#10A867', colors.topicGreen.icon)} background={colors.topicGreen.background} onPress={() => onNavigate('SecurityPrivacy')} />
        <ProfileMenuRow title="Dados pessoais" subtitle="Suas informações e conta" icon="profile" tint={colors.primary} background={colors.tone('#E4F1FF', colors.surfaceTint)} onPress={() => onNavigate('Account')} last={!PREMIUM_OFFERED} />
        {PREMIUM_OFFERED && <ProfileMenuRow title="Assinatura e plano" subtitle="Plano Básico ou Premium" icon="card" tint={colors.tone('#8548E6', colors.topicPurple.icon)} background={colors.topicPurple.background} onPress={() => onNavigate('Subscription')} last />}
      </ProfileSection>
      <Pressable accessibilityRole="button" accessibilityLabel="Sair da conta" onPress={onLogout} style={({ pressed }) => [st.logout, pressed && { opacity: .7 }]}><Text style={st.logoutText}>Sair da conta</Text></Pressable>
    </ScrollView>
  </SafeAreaView>;
}

export function SecurityPrivacyScreen({ onBack }: { onBack: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const user = firebaseAuth.currentUser;
  const methods = (user?.providerData || []).map(provider => providerName[provider.providerId] || provider.providerId);
  return <SecondaryPage title="Segurança e privacidade" onBack={onBack}>
    <Text style={st.pageIntro}>Informações da sua autenticação.</Text>
    <InfoCard label="Métodos de acesso" value={methods.join(', ') || 'Não disponível'} />
    <InfoCard label="E-mail da conta" value={user?.email || 'Não disponível'} />
    {hasPasswordSignIn() ? <ChangePasswordForm /> : <Text style={[st.helper, { color: colors.tone('#7688A4', colors.secondary) }]}>
      {`Sua conta entra pelo ${methods[0] || 'login social'}, então não tem uma senha do Newzi para trocar.`}</Text>}
  </SecondaryPage>;
}

const providerName: Record<string, string> = { password: 'E-mail e senha', 'google.com': 'Google', 'apple.com': 'Apple' };

/** Current password, new password and its confirmation; saved on Firebase without leaving the app. */
function ChangePasswordForm() {
  const st = useStyles(makeStyles);
  const { colors } = useTheme();
  const [current, setCurrent] = useState(''); const [next, setNext] = useState(''); const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [done, setDone] = useState(false);
  const checks = passwordChecks(next);
  const submit = async () => {
    setError(''); setDone(false);
    if (!current) { setError('Digite sua senha atual.'); return; }
    if (!isStrongEnough(next)) { setError('A nova senha precisa de 8 caracteres, uma letra e um número.'); return; }
    if (next !== confirm) { setError('A confirmação não é igual à nova senha.'); return; }
    if (next === current) { setError('A nova senha precisa ser diferente da atual.'); return; }
    setBusy(true);
    try { await changePasswordWithFirebase(current, next); setCurrent(''); setNext(''); setConfirm(''); setDone(true); }
    catch (cause) {
      const code = typeof cause === 'object' && cause && 'code' in cause ? String((cause as { code?: string }).code) : '';
      setError(code === 'auth/wrong-password' || code === 'auth/invalid-credential' ? 'A senha atual está incorreta.' : friendlyFirebaseAuthError(cause));
    } finally { setBusy(false); }
  };
  const field = (label: string, value: string, onChange: (value: string) => void, autoComplete: 'current-password' | 'new-password') => <>
    <Text style={st.formLabel}>{label}</Text>
    <TextInput accessibilityLabel={label} value={value} onChangeText={text => { onChange(text); setError(''); setDone(false); }} secureTextEntry autoCapitalize="none" autoCorrect={false}
      autoComplete={autoComplete} textContentType={autoComplete === 'current-password' ? 'password' : 'newPassword'} placeholderTextColor={colors.tone('#8192AE', colors.muted)} style={st.input} />
  </>;
  return <View style={{ marginTop: 18 }}>
    <Text accessibilityRole="header" style={[st.formLabel, { fontSize: 17, marginTop: 0 }]}>Alterar senha</Text>
    <Text style={st.helper}>Confirme a senha atual e escolha a nova. As outras sessões da sua conta serão encerradas.</Text>
    {field('Senha atual', current, setCurrent, 'current-password')}
    {field('Nova senha', next, setNext, 'new-password')}
    {!!next && <Text style={[st.helper, { color: checks.longEnough && checks.letterAndNumber ? colors.success : colors.tone('#7688A4', colors.secondary) }]}>
      {`${checks.longEnough ? '✓' : '•'} Pelo menos 8 caracteres   ${checks.letterAndNumber ? '✓' : '•'} Uma letra e um número`}</Text>}
    {field('Confirmar nova senha', confirm, setConfirm, 'new-password')}
    {!!error && <Text accessibilityRole="alert" style={[st.formMessage, { color: colors.danger }]}>{error}</Text>}
    {done && <Text accessibilityRole="alert" style={[st.formMessage, { color: colors.success }]}>Senha alterada. Use a nova senha no próximo acesso.</Text>}
    <ActionButton title={busy ? 'Salvando…' : 'Salvar nova senha'} disabled={busy} onPress={() => void submit()} />
  </View>;
}

export function ProfileInfoScreen({ title, message, onBack }: { title: string; message: string; onBack: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <SecondaryPage title={title} onBack={onBack}><View style={st.infoPanel}><Text style={st.infoText}>{message}</Text></View></SecondaryPage>;
}

function SecondaryPage({ title, onBack, children }: { title: string; onBack: () => void; children: React.ReactNode }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <SafeAreaView style={st.safe}><StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} /><ScrollView contentContainerStyle={st.secondaryContent}><View style={st.secondaryHeader}><Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={st.backButton}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View></Pressable><Text numberOfLines={1} style={st.secondaryTitle}>{title}</Text><View style={{ width: 42 }} /></View>{children}</ScrollView></SafeAreaView>;
}
function ActionButton({ title, onPress, disabled = false }: { title: string; onPress: () => void; disabled?: boolean }) { const st = useStyles(makeStyles); const theme = useTheme(); const { colors } = theme; return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[st.actionButton, disabled && { opacity: .6 }]}><Text style={st.actionButtonText}>{title}</Text></Pressable>; }
function InfoCard({ label, value }: { label: string; value: string }) { const st = useStyles(makeStyles); const theme = useTheme(); const { colors } = theme; return <View style={st.infoCard}><Text style={st.infoLabel}>{label}</Text><Text style={st.infoValue}>{value}</Text></View>; }

const makeStyles = (colors: Palette) => ({
  dialogBackdrop: { flex: 1, backgroundColor: colors.tone('#0A1E4466', colors.scrim), alignItems: 'center' as const, justifyContent: 'center' as const, padding: 24 }, dialogCard: { width: '100%' as const, maxWidth: 380, borderRadius: 24, backgroundColor: colors.surface, padding: 22, alignItems: 'stretch' as const }, dialogIcon: { alignSelf: 'center' as const, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.tone('#E4F1FF', colors.surfaceTint), alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 12 }, dialogTitle: { textAlign: 'center' as const, color: colors.tone('#111B48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, dialogBody: { textAlign: 'center' as const, color: colors.tone('#5E7296', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20, marginTop: 8 }, dialogSecondary: { minHeight: 44, alignItems: 'center' as const, justifyContent: 'center' as const, marginTop: 6 }, dialogSecondaryText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const },
  safe: { flex: 1, backgroundColor: colors.background } as const, scrollContent: { paddingHorizontal: TAB_GUTTER, paddingTop: 0 } as const,
  
  hero: { justifyContent: 'center' as const, marginHorizontal: 1, marginTop: 4, marginBottom: 18 }, heroCopy: { paddingLeft: 3 }, heroTitle: { color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 34, lineHeight: 40, fontWeight: '800' as const, letterSpacing: -.8 }, heroSub: { color: colors.tone('#64799E', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 16, lineHeight: 20, marginTop: 2 }, 
  profileCard: { minHeight: 139, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingHorizontal: 14, paddingVertical: 13, borderRadius: 25, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.tone('#EFF5FA', colors.divider), marginBottom: 21, shadowColor: colors.tone('#7797BA', colors.shadow.color), shadowOpacity: .08, shadowRadius: 11, shadowOffset: { width: 0, height: 4 }, elevation: 2 }, profileAvatarWrap: { width: 88, height: 88, flexShrink: 0, position: 'relative' as const }, cameraBadge: { position: 'absolute' as const, width: 38, height: 38, borderRadius: 20, right: -3, bottom: -1, backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, shadowColor: colors.tone('#6382A5', colors.shadow.color), shadowOpacity: .15, shadowRadius: 5, elevation: 2 }, profileCopy: { flex: 1, minWidth: 0 }, profileName: { color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800' as const }, profileEmail: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 3 }, memberSince: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, marginTop: 3 }, editButton: { minHeight: 45, minWidth: 105, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 6, paddingHorizontal: 9, borderRadius: 14, borderWidth: 1.2, borderColor: colors.primary, backgroundColor: colors.background }, editText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' as const },
  section: { marginBottom: 16 }, sectionTitle: { color: colors.tone('#111B48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 20, lineHeight: 25, fontWeight: '800' as const, letterSpacing: -.4 }, sectionSubtitle: { color: colors.tone('#687D9F', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, marginTop: 1, marginBottom: 8 }, menuCard: { backgroundColor: colors.surface, borderRadius: 25, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.tone('#F0F5FA', colors.divider), shadowColor: colors.tone('#7797BA', colors.shadow.color), shadowOpacity: .06, shadowRadius: 9, shadowOffset: { width: 0, height: 3 }, elevation: 1 }, menuRow: { minHeight: 78, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingVertical: 9 }, menuRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider }, menuIconBox: { width: 49, height: 49, borderRadius: 14, alignItems: 'center' as const, justifyContent: 'center' as const, flexShrink: 0 }, menuCopy: { flex: 1, minWidth: 0 }, menuTitle: { color: colors.tone('#111B48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const }, menuSubtitle: { color: colors.tone('#6B80A0', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 16, marginTop: 2 },
  secondaryContent: { paddingHorizontal: 18, paddingTop: 7, paddingBottom: 42 }, secondaryHeader: { height: 54, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 16 }, backButton: { width: 42, height: 46, justifyContent: 'center' as const }, backGlyph: { color: colors.tone('#667C9F', colors.secondary), fontSize: 34 }, secondaryTitle: { flex: 1, textAlign: 'center' as const, color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, pageIntro: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 21, marginBottom: 16 }, formLabel: { color: colors.tone('#16254A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const, marginTop: 14, marginBottom: 7 }, input: { minHeight: 50, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 15, color: colors.tone('#16254A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15 }, readonly: { justifyContent: 'center' as const }, readonlyText: { color: colors.tone('#7486A4', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15 }, helper: { color: colors.tone('#7688A4', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 17, marginTop: 7 }, timeCard: { borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 15, paddingVertical: 6 }, logout: { minHeight: 50, borderRadius: 25, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, marginTop: 4, marginBottom: 12 }, logoutText: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const }, formMessage: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 12 }, actionButton: { minHeight: 50, borderRadius: 25, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary, marginTop: 18, paddingHorizontal: 20 }, actionButtonText: { color: colors.onPrimary, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const },
  preferenceGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 9 }, topicChoice: { minHeight: 50, minWidth: '47%' as const, maxWidth: '49%' as const, flexGrow: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.tone('#E4EDF7', colors.border), backgroundColor: colors.surface, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 12 }, topicChoiceText: { flex: 1, color: colors.tone('#344866', colors.body), fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '600' as const }, checkMark: { width: 20, color: colors.onPrimary, fontSize: 16, fontWeight: '800' as const }, choiceLine: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 8, marginBottom: 5 }, sizeChoice: { minHeight: 40, borderRadius: 14, borderWidth: 1, borderColor: colors.tone('#E2ECF6', colors.border), backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 11 }, sizeChoiceActive: { borderColor: colors.primary, backgroundColor: colors.surfaceTint }, sizeChoiceText: { color: colors.tone('#5D7192', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600' as const }, voiceRow: { minHeight: 66, flexDirection: 'row' as const, alignItems: 'center' as const, backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.tone('#E6EEF7', colors.border), paddingHorizontal: 14, marginTop: 14 }, audioToggle: { minHeight: 57, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 4, marginTop: 8 },
  addTimeRow: { minHeight: 48, marginTop: 10, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 }, addTimeText: { flex: 1, color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const }, premiumTag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: colors.tone('#FFEFD2', '#3B2A10') }, premiumTagText: { color: colors.tone('#8A5200', '#FFC56B'), fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800' as const, letterSpacing: 1 },
  infoCard: { backgroundColor: colors.surface, borderRadius: 17, padding: 15, marginBottom: 10, borderWidth: 1, borderColor: colors.divider }, infoLabel: { color: colors.tone('#7184A2', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12 }, infoValue: { color: colors.tone('#15234A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600' as const, marginTop: 4 }, infoPanel: { backgroundColor: colors.surface, padding: 18, borderRadius: 20, borderWidth: 1, borderColor: colors.divider }, infoText: { color: colors.tone('#63799B', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 22 },
});
