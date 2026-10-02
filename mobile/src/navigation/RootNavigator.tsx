import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { NavigationContainer, useIsFocused, useNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator, type BottomTabBarProps, type BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { Briefing, BriefingItem, SavedTopicSummary, Topic, User } from '../types/api';
import { colors } from '../theme';
import { VoiceSettingsScreen } from '../components/VoiceSettingsScreen';
import { OnboardingScreen } from '../components/OnboardingScreen';
import { AuthEntryScreen, CreateAccountScreen, ForgotPasswordScreen, LoginScreen, type AuthStackParamList } from '../components/AuthScreens';
import { MiniAudioPlayer } from '../components/MiniAudioPlayer';
import { ArticleLoadState } from '../components/ArticleDetailScreen';
import { AccountScreen } from '../components/AccountScreen';
import { HistoryScreen } from '../components/HistoryScreen';
import { NotificationSettingsScreen } from '../components/NotificationSettingsScreen';
import { getAudioContext } from '../audio/player';
import { startContentRevisionMonitor } from '../services/contentRevision';
import { SearchScreen, TopicFeedScreen } from '../components/HomeScreen';
import { Icon } from '../components/Icon';
import { ContentPreferencesScreen, DailyBriefingSettingsScreen, EditProfileScreen, ProfileInfoScreen, ProfileScreen, SecurityPrivacyScreen } from '../components/ProfileScreen';
import { AudioExpandedScreen, DetailScreen, ExploreScreen, SavedContentScreen, SavedScreen, SavedTopicsScreen, TodayScreen } from '../screens/ScreenViews';

export type RootAuthState = 'BOOTING' | 'AUTHENTICATED' | 'UNAUTHENTICATED';
export type MainStackParamList = { Tabs: undefined; Detail: { item?: BriefingItem; notificationId?: string; trackReadingProgress?: boolean; readingProgress?: number }; SavedTopics: undefined; SavedContent: { topic?: SavedTopicSummary }; EditProfile: undefined; ContentPreferences: undefined; DailyBriefing: undefined; SecurityPrivacy: undefined; Subscription: undefined; AudioExpanded: { briefing: Briefing }; History: undefined; Search: undefined; TopicFeed: { topic: Topic }; NotificationSettings: undefined; VoiceSettings: undefined; Account: undefined };
type MainTabParamList = { Inicio: undefined; Explorar: undefined; Salvos: undefined; Perfil: undefined };
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const OnboardingStack = createNativeStackNavigator();
const MainStack = createNativeStackNavigator<MainStackParamList>();
const Tabs = createBottomTabNavigator<MainTabParamList>();

function FloatingTabBar({ props, onAudio, onExpand, showMini }: { props: BottomTabBarProps; onAudio: () => void; onExpand: (briefing: Briefing) => void; showMini: boolean }) {
  const insets = useSafeAreaInsets();
  const tabItems = [
    { route: props.state.routes.find(item => item.name === 'Inicio')!, icon: 'home' as const, label: 'Início' },
    { route: props.state.routes.find(item => item.name === 'Explorar')!, icon: 'explore' as const, label: 'Explorar' },
    null,
    { route: props.state.routes.find(item => item.name === 'Salvos')!, icon: 'saved' as const, label: 'Salvos' },
    { route: props.state.routes.find(item => item.name === 'Perfil')!, icon: 'profile' as const, label: 'Perfil' },
  ];
  return <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, paddingBottom: Math.max(insets.bottom, 8), alignItems: 'center' }}>
    {showMini && <MiniAudioPlayer onExpand={onExpand} />}
    <View style={{ width: '80%', alignSelf: 'center', height: 66, borderRadius: 34, backgroundColor: '#FFFFFF', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', paddingHorizontal: 2, shadowColor: '#496B99', shadowOpacity: .16, shadowRadius: 16, shadowOffset: { width: 0, height: 5 }, elevation: 8 }}>
      {tabItems.map(item => {
        if (!item) return <PressAudio key="audio" onPress={onAudio} />;
        const focused = props.state.index === props.state.routes.findIndex(route => route.key === item.route.key);
        return <Pressable key={item.route.key} accessibilityRole="button" accessibilityLabel={item.label} accessibilityState={{ selected: focused }} onPress={() => {
          const event = props.navigation.emit({ type: 'tabPress', target: item.route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) props.navigation.navigate(item.route.name, item.route.params);
        }} style={{ flex: 1, height: 60, alignItems: 'center', justifyContent: 'center', gap: 2 }}>
          <Icon name={item.icon} color={focused ? colors.primary : '#7183A2'} size={22} />
          <Text style={{ color: focused ? colors.primary : '#7183A2', fontFamily: 'Inter', fontWeight: focused ? '700' : '500', fontSize: 10 }}>{item.label}</Text>
        </Pressable>;
      })}
    </View>
  </View>;
}
function PressAudio({ onPress }: { onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel="Abrir player de áudio" onPress={onPress} style={{ width: 54, height: 54, borderRadius: 27, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', shadowColor: colors.primary, shadowOpacity: .35, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 6 }}><Icon name="audio" color="#FFFFFF" size={27} /></Pressable>;
}

function MainTabs({ onAuthExpired, user }: { onAuthExpired: () => void; user: User | null }) {
  const navigation = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const [latestBriefing, setLatestBriefing] = React.useState<Briefing | null>(null);
  const showAudio = () => { const current = getAudioContext()?.briefing; const briefing = current || latestBriefing; briefing ? navigation.navigate('AudioExpanded', { briefing }) : navigation.navigate('History'); };
  return <Tabs.Navigator tabBar={props => <FloatingTabBar props={props} onAudio={showAudio} onExpand={briefing => navigation.navigate('AudioExpanded', { briefing })} showMini={props.state.routes[props.state.index]?.name !== 'Inicio'} />}
    screenOptions={{ headerShown: false, tabBarStyle: { position: 'absolute', height: 82, backgroundColor: 'transparent', borderTopWidth: 0, elevation: 0 } }}>
    <Tabs.Screen name="Inicio" options={{ title: 'Início', tabBarAccessibilityLabel: 'Início' }}>{() => <TodayTab user={user} onAuthExpired={onAuthExpired} onLatestBriefing={setLatestBriefing} />}</Tabs.Screen>
    <Tabs.Screen name="Explorar" options={{ title: 'Explorar', tabBarAccessibilityLabel: 'Explorar' }}>{() => <ExploreTab user={user} />}</Tabs.Screen>
    <Tabs.Screen name="Salvos" options={{ title: 'Salvos', tabBarAccessibilityLabel: 'Salvos' }}>{() => <SavedTab />}</Tabs.Screen>
    <Tabs.Screen name="Perfil" options={{ title: 'Perfil', tabBarAccessibilityLabel: 'Perfil' }}>{() => <ProfileTab user={user} onSearch={() => navigation.navigate('Search')} />}</Tabs.Screen>
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
function ExploreTab({ user }: { user: User | null }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ExploreScreen user={user} onTopic={topic => parent?.navigate('TopicFeed', { topic })} onDetail={item => parent?.navigate('Detail', { item })} onProfile={() => parent?.navigate('Account')} />; }
function SavedTab() { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); const focused = useIsFocused(); return <SavedScreen refreshOnFocus={focused} onDetail={(item, progress) => parent?.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => parent?.navigate('AudioExpanded', { briefing })} onSearch={() => parent?.navigate('Search')} onProfile={() => parent?.navigate('Account')} onSeeAll={() => parent?.navigate('SavedContent', {})} onSeeTopics={() => parent?.navigate('SavedTopics')} onTopic={topic => parent?.navigate('SavedContent', { topic })} />; }
function ProfileTab({ user, onSearch }: { user: User | null; onSearch: () => void }) { const navigation = useNavigation<BottomTabNavigationProp<MainTabParamList>>(); const parent = navigation.getParent<NativeStackNavigationProp<MainStackParamList>>(); return <ProfileScreen user={user} onNavigate={route => parent?.navigate(route as never)} onSearch={onSearch} />; }
function DetailScreenRoute({ route, navigation }: any) {
  const [item, setItem] = React.useState<BriefingItem | null>(route.params?.item || null);
  const [loading, setLoading] = React.useState(!route.params?.item);
  const [error, setError] = React.useState('');
  const [retry, setRetry] = React.useState(0);
  React.useEffect(() => {
    let active = true;
    if (route.params?.item) { setItem(route.params.item); setLoading(false); setError(''); return () => { active = false; }; }
    const notificationId = route.params?.notificationId;
    if (!notificationId) { setLoading(false); setError('O conteúdo desta notícia não está disponível.'); return () => { active = false; }; }
    setItem(null); setLoading(true); setError('');
    import('../api/client').then(({ api }) => api.briefing(notificationId)).then(result => {
      if (!active) return;
      const loaded = result.items?.[0];
      if (!loaded) throw new Error('not found');
      setItem(loaded); setLoading(false);
    }).catch(() => { if (active) { setLoading(false); setError('Verifique sua conexão e tente novamente.'); } });
    return () => { active = false; };
  }, [route.params?.item, route.params?.notificationId, retry]);
  if (!item) return <ArticleLoadState onBack={() => navigation.goBack()} onRetry={() => setRetry(value => value + 1)} loading={loading} error={error} />;
  return <DetailScreen item={item} onBack={() => navigation.goBack()} onRelated={story => navigation.navigate('Detail', { item: story })} onTopic={topic => navigation.navigate('TopicFeed', { topic })} onBriefing={briefing => briefing.id ? navigation.navigate('AudioExpanded', { briefing }) : navigation.navigate('History')} trackReadingProgress={!!route.params?.trackReadingProgress} readingProgress={route.params?.readingProgress || 0} />;
}
function WithMini({ children, navigation }: { children: React.ReactNode; navigation: NativeStackNavigationProp<MainStackParamList> }) {
  const focused = useIsFocused();
  return <View style={{ flex: 1 }}>
    <View style={{ flex: 1 }}>{children}</View>
    {focused && <MiniAudioPlayer onExpand={briefing => navigation.navigate('AudioExpanded', { briefing })} />}
  </View>;
}

function MainFlow({ onAuthExpired, onLogout, onUserUpdated, notificationId, user }: { onAuthExpired: () => void; onLogout: () => void; onUserUpdated: (user: User) => void; notificationId?: string; user: User | null }) {
  React.useEffect(() => startContentRevisionMonitor(), []);
  return <MainStack.Navigator screenOptions={{ headerShown: false }}>
    <MainStack.Screen name="Tabs">{() => <MainTabs user={user} onAuthExpired={onAuthExpired} />}</MainStack.Screen>
    <MainStack.Screen name="Search">{({ navigation }) => <WithMini navigation={navigation}><SearchScreen onBack={() => navigation.goBack()} onDetail={item => navigation.navigate('Detail', { item })} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="TopicFeed">{({ route, navigation }) => <WithMini navigation={navigation}><TopicFeedScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={item => navigation.navigate('Detail', { item })} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="EditProfile">{({ navigation }) => <WithMini navigation={navigation}><EditProfileScreen user={user} onBack={() => navigation.goBack()} onSaved={updated => { onUserUpdated(updated); navigation.goBack(); }} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="ContentPreferences">{({ navigation }) => <WithMini navigation={navigation}><ContentPreferencesScreen onBack={() => navigation.goBack()} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="DailyBriefing">{({ navigation }) => <WithMini navigation={navigation}><DailyBriefingSettingsScreen onBack={() => navigation.goBack()} onVoice={() => navigation.navigate('VoiceSettings')} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="SecurityPrivacy">{({ navigation }) => <WithMini navigation={navigation}><SecurityPrivacyScreen onBack={() => navigation.goBack()} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="Subscription">{({ navigation }) => <WithMini navigation={navigation}><ProfileInfoScreen title="Assinatura e plano" message="Planos e pagamentos ainda não estão disponíveis nesta versão do Newzi." onBack={() => navigation.goBack()} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="SavedTopics">{({ navigation }) => <WithMini navigation={navigation}><SavedTopicsScreen onBack={() => navigation.goBack()} onSelect={topic => navigation.navigate('SavedContent', { topic })} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="SavedContent">{({ route, navigation }) => <WithMini navigation={navigation}><SavedContentScreen topic={route.params.topic} onBack={() => navigation.goBack()} onDetail={(item, progress) => navigation.navigate('Detail', { item, trackReadingProgress: true, readingProgress: progress })} onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} /></WithMini>}</MainStack.Screen>
    <MainStack.Screen name="Detail" initialParams={notificationId ? { notificationId } : undefined}>
      {({ route, navigation }) => <WithMini navigation={navigation}><DetailScreenRoute route={route} navigation={navigation} /></WithMini>}
    </MainStack.Screen>
    <MainStack.Screen name="AudioExpanded">
      {({ route, navigation }) => <AudioExpandedScreen briefing={route.params.briefing} onBack={() => navigation.goBack()}
        onDetail={item => navigation.navigate('Detail', { item })}
        onHome={() => navigation.navigate('Tabs' as never, { screen: 'Inicio' } as never)}
        onSchedule={() => navigation.navigate('DailyBriefing')} />}
    </MainStack.Screen>
    <MainStack.Screen name="History">
      {({ navigation }) => <WithMini navigation={navigation}><HistoryScreen onBack={() => navigation.goBack()}
        onAudio={briefing => navigation.navigate('AudioExpanded', { briefing })} /></WithMini>}
    </MainStack.Screen>
    <MainStack.Screen name="NotificationSettings">
      {({ navigation }) => <WithMini navigation={navigation}><NotificationSettingsScreen onBack={() => navigation.goBack()} /></WithMini>}
    </MainStack.Screen>
    <MainStack.Screen name="VoiceSettings">
      {({ navigation }) => <WithMini navigation={navigation}><VoiceSettingsScreen onBack={() => navigation.goBack()} /></WithMini>}
    </MainStack.Screen>
    <MainStack.Screen name="Account">
      {({ navigation }) => <WithMini navigation={navigation}><AccountScreen onBack={() => navigation.goBack()} onLogout={onLogout} onEditProfile={() => navigation.navigate('EditProfile')} /></WithMini>}
    </MainStack.Screen>
  </MainStack.Navigator>;
}
export function RootNavigator({ authState, needsOnboarding, user, pendingBriefingId, bootstrapError, onRetrySession, onAuthenticated, onOnboardingDone, onLogout, onAuthExpired, onUserUpdated }: { authState: RootAuthState; needsOnboarding: boolean; user: User | null; bootstrapError: string; onRetrySession: () => void; onAuthenticated: (user: User) => Promise<void>; onOnboardingDone: (user: User) => void; onLogout: () => void; onAuthExpired: () => void; onUserUpdated: (user: User) => void; pendingBriefingId?: string }) { return <SafeAreaProvider><NavigationContainer>{authState === 'UNAUTHENTICATED' && <AuthStack.Navigator screenOptions={{ headerShown: false }}><AuthStack.Screen name="AuthEntry">{props => <AuthEntryScreen {...props} bootstrapError={bootstrapError} onRetrySession={onRetrySession} />}</AuthStack.Screen><AuthStack.Screen name="Login">{props => <LoginScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="CreateAccount">{props => <CreateAccountScreen {...props} onAuthenticated={onAuthenticated} />}</AuthStack.Screen><AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} /></AuthStack.Navigator>}{authState === 'AUTHENTICATED' && needsOnboarding && <OnboardingStack.Navigator screenOptions={{ headerShown: false }}><OnboardingStack.Screen name="Onboarding">{() => <OnboardingScreen onDone={onOnboardingDone} />}</OnboardingStack.Screen></OnboardingStack.Navigator>}{authState === 'AUTHENTICATED' && !needsOnboarding && user && <MainFlow key={pendingBriefingId || 'main'} user={user} notificationId={pendingBriefingId} onAuthExpired={onAuthExpired} onLogout={onLogout} onUserUpdated={onUserUpdated} />}</NavigationContainer></SafeAreaProvider>; }
