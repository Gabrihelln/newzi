import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { api, ClientError } from '../api/client';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { FollowedStory, KeywordAlert, NotificationSettings, NotificationSwitches } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { SettingSwitch } from './NotificationParts';
import { ScreenState } from './ScreenPrimitives';
import { Badge, Card, IconBox, SectionHeading, SettingsPage } from './SettingsKit';

/** Perfil › Notificações › Alertas personalizados (Premium): keywords and followed stories, each with its switch. */
export function PersonalAlertsCard({ settings, busy, onChange, onKeywords }: {
  settings: NotificationSettings; busy: Partial<Record<keyof NotificationSwitches, boolean>>;
  onChange: (field: keyof NotificationSwitches, value: boolean) => void; onKeywords: () => void;
}) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const keywords = usePremiumFeature('keyword_alerts');
  const stories = usePremiumFeature('story_follow');
  const [counts, setCounts] = useState<{ keywords: number; stories: number } | null>(null);
  useEffect(() => {
    if (!keywords.unlocked && !stories.unlocked) return;
    Promise.all([keywords.unlocked ? api.keywordAlerts() : Promise.resolve({ items: [] }), stories.unlocked ? api.followedStories() : Promise.resolve({ items: [] })])
      .then(([words, followed]) => setCounts({ keywords: words.items.length, stories: followed.items.length })).catch(() => undefined);
  }, [keywords.unlocked, stories.unlocked]);
  if (!keywords.visible && !stories.visible) return null;
  return <>
    <Text accessibilityRole="header" style={s.sectionTitle}>Alertas personalizados</Text>
    <Text style={s.sectionText}>Saiba na hora quando sair notícia sobre o que importa para você.</Text>
    <Card style={{ paddingVertical: 4, marginBottom: 8 }}>
      {keywords.visible && <View style={[s.row, s.divider]}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Palavras-chave${keywords.unlocked ? '' : '. Recurso Premium'}`} onPress={() => keywords.unlocked ? onKeywords() : requestPremium('keyword_alerts')} style={s.rowPress}>
          <IconBox icon="search" tint="purple" size={44} />
          <View style={{ flex: 1 }}><Text style={s.rowTitle}>Palavras-chave</Text><Text style={s.rowText}>{keywords.unlocked ? `${counts?.keywords ?? '…'} na sua lista · toque para editar` : 'Empresas, pessoas, cidades, ações'}</Text></View>
          {keywords.unlocked && <Icon name="chevron" color={colors.secondary} size={16} />}
        </Pressable>
        {keywords.unlocked ? <SettingSwitch label="Alertas por palavra-chave" value={settings.keyword_alerts_enabled !== false} busy={busy.keyword_alerts_enabled} onChange={value => onChange('keyword_alerts_enabled', value)} />
          : <Badge label="PREMIUM" tint="orange" />}
      </View>}
      {stories.visible && <View style={s.row}>
        <View style={s.rowPress}>
          <IconBox icon="bell" tint="teal" size={44} />
          <View style={{ flex: 1 }}><Text style={s.rowTitle}>Histórias que você acompanha</Text><Text style={s.rowText}>{stories.unlocked ? `${counts?.stories ?? '…'} acompanhando · toque no sino de uma notícia` : 'Novidades de uma história até ela acabar'}</Text></View>
        </View>
        {stories.unlocked ? <SettingSwitch label="Novidades das histórias" value={settings.story_updates_enabled !== false} busy={busy.story_updates_enabled} onChange={value => onChange('story_updates_enabled', value)} />
          : <Pressable accessibilityRole="button" accessibilityLabel="Acompanhar histórias. Recurso Premium" onPress={() => requestPremium('story_follow')}><Badge label="PREMIUM" tint="orange" /></Pressable>}
      </View>}
    </Card>
  </>;
}

/** Perfil › Notificações › Palavras-chave (Premium): add and remove the words that trigger an alert. */
export function KeywordAlertsScreen({ onBack }: { onBack: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const feature = usePremiumFeature('keyword_alerts');
  const [items, setItems] = useState<KeywordAlert[] | null>(null);
  const [followed, setFollowed] = useState<FollowedStory[]>([]);
  const [failed, setFailed] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setFailed(false);
    api.keywordAlerts().then(result => setItems(result.items)).catch(() => setFailed(true));
    api.followedStories().then(result => setFollowed(result.items)).catch(() => undefined);
  }, []);
  useEffect(load, [load]);
  const add = async () => {
    if (text.trim().length < 2) { setError('Digite pelo menos 2 letras.'); return; }
    setBusy(true); setError('');
    try { setItems((await api.addKeywordAlert(text.trim())).items); setText(''); }
    catch (cause) {
      if (handlePremiumError(cause)) return;
      setError(cause instanceof ClientError && cause.code === 'KEYWORD_EXISTS' ? 'Essa palavra já está na sua lista.' : 'Não foi possível adicionar agora.');
    } finally { setBusy(false); }
  };
  const remove = async (item: KeywordAlert) => {
    setItems(current => (current || []).filter(entry => entry.id !== item.id));
    try { setItems((await api.removeKeywordAlert(item.id)).items); } catch { load(); }
  };
  const unfollow = async (story: FollowedStory) => {
    setFollowed(current => current.filter(entry => entry.story_id !== story.story_id));
    try { await api.followStory(story.story_id, false); } catch { load(); }
  };
  const max = feature.limits?.keyword_alerts || 20;
  return <SettingsPage title="Palavras-chave" onBack={onBack}>
    {failed ? <ScreenState kind="error" title="Lista indisponível" message="Verifique sua internet e tente de novo." onRetry={load} />
      : !items ? <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} /> : <>
        <SectionHeading title="Avise quando sair notícia sobre…" subtitle={`Até ${max} palavras. O aviso chega quando uma manchete nova citar uma delas, no máximo 3 vezes por dia para cada.`} />
        <View style={s.addRow}>
          <TextInput accessibilityLabel="Nova palavra-chave" value={text} onChangeText={value => { setText(value); setError(''); }} placeholder="Ex.: Petrobras, Lula, Curitiba" placeholderTextColor={colors.muted}
            maxLength={40} autoCorrect={false} returnKeyType="done" onSubmitEditing={() => void add()} style={s.input} />
          <Pressable accessibilityRole="button" accessibilityLabel="Adicionar palavra-chave" disabled={busy || items.length >= max} onPress={() => void add()} style={[s.addButton, (busy || items.length >= max) && { opacity: .5 }]}>
            {busy ? <ActivityIndicator color={colors.onPrimary} /> : <Icon name="plus" color={colors.onPrimary} size={20} />}
          </Pressable>
        </View>
        {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
        <View style={s.chips}>
          {items.map(item => <View key={item.id} style={s.chip}>
            <Text style={s.chipText}>{item.keyword}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={`Remover ${item.keyword}`} onPress={() => void remove(item)} hitSlop={8}><Icon name="close" color={colors.primary} size={14} /></Pressable>
          </View>)}
          {!items.length && <Text style={s.empty}>Nenhuma palavra ainda. Que tal a empresa onde você trabalha ou sua cidade?</Text>}
        </View>
        <SectionHeading title="Histórias que você acompanha" subtitle="Toque no sino de uma notícia para receber as novidades dela por 7 dias." />
        <Card style={{ paddingVertical: 4 }}>
          {!followed.length && <Text style={s.empty}>Você não está acompanhando nenhuma história.</Text>}
          {followed.map((story, index) => <View key={story.story_id} style={[s.row, index < followed.length - 1 && s.divider]}>
            <View style={{ flex: 1 }}><Text numberOfLines={2} style={s.rowTitle}>{story.headline}</Text><Text style={s.rowText}>Até {new Date(story.until).toLocaleDateString('pt-BR')}</Text></View>
            <Pressable accessibilityRole="button" accessibilityLabel={`Deixar de acompanhar ${story.headline}`} onPress={() => void unfollow(story)} hitSlop={8} style={s.remove}><Icon name="bellOff" color={colors.danger} size={16} /></Pressable>
          </View>)}
        </Card>
      </>}
  </SettingsPage>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  sectionTitle: { fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontSize: 21, fontWeight: '800', marginTop: 18 },
  sectionText: { fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 14, marginTop: 2, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 72, paddingVertical: 10 },
  rowPress: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowTitle: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, fontWeight: '800', color: colors.ink },
  rowText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary, marginTop: 2 },
  addRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  input: { flex: 1, minHeight: 52, borderRadius: 16, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, fontFamily: typography.fontFamily.ui, fontSize: 16, color: colors.ink, backgroundColor: colors.surface },
  addButton: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  error: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.danger, marginTop: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 38, paddingHorizontal: 14, borderRadius: 19, backgroundColor: colors.surfaceBlue },
  chipText: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.primary },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: colors.secondary, paddingVertical: 12 },
  remove: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.dangerSurface },
});
