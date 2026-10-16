import type { NextBriefing } from '../types/api';

const systemTimezone =() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Sao_Paulo';

export function greetingForLocalTime(now: Date, timeZone = systemTimezone()) {
  const hour = Number(new Intl.DateTimeFormat('en-US', { timeZone, hour: '2-digit', hourCycle: 'h23' }).format(now));
  if (hour >= 5 && hour < 12) return 'Bom dia,';
  if (hour >= 12 && hour < 18) return 'Boa tarde,';
  return 'Boa noite,';
}

export function formatHomeDate(now: Date, timeZone = systemTimezone()) {
  return new Intl.DateTimeFormat('pt-BR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone,
  }).format(now);
}

/** `next` comes from the backend: once today's briefing is made, a new time only starts tomorrow. */
export function nextBriefingLabel(time: string, timeZone: string, now: Date, next?: NextBriefing | null) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  const [hour, minute] = (time || '06:30').split(':').map(Number);
  const currentMinutes = Number(values.hour) * 60 + Number(values.minute);
  const todayPending = !next || next.date === `${values.year}-${values.month}-${values.day}`;
  return `${todayPending && currentMinutes < hour * 60 + minute ? 'Hoje' : 'Amanhã'} às ${time || '06:30'}`;
}
