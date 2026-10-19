import React from 'react';
import { Animated, Easing, PanResponder, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { isLiquidGlassSupported, LiquidGlassView } from '@callstack/liquid-glass';
import { DarkTheme, DefaultTheme, NavigationContainer, useIsFocused, useNavigation, type Theme as NavigationTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator, type BottomTabBarProps, type BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { Briefing, BriefingItem, SavedCollection, SavedTopicSummary, Topic, User } from '../types/api';
import { CollectionScreen } from '../components/Collections';
import { KeywordAlertsScreen } from '../components/PersonalAlerts';
import { useTheme } from '../theme';
import { VoiceSettingsScreen } from '../components/VoiceSettingsScreen';
import { OnboardingScreen } from '../components/OnboardingScreen';
import { AuthEntryScreen, CreateAccountScreen, ForgotPasswordScreen, LoginScreen, type AuthStackParamList } from '../components/AuthScreens';
import { MiniAudioPlayer } from '../components/MiniAudioPlayer';
import { ArticleLoadState } from '../components/ArticleDetailScreen';
import { AccountScreen } from '../components/AccountScreen';
import { HistoryScreen } from '../components/HistoryScreen';
import { NotificationSettingsScreen } from '../components/NotificationSettingsScreen';
import { AppearanceScreen } from '../components/AppearanceScreen';
import { FootballScreen } from '../components/FootballScreen';
import { FootballTablesScreen } from '../components/FootballTablesScreen';
import { FavoriteTeamsScreen } from '../components/FavoriteTeamsScreen';
import { SubscriptionScreen } from '../components/SubscriptionScreen';
import { getAudioContext, sameBriefing, subscribeAudio } from '../audio/player';
import { startContentRevisionMonitor } from '../services/contentRevision';
import { PremiumHost, startEntitlementsMonitor } from '../services/premium';
import { startIosWidgets } from '../services/iosWidgets';
import '../audio/queue';
import { TopicFeedScreen } from '../components/HomeScreen';
import { BrandPage, BrandPageHeader, ScreenState } from '../components/ScreenPrimitives';
import { listenForDeepLinks, navigationRef, setMainFlowReady } from './notificationRouting';
import { Icon } from '../components/Icon';
import { ProfileScreen, SecurityPrivacyScreen } from '../components/ProfileScreen';
import { DailyBriefingSettingsScreen } from '../components/DailyBriefingSettingsScreen';
import { EditProfileScreen } from '../components/EditProfileScreen';
import { ContentPreferencesScreen } from '../components/ContentPreferencesScreen';
import { AudioExpandedScreen, DetailScreen, ExploreScreen, SavedContentScreen, SavedScreen, SavedTopicsScreen, TodayScreen } from '../screens/ScreenViews';

export type RootAuthState = 'BOOTING' | 'AUTHENTICATED' | 'UNAUTHENTICATED';
export type MainStackParamList = { Tabs: undefined; Detail: { item?: BriefingItem; storyId?: string; trackReadingProgress?: boolean; readingProgress?: number }; SavedTopics: undefined; SavedContent: { topic?: SavedTopicSummary }; EditProfile: undefined; ContentPreferences: undefined; DailyBriefing: undefined; SecurityPrivacy: undefined; Subscription: undefined; AudioExpanded: { briefing?: Briefing; briefingId?: string }; History: undefined; TopicFeed: { topic: Topic }; NotificationSettings: undefined; Appearance: undefined; VoiceSettings: undefined; Football: { matchAudio?: number } | undefined; FootballTables: { code?: string } | undefined; FavoriteTeams: undefined; Account: undefined; SavedCollection: { collection: SavedCollection }; KeywordAlerts: undefined };
type MainTabParamList = { Inicio: undefined; Explorar: undefined; Salvos: undefined; Perfil: undefined };
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const OnboardingStack = createNativeStackNavigator();
const MainStack = createNativeStackNavigator<MainStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();
// Space between the floating tab bar and each side of the screen.
const TAB_BAR_SIDE = 14;
// Inner padding of the bar, width of the player slot in the middle and size of the selection bubble.
const TAB_BAR_INSET = 8;
const TAB_PLAYER_SLOT = 68;
const TAB_BAR_HEIGHT = 68;
const TAB_BUBBLE_HEIGHT = 56;

const TAB_ITEMS = [
  { name: 'Inicio' as const, icon: 'home' as const, label: 'Início' },
  { name: 'Explorar' as const, icon: 'explore' as const, label: 'Explorar' },
  { name: 'Salvos' as const, icon: 'saved' as const, label: 'Salvos' },
  { name: 'Perfil' as const, icon: 'profile' as const, label: 'Perfil' },
];

/** Floating tab bar. On iOS 26 it is clear Liquid Glass; a glass bubble sits behind the chosen tab and, as in
    WhatsApp, grows under the finger, follows it across the bar and settles on the tab where the finger lifts. */
function FloatingTabBar({ props, onAudio, onExpand, showMini }: { props: BottomTabBarProps; onAudio: () => void; onExpand: (briefing: Briefing) => void; showMini: boolean }) {
  const { colors, dark } = useTheme();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const tabsFocused = useIsFocused();
  const [audioPlaying, setAudioPlaying] = React.useState(false);
  React.useEffect(() => subscribeAudio(state => setAudioPlaying(state.playing)), []);
  const onHome = props.state.routes[props.state.index]?.name === 'Inicio';
  const routes = TAB_ITEMS.map(item => props.state.routes.find(route => route.name === item.name)!);
  const focusedIndex = Math.max(0, routes.findIndex(route => route.key === props.state.routes[props.state.index]?.key));

  // Geometry of the row inside the bar: two tabs, the player slot, two tabs.
  const rowWidth = width - TAB_BAR_SIDE * 2 - TAB_BAR_INSET * 2;
  const tabWidth = (rowWidth - TAB_PLAYER_SLOT) / 4;
  const bubbleWidth = Math.min(tabWidth - 4, 84);
  const slotLeft = (index: number) => index * tabWidth + (index >= 2 ? TAB_PLAYER_SLOT : 0);
  const bubbleLeft = (index: number) => slotLeft(index) + (tabWidth - bubbleWidth) / 2;

  const bubbleX = React.useRef(new Animated.Value(bubbleLeft(focusedIndex))).current;
  const pressed = React.useRef(new Animated.Value(0)).current;
  const [hover, setHover] = React.useState<number | null>(null);
  const dragging = React.useRef(false);

  const select = (index: number) => {
    const route = routes[index];
    const event = props.navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
    if (index !== focusedIndex && !event.defaultPrevented) props.navigation.navigate(route.name, route.params);
  };
  const settle = (index: number) => Animated.spring(bubbleX, { toValue: bubbleLeft(index), useNativeDriver: true, speed: 18, bounciness: 7 }).start();
  React.useEffect(() => { if (!dragging.current) settle(focusedIndex); }, [focusedIndex, width]); // eslint-disable-line react-hooks/exhaustive-deps

  // The responder reads the latest geometry and focus through this ref.
  const live = React.useRef({ tabWidth, bubbleWidth, rowWidth, focusedIndex, select, settle, bubbleLeft });
  live.current = { tabWidth, bubbleWidth, rowWidth, focusedIndex, select, settle, bubbleLeft };
  const responder = React.useRef((() => {
    const rowX = (pageX: number) => pageX - TAB_BAR_SIDE - TAB_BAR_INSET;
    const inPlayer = (x: number) => { const { tabWidth: w } = live.current; return x >= w * 2 && x <= w * 2 + TAB_PLAYER_SLOT; };
    const nearest = (x: number) => {
      let best = 0;
      [0, 1, 2, 3].forEach(index => {
        const { tabWidth: w } = live.current;
        const center = (i: number) => i * w + (i >= 2 ? TAB_PLAYER_SLOT : 0) + w / 2;
        if (Math.abs(center(index) - x) < Math.abs(center(best) - x)) best = index;
      });
      return best;
    };
    const follow = (x: number) => {
      const { bubbleWidth: b, rowWidth: r } = live.current;
      bubbleX.setValue(Math.min(Math.max(x - b / 2, 0), r - b));
      const index = nearest(x);
      setHover(current => current === index ? current : index);
    };
    const release = (x: number | null) => {
      dragging.current = false;
      Animated.spring(pressed, { toValue: 0, useNativeDriver: true, speed: 16, bounciness: 6 }).start();
      setHover(null);
      if (x === null) { live.current.settle(live.current.focusedIndex); return; }
      const index = nearest(x);
      live.current.settle(index);
      live.current.select(index);
    };
    return PanResponder.create({
      // Touches on the player in the middle stay with its own button.
      onStartShouldSetPanResponder: event => !inPlayer(rowX(event.nativeEvent.pageX)),
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: event => {
        dragging.current = true;
        Animated.spring(pressed, { toValue: 1, useNativeDriver: true, speed: 22, bounciness: 8 }).start();
        const x = rowX(event.nativeEvent.pageX);
        const index = nearest(x);
        setHover(index);
        Animated.spring(bubbleX, { toValue: live.current.bubbleLeft(index), useNativeDriver: true, speed: 22, bounciness: 6 }).start();
      },
      onPanResponderMove: (_, gesture) => follow(rowX(gesture.moveX)),
      onPanResponderRelease: (event, gesture) => release(rowX(gesture.moveX || event.nativeEvent.pageX)),
      onPanResponderTerminate: () => release(null),
    });
  })()).current;

  const glass = isLiquidGlassSupported;
  const bubbleColor = dark ? 'rgba(255,255,255,0.16)' : glass ? 'rgba(120,120,128,0.18)' : 'rgba(8,124,240,0.10)';
  const bubbleStyle = {
    transform: [
      { translateX: bubbleX },
      { scaleX: pressed.interpolate({ inputRange: [0, 1], outputRange: [1, 1.16] }) },
      { scaleY: pressed.interpolate({ inputRange: [0, 1], outputRange: [1, 1.1] }) },
    ],
    opacity: pressed.interpolate({ inputRange: [0, 1], outputRange: [1, .85] }),
  };
  const shown = hover ?? focusedIndex;
  const tab = (index: number) => {
    const item = TAB_ITEMS[index];
    const active = shown === index;
    return <View key={item.name} accessible accessibilityRole="button" accessibilityLabel={item.label} accessibilityState={{ selected: index === focusedIndex }}
      onAccessibilityTap={() => select(index)} style={{ width: tabWidth, height: TAB_BUBBLE_HEIGHT, alignItems: 'center', justifyContent: 'center', gap: 2 }}>
      <Icon name={item.icon} color={active ? colors.primary : colors.tabIdle} size={22} />
      <Text style={{ color: active ? colors.primary : colors.tabIdle, fontFamily: 'Inter', fontWeight: active ? '700' : '500', fontSize: 10 }}>{item.label}</Text>
    </View>;
  };
  return <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, paddingBottom: Math.max(insets.bottom, 8), alignItems: 'center' }}>
    {showMini && <MiniAudioPlayer onExpand={onExpand} />}
    {/* Clear, interactive glass with a bright rim on iOS 26; a solid surface elsewhere. */}
    <LiquidGlassView effect={glass ? 'clear' : 'none'} interactive={glass} colorScheme={dark ? 'dark' : 'light'}
      tintColor={glass ? (dark ? 'rgba(20,28,44,0.18)' : 'rgba(255,255,255,0.10)') : undefined}
      style={{ width: width - TAB_BAR_SIDE * 2, alignSelf: 'center', height: TAB_BAR_HEIGHT, borderRadius: TAB_BAR_HEIGHT / 2, justifyContent: 'center',
        backgroundColor: glass ? 'transparent' : colors.surface,
        borderWidth: glass ? 1 : StyleSheet.hairlineWidth, borderColor: glass ? (dark ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.7)') : colors.border,
        shadowColor: colors.shadow.color, shadowOpacity: dark ? .4 : glass ? .14 : .24, shadowRadius: 22, shadowOffset: { width: 0, height: 10 }, elevation: 14 }}>
      <View {...responder.panHandlers} style={{ marginHorizontal: TAB_BAR_INSET, flexDirection: 'row', alignItems: 'center' }}>
        <Animated.View pointerEvents="none" style={[{ position: 'absolute', left: 0, top: 0, width: bubbleWidth, height: TAB_BUBBLE_HEIGHT, borderRadius: TAB_BUBBLE_HEIGHT / 2, backgroundColor: bubbleColor,
          borderWidth: glass ? StyleSheet.hairlineWidth : 0, borderColor: dark ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.8)' }, bubbleStyle]} />
        {tab(0)}{tab(1)}
        <View style={{ width: TAB_PLAYER_SLOT, alignItems: 'center' }}><PressAudio onPress={onAudio} active={audioPlaying && onHome && tabsFocused} /></View>
        {tab(2)}{tab(3)}
      </View>
    </LiquidGlassView>
  </View>;
}
/** Central player button; pulses while the daily briefing is playing on the Home tab. */
function PressAudio({ onPress, active }: { onPress: () => void; active: boolean }) {
  const { colors } = useTheme();
  const pulse = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    if (!active) { pulse.stopAnimation(); pulse.setValue(0); return; }
    const loop = Animated.loop(Animated.timing(pulse, { toValue: 1, duration: 1400, easing: Easing.out(Easing.ease), useNativeDriver: true }));
    loop.start();
    return () => { loop.stop(); pulse.setValue(0); };
  }, [active, pulse]);
  const ring = { transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.45] }) }], opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [active ? .45 : 0, 0] }) };
  const button = { transform: [{ scale: pulse.interpolate({ inputRange: [0, .5, 1], outputRange: [1, 1.07, 1] }) }] };
  return <View style={{ width: 54, height: 54, alignItems: 'center', justifyContent: 'center' }}>
    <Animated.View pointerEvents="none" style={[{ position: 'absolute', width: 54, height: 54, borderRadius: 27, backgroundColor: colors.primary }, ring]} />
    <Animated.View style={button}>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir player de áudio" onPress={onPress} style={{ width: 54, height: 54, borderRadius: 27, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', shadowColor: colors.primary, shadowOpacity: .35, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 6 }}><Icon name="audio" color={colors.onPrimary} size={27} /></Pressable>
    </Animated.View>
  </View>;
}

