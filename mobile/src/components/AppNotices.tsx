import React, { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { openFromNotification } from '../navigation/notificationRouting';
import { dismissPushNotice, subscribeAppNotices, type AppNoticeState } from '../services/appNotices';
import { radius, spacing, typography, useTheme } from '../theme';
import { Icon } from './Icon';

const PUSH_NOTICE_MS = 7000;

/** A push received while the app is open, and the offline notice, over the signed-in screens. */
export function AppNotices() {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [state, setState] = useState<AppNoticeState>({ push: null, offline: false });
  useEffect(() => subscribeAppNotices(setState), []);
  useEffect(() => {
    if (!state.push) return;
    const timer = setTimeout(dismissPushNotice, PUSH_NOTICE_MS);
    return () => clearTimeout(timer);
  }, [state.push]);
  if (!state.push && !state.offline) return null;
  const push = state.push;
  return <View pointerEvents="box-none" style={{ position: 'absolute', top: insets.top + spacing.sm, left: spacing.lg, right: spacing.lg, gap: spacing.sm }}>
    {push && <Pressable accessibilityRole="button" accessibilityLabel={`${push.title}. ${push.body}`}
      onPress={() => { dismissPushNotice(); openFromNotification(push.data); }}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md,
        borderWidth: 1, borderColor: colors.border, padding: spacing.md, opacity: pressed ? .85 : 1,
        shadowColor: colors.shadow.color, shadowOpacity: .18, shadowRadius: 14, shadowOffset: { width: 0, height: 5 }, elevation: 8 })}>
      <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceBlue, alignItems: 'center', justifyContent: 'center' }}>
        <Icon name={push.data.type === 'DAILY_BRIEFING' ? 'audio' : 'bolt'} color={colors.primary} size={20} />
      </View>
      <View style={{ flex: 1 }}>
        <Text numberOfLines={2} style={{ fontFamily: typography.fontFamily.ui, color: colors.textPrimary, fontWeight: '700', fontSize: 15 }}>{push.title}</Text>
        {!!push.body && <Text numberOfLines={2} style={{ fontFamily: typography.fontFamily.ui, color: colors.secondary, fontSize: 13, marginTop: 2 }}>{push.body}</Text>}
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Fechar aviso" hitSlop={10} onPress={dismissPushNotice}>
        <Text style={{ color: colors.muted, fontSize: 18, fontWeight: '700' }}>×</Text>
      </Pressable>
    </Pressable>}
    {state.offline && <View accessibilityRole="alert" style={{ alignSelf: 'center', backgroundColor: colors.warningSurface, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm }}>
      <Text style={{ fontFamily: typography.fontFamily.ui, color: colors.warning, fontWeight: '700', fontSize: 13 }}>Sem conexão · mostrando a última versão salva</Text>
    </View>}
  </View>;
}
