export type User = {
  id: string;
  email: string;
  display_name: string;
  created_at?: string | null;
  language?: string;
  timezone?: string;
  status?: 'ACTIVE' | 'DISABLED';
  onboarding_status?: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  /** Uploaded profile photo, a path on the API (/api/v1/avatars/…). */
  photo_url?: string | null;
};

export type Session = { token: string; expires_at: string };
export type Topic = { id?: string; code: string; name: string; label?: string; description?: string; aliases?: string[]; depth?: number; path?: string[]; children?: string[]; parent_id?: string | null; type?: string; enabled?: boolean; order?: number; content_count?: number };
export type ClientConfig = { supported_languages: string[]; supported_briefing_sizes: number[]; country_scopes: string[]; topics: Topic[] };
export type Preferences = { user_id?: string; topics: string[]; content_scope?: 'selected' | 'all'; language: string; country_scope: 'LOCAL' | 'GLOBAL' | 'BOTH'; briefing_time: string; timezone: string; briefing_size: 5 | 10 | 15; audio_enabled: boolean; audio_voice_id?: string | null; briefing_length?: BriefingLength; next_briefing?: NextBriefing };
/** Premium: 'extended' narrates more of each story and what other outlets added. */
export type BriefingLength = 'standard' | 'extended';
/** When the next new briefing arrives; once today's is made, a new time only starts tomorrow. */
export type NextBriefing = { date: string; time: string; day: 'TODAY' | 'TOMORROW'; slot?: number };
export type AudioVoice = { id: string; name: string; description: string; language: string; gender: 'female' | 'male'; preview_url: string };
export type AudioVoiceCatalog = { voices: AudioVoice[]; default_voice_id: string | null; preview_text?: string };
export type Onboarding = { status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED'; preferences: Preferences };
export type BriefingSource = { name?: string; publisher?: string; url: string; article_id?: string; published_at?: string };
export type BriefingItem = { id: string; position: number; headline: string; summary: string; category?: string | null; primary_taxonomy_id?: string | null; primary_taxonomy_label?: string | null; why_it_matters?: string | null; key_points: string[]; confidence?: number; evidence_quality?: string; warnings?: string[]; summary_provider?: string; sources: BriefingSource[]; published_at?: string | null; image_url?: string | null; reading_time_minutes?: number; trending?: { rank: number; outlets: number } };
export type Briefing = { profile_stale?: boolean; id?: string; delivery_id?: string; edition_id?: string; date: string; status: 'PENDING' | 'CONTENT_READY' | 'AUDIO_QUEUED' | 'GENERATING' | 'READY' | 'FAILED'; content_status?: string; audio_status?: string; selected_voice_id?: string | null; active_voice_id?: string | null; audio_variant_id?: string | null; active_audio_variant_id?: string | null; audio_url?: string | null; script_id?: string | null; generation_stage?: string | null; generation_started_at?: string | null; generation_updated_at?: string | null; generation_error_code?: string | null; generated_at?: string | null; audio_duration_ms?: number | null; listening_progress_seconds?: number; listening_duration_seconds?: number; completed_at?: string | null; items: BriefingItem[]; slot?: number; kind?: BriefingKind; theme?: string | null; theme_label?: string | null; delivery_time?: string; narration?: 'standard' | 'extended' | 'saved' };
/** SCHEDULED: the daily briefing; EXTRA: the day's 2nd or 3rd (Premium); ON_DEMAND: "Gerar agora" (Premium). */
export type BriefingKind = 'SCHEDULED' | 'EXTRA' | 'ON_DEMAND';
export type BriefingHistoryPage = { items: Briefing[]; next_cursor: string | null; limited?: { days: number; older_count: number } };
export type BriefingSearchResult = { briefing_id: string; date: string; slot: number; kind: BriefingKind; theme_label?: string | null; delivery_time?: string; item: BriefingItem };
export type ExtraBriefing = { slot: number; time: string; theme: string | null; theme_label?: string | null; length: BriefingLength; enabled: boolean; active?: boolean };
export type BriefingSlots = { main: { slot: 1; time: string; length: BriefingLength }; extra: ExtraBriefing[]; limit: number; premium: boolean };
export type GenerationStatus = { generation_id: string; reason: string; status: 'PENDING' | 'GENERATING' | 'READY' | 'FAILED'; stage: string; delivery_id?: string | null; error_code?: string | null; remaining_today?: number; coalesced?: boolean };
export type NotificationSettings = { notifications_enabled: boolean; daily_briefing_enabled: boolean; breaking_news_enabled: boolean; briefing_time?: string | null; briefing_size?: number | null;
  breaking_news_rules?: { min_sources: number; quiet_hours: { start: number; end: number } | null }; active_devices?: number;
  keyword_alerts_enabled?: boolean; story_updates_enabled?: boolean; team_reminder_enabled?: boolean; live_activities_enabled?: boolean };
export type NotificationSwitches = Pick<NotificationSettings, 'notifications_enabled' | 'daily_briefing_enabled' | 'breaking_news_enabled' | 'keyword_alerts_enabled' | 'story_updates_enabled'>;
export type SavedTopicSummary = { id: string; name: string; count: number; order: number };
export type SavedArticle = BriefingItem & { saved_at?: string; reading_progress?: number; reading_updated_at?: string | null };
export type SavedOverviewItem = { type: 'article'; saved_at: string; item: BriefingItem; reading_progress: number } | { type: 'briefing'; saved_at: string; briefing: Briefing };
export type SavedOverview = { saved_count: number; continue_reading: SavedArticle | null; topic_summary: SavedTopicSummary[]; recent_items: SavedOverviewItem[]; collections?: SavedCollection[] };
export type SavedStoryPage = { items: SavedArticle[]; next_cursor: string | null };
export type HomeData = { preferences: Preferences; today_briefing: Briefing; latest_briefing: Briefing | null; topics: Topic[]; latest_news: BriefingItem[]; trending?: BriefingItem[]; saved_story_ids: string[] };
export type AudioSegment = { id: string; position: number; type: 'INTRO' | 'ITEM' | 'OUTRO' | string; briefing_item_id?: string | null; script_text?: string; segment_start_ms?: number | null; segment_end_ms?: number | null };
export type AudioMetadata = { status: 'NOT_AVAILABLE' | 'PENDING' | 'GENERATING' | 'VALIDATING' | 'READY' | 'FAILED' | 'OFFLINE'; audio_status?: string; selected_voice_id?: string | null; active_voice_id?: string | null; active_audio_variant_id?: string | null; audio_variant_id?: string | null; generation_stage?: string | null; generation_started_at?: string | null; generation_updated_at?: string | null; generation_error_code?: string | null; edition_id?: string; audio_url?: string; duration_ms?: number; audio_duration_ms?: number; size_bytes?: number; mime_type?: string; language?: string; voice?: string; resolved_voice?: string | null; provider?: string; generated_at?: string; asset_version?: string; artifact_id?: string; error_code?: string | null; script_id?: string; segments?: AudioSegment[] };
export type FootballCompetition = { code: string; name: string; table?: boolean };
export type FootballMatch = { id: number; kickoff: string; status: string; matchday: number | null; competition?: FootballCompetition; home: string; away: string; home_tla?: string; away_tla?: string; home_goals: number | null; away_goals: number | null;
  home_id?: number | null; away_id?: number | null; home_crest?: string | null; away_crest?: string | null };
export type FootballOverview = ({ available: true; live: FootballMatch[]; upcoming: FootballMatch[]; competitions: FootballCompetition[] } | { available: false; reason: string })
  & { favorite_team_ids?: number[]; followed_match_ids?: number[] };
export type FootballStandingRow = { position: number; team: string; team_id?: number | null; tla: string; crest?: string | null; played: number | null; won: number | null; draw: number | null; lost: number | null; goal_difference: number | null; points: number | null;
  form?: ('W' | 'D' | 'L')[]; zone?: 'libertadores' | 'pre_libertadores' | 'sul_americana' | 'relegation' | null };
export type FootballStandings = { available: true; competition: FootballCompetition; season?: string | null; matchday: number | null; groups: { name: string | null; rows: FootballStandingRow[] }[] } | { available: false; reason: string };
export type FootballRound = { available: true; competition: FootballCompetition; matchday: number | null; current_matchday: number | null; matchdays: number[]; matches: FootballMatch[] } | { available: false; reason: string };
export type FootballTeam = { id: number; name: string; tla: string | null; crest: string | null; competitions: FootballCompetition[] };
export type FootballAlerts = { kickoff: boolean; goals: boolean; final: boolean; news: boolean; reminder?: boolean; live_activities?: boolean };
export type FootballFavorites = { teams: FootballTeam[]; limit: number; alerts: FootballAlerts; followed_matches: number[] };
export type SubscriptionPlan = { id: string; name: string; price: string; per: string; monthly_equivalent?: string; savings_percent?: number };
export type Subscription = {
  tier: 'basic' | 'premium'; period: string | null; status: string; expires_at: string | null; will_renew: boolean; payment_issue: boolean;
  limits: PlanLimits; usage: { briefing_times: number }; entitlements?: Entitlements; benefits: { title: string; detail: string }[]; plans: SubscriptionPlan[]; purchases_enabled: boolean;
  legal?: { terms_url?: string | null; privacy_url?: string | null };
};
export type PremiumFeatureId = 'extra_briefings' | 'themed_briefings' | 'on_demand_briefing' | 'extended_briefing' | 'offline_downloads' | 'audio_queue'
  | 'premium_widgets' | 'live_activities' | 'team_reminders' | 'match_audio' | 'keyword_alerts' | 'story_follow' | 'collections' | 'full_history' | 'briefing_search';
export type PlanLimits = { briefing_times: number; favorite_teams: number; history_days: number | null; on_demand_per_day: number; keyword_alerts: number; followed_stories: number; collections: number };
/** What the account may use; decided by the server (PREMIUM_ENFORCED off: everything for everyone). */
export type Entitlements = { premium: boolean; enforced: boolean; limits: PlanLimits; features: Record<PremiumFeatureId, boolean> };
export type SavedCollection = { id: string; name: string; count: number; cover_image_url: string | null; created_at: string };
export type KeywordAlert = { id: string; keyword: string; created_at: string };
export type FollowedStory = { story_id: string; headline: string; until: string; last_update_at: string };
export type ReadyAudio = { status: 'READY' | 'PENDING' | 'GENERATING' | 'VALIDATING' | 'FAILED' | 'NOT_AVAILABLE' | 'EMPTY'; audio_url?: string; duration_ms?: number | null };
export type SavedAudio = ReadyAudio & { story_count: number; edition_id?: string; stories?: { id: string; headline: string }[] };
export type MatchAudio = ReadyAudio & { match_id: number };
export type ApiError = { error: { code: string; message: string; request_id?: string; feature?: PremiumFeatureId } };
