import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Image, ImageSourcePropType, KeyboardAvoidingView, Modal,
  Platform, Pressable, ScrollView, StatusBar, StyleSheet, Text, TextInput,
  useWindowDimensions, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, ClientError, CONNECTION_ERROR_MESSAGE } from '../api/client';
import { getDeviceTimezone } from '../config/timezone';
import { requestAndRegisterDevice } from '../push/push';
import {typography, useStyles, useTheme, type Palette } from '../theme';
import type { ClientConfig, Preferences, Topic, User } from '../types/api';
import { Icon } from './Icon';
import { useLogo } from './brand';
import { TimeWheel } from './TimeWheel';
import type { IconName } from './Icon';

const art = {
  reading: require('../../assets/onboarding/new-reading.png'),
  waving: require('../../assets/onboarding/new-waving.png'),
  globe: require('../../assets/onboarding/new-globe.png'),
  clock: require('../../assets/onboarding/new-clock.png'),
  tablet: require('../../assets/onboarding/new-tablet.png'),
  phone: require('../../assets/onboarding/new-phone.png'),
  celebrate: require('../../assets/onboarding/new-celebrate.png'),
  sunrise: require('../../assets/onboarding/new-sunrise.png'),
} as const;

const initialPreferences: Preferences = {
  topics: [], language: 'pt-BR', country_scope: 'GLOBAL', briefing_time: '06:30',
  timezone: getDeviceTimezone(), briefing_size: 10, audio_enabled: false,
};
const timePattern = /^([01]\d|2[0-3]):[0-5]\d$/;
const scopeLabel: Record<Preferences['country_scope'], string> = { LOCAL: 'Brasil', GLOBAL: 'Global', BOTH: 'Brasil e Global' };
const sizeLabel: Record<Preferences['briefing_size'], string> = { 5: 'Rápido', 10: 'Essencial', 15: 'Completo' };
const languageLabel = (language: string) => language === 'pt-BR' ? 'Português' : language === 'en' ? 'Inglês' : language;
const errorMessage = (error: unknown) => {
  if (error instanceof ClientError) {
    if (error.code === 'BACKEND_UNREACHABLE' || error.code === 'OFFLINE') return CONNECTION_ERROR_MESSAGE;
    if (error.code === 'TIMEOUT') return 'A conexão demorou demais. Tente novamente.';
    if (error.code === 'VALIDATION_ERROR') return 'Confira suas escolhas e tente novamente.';
    return error.message;
  }
  return 'Não foi possível concluir. Tente novamente.';
};

function Brand({ large = false }: { large?: boolean }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Image source={useLogo()} resizeMode="contain" accessibilityLabel="NEWZI" style={large ? s.logoLarge : s.logo} />;
}

function Progress({ step }: { step: number }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View accessibilityLabel={`Etapa ${step} de 7`} style={s.progress}>
    {Array.from({ length: 5 }, (_, index) => <View key={index} style={[s.progressMark, index === Math.round((step - 1) * 4 / 6) && s.progressActive]} />)}
  </View>;
}

function Action({ label, onPress, secondary = false, disabled = false, full = false }: {
  label: string; onPress: () => void; secondary?: boolean; disabled?: boolean; full?: boolean;
}) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [s.action, secondary ? s.actionSecondary : s.actionPrimary, full && s.actionFull, (pressed || disabled) && { opacity: .65 }]}>
    <Text style={[s.actionText, secondary && s.actionSecondaryText]}>{label}</Text>
    {!secondary && <Icon name="chevron" color={colors.onPrimary} size={18} />}
  </Pressable>;
}

function Option({ label, detail, selected, onPress, icon, disabled = false }: {
  label: string; detail?: string; selected: boolean; onPress: () => void; icon?: IconName; disabled?: boolean;
}) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: selected, disabled }}
    accessibilityLabel={`${label}${detail ? `, ${detail}` : ''}`} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [s.option, selected && s.optionSelected, disabled && s.optionDisabled, pressed && { opacity: .75 }]}>
    {icon && <View style={[s.optionIcon, selected && s.optionIconSelected]}><Icon name={icon} color={selected ? colors.tone('#1872F7', colors.primary) : colors.tone('#507AB8', colors.secondary)} size={17} /></View>}
    <View style={s.optionCopy}><Text numberOfLines={2} style={[s.optionLabel, selected && s.optionLabelSelected]}>{label}</Text>
      {!!detail && <Text style={s.optionDetail}>{detail}</Text>}</View>
    {selected && <Icon name="checkCircle" color={colors.tone('#2879F9', colors.primary)} size={19} />}
  </Pressable>;
}

