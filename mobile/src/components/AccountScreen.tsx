import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { firebaseAuth } from '../services/firebaseAuth';
import type { User } from '../types/api';
import {spacing, typography, useStyles, useTheme, type Palette } from '../theme';
import { BrandPage, BrandPageHeader, ScreenState, SettingsCard, SettingsSection } from './ScreenPrimitives';
import { Icon } from './Icon';

export function AccountScreen({ onBack, onEditProfile }: { onBack: () => void; onEditProfile: () => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      setUser(await api.me() as User);
      setStatus('loaded');
    } catch {
      setUser(null);
      setStatus('error');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const created = user?.created_at || firebaseAuth.currentUser?.metadata?.creationTime;
  const createdLabel = created && !Number.isNaN(new Date(created).getTime())
    ? new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(created))
    : 'Data indisponível';

  return <BrandPage>
    <BrandPageHeader title="Dados pessoais" subtitle="Informações da sua conta Newzi." onBack={onBack} />
    {status === 'loading' && <ScreenState kind="loading" title="Carregando dados da conta" />}
    {status === 'error' && <ScreenState kind="error" title="Não foi possível carregar sua conta" message="Confira sua conexão e tente novamente." onRetry={() => void load()} />}
    {status === 'loaded' && user && <>
      <SettingsSection title="Informações da conta">
        <SettingsCard>
          <Info label="Nome" value={user.display_name || firebaseAuth.currentUser?.displayName || 'Nome não informado'} />
          <Info label="E-mail" value={user.email || firebaseAuth.currentUser?.email || 'E-mail não informado'} />
          <Info label="Membro desde" value={createdLabel} />
          {!!user.status && <Info label="Status" value={user.status === 'ACTIVE' ? 'Ativa' : 'Desativada'} />}
          <Pressable accessibilityRole="button" onPress={onEditProfile} style={s.action}>
            <Icon name="edit" color={colors.primary} size={20} /><Text style={s.actionText}>Editar perfil</Text>
          </Pressable>
        </SettingsCard>
      </SettingsSection>
      <SettingsSection title="Sessão">
        <SettingsCard><Info label="Conta conectada" value={user.email || firebaseAuth.currentUser?.email || 'E-mail não informado'} /></SettingsCard>
      </SettingsSection>
    </>}
  </BrandPage>;
}

function Info({ label, value }: { label: string; value: string }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={s.info}><Text style={s.label}>{label}</Text><Text style={s.value}>{value}</Text></View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  info: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.surfaceSoft },
  label: { color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: typography.caption },
  value: { color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontSize: typography.body, lineHeight: 23, fontWeight: '600', marginTop: spacing.xs },
  action: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.sm },
  actionText: { color: colors.primary, fontFamily: typography.fontFamily.ui, fontWeight: '700', fontSize: typography.bodySmall },
});
