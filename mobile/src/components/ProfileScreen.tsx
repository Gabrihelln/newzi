import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Modal, Pressable, SafeAreaView, ScrollView, StatusBar, Switch, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { firebaseAuth } from '../services/firebaseAuth';
import { updateProfile } from '@react-native-firebase/auth';
import { resetPasswordWithFirebase, getFirebaseIdToken } from '../services/firebaseAuth';
import { saveUserProfile } from '../services/firestoreUser';
import { api } from '../api/client';
import { colors, typography } from '../theme';
import { Icon } from './Icon';
import { useFloatingTabContentInset } from '../navigation/floatingTabLayout';
import type { ClientConfig, Preferences, User } from '../types/api';
import { ScreenState } from './ScreenPrimitives';
import { getDeviceTimezone } from '../config/timezone';
import { isValidBriefingTime } from '../config/time';
import { notifyContentChanged } from '../services/contentRevision';

const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const newTablet = require('../../assets/onboarding/new-tablet.png');
const fallbackAvatar = require('../../assets/onboarding/new-waving.png');
type ProfileRoute = 'EditProfile' | 'ContentPreferences' | 'NotificationSettings' | 'DailyBriefing' | 'SecurityPrivacy' | 'Account' | 'Subscription';
type ProfileScreenProps = { user: User | null; onNavigate: (route: ProfileRoute) => void; onSearch: () => void };

function memberSince(user?: User | null) {
  const value = firebaseAuth.currentUser?.metadata?.creationTime || user?.created_at;
  if (!value) return 'Data de cadastro indisponível';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Data de cadastro indisponível' : `Membro desde ${new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(date)}`;
}

function ProfileHeader({ onSearch, onAvatar }: { onSearch: () => void; onAvatar: () => void }) {
  const [failed, setFailed] = useState(false);
  const avatar = firebaseAuth.currentUser?.photoURL;
  return <View style={st.header}>
    <Image source={logo} resizeMode="contain" accessibilityLabel="NEWZI" style={st.logo} />
    <View style={st.headerRight}>
      <Pressable accessibilityRole="button" accessibilityLabel="Buscar notícias" onPress={onSearch} style={st.headerButton}><Icon name="search" color="#12264D" size={25} /></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir dados pessoais" onPress={onAvatar} style={st.headerAvatar}>{avatar && !failed ? <Image source={{ uri: avatar }} onError={() => setFailed(true)} style={st.avatarImage} /> : <Image source={fallbackAvatar} style={st.avatarImage} />}</Pressable>
    </View>
  </View>;
}

function ProfileHero() {
  const { width } = useWindowDimensions();
  return <View style={st.hero}>
    <View pointerEvents="none" style={[st.heroOrb, { width: width * .45, right: 12 }]} />
    <View style={st.heroCopy}><Text style={st.heroTitle}>Seu perfil</Text><Text style={st.heroSub}>Gerencie suas preferências{ '\n' }e personalize sua experiência.</Text></View>
    <Image source={newTablet} resizeMode="contain" style={st.heroMascot} accessibilityLabel="New com um tablet" />
  </View>;
}

