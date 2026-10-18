import React, { useId } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, RadialGradient, Rect, Stop } from 'react-native-svg';
import { API_BASE_URL } from '../config/env';
import type { Briefing } from '../types/api';
import { typography } from '../theme';

const appIcon = require('../../assets/icon.png');

export type EditionPeriod = 'morning' | 'afternoon' | 'night';
const PERIODS: Record<EditionPeriod, { label: string; sky: [string, string, string]; sun: string }> = {
  morning: { label: 'RESUMO DA MANHÃ', sky: ['#FF9B5E', '#B8789E', '#3D5FD6'], sun: '#FFD27A' },
  afternoon: { label: 'RESUMO DA TARDE', sky: ['#5FB2FF', '#4A86E8', '#2F4FC4'], sun: '#FFE7A3' },
  night: { label: 'RESUMO DA NOITE', sky: ['#5B4BC4', '#33307F', '#141B4D'], sun: '#C9D6FF' },
};

/** The edition's time of day, from when it was made (or the delivery date): it picks the cover's sky. */
export function editionPeriod(briefing: Pick<Briefing, 'generated_at'>): EditionPeriod {
  const hour = briefing.generated_at ? new Date(briefing.generated_at).getHours() : 7;
  return hour >= 5 && hour < 12 ? 'morning' : hour >= 12 && hour < 18 ? 'afternoon' : 'night';
}

export const editionPeriodLabel = (briefing: Pick<Briefing, 'generated_at'>) => PERIODS[editionPeriod(briefing)].label;

/**
 * The same cover as a PNG from the API, for the media notification and the lock screen (Android and iOS load
 * artwork from a plain URL). It only carries the period, the day and the counts.
 */
export function editionArtworkUrl(briefing: Pick<Briefing, 'generated_at' | 'date' | 'items' | 'audio_duration_ms'>, durationSeconds?: number) {
  const minutes = durationSeconds ? Math.round(durationSeconds / 60) : briefing.audio_duration_ms ? Math.round(briefing.audio_duration_ms / 60000) : 0;
  const query = `period=${editionPeriod(briefing)}&day=${encodeURIComponent(briefing.date)}&items=${Math.min(50, briefing.items.length)}&minutes=${Math.max(0, Math.min(180, minutes))}`;
  return `${API_BASE_URL}/api/v1/covers/edition.png?${query}`;
}

/** "Sábado, 18 out" (short) or "18 out" for the edition's day. */
export function editionDay(briefing: Pick<Briefing, 'date'>, withWeekday = true) {
  const date = new Date(`${briefing.date}T12:00:00`);
  if (Number.isNaN(date.getTime())) return briefing.date;
  const day = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short' }).format(date).replace('.', '').replace(' de ', ' ');
  if (!withWeekday) return day;
  const weekday = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(date).replace('-feira', '');
  return `${weekday[0].toUpperCase()}${weekday.slice(1)}, ${day}`;
}

/**
 * The cover of a daily edition, drawn with the brand instead of an illustration: the stacked sheets of the
 * Newzi icon over a sunrise gradient. `compact` is the small square used in the mini player and the chapters
 * strip (sheets only); the full cover adds the period, the day, "N notícias · X min" and the app seal.
 */
