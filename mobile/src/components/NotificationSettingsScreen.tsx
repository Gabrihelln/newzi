import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { api, ClientError } from '../api/client';
import { checkPushPermission, isPushAllowed, requestAndRegisterDevice, type PushPermissionState } from '../push/push';
import type { NotificationSettings, NotificationSwitches } from '../types/api';
import { radius, spacing, typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { NoticeSwitches, platformName } from './NotificationParts';
import { PersonalAlertsCard } from './PersonalAlerts';
import { BrandPage, BrandPageHeader, ScreenState, SettingsCard } from './ScreenPrimitives';

type Field = keyof NotificationSwitches;

export function NotificationSettingsScreen({ onBack, onKeywords }: { onBack: () => void; onKeywords?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [saving, setSaving] = useState<Partial<Record<Field, boolean>>>({});
  const [permission, setPermission] = useState<PushPermissionState | null>(null);
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState('');
  // The values the server confirmed, so a failed save reverts only its own switch.
  const confirmed = useRef<NotificationSettings | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setMessage('');
    try {
      const loaded = await api.notificationSettings();
      confirmed.current = loaded;
      setSettings(loaded);
      setStatus('loaded');
    } catch {
      setStatus('error');
    }
  }, []);

  const refreshPermission = useCallback(() => { checkPushPermission().then(setPermission).catch(() => setPermission('NOT_DETERMINED')); }, []);

  useEffect(() => { void load(); refreshPermission(); }, [load, refreshPermission]);
  // Coming back from the system settings: show what the person changed there.
  useEffect(() => {
    const listener = AppState.addEventListener('change', state => { if (state === 'active') refreshPermission(); });
    return () => listener.remove();
  }, [refreshPermission]);

  // Each switch saves on its own, right away: there is no save button. Turning a notice on while the phone
  // blocks notifications also asks for the system permission, since nothing would arrive without it.
  const change = async (field: Field, value: boolean) => {
    if (!settings || saving[field]) return;
    if (value && permission !== null && !isPushAllowed(permission) && !asking) void allowNotifications();
    setMessage('');
    setSaving(current => ({ ...current, [field]: true }));
    setSettings(current => current && { ...current, [field]: value });
    try {
      const saved = await api.saveNotificationSettings({ [field]: value });
      confirmed.current = saved;
      setSettings(current => current && { ...current, [field]: saved[field] });
    } catch (error) {
      setSettings(current => current && { ...current, [field]: confirmed.current?.[field] ?? !value });
      setMessage(error instanceof ClientError && error.code === 'RATE_LIMITED'
        ? 'Muitas mudanças seguidas. Aguarde alguns segundos e tente de novo.'
        : 'Não foi possível salvar esta escolha. Verifique sua internet e tente de novo.');
    } finally {
      setSaving(current => ({ ...current, [field]: false }));
    }
  };

  const allowNotifications = async () => {
    setAsking(true);
    setMessage('');
    try { setPermission((await requestAndRegisterDevice()).permission); }
    catch { setMessage('Não foi possível abrir a permissão agora. Tente pelos ajustes do celular.'); }
    finally { setAsking(false); }
  };

  const blocked = permission !== null && !isPushAllowed(permission);
  const daily = settings?.notifications_enabled && settings.daily_briefing_enabled;
  const breaking = settings?.notifications_enabled && settings.breaking_news_enabled;

  return <BrandPage>
    <BrandPageHeader title="Notificações" onBack={onBack} />
    {status === 'loading' && <ScreenState kind="loading" title="Carregando suas notificações" />}
    {status === 'error' && <ScreenState kind="error" title="Notificações indisponíveis" message="Não foi possível carregar suas escolhas. Verifique sua internet." onRetry={() => void load()} />}
    {status === 'loaded' && settings && <>
      {blocked
        ? <View accessibilityRole="summary" style={[s.status, s.statusWarning]}>
          <View style={[s.statusIcon, { backgroundColor: colors.tone('#FDE7C2', colors.topicOrange.background) }]}><Icon name="bellOff" color={colors.tone('#C27A0E', colors.warning)} size={24} /></View>
          <View style={{ flex: 1 }}>
            <Text style={[s.statusLabel, { color: colors.warning }]}>{`PERMISSÃO DO ${platformName.toUpperCase()}`}</Text>
            <Text style={[s.statusTitle, { color: colors.tone('#5A3A06', colors.textPrimary) }]}>{permission === 'NOT_DETERMINED' ? 'Notificações não ativadas' : 'Notificações bloqueadas'}</Text>
            <Text style={[s.statusText, { color: colors.tone('#6E5326', colors.body) }]}>Suas escolhas abaixo ficam salvas, mas nenhum aviso chega até você liberar no celular.</Text>
            <Pressable accessibilityRole="button" disabled={asking} onPress={() => void allowNotifications()} style={({ pressed }) => [s.statusButton, (pressed || asking) && { opacity: .75 }]}>
              <Icon name="settings" color="#FFFFFF" size={16} /><Text style={s.statusButtonText}>{asking ? 'Aguarde…' : 'Ativar permissão'}</Text>
            </Pressable>
          </View>
        </View>
        : permission !== null && <View accessibilityRole="summary" style={[s.status, settings.notifications_enabled && (daily || breaking) ? s.statusOk : s.statusPaused]}>
          {settings.notifications_enabled && (daily || breaking)
            ? <>
              <View style={[s.statusIcon, { backgroundColor: 'rgba(255,255,255,.18)' }]}><Icon name="shield" color="#FFFFFF" size={24} /></View>
              <View style={{ flex: 1 }}>
                <Text style={[s.statusLabel, { color: 'rgba(255,255,255,.85)' }]}>NESTE APARELHO</Text>
                <Text style={[s.statusTitle, { color: '#FFFFFF' }]}>Notificações ativas</Text>
                <Text style={[s.statusText, { color: 'rgba(255,255,255,.92)' }]}>{daily && breaking ? `Você recebe o resumo${settings.briefing_time ? ` das ${settings.briefing_time}` : ''} e notícias urgentes.`
                  : daily ? `Você recebe o resumo${settings.briefing_time ? ` das ${settings.briefing_time}` : ''}.` : 'Você recebe as notícias urgentes dos seus temas.'}</Text>
              </View>
            </>
            : <>
              <View style={[s.statusIcon, { backgroundColor: colors.surfaceBlue }]}><Icon name="bellOff" color={colors.secondary} size={24} /></View>
              <View style={{ flex: 1 }}>
                <Text style={[s.statusLabel, { color: colors.secondary }]}>NESTE APARELHO</Text>
                <Text style={s.statusTitle}>{settings.notifications_enabled ? 'Nenhum aviso escolhido' : 'Notificações pausadas'}</Text>
                <Text style={s.statusText}>{settings.notifications_enabled ? 'Ligue o resumo diário ou as notícias urgentes para receber avisos.' : 'Ligue “Receber notificações” para voltar a receber avisos.'}</Text>
              </View>
            </>}
        </View>}

      <Text accessibilityRole="header" style={s.sectionTitle}>Avisos do Newzi</Text>
      <Text style={s.sectionText}>Escolha o que pode tocar no seu celular.</Text>
      <SettingsCard style={s.card}>
        <NoticeSwitches settings={settings} rules={settings.breaking_news_rules} busy={saving} onChange={(field, value) => void change(field, value)} />
      </SettingsCard>
      {onKeywords && <PersonalAlertsCard settings={settings} busy={saving} onChange={(field, value) => void change(field, value)} onKeywords={onKeywords} />}
      {!!message && <Text accessibilityRole="alert" style={s.error}>{message}</Text>}
    </>}
  </BrandPage>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  status: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, borderRadius: 26, padding: spacing.xl, marginBottom: spacing.xxl },
  statusOk: { backgroundColor: colors.tone('#1F7FEA', colors.inverse), shadowColor: '#1F7FEA', shadowOpacity: .25, shadowRadius: 16, shadowOffset: { width: 0, height: 8 }, elevation: 4 },
  statusWarning: { backgroundColor: colors.tone('#FFF4E2', colors.warningSurface), borderWidth: 1, borderColor: colors.tone('#F6D9A6', colors.warning) },
  statusPaused: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  statusIcon: { width: 48, height: 48, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  statusLabel: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '700', letterSpacing: .6 },
  statusTitle: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontSize: 19, fontWeight: '800', marginTop: 2 },
  statusText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 13, lineHeight: 19, marginTop: 4 },
  statusButton: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minHeight: 44, marginTop: spacing.md, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.tone('#E8900F', '#C27A0E') },
  statusButtonText: { fontFamily: typography.fontFamily.ui, color: '#FFFFFF', fontWeight: '800', fontSize: 14 },
  sectionTitle: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontSize: 21, fontWeight: '800', marginTop: spacing.md },
  sectionText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 14, marginTop: 2, marginBottom: spacing.md },
  card: { paddingVertical: 0, marginBottom: spacing.sm },
  error: { fontFamily: typography.fontFamily.ui, color: colors.danger, fontSize: 13, lineHeight: 19, marginBottom: spacing.sm },
});