function Sheet({ visible, title, onClose, children }: { visible: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
    <View style={s.modalRoot}><Pressable accessibilityLabel="Fechar" style={s.modalBackdrop} onPress={onClose} />
      <View style={s.sheet}><View style={s.sheetHandle} /><View style={s.sheetHeading}>
        <Text style={s.sheetTitle}>{title}</Text><Pressable accessibilityRole="button" accessibilityLabel="Fechar" onPress={onClose} style={s.close}><Icon name="close" color={colors.secondary} size={19} /></Pressable>
      </View>{children}</View>
    </View>
  </Modal>;
}

function TopicSelector({ visible, topics, selected, onToggle, onClose }: {
  visible: boolean; topics: Topic[]; selected: string[]; onToggle: (code: string) => void; onClose: () => void;
}) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => topics.filter(topic => `${topic.name} ${topic.code}`.toLocaleLowerCase('pt-BR').includes(query.toLocaleLowerCase('pt-BR'))), [topics, query]);
  return <Sheet visible={visible} title="Outros temas" onClose={onClose}>
    <TextInput value={query} onChangeText={setQuery} placeholder="Buscar temas" placeholderTextColor={colors.muted}
      accessibilityLabel="Buscar temas" style={s.search} autoCapitalize="none" />
    <ScrollView keyboardShouldPersistTaps="handled" style={s.topicList}>
      {filtered.map(topic => <Option key={topic.code} label={topic.name} selected={selected.includes(topic.code)} onPress={() => onToggle(topic.code)} />)}
      {filtered.length === 0 && <Text style={s.empty}>Nenhum tema encontrado.</Text>}
    </ScrollView>
    <Action label="Concluir" onPress={onClose} full />
  </Sheet>;
}

function Mascot({ source, width, style }: { source: ImageSourcePropType; width: number; style?: object }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <Image source={source} resizeMode="contain" style={[{ width, height: width }, style]} accessibilityLabel="Mascote NEW" />;
}

