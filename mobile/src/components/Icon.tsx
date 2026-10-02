import React from 'react';
import Svg, { Circle, Path, Rect } from 'react-native-svg';
import { colors } from '../theme';

export type IconName = 'search' | 'bell' | 'chevron' | 'chevronDown' | 'close' | 'calendar' | 'bookmark' | 'clock' | 'play' | 'pause' | 'audio' | 'home' | 'explore' | 'saved' | 'profile' | 'topic' | 'settings' | 'sun' | 'lock' | 'card' | 'help' | 'message' | 'camera' | 'edit' | 'share' | 'more' | 'dots' | 'headphones' | 'speed' | 'article' | 'check' | 'checkCircle' | 'arrowUpRight' | 'stop' | 'radio' | 'radioActive' | 'globe' | 'rewind' | 'forward' | 'previous' | 'next' | 'volume' | 'cpu' | 'brain' | 'growth' | 'coins' | 'landmark' | 'heart' | 'leaf' | 'sparkles' | 'image' | 'ratingGreat' | 'ratingGood' | 'ratingNeutral' | 'ratingBad' | 'ratingPoor';

export function Icon({ name, color = colors.text, size = 22 }: { name: IconName; color?: string; size?: number }) {
  const stroke = { stroke: color, strokeWidth: 1.9, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return <Svg width={size} height={size} viewBox="0 0 24 24">
    {name === 'search' && <><Circle cx="10.8" cy="10.8" r="7.2" {...stroke} /><Path d="m16 16 5 5" {...stroke} /></>}
    {name === 'bell' && <><Path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" {...stroke} /><Path d="M10 21h4" {...stroke} /></>}
    {name === 'chevron' && <Path d="m9 5 7 7-7 7" {...stroke} />}
    {name === 'chevronDown' && <Path d="m5 9 7 7 7-7" {...stroke} />}
    {name === 'close' && <Path d="m6 6 12 12M18 6 6 18" {...stroke} />}
    {name === 'calendar' && <><Rect x="3" y="5" width="18" height="16" rx="2" {...stroke} /><Path d="M7 3v4m10-4v4M3 10h18m-13 4h2m4 0h2m-8 3h2" {...stroke} /></>}
    {(name === 'bookmark' || name === 'saved') && <Path d="M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4Z" {...stroke} />}
    {name === 'clock' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M12 7v5l3 2" {...stroke} /></>}
    {name === 'play' && <Path d="m8 5 12 7-12 7Z" fill={color} />}
    {name === 'pause' && <><Rect x="6" y="4" width="4" height="16" rx="1.5" fill={color} /><Rect x="14" y="4" width="4" height="16" rx="1.5" fill={color} /></>}
    {name === 'audio' && <Path d="M4 10v4m4-8v12m4-16v20m4-15v10m4-7v4" {...stroke} />}
    {name === 'home' && <Path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" {...stroke} />}
    {name === 'explore' && <><Rect x="3" y="3" width="7" height="7" rx="1.4" {...stroke} /><Rect x="14" y="3" width="7" height="7" rx="1.4" {...stroke} /><Rect x="3" y="14" width="7" height="7" rx="1.4" {...stroke} /><Rect x="14" y="14" width="7" height="7" rx="1.4" {...stroke} /></>}
    {name === 'profile' && <><Circle cx="12" cy="8" r="4" {...stroke} /><Path d="M4 21a8 8 0 0 1 16 0" {...stroke} /></>}
    {name === 'topic' && <><Path d="M4 18V9m5 9V5m5 13v-6m5 6V7" {...stroke} /><Path d="m3 7 6-3 5 4 7-5" {...stroke} /></>}
    {name === 'settings' && <><Circle cx="12" cy="12" r="3.5" {...stroke} /><Path d="m19.4 13.5 1.2.9-1.2 2.1-1.5-.5a7.8 7.8 0 0 1-1.4.8l-.3 1.6h-2.4l-.4-1.6a7.8 7.8 0 0 1-1.5-.1l-1 1.3-2.1-1.2.5-1.5a7.8 7.8 0 0 1-.8-1.4l-1.6-.3v-2.4l1.6-.4c.1-.5.3-1 .6-1.5l-.8-1.4 1.7-1.7 1.4.8c.5-.3 1-.5 1.5-.6l.4-1.6h2.4l.3 1.6c.5.1 1 .4 1.4.7l1.5-.5 1.2 2.1-1.2 1a7.8 7.8 0 0 1 .1 1.6Z" {...stroke} /></>}
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
    {name === 'image' && <><Rect x="3" y="4" width="18" height="16" rx="2" {...stroke} /><Circle cx="8.5" cy="9" r="1.5" {...stroke} /><Path d="m4 17 5-5 3.5 3 3.5-4 4 4" {...stroke} /></>}
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
