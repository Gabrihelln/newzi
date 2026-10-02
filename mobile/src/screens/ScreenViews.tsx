import React from 'react';
import type { HomeScreenProps } from '../components/HomeScreen';
import { HomeScreen } from '../components/HomeScreen';
import { BriefingAudioScreen } from '../components/BriefingAudioScreen';
import { ArticleDetailScreen } from '../components/ArticleDetailScreen';
import type { Briefing, BriefingItem, Topic } from '../types/api';

export { SavedScreen, SavedContentScreen, SavedTopicsScreen } from '../components/SavedScreen';
export { ExploreScreen } from '../components/ExploreScreen';

const noop = () => undefined;

export function TodayScreen(props: Partial<HomeScreenProps> & Pick<HomeScreenProps, 'onDetail' | 'onAuthExpired'>) {
  return <HomeScreen user={props.user || null} onDetail={props.onDetail} onAuthExpired={props.onAuthExpired}
    onAudio={props.onAudio || noop} onHistory={props.onHistory || noop} onSearch={props.onSearch || noop}
    onProfile={props.onProfile || noop} onExplore={props.onExplore || noop}
    onSchedule={props.onSchedule || noop} onTopic={props.onTopic || noop} onLatestBriefing={props.onLatestBriefing || noop} />;
}

export function AudioExpandedScreen({ briefing, onBack, onDetail, onHome, onSchedule }: {
  briefing: Briefing; onBack: () => void; onDetail: (item: BriefingItem) => void; onHome: () => void; onSchedule: () => void;
}) {
  return <BriefingAudioScreen briefing={briefing} onBack={onBack} onDetail={onDetail} onHome={onHome} onSchedule={onSchedule} />;
}

export function DetailScreen({ item, onBack, onRelated, onTopic, onBriefing, trackReadingProgress = false, readingProgress = 0 }: {
  item: BriefingItem; onBack: () => void; onRelated: (item: BriefingItem) => void; onTopic: (topic: Topic) => void;
  onBriefing: (briefing: Briefing) => void; trackReadingProgress?: boolean; readingProgress?: number;
}) {
  return <ArticleDetailScreen item={item} onBack={onBack} onRelated={onRelated} onTopic={onTopic} onBriefing={onBriefing}
    trackReadingProgress={trackReadingProgress} readingProgress={readingProgress} />;
}
