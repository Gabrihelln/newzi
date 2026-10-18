import React from 'react';
import Svg, { Circle, Path, Rect, Text as SvgText } from 'react-native-svg';
import { useTheme } from '../theme';

export type IconName = 'ball' | 'trending' | 'moon' | 'search' | 'bell' | 'chevron' | 'chevronDown' | 'close' | 'calendar' | 'bookmark' | 'clock' | 'play' | 'pause' | 'audio' | 'home' | 'explore' | 'saved' | 'profile' | 'topic' | 'settings' | 'sun' | 'lock' | 'card' | 'help' | 'message' | 'camera' | 'edit' | 'share' | 'more' | 'dots' | 'headphones' | 'speed' | 'article' | 'check' | 'checkCircle' | 'arrowUpRight' | 'stop' | 'radio' | 'radioActive' | 'globe' | 'rewind' | 'forward' | 'previous' | 'next' | 'volume' | 'cpu' | 'brain' | 'growth' | 'coins' | 'landmark' | 'heart' | 'leaf' | 'sparkles' | 'image' | 'ratingGreat' | 'ratingGood' | 'ratingNeutral' | 'ratingBad' | 'ratingPoor' | 'trash' | 'flag' | 'layers' | 'mic' | 'shield' | 'bellOff' | 'bolt' | 'info' | 'mail' | 'phone' | 'pin' | 'star' | 'plus' | 'apple' | 'google' | 'replay15' | 'forward15' | 'filter';

