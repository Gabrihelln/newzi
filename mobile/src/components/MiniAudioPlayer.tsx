import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Image, PanResponder, Pressable, Text, View } from 'react-native';
import { dismissMiniAudio, getAudioProgress, pauseAudio, playAudio, subscribeAudio, subscribeAudioContext } from '../audio/player';
import type { AudioContext, PlaybackState } from '../audio/player';
import type { Briefing } from '../types/api';
import { colors, radius, spacing, typography } from '../theme';
import { Icon } from './Icon';

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const cover = require('../../assets/onboarding/new-sunrise.png');

export function MiniAudioPlayer({ onExpand }: { onExpand: (briefing: Briefing) => void }) {
  const [session, setSession] = useState<AudioContext | null>(null);
  const [playback, setPlayback] = useState<PlaybackState | null>(null);
  const translateY = useRef(new Animated.Value(0)).current;
  const dismissing = useRef(false);
  const requestDismiss = useCallback((targetY = 112) => {
    if (dismissing.current) return;
    dismissing.current = true;
    Animated.timing(translateY, { toValue: Math.max(112, targetY), duration: 170, useNativeDriver: true }).start(({ finished }) => {
      if (!finished) {
        dismissing.current = false;
        translateY.setValue(0);
        return;
      }
      void dismissMiniAudio().finally(() => {
        translateY.setValue(0);
        dismissing.current = false;
      });
    });
  }, [translateY]);
  const panResponder = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_event, gesture) => gesture.dy > 8 && Math.abs(gesture.dy) > Math.abs(gesture.dx),
    onPanResponderMove: (_event, gesture) => translateY.setValue(Math.max(0, gesture.dy)),
    onPanResponderRelease: (_event, gesture) => {
      if (gesture.dy > 76 || gesture.vy > 0.9) requestDismiss(gesture.dy + 80);
      else Animated.spring(translateY, { toValue: 0, useNativeDriver: true, stiffness: 220, damping: 24 }).start();
    },
    onPanResponderTerminate: () => Animated.spring(translateY, { toValue: 0, useNativeDriver: true, stiffness: 220, damping: 24 }).start(),
  }), [requestDismiss, translateY]);
  useEffect(() => subscribeAudioContext(setSession), []);
  useEffect(() => subscribeAudio(setPlayback), []);
  useEffect(() => {
    if (!session || !playback?.started) return;
    const timer = setInterval(() => getAudioProgress().catch(() => undefined), 700);
    return () => clearInterval(timer);
  }, [session?.url, playback?.started]);
  if (!session || !playback?.loaded || !playback.started || playback.ended) return null;
  const toggle = () => playback.playing ? pauseAudio() : playAudio().catch(() => undefined);
  const date = session.briefing.generated_at ? new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' }).format(new Date(session.briefing.generated_at)).replace('.', '') : session.briefing.date;
  const progress = playback.duration ? Math.max(0, Math.min(1, playback.position / playback.duration)) : 0;
  return <Animated.View {...panResponder.panHandlers} style={{ width: '92%', maxWidth: 520, alignSelf: 'center', marginBottom: spacing.md, overflow: 'visible', zIndex: 20, elevation: 20, transform: [{ translateY }] }}>
    <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: radius.lg, minHeight: 94, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, shadowColor: '#496B99', shadowOpacity: .14, shadowRadius: 14, shadowOffset: { width: 0, height: 5 }, elevation: 7 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Expandir player do briefing" onPress={() => onExpand(session.briefing)}
        style={{ flex: 1, minHeight: 66, flexDirection: 'row', alignItems: 'center' }}>
        <Image source={cover} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ width: 58, height: 58, borderRadius: radius.md, marginRight: spacing.md }} />
        <View style={{ flex: 1, justifyContent: 'center' }}>
        <Text numberOfLines={1} style={{ color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontWeight: '800', fontSize: 15 }}>Seu briefing diário</Text>
        <Text numberOfLines={1} style={{ color: colors.secondary, fontSize: 12, marginTop: 4 }}>{date} · {clock(playback.position)} / {clock(playback.duration)}</Text>
        <View style={{ height: 4, backgroundColor: '#DBE7F4', borderRadius: 3, marginTop: 8, overflow: 'hidden' }}><View style={{ width: `${progress * 100}%`, height: 4, backgroundColor: colors.primary, borderRadius: 3 }} /></View>
        </View>
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel={playback.playing ? 'Pausar áudio' : 'Reproduzir áudio'}
        accessibilityState={{ selected: playback.playing }} onPress={toggle}
        style={{ width: 52, height: 52, borderRadius: radius.pill, backgroundColor: colors.primary,
          alignItems: 'center', justifyContent: 'center', marginLeft: spacing.md, shadowColor: colors.primary, shadowOpacity: .25, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4 }}>
        <Icon name={playback.playing ? 'pause' : 'play'} color={colors.surface} size={22} />
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Fechar mini player" onPress={() => requestDismiss()}
        hitSlop={4} style={{ position: 'absolute', top: -18, right: -8, width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}>
        <View style={{ width: 34, height: 34, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, shadowColor: '#496B99', shadowOpacity: .2, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 9 }}>
          <Icon name="close" color={colors.textPrimary} size={17} />
        </View>
      </Pressable>
    </View>
  </Animated.View>;
}
