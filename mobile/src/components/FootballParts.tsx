import React, { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { absolutePhotoUrl } from './SettingsKit';
import { typography, useTheme } from '../theme';

/** Competitions offered in Esportes, as the backend names them (football.py COMPETITIONS), Brazilian first. */
export const COMPETITIONS = [
  { code: 'BSA', name: 'Brasileirão', short: 'BR', color: '#16A34A', table: true },
  { code: 'CLI', name: 'Libertadores', short: 'LIB', color: '#C9A227', table: false },
  { code: 'CL', name: 'Champions League', short: 'UCL', color: '#1E3A8A', table: true },
  { code: 'PL', name: 'Premier League', short: 'PL', color: '#5B2A86', table: true },
  { code: 'PD', name: 'La Liga', short: 'LL', color: '#E11D48', table: true },
  { code: 'SA', name: 'Serie A', short: 'SA', color: '#1D4ED8', table: true },
  { code: 'BL1', name: 'Bundesliga', short: 'BL', color: '#DC2626', table: true },
  { code: 'FL1', name: 'Ligue 1', short: 'L1', color: '#0F766E', table: true },
  { code: 'PPL', name: 'Liga Portugal', short: 'POR', color: '#15803D', table: true },
  { code: 'DED', name: 'Eredivisie', short: 'ERE', color: '#EA580C', table: true },
  { code: 'ELC', name: 'Championship', short: 'EFL', color: '#334155', table: true },
  { code: 'WC', name: 'Copa do Mundo', short: 'WC', color: '#7C2D12', table: true },
  { code: 'EC', name: 'Eurocopa', short: 'EC', color: '#1E40AF', table: true },
];
export const competitionInfo = (code?: string, name?: string) =>
  COMPETITIONS.find(item => item.code === code) || { code: code || '', name: name || code || '', short: (code || '?').slice(0, 3), color: '#64748B', table: true };

/**
 * A team's official crest (football-data.org's image, cached by our API), or its three letters on a disc when
 * there is none or it does not load.
 */
export function TeamCrest({ crest, tla, name, size = 28 }: { crest?: string | null; tla?: string | null; name?: string; size?: number }) {
  const { colors } = useTheme();
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [crest]);
  const uri = absolutePhotoUrl(crest);
  if (uri && !failed) return <Image source={{ uri }} onError={() => setFailed(true)} resizeMode="contain" accessibilityIgnoresInvertColors
    style={{ width: size, height: size }} />;
  const letters = (tla || (name || '?').replace(/[^A-Za-zÀ-ÿ]/g, '').slice(0, 3)).toUpperCase();
  return <View style={[styles.fallback, { width: size, height: size, borderRadius: size / 2, backgroundColor: colors.surfaceSoft, borderColor: colors.border }]}>
    <Text style={[styles.fallbackText, { fontSize: Math.max(8, size * .3), color: colors.secondary }]}>{letters}</Text>
  </View>;
}

/** The small coloured square with the competition's code ("BR", "LIB"). */
export function CompetitionBadge({ code, name, size = 26 }: { code?: string; name?: string; size?: number }) {
  const info = competitionInfo(code, name);
  return <View style={[styles.badge, { width: size, height: size, borderRadius: size * .28, backgroundColor: info.color }]}>
    <Text style={[styles.badgeText, { fontSize: Math.max(8, size * (info.short.length > 2 ? .3 : .38)) }]}>{info.short}</Text>
  </View>;
}

export const ZONE_COLORS: Record<string, string> = { libertadores: '#2563EB', pre_libertadores: '#16A34A', sul_americana: '#8B5CF6', relegation: '#EF4444' };
export const ZONE_LABELS: Record<string, string> = { libertadores: 'Libertadores', pre_libertadores: 'Pré-Libertadores', sul_americana: 'Sul-Americana', relegation: 'Rebaixamento' };

const styles = StyleSheet.create({
  fallback: { alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  fallbackText: { fontFamily: typography.fontFamily.ui, fontWeight: '800' },
  badge: { alignItems: 'center', justifyContent: 'center' },
  badgeText: { color: '#FFFFFF', fontFamily: typography.fontFamily.ui, fontWeight: '800' },
});
