import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { ActivityIndicator, Image, Pressable, SafeAreaView, ScrollView, StatusBar, Switch, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { firebaseAuth } from '../services/firebaseAuth';
import { updateProfile } from '@react-native-firebase/auth';
import { resetPasswordWithFirebase, getFirebaseIdToken } from '../services/firebaseAuth';
import { api } from '../api/client';
import {typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { useLogo } from './brand';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import type { Preferences, User } from '../types/api';
import { ScreenState } from './ScreenPrimitives';
import { getDeviceTimezone } from '../config/timezone';
import { isValidBriefingTime } from '../config/time';
import { PremiumSheet } from './PremiumSheet';
import { PREMIUM_OFFERED } from '../config/store';
import { TimeWheel } from './TimeWheel';

const newTablet = require('../../assets/onboarding/new-tablet.png');
const fallbackAvatar = require('../../assets/onboarding/new-waving.png');
type ProfileRoute = 'EditProfile' | 'ContentPreferences' | 'NotificationSettings' | 'Appearance' | 'DailyBriefing' | 'SecurityPrivacy' | 'Account' | 'Subscription';
type ProfileScreenProps = { user: User | null; onNavigate: (route: ProfileRoute) => void; onSearch: () => void; onLogout: () => void };

function memberSince(user?: User | null) {
  const value = firebaseAuth.currentUser?.metadata?.creationTime || user?.created_at;
  if (!value) return 'Data de cadastro indisponível';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Data de cadastro indisponível' : `Membro desde ${new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(date)}`;
}

function ProfileHeader({ onSearch, onAvatar }: { onSearch: () => void; onAvatar: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [failed, setFailed] = useState(false);
  const avatar = firebaseAuth.currentUser?.photoURL;
  return <View style={st.header}>
    <Image source={useLogo()} resizeMode="contain" accessibilityLabel="NEWZI" style={st.logo} />
    <View style={st.headerRight}>
      <Pressable accessibilityRole="button" accessibilityLabel="Buscar notícias" onPress={onSearch} style={st.headerButton}><Icon name="search" color={colors.tone('#12264D', colors.ink)} size={25} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir dados pessoais" onPress={onAvatar} style={st.headerAvatar}>{avatar && !failed ? <Image source={{ uri: avatar }} onError={() => setFailed(true)} style={st.avatarImage} /> : <Image source={fallbackAvatar} style={st.avatarImage} />}</Pressable>
    </View>
  </View>;
}

function ProfileHero() {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const { width } = useWindowDimensions();
  return <View style={st.hero}>
    <View pointerEvents="none" style={[st.heroOrb, { width: width * .45, right: 12 }]} />
    <View style={st.heroCopy}><Text style={st.heroTitle}>Seu perfil</Text><Text style={st.heroSub}>Gerencie suas preferências{ '\n' }e personalize sua experiência.</Text></View>
    <Image source={newTablet} resizeMode="contain" style={st.heroMascot} accessibilityLabel="New com um tablet" />
  </View>;
}

function ProfileCard({ user, onEdit }: { user: User | null; onEdit: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [failed, setFailed] = useState(false);
  const avatar = firebaseAuth.currentUser?.photoURL;
  const name = user?.display_name?.trim() || firebaseAuth.currentUser?.displayName?.trim() || 'Sua conta';
  return <View style={st.profileCard}>
    <View style={st.profileAvatarWrap}>
      {avatar && !failed ? <Image source={{ uri: avatar }} onError={() => setFailed(true)} style={st.profileAvatar} /> : <Image source={fallbackAvatar} style={st.profileAvatar} />}
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

export function ProfileScreen({ user, onNavigate, onSearch, onLogout }: ProfileScreenProps) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const bottomPadding = useFloatingTabContentInset(true);
  return <SafeAreaView style={st.safe}>
    <StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} />
    <ScrollView contentContainerStyle={[st.scrollContent, { paddingBottom: bottomPadding }]}>
      <ProfileHeader onSearch={onSearch} onAvatar={() => onNavigate('Account')} />
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

export function EditProfileScreen({ user, onBack, onSaved }: { user: User | null; onBack: () => void; onSaved: (user: User) => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [name, setName] = useState(user?.display_name || firebaseAuth.currentUser?.displayName || '');
  const [photoUrl, setPhotoUrl] = useState(firebaseAuth.currentUser?.photoURL || '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const save = async () => {
    const firebaseUser = firebaseAuth.currentUser;
    if (!firebaseUser || !name.trim()) { setMessage('Informe seu nome para continuar.'); return; }
    if (photoUrl && !/^https?:\/\//i.test(photoUrl.trim())) { setMessage('O link da foto deve começar com http:// ou https://.'); return; }
    setBusy(true); setMessage('');
    try {
      await updateProfile(firebaseUser, { displayName: name.trim(), photoURL: photoUrl.trim() || null });
      await getFirebaseIdToken(true);
      const updated = await api.me() as User;
      onSaved(updated); setMessage('Perfil atualizado.');
    } catch { setMessage('Não foi possível salvar as alterações. Verifique sua conexão e tente novamente.'); }
    finally { setBusy(false); }
  };
  return <SecondaryPage title="Editar perfil" onBack={onBack}>
    <Text style={st.formLabel}>Nome completo</Text><TextInput accessibilityLabel="Nome completo" value={name} onChangeText={setName} placeholder="Seu nome" placeholderTextColor={colors.tone('#8192AE', colors.muted)} style={st.input} />
    <Text style={st.formLabel}>E-mail</Text><View style={[st.input, st.readonly]}><Text style={st.readonlyText}>{user?.email || firebaseAuth.currentUser?.email || 'E-mail indisponível'}</Text></View>
    <Text style={st.formLabel}>Foto de perfil</Text><TextInput accessibilityLabel="Link da foto de perfil" value={photoUrl} onChangeText={setPhotoUrl} autoCapitalize="none" keyboardType="url" placeholder="https://…" placeholderTextColor={colors.tone('#8192AE', colors.muted)} style={st.input} /><Text style={st.helper}>Cole o link de uma imagem. Ainda não é possível enviar fotos do aparelho.</Text>
    {!!message && <Text style={st.formMessage}>{message}</Text>}<ActionButton title={busy ? 'Salvando…' : 'Salvar alterações'} disabled={busy} onPress={() => void save()} />
  </SecondaryPage>;
}

export function DailyBriefingSettingsScreen({ onBack, onVoice, onSubscription }: { onBack: () => void; onVoice: () => void; onSubscription: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [prefs, setPrefs] = useState<Preferences | null>(null); const [voices, setVoices] = useState<{ id: string; name: string }[]>([]); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState(''); const [timeError, setTimeError] = useState('');
  const timezone = getDeviceTimezone();
  const [premium, setPremium] = useState(false); const [upsell, setUpsell] = useState(false);
  // The saved time: a new one only says "amanhã" when the user actually changed it.
  const initialTime = useRef('');
  useEffect(() => { if (PREMIUM_OFFERED) api.subscription().then(plan => setPremium(plan.tier === 'premium')).catch(() => undefined); }, []);
  // Extra briefing times are Premium; Básico readers see what Premium offers. The extra times themselves arrive with purchases.
  const addTime = () => premium ? setMessage('Os horários extras do Premium chegam em uma próxima versão.') : setUpsell(true);
  const load = async () => { setLoading(true); setLoadError(''); try { const [p, catalog] = await Promise.all([api.preferences(), api.audioVoices().catch(() => ({ voices: [] }))]); setPrefs({ ...p, timezone }); initialTime.current = p.briefing_time; setVoices(catalog.voices); } catch { setPrefs(null); setLoadError('Não foi possível carregar suas configurações.'); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  // The voice is chosen on its own screen: show it when coming back, and never save this screen's stale copy over it.
  useFocusEffect(useCallback(() => { api.preferences().then(saved => setPrefs(current => current ? { ...current, audio_voice_id: saved.audio_voice_id } : current)).catch(() => undefined); }, []));
  const save = async () => { if (!prefs) return; if (!isValidBriefingTime(prefs.briefing_time)) { setTimeError('Use um horário válido entre 00:00 e 23:59.'); return; } setBusy(true); setMessage(''); setTimeError(''); const updated = { ...prefs, timezone }; const { briefing_time, briefing_size, language, country_scope, audio_enabled } = updated; try { const saved = await api.savePreferences({ briefing_time, timezone, briefing_size, language, country_scope, audio_enabled }); setPrefs({ ...updated, next_briefing: saved?.next_briefing }); setMessage(saved?.next_briefing?.day === 'TOMORROW' && briefing_time !== initialTime.current ? `Configurações salvas. O resumo de hoje já foi feito; o próximo chega amanhã às ${briefing_time}.` : 'Configurações salvas.'); initialTime.current = briefing_time; } catch { setMessage('Não foi possível salvar as configurações.'); } finally { setBusy(false); } };
  const selectedVoice = voices.find(voice => voice.id === prefs?.audio_voice_id)?.name || 'Voz padrão';
  return <SecondaryPage title="Resumo diário" onBack={onBack}>{loading ? <ScreenState kind="loading" title="Carregando configurações" /> : loadError ? <ScreenState kind="error" title="Configurações indisponíveis" message={loadError} onRetry={() => void load()} /> : !prefs ? null : <>
    <Text style={st.pageIntro}>Ajuste quando o resumo chega e como prefere ouvi-lo.</Text>
    <Text style={st.formLabel}>Horário de entrega</Text><View style={st.timeCard}><TimeWheel value={prefs.briefing_time} onChange={briefing_time => { setPrefs({ ...prefs, briefing_time }); setTimeError(''); }} /></View>
    {!!timeError && <Text accessibilityRole="alert" style={st.helper}>{timeError}</Text>}
    {PREMIUM_OFFERED && <Pressable accessibilityRole="button" accessibilityLabel="Adicionar outro horário de resumo. Recurso Premium" onPress={addTime} style={st.addTimeRow}><Icon name="clock" color={colors.primary} size={19} /><Text style={st.addTimeText}>Adicionar outro horário</Text><View style={st.premiumTag}><Text style={st.premiumTagText}>PREMIUM</Text></View></Pressable>}
    <Text style={st.formLabel}>Fuso horário</Text><InfoCard label="Automático pelo aparelho" value={timezone} />
    <Text style={st.formLabel}>Tamanho</Text><View style={st.choiceLine}>{[5, 10, 15].map(size => <Pressable key={size} accessibilityRole="radio" accessibilityState={{ selected: prefs.briefing_size === size }} onPress={() => setPrefs({ ...prefs, briefing_size: size as Preferences['briefing_size'] })} style={[st.sizeChoice, prefs.briefing_size === size && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.briefing_size === size && { color: colors.primary }]}>{size} notícias</Text></Pressable>)}</View>
    <Text style={st.formLabel}>Idioma e cobertura</Text><View style={st.choiceLine}>{['pt-BR', 'en'].map(language => <Pressable key={language} accessibilityRole="radio" accessibilityState={{ selected: prefs.language === language }} onPress={() => setPrefs({ ...prefs, language })} style={[st.sizeChoice, prefs.language === language && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.language === language && { color: colors.primary }]}>{language === 'pt-BR' ? 'Português' : 'English'}</Text></Pressable>)}</View><View style={st.choiceLine}>{(['LOCAL', 'GLOBAL', 'BOTH'] as const).map(scope => <Pressable key={scope} accessibilityRole="radio" accessibilityState={{ selected: prefs.country_scope === scope }} onPress={() => setPrefs({ ...prefs, country_scope: scope })} style={[st.sizeChoice, prefs.country_scope === scope && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.country_scope === scope && { color: colors.primary }]}>{scope === 'BOTH' ? 'Brasil e global' : scope === 'LOCAL' ? 'Brasil' : 'Global'}</Text></Pressable>)}</View>
    <Pressable accessibilityRole="button" accessibilityLabel={`Voz do resumo: ${selectedVoice}`} onPress={onVoice} style={st.voiceRow}><View style={{ flex: 1 }}><Text style={st.menuTitle}>Voz do resumo</Text><Text style={st.menuSubtitle}>{selectedVoice} · Alterar voz</Text></View><Icon name="chevron" color={colors.tone('#64789C', colors.secondary)} /></Pressable>
    <View style={st.audioToggle}><Text style={st.menuTitle}>Áudio do resumo</Text><Switch accessibilityLabel="Áudio do resumo" value={prefs.audio_enabled} onValueChange={audio_enabled => setPrefs({ ...prefs, audio_enabled })} trackColor={{ false: colors.switchTrackOff, true: colors.switchTrackOn }} ios_backgroundColor={colors.switchTrackOff} thumbColor={prefs.audio_enabled ? colors.primary : colors.switchThumbOff} /></View>
    {!!message && <Text accessibilityRole="alert" style={st.formMessage}>{message}</Text>}<ActionButton title={busy ? 'Salvando…' : 'Salvar configurações'} disabled={busy || !isValidBriefingTime(prefs.briefing_time)} onPress={() => void save()} />
    <PremiumSheet feature="briefing_times" visible={upsell} onClose={() => setUpsell(false)} onSeePlans={onSubscription} />
  </>}</SecondaryPage>;
}

export function SecurityPrivacyScreen({ onBack }: { onBack: () => void }) {
  const st = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [message, setMessage] = useState(''); const user = firebaseAuth.currentUser;
  const sendReset = async () => { if (!user?.email) { setMessage('Não há e-mail associado a esta sessão.'); return; } try { await resetPasswordWithFirebase(user.email); setMessage(`Enviamos as instruções para ${user.email}.`); } catch { setMessage('Não foi possível enviar as instruções agora.'); } };
  return <SecondaryPage title="Segurança e privacidade" onBack={onBack}><Text style={st.pageIntro}>Informações da sua autenticação.</Text><InfoCard label="Métodos de acesso" value={user?.providerData.map(provider => provider.providerId).join(', ') || 'Não disponível'} /><InfoCard label="E-mail da conta" value={user?.email || 'Não disponível'} /><ActionButton title="Redefinir senha por e-mail" onPress={() => void sendReset()} />{!!message && <Text style={st.formMessage}>{message}</Text>}<Text style={st.helper}>Controles avançados de privacidade e sessões não estão disponíveis nesta versão.</Text></SecondaryPage>;
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
  safe: { flex: 1, backgroundColor: colors.background } as const, scrollContent: { paddingHorizontal: 18, paddingTop: 5 } as const,
  header: { height: 56, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 3 }, logo: { width: 124, height: 44, marginLeft: -4 }, headerRight: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 }, headerButton: { width: 34, height: 42, alignItems: 'center' as const, justifyContent: 'center' as const }, headerAvatar: { width: 43, height: 43, borderRadius: 24, overflow: 'hidden' as const, backgroundColor: colors.surfaceTint, marginLeft: 2 }, avatarImage: { width: '100%' as const, height: '100%' as const },
  hero: { height: 131, justifyContent: 'center' as const, marginHorizontal: 1, position: 'relative' as const, overflow: 'hidden' as const }, heroOrb: { position: 'absolute' as const, height: 112, bottom: -20, borderRadius: 70, backgroundColor: colors.surfaceTint }, heroCopy: { zIndex: 1, width: '69%' as const, paddingLeft: 3 }, heroTitle: { color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 34, lineHeight: 40, fontWeight: '800' as const, letterSpacing: -.8 }, heroSub: { color: colors.tone('#64799E', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 16, lineHeight: 20, marginTop: 2 }, heroMascot: { position: 'absolute' as const, width: 199, height: 154, right: -10, bottom: -12 },
  profileCard: { minHeight: 139, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingHorizontal: 14, paddingVertical: 13, borderRadius: 25, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.tone('#EFF5FA', colors.divider), marginBottom: 21, shadowColor: colors.tone('#7797BA', colors.shadow.color), shadowOpacity: .08, shadowRadius: 11, shadowOffset: { width: 0, height: 4 }, elevation: 2 }, profileAvatarWrap: { width: 88, height: 88, flexShrink: 0, position: 'relative' as const }, profileAvatar: { width: 88, height: 88, borderRadius: 46, backgroundColor: colors.surfaceTint }, cameraBadge: { position: 'absolute' as const, width: 38, height: 38, borderRadius: 20, right: -3, bottom: -1, backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, shadowColor: colors.tone('#6382A5', colors.shadow.color), shadowOpacity: .15, shadowRadius: 5, elevation: 2 }, profileCopy: { flex: 1, minWidth: 0 }, profileName: { color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800' as const }, profileEmail: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 3 }, memberSince: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, marginTop: 3 }, editButton: { minHeight: 45, minWidth: 105, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 6, paddingHorizontal: 9, borderRadius: 14, borderWidth: 1.2, borderColor: colors.primary, backgroundColor: colors.background }, editText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' as const },
  section: { marginBottom: 16 }, sectionTitle: { color: colors.tone('#111B48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 20, lineHeight: 25, fontWeight: '800' as const, letterSpacing: -.4 }, sectionSubtitle: { color: colors.tone('#687D9F', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, marginTop: 1, marginBottom: 8 }, menuCard: { backgroundColor: colors.surface, borderRadius: 25, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.tone('#F0F5FA', colors.divider), shadowColor: colors.tone('#7797BA', colors.shadow.color), shadowOpacity: .06, shadowRadius: 9, shadowOffset: { width: 0, height: 3 }, elevation: 1 }, menuRow: { minHeight: 78, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingVertical: 9 }, menuRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider }, menuIconBox: { width: 49, height: 49, borderRadius: 14, alignItems: 'center' as const, justifyContent: 'center' as const, flexShrink: 0 }, menuCopy: { flex: 1, minWidth: 0 }, menuTitle: { color: colors.tone('#111B48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const }, menuSubtitle: { color: colors.tone('#6B80A0', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 16, marginTop: 2 },
  secondaryContent: { paddingHorizontal: 18, paddingTop: 7, paddingBottom: 42 }, secondaryHeader: { height: 54, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 16 }, backButton: { width: 42, height: 46, justifyContent: 'center' as const }, backGlyph: { color: colors.tone('#667C9F', colors.secondary), fontSize: 34 }, secondaryTitle: { flex: 1, textAlign: 'center' as const, color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, pageIntro: { color: colors.tone('#657A9D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 21, marginBottom: 16 }, formLabel: { color: colors.tone('#16254A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const, marginTop: 14, marginBottom: 7 }, input: { minHeight: 50, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 15, color: colors.tone('#16254A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15 }, readonly: { justifyContent: 'center' as const }, readonlyText: { color: colors.tone('#7486A4', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15 }, helper: { color: colors.tone('#7688A4', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 17, marginTop: 7 }, timeCard: { borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 15, paddingVertical: 6 }, logout: { minHeight: 50, borderRadius: 25, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, marginTop: 4, marginBottom: 12 }, logoutText: { color: colors.danger, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const }, formMessage: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 12 }, actionButton: { minHeight: 50, borderRadius: 25, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary, marginTop: 18, paddingHorizontal: 20 }, actionButtonText: { color: colors.onPrimary, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const },
  preferenceGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 9 }, topicChoice: { minHeight: 50, minWidth: '47%' as const, maxWidth: '49%' as const, flexGrow: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.tone('#E4EDF7', colors.border), backgroundColor: colors.surface, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 12 }, topicChoiceText: { flex: 1, color: colors.tone('#344866', colors.body), fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '600' as const }, checkMark: { width: 20, color: colors.onPrimary, fontSize: 16, fontWeight: '800' as const }, choiceLine: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 8, marginBottom: 5 }, sizeChoice: { minHeight: 40, borderRadius: 14, borderWidth: 1, borderColor: colors.tone('#E2ECF6', colors.border), backgroundColor: colors.surface, alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 11 }, sizeChoiceActive: { borderColor: colors.primary, backgroundColor: colors.surfaceTint }, sizeChoiceText: { color: colors.tone('#5D7192', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600' as const }, voiceRow: { minHeight: 66, flexDirection: 'row' as const, alignItems: 'center' as const, backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.tone('#E6EEF7', colors.border), paddingHorizontal: 14, marginTop: 14 }, audioToggle: { minHeight: 57, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 4, marginTop: 8 },
  addTimeRow: { minHeight: 48, marginTop: 10, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 }, addTimeText: { flex: 1, color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const }, premiumTag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: colors.tone('#FFEFD2', '#3B2A10') }, premiumTagText: { color: colors.tone('#8A5200', '#FFC56B'), fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800' as const, letterSpacing: 1 },
  infoCard: { backgroundColor: colors.surface, borderRadius: 17, padding: 15, marginBottom: 10, borderWidth: 1, borderColor: colors.divider }, infoLabel: { color: colors.tone('#7184A2', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 12 }, infoValue: { color: colors.tone('#15234A', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600' as const, marginTop: 4 }, infoPanel: { backgroundColor: colors.surface, padding: 18, borderRadius: 20, borderWidth: 1, borderColor: colors.divider }, infoText: { color: colors.tone('#63799B', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 22 },
});
