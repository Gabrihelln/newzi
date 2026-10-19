import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, FlatList, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, ClientError } from '../api/client';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { BriefingItem, SavedArticle, SavedCollection } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { ArticleImage } from './ArticleImage';
import { Icon } from './Icon';
import { Badge } from './SettingsKit';

/** Salvos › Coleções (Premium): the reader's folders of saved stories, and "Nova coleção". */
export function CollectionsSection({ collections, onOpen, onChanged }: { collections: SavedCollection[]; onOpen: (collection: SavedCollection) => void; onChanged: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const feature = usePremiumFeature('collections');
  const [creating, setCreating] = useState(false);
  if (!feature.visible && !collections.length) return null;
  const create = () => feature.unlocked ? setCreating(true) : requestPremium('collections');
  return <View style={{ marginBottom: 12 }}>
    <View style={s.head}>
      <Text accessibilityRole="header" style={s.title}>Coleções</Text>
      {!feature.unlocked && <Badge label="PREMIUM" tint="orange" />}
    </View>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.list}>
      {collections.map(collection => <Pressable key={collection.id} accessibilityRole="button" accessibilityLabel={`${collection.name}, ${collection.count} matérias`} onPress={() => onOpen(collection)} style={s.card}>
        {collection.cover_image_url ? <ArticleImage uri={collection.cover_image_url} style={s.cover} /> : <View style={[s.cover, s.coverEmpty]}><Icon name="folder" color={colors.primary} size={28} /></View>}
        <Text numberOfLines={1} style={s.cardTitle}>{collection.name}</Text>
        <Text style={s.cardMeta}>{collection.count} {collection.count === 1 ? 'matéria' : 'matérias'}</Text>
      </Pressable>)}
      <Pressable accessibilityRole="button" accessibilityLabel={`Nova coleção${feature.unlocked ? '' : '. Recurso Premium'}`} onPress={create} style={[s.card, s.newCard]}>
        <View style={[s.cover, s.coverEmpty]}><Icon name="plus" color={colors.primary} size={28} /></View>
        <Text style={[s.cardTitle, { color: colors.primary }]}>Nova coleção</Text>
        <Text style={s.cardMeta}>Organize seus salvos</Text>
      </Pressable>
    </ScrollView>
    <NewCollectionModal visible={creating} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); onChanged(); }} />
  </View>;
}

export function NewCollectionModal({ visible, onClose, onCreated }: { visible: boolean; onClose: () => void; onCreated: (collection: SavedCollection) => void }) {
  return <NameModal visible={visible} title="Nova coleção" action="Criar" onClose={onClose} onSubmit={async name => onCreated(await api.createCollection(name))} />;
}

/** Asks for a collection's name (create or rename). */
function NameModal({ visible, title, action, initial = '', onClose, onSubmit }: { visible: boolean; title: string; action: string; initial?: string; onClose: () => void; onSubmit: (name: string) => Promise<void> }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (visible) { setName(initial); setError(''); } }, [visible, initial]);
  const create = async () => {
    if (!name.trim()) { setError('Dê um nome à coleção.'); return; }
    setBusy(true); setError('');
    try { await onSubmit(name.trim()); }
    catch (cause) {
      if (handlePremiumError(cause)) { onClose(); return; }
      setError(cause instanceof ClientError && cause.code === 'COLLECTION_EXISTS' ? 'Você já tem uma coleção com esse nome.' : 'Não foi possível salvar a coleção.');
    } finally { setBusy(false); }
  };
  return <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
    <Pressable accessibilityLabel="Fechar" onPress={onClose} style={s.scrimCenter}>
      <Pressable onPress={() => undefined} style={s.dialog}>
        <Text accessibilityRole="header" style={s.dialogTitle}>{title}</Text>
        <TextInput accessibilityLabel="Nome da coleção" value={name} onChangeText={setName} placeholder="Ex.: Para ler no fim de semana" placeholderTextColor={colors.muted} maxLength={40} autoFocus
          onSubmitEditing={() => void create()} returnKeyType="done" style={s.input} />
        {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
        <View style={s.dialogActions}>
          <Pressable accessibilityRole="button" onPress={onClose} style={s.secondary}><Text style={s.secondaryText}>Cancelar</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => void create()} style={s.primary}>{busy ? <ActivityIndicator color={colors.onPrimary} /> : <Text style={s.primaryText}>{action}</Text>}</Pressable>
        </View>
      </Pressable>
    </Pressable>
  </Modal>;
}