function ProfileCard({ user, onEdit }: { user: User | null; onEdit: () => void }) {
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

function ProfileMenuRow({ title, subtitle, icon, tint, background, onPress, last = false }: { title: string; subtitle: string; icon: 'settings' | 'bell' | 'sun' | 'lock' | 'profile' | 'card'; tint: string; background: string; onPress: () => void; last?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`${title}. ${subtitle}`} onPress={onPress} style={[st.menuRow, !last && st.menuRowBorder]}>
    <View style={[st.menuIconBox, { backgroundColor: background }]}><Icon name={icon} color={tint} size={25} /></View>
    <View style={st.menuCopy}><Text style={st.menuTitle}>{title}</Text><Text numberOfLines={2} style={st.menuSubtitle}>{subtitle}</Text></View>
    <Icon name="chevron" color="#64789C" size={20} />
  </Pressable>;
}

function ProfileSection({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <View style={st.section}><Text style={st.sectionTitle}>{title}</Text><Text style={st.sectionSubtitle}>{subtitle}</Text><View style={st.menuCard}>{children}</View></View>;
}

export function ProfileScreen({ user, onNavigate, onSearch }: ProfileScreenProps) {
  const bottomPadding = useFloatingTabContentInset(true);
  return <SafeAreaView style={st.safe}>
    <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
    <ScrollView contentContainerStyle={[st.scrollContent, { paddingBottom: bottomPadding }]}>
      <ProfileHeader onSearch={onSearch} onAvatar={() => onNavigate('Account')} />
      <ProfileHero />
      <ProfileCard user={user} onEdit={() => onNavigate('EditProfile')} />
      <ProfileSection title="Meu Newzi" subtitle="Personalize sua experiência e receba conteúdos mais relevantes.">
        <ProfileMenuRow title="Preferências de conteúdo" subtitle="Escolha os assuntos que mais te interessam" icon="settings" tint="#087CF0" background="#E4F1FF" onPress={() => onNavigate('ContentPreferences')} />
        <ProfileMenuRow title="Notificações" subtitle="Gerencie seus alertas e lembretes" icon="bell" tint="#8548E6" background="#F0E8FF" onPress={() => onNavigate('NotificationSettings')} />
        <ProfileMenuRow title="Briefing diário" subtitle="Configure horário, voz e formato do seu briefing" icon="sun" tint="#F39711" background="#FFF1D9" onPress={() => onNavigate('DailyBriefing')} last />
      </ProfileSection>
      <ProfileSection title="Minha conta" subtitle="Segurança, privacidade e dados da sua conta.">
        <ProfileMenuRow title="Segurança e privacidade" subtitle="Senha, autenticação e dados" icon="lock" tint="#10A867" background="#E4F8EF" onPress={() => onNavigate('SecurityPrivacy')} />
        <ProfileMenuRow title="Dados pessoais" subtitle="Suas informações e conta" icon="profile" tint="#087CF0" background="#E4F1FF" onPress={() => onNavigate('Account')} />
        <ProfileMenuRow title="Assinatura e plano" subtitle="Gerencie seu plano Newzi" icon="card" tint="#8548E6" background="#F0E8FF" onPress={() => onNavigate('Subscription')} last />
      </ProfileSection>
    </ScrollView>
  </SafeAreaView>;
}

export function EditProfileScreen({ user, onBack, onSaved }: { user: User | null; onBack: () => void; onSaved: (user: User) => void }) {
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
      await saveUserProfile(firebaseUser, name.trim()).catch(() => undefined);
      await getFirebaseIdToken(true);
      const updated = await api.me() as User;
      onSaved(updated); setMessage('Perfil atualizado.');
    } catch { setMessage('Não foi possível salvar as alterações. Verifique sua conexão e tente novamente.'); }
    finally { setBusy(false); }
  };
  return <SecondaryPage title="Editar perfil" onBack={onBack}>
    <Text style={st.formLabel}>Nome completo</Text><TextInput accessibilityLabel="Nome completo" value={name} onChangeText={setName} placeholder="Seu nome" placeholderTextColor="#8192AE" style={st.input} />
    <Text style={st.formLabel}>E-mail</Text><View style={[st.input, st.readonly]}><Text style={st.readonlyText}>{user?.email || firebaseAuth.currentUser?.email || 'E-mail indisponível'}</Text></View>
    <Text style={st.formLabel}>Foto de perfil</Text><TextInput accessibilityLabel="Link da foto de perfil" value={photoUrl} onChangeText={setPhotoUrl} autoCapitalize="none" keyboardType="url" placeholder="https://…" placeholderTextColor="#8192AE" style={st.input} /><Text style={st.helper}>A foto é sincronizada pelo Firebase Auth. O envio de imagens do aparelho não está configurado neste app.</Text>
    {!!message && <Text style={st.formMessage}>{message}</Text>}<ActionButton title={busy ? 'Salvando…' : 'Salvar alterações'} disabled={busy} onPress={() => void save()} />
  </SecondaryPage>;
}

function normalizeTopicSearch(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').trim();
}

/** Canonical description of what drives briefing content, used to tell whether a save requires a new briefing. */
const contentProfileKey = (prefs: Pick<Preferences, 'topics' | 'content_scope'>) => prefs.content_scope === 'all' ? 'all' : [...prefs.topics].sort().join('|');

