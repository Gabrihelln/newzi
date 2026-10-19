import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { AudioNotReady, playEntry, savedEntry } from '../audio/queue';
import { api } from '../api/client';
import { savedOfflineEnabled, setSavedOffline, syncSavedOffline } from '../services/offline';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { Briefing } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { SettingSwitch } from './NotificationParts';
import { Badge } from './SettingsKit';

/**
 * Salvos (Premium): "Ouvir as matérias salvas" (narrated one after the other) and "Disponível offline"
 * (stories, pictures and saved briefings kept on the phone).
 */
export function SavedPremiumTools({ onAudio, storyCount }: { onAudio: (briefing: Briefing) => void; storyCount: number }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const listen = usePremiumFeature('audio_queue');
  const offline = usePremiumFeature('offline_downloads');
  const [preparing, setPreparing] = useState(false);
  const [note, setNote] = useState('');
  const [offlineOn, setOfflineOn] = useState(savedOfflineEnabled());
  const [syncing, setSyncing] = useState(false);
  useEffect(() => {
    if (!offline.unlocked || !savedOfflineEnabled()) return;
    setSyncing(true);
    syncSavedOffline().catch(() => undefined).finally(() => setSyncing(false));
  }, [offline.unlocked]);
  if (!listen.visible && !offline.visible) return null;

  const play = async () => {
    if (!listen.unlocked) { requestPremium('audio_queue'); return; }
    setPreparing(true); setNote('');
    try {
      const briefing = await playEntry(savedEntry());
      if (briefing) onAudio(briefing);
    } catch (error) {
      if (handlePremiumError(error)) return;
      if (error instanceof AudioNotReady) {
        const saved = await api.savedAudio().catch(() => null);
        setNote(saved?.status === 'EMPTY' ? 'Todas as suas matérias salvas já foram lidas.' : 'Estamos narrando suas matérias salvas. Tente de novo em instantes.');
      } else setNote('Não foi possível tocar agora. Verifique sua conexão.');
    } finally { setPreparing(false); }
  };
  const toggleOffline = async (value: boolean) => {
    if (!offline.unlocked) { requestPremium('offline_downloads'); return; }
    setOfflineOn(value); setSyncing(value);
    try {
      await setSavedOffline(value);
      if (value) setNote('Seus salvos estão disponíveis sem internet.');
    } catch { setNote('Não foi possível baixar tudo agora; tentaremos de novo ao abrir os Salvos.'); }
    finally { setSyncing(false); }
  };

  return <View style={s.wrap}>
    {listen.visible && <Pressable accessibilityRole="button" accessibilityLabel={`Ouvir as matérias salvas${listen.unlocked ? '' : '. Recurso Premium'}`} disabled={preparing || !storyCount} onPress={() => void play()} style={[s.card, !storyCount && { opacity: .5 }]}>
      <View style={s.icon}>{preparing ? <ActivityIndicator color={colors.primary} /> : <Icon name="headphones" color={colors.primary} size={22} />}</View>
      <View style={{ flex: 1 }}><Text style={s.title}>Ouvir as matérias salvas</Text><Text style={s.text}>Narradas uma depois da outra</Text></View>
      {listen.unlocked ? <Icon name="play" color={colors.primary} size={18} /> : <Badge label="PREMIUM" tint="orange" />}
    </Pressable>}
    {offline.visible && <View style={s.card}>
      <View style={s.icon}>{syncing ? <ActivityIndicator color={colors.primary} /> : <Icon name="download" color={colors.primary} size={22} />}</View>
      <View style={{ flex: 1 }}><Text style={s.title}>Disponível offline</Text><Text style={s.text}>Matérias e resumos salvos sem internet</Text></View>
      {offline.unlocked ? <SettingSwitch label="Salvos disponíveis offline" value={offlineOn} onChange={value => void toggleOffline(value)} busy={syncing} />
        : <Pressable accessibilityRole="button" accessibilityLabel="Disponível offline. Recurso Premium" onPress={() => requestPremium('offline_downloads')}><Badge label="PREMIUM" tint="orange" /></Pressable>}
    </View>}
    {!!note && <Text style={s.note}>{note}</Text>}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  wrap: { gap: 8, marginBottom: 16 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 70, paddingHorizontal: 14, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider },
  icon: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceTint },
  title: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.ink },
  text: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.secondary, marginTop: 2 },
  note: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.secondary, textAlign: 'center' },
});