/** Article › Adicionar à coleção: tick the collections the story belongs to (adding saves it). */
export function AddToCollectionSheet({ story, visible, onClose, onSaved }: { story: BriefingItem; visible: boolean; onClose: () => void; onSaved?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [collections, setCollections] = useState<SavedCollection[] | null>(null);
  const [members, setMembers] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const load = useCallback(() => {
    api.collections().then(result => setCollections(result.items)).catch(() => setCollections([]));
    api.storyCollections(story.id).then(result => setMembers(new Set(result.collection_ids))).catch(() => undefined);
  }, [story.id]);
  useEffect(() => { if (visible) load(); }, [visible, load]);
  const toggle = async (collection: SavedCollection) => {
    const member = !members.has(collection.id);
    setBusy(collection.id);
    try { const result = await api.setCollectionMember(collection.id, story, member); setMembers(new Set(result.collections)); if (member) onSaved?.(); }
    catch (cause) { if (!handlePremiumError(cause)) Alert.alert('Coleções', 'Não foi possível atualizar a coleção.'); }
    finally { setBusy(null); }
  };
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
    <Pressable accessibilityLabel="Fechar" onPress={onClose} style={s.scrim}>
      <Pressable onPress={() => undefined} style={s.sheet}>
        <Text accessibilityRole="header" style={s.dialogTitle}>Adicionar à coleção</Text>
        {!collections ? <ActivityIndicator color={colors.primary} style={{ marginVertical: 20 }} /> : <ScrollView style={{ maxHeight: 380 }}>
          {collections.map(collection => {
            const on = members.has(collection.id);
            return <Pressable key={collection.id} accessibilityRole="checkbox" accessibilityState={{ checked: on }} onPress={() => void toggle(collection)} style={s.option}>
              <Icon name="folder" color={colors.primary} size={20} />
              <Text numberOfLines={1} style={s.optionText}>{collection.name}</Text>
              {busy === collection.id ? <ActivityIndicator color={colors.primary} /> : <View style={[s.check, on && s.checkOn]}>{on && <Icon name="check" color={colors.onPrimary} size={14} />}</View>}
            </Pressable>;
          })}
          {!collections.length && <Text style={s.empty}>Você ainda não tem coleções.</Text>}
        </ScrollView>}
        <Pressable accessibilityRole="button" onPress={() => setCreating(true)} style={s.option}>
          <Icon name="plus" color={colors.primary} size={20} /><Text style={[s.optionText, { color: colors.primary }]}>Nova coleção</Text>
        </Pressable>
        <NewCollectionModal visible={creating} onClose={() => setCreating(false)} onCreated={collection => { setCreating(false); setCollections(current => [...(current || []), collection]); void toggle(collection); }} />
      </Pressable>
    </Pressable>
  </Modal>;
}

/** Salvos › a collection: its stories; rename or delete it (the stories stay in Salvos). */
export function CollectionScreen({ collection, onBack, onDetail }: { collection: SavedCollection; onBack: () => void; onDetail: (item: BriefingItem, progress?: number) => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [name, setName] = useState(collection.name);
  const [items, setItems] = useState<SavedArticle[] | null>(null);
  const [error, setError] = useState('');
  const [renaming, setRenaming] = useState(false);
  const load = useCallback(() => { setError(''); api.collectionStories(collection.id).then(result => setItems(result.items)).catch(() => setError('Não foi possível carregar a coleção.')); }, [collection.id]);
  useEffect(load, [load]);
  const remove = async (item: SavedArticle) => {
    setItems(current => (current || []).filter(story => story.id !== item.id));
    try { await api.setCollectionMember(collection.id, item, false); } catch { load(); }
  };
  const options = () => Alert.alert(name, undefined, [
    { text: 'Renomear', onPress: () => setRenaming(true) },
    { text: 'Apagar coleção', style: 'destructive', onPress: () => Alert.alert('Apagar coleção?', 'As matérias continuam nos seus salvos.', [{ text: 'Cancelar', style: 'cancel' },
      { text: 'Apagar', style: 'destructive', onPress: () => { api.deleteCollection(collection.id).then(onBack).catch(() => undefined); } }]) },
    { text: 'Cancelar', style: 'cancel' },
  ]);
  return <SafeAreaView style={s.safe} edges={['top']}>
    <View style={s.screenHead}>
      <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={onBack} style={s.back}><View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.textPrimary} size={21} /></View></Pressable>
      <Text numberOfLines={1} accessibilityRole="header" style={s.screenTitle}>{name}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Opções da coleção" onPress={options} style={s.back}><Icon name="dots" color={colors.textPrimary} size={21} /></Pressable>
    </View>
    {!items ? (error ? <Pressable onPress={load}><Text style={s.empty}>{error} Toque para tentar de novo.</Text></Pressable> : <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} />)
      : <FlatList data={items} keyExtractor={item => item.id} contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: 40 }}
        ListEmptyComponent={<Text style={s.empty}>Nenhuma matéria nesta coleção. Abra uma notícia e toque em “Coleção” para adicionar.</Text>}
        renderItem={({ item }) => <View style={s.row}>
          <Pressable accessibilityRole="button" accessibilityLabel={item.headline} onPress={() => onDetail(item, item.reading_progress)} style={s.rowPress}>
            <ArticleImage uri={item.image_url} articleId={item.id} style={s.thumb} />
            <View style={{ flex: 1 }}><Text numberOfLines={1} style={s.rowMeta}>{(item.primary_taxonomy_label || item.category || 'Notícias').toLocaleUpperCase('pt-BR')}</Text><Text numberOfLines={2} style={s.rowTitle}>{item.headline}</Text></View>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Tirar da coleção" onPress={() => void remove(item)} hitSlop={6} style={s.removeButton}><Icon name="close" color={colors.secondary} size={17} /></Pressable>
        </View>} />}
    <NameModal visible={renaming} title="Renomear coleção" action="Salvar" initial={name} onClose={() => setRenaming(false)}
      onSubmit={async value => { const updated = await api.renameCollection(collection.id, value); setName(updated.name); setRenaming(false); }} />
  </SafeAreaView>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 5, marginBottom: 9 },
  title: { flex: 1, color: colors.tone('#101A48', colors.ink), fontFamily: typography.fontFamily.ui, fontSize: 20, lineHeight: 25, fontWeight: '800', letterSpacing: -.5 },
  list: { gap: 10, paddingBottom: 6 },
  card: { width: 140, padding: 8, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider },
  newCard: { borderStyle: 'dashed', borderColor: colors.tone('#BBD5F3', colors.border) },
  cover: { width: '100%', height: 84, borderRadius: 14, backgroundColor: colors.surfaceTint },
  coverEmpty: { alignItems: 'center', justifyContent: 'center' },
  cardTitle: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800', color: colors.ink, marginTop: 8 },
  cardMeta: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.secondary, marginTop: 2 },
  scrim: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'flex-end' },
  scrimCenter: { flex: 1, backgroundColor: colors.scrim, justifyContent: 'center', padding: 24 },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, paddingBottom: 30 },
  dialog: { backgroundColor: colors.surface, borderRadius: 24, padding: 20 },
  dialogTitle: { fontFamily: typography.fontFamily.ui, fontSize: 18, fontWeight: '800', color: colors.ink, marginBottom: 10 },
  input: { minHeight: 50, borderRadius: 14, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, fontFamily: typography.fontFamily.ui, fontSize: 16, color: colors.ink, backgroundColor: colors.tone('#F7FAFE', colors.surfaceSoft) },
  error: { fontFamily: typography.fontFamily.ui, fontSize: 13, color: colors.danger, marginTop: 8 },
  dialogActions: { flexDirection: 'row', gap: 10, marginTop: 16 },
  secondary: { flex: 1, minHeight: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  secondaryText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.secondary },
  primary: { flex: 1, minHeight: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  primaryText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '800', color: colors.onPrimary },
  option: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 12, borderTopWidth: 1, borderTopColor: colors.divider },
  optionText: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '600', color: colors.ink },
  check: { width: 24, height: 24, borderRadius: 7, borderWidth: 1.6, borderColor: colors.borderStrong, alignItems: 'center', justifyContent: 'center' },
  checkOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  empty: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, color: colors.secondary, textAlign: 'center', paddingVertical: 20, paddingHorizontal: 18 },
  safe: { flex: 1, backgroundColor: colors.background },
  screenHead: { height: 56, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14 },
  back: { width: 42, height: 46, alignItems: 'center', justifyContent: 'center' },
  screenTitle: { flex: 1, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800', color: colors.ink },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 9, marginBottom: 9, borderRadius: 18, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider },
  rowPress: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 10 },
  thumb: { width: 70, height: 70, borderRadius: 16 },
  rowMeta: { fontFamily: typography.fontFamily.ui, fontSize: 10, fontWeight: '800', color: colors.primary },
  rowTitle: { fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 19, fontWeight: '700', color: colors.ink, marginTop: 4 },
  removeButton: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceTint },
});