export function EditionCover({ briefing, size, durationSeconds, compact = false }: { briefing: Briefing; size: number; durationSeconds?: number; compact?: boolean }) {
  const id = useId().replace(/:/g, '');
  const period = PERIODS[editionPeriod(briefing)];
  const radius = compact ? size * .24 : 30;
  const minutes = durationSeconds ? Math.max(1, Math.round(durationSeconds / 60)) : briefing.audio_duration_ms ? Math.max(1, Math.round(briefing.audio_duration_ms / 60000)) : null;
  const sheet = size * (compact ? .5 : .36);
  return <View accessible accessibilityLabel={compact ? 'Capa do resumo' : `Capa do ${period.label.toLowerCase()}, ${editionDay(briefing)}`}
    style={[styles.cover, { width: size, height: size, borderRadius: radius }]}>
    <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
      <Defs>
        <LinearGradient id={`sky${id}`} x1="0" y1="0" x2="0.35" y2="1">
          <Stop offset="0" stopColor={period.sky[0]} /><Stop offset="0.55" stopColor={period.sky[1]} /><Stop offset="1" stopColor={period.sky[2]} />
        </LinearGradient>
        <RadialGradient id={`sun${id}`} cx="0.5" cy="0.5" r="0.5">
          <Stop offset="0" stopColor={period.sun} stopOpacity="1" /><Stop offset="0.55" stopColor={period.sun} stopOpacity="0.85" /><Stop offset="1" stopColor={period.sun} stopOpacity="0" />
        </RadialGradient>
      </Defs>
      <Rect width={size} height={size} fill={`url(#sky${id})`} />
      <Circle cx={size * .5} cy={size * (compact ? .78 : .78)} r={size * (compact ? .42 : .3)} fill={`url(#sun${id})`} />
    </Svg>
    {/* Stacked sheets: two faded ones behind, the front one with "text" lines. */}
    <View style={[styles.sheets, { width: sheet * 1.45, height: sheet * 1.2, top: compact ? size * .2 : size * .3 }]}>
      <View style={[styles.sheet, styles.sheetBack, { width: sheet, height: sheet * 1.1, borderRadius: sheet * .2, left: sheet * .42, transform: [{ rotate: '8deg' }] }]} />
      <View style={[styles.sheet, styles.sheetMiddle, { width: sheet, height: sheet * 1.1, borderRadius: sheet * .2, left: sheet * .22, transform: [{ rotate: '4deg' }] }]} />
      <View style={[styles.sheet, { width: sheet, height: sheet * 1.1, borderRadius: sheet * .2, transform: [{ rotate: '-5deg' }], padding: sheet * .14, gap: sheet * .07 }]}>
        <View style={[styles.line, { width: '58%', height: sheet * .08, backgroundColor: '#1F7FEA' }]} />
        {!compact && [92, 80, 86, 55].map((width, index) => <View key={index} style={[styles.line, { width: `${width}%`, height: sheet * .06 }]} />)}
        {compact && [86, 66].map((width, index) => <View key={index} style={[styles.line, { width: `${width}%`, height: sheet * .07 }]} />)}
      </View>
    </View>
    {!compact && <>
      <View style={styles.heading}>
        <Text style={styles.period}>{period.label}</Text>
        <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.day, { fontSize: Math.max(24, size * .1) }]}>{editionDay(briefing)}</Text>
      </View>
      <View style={styles.footer}>
        <View style={styles.pill}><Text style={styles.pillText}>{briefing.items.length} {briefing.items.length === 1 ? 'notícia' : 'notícias'}{minutes ? ` · ${minutes} min` : ''}</Text></View>
        <View style={styles.seal}><Image source={appIcon} style={styles.sealIcon} /></View>
      </View>
    </>}
  </View>;
}

const styles = StyleSheet.create({
  cover: { overflow: 'hidden', backgroundColor: '#3D5FD6' },
  sheets: { position: 'absolute', alignSelf: 'center' },
  sheet: { position: 'absolute', backgroundColor: '#FFFFFF', shadowColor: '#0B1A44', shadowOpacity: .22, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 6 },
  sheetBack: { backgroundColor: 'rgba(255,255,255,.38)', elevation: 0, shadowOpacity: 0 },
  sheetMiddle: { backgroundColor: 'rgba(255,255,255,.6)', elevation: 0, shadowOpacity: 0 },
  line: { borderRadius: 4, backgroundColor: '#D6E2F2' },
  heading: { position: 'absolute', left: 22, right: 22, top: 22 },
  period: { fontFamily: typography.fontFamily.ui, fontSize: 12, fontWeight: '800', letterSpacing: 2.4, color: 'rgba(255,255,255,.9)' },
  day: { fontFamily: typography.fontFamily.ui, fontWeight: '800', color: '#FFFFFF', marginTop: 2, letterSpacing: -.6 },
  footer: { position: 'absolute', left: 18, right: 18, bottom: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  pill: { paddingHorizontal: 13, paddingVertical: 7, borderRadius: 999, backgroundColor: 'rgba(255,255,255,.28)' },
  pillText: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: '#FFFFFF' },
  seal: { width: 36, height: 36, borderRadius: 10, padding: 2, backgroundColor: '#FFFFFF' },
  sealIcon: { width: '100%', height: '100%', borderRadius: 8 },
});