function MainTabs({ onAuthExpired, onLogout, user }: { onAuthExpired: () => void; onLogout: () => void; user: User | null }) {
  const navigation = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const [latestBriefing, setLatestBriefing] = React.useState<Briefing | null>(null);
  const showAudio = () => { const loaded = getAudioContext()?.briefing; const current = loaded && latestBriefing && loaded.id === latestBriefing.id && !sameBriefing(loaded, latestBriefing) ? latestBriefing : loaded; const briefing = current || latestBriefing; briefing ? navigation.navigate('AudioExpanded', { briefing }) : navigation.navigate('History'); };
  return <Tabs.Navigator tabBar={props => <FloatingTabBar props={props} onAudio={showAudio} onExpand={briefing => navigation.navigate('AudioExpanded', { briefing })} showMini={props.state.routes[props.state.index]?.name !== 'Inicio'} />}
    screenOptions={{ headerShown: false, tabBarStyle: { position: 'absolute', height: 82, backgroundColor: 'transparent', borderTopWidth: 0, elevation: 0 } }}>
    <Tabs.Screen name="Inicio" options={{ title: 'Início', tabBarAccessibilityLabel: 'Início' }}>{() => <TodayTab user={user} onAuthExpired={onAuthExpired} onLatestBriefing={setLatestBriefing} />}</Tabs.Screen>
    <Tabs.Screen name="Explorar" options={{ title: 'Explorar', tabBarAccessibilityLabel: 'Explorar' }}>{() => <ExploreTab user={user} />}</Tabs.Screen>
    <Tabs.Screen name="Salvos" options={{ title: 'Salvos', tabBarAccessibilityLabel: 'Salvos' }}>{() => <SavedTab />}</Tabs.Screen>
    <Tabs.Screen name="Perfil" options={{ title: 'Perfil', tabBarAccessibilityLabel: 'Perfil' }}>{() => <ProfileTab user={user} onLogout={onLogout} />}</Tabs.Screen>
  </Tabs.Navigator>;
}
function TodayTab({ onAuthExpired, user, onLatestBriefing }: { onAuthExpired: () => void; user: User | null; onLatestBriefing: (briefing: Briefing | null) => void }) {
  const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>();
  const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>();
  return <TodayScreen user={user} onAuthExpired={onAuthExpired} onLatestBriefing={onLatestBriefing}
    onDetail={item => parent?.navigate('Detail', { item })} onAudio={briefing => parent?.navigate('AudioExpanded', { briefing })}
    onHistory={() => parent?.navigate('History')}
    onProfile={() => parent?.navigate('Account')}
    onExplore={() => navigation.navigate('Explorar')} onSchedule={() => parent?.navigate('DailyBriefing')}
    onTopic={topic => parent?.navigate('TopicFeed', { topic })} />;
}
function ExploreTab({ user }: { user: User | null }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ExploreScreen user={user} onTopic={topic => parent?.navigate('TopicFeed', { topic })} onDetail={item => parent?.navigate('Detail', { item })} onProfile={() => parent?.navigate('Account')} onFootball={() => parent?.navigate('Football')} onEditTopics={() => parent?.navigate('ContentPreferences')} />; }
function SavedTab() { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); const focused = useIsFocused(); return <SavedScreen refreshOnFocus={focused} onDetail={(item, progress) => parent?.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => parent?.navigate('AudioExpanded', { briefing })} onProfile={() => parent?.navigate('Account')} onSeeAll={() => parent?.navigate('SavedContent', {})} onSeeTopics={() => parent?.navigate('SavedTopics')} onTopic={topic => parent?.navigate('SavedContent', { topic })} onCollection={collection => parent?.navigate('SavedCollection', { collection })} />; }
function ProfileTab({ user, onLogout }: { user: User | null; onLogout: () => void }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ProfileScreen user={user} onNavigate={route => parent?.navigate(route as never)} onLogout={onLogout} />; }
function DetailScreenRoute({ route, navigation }: any) {
  const [item, setItem] = React.useState<BriefingItem | null>(route.params?.item || null);
  const [loading, setLoading] = React.useState(!route.params?.item);
  const [error, setError] = React.useState('');
  const [retry, setRetry] = React.useState(0);
  React.useEffect(() => {
    let active = true;
    if (route.params?.item) { setItem(route.params.item); setLoading(false); setError(''); return () => { active = false; }; }
    const storyId = route.params?.storyId;
    if (!storyId) { setLoading(false); setError('O conteúdo desta notícia não está disponível.'); return () => { active = false; }; }
    setItem(null); setLoading(true); setError('');
    import('../api/client').then(({ api }) => api.story(storyId)).then(result => {
      if (!active) return;
      setItem(result.item); setLoading(false);
    }).catch(() => { if (active) { setLoading(false); setError('Verifique sua conexão e tente novamente.'); } });
    return () => { active = false; };
  }, [route.params?.item, route.params?.storyId, retry]);
  if (!item) return <ArticleLoadState onBack={() => navigation.goBack()} onRetry={() => setRetry(value => value + 1)} loading={loading} error={error} />;
  return <DetailScreen item={item} onBack={() => navigation.goBack()} onRelated={story => navigation.navigate('Detail', { item: story })} onTopic={topic => navigation.navigate('TopicFeed', { topic })} onBriefing={briefing => briefing.id ? navigation.navigate('AudioExpanded', { briefing }) : navigation.navigate('History')} trackReadingProgress={!!route.params?.trackReadingProgress} readingProgress={route.params?.readingProgress || 0} />;
}