export function OnboardingScreen({ onDone }: { onDone: (user: User) => void }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  const { width, height } = useWindowDimensions();
  const compact = height < 730;
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [prefs, setPrefs] = useState<Preferences>(initialPreferences);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [topicSheet, setTopicSheet] = useState(false);
  const [choiceSheet, setChoiceSheet] = useState<'language' | 'scope' | null>(null);
  const [completedUser, setCompletedUser] = useState<User | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.config(), api.onboarding().catch(() => null)])
      .then(([configuration, onboarding]) => {
        if (!mounted) return;
        if (onboarding?.preferences) setPrefs(current => ({ ...current, ...onboarding.preferences }));
        setConfig(configuration);
      })
      .catch(cause => { if (mounted) setError(errorMessage(cause)); });
    return () => { mounted = false; };
  }, []);

  const update = (change: Partial<Preferences>) => setPrefs(current => ({ ...current, ...change }));
  const toggleTopic = (code: string) => update({ topics: prefs.topics.includes(code) ? prefs.topics.filter(item => item !== code) : [...prefs.topics, code] });
  const topics = config?.topics.filter(topic => topic.enabled !== false) || [];
  const compactTopics = useMemo(() => {
    const desired = ['tecnologia', 'inteligência artificial', 'negócios', 'economia'];
    const ranked = [...topics].sort((a, b) => {
      const ar = desired.findIndex(name => a.name.toLocaleLowerCase('pt-BR').includes(name));
      const br = desired.findIndex(name => b.name.toLocaleLowerCase('pt-BR').includes(name));
      return (ar < 0 ? 100 : ar) - (br < 0 ? 100 : br);
    });
    return [...ranked.filter(topic => prefs.topics.includes(topic.code)), ...ranked.filter(topic => !prefs.topics.includes(topic.code))].slice(0, 4);
  }, [topics, prefs.topics]);
  const selectedNames = prefs.topics.map(code => topics.find(topic => topic.code === code)?.name || code);
  const shortTopics = selectedNames.length > 2 ? `${selectedNames.slice(0, 2).join(', ')} e +${selectedNames.length - 2}` : selectedNames.join(' e ');

  const next = async () => {
    setError('');
    if (step === 2 && prefs.topics.length === 0) { setError('Selecione pelo menos um tema.'); return; }
    if (step === 4 && !timePattern.test(prefs.briefing_time)) { setError('Escolha um horário válido no formato HH:MM.'); return; }
    if (step === 6) {
      setBusy(true);
      try { await requestAndRegisterDevice(); } catch { /* A permissão ou o registro não impedem o onboarding. */ }
      finally { setBusy(false); setStep(7); }
      return;
    }
    setStep(value => value + 1);
  };

  const finish = async () => {
    if (!config) return;
    if (!prefs.topics.length || !prefs.topics.every(code => topics.some(topic => topic.code === code))) { setStep(2); setError('Selecione pelo menos um tema válido.'); return; }
    if (!config.supported_languages.includes(prefs.language) || !config.country_scopes.includes(prefs.country_scope)) { setStep(3); setError('Confira o idioma e a cobertura.'); return; }
    if (!timePattern.test(prefs.briefing_time)) { setStep(4); setError('Escolha um horário válido.'); return; }
    if (!config.supported_briefing_sizes.includes(prefs.briefing_size)) { setStep(5); setError('Escolha um tamanho válido.'); return; }
    setBusy(true); setError('');
    try {
      await api.saveOnboarding(prefs);
      const user = await api.me();
      setCompletedUser(user);
      setStep(8);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  };

  const titles = ['', 'Bem-vindo\nao Newzi', 'Escolha o que\nimporta para você', 'Defina seu idioma\ne escopo', 'Escolha o melhor\nhorário', 'Escolha o tamanho\ndo seu resumo', 'Ative as notificações', 'Pronto!'];
  const subtitles = ['', 'Notícias importantes, todos\nos dias, de forma clara, rápida\ne no seu ritmo.', 'Selecione os temas que mais\ninteressam e receba um resumo\npersonalizado.', 'Receba notícias em português,\nno cenário global ou nos dois.', 'Receba seu resumo diário\nno momento ideal.', 'Você decide quanto tempo\ntem hoje. A gente se adapta.', 'Receba um aviso quando seu\nresumo do dia estiver pronto.', 'Seu Newzi está configurado\ne pronto para te acompanhar.'];
  const mascotWidth = Math.min(width * (compact ? .53 : .64), compact ? 235 : 290);

  if (!config) return <SafeAreaView style={s.root} edges={['top', 'bottom']}><StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} />
    <View style={s.loading}><ActivityIndicator color={colors.primary} />{!!error && <><Text style={s.error}>{error}</Text><Action label="Tentar novamente" onPress={() => {
      setError('');
      Promise.all([api.config(), api.onboarding().catch(() => null)])
        .then(([configuration, onboarding]) => { if (onboarding?.preferences) setPrefs(current => ({ ...current, ...onboarding.preferences })); setConfig(configuration); })
        .catch(cause => setError(errorMessage(cause)));
    }} /></>}</View>
  </SafeAreaView>;

  return <SafeAreaView style={s.root} edges={['top', 'bottom']}>
    <StatusBar barStyle={theme.statusBar} backgroundColor={colors.background} />
    <View pointerEvents="none" style={s.atmosphereTop} /><View pointerEvents="none" style={s.atmosphereBottom} />
    {step === 0 ? <>
      <View style={s.startHead}><Brand large /><Text style={s.startTagline}>Seu resumo diário,{'\n'}sem complicação.</Text></View>
      <View style={s.startArt}><Mascot source={art.reading} width={Math.min(width * .95, compact ? 350 : 420)} /></View>
      <View style={s.bottom}><Action label="Começar" onPress={() => setStep(1)} full /></View>
    </> : step === 8 ? <>
      <View style={s.finalHead}><Brand large /><Text style={s.finalTitle}>Grandes dias{'\n'}começam com{'\n'}boas informações.</Text><View style={s.finalDash} /></View>
      <Image source={art.sunrise} resizeMode="cover" style={s.sunrise} accessibilityLabel="NEW observa o nascer do sol sobre a cidade" />
      <Text style={s.finalFoot}>Informação que se encaixa{'\n'}na sua rotina.</Text>
      <View style={s.finalAction}><Action label="Começar agora" onPress={() => { if (completedUser) onDone(completedUser); }} disabled={!completedUser} full /></View>
    </> : <>
      <View style={s.top}><Progress step={step} /></View>
      <KeyboardAvoidingView style={s.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={[s.content, compact && s.contentCompact]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <Text style={[s.title, compact && s.titleCompact]}>{titles[step]}</Text>
          <Text style={[s.subtitle, compact && s.subtitleCompact]}>{subtitles[step]}</Text>
          {step === 1 && <View style={s.heroFull}><Mascot source={art.waving} width={mascotWidth} /></View>}
          {step === 2 && <View style={s.splitArea}>
            <Mascot source={art.waving} width={Math.min(width * .52, 235)} style={s.splitMascot} />
            <View style={s.splitOptions}>{compactTopics.map(topic => <Option key={topic.code} label={topic.name} icon="topic" selected={prefs.topics.includes(topic.code)} onPress={() => toggleTopic(topic.code)} />)}
              <Pressable accessibilityRole="button" accessibilityLabel="Outros temas" onPress={() => setTopicSheet(true)} style={s.moreTopics}><Icon name="dots" color={colors.tone('#668BBF', colors.secondary)} size={18} /><Text style={s.moreText}>Outros temas</Text></Pressable>
            </View>
          </View>}
          {step === 3 && <View style={s.globeArea}>
            <View style={s.inlineChoices}>
              <Pressable accessibilityRole="button" accessibilityLabel={`Idioma: ${languageLabel(prefs.language)}`} onPress={() => setChoiceSheet('language')} style={s.choice}><Icon name="globe" color={colors.tone('#1978FA', colors.primary)} size={20} /><Text style={s.choiceText}>{prefs.language === 'pt-BR' ? 'PT-BR' : prefs.language.toUpperCase()}</Text><Icon name="checkCircle" color={colors.tone('#1978FA', colors.primary)} size={17} /></Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel={`Cobertura: ${scopeLabel[prefs.country_scope]}`} onPress={() => setChoiceSheet('scope')} style={s.choice}><Icon name="globe" color={colors.tone('#1978FA', colors.primary)} size={20} /><Text numberOfLines={1} style={s.choiceText}>{scopeLabel[prefs.country_scope]}</Text><Icon name="chevronDown" color={colors.tone('#1978FA', colors.primary)} size={17} /></Pressable>
            </View><Mascot source={art.globe} width={mascotWidth} style={s.centerMascot} />
          </View>}
          {step === 4 && <View style={s.clockArea}><Mascot source={art.clock} width={Math.min(width * .6, compact ? 190 : 240)} style={s.centerMascot} />
            <View style={s.timeCard}><View style={s.timeCardHead}><Icon name="clock" color={colors.tone('#2878F4', colors.primary)} size={17} /><Text style={s.timeCardTitle}>Resumo diário às {prefs.briefing_time}</Text></View>
              <TimeWheel value={prefs.briefing_time} onChange={briefing_time => { update({ briefing_time }); setError(''); }} />
              <Text style={s.timeCardHint}>Deslize para escolher a hora e os minutos.</Text>
            </View>
          </View>}
          {step === 5 && <View style={s.splitArea}>
            <Mascot source={art.tablet} width={Math.min(width * .53, 245)} style={s.splitMascot} />
            <View style={s.splitOptions}>{[10, 5, 15].filter(size => config.supported_briefing_sizes.includes(size)).map(size => <Option key={size} label={sizeLabel[size as Preferences['briefing_size']]} detail={size === 10 ? '10 notícias · 5 min' : size === 5 ? '5 notícias · 3 min' : '15 notícias'} icon={size === 10 ? 'clock' : size === 5 ? 'audio' : 'article'} selected={prefs.briefing_size === size} onPress={() => update({ briefing_size: size as Preferences['briefing_size'] })} />)}</View>
          </View>}
          {step === 6 && <View style={s.heroFull}><Mascot source={art.phone} width={mascotWidth} /></View>}
          {step === 7 && <View style={s.readyArea}><Mascot source={art.celebrate} width={Math.min(width * .6, compact ? 210 : 250)} style={s.centerMascot} />
            <View style={s.summary}>
              <SummaryRow icon="globe" label="Idioma" value={`${languageLabel(prefs.language)} · ${scopeLabel[prefs.country_scope]}`} />
              <SummaryRow icon="topic" label="Temas" value={shortTopics} />
              <SummaryRow icon="article" label="Tamanho" value={`${sizeLabel[prefs.briefing_size]} · ${prefs.briefing_size} notícias`} />
              <SummaryRow icon="clock" label="Horário" value={prefs.briefing_time} last />
            </View>
          </View>}
          {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
        </ScrollView>
        <View style={s.bottom}><Action label="Voltar" secondary onPress={() => { setError(''); setStep(value => value - 1); }} disabled={busy} />
          <Action label={step === 7 ? busy ? 'Salvando…' : 'Começar agora' : busy ? 'Aguarde…' : 'Próximo'} onPress={step === 7 ? finish : next} disabled={busy} />
        </View>
      </KeyboardAvoidingView>
    </>}
    <TopicSelector visible={topicSheet} topics={topics} selected={prefs.topics} onToggle={toggleTopic} onClose={() => setTopicSheet(false)} />
    <Sheet visible={choiceSheet !== null} title={choiceSheet === 'language' ? 'Escolha o idioma' : 'Escolha a cobertura'} onClose={() => setChoiceSheet(null)}>
      <View style={s.choiceList}>{choiceSheet === 'language' ? config.supported_languages.map(language => <Option key={language} label={language === 'pt-BR' ? 'Português (Brasil)' : language === 'en' ? 'English' : language} selected={prefs.language === language} onPress={() => { update({ language }); setChoiceSheet(null); }} />)
        : config.country_scopes.map(scope => <Option key={scope} label={scopeLabel[scope as Preferences['country_scope']]} selected={prefs.country_scope === scope} onPress={() => { update({ country_scope: scope as Preferences['country_scope'] }); setChoiceSheet(null); }} />)}</View>
    </Sheet>
  </SafeAreaView>;
}

function SummaryRow({ icon, label, value, last = false }: { icon: IconName; label: string; value: string; last?: boolean }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const { colors } = theme;
  return <View style={[s.summaryRow, !last && s.summaryBorder]}><Icon name={icon} color={colors.tone('#1872F7', colors.primary)} size={16} /><Text style={s.summaryLabel}>{label}</Text><Text numberOfLines={2} style={s.summaryValue}>{value}</Text></View>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background }, fill: { flex: 1 }, loading: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  atmosphereTop: { position: 'absolute', top: '20%', left: -90, width: 260, height: 260, borderRadius: 130, backgroundColor: colors.surfaceTint },
  atmosphereBottom: { position: 'absolute', bottom: -100, right: -110, width: 400, height: 400, borderRadius: 200, backgroundColor: colors.surfaceTint },
  logo: { width: 175, height: 64 }, logoLarge: { width: 255, height: 84 },
  top: { height: 62, alignItems: 'center', justifyContent: 'center' }, progress: { flexDirection: 'row', gap: 7, alignItems: 'center' }, progressMark: { width: 17, height: 5, borderRadius: 9, backgroundColor: colors.tone('#D9E5F3', colors.placeholder) }, progressActive: { backgroundColor: colors.tone('#2878F4', colors.primary) },
  content: { flexGrow: 1, paddingHorizontal: 22, paddingTop: 23, alignItems: 'center' }, contentCompact: { paddingTop: 6 },
  title: { fontFamily: typography.fontFamily.ui, fontSize: 27, lineHeight: 31, fontWeight: '800', letterSpacing: -1.1, color: colors.ink, textAlign: 'center' }, titleCompact: { fontSize: 24, lineHeight: 28 },
  subtitle: { fontFamily: typography.fontFamily.ui, fontSize: 15, lineHeight: 21, color: colors.tone('#56709F', colors.secondary), textAlign: 'center', marginTop: 12 }, subtitleCompact: { fontSize: 14, lineHeight: 19, marginTop: 7 },
  heroFull: { flex: 1, justifyContent: 'center', alignItems: 'center', minHeight: 260, paddingBottom: 10 }, centerMascot: { alignSelf: 'center' },
  splitArea: { flex: 1, width: '100%', minHeight: 315, justifyContent: 'center', marginTop: 8 }, splitMascot: { position: 'absolute', left: -52, bottom: -5 }, splitOptions: { width: '64%', alignSelf: 'flex-end', gap: 8, paddingBottom: 8 },
  option: { minHeight: 52, borderWidth: 1, borderColor: colors.divider, borderRadius: 14, backgroundColor: colors.overlay, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 7, gap: 7 },
  optionSelected: { borderColor: colors.tone('#5796FF', colors.primary), backgroundColor: colors.surfaceTint }, optionDisabled: { opacity: .5 }, optionIcon: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.surfaceTint, alignItems: 'center', justifyContent: 'center' }, optionIconSelected: { backgroundColor: colors.tone('#D2E7FF', colors.placeholder) },
  optionIconText: { fontFamily: typography.fontFamily.ui, fontSize: 11, fontWeight: '800', color: colors.tone('#507AB8', colors.secondary) }, optionIconTextSelected: { color: colors.tone('#1872F7', colors.primary) }, optionCopy: { flex: 1 },
  optionLabel: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, fontWeight: '700', color: colors.tone('#142953', colors.ink), lineHeight: 16 }, optionLabelSelected: { color: colors.tone('#086BEE', colors.primary) }, optionDetail: { fontFamily: typography.fontFamily.ui, fontSize: 10.5, color: colors.tone('#617AA5', colors.secondary), marginTop: 2 },
  check: { width: 20, height: 20, borderRadius: 10, backgroundColor: colors.tone('#2879F9', colors.primary), alignItems: 'center', justifyContent: 'center' }, checkText: { color: colors.onPrimary, fontSize: 12, fontWeight: '900' },
  moreTopics: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, borderRadius: 13, backgroundColor: colors.overlay }, moreDots: { color: colors.tone('#668BBF', colors.secondary), fontWeight: '800', fontSize: 14 }, moreText: { fontFamily: typography.fontFamily.ui, fontSize: 11, color: colors.tone('#5B729F', colors.secondary) },
  globeArea: { flex: 1, width: '100%', alignItems: 'center', justifyContent: 'space-evenly', minHeight: 320 }, inlineChoices: { flexDirection: 'row', gap: 8, width: '100%', marginTop: 12 },
  choice: { flex: 1, minHeight: 58, borderRadius: 14, borderWidth: 1, borderColor: colors.tone('#7CABFC', colors.primary), backgroundColor: colors.surfaceTint, paddingHorizontal: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 }, choiceIcon: { fontSize: 21, color: colors.tone('#1978FA', colors.primary) }, choiceText: { fontFamily: typography.fontFamily.ui, fontSize: 12, color: colors.tone('#175ABE', colors.primary), fontWeight: '700', flexShrink: 1 }, choiceCheck: { color: colors.tone('#1978FA', colors.primary), fontWeight: '800' }, choiceChevron: { color: colors.tone('#1978FA', colors.primary), fontSize: 17 },
  clockArea: { flex: 1, width: '100%', alignItems: 'center', justifyContent: 'center', minHeight: 315 },
  timeCard: { width: '100%', maxWidth: 340, backgroundColor: colors.surface, borderRadius: 24, borderWidth: 1, borderColor: colors.tone('#E0ECF8', colors.border), marginTop: -7, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 12 },
  timeCardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, marginBottom: 6 }, timeCardTitle: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.tone('#10264E', colors.ink) },
  timeCardHint: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.tone('#617AA5', colors.secondary), textAlign: 'center', marginTop: 6 },
  readyArea: { flex: 1, width: '100%', alignItems: 'center', justifyContent: 'center', minHeight: 370 },
  summary: { backgroundColor: colors.surface, borderRadius: 20, borderWidth: 1, borderColor: colors.divider, width: '100%', paddingHorizontal: 14, paddingVertical: 5, marginTop: -10 }, summaryRow: { minHeight: 42, flexDirection: 'row', alignItems: 'center' }, summaryBorder: { borderBottomWidth: 1, borderColor: colors.divider }, summaryIcon: { width: 25, color: colors.tone('#2677ED', colors.primary), fontSize: 17 }, summaryLabel: { width: 65, fontFamily: typography.fontFamily.ui, fontSize: 11, color: colors.tone('#6E83A6', colors.secondary) }, summaryValue: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 11, lineHeight: 15, fontWeight: '700', color: colors.tone('#19305A', colors.ink), textAlign: 'right' },
  bottom: { flexDirection: 'row', gap: 10, paddingHorizontal: 18, paddingTop: 8, paddingBottom: 12, backgroundColor: 'transparent' }, action: { flex: 1, minHeight: 54, borderRadius: 28, alignItems: 'center', justifyContent: 'center', flexDirection: 'row' }, actionFull: { flex: 1 }, actionPrimary: { backgroundColor: colors.tone('#2778F5', colors.primary) }, actionSecondary: { backgroundColor: colors.surface, borderColor: colors.tone('#E2ECF6', colors.border), borderWidth: 1 }, actionText: { fontFamily: typography.fontFamily.ui, fontSize: 15, fontWeight: '700', color: colors.onPrimary }, actionSecondaryText: { color: colors.tone('#647DAA', colors.secondary), fontWeight: '500' }, actionArrow: { color: colors.onPrimary, fontSize: 27, fontWeight: '300', position: 'absolute', right: 17, top: 10 },
  startHead: { alignItems: 'center', paddingTop: 48 }, startTagline: { textAlign: 'center', fontFamily: typography.fontFamily.ui, color: colors.tone('#405D93', colors.secondary), fontSize: 19, lineHeight: 24, marginTop: 3 }, startArt: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  finalHead: { alignItems: 'center', paddingTop: 48, zIndex: 1 }, finalTitle: { fontFamily: typography.fontFamily.ui, fontSize: 20, color: colors.tone('#405D93', colors.secondary), lineHeight: 23, textAlign: 'center', marginTop: 11 }, finalDash: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.tone('#2578FA', colors.primary), marginTop: 12 }, sunrise: { position: 'absolute', width: '100%', height: '48%', bottom: '18%' }, finalFoot: { position: 'absolute', bottom: 105, alignSelf: 'center', textAlign: 'center', color: colors.tone('#54709D', colors.secondary), fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20 }, finalAction: { position: 'absolute', bottom: 16, left: 0, right: 0, flexDirection: 'row', paddingHorizontal: 18 },
  error: { fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 19, color: colors.tone('#BC3D4E', colors.topicRed.icon), textAlign: 'center', marginTop: 10, marginBottom: 8 },
  modalRoot: { flex: 1, justifyContent: 'flex-end' }, modalBackdrop: { ...StyleSheet.absoluteFill, backgroundColor: colors.scrim }, sheet: { backgroundColor: colors.background, borderTopLeftRadius: 25, borderTopRightRadius: 25, paddingHorizontal: 20, paddingBottom: 25, maxHeight: '80%' }, sheetHandle: { width: 43, height: 5, borderRadius: 5, backgroundColor: colors.tone('#CCD7E5', colors.placeholder), alignSelf: 'center', marginTop: 9, marginBottom: 13 }, sheetHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }, sheetTitle: { fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800', color: colors.tone('#10234B', colors.ink) }, close: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' }, closeText: { fontSize: 27, color: colors.tone('#6E82A3', colors.secondary) },
  search: { height: 48, borderRadius: 14, borderWidth: 1, borderColor: colors.tone('#D8E6F7', colors.border), backgroundColor: colors.surface, paddingHorizontal: 14, marginBottom: 12, color: colors.tone('#142953', colors.ink), fontFamily: typography.fontFamily.ui }, topicList: { maxHeight: 350 }, empty: { textAlign: 'center', color: colors.tone('#6D83A7', colors.secondary), padding: 20 }, choiceList: { gap: 9, marginBottom: 10 },
});