export function ContentPreferencesScreen({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [savedProfile, setSavedProfile] = useState('');
  const [savedDialog, setSavedDialog] = useState<null | { regenerating: boolean }>(null);
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const load = async () => { setLoading(true); setLoadError(''); try { const [p, c] = await Promise.all([api.preferences(), api.config()]); const loaded = { ...p, content_scope: p.content_scope || 'selected' }; setPrefs(loaded); setSavedProfile(contentProfileKey(loaded)); setConfig(c); } catch { setPrefs(null); setConfig(null); setLoadError('Não foi possível carregar suas preferências.'); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  const topics = useMemo(() => (config?.topics || []).filter(topic => topic.enabled !== false).slice().sort((a, b) => (a.order || 0) - (b.order || 0)), [config]);
  const topicsByCode = useMemo(() => new Map(topics.map(topic => [topic.code, topic])), [topics]);
  const childrenByParent = useMemo(() => {
    const children = new Map<string, typeof topics>();
    for (const topic of topics) {
      if (!topic.parent_id) continue;
      const siblings = children.get(topic.parent_id) || [];
      siblings.push(topic);
      children.set(topic.parent_id, siblings);
    }
    return children;
  }, [topics]);
  const roots = topics.filter(topic => !topic.parent_id);
  const selectedTopics = prefs?.topics || [];
  const allContent = prefs?.content_scope === 'all';
  const normalizedQuery = normalizeTopicSearch(query);
  const descendantsByCode = useMemo(() => {
    const descendants = new Map<string, string[]>();
    for (const topic of topics) for (const ancestor of (topic.path || []).slice(0, -1)) descendants.set(ancestor, [...(descendants.get(ancestor) || []), topic.code]);
    return descendants;
  }, [topics]);
  const isCovered = (code: string) => allContent || selectedTopics.includes(code) || (topicsByCode.get(code)?.path || []).slice(0, -1).some(ancestor => selectedTopics.includes(ancestor));
  const subjectCount = topics.length - roots.length;
  // Exact name/alias matches first ("IA" → Inteligência Artificial), then word prefixes, then substrings.
  const searchResults = normalizedQuery ? topics.map(topic => {
    const parentNames = (topic.path || []).slice(0, -1).map(code => topicsByCode.get(code)?.name || '');
    const primary = [topic.name, topic.code, ...(topic.aliases || [])].map(normalizeTopicSearch);
    const secondary = [topic.description || '', ...parentNames].map(normalizeTopicSearch);
    const words = (value: string) => value.split(/[\s_-]+/);
    const rank = primary.some(value => value === normalizedQuery) ? 0
      : primary.some(value => words(value).some(word => word.startsWith(normalizedQuery))) ? 1
      : normalizedQuery.length > 2 && primary.some(value => value.includes(normalizedQuery)) ? 2
      : normalizedQuery.length > 2 && secondary.some(value => value.includes(normalizedQuery)) ? 3 : -1;
    return { topic, rank };
  }).filter(result => result.rank >= 0).sort((a, b) => a.rank - b.rank || (a.topic.depth || 0) - (b.topic.depth || 0) || (a.topic.order || 0) - (b.topic.order || 0)).map(result => result.topic) : [];
  const toggleTopic = (code: string) => setPrefs(current => current ? { ...current, topics: current.topics.includes(code) ? current.topics.filter(item => item !== code) : [...current.topics, code] } : current);
  const toggleExpanded = (code: string) => setExpanded(current => { const next = new Set(current); if (next.has(code)) next.delete(code); else next.add(code); return next; });
  const expandableCodes = topics.filter(topic => (childrenByParent.get(topic.code) || []).length > 0).map(topic => topic.code);
  const allExpanded = expandableCodes.length > 0 && expandableCodes.every(code => expanded.has(code));
  const domainSummary = (root: typeof topics[number]) => {
    const descendants = descendantsByCode.get(root.code) || [];
    if (!descendants.length) return root.description || 'Assunto';
    if (allContent || selectedTopics.includes(root.code)) return `Todos os ${descendants.length} assuntos incluídos`;
    const covered = descendants.filter(isCovered).length;
    return covered ? `${covered} de ${descendants.length} assuntos selecionados` : `${descendants.length} assuntos`;
  };
  const topicPath = (topic: typeof topics[number]) => (topic.path || [topic.code]).map(code => topicsByCode.get(code)?.name || code).join(' › ');
  const renderTopic = (topic: typeof topics[number], depth = 0, showPath = false): React.ReactNode => {
    const selected = selectedTopics.includes(topic.code);
    const ancestorIds = (topic.path || []).slice(0, -1);
    const inheritedBy = ancestorIds.find(code => selectedTopics.includes(code));
    const checked = allContent || selected || Boolean(inheritedBy);
    const disabled = allContent || Boolean(inheritedBy);
    const children = childrenByParent.get(topic.code) || [];
    const isExpanded = expanded.has(topic.code) || Boolean(normalizedQuery);
    const tint = ['#087CF0', '#8548E6', '#10A867', '#F39711', '#E83E54'][Math.max(0, depth) % 5];
    return <View key={topic.code} style={{ marginLeft: Math.min(depth * 12, 36), borderBottomWidth: 1, borderBottomColor: '#EEF3F8' }}>
      <View style={{ minHeight: showPath ? 72 : 58, flexDirection: 'row', alignItems: 'center', paddingVertical: 8, paddingRight: 8 }}>
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked, disabled }} onPress={() => !disabled && toggleTopic(topic.code)} style={{ flex: 1, minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 10, opacity: disabled && !allContent ? .72 : 1 }}>
          <View style={{ width: 23, height: 23, borderRadius: 7, borderWidth: 1.5, borderColor: checked ? tint : '#C9D6E6', backgroundColor: checked ? tint : '#FFFFFF', alignItems: 'center', justifyContent: 'center' }}>{checked && <Icon name="check" color="#FFFFFF" size={15} />}</View>
          <View style={{ flex: 1 }}><Text style={{ color: '#17264B', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' }}>{topic.name}</Text>{showPath ? <Text numberOfLines={1} style={{ color: '#788AA6', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }}>{topicPath(topic)}</Text> : inheritedBy ? <Text style={{ color: '#7184A2', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }}>Incluído por {topicsByCode.get(inheritedBy)?.name || inheritedBy}</Text> : topic.description ? <Text numberOfLines={1} style={{ color: '#7184A2', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }}>{topic.description}</Text> : null}</View>
        </Pressable>
        {children.length > 0 && !showPath && <Pressable accessibilityRole="button" accessibilityLabel={`${isExpanded ? 'Recolher' : 'Expandir'} ${topic.name}`} onPress={() => toggleExpanded(topic.code)} style={{ minWidth: 48, minHeight: 44, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' }}>{isExpanded ? '−' : `+${children.length}`}</Text></Pressable>}
      </View>
      {isExpanded && !showPath && children.map(child => renderTopic(child, depth + 1))}
    </View>;
  };
  const save = async () => {
    if (!prefs) return;
    if (prefs.content_scope !== 'all' && prefs.topics.length === 0) { setMessage('Selecione ao menos um assunto ou ative “Acompanhar tudo”.'); return; }
    setBusy(true); setMessage('');
    // A selected domain already includes its subjects; keep the saved list canonical.
    const topicsToSave = prefs.topics.filter(code => !(topicsByCode.get(code)?.path || []).slice(0, -1).some(ancestor => prefs.topics.includes(ancestor)));
    try { const updated = { ...prefs, topics: topicsToSave.length ? topicsToSave : prefs.topics, content_scope: prefs.content_scope || 'selected' }; const saved = await api.savePreferences(updated); const next = { ...updated, ...saved }; setPrefs(next);
      const profile = contentProfileKey(next); const regenerating = profile !== savedProfile; setSavedProfile(profile);
      notifyContentChanged(); setSavedDialog({ regenerating }); }
    catch { setMessage('Não foi possível salvar as preferências.'); }
    finally { setBusy(false); }
  };
  return <SecondaryPage title="Preferências de conteúdo" onBack={onBack}>{loading ? <ScreenState kind="loading" title="Carregando preferências" /> : loadError ? <ScreenState kind="error" title="Preferências indisponíveis" message={loadError} onRetry={() => void load()} /> : !prefs || !config ? null : <>
    <Text style={st.pageIntro}>Escolha os assuntos que você quer acompanhar.</Text>
    <Text style={[st.helper, { marginTop: -8, marginBottom: 12 }]}>{roots.length} domínios · {subjectCount} assuntos{allContent ? ' · todos incluídos' : selectedTopics.length ? ` · ${topics.filter(topic => isCovered(topic.code)).length} incluídos` : ''}</Text>
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 15, marginBottom: 14, borderRadius: 18, borderWidth: 1, borderColor: allContent ? '#9BC8FF' : '#E4EDF7', backgroundColor: allContent ? '#EEF6FF' : '#FFFFFF' }}>
      <View style={{ flex: 1, paddingRight: 12 }}><Text style={{ color: '#15234A', fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800' }}>Quero acompanhar tudo</Text><Text style={{ color: '#6A7E9E', fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 17, marginTop: 3 }}>Marca todos os domínios e todos os assuntos de cada um.</Text></View>
      <Switch accessibilityLabel="Quero acompanhar tudo" value={allContent} onValueChange={value => setPrefs(current => current ? { ...current, content_scope: value ? 'all' : 'selected' } : current)} trackColor={{ false: '#CBD7E7', true: '#9DC8FF' }} thumbColor={allContent ? colors.primary : '#FFFFFF'} />
    </View>
    {!allContent && selectedTopics.length > 0 && <View style={{ marginBottom: 14 }}>
      <Text style={[st.helper, { marginBottom: 8 }]}>Selecionados ({selectedTopics.length}) · toque para remover</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{selectedTopics.map(code => {
        const topic = topicsByCode.get(code);
        const parent = topic?.parent_id ? topicsByCode.get(topic.parent_id)?.name : null;
        return <Pressable key={code} accessibilityRole="button" accessibilityLabel={`Remover ${topic?.name || code}`} onPress={() => toggleTopic(code)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 34, paddingLeft: 12, paddingRight: 8, borderRadius: 17, backgroundColor: '#E4F1FF', borderWidth: 1, borderColor: '#B7D6FF' }}>
          <Text style={{ color: '#0B4FA8', fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' }}>{topic?.name || code}{parent ? <Text style={{ fontWeight: '500', color: '#4D73A8' }}>{` · ${parent}`}</Text> : null}</Text>
          <Icon name="close" color="#0B4FA8" size={14} />
        </Pressable>;
      })}</View>
    </View>}
    <TextInput accessibilityLabel="Buscar assuntos" value={query} onChangeText={setQuery} placeholder="Buscar assunto, tema ou alias" placeholderTextColor="#8192AE" autoCorrect={false} style={[st.input, { marginBottom: 12 }]} />
    {allContent && <Text style={[st.helper, { marginBottom: 10 }]}>Sua seleção ficará salva caso você volte a acompanhar assuntos específicos.</Text>}
    {!normalizedQuery && expandableCodes.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel={allExpanded ? 'Recolher todos os domínios' : 'Expandir todos os domínios'} onPress={() => setExpanded(allExpanded ? new Set() : new Set(expandableCodes))} style={{ alignSelf: 'flex-end', minHeight: 36, justifyContent: 'center', paddingHorizontal: 4, marginBottom: 6 }}><Text style={{ color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' }}>{allExpanded ? 'Recolher todos' : 'Expandir todos'}</Text></Pressable>}
    {normalizedQuery ? searchResults.length ? <View style={{ backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E6EEF7', paddingHorizontal: 12 }}>{searchResults.map(topic => renderTopic(topic, 0, true))}</View> : <Text style={st.helper}>Nenhum assunto encontrado.</Text> : <View style={{ gap: 10 }}>{roots.map(root => {
      const descendants = (childrenByParent.get(root.code) || []).length;
      const directSelected = selectedTopics.includes(root.code);
      const isExpanded = expanded.has(root.code);
      return <View key={root.code} style={{ backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: directSelected ? '#B7D6FF' : '#E6EEF7', paddingHorizontal: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: allContent || directSelected, disabled: allContent }} onPress={() => !allContent && toggleTopic(root.code)} style={{ flex: 1, minHeight: 60, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 24, height: 24, borderRadius: 8, borderWidth: 1.5, borderColor: allContent || directSelected ? colors.primary : '#C9D6E6', backgroundColor: allContent || directSelected ? colors.primary : '#FFFFFF', alignItems: 'center', justifyContent: 'center' }}>{(allContent || directSelected) && <Icon name="check" color="#FFFFFF" size={15} />}</View><View style={{ flex: 1 }}><Text style={{ color: '#17264B', fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800' }}>{root.name}</Text><Text style={{ color: '#7184A2', fontFamily: typography.fontFamily.ui, fontSize: 11, marginTop: 2 }}>{domainSummary(root)}</Text></View>
          </Pressable>
          {descendants > 0 && <Pressable accessibilityRole="button" accessibilityLabel={`${isExpanded ? 'Recolher' : 'Expandir'} ${root.name}`} onPress={() => toggleExpanded(root.code)} style={{ minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' }}>{isExpanded ? '−' : `+${descendants}`}</Text></Pressable>}
        </View>
        {isExpanded && (childrenByParent.get(root.code) || []).map(child => renderTopic(child, 1))}
      </View>;
    })}</View>}
    {!!message && <Text accessibilityRole="alert" style={st.formMessage}>{message}</Text>}
    <ActionButton title={busy ? 'Salvando…' : 'Salvar preferências'} disabled={busy} onPress={() => void save()} />
    <Modal visible={Boolean(savedDialog)} transparent animationType="fade" onRequestClose={() => { setSavedDialog(null); onDone(); }}>
      <View style={st.dialogBackdrop}>
        <View accessibilityViewIsModal style={st.dialogCard}>
          <View style={st.dialogIcon}><Icon name="checkCircle" color={colors.primary} size={30} /></View>
          <Text style={st.dialogTitle}>Preferências salvas</Text>
          <Text style={st.dialogBody}>{savedDialog?.regenerating
            ? 'Estamos preparando um novo briefing em áudio com as suas novas preferências. Normalmente leva menos de um minuto — você será notificado quando ele estiver pronto para ouvir.'
            : 'Sua tela inicial e o Explorar já foram atualizados com as suas preferências.'}</Text>
          <ActionButton title="Ir para o início" onPress={() => { setSavedDialog(null); onDone(); }} />
          <Pressable accessibilityRole="button" onPress={() => setSavedDialog(null)} style={st.dialogSecondary}><Text style={st.dialogSecondaryText}>Continuar editando</Text></Pressable>
        </View>
      </View>
    </Modal>
  </>}</SecondaryPage>;
}

export function DailyBriefingSettingsScreen({ onBack, onVoice }: { onBack: () => void; onVoice: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null); const [voices, setVoices] = useState<{ id: string; name: string }[]>([]); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState(''); const [timeError, setTimeError] = useState('');
  const timezone = getDeviceTimezone();
  const load = async () => { setLoading(true); setLoadError(''); try { const [p, catalog] = await Promise.all([api.preferences(), api.audioVoices().catch(() => ({ voices: [] }))]); setPrefs({ ...p, timezone }); setVoices(catalog.voices); } catch { setPrefs(null); setLoadError('Não foi possível carregar suas configurações.'); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  const save = async () => { if (!prefs) return; if (!isValidBriefingTime(prefs.briefing_time)) { setTimeError('Use um horário válido entre 00:00 e 23:59.'); return; } setBusy(true); setMessage(''); setTimeError(''); const updated = { ...prefs, timezone }; try { await api.savePreferences(updated); setPrefs(updated); setMessage('Configurações salvas.'); } catch { setMessage('Não foi possível salvar as configurações.'); } finally { setBusy(false); } };
  const selectedVoice = voices.find(voice => voice.id === prefs?.audio_voice_id)?.name || 'Voz padrão';
  return <SecondaryPage title="Briefing diário" onBack={onBack}>{loading ? <ScreenState kind="loading" title="Carregando configurações" /> : loadError ? <ScreenState kind="error" title="Configurações indisponíveis" message={loadError} onRetry={() => void load()} /> : !prefs ? null : <>
    <Text style={st.pageIntro}>Ajuste quando o briefing chega e como prefere ouvi-lo.</Text>
    <Text style={st.formLabel}>Horário de entrega</Text><TextInput accessibilityLabel="Horário de entrega" value={prefs.briefing_time} onChangeText={briefing_time => { setPrefs({ ...prefs, briefing_time }); setTimeError(''); }} keyboardType="numbers-and-punctuation" maxLength={5} placeholder="06:30" style={st.input} />
    {!isValidBriefingTime(prefs.briefing_time) && <Text accessibilityRole="alert" style={st.helper}>{timeError || 'Digite o horário no formato HH:mm, entre 00:00 e 23:59.'}</Text>}
    <Text style={st.formLabel}>Fuso horário</Text><InfoCard label="Automático pelo aparelho" value={timezone} />
    <Text style={st.formLabel}>Tamanho</Text><View style={st.choiceLine}>{[5, 10, 15].map(size => <Pressable key={size} accessibilityRole="radio" accessibilityState={{ selected: prefs.briefing_size === size }} onPress={() => setPrefs({ ...prefs, briefing_size: size as Preferences['briefing_size'] })} style={[st.sizeChoice, prefs.briefing_size === size && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.briefing_size === size && { color: colors.primary }]}>{size} notícias</Text></Pressable>)}</View>
    <Text style={st.formLabel}>Idioma e cobertura</Text><View style={st.choiceLine}>{['pt-BR', 'en'].map(language => <Pressable key={language} accessibilityRole="radio" accessibilityState={{ selected: prefs.language === language }} onPress={() => setPrefs({ ...prefs, language })} style={[st.sizeChoice, prefs.language === language && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.language === language && { color: colors.primary }]}>{language === 'pt-BR' ? 'Português' : 'English'}</Text></Pressable>)}</View><View style={st.choiceLine}>{(['LOCAL', 'GLOBAL', 'BOTH'] as const).map(scope => <Pressable key={scope} accessibilityRole="radio" accessibilityState={{ selected: prefs.country_scope === scope }} onPress={() => setPrefs({ ...prefs, country_scope: scope })} style={[st.sizeChoice, prefs.country_scope === scope && st.sizeChoiceActive]}><Text style={[st.sizeChoiceText, prefs.country_scope === scope && { color: colors.primary }]}>{scope === 'BOTH' ? 'Brasil e global' : scope === 'LOCAL' ? 'Brasil' : 'Global'}</Text></Pressable>)}</View>
    <Pressable accessibilityRole="button" accessibilityLabel={`Voz do briefing: ${selectedVoice}`} onPress={onVoice} style={st.voiceRow}><View style={{ flex: 1 }}><Text style={st.menuTitle}>Voz do briefing</Text><Text style={st.menuSubtitle}>{selectedVoice} · Alterar voz</Text></View><Icon name="chevron" color="#64789C" /></Pressable>
    <View style={st.audioToggle}><Text style={st.menuTitle}>Áudio do briefing</Text><Switch value={prefs.audio_enabled} onValueChange={audio_enabled => setPrefs({ ...prefs, audio_enabled })} trackColor={{ false: '#CBD7E7', true: '#9DC8FF' }} thumbColor={prefs.audio_enabled ? colors.primary : '#FFFFFF'} /></View>
    {!!message && <Text accessibilityRole="alert" style={st.formMessage}>{message}</Text>}<ActionButton title={busy ? 'Salvando…' : 'Salvar configurações'} disabled={busy || !isValidBriefingTime(prefs.briefing_time)} onPress={() => void save()} />
  </>}</SecondaryPage>;
}

export function SecurityPrivacyScreen({ onBack }: { onBack: () => void }) {
  const [message, setMessage] = useState(''); const user = firebaseAuth.currentUser;
  const sendReset = async () => { if (!user?.email) { setMessage('Não há e-mail associado a esta sessão.'); return; } try { await resetPasswordWithFirebase(user.email); setMessage(`Enviamos as instruções para ${user.email}.`); } catch { setMessage('Não foi possível enviar as instruções agora.'); } };
  return <SecondaryPage title="Segurança e privacidade" onBack={onBack}><Text style={st.pageIntro}>Informações da sua autenticação.</Text><InfoCard label="Métodos de acesso" value={user?.providerData.map(provider => provider.providerId).join(', ') || 'Não disponível'} /><InfoCard label="E-mail da conta" value={user?.email || 'Não disponível'} /><ActionButton title="Redefinir senha por e-mail" onPress={() => void sendReset()} />{!!message && <Text style={st.formMessage}>{message}</Text>}<Text style={st.helper}>Controles avançados de privacidade e sessões não estão disponíveis nesta versão.</Text></SecondaryPage>;
}

export function ProfileInfoScreen({ title, message, onBack }: { title: string; message: string; onBack: () => void }) {
  return <SecondaryPage title={title} onBack={onBack}><View style={st.infoPanel}><Text style={st.infoText}>{message}</Text></View></SecondaryPage>;
}

function SecondaryPage({ title, onBack, children }: { title: string; onBack: () => void; children: React.ReactNode }) {
  return <SafeAreaView style={st.safe}><StatusBar barStyle="dark-content" backgroundColor={colors.background} /><ScrollView contentContainerStyle={st.secondaryContent}><View style={st.secondaryHeader}><Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={st.backButton}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View></Pressable><Text numberOfLines={1} style={st.secondaryTitle}>{title}</Text><View style={{ width: 42 }} /></View>{children}</ScrollView></SafeAreaView>;
}
function ActionButton({ title, onPress, disabled = false }: { title: string; onPress: () => void; disabled?: boolean }) { return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[st.actionButton, disabled && { opacity: .6 }]}><Text style={st.actionButtonText}>{title}</Text></Pressable>; }
function InfoCard({ label, value }: { label: string; value: string }) { return <View style={st.infoCard}><Text style={st.infoLabel}>{label}</Text><Text style={st.infoValue}>{value}</Text></View>; }

const st = {
  dialogBackdrop: { flex: 1, backgroundColor: '#0A1E4466', alignItems: 'center' as const, justifyContent: 'center' as const, padding: 24 }, dialogCard: { width: '100%' as const, maxWidth: 380, borderRadius: 24, backgroundColor: '#FFFFFF', padding: 22, alignItems: 'stretch' as const }, dialogIcon: { alignSelf: 'center' as const, width: 56, height: 56, borderRadius: 28, backgroundColor: '#E4F1FF', alignItems: 'center' as const, justifyContent: 'center' as const, marginBottom: 12 }, dialogTitle: { textAlign: 'center' as const, color: '#111B48', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, dialogBody: { textAlign: 'center' as const, color: '#5E7296', fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20, marginTop: 8 }, dialogSecondary: { minHeight: 44, alignItems: 'center' as const, justifyContent: 'center' as const, marginTop: 6 }, dialogSecondaryText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const },
  safe: { flex: 1, backgroundColor: colors.background } as const, scrollContent: { paddingHorizontal: 18, paddingTop: 5 } as const,
  header: { height: 56, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 3 }, logo: { width: 124, height: 44, marginLeft: -4 }, headerRight: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 }, headerButton: { width: 34, height: 42, alignItems: 'center' as const, justifyContent: 'center' as const }, headerAvatar: { width: 43, height: 43, borderRadius: 24, overflow: 'hidden' as const, backgroundColor: '#E5F0FB', marginLeft: 2 }, avatarImage: { width: '100%' as const, height: '100%' as const },
  hero: { height: 131, justifyContent: 'center' as const, marginHorizontal: 1, position: 'relative' as const, overflow: 'hidden' as const }, heroOrb: { position: 'absolute' as const, height: 112, bottom: -20, borderRadius: 70, backgroundColor: '#EAF5FF' }, heroCopy: { zIndex: 1, width: '69%' as const, paddingLeft: 3 }, heroTitle: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 34, lineHeight: 40, fontWeight: '800' as const, letterSpacing: -.8 }, heroSub: { color: '#64799E', fontFamily: typography.fontFamily.ui, fontSize: 16, lineHeight: 20, marginTop: 2 }, heroMascot: { position: 'absolute' as const, width: 199, height: 154, right: -10, bottom: -12 },
  profileCard: { minHeight: 139, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingHorizontal: 14, paddingVertical: 13, borderRadius: 25, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#EFF5FA', marginBottom: 21, shadowColor: '#7797BA', shadowOpacity: .08, shadowRadius: 11, shadowOffset: { width: 0, height: 4 }, elevation: 2 }, profileAvatarWrap: { width: 88, height: 88, flexShrink: 0, position: 'relative' as const }, profileAvatar: { width: 88, height: 88, borderRadius: 46, backgroundColor: '#E5F0FB' }, cameraBadge: { position: 'absolute' as const, width: 38, height: 38, borderRadius: 20, right: -3, bottom: -1, backgroundColor: '#FFFFFF', alignItems: 'center' as const, justifyContent: 'center' as const, shadowColor: '#6382A5', shadowOpacity: .15, shadowRadius: 5, elevation: 2 }, profileCopy: { flex: 1, minWidth: 0 }, profileName: { color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 21, fontWeight: '800' as const }, profileEmail: { color: '#657A9D', fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 3 }, memberSince: { color: '#657A9D', fontFamily: typography.fontFamily.ui, fontSize: 12, marginTop: 3 }, editButton: { minHeight: 45, minWidth: 105, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 6, paddingHorizontal: 9, borderRadius: 14, borderWidth: 1.2, borderColor: colors.primary, backgroundColor: '#F8FBFF' }, editText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700' as const },
  section: { marginBottom: 16 }, sectionTitle: { color: '#111B48', fontFamily: typography.fontFamily.ui, fontSize: 20, lineHeight: 25, fontWeight: '800' as const, letterSpacing: -.4 }, sectionSubtitle: { color: '#687D9F', fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, marginTop: 1, marginBottom: 8 }, menuCard: { backgroundColor: '#FFFFFF', borderRadius: 25, paddingHorizontal: 12, borderWidth: 1, borderColor: '#F0F5FA', shadowColor: '#7797BA', shadowOpacity: .06, shadowRadius: 9, shadowOffset: { width: 0, height: 3 }, elevation: 1 }, menuRow: { minHeight: 78, flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12, paddingVertical: 9 }, menuRowBorder: { borderBottomWidth: 1, borderBottomColor: '#E9F0F8' }, menuIconBox: { width: 49, height: 49, borderRadius: 14, alignItems: 'center' as const, justifyContent: 'center' as const, flexShrink: 0 }, menuCopy: { flex: 1, minWidth: 0 }, menuTitle: { color: '#111B48', fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const }, menuSubtitle: { color: '#6B80A0', fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 16, marginTop: 2 },
  secondaryContent: { paddingHorizontal: 18, paddingTop: 7, paddingBottom: 42 }, secondaryHeader: { height: 54, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 16 }, backButton: { width: 42, height: 46, justifyContent: 'center' as const }, backGlyph: { color: '#667C9F', fontSize: 34 }, secondaryTitle: { flex: 1, textAlign: 'center' as const, color: '#101A48', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800' as const }, pageIntro: { color: '#657A9D', fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 21, marginBottom: 16 }, formLabel: { color: '#16254A', fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700' as const, marginTop: 14, marginBottom: 7 }, input: { minHeight: 50, borderRadius: 16, borderWidth: 1, borderColor: '#DDE9F6', backgroundColor: '#FFFFFF', paddingHorizontal: 15, color: '#16254A', fontFamily: typography.fontFamily.ui, fontSize: 15 }, readonly: { justifyContent: 'center' as const }, readonlyText: { color: '#7486A4', fontFamily: typography.fontFamily.ui, fontSize: 15 }, helper: { color: '#7688A4', fontFamily: typography.fontFamily.ui, fontSize: 12, lineHeight: 17, marginTop: 7 }, formMessage: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 12 }, actionButton: { minHeight: 50, borderRadius: 25, alignItems: 'center' as const, justifyContent: 'center' as const, backgroundColor: colors.primary, marginTop: 18, paddingHorizontal: 20 }, actionButtonText: { color: '#FFFFFF', fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700' as const },
  preferenceGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 9 }, topicChoice: { minHeight: 50, minWidth: '47%' as const, maxWidth: '49%' as const, flexGrow: 1, borderRadius: 16, borderWidth: 1, borderColor: '#E4EDF7', backgroundColor: '#FFFFFF', flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 12 }, topicChoiceText: { flex: 1, color: '#344866', fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '600' as const }, checkMark: { width: 20, color: '#FFFFFF', fontSize: 16, fontWeight: '800' as const }, choiceLine: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 8, marginBottom: 5 }, sizeChoice: { minHeight: 40, borderRadius: 14, borderWidth: 1, borderColor: '#E2ECF6', backgroundColor: '#FFFFFF', alignItems: 'center' as const, justifyContent: 'center' as const, paddingHorizontal: 11 }, sizeChoiceActive: { borderColor: colors.primary, backgroundColor: '#EEF6FF' }, sizeChoiceText: { color: '#5D7192', fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '600' as const }, voiceRow: { minHeight: 66, flexDirection: 'row' as const, alignItems: 'center' as const, backgroundColor: '#FFFFFF', borderRadius: 16, borderWidth: 1, borderColor: '#E6EEF7', paddingHorizontal: 14, marginTop: 14 }, audioToggle: { minHeight: 57, flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, paddingHorizontal: 4, marginTop: 8 },
  infoCard: { backgroundColor: '#FFFFFF', borderRadius: 17, padding: 15, marginBottom: 10, borderWidth: 1, borderColor: '#EBF1F8' }, infoLabel: { color: '#7184A2', fontFamily: typography.fontFamily.ui, fontSize: 12 }, infoValue: { color: '#15234A', fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600' as const, marginTop: 4 }, infoPanel: { backgroundColor: '#FFFFFF', padding: 18, borderRadius: 20, borderWidth: 1, borderColor: '#E8EFF7' }, infoText: { color: '#63799B', fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 22 },
};
