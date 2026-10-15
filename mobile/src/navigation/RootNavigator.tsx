import React from 'react';
import { Animated, Easing, Pressable, Text, View } from 'react-native';
import { DarkTheme, DefaultTheme, NavigationContainer, useIsFocused, useNavigation, type Theme as NavigationTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator, type BottomTabBarProps, type BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { Briefing, BriefingItem, SavedTopicSummary, Topic, User } from '../types/api';
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
import { SubscriptionScreen } from '../components/SubscriptionScreen';
import { getAudioContext, sameBriefing, subscribeAudio } from '../audio/player';
import { startContentRevisionMonitor } from '../services/contentRevision';
import { SearchScreen, TopicFeedScreen } from '../components/HomeScreen';
import { AppNotices } from '../components/AppNotices';
import { BrandPage, BrandPageHeader, ScreenState } from '../components/ScreenPrimitives';
import { navigationRef, setMainFlowReady } from './notificationRouting';
import { Icon } from '../components/Icon';
import { ContentPreferencesScreen, DailyBriefingSettingsScreen, EditProfileScreen, ProfileScreen, SecurityPrivacyScreen } from '../components/ProfileScreen';
import { AudioExpandedScreen, DetailScreen, ExploreScreen, SavedContentScreen, SavedScreen, SavedTopicsScreen, TodayScreen } from '../screens/ScreenViews';

export type RootAuthState = 'BOOTING' | 'AUTHENTICATED' | 'UNAUTHENTICATED';
export type MainStackParamList = { Tabs: undefined; Detail: { item?: BriefingItem; storyId?: string; trackReadingProgress?: boolean; readingProgress?: number }; SavedTopics: undefined; SavedContent: { topic?: SavedTopicSummary }; EditProfile: undefined; ContentPreferences: undefined; DailyBriefing: undefined; SecurityPrivacy: undefined; Subscription: undefined; AudioExpanded: { briefing?: Briefing; briefingId?: string }; History: undefined; Search: undefined; TopicFeed: { topic: Topic }; NotificationSettings: undefined; Appearance: undefined; VoiceSettings: undefined; Football: undefined; Account: undefined };
type MainTabParamList = { Inicio: undefined; Explorar: undefined; Salvos: undefined; Perfil: undefined };
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const OnboardingStack = createNativeStackNavigator();
const MainStack = createNativeStackNavigator<MainStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();

function FloatingTabBar({ props, onAudio, onExpand, showMini }: { props: BottomTabBarProps; onAudio: () => void; onExpand: (briefing: Briefing) => void; showMini: boolean }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const tabsFocused = useIsFocused();
  const [audioPlaying, setAudioPlaying] = React.useState(false);
  React.useEffect(() => subscribeAudio(state => setAudioPlaying(state.playing)), []);
  const onHome = props.state.routes[props.state.index]?.name === 'Inicio';
  const tabItems = [
    { route: props.state.routes.find(item => item.name === 'Inicio')!, icon: 'home' as const, label: 'Início' },
    { route: props.state.routes.find(item => item.name === 'Explorar')!, icon: 'explore' as const, label: 'Explorar' },
    null,
    { route: props.state.routes.find(item => item.name === 'Salvos')!, icon: 'saved' as const, label: 'Salvos' },
    { route: props.state.routes.find(item => item.name === 'Perfil')!, icon: 'profile' as const, label: 'Perfil' },
  ];
  return <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, paddingBottom: Math.max(insets.bottom, 8), alignItems: 'center' }}>
    {showMini && <MiniAudioPlayer onExpand={onExpand} />}
    <View style={{ width: '80%', alignSelf: 'center', height: 66, borderRadius: 34, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', paddingHorizontal: 2, shadowColor: colors.shadow.color, shadowOpacity: .16, shadowRadius: 16, shadowOffset: { width: 0, height: 5 }, elevation: 8 }}>
      {tabItems.map(item => {
        if (!item) return <PressAudio key="audio" onPress={onAudio} active={audioPlaying && onHome && tabsFocused} />;
        const focused = props.state.index === props.state.routes.findIndex(route => route.key === item.route.key);
        return <Pressable key={item.route.key} accessibilityRole="button" accessibilityLabel={item.label} accessibilityState={{ selected: focused }} onPress={() => {
          const event = props.navigation.emit({ type: 'tabPress', target: item.route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) props.navigation.navigate(item.route.name, item.route.params);
        }} style={{ flex: 1, height: 60, alignItems: 'center', justifyContent: 'center', gap: 2 }}>
          <Icon name={item.icon} color={focused ? colors.primary : colors.tabIdle} size={22} />
          <Text style={{ color: focused ? colors.primary : colors.tabIdle, fontFamily: 'Inter', fontWeight: focused ? '700' : '500', fontSize: 10 }}>{item.label}</Text>
        </Pressable>;
      })}
    </View>
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
    <Tabs.Screen name="Perfil" options={{ title: 'Perfil', tabBarAccessibilityLabel: 'Perfil' }}>{() => <ProfileTab user={user} onSearch={() => navigation.navigate('Search')} onLogout={onLogout} />}</Tabs.Screen>
  </Tabs.Navigator>;
}
function TodayTab({ onAuthExpired, user, onLatestBriefing }: { onAuthExpired: () => void; user: User | null; onLatestBriefing: (briefing: Briefing | null) => void }) {
  const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>();
  const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>();
  return <TodayScreen user={user} onAuthExpired={onAuthExpired} onLatestBriefing={onLatestBriefing}
    onDetail={item => parent?.navigate('Detail', { item })} onAudio={briefing => parent?.navigate('AudioExpanded', { briefing })}
    onHistory={() => parent?.navigate('History')} onSearch={() => parent?.navigate('Search')}
    onProfile={() => parent?.navigate('Account')}
    onExplore={() => navigation.navigate('Explorar')} onSchedule={() => parent?.navigate('DailyBriefing')}
    onTopic={topic => parent?.navigate('TopicFeed', { topic })} />;
}
function ExploreTab({ user }: { user: User | null }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ExploreScreen user={user} onTopic={topic => parent?.navigate('TopicFeed', { topic })} onDetail={item => parent?.navigate('Detail', { item })} onProfile={() => parent?.navigate('Account')} onFootball={() => parent?.navigate('Football')} />; }
function SavedTab() { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); const focused = useIsFocused(); return <SavedScreen refreshOnFocus={focused} onDetail={(item, progress) => parent?.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => parent?.navigate('AudioExpanded', { briefing })} onSearch={() => parent?.navigate('Search')} onProfile={() => parent?.navigate('Account')} onSeeAll={() => parent?.navigate('SavedContent', {})} onSeeTopics={() => parent?.navigate('SavedTopics')} onTopic={topic => parent?.navigate('SavedContent', { topic })} />; }
function ProfileTab({ user, onSearch, onLogout }: { user: User | null; onSearch: () => void; onLogout: () => void }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ProfileScreen user={user} onNavigate={route => parent?.navigate(route as never)} onSearch={onSearch} onLogout={onLogout} />; }
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
function AudioExpandedRoute({ briefing, briefingId, ...actions }: { briefing?: Briefing; briefingId?: string; onBack: () => void; onDetail: (item: BriefingItem) => void; onHome: () => void; onSchedule: () => void }) {
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
  React.useEffect(() => { setMainFlowReady(true); return () => setMainFlowReady(false); }, []);
  return <><MainStack.Navigator screenOptions={{ headerShown: false }}>
    <MainStack.Screen name="Tabs">{() => <MainTabs user={user} onAuthExpired={onAuthExpired} onLogout={onLogout} />}</MainStack.Screen>
    <MainStack.Screen name="Search">{({ navigation }) => <SearchScreen onBack={() => navigation.goBack()} onDetail={item => navigation.navigate('Detail', { item })} />}</MainStack.Screen>
    <MainStack.Screen name="TopicFeed">{({ route, navigation }) => <TopicFeedScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={item => navigation.navigate('Detail', { item })} />}</MainStack.Screen>
    <MainStack.Screen name="EditProfile">{({ navigation }) => <EditProfileScreen user={user} onBack={() => navigation.goBack()} onSaved={updated => { onUserUpdated(updated); navigation.goBack(); }} />}</MainStack.Screen>
    <MainStack.Screen name="ContentPreferences">{({ navigation }) => <ContentPreferencesScreen onBack={() => navigation.goBack()} onDone={() => navigation.navigate('Tabs' as never, { screen: 'Inicio' } as never)} />}</MainStack.Screen>
    <MainStack.Screen name="DailyBriefing">{({ navigation }) => <DailyBriefingSettingsScreen onBack={() => navigation.goBack()} onVoice={() => navigation.navigate('VoiceSettings')} onSubscription={() => navigation.navigate('Subscription')} />}</MainStack.Screen>
    <MainStack.Screen name="SecurityPrivacy">{({ navigation }) => <SecurityPrivacyScreen onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="Subscription">{({ navigation }) => <SubscriptionScreen onBack={() => navigation.goBack()} />}</MainStack.Screen>
    <MainStack.Screen name="SavedTopics">{({ navigation }) => <SavedTopicsScreen onBack={() => navigation.goBack()} onSelect={topic => navigation.navigate('SavedContent', { topic })} />}</MainStack.Screen>
    <MainStack.Screen name="SavedContent">{({ route, navigation }) => <SavedContentScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={(item, progress) => navigation.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} />}</MainStack.Screen>
    <MainStack.Screen name="Detail">
      {({ route, navigation }) => <DetailScreenRoute route={route} navigation={navigation} />}
    </MainStack.Screen>
    <MainStack.Screen name="AudioExpanded">
      {({ route, navigation }) => <AudioExpandedRoute briefing={route.params.briefing} briefingId={route.params.briefingId} onBack={() => navigation.goBack()}
        onDetail={item => navigation.navigate('Detail', { item })}
        onHome={() => navigation.navigate('Tabs' as never, { screen: 'Inicio' } as never)}
        onSchedule={() => navigation.navigate('DailyBriefing')} />}
    </MainStack.Screen>
    <MainStack.Screen name="History">
      {({ navigation }) => <HistoryScreen onBack={() => navigation.goBack()}
        onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} />}
    </MainStack.Screen>
    <MainStack.Screen name="NotificationSettings">
      {({ navigation }) => <NotificationSettingsScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="Football">
      {({ navigation }) => <FootballScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="Appearance">
      {({ navigation }) => <AppearanceScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="VoiceSettings">
      {({ navigation }) => <VoiceSettingsScreen onBack={() => navigation.goBack()} />}
    </MainStack.Screen>
    <MainStack.Screen name="Account">
      {({ navigation }) => <AccountScreen onBack={() => navigation.goBack()} onEditProfile={() => navigation.navigate('EditProfile')} />}
    </MainStack.Screen>
  </MainStack.Navigator><AppNotices /></>;
}
/** Screen backgrounds during transitions follow the app theme (no white flash in dark mode). */
function navigationTheme(theme: ReturnType<typeof useTheme>): NavigationTheme {
  const base = theme.dark ? DarkTheme : DefaultTheme;
  return { ...base, colors: { ...base.colors, background: theme.colors.background, card: theme.colors.surface, text: theme.colors.textPrimary, border: theme.colors.border, primary: theme.colors.primary } };
}

export function RootNavigator({ authState, needsOnboarding, user, bootstrapError, onRetrySession, onAuthenticated, onOnboardingDone, onLogout, onAuthExpired, onUserUpdated }: { authState: RootAuthState; needsOnboarding: boolean; user: User | null; bootstrapError: string; onRetrySession: () => void; onAuthenticated: (user: User) => Promise<void>; onOnboardingDone: (user: User) => void; onLogout: () => void; onAuthExpired: () => void; onUserUpdated: (user: User) => void }) { const theme = useTheme(); return <SafeAreaProvider><NavigationContainer ref={navigationRef} theme={navigationTheme(theme)}>{authState === 'UNAUTHENTICATED' && <AuthStack.Navigator screenOptions={{ headerShown: false }}><AuthStack.Screen name="AuthEntry">{props => <AuthEntryScreen {...props} bootstrapError={bootstrapError} onRetrySession={onRetrySession} />}</AuthStack.Screen><AuthStack.Screen name="Login">{props => <LoginScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="CreateAccount">{props => <CreateAccountScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} /></AuthStack.Navigator>}{authState === 'AUTHENTICATED' && needsOnboarding && <OnboardingStack.Navigator screenOptions={{ headerShown: false }}><OnboardingStack.Screen name="Onboarding">{() => <OnboardingScreen onDone={onOnboardingDone} />}</OnboardingStack.Screen></OnboardingStack.Navigator>}{authState === 'AUTHENTICATED' && !needsOnboarding && user && <MainFlow user={user} onAuthExpired={onAuthExpired} onLogout={onLogout} onUserUpdated={onUserUpdated} />}</NavigationContainer></SafeAreaProvider>; }
