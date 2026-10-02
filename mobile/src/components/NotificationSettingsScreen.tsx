import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';
import { api } from '../api/client';
import { requestAndRegisterDevice } from '../push/push';
import type { NotificationSettings } from '../types/api';
import { colors, spacing } from '../theme';
import { BrandPage, BrandPageHeader, ScreenState, SettingsCard, SettingsSection } from './ScreenPrimitives';

export function NotificationSettingsScreen({ onBack }: { onBack: () => void }) {
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [saving, setSaving] = useState(false);
  const [permission, setPermission] = useState<'UNKNOWN' | 'AUTHORIZED' | 'DENIED' | 'UNAVAILABLE'>('UNKNOWN');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setMessage('');
    try {
      setSettings(await api.notificationSettings());
      setStatus('loaded');
    } catch {
      setSettings(null);
      setStatus('error');
      setMessage('Não foi possível carregar suas preferências de notificação.');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const setEnabled = async (enabled: boolean) => {
    if (!settings || saving) return;
    setSaving(true);
    setMessage('');
    try {
      const saved = await api.saveNotificationSettings({ notifications_enabled: enabled, daily_briefing_enabled: enabled });
      setSettings(saved);
    } catch {
      setMessage('Não foi possível salvar esta preferência. Tente novamente.');
    } finally {
      setSaving(false);
    }
  };

  const requestPermission = async () => {
    setMessage('');
    try {
      const result = await requestAndRegisterDevice();
      setPermission(result.permission === 'AUTHORIZED' ? 'AUTHORIZED' : result.permission === 'DENIED' ? 'DENIED' : 'UNAVAILABLE');
      if (!result.device && result.permission !== 'AUTHORIZED') setMessage('Não foi possível registrar as notificações neste aparelho. Verifique a permissão do sistema.');
    } catch {
      setPermission('UNAVAILABLE');
      setMessage('Não foi possível solicitar a permissão agora.');
    }
  };

  return <BrandPage>
    <BrandPageHeader title="Notificações" subtitle="Gerencie o aviso de briefing neste aparelho." onBack={onBack} />
    <SettingsSection title="Briefing diário">
      <SettingsCard>
        {status === 'loading' && <ScreenState kind="loading" title="Carregando preferências" />}
        {status === 'error' && <ScreenState kind="error" title="Preferências indisponíveis" message={message} onRetry={() => void load()} />}
        {status === 'loaded' && settings && <View style={{ minHeight: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.textPrimary, fontWeight: '700', fontSize: 16 }}>Avisar quando estiver pronto</Text>
            <Text style={{ color: colors.secondary, fontSize: 13, marginTop: 4 }}>{settings.briefing_time ? `Seu horário: ${settings.briefing_time}` : 'Receba um aviso após a preparação do briefing.'}</Text>
          </View>
          <Switch accessibilityLabel="Notificação do briefing diário" disabled={saving} value={settings.notifications_enabled && settings.daily_briefing_enabled} onValueChange={enabled => void setEnabled(enabled)} trackColor={{ false: '#CBD7E7', true: '#9CC9FF' }} thumbColor={settings.notifications_enabled && settings.daily_briefing_enabled ? colors.primary : '#FFFFFF'} />
        </View>}
      </SettingsCard>
    </SettingsSection>
    <SettingsSection title="Permissão do sistema">
      <SettingsCard>
        <Text style={{ color: colors.textPrimary, fontWeight: '700', fontSize: 15 }}>{permission === 'AUTHORIZED' ? 'Permissão concedida' : permission === 'DENIED' ? 'Permissão negada' : permission === 'UNAVAILABLE' ? 'Permissão indisponível' : 'Verificar neste aparelho'}</Text>
        <Text style={{ color: colors.secondary, fontSize: 13, lineHeight: 19, marginTop: spacing.xs }}>A preferência do Newzi e a permissão do Android são controles separados.</Text>
        {permission !== 'AUTHORIZED' && <PressPermissionButton label={permission === 'DENIED' ? 'Tentar novamente' : 'Solicitar permissão'} onPress={() => void requestPermission()} />}
      </SettingsCard>
    </SettingsSection>
    {!!message && status === 'loaded' && <Text accessibilityRole="alert" style={{ color: colors.danger, marginTop: spacing.sm }}>{message}</Text>}
  </BrandPage>;
}

function PressPermissionButton({ label, onPress }: { label: string; onPress: () => void }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={{ minHeight: 46, justifyContent: 'center', marginTop: spacing.sm }}><Text style={{ color: colors.primary, fontWeight: '700' }}>{label}</Text></Pressable>;
}