/** `filled` paints the whole shape (a saved bookmark); otherwise icons are outlines. */
export function Icon({ name, color: requested, size = 22, filled = false }: { name: IconName; color?: string; size?: number; filled?: boolean }) {
  const theme = useTheme();
  const color = requested ?? theme.colors.text;
  const stroke = { stroke: color, strokeWidth: 1.9, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return <Svg width={size} height={size} viewBox="0 0 24 24">
    {name === 'search' && <><Circle cx="10.8" cy="10.8" r="7.2" {...stroke} /><Path d="m16 16 5 5" {...stroke} /></>}
    {name === 'mail' && <><Rect x="3" y="5" width="18" height="14" rx="2" {...stroke} /><Path d="m4 7 8 6 8-6" {...stroke} /></>}
    {name === 'phone' && <><Rect x="6.5" y="2.5" width="11" height="19" rx="2.4" {...stroke} /><Path d="M11 18.5h2" {...stroke} /></>}
    {name === 'pin' && <><Path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" {...stroke} /><Circle cx="12" cy="10" r="2.3" {...stroke} /></>}
    {name === 'star' && <Path d="m12 3.5 2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8Z" {...stroke} />}
    {name === 'plus' && <Path d="M12 5v14M5 12h14" {...stroke} />}
    {name === 'apple' && <><Path d="M16.9 12.6c.1 2 1.5 2.7 1.6 2.8-.8 2.1-2.2 4.2-3.9 4.2-.9 0-1.3-.5-2.4-.5s-1.6.5-2.4.5c-1.7.1-3.2-2.3-4-4.4-1.6-3.5-.7-8.5 3.2-8.6 1 0 1.9.6 2.5.6.7 0 1.8-.7 3-.6 1.3.1 2.2.6 2.8 1.5-2.4 1.3-2.3 4.3-.2 5.5Z" fill={color} /><Path d="M14.5 5.5c.7-.8 1.1-1.9 1-3-1 .1-2.1.8-2.8 1.6-.7.8-1.1 1.8-1 2.8 1.1.1 2.1-.5 2.8-1.4Z" fill={color} /></>}
    {/* Google's "G" keeps its own colors whatever color is asked for. */}
    {name === 'google' && <><Path fill="#4285F4" d="M21.35 12.24c0-.71-.06-1.23-.2-1.78H12v3.55h5.37a4.8 4.8 0 0 1-1.98 3.14v2.6h3.18c1.86-1.72 2.78-4.25 2.78-7.51Z" /><Path fill="#34A853" d="M12 21.5c2.7 0 4.96-.9 6.62-2.45l-3.18-2.6c-.9.6-2.05.96-3.44.96-2.64 0-4.87-1.78-5.67-4.16H3.05v2.67A9.5 9.5 0 0 0 12 21.5Z" /><Path fill="#FBBC05" d="M6.33 13.25A5.8 5.8 0 0 1 6.03 12c0-.43.1-.85.3-1.25V8.08H3.05A9.5 9.5 0 0 0 2.5 12c0 1.53.37 2.99 1.05 4.25l3.28-3Z" /><Path fill="#EA4335" d="M12 6.59c1.47 0 2.8.5 3.84 1.53l2.86-2.87A9.22 9.22 0 0 0 12 2.5a9.5 9.5 0 0 0-8.95 5.58l3.28 2.67C7.13 8.37 9.36 6.59 12 6.59Z" /></>}
    {/* 15-second skips: a clean circular arrow with the number inside, as in common players. */}
    {name === 'replay15' && <><Path d="M5.2 8.6A8 8 0 1 1 4 12.8" {...stroke} /><Path d="M4.6 4.4v4.6h4.6" {...stroke} /><SvgText x="12.4" y="15.6" fontSize="8.4" fontWeight="800" fill={color} textAnchor="middle">15</SvgText></>}
    {name === 'forward15' && <><Path d="M18.8 8.6A8 8 0 1 0 20 12.8" {...stroke} /><Path d="M19.4 4.4v4.6h-4.6" {...stroke} /><SvgText x="11.6" y="15.6" fontSize="8.4" fontWeight="800" fill={color} textAnchor="middle">15</SvgText></>}
    {name === 'filter' && <Path d="M4 7h16M7 12h10M10 17h4" {...stroke} />}
    {name === 'bellOff' && <><Path d="M8.7 3.9A6 6 0 0 1 18 9c0 3.2.6 5 1.3 6.2M6.3 6.3A6 6 0 0 0 6 9c0 7-3 7-3 9h15" {...stroke} /><Path d="M10 21h4M3 3l18 18" {...stroke} /></>}
    {name === 'shield' && <><Path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.3 7.5 9.5 4.4-1.2 7.5-4.9 7.5-9.5V6Z" {...stroke} /><Path d="m8.8 12 2.2 2.2 4.3-4.4" {...stroke} /></>}
    {name === 'bolt' && <Path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12Z" {...stroke} />}
    {name === 'info' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M12 11v5.5M12 7.6h.01" {...stroke} /></>}
    {name === 'bell' && <><Path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" {...stroke} /><Path d="M10 21h4" {...stroke} /></>}
    {name === 'chevron' && <Path d="m9 5 7 7-7 7" {...stroke} />}
    {name === 'chevronDown' && <Path d="m5 9 7 7 7-7" {...stroke} />}
    {name === 'close' && <Path d="m6 6 12 12M18 6 6 18" {...stroke} />}
    {name === 'calendar' && <><Rect x="3" y="5" width="18" height="16" rx="2" {...stroke} /><Path d="M7 3v4m10-4v4M3 10h18m-13 4h2m4 0h2m-8 3h2" {...stroke} /></>}
    {(name === 'bookmark' || name === 'saved') && <Path d="M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4Z" {...stroke} fill={filled ? color : 'none'} />}
    {name === 'clock' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M12 7v5l3 2" {...stroke} /></>}
    {name === 'play' && <Path d="m8 5 12 7-12 7Z" fill={color} />}
    {name === 'pause' && <><Rect x="6" y="4" width="4" height="16" rx="1.5" fill={color} /><Rect x="14" y="4" width="4" height="16" rx="1.5" fill={color} /></>}
    {name === 'audio' && <Path d="M4 10v4m4-8v12m4-16v20m4-15v10m4-7v4" {...stroke} />}
    {name === 'home' && <Path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" {...stroke} />}
    {name === 'explore' && <><Rect x="3" y="3" width="7" height="7" rx="1.4" {...stroke} /><Rect x="14" y="3" width="7" height="7" rx="1.4" {...stroke} /><Rect x="3" y="14" width="7" height="7" rx="1.4" {...stroke} /><Rect x="14" y="14" width="7" height="7" rx="1.4" {...stroke} /></>}
    {name === 'profile' && <><Circle cx="12" cy="8" r="4" {...stroke} /><Path d="M4 21a8 8 0 0 1 16 0" {...stroke} /></>}
    {name === 'topic' && <><Path d="M4 18V9m5 9V5m5 13v-6m5 6V7" {...stroke} /><Path d="m3 7 6-3 5 4 7-5" {...stroke} /></>}
    {name === 'settings' && <><Circle cx="12" cy="12" r="3.2" {...stroke} /><Path d="M9.81 4.93 L10.09 2.59 L13.91 2.59 L14.19 4.93 A7.4 7.4 0 0 1 15.45 5.45L15.45 5.45 L17.30 4.00 L20.00 6.70 L18.55 8.55 A7.4 7.4 0 0 1 19.07 9.81L19.07 9.81 L21.41 10.09 L21.41 13.91 L19.07 14.19 A7.4 7.4 0 0 1 18.55 15.45L18.55 15.45 L20.00 17.30 L17.30 20.00 L15.45 18.55 A7.4 7.4 0 0 1 14.19 19.07L14.19 19.07 L13.91 21.41 L10.09 21.41 L9.81 19.07 A7.4 7.4 0 0 1 8.55 18.55L8.55 18.55 L6.70 20.00 L4.00 17.30 L5.45 15.45 A7.4 7.4 0 0 1 4.93 14.19L4.93 14.19 L2.59 13.91 L2.59 10.09 L4.93 9.81 A7.4 7.4 0 0 1 5.45 8.55L5.45 8.55 L4.00 6.70 L6.70 4.00 L8.55 5.45 A7.4 7.4 0 0 1 9.81 4.93Z" {...stroke} /></>}
    {name === 'ball' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="m12 7.5 3.4 2.5-1.3 4h-4.2l-1.3-4ZM12 3v4.5m3.4 2.5 5-1.6m-6.3 5.6 3 4.2M9.9 14l-3 4.2M8.6 10l-5-1.6" {...stroke} /></>}
    {name === 'trending' && <Path d="M3 17l6-6 4 4 8-8M14 7h7v7" {...stroke} />}
    {name === 'moon' && <Path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a6.8 6.8 0 0 0 10.7 10.7Z" {...stroke} />}
    {name === 'sun' && <><Circle cx="12" cy="12" r="4" {...stroke} /><Path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" {...stroke} /></>}
    {name === 'lock' && <><Rect x="4" y="10" width="16" height="11" rx="2" {...stroke} /><Path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" {...stroke} /></>}
    {name === 'card' && <><Rect x="3" y="5" width="18" height="14" rx="2" {...stroke} /><Path d="M3 10h18m-14 5h4" {...stroke} /></>}
    {name === 'help' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M9.6 9a2.5 2.5 0 1 1 4.2 1.8c-1 .9-1.8 1.2-1.8 2.7m0 3h.01" {...stroke} /></>}
    {name === 'message' && <><Path d="M4 5h16v12H9l-5 4Z" {...stroke} /><Path d="M8 9h8m-8 4h5" {...stroke} /></>}
    {name === 'camera' && <><Path d="M4 8h3l1.5-2h7L17 8h3v11H4Z" {...stroke} /><Circle cx="12" cy="13" r="3.2" {...stroke} /></>}
    {name === 'edit' && <><Path d="m4 16.5-.8 4.3 4.3-.8L20 7.5 16.5 4Z" {...stroke} /><Path d="m14.8 5.7 3.5 3.5" {...stroke} /></>}
    {name === 'share' && <><Path d="M12 15V3m-4 4 4-4 4 4" {...stroke} /><Path d="M5 12v8h14v-8" {...stroke} /></>}
    {name === 'more' && <><Circle cx="5" cy="12" r="1" fill={color} /><Circle cx="12" cy="12" r="1" fill={color} /><Circle cx="19" cy="12" r="1" fill={color} /></>}
    {name === 'dots' && <><Circle cx="5" cy="12" r="1.5" fill={color} /><Circle cx="12" cy="12" r="1.5" fill={color} /><Circle cx="19" cy="12" r="1.5" fill={color} /></>}
    {name === 'headphones' && <><Path d="M4 13v-2a8 8 0 0 1 16 0v2" {...stroke} /><Path d="M4 13h3v7H6a2 2 0 0 1-2-2Zm16 0h-3v7h1a2 2 0 0 0 2-2Z" {...stroke} /></>}
    {name === 'speed' && <><Path d="M4.5 18a9 9 0 1 1 15 0" {...stroke} /><Path d="m12 13 4-4m-9 9h10" {...stroke} /><Circle cx="12" cy="13" r="1.2" fill={color} /></>}
    {name === 'article' && <><Path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" {...stroke} /><Path d="M14 3v5h5M8 12h8m-8 4h8" {...stroke} /></>}
    {name === 'check' && <Path d="m5 12 4 4L19 6" {...stroke} />}
    {name === 'checkCircle' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="m7.5 12 3 3 6-6" {...stroke} /></>}
    {name === 'arrowUpRight' && <Path d="M7 17 17 7M8 7h9v9" {...stroke} />}
    {name === 'stop' && <Rect x="6" y="6" width="12" height="12" rx="2" fill={color} />}
    {(name === 'radio' || name === 'radioActive') && <><Circle cx="12" cy="12" r="8.5" {...stroke} />{name === 'radioActive' && <Circle cx="12" cy="12" r="4" fill={color} />}</>}
    {name === 'globe' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M3.5 12h17M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" {...stroke} /></>}
    {name === 'rewind' && <><Path d="M3 11a9 9 0 1 1 2.2 6" {...stroke} /><Path d="M3 5v6h6m3-4-4 5 4 5" {...stroke} /></>}
    {name === 'forward' && <><Path d="M21 11a9 9 0 1 0-2.2 6" {...stroke} /><Path d="M21 5v6h-6m-3-4 4 5-4 5" {...stroke} /></>}
    {name === 'previous' && <><Path d="M5 5v14" {...stroke} /><Path d="m19 5-10 7 10 7Z" fill={color} /></>}
    {name === 'next' && <><Path d="M19 5v14" {...stroke} /><Path d="m5 5 10 7-10 7Z" fill={color} /></>}
    {name === 'volume' && <><Path d="M4 10v4h3l5 4V6l-5 4Z" {...stroke} /><Path d="M16 9a5 5 0 0 1 0 6m2.5-8a8 8 0 0 1 0 10" {...stroke} /></>}
    {name === 'cpu' && <><Rect x="6" y="6" width="12" height="12" rx="2" {...stroke} /><Rect x="9" y="9" width="6" height="6" rx="1" {...stroke} /><Path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4" {...stroke} /></>}
    {name === 'brain' && <Path d="M12 4a3 3 0 0 0-5.5 1.6 3 3 0 0 0-2 5.3 3 3 0 0 0 1.8 5.4A3 3 0 0 0 12 19Zm0 0a3 3 0 0 1 5.5 1.6 3 3 0 0 1 2 5.3 3 3 0 0 1-1.8 5.4A3 3 0 0 1 12 19m0-15v16m-4-9h4m4 3h-4" {...stroke} />}
    {name === 'growth' && <><Path d="M4 20V12m5 8V8m5 12v-5m5 5V5" {...stroke} /><Path d="m3 8 6-3 5 4 7-6" {...stroke} /></>}
    {name === 'coins' && <><EllipseLike color={color} stroke={stroke} /></>}
    {name === 'landmark' && <><Path d="M3 9h18L12 4 3 9Zm2 2v8m4-8v8m6-8v8m4-8v8M3 21h18" {...stroke} /></>}
    {name === 'heart' && <Path d="M20.8 4.6a5.4 5.4 0 0 0-7.6 0L12 5.8l-1.2-1.2a5.4 5.4 0 0 0-7.6 7.6l1.2 1.2L12 21l7.6-7.6 1.2-1.2a5.4 5.4 0 0 0 0-7.6Z" {...stroke} />}
    {name === 'leaf' && <><Path d="M20 4C11 4 5 7 5 14a6 6 0 0 0 6 6c7 0 9-8 9-16Z" {...stroke} /><Path d="M4 21c3-6 7-9 13-13" {...stroke} /></>}
    {name === 'sparkles' && <><Path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5Z" {...stroke} /><Path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8Z" {...stroke} /></>}
    {name === 'trash' && <><Path d="M4 7h16M10 3h4a1 1 0 0 1 1 1v3H9V4a1 1 0 0 1 1-1Z" {...stroke} /><Path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M10 11v6m4-6v6" {...stroke} /></>}
    {name === 'flag' && <Path d="M5 21V4m0 0h11l-2 4 2 4H5" {...stroke} />}
    {name === 'layers' && <><Path d="m12 3 9 5-9 5-9-5Z" {...stroke} /><Path d="m3 13 9 5 9-5" {...stroke} /></>}
    {name === 'mic' && <><Rect x="9" y="3" width="6" height="11" rx="3" {...stroke} /><Path d="M5 11a7 7 0 0 0 14 0M12 18v3" {...stroke} /></>}
    {name === 'image' &&<><Rect x="3" y="4" width="18" height="16" rx="2" {...stroke} /><Circle cx="8.5" cy="9" r="1.5" {...stroke} /><Path d="m4 17 5-5 3.5 3 3.5-4 4 4" {...stroke} /></>}
    {(name === 'ratingGreat' || name === 'ratingGood' || name === 'ratingNeutral' || name === 'ratingBad' || name === 'ratingPoor') && <>
      <Circle cx="12" cy="12" r="9" {...stroke} />
      <Circle cx="9" cy="10" r=".8" fill={color} /><Circle cx="15" cy="10" r=".8" fill={color} />
      {name === 'ratingGreat' && <Path d="M7 13c1 3 2.7 4.5 5 4.5s4-1.5 5-4.5" {...stroke} />}
      {name === 'ratingGood' && <Path d="M8 14c1 2 2.3 3 4 3s3-1 4-3" {...stroke} />}
      {name === 'ratingNeutral' && <Path d="M8 15h8" {...stroke} />}
      {name === 'ratingBad' && <Path d="M8 17c1-2 2.3-3 4-3s3 1 4 3" {...stroke} />}
      {name === 'ratingPoor' && <><Path d="m7.5 8 2 1m7-1-2 1M8 18c1-2.5 2.3-3.5 4-3.5s3 1 4 3.5" {...stroke} /></>}
    </>}
  </Svg>;
}

function EllipseLike({ color, stroke }: { color: string; stroke: { stroke: string; strokeWidth: number; strokeLinecap: 'round'; strokeLinejoin: 'round'; fill: string } }) {
  return <><Path d="M5 7c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3Zm0 0v4c0 1.7 3.1 3 7 3s7-1.3 7-3V7m-14 4v4c0 1.7 3.1 3 7 3s7-1.3 7-3v-4m-14 4v2c0 1.7 3.1 3 7 3s7-1.3 7-3v-2" {...stroke} /><Circle cx="18" cy="17" r="3.5" fill={color} /><Path d="M18 15v4m-2-2h4" stroke="#FFFFFF" strokeWidth={1.2} strokeLinecap="round" /></>;
}
