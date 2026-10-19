import React, { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { requestPremium, usePremiumFeature } from '../services/premium';
import type { BriefingLength, ExtraBriefing, Topic } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { Badge, Card, Divider, IconBox, Segmented } from './SettingsKit';
import { TimeWheel } from './TimeWheel';

export type ExtraDraft = Pick<ExtraBriefing, 'time' | 'theme' | 'length' | 'enabled'>;
export const extraDraftOf = (items: ExtraBriefing[]): ExtraDraft[] => items.map(({ time, theme, length, enabled }) => ({ time, theme, length, enabled }));
export const sameExtras = (a: ExtraDraft[], b: ExtraDraft[]) => JSON.stringify(a) === JSON.stringify(b);
const LENGTHS: { value: BriefingLength; label: string; detail: string }[] = [
  { value: 'standard', label: 'Padrão', detail: 'Os destaques' }, { value: 'extended', label: 'Estendido', detail: 'Mais contexto' },
];

/** A free time after the others (the next round hour that is not taken). */
function freeTime(taken: string[]) {
  for (const hour of [12, 18, 21, 9, 15, 20, 7]) {
    const value = `${String(hour).padStart(2, '0')}:00`;
    if (!taken.includes(value)) return value;
  }
  return '13:30';
}

/**
 * Perfil › Resumo diário › Mais resumos no dia (Premium): up to two extra briefings, each with its own time,
 * a theme (one topic, or all of the reader's topics) and a length. Edits are kept in the parent's draft and saved
 * with the screen's save bar.
 */
export function ExtraBriefingsCard({ value, onChange, mainTime, limit }: { value: ExtraDraft[]; onChange: (value: ExtraDraft[]) => void; mainTime: string; limit: number }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const extras = usePremiumFeature('extra_briefings');
  const extended = usePremiumFeature('extended_briefing');
  const [themes, setThemes] = useState<Topic[]>([]);
  const [editingTime, setEditingTime] = useState<number | null>(null);
  const [editingTheme, setEditingTheme] = useState<number | null>(null);
  useEffect(() => {
    api.config().then(config => setThemes((config.topics as Topic[]).filter(topic => !topic.parent_id && topic.enabled !== false))).catch(() => undefined);
  }, []);
  if (!extras.visible) return null;

  const allowed = Math.max(0, limit - 1);
  const update = (index: number, change: Partial<ExtraDraft>) => onChange(value.map((item, position) => position === index ? { ...item, ...change } : item));
  const add = () => {
    if (!extras.unlocked) { requestPremium('extra_briefings'); return; }
    onChange([...value, { time: freeTime([mainTime, ...value.map(item => item.time)]), theme: null, length: 'standard', enabled: true }]);
  };
  const themeName = (id: string | null) => id ? themes.find(topic => (topic.code || topic.id) === id)?.name || 'Tema' : 'Todos os seus assuntos';

  return <Card>
    {value.map((item, index) => <View key={index}>
      {index > 0 && <Divider />}
      <View style={s.head}>
        <IconBox icon={item.theme ? 'topic' : 'headphones'} tint={index ? 'teal' : 'purple'} />
        <View style={{ flex: 1 }}>
          <Text style={s.title}>{index === 0 ? 'Segundo resumo' : 'Terceiro resumo'}</Text>
          <Text style={s.text}>{themeName(item.theme)} · {item.length === 'extended' ? 'estendido' : 'padrão'}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel={`Remover o ${index === 0 ? 'segundo' : 'terceiro'} resumo`} onPress={() => onChange(value.filter((_, position) => position !== index))} hitSlop={8} style={s.remove}>
          <Icon name="trash" color={colors.danger} size={17} />
        </Pressable>
      </View>
      <View style={s.choices}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Horário ${item.time}. Alterar`} onPress={() => setEditingTime(index)} style={s.choice}>
          <Icon name="clock" color={colors.primary} size={17} /><Text style={s.choiceText}>{item.time}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={`Tema: ${themeName(item.theme)}. Alterar`} onPress={() => setEditingTheme(index)} style={[s.choice, { flex: 1 }]}>
          <Icon name="topic" color={colors.primary} size={17} /><Text numberOfLines={1} style={[s.choiceText, { flex: 1 }]}>{themeName(item.theme)}</Text><Icon name="chevronDown" color={colors.secondary} size={15} />
        </Pressable>
      </View>
      {extended.visible && <View style={{ marginTop: 10 }}>
        <Segmented label="Duração do resumo" value={item.length} onChange={length => extended.unlocked || length === 'standard' ? update(index, { length }) : requestPremium('extended_briefing')}
          options={LENGTHS} />
      </View>}
    </View>)}
    {value.length > 0 && <Divider />}
    {value.length < Math.max(allowed, 1) && <Pressable accessibilityRole="button" accessibilityLabel={`Adicionar outro resumo no dia${extras.unlocked ? '' : '. Recurso Premium'}`} onPress={add} style={({ pressed }) => [s.head, pressed && { opacity: .75 }]}>
      <IconBox icon="plus" tint="blue" />
      <View style={{ flex: 1 }}><Text style={[s.title, { color: colors.primary }]}>Adicionar outro resumo</Text><Text style={s.text}>Até {limit > 1 ? limit : 3} por dia, cada um com seu horário e tema</Text></View>
      {!extras.unlocked && <Badge label="PREMIUM" tint="orange" />}
    </Pressable>}

    <Modal visible={editingTime !== null} transparent animationType="slide" onRequestClose={() => setEditingTime(null)}>
      <Pressable accessibilityLabel="Fechar" onPress={() => setEditingTime(null)} style={s.scrim}>
        <Pressable onPress={() => undefined} style={s.sheet}>
          <Text accessibilityRole="header" style={s.sheetTitle}>Horário do resumo</Text>
          {editingTime !== null && <View style={s.wheel}><TimeWheel large value={value[editingTime]?.time || '12:00'} onChange={time => update(editingTime, { time })} /></View>}
          {editingTime !== null && [mainTime, ...value.filter((_, position) => position !== editingTime).map(item => item.time)].includes(value[editingTime]?.time) &&
            <Text accessibilityRole="alert" style={s.warning}>Já existe um resumo nesse horário. Escolha outro.</Text>}
          <Pressable accessibilityRole="button" onPress={() => setEditingTime(null)} style={s.done}><Text style={s.doneText}>Pronto</Text></Pressable>
        </Pressable>
      </Pressable>
    </Modal>

    <Modal visible={editingTheme !== null} transparent animationType="slide" onRequestClose={() => setEditingTheme(null)}>
      <Pressable accessibilityLabel="Fechar" onPress={() => setEditingTheme(null)} style={s.scrim}>
        <Pressable onPress={() => undefined} style={s.sheet}>
          <Text accessibilityRole="header" style={s.sheetTitle}>Tema do resumo</Text>
          <Text style={s.sheetText}>Um resumo só sobre um tema, ou com todos os assuntos que você segue.</Text>
          <ScrollView style={{ maxHeight: 420 }}>
            {[{ id: null, name: 'Todos os seus assuntos' }, ...themes.map(topic => ({ id: (topic.code || topic.id) as string, name: topic.name }))].map(option => {
              const on = editingTheme !== null && (value[editingTheme]?.theme || null) === option.id;
              return <Pressable key={option.id || 'all'} accessibilityRole="radio" accessibilityState={{ checked: on }} onPress={() => { if (editingTheme !== null) update(editingTheme, { theme: option.id }); setEditingTheme(null); }} style={s.option}>
                <Text style={[s.optionText, on && { color: colors.primary }]}>{option.name}</Text>
                {on && <Icon name="check" color={colors.primary} size={18} />}
              </Pressable>;
            })}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  </Card>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  title: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  text: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.secondary, marginTop: 2 },
  remove: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.dangerSurface },
  choices: { flexDirection: 'row', gap: 8, marginTop: 12 },
  choice: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 44, paddingHorizontal: 14, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.tone('#F7FAFE', colors.surfaceSoft) },
  choiceText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.ink },
  scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, paddingBottom: 30 },
  sheetTitle: { fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800', color: colors.ink, marginBottom: 6 },
  sheetText: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: colors.secondary, marginBottom: 8 },
  wheel: { marginTop: 8, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.tone('#F7FAFE', colors.surfaceSoft), overflow: 'hidden' },
  warning: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.danger, marginTop: 10, textAlign: 'center' },
  done: { marginTop: 16, minHeight: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  doneText: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.onPrimary },
  option: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: colors.divider },
  optionText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.ink },
});
