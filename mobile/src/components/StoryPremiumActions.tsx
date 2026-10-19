import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { handlePremiumError, requestPremium, usePremiumFeature } from '../services/premium';
import type { BriefingItem } from '../types/api';
import { typography, useStyles, useTheme, type Palette } from '../theme';
import { AddToCollectionSheet } from './Collections';
import { Icon } from './Icon';

/**
 * Notícia (Premium): "Acompanhar história" (a push when the story has news, for a week) and "Coleção"
 * (put the story in one of the reader's collections; it is saved too).
 */
export function StoryPremiumActions({ story, onSaved }: { story: BriefingItem; onSaved?: () => void }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const follow = usePremiumFeature('story_follow');
  const collections = usePremiumFeature('collections');
  const [following, setFollowing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [sheet, setSheet] = useState(false);
  // A story inside a briefing has the briefing item's id; following needs the article's.
  const articleId = story.sources?.find(source => source.article_id)?.article_id || story.id;
  useEffect(() => {
    let active = true;
    if (follow.unlocked) api.storyFollow(articleId).then(result => { if (active) setFollowing(result.following); }).catch(() => undefined);
    return () => { active = false; };
  }, [articleId, follow.unlocked]);
  if (!follow.visible && !collections.visible) return null;

  const toggleFollow = async () => {
    if (!follow.unlocked) { requestPremium('story_follow'); return; }
    setBusy(true); setNote('');
    try {
      const result = await api.followStory(articleId, !following);
      setFollowing(result.following);
      setNote(result.following ? 'Avisaremos quando essa história tiver novidade (por 7 dias).' : '');
    } catch (error) { if (!handlePremiumError(error)) setNote('Não foi possível atualizar agora.'); }
    finally { setBusy(false); }
  };

  return <View style={s.wrap}>
    <View style={s.row}>
      {follow.visible && <Pressable accessibilityRole="button" accessibilityState={{ selected: following, busy }} accessibilityLabel={following ? 'Deixar de acompanhar esta história' : `Acompanhar esta história${follow.unlocked ? '' : '. Recurso Premium'}`}
        onPress={() => void toggleFollow()} style={[s.pill, following && s.pillOn]}>
        {busy ? <ActivityIndicator size="small" color={following ? colors.onPrimary : colors.primary} /> : <Icon name={following ? 'bellOff' : 'bell'} color={following ? colors.onPrimary : colors.primary} size={17} />}
        <Text style={[s.pillText, following && { color: colors.onPrimary }]}>{following ? 'Acompanhando' : 'Acompanhar história'}</Text>
        {!follow.unlocked && <Text style={s.star}>★</Text>}
      </Pressable>}
      {collections.visible && <Pressable accessibilityRole="button" accessibilityLabel={`Adicionar a uma coleção${collections.unlocked ? '' : '. Recurso Premium'}`}
        onPress={() => collections.unlocked ? setSheet(true) : requestPremium('collections')} style={s.pill}>
        <Icon name="folder" color={colors.primary} size={17} /><Text style={s.pillText}>Coleção</Text>
        {!collections.unlocked && <Text style={s.star}>★</Text>}
      </Pressable>}
    </View>
    {!!note && <Text style={s.note}>{note}</Text>}
    {sheet && <AddToCollectionSheet story={story} visible={sheet} onClose={() => setSheet(false)} onSaved={onSaved} />}
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  wrap: { marginBottom: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 40, paddingHorizontal: 14, borderRadius: 20, borderWidth: 1, borderColor: colors.tone('#CFE2F8', colors.border), backgroundColor: colors.tone('#F2F8FF', colors.surfaceTint) },
  pillOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillText: { fontFamily: typography.fontFamily.ui, fontSize: 13.5, fontWeight: '700', color: colors.primary },
  star: { fontSize: 12, color: colors.tone('#C27A00', '#FFC56B') },
  note: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.secondary, marginTop: 8 },
});