/** The briefing player, also reachable from a daily-briefing push that carries only the delivery id. */
function AudioExpandedRoute({ briefing, briefingId, ...actions }: { briefing?: Briefing; briefingId?: string; onBack: () => void; onDetail: (item: BriefingItem) => void; onHome: () => void; onSchedule: () => void; onAdvance: (briefing: Briefing) => void }) {
  const [loaded, setLoaded] = React.useState<Briefing | null>(briefing || null);
  const [error, setError] = React.useState(false);
  const [retry, setRetry] = React.useState(0);
  React.useEffect(() => {
    if (briefing) { setLoaded(briefing); return; }
    if (!briefingId) { setError(true); return; }
    let active = true;
    setError(false);
    import('../api/client').then(({ api }) => api.briefing(briefingId)).then(result => { if (active) setLoaded(result as Briefing); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [briefing, briefingId, retry]);
  if (loaded) return <AudioExpandedScreen briefing={loaded} {...actions} />;
  return <BrandPage><BrandPageHeader title="Seu resumo" onBack={actions.onBack} />
    {error ? <ScreenState kind="error" title="Resumo indisponível" message="Verifique sua conexão e tente novamente." onRetry={() => setRetry(value => value + 1)} />
      : <ScreenState kind="loading" title="Carregando seu resumo" />}
  </BrandPage>;
}

function MainFlow({ onAuthExpired, onLogout, onUserUpdated, user }: { onAuthExpired: () => void; onLogout: () => void; onUserUpdated: (user: User) => void; user: User | null }) {
  React.useEffect(() => startContentRevisionMonitor(), []);
  React.useEffect(() => startEntitlementsMonitor(), []);
  React.useEffect(() => startIosWidgets(), []);
  React.useEffect(() => listenForDeepLinks(), []);
  React.useEffect(() => { setMainFlowReady(true); return () => setMainFlowReady(false); }, []);
  return <><MainStack.Navigator screenOptions={{ headerShown: false }}>
    <MainStack.Screen name="Tabs">{() => <MainTabs user={user} onAuthExpired={onAuthExpired} onLogout={onLogout} />}</MainStack.Screen>
    <MainStack.Screen name="TopicFeed">{({ route, navigation }) => <TopicFeedScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={item => navigation.navigate('Detail', { item })} />}</MainStack.Screen>
    <MainStack.Screen name="EditProfile">{({ navigation }) => <EditProfileScreen user={user} onBack={() => navigation.goBack()} onSaved={updated => { onUserUpdated(updated); navigation.goBack(); }} />}</MainStack.Screen>
    <MainStack.Screen name="ContentPreferences">{({ navigation }) => <ContentPreferencesScreen onBack={() => navigation.goBack()} onDone={() => navigation.navigate('Tabs' as never, { screen: 'Inicio' } as never)} />}</MainStack.Screen>
    <MainStack.Screen name="DailyBriefing">{({ navigation }) => <DailyBriefingSettingsScreen onBack={() => navigation.goBack()} onVoice={() => navigation.navigate('VoiceSettings')} onSubscription={() => navigation.navigate('Subscription')} />}</MainStack.Screen>
    <MainStack.Screen name="SecurityPrivacy">{({ navigation }) => <SecurityPrivacyScreen onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="Subscription">{({ navigation }) => <SubscriptionScreen onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="SavedTopics">{({ navigation }) => <SavedTopicsScreen onBack={() => navigation.goBack()} onSelect={topic => navigation.navigate('SavedContent', { topic })} />}</MainStack.Screen>
    <MainStack.Screen name="SavedCollection">{({ route, navigation }) => <CollectionScreen collection={route.params.collection} onBack={() => navigation.goBack()} onDetail={(item, progress) => navigation.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} />}</MainStack.Screen>
    <MainStack.Screen name="SavedContent">{({ route, navigation }) => <SavedContentScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={(item, progress) => navigation.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} />}</MainStack.Screen>
    <MainStack.Screen name="Detail">
      {({ route, navigation }) => <DetailScreenRoute route={route} navigation={navigation} />}
    </MainStack.Screen>
    <MainStack.Screen name="AudioExpanded">
      {({ route, navigation }) => <AudioExpandedRoute briefing={route.params.briefing} briefingId={route.params.briefingId} onBack={() => navigation.goBack()}
        onDetail={item => navigation.navigate('Detail', { item })}
        onHome={() => navigation.navigate('Tabs' as never, { screen: 'Inicio' } as never)}
        onSchedule={() => navigation.navigate('DailyBriefing')}
        onAdvance={next => navigation.setParams({ briefing: next, briefingId: undefined })} />}
    </MainStack.Screen>
    <MainStack.Screen name="History">
      {({ navigation }) => <HistoryScreen onBack={() => navigation.goBack()}
        onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} onDetail={item => navigation.navigate('Detail', { item })} />}
    </MainStack.Screen>
    <MainStack.Screen name="NotificationSettings">
      {({ navigation }) => <NotificationSettingsScreen onBack={() => navigation.goBack()} onKeywords={() => navigation.navigate('KeywordAlerts')} />}
    </MainStack.Screen>
    <MainStack.Screen name="KeywordAlerts">{({ navigation }) => <KeywordAlertsScreen onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="Football">
      {({ navigation, route }) => <FootballScreen onBack={() => navigation.goBack()} onTables={code => navigation.navigate('FootballTables', { code })} onFavorites={() => navigation.navigate('FavoriteTeams')}
        matchAudio={route.params?.matchAudio} onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} />}
    </MainStack.Screen>
    <MainStack.Screen name="FootballTables">{({ navigation, route }) => <FootballTablesScreen initialCode={route.params?.code} onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="FavoriteTeams">{({ navigation }) => <FavoriteTeamsScreen onBack={() => navigation.goBack()} onSubscription={() => navigation.navigate('Subscription')} />}</MainStack.Screen>
    <MainStack.Screen name="Appearance">
      {({ navigation }) => <AppearanceScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="VoiceSettings">
      {({ navigation }) => <VoiceSettingsScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="Account">
      {({ navigation }) => <AccountScreen onBack={() => navigation.goBack()} onEditProfile={() => navigation.navigate('EditProfile')} onAccountDeleted={onLogout} />}
    </MainStack.Screen>
  </MainStack.Navigator><PremiumHost /></>;
}
/** Screen backgrounds during transitions follow the app theme (no white flash in dark mode). */
function navigationTheme(theme: ReturnType<typeof useTheme>): NavigationTheme {
  const base = theme.dark ? DarkTheme : DefaultTheme;
  return { ...base, colors: { ...base.colors, background: theme.colors.background, card: theme.colors.surface, text: theme.colors.textPrimary, border: theme.colors.border, primary: theme.colors.primary } };
}

export function RootNavigator({ authState, needsOnboarding, user, bootstrapError, onRetrySession, onAuthenticated, onOnboardingDone, onLogout, onAuthExpired, onUserUpdated }: { authState: RootAuthState; needsOnboarding: boolean; user: User | null; bootstrapError: string; onRetrySession: () => void; onAuthenticated: (user: User) => Promise<void>; onOnboardingDone: (user: User) => void; onLogout: () => void; onAuthExpired: () => void; onUserUpdated: (user: User) => void }) { const theme = useTheme(); return <SafeAreaProvider><NavigationContainer ref={navigationRef} theme={navigationTheme(theme)}>{authState === 'UNAUTHENTICATED' && <AuthStack.Navigator screenOptions={{ headerShown: false }}><AuthStack.Screen name="AuthEntry">{props => <AuthEntryScreen {...props} bootstrapError={bootstrapError} onRetrySession={onRetrySession} />}</AuthStack.Screen><AuthStack.Screen name="Login">{props => <LoginScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="CreateAccount">{props => <CreateAccountScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} /></AuthStack.Navigator>}{authState === 'AUTHENTICATED' && needsOnboarding && <OnboardingStack.Navigator screenOptions={{ headerShown: false }}><OnboardingStack.Screen name="Onboarding">{() => <OnboardingScreen onDone={onOnboardingDone} />}</OnboardingStack.Screen></OnboardingStack.Navigator>}{authState === 'AUTHENTICATED' && !needsOnboarding && user && <MainFlow user={user} onAuthExpired={onAuthExpired} onLogout={onLogout} onUserUpdated={onUserUpdated} />}</NavigationContainer></SafeAreaProvider>; }
