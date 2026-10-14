import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';
import { api } from '../api/client';
import { requestAndRegisterDevice } from '../push/push';
import type { NotificationSettings } from '../types/api';
import { spacing, useTheme } from '../theme';
import { BrandPage, BrandPageHeader, ScreenState, SettingsCard, SettingsSection } from './ScreenPrimitives';

export function NotificationSettingsScreen({ onBack }: { onBack: () => void }) {
  const { colors } = useTheme();
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

  // Each switch saves only its own field: turning the daily briefing off must not silence breaking news.
  const setEnabled = async (field: keyof Pick<NotificationSettings, 'notifications_enabled' | 'daily_briefing_enabled' | 'breaking_news_enabled'>, enabled: boolean) => {
    if (!settings || saving) return;
    setSaving(true);
    setMessage('');
    setSettings({ ...settings, [field]: enabled });
    try {
      const saved = await api.saveNotificationSettings({ [field]: enabled });
      setSettings(saved);
    } catch {
      setSettings(settings);
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
    <BrandPageHeader title="Notificações" subtitle="Escolha quais avisos receber neste aparelho." onBack={onBack} />
    <SettingsSection title="Avisos do Newzi">
      <SettingsCard>
        {status === 'loading' && <ScreenState kind="loading" title="Carregando preferências" />}
        {status === 'error' && <ScreenState kind="error" title="Preferências indisponíveis" message={message} onRetry={() => void load()} />}
        {status === 'loaded' && settings && <>
          <SettingRow title="Receber notificações" description="Desligue para pausar todos os avisos do Newzi." label="Todas as notificações"
            value={settings.notifications_enabled} disabled={saving} onChange={enabled => void setEnabled('notifications_enabled', enabled)} />
          <SettingRow title="Briefing diário" description={settings.briefing_time ? `Aviso quando o briefing estiver pronto, por volta das ${settings.briefing_time}.` : 'Aviso quando o seu briefing estiver pronto.'}
            label="Notificação do briefing diário" value={settings.daily_briefing_enabled} inactive={!settings.notifications_enabled} disabled={saving}
            onChange={enabled => void setEnabled('daily_briefing_enabled', enabled)} />
          <SettingRow title="Notícias urgentes" description="Quando vários veículos noticiam algo importante dos seus temas. No máximo 2 por dia, nunca entre 22h e 7h."
            label="Notificação de notícias urgentes" value={settings.breaking_news_enabled} inactive={!settings.notifications_enabled} disabled={saving}
            onChange={enabled => void setEnabled('breaking_news_enabled', enabled)} />
        </>}
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

function SettingRow({ title, description, label, value, inactive = false, disabled, onChange }: { title: string; description: string; label: string; value: boolean; inactive?: boolean; disabled: boolean; onChange: (value: boolean) => void }) {
  const { colors } = useTheme();
  // A specific notice keeps its own value while all notifications are paused, but cannot be changed.
  const on = value && !inactive;
  return <View style={{ minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md, paddingVertical: spacing.sm, opacity: inactive ? .5 : 1 }}>
    <View style={{ flex: 1 }}>
      <Text style={{ color: colors.textPrimary, fontWeight: '700', fontSize: 16 }}>{title}</Text>
      <Text style={{ color: colors.secondary, fontSize: 13, lineHeight: 18, marginTop: 4 }}>{description}</Text>
    </View>
    <Switch accessibilityLabel={label} accessibilityState={{ disabled: disabled || inactive }} disabled={disabled || inactive} value={on} onValueChange={onChange}
      trackColor={{ false: colors.switchTrackOff, true: colors.switchTrackOn }} thumbColor={on ? colors.primary : colors.switchThumbOff} />
  </View>;
}

function PressPermissionButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { colors } = useTheme();
  return <Pressable accessibilityRole="button" onPress={onPress} style={{ minHeight: 46, justifyContent: 'center', marginTop: spacing.sm }}><Text style={{ color: colors.primary, fontWeight: '700' }}>{label}</Text></Pressable>;
}
