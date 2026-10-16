import React, { useEffect, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';
import { typography, useStyles, type Palette } from '../theme';

const ITEM_HEIGHT = 44;
const LARGE_ITEM_HEIGHT = 48;
const VISIBLE_ROWS = 3;
const hours = Array.from({ length: 24 }, (_, value) => value);
const minutes = Array.from({ length: 60 }, (_, value) => value);
const pad = (value: number) => String(value).padStart(2, '0');

/** Splits "HH:MM" into numbers; anything invalid falls back to 06:30. */
function parseTime(value: string) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  const hour = match ? Number(match[1]) : 6, minute = match ? Number(match[2]) : 30;
  return { hour: hour <= 23 ? hour : 6, minute: minute <= 59 ? minute : 30 };
}

function WheelColumn({ values, selected, onSelect, label, large = false }: { values: number[]; selected: number; onSelect: (value: number) => void; label: string; large?: boolean }) {
  const s = useStyles(makeStyles);
  const rowHeight = large ? LARGE_ITEM_HEIGHT : ITEM_HEIGHT;
  const scroll = useRef<ScrollView>(null);
  const current = useRef(selected);
  useEffect(() => {
    if (current.current === selected) return;
    current.current = selected;
    scroll.current?.scrollTo({ y: values.indexOf(selected) * rowHeight, animated: true });
  }, [selected, values]);
  const settle = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const index = Math.max(0, Math.min(values.length - 1, Math.round(event.nativeEvent.contentOffset.y / rowHeight)));
    if (values[index] === current.current) return;
    current.current = values[index];
    onSelect(values[index]);
  };
  const pick = (value: number) => { scroll.current?.scrollTo({ y: values.indexOf(value) * rowHeight, animated: true }); current.current = value; onSelect(value); };
  return <ScrollView ref={scroll} accessibilityLabel={`${label}: ${pad(selected)}`} style={large ? s.columnLarge : s.column} contentOffset={{ x: 0, y: values.indexOf(selected) * rowHeight }}
    contentContainerStyle={large ? s.columnContentLarge : s.columnContent} snapToInterval={rowHeight} decelerationRate="fast" showsVerticalScrollIndicator={false} nestedScrollEnabled
    onMomentumScrollEnd={settle} onScrollEndDrag={event => { if (!event.nativeEvent.velocity?.y) settle(event); }}>
    {values.map(value => <Pressable key={value} accessibilityRole="button" accessibilityLabel={`${label} ${pad(value)}`} onPress={() => pick(value)} style={large ? s.itemLarge : s.item}>
      <Text style={large ? [s.itemTextLarge, value === selected && s.itemTextLargeSelected] : [s.itemText, value === selected && s.itemTextSelected]}>{pad(value)}</Text>
    </Pressable>)}
  </ScrollView>;
}

/** Inline hour/minute wheel, so picking a time never opens the keyboard. `large` is the onboarding's bigger wheel. */
export function TimeWheel({ value, onChange, large = false }: { value: string; onChange: (time: string) => void; large?: boolean }) {
  const s = useStyles(makeStyles);
  const { hour, minute } = parseTime(value);
  return <View style={large ? s.wheelLarge : s.wheel}>
    <View pointerEvents="none" style={large ? s.bandLarge : s.band} />
    <WheelColumn large={large} label="Hora" values={hours} selected={hour} onSelect={next => onChange(`${pad(next)}:${pad(minute)}`)} />
    <Text style={large ? s.separatorLarge : s.separator}>:</Text>
    <WheelColumn large={large} label="Minuto" values={minutes} selected={minute} onSelect={next => onChange(`${pad(hour)}:${pad(next)}`)} />
  </View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  wheel: { height: ITEM_HEIGHT * VISIBLE_ROWS, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  band: { position: 'absolute', left: 0, right: 0, top: ITEM_HEIGHT, height: ITEM_HEIGHT, borderRadius: 14, backgroundColor: colors.surfaceTint },
  column: { width: 72, height: ITEM_HEIGHT * VISIBLE_ROWS }, columnContent: { paddingVertical: ITEM_HEIGHT },
  item: { height: ITEM_HEIGHT, alignItems: 'center', justifyContent: 'center' },
  itemText: { fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '600', color: colors.tone('#9AADC9', colors.muted) },
  itemTextSelected: { fontSize: 26, fontWeight: '800', color: colors.tone('#10264E', colors.ink) },
  wheelLarge: { height: LARGE_ITEM_HEIGHT * VISIBLE_ROWS, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  bandLarge: { position: 'absolute', left: 16, right: 16, top: LARGE_ITEM_HEIGHT - 1, height: 50, borderRadius: 14, backgroundColor: colors.surfaceTint },
  columnLarge: { width: 92, height: LARGE_ITEM_HEIGHT * VISIBLE_ROWS }, columnContentLarge: { paddingVertical: LARGE_ITEM_HEIGHT },
  itemLarge: { height: LARGE_ITEM_HEIGHT, alignItems: 'center', justifyContent: 'center' },
  // Unselected values are darker than the prototype's #A9BAD0 so they keep 4.5:1 on white.
  itemTextLarge: { fontFamily: typography.fontFamily.ui, fontSize: 22, fontWeight: '500', color: colors.tone('#5F769B', colors.secondary), fontVariant: ['tabular-nums'] },
  itemTextLargeSelected: { fontSize: 34, fontWeight: '800', color: colors.tone('#071A42', colors.ink) },
  separatorLarge: { fontFamily: typography.fontFamily.ui, fontSize: 32, fontWeight: '800', color: colors.tone('#071A42', colors.ink), marginBottom: 4 },
  separator: { fontFamily: typography.fontFamily.ui, fontSize: 26, fontWeight: '800', color: colors.tone('#10264E', colors.ink), marginHorizontal: 4, marginBottom: 3 },
});
