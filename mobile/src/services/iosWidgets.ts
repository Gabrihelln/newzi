import { AppState, NativeEventEmitter, NativeModules, Platform } from 'react-native';
import { api } from '../api/client';
import { currentPushToken } from '../push/push';
import type { FootballMatch, HomeData } from '../types/api';
import { getEntitlements } from './premium';

/**
 * iPhone widgets and Live Activities (mobile/ios/NewziWidgets). The app shares what the widgets show through the
 * App Group (NativeModules.NewziWidgets.setData), and keeps the server told about Live Activity tokens so it can
 * start and update a favourite team's game on the lock screen (Premium).
 */
type Bridge = {
  setData?: (json: string) => void;
  liveActivitiesEnabled?: () => Promise<boolean>;
  observeLiveActivities?: () => void;
  startMatch?: (json: string) => Promise<boolean>;
  endMatch?: (matchId: number) => void;
};
const bridge = (): Bridge => (Platform.OS === 'ios' ? NativeModules.NewziWidgets || {} : {}) as Bridge;

type WidgetStory = { id: string; title: string; topic?: string };
type WidgetMatch = { id: number; home: string; away: string; homeTla: string; awayTla: string; homeGoals: number | null; awayGoals: number | null; status: 'SCHEDULED' | 'LIVE' | 'FINISHED'; kickoff: number; competition: string };
type WidgetTeam = { id: number; name: string; tla: string; match?: WidgetMatch };
type WidgetTopic = { id: string; name: string; headlines: WidgetStory[] };

let briefing: { title: string; next: string; headlines: WidgetStory[] } | null = null;
let topics: WidgetTopic[] = [];
let teams: WidgetTeam[] = [];
let lastJson = '';
let topicsLoadedAt = 0;
const TOPICS_EVERY_MS = 30 * 60 * 1000;
const FOOTBALL_EVERY_MS = 5 * 60 * 1000;

const storyOf = (item: { id: string; headline: string; primary_taxonomy_label?: string | null; category?: string | null; sources?: { article_id?: string }[] }): WidgetStory => ({
  // Widgets open the article (newzi://story/ID): a briefing item points to its first article.
  id: item.sources?.find(source => source.article_id)?.article_id || item.id, title: item.headline, topic: item.primary_taxonomy_label || item.category || undefined,
});

function publish() {
  const write = bridge().setData;
  if (!write) return;
  const payload = { updatedAt: Date.now() / 1000, premium: Boolean(getEntitlements()?.features.premium_widgets), briefing, topics, teams };
  const json = JSON.stringify(payload);
  if (json === lastJson) return;
  lastJson = json;
  write(json);
}

const nextLabel = (home: HomeData) => {
  const next = home.preferences.next_briefing;
  if (!next) return '';
  return `${next.day === 'TODAY' ? 'Hoje' : 'Amanhã'} às ${next.time}`;
};

/** Called by the Home after each load: the briefing's headlines (and, for Premium, the reader's topics). */
export function updateWidgetsFromHome(home: HomeData) {
  if (Platform.OS !== 'ios') return;
  const current = home.today_briefing?.items?.length ? home.today_briefing : home.latest_briefing;
  const source = current?.items?.length ? current.items : home.latest_news;
  briefing = { title: 'Seu resumo diário', next: nextLabel(home), headlines: (source || []).slice(0, 6).map(storyOf) };
  publish();
  if (getEntitlements()?.features.premium_widgets && Date.now() - topicsLoadedAt > TOPICS_EVERY_MS) void loadTopics(home);
}

async function loadTopics(home: HomeData) {
  topicsLoadedAt = Date.now();
  const chosen = home.topics.filter(topic => home.preferences.content_scope === 'all' || home.preferences.topics.includes(topic.code || topic.id || '')).slice(0, 6);
  const loaded: WidgetTopic[] = [];
  for (const topic of chosen) {
    try {
      const result = await api.news(6, { topic: topic.code || topic.id });
      loaded.push({ id: (topic.code || topic.id) as string, name: topic.name, headlines: result.items.slice(0, 6).map(storyOf) });
    } catch { /* keep the others */ }
  }
  if (loaded.length) { topics = loaded; publish(); }
}

