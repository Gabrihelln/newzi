import React, { useCallback, useEffect, useState } from 'react';
import { Alert, BackHandler, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { updateProfile } from '@react-native-firebase/auth';
import { api, ClientError } from '../api/client';
import { firebaseAuth, getFirebaseIdToken } from '../services/firebaseAuth';
import { choosePhoto, uploadProfilePhoto, type PickedPhoto } from '../services/profilePhoto';
import type { User } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { signInMethod } from './AccountScreen';
import { Icon } from './Icon';
import { absolutePhotoUrl, Card, ProfileAvatar, SaveBar, SectionHeading, SettingsPage } from './SettingsKit';

const NAME_MAX = 60;

export function EditProfileScreen({ user, onBack, onSaved }: { user: User | null; onBack: () => void; onSaved: (user: User) => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const firebaseUser = firebaseAuth.currentUser;
  const initialName = user?.display_name || firebaseUser?.displayName || '';
  const [name, setName] = useState(initialName);
  const [photo, setPhoto] = useState<PickedPhoto | null>(null);
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dirty = name.trim() !== initialName.trim() || Boolean(photo);
  const email = user?.email || firebaseUser?.email || '';
  const method = signInMethod();
  const shown = photo?.uri || firebaseUser?.photoURL || absolutePhotoUrl(user?.photo_url);

  const pickPhoto = async () => {
    setError('');
    try { const picked = await choosePhoto(); if (picked) setPhoto(picked); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível abrir a foto.'); }
  };

  const save = async () => {
    if (!firebaseUser) return;
    if (!name.trim()) { setError('Informe seu nome para continuar.'); return; }
    setBusy(true); setError('');
    try {
      if (photo) await uploadProfilePhoto(photo);
      if (name.trim() !== (firebaseUser.displayName || '')) await updateProfile(firebaseUser, { displayName: name.trim() });
      await getFirebaseIdToken(true);
      onSaved(await api.me() as User);
    } catch (cause) {
      setError(cause instanceof ClientError && cause.code === 'VALIDATION_ERROR' ? 'Essa imagem não pôde ser usada. Escolha outra foto.'
        : 'Não foi possível salvar as alterações. Verifique sua conexão e tente novamente.');
    } finally { setBusy(false); }
  };

  const leave = useCallback(() => {
    if (!dirty || busy) { if (!busy) onBack(); return true; }
    Alert.alert('Descartar alterações?', 'Seu nome e sua foto continuarão como estavam.', [
      { text: 'Continuar editando', style: 'cancel' }, { text: 'Descartar', style: 'destructive', onPress: onBack }]);
    return true;
  }, [dirty, busy, onBack]);
  useEffect(() => { const sub = BackHandler.addEventListener('hardwareBackPress', leave); return () => sub.remove(); }, [leave]);

  return <SettingsPage title="Editar perfil" onBack={leave} footer={<SaveBar visible={dirty} busy={busy} onSave={() => void save()} error={error} />}>
    <Card style={s.profile}>
      <ProfileAvatar name={name || initialName} photo={shown} size={118} letters={2} />
      <Text numberOfLines={1} style={s.name}>{name.trim() || 'Seu nome'}</Text>
      <Text style={s.hint}>Assim seu nome e sua foto aparecem no Newzi.</Text>
      <Pressable accessibilityRole="button" onPress={() => void pickPhoto()} style={({ pressed }) => [s.photoButton, pressed && { opacity: .8 }]}>
        <Icon name="camera" color={colors.primary} size={19} /><Text style={s.photoText}>Trocar foto</Text>
      </Pressable>
    </Card>

    <SectionHeading title="Seus dados" subtitle="O nome aparece no Início e no Perfil." />
    <Card>
      <Text style={s.label}>Nome completo</Text>
      <View style={[s.field, focused && s.fieldFocused]}>
        <Icon name="profile" color={colors.primary} size={21} />
        <TextInput accessibilityLabel="Nome completo" value={name} onChangeText={text => { setName(text); setError(''); }} maxLength={NAME_MAX}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} autoCapitalize="words" autoComplete="name" textContentType="name"
          placeholder="Seu nome" placeholderTextColor={colors.muted} style={s.input} />
        <Text style={s.counter}>{name.length}/{NAME_MAX}</Text>
      </View>
      <Text style={[s.label, { marginTop: 18 }]}>E-mail</Text>
      <View accessible accessibilityLabel={`E-mail: ${email}. Não pode ser alterado.`} style={[s.field, s.fieldLocked]}>
        <Icon name="mail" color={colors.secondary} size={21} />
        <Text numberOfLines={1} style={[s.input, s.lockedText]}>{email || 'E-mail não informado'}</Text>
        <Icon name="lock" color={colors.muted} size={18} />
      </View>
      <View style={s.info}>
        <Icon name="info" color={colors.muted} size={16} />
        <Text style={s.infoText}>{method.label === 'Google' || method.label === 'Apple'
          ? `O e-mail vem da sua conta ${method.label} e não pode ser trocado aqui.` : 'O e-mail é o do seu acesso e não pode ser trocado aqui.'}</Text>
      </View>
    </Card>
  </SettingsPage>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  profile: { alignItems: 'center', paddingVertical: 26 },
  name: { fontFamily: typography.fontFamily.ui, fontSize: 23, fontWeight: '800', color: colors.ink, marginTop: 14, maxWidth: '100%' },
  hint: { fontFamily: typography.fontFamily.ui, fontSize: 14, color: colors.secondary, marginTop: 4, textAlign: 'center' },
  photoButton: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48, paddingHorizontal: 26, marginTop: 18, borderRadius: 16, borderWidth: 1.5, borderColor: colors.primary },
  photoText: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, fontWeight: '800', color: colors.primary },
  label: { fontFamily: typography.fontFamily.ui, fontSize: 14.5, fontWeight: '800', color: colors.ink, marginBottom: 9 },
  field: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56, paddingHorizontal: 16, borderRadius: 16, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surface },
  fieldFocused: { borderColor: colors.primary, shadowColor: colors.primary, shadowOpacity: .18, shadowRadius: 8, shadowOffset: { width: 0, height: 0 }, elevation: 2 },
  fieldLocked: { backgroundColor: colors.tone('#F1F5FA', colors.surfaceSoft), borderColor: colors.tone('#E3EAF3', colors.border) },
  input: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 16, color: colors.ink, paddingVertical: 10 },
  lockedText: { color: colors.secondary },
  counter: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.muted },
  info: { flexDirection: 'row', gap: 8, marginTop: 12 },
  infoText: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 19, color: colors.secondary },
});
