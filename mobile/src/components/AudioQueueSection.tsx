import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { addToQueue, AudioNotReady, getQueue, playEntry, removeFromQueue, savedEntry, subscribeQueue, type QueueEntry } from '../audio/queue';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import { api } from '../api/client';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { Badge } from './SettingsKit';

/**
 * Player › A seguir (Premium): what plays after the current audio, and "Ouvir as matérias salvas" to add the saved
 * stories narrated. Briefings are added from Outros resumos.
 */
export function AudioQueueSection() {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const feature = usePremiumFeature('audio_queue');
  const [entries, setEntries] = useState<QueueEntry[]>(getQueue());
  const [preparing, setPreparing] = useState(false);
  const [note, setNote] = useState('');
  useEffect(() => subscribeQueue(setEntries), []);
  if (!feature.visible) return null;

  const addSaved = async () => {
    if (!feature.unlocked) { requestPremium('audio_queue'); return; }
    setPreparing(true); setNote('');
    try {
      // Narrating the saved stories starts now, so they are ready when their turn comes.
      const saved = await api.savedAudio(true);
      if (saved.status === 'EMPTY') { setNote('Você não tem matérias salvas para ouvir.'); return; }
      addToQueue(savedEntry());
      setNote(saved.status === 'READY' ? `${saved.story_count} matérias na fila.` : 'Estamos narrando suas matérias salvas; elas tocam quando chegar a vez.');
    } catch (error) { if (!handlePremiumError(error)) setNote('Não foi possível preparar suas matérias salvas.'); }
    finally { setPreparing(false); }
  };

  return <View style={s.wrap}>
    <View style={s.head}>
      <Icon name="queue" color={colors.primary} size={20} />
      <Text accessibilityRole="header" style={s.title}>A seguir</Text>
      {!feature.unlocked && <Badge label="PREMIUM" tint="orange" />}
    </View>
    {!entries.length && <Text style={s.empty}>{feature.unlocked ? 'Adicione resumos em Outros resumos ou suas matérias salvas, e eles tocam um depois do outro.' : 'Ouça resumos e matérias salvas em sequência, como um podcast.'}</Text>}
    {entries.map((entry, index) => <View key={entry.key} style={s.row}>
      <Text style={s.index}>{index + 1}</Text>
      <View style={{ flex: 1, minWidth: 0 }}><Text numberOfLines={1} style={s.rowTitle}>{entry.title}</Text>{!!entry.subtitle && <Text numberOfLines={1} style={s.rowText}>{entry.subtitle}</Text>}</View>
      <Pressable accessibilityRole="button" accessibilityLabel={`Tocar agora: ${entry.title}`} onPress={() => { removeFromQueue(entry.key); playEntry(entry).catch(error => setNote(error instanceof AudioNotReady ? 'Esse áudio ainda está sendo preparado.' : 'Não foi possível tocar agora.')); }} hitSlop={6} style={s.iconButton}>
        <Icon name="play" color={colors.primary} size={15} />
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel={`Tirar da fila: ${entry.title}`} onPress={() => removeFromQueue(entry.key)} hitSlop={6} style={s.iconButton}>
        <Icon name="close" color={colors.secondary} size={15} />
      </Pressable>
    </View>)}
    {!entries.some(entry => entry.kind === 'saved') && <Pressable accessibilityRole="button" disabled={preparing} onPress={() => void addSaved()} style={({ pressed }) => [s.add, pressed && { opacity: .8 }]}>
      {preparing ? <ActivityIndicator color={colors.primary} size="small" /> : <Icon name="bookmark" color={colors.primary} size={18} />}
      <Text style={s.addText}>Ouvir as matérias salvas</Text>
    </Pressable>}
    {!!note && <Text style={s.note}>{note}</Text>}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  wrap: { alignSelf: 'stretch', marginTop: 14, padding: 14, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  title: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 17, color: colors.secondary },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 48, borderTopWidth: 1, borderTopColor: colors.divider },
  index: { width: 18, fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '800', color: colors.muted, textAlign: 'center' },
  rowTitle: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.ink },
  rowText: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.secondary, marginTop: 1 },
  iconButton: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceTint },
  add: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 44, marginTop: 10, borderRadius: 22, backgroundColor: colors.surfaceBlue },
  addText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.primary },
  note: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.secondary, marginTop: 8, textAlign: 'center' },
});