const status = (match: FootballMatch): WidgetMatch['status'] => ['IN_PLAY', 'PAUSED'].includes(match.status) ? 'LIVE' : match.status === 'FINISHED' ? 'FINISHED' : 'SCHEDULED';
const widgetMatch = (match: FootballMatch): WidgetMatch => ({
  id: match.id, home: match.home, away: match.away, homeTla: match.home_tla || match.home.slice(0, 3).toUpperCase(), awayTla: match.away_tla || match.away.slice(0, 3).toUpperCase(),
  homeGoals: match.home_goals, awayGoals: match.away_goals, status: status(match), kickoff: Date.parse(match.kickoff) / 1000, competition: match.competition?.name || '',
});

const started = new Set<number>();

/** Favourite teams' next or live games for the team widget, and a Live Activity for each live game (Premium). */
async function refreshFootball() {
  const entitlements = getEntitlements();
  if (!entitlements?.features.premium_widgets && !entitlements?.features.live_activities) return;
  try {
    const [favorites, overview] = await Promise.all([api.footballFavorites(), api.football('explore')]);
    if (!overview.available || !favorites.teams.length) { teams = []; publish(); return; }
    const games = [...overview.live, ...overview.upcoming];
    teams = favorites.teams.map(team => {
      const match = games.find(game => game.home_id === team.id || game.away_id === team.id);
      return { id: team.id, name: team.name, tla: team.tla || team.name.slice(0, 3).toUpperCase(), match: match ? widgetMatch(match) : undefined };
    });
    publish();
    // The app starts the activity of a live game itself too (the server can only start them on iOS 17.2+).
    const start = bridge().startMatch;
    if (!start || !entitlements.features.live_activities || favorites.alerts.live_activities === false) return;
    if (!(await bridge().liveActivitiesEnabled?.().catch(() => false))) return;
    for (const game of overview.live) {
      if (started.has(game.id) || !favorites.teams.some(team => team.id === game.home_id || team.id === game.away_id)) continue;
      const item = widgetMatch(game);
      const json = JSON.stringify({
        attributes: { matchId: item.id, home: item.home, away: item.away, homeTla: item.homeTla, awayTla: item.awayTla, competition: item.competition, kickoff: item.kickoff },
        state: { homeGoals: item.homeGoals ?? 0, awayGoals: item.awayGoals ?? 0, status: item.status, updatedAt: Date.now() / 1000 },
      });
      if (await start(json).catch(() => false)) started.add(game.id);
    }
  } catch { /* offline: the widgets keep the last data */ }
}

/** Live Activity tokens go to the server (with this phone's FCM token, the channel the updates travel through). */
function watchLiveActivityTokens() {
  const native = bridge();
  if (!native.observeLiveActivities || !NativeModules.NewziWidgets) return () => undefined;
  const emitter = new NativeEventEmitter(NativeModules.NewziWidgets);
  const send = async (body: { token: string; matchId?: number }, kind: 'start' | 'update') => {
    if (!getEntitlements()?.features.live_activities) return;
    const pushToken = await currentPushToken();
    if (!pushToken) return;
    api.registerLiveActivityToken({ kind, token: body.token, push_token: pushToken, ...(kind === 'update' ? { match_id: body.matchId } : {}) }).catch(() => undefined);
  };
  const subscriptions = [
    emitter.addListener('liveActivityStartToken', body => void send(body, 'start')),
    emitter.addListener('liveActivityToken', body => void send(body, 'update')),
  ];
  native.observeLiveActivities();
  return () => subscriptions.forEach(subscription => subscription.remove());
}

/** Started by the signed-in app on iPhone: football data for the widgets and Live Activities, every few minutes. */
export function startIosWidgets() {
  if (Platform.OS !== 'ios' || !NativeModules.NewziWidgets) return () => undefined;
  const stopTokens = watchLiveActivityTokens();
  void refreshFootball();
  const timer = setInterval(() => { if (AppState.currentState === 'active') void refreshFootball(); }, FOOTBALL_EVERY_MS);
  const subscription = AppState.addEventListener('change', state => { if (state === 'active') void refreshFootball(); });
  return () => { clearInterval(timer); subscription.remove(); stopTokens(); };
}

/** Signing out clears what the widgets show. */
export function clearIosWidgets() {
  briefing = null; topics = []; teams = []; lastJson = '';
  bridge().setData?.(JSON.stringify({ updatedAt: Date.now() / 1000, premium: false, briefing: null, topics: [], teams: [] }));
}
