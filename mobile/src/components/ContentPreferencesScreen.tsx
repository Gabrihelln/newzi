import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, BackHandler, Modal, Pressable, ScrollView, StatusBar, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../api/client';
import { notifyContentChanged } from '../services/contentRevision';
import { buildTopicTree, coverage, isCovered, toggleTopic, type Coverage } from '../services/topicSelection';
import type { ClientConfig, Preferences, Topic } from '../types/api';
import { radius, spacing, typography, useStyles, useTheme, type Palette } from '../theme';
import { Icon } from './Icon';
import { ScreenState } from './ScreenPrimitives';
import { TopicIcon, topicIconFor } from './TopicIcon';

const VISIBLE_DOMAINS = 8;
const VISIBLE_SUBJECTS = 4;

const fold = (value: string) => value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');
type Content = Pick<Preferences, 'topics' | 'content_scope'>;
/** What decides the briefing's content, in canonical form: a save with the same key changes nothing. */
const contentKey = (content: Content) => content.content_scope === 'all' ? 'all' : [...content.topics].sort().join('|');
const domainTints = (colors: Palette) => [colors.topicBlue, colors.topicGreen, colors.topicPurple, colors.topicOrange, colors.topicRed, colors.topicTeal];

/** Text with every match of the search in bold primary color (accents ignored). */
function Highlight({ text, query, style }: { text: string; query: string; style: object }) {
  const { colors } = useTheme();
  const needle = fold(query.trim());
  if (!needle) return <Text style={style}>{text}</Text>;
  // Folding keeps one character per character of these names, so indexes line up with the original text.
  const haystack = fold(text);
  const parts: React.ReactNode[] = [];
  let from = 0;
  for (let at = haystack.indexOf(needle); at >= 0 && haystack.length === text.length; at = haystack.indexOf(needle, at + needle.length)) {
    if (at > from) parts.push(text.slice(from, at));
    parts.push(<Text key={at} style={{ color: colors.primary, fontWeight: '800' }}>{text.slice(at, at + needle.length)}</Text>);
    from = at + needle.length;
  }
  parts.push(text.slice(from));
  return <Text style={style}>{parts}</Text>;
}

/** Checkbox with the three states of a topic: followed, partly followed (a dash) and not followed. */
function Check({ state, tint, size = 24 }: { state: Coverage; tint: string; size?: number }) {
  const { colors } = useTheme();
  return <View style={{ width: size, height: size, borderRadius: size / 3.2, borderWidth: 1.6, alignItems: 'center', justifyContent: 'center',
    borderColor: state === 'none' ? colors.borderStrong : tint, backgroundColor: state === 'all' ? tint : colors.surface }}>
    {state === 'all' ? <Icon name="check" color={colors.onPrimary} size={size * .62} /> : state === 'some' ? <View style={{ width: size * .45, height: 2.5, borderRadius: 2, backgroundColor: tint }} /> : null}
  </View>;
}

export function ContentPreferencesScreen({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const s = useStyles(makeStyles);
  const { colors, statusBar } = useTheme();
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [content, setContent] = useState<Content | null>(null);
  const [briefingSize, setBriefingSize] = useState(10);
  const [saved, setSaved] = useState<Content | null>(null);
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [dialog, setDialog] = useState<null | { regenerating: boolean }>(null);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [showAllSubjects, setShowAllSubjects] = useState<Set<string>>(() => new Set());
  const [showAllDomains, setShowAllDomains] = useState(false);
  const search = useRef<TextInput>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const [prefs, configuration] = await Promise.all([api.preferences(), api.config()]);
      const loaded = { topics: prefs.topics || [], content_scope: prefs.content_scope || 'selected' } as Content;
      setContent(loaded); setSaved(loaded); setBriefingSize(prefs.briefing_size || 10); setConfig(configuration);
      setStatus('loaded');
    } catch { setStatus('error'); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const topics = useMemo(() => (config?.topics || []).filter(topic => topic.enabled !== false).sort((a, b) => (a.order || 0) - (b.order || 0)), [config]);
  const byCode = useMemo(() => new Map(topics.map(topic => [topic.code, topic])), [topics]);
  const tree = useMemo(() => buildTopicTree(topics), [topics]);
  const roots = useMemo(() => topics.filter(topic => !topic.parent_id), [topics]);
  const childrenOf = useCallback((code: string) => (tree.children.get(code) || []).map(child => byCode.get(child)).filter(Boolean) as Topic[], [tree, byCode]);
  const descendantsOf = useMemo(() => {
    const all = new Map<string, string[]>();
    const walk = (code: string): string[] => (tree.children.get(code) || []).flatMap(child => [child, ...walk(child)]);
    for (const root of roots) all.set(root.code, walk(root.code));
    return all;
  }, [tree, roots]);
  const rootOf = (topic: Topic) => byCode.get((topic.path || [topic.code])[0]) || topic;
  const tintOf = (root: Topic) => domainTints(colors)[Math.max(0, roots.indexOf(root)) % 6];

  const all = content?.content_scope === 'all';
  const selection = content?.topics || [];
  const stateOf = (code: string): Coverage => all ? 'all' : coverage(selection, code, tree);
  const subjects = topics.length - roots.length;
  const coveredSubjects = all ? subjects : topics.filter(topic => topic.parent_id && isCovered(selection, topic.code, tree)).length;
  const coveredDomains = roots.filter(root => stateOf(root.code) !== 'none');
  const wholeDomains = roots.filter(root => stateOf(root.code) === 'all').map(root => root.name);
  // Each topic added or removed, plus turning "follow everything" on or off, is one pending change.
  const changes = !content || !saved ? 0 : (content.content_scope !== saved.content_scope ? 1 : 0)
    + selection.filter(code => !saved.topics.includes(code)).length + saved.topics.filter(code => !selection.includes(code)).length;

  const toggle = (code: string) => setContent(current => current && ({ content_scope: 'selected',
    // With everything followed, a change starts from all domains (e.g. everything but Sports).
    topics: toggleTopic(current.content_scope === 'all' ? roots.map(root => root.code) : current.topics, code, tree) }));
  const flip = (set: Set<string>, code: string) => { const next = new Set(set); if (next.has(code)) next.delete(code); else next.add(code); return next; };

  const leave = useCallback(() => {
    if (!changes) { onBack(); return true; }
    Alert.alert('Descartar alterações?', `Você tem ${changes} ${changes === 1 ? 'alteração não salva' : 'alterações não salvas'}.`, [
      { text: 'Continuar editando', style: 'cancel' }, { text: 'Descartar', style: 'destructive', onPress: onBack }]);
    return true;
  }, [changes, onBack]);
  useEffect(() => { const sub = BackHandler.addEventListener('hardwareBackPress', leave); return () => sub.remove(); }, [leave]);

  const save = async () => {
    if (!content || !saved || saving) return;
    if (!all && !selection.length) { setMessage('Escolha ao menos um assunto ou ative “Quero acompanhar tudo”.'); return; }
    setSaving(true); setMessage('');
    // Only what this screen owns: saving the whole preferences object could undo a time or voice changed elsewhere.
    const body = { content_scope: content.content_scope || 'selected', topics: selection };
    try {
      const result = await api.savePreferences(body);
      const next = { topics: result?.topics || body.topics, content_scope: result?.content_scope || body.content_scope } as Content;
      const regenerating = contentKey(next) !== contentKey(saved);
      setContent(next); setSaved(next);
      notifyContentChanged();
      setDialog({ regenerating });
    } catch { setMessage('Não foi possível salvar suas preferências. Verifique sua internet e tente de novo.'); }
    finally { setSaving(false); }
  };

  const needle = fold(query.trim());
  const results = useMemo(() => !needle ? [] : topics.map(topic => {
    const primary = [topic.name, topic.code, ...(topic.aliases || [])].map(fold);
    const words = (value: string) => value.split(/[\s_-]+/);
    const rank = primary.some(value => value === needle) ? 0 : primary.some(value => words(value).some(word => word.startsWith(needle))) ? 1
      : needle.length > 2 && primary.some(value => value.includes(needle)) ? 2
      : needle.length > 2 && fold([topic.description || '', ...(topic.path || []).map(code => byCode.get(code)?.name || '')].join(' ')).includes(needle) ? 3 : -1;
    return { topic, rank };
  }).filter(item => item.rank >= 0).sort((a, b) => a.rank - b.rank || (a.topic.depth || 0) - (b.topic.depth || 0)).slice(0, 60).map(item => item.topic), [needle, topics, byCode]);
  const pathOf = (topic: Topic) => (topic.path || [topic.code]).map(code => byCode.get(code)?.name || code).join(' › ');
  const cancelSearch = () => { setQuery(''); setSearching(false); search.current?.blur(); };

  const subjectRow = (topic: Topic, tint: string, depth: number): React.ReactNode => {
    const children = childrenOf(topic.code);
    const open = expanded.has(topic.code);
    return <View key={topic.code}>
      <View style={[s.subject, { paddingLeft: depth * 14 }]}>
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: stateOf(topic.code) === 'some' ? 'mixed' : stateOf(topic.code) === 'all' }} onPress={() => toggle(topic.code)} style={s.subjectMain}>
          <Check state={stateOf(topic.code)} tint={tint} size={22} />
          <View style={{ flex: 1 }}>
            <Text style={s.subjectName}>{topic.name}</Text>
            {!!topic.description && <Text numberOfLines={1} style={s.subjectText}>{topic.description}</Text>}
          </View>
        </Pressable>
        {children.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel={`${open ? 'Recolher' : 'Abrir'} ${topic.name}`} onPress={() => setExpanded(current => flip(current, topic.code))} style={s.subjectToggle}>
          <View style={{ transform: [{ rotate: open ? '180deg' : '0deg' }] }}><Icon name="chevronDown" color={colors.secondary} size={16} /></View>
        </Pressable>}
      </View>
      {open && children.map(child => subjectRow(child, tint, depth + 1))}
    </View>;
  };

  const domainCard = (root: Topic) => {
    const tint = tintOf(root);
    const state = stateOf(root.code);
    const total = (descendantsOf.get(root.code) || []).length;
    const covered = state === 'all' ? total : (descendantsOf.get(root.code) || []).filter(code => isCovered(selection, code, tree)).length;
    const open = expanded.has(root.code);
    const children = childrenOf(root.code);
    const visible = showAllSubjects.has(root.code) ? children : children.slice(0, VISIBLE_SUBJECTS);
    return <View key={root.code} style={[s.domain, state === 'all' && { borderColor: tint.icon, borderWidth: 1.5 }]}>
      <View style={s.domainHead}>
        <Pressable accessibilityRole="checkbox" accessibilityLabel={root.name} accessibilityState={{ checked: state === 'some' ? 'mixed' : state === 'all' }} onPress={() => toggle(root.code)} hitSlop={6}>
          <Check state={state} tint={tint.icon} />
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={`${open ? 'Recolher' : 'Abrir'} ${root.name}`} onPress={() => setExpanded(current => flip(current, root.code))} style={s.domainMain}>
          <View style={[s.domainIcon, { backgroundColor: tint.background }]}><TopicIcon name={topicIconFor(root)} color={tint.icon} size={22} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.domainName}>{root.name}</Text>
            <Text style={s.domainCount}>{!total ? root.description || 'Assunto' : state === 'all' ? `Todos os ${total} assuntos` : covered ? `${covered} de ${total} assuntos` : `${total} assuntos`}</Text>
            {total > 0 && <View style={s.bar}><View style={[s.barFill, { width: `${Math.round(covered / total * 100)}%`, backgroundColor: tint.icon }]} /></View>}
          </View>
          {children.length > 0 && <View style={[s.chevron, open && { backgroundColor: tint.background }]}>
            <View style={{ transform: [{ rotate: open ? '180deg' : '0deg' }] }}><Icon name="chevronDown" color={open ? tint.icon : colors.secondary} size={18} /></View>
          </View>}
        </Pressable>
      </View>
      {open && children.length > 0 && <View style={s.domainBody}>
        <Pressable accessibilityRole="button" onPress={() => toggle(root.code)} style={s.subjectMain}>
          <Check state={state === 'all' ? 'all' : 'none'} tint={tint.icon} size={22} />
          <Text style={[s.selectAll, { color: tint.icon }]}>{state === 'all' ? `Desmarcar todos os ${total}` : `Selecionar todos os ${total}`}</Text>
        </Pressable>
        {visible.map(child => subjectRow(child, tint.icon, 0))}
        {children.length > visible.length && <Pressable accessibilityRole="button" onPress={() => setShowAllSubjects(current => flip(current, root.code))} style={s.more}>
          <Text style={s.moreText}>Ver mais {children.length - visible.length} {children.length - visible.length === 1 ? 'assunto' : 'assuntos'}</Text>
        </Pressable>}
      </View>}
    </View>;
  };

  const tooMany = !all && selection.length > briefingSize;
  const header = <View style={s.header}>
    <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={leave} hitSlop={8} style={s.back}>
      <View style={{ transform: [{ rotate: '180deg' }] }}><Icon name="chevron" color={colors.secondary} size={22} /></View>
    </Pressable>
    <Text accessibilityRole="header" numberOfLines={1} style={s.title}>Preferências de conteúdo</Text>
    <View style={{ width: 42 }} />
  </View>;

  if (status !== 'loaded' || !content || !config) return <SafeAreaView style={s.safe}><StatusBar barStyle={statusBar} backgroundColor={colors.background} />{header}
    {status === 'error' ? <ScreenState kind="error" title="Preferências indisponíveis" message="Não foi possível carregar seus assuntos. Verifique sua internet." onRetry={() => void load()} />
      : <ScreenState kind="loading" title="Carregando preferências" />}
  </SafeAreaView>;

  const domainsShown = showAllDomains ? roots : roots.slice(0, VISIBLE_DOMAINS);
  const searchMode = searching || !!needle;

  return <SafeAreaView style={s.safe} edges={['top', 'bottom']}>
    <StatusBar barStyle={statusBar} backgroundColor={colors.background} />
    {header}
    <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
      {!searchMode && <View style={s.summary}>
        <Text style={s.summaryLabel}>SEU RESUMO ACOMPANHA</Text>
        <Text style={s.summaryTitle}>{all ? `Todos os ${subjects} assuntos` : `${coveredSubjects} ${coveredSubjects === 1 ? 'assunto' : 'assuntos'} em ${coveredDomains.length} ${coveredDomains.length === 1 ? 'domínio' : 'domínios'}`}</Text>
        <View style={s.summaryBar}><View style={[s.summaryFill, { width: `${subjects ? Math.round(coveredSubjects / subjects * 100) : 0}%` }]} /></View>
        <Text style={s.summaryText}>{all ? `Os ${roots.length} domínios estão incluídos.` : `${selection.length} ${selection.length === 1 ? 'item escolhido' : 'itens escolhidos'}${wholeDomains.length === 1 ? ` · ${wholeDomains[0]} inteira incluída` : wholeDomains.length > 1 ? ` · ${wholeDomains.length} domínios inteiros incluídos` : ''}`}</Text>
      </View>}
      {!searchMode && tooMany && <View style={s.warning}>
        <Icon name="info" color={colors.warning} size={18} />
        <Text style={s.warningText}>{selection.length > 20 ? 'Com muitos assuntos, seu resumo pode chegar a 20 notícias. Nos dias mais movimentados, alguns podem ficar de fora.'
          : `Para incluir todos os seus assuntos, o resumo pode ter mais de ${briefingSize} notícias (até 20).`}</Text>
      </View>}

      <View style={[s.search, searchMode && s.searchActive]}>
        <Icon name="search" color={searchMode ? colors.primary : colors.muted} size={20} />
        <TextInput ref={search} accessibilityLabel="Buscar assunto" value={query} onChangeText={setQuery} onFocus={() => setSearching(true)} onBlur={() => { if (!query.trim()) setSearching(false); }}
          placeholder="Buscar assunto, tema ou sigla" placeholderTextColor={colors.muted} autoCorrect={false} returnKeyType="search" style={s.searchInput} />
        {!!query && <Pressable accessibilityRole="button" accessibilityLabel="Limpar busca" onPress={() => setQuery('')} hitSlop={8} style={s.searchClear}><Icon name="close" color={colors.surface} size={13} /></Pressable>}
      </View>

      {searchMode ? <>
        <View style={s.sectionRow}>
          <Text style={s.resultsCount}>{needle ? `${results.length} ${results.length === 1 ? 'RESULTADO' : 'RESULTADOS'}` : 'DIGITE PARA BUSCAR'}</Text>
          <Pressable accessibilityRole="button" onPress={cancelSearch} hitSlop={8}><Text style={s.link}>Cancelar</Text></Pressable>
        </View>
        {needle && !results.length && <Text style={s.helper}>Nenhum assunto encontrado para “{query.trim()}”.</Text>}
        {results.length > 0 && <View style={s.results}>{results.map((topic, index) => {
          const root = rootOf(topic); const tint = tintOf(root); const state = stateOf(topic.code);
          return <Pressable key={topic.code} accessibilityRole="checkbox" accessibilityState={{ checked: state === 'some' ? 'mixed' : state === 'all' }} onPress={() => toggle(topic.code)}
            style={[s.result, index < results.length - 1 && s.resultDivider]}>
            <View style={[s.domainIcon, { backgroundColor: tint.background }]}><TopicIcon name={topicIconFor(root)} color={tint.icon} size={22} /></View>
            <View style={{ flex: 1 }}>
              <Highlight text={topic.name} query={query} style={s.resultName} />
              <Highlight text={pathOf(topic)} query={query} style={s.resultPath} />
            </View>
            <Check state={state} tint={colors.primary} size={26} />
          </Pressable>;
        })}</View>}
      </> : <>
        {!all && selection.length > 0 && <>
          <View style={s.sectionRow}>
            <Text accessibilityRole="header" style={s.sectionTitle}>Selecionados</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Limpar selecionados" onPress={() => setContent({ content_scope: 'selected', topics: [] })} hitSlop={8}><Text style={s.link}>Limpar</Text></Pressable>
          </View>
          <Text style={s.helper}>Toque em um assunto para remover.</Text>
          <View style={s.chips}>{selection.map(code => {
            const topic = byCode.get(code); const parent = topic?.parent_id ? byCode.get(topic.parent_id)?.name : null;
            return <Pressable key={code} accessibilityRole="button" accessibilityLabel={`Remover ${topic?.name || code}`} onPress={() => toggle(code)} style={s.chip}>
              <Text style={s.chipText}>{topic?.name || code}{parent ? <Text style={s.chipParent}>{` · ${parent}`}</Text> : null}</Text>
              <Icon name="close" color={colors.primary} size={14} />
            </Pressable>;
          })}</View>
        </>}

        <Text accessibilityRole="header" style={[s.sectionTitle, { marginTop: spacing.xl }]}>Domínios</Text>
        <Text style={s.helper}>{roots.length} domínios · {subjects} assuntos. Abra para escolher assuntos específicos.</Text>
        <View style={s.everything}>
          <View style={[s.domainIcon, { backgroundColor: colors.topicBlue.background }]}><Icon name="layers" color={colors.topicBlue.icon} size={21} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.domainName}>Quero acompanhar tudo</Text>
            <Text style={s.domainCount}>Segue todos os domínios. Desmarque o que não quiser.</Text>
          </View>
          <Switch accessibilityLabel="Quero acompanhar tudo" value={all} onValueChange={value => setContent(current => current && { ...current, content_scope: value ? 'all' : 'selected' })}
            trackColor={{ false: colors.switchTrackOff, true: colors.switchTrackOn }} ios_backgroundColor={colors.switchTrackOff} thumbColor={all ? colors.primary : colors.switchThumbOff} />
        </View>
        {all && <Text style={[s.helper, { marginTop: -4 }]}>Sua seleção anterior fica guardada caso você volte a escolher assuntos específicos.</Text>}
        <View style={{ gap: 10 }}>{domainsShown.map(domainCard)}</View>
        {roots.length > VISIBLE_DOMAINS && <Pressable accessibilityRole="button" onPress={() => setShowAllDomains(value => !value)} style={s.more}>
          <Text style={s.moreText}>{showAllDomains ? 'Mostrar menos domínios' : `Mostrar mais ${roots.length - VISIBLE_DOMAINS} domínios`}</Text>
        </Pressable>}
      </>}
    </ScrollView>

    {!searchMode && <View style={s.footer}>
      {!!message && <Text accessibilityRole="alert" style={s.error}>{message}</Text>}
      {changes > 0 && <View style={s.pending}><View style={s.pendingDot} /><Text style={s.pendingText}>{changes} {changes === 1 ? 'alteração não salva' : 'alterações não salvas'}</Text></View>}
      <Pressable accessibilityRole="button" accessibilityState={{ disabled: !changes || saving, busy: saving }} disabled={!changes || saving} onPress={() => void save()}
        style={({ pressed }) => [s.save, (!changes || saving) && s.saveDisabled, pressed && { opacity: .85 }]}>
        <Text style={[s.saveText, (!changes || saving) && s.saveTextDisabled]}>{saving ? 'Salvando…' : changes ? 'Salvar preferências' : 'Preferências salvas'}</Text>
      </Pressable>
    </View>}

    <Modal visible={Boolean(dialog)} transparent animationType="fade" onRequestClose={() => { setDialog(null); onDone(); }}>
      <View style={s.backdrop}>
        <View accessibilityViewIsModal style={s.dialog}>
          <View style={s.dialogIcon}><Icon name="checkCircle" color={colors.primary} size={30} /></View>
          <Text style={s.dialogTitle}>Preferências salvas</Text>
          <Text style={s.dialogBody}>{dialog?.regenerating
            ? 'Estamos preparando um novo resumo em áudio com os seus assuntos. Normalmente leva menos de um minuto — você será avisado quando ele estiver pronto.'
            : 'Sua tela inicial e o Explorar já foram atualizados com as suas preferências.'}</Text>
          <Pressable accessibilityRole="button" onPress={() => { setDialog(null); onDone(); }} style={s.save}><Text style={s.saveText}>Ir para o início</Text></Pressable>
          <Pressable accessibilityRole="button" onPress={() => setDialog(null)} style={s.dialogSecondary}><Text style={s.link}>Continuar editando</Text></Pressable>
        </View>
      </View>
    </Modal>
  </SafeAreaView>;
}

const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { height: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14 },
  back: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800', color: colors.ink },
  content: { paddingHorizontal: 18, paddingTop: 6, paddingBottom: 24 },
  summary: { borderRadius: 22, padding: 18, backgroundColor: colors.tone('#1F7FEA', colors.inverse), marginBottom: 12, shadowColor: '#1F7FEA', shadowOpacity: .22, shadowRadius: 14, shadowOffset: { width: 0, height: 8 }, elevation: 3 },
  summaryLabel: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, fontWeight: '700', letterSpacing: .6, color: 'rgba(255,255,255,.85)' },
  summaryTitle: { fontFamily: typography.fontFamily.ui, fontSize: 20, fontWeight: '800', color: '#FFFFFF', marginTop: 3 },
  summaryBar: { height: 6, borderRadius: 3, backgroundColor: 'rgba(255,255,255,.3)', marginTop: 12, overflow: 'hidden' },
  summaryFill: { height: 6, borderRadius: 3, backgroundColor: '#FFFFFF' },
  summaryText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: 'rgba(255,255,255,.92)', marginTop: 9 },
  warning: { flexDirection: 'row', gap: 10, padding: 14, borderRadius: 16, backgroundColor: colors.tone('#FFF6E7', colors.warningSurface), borderWidth: 1, borderColor: colors.tone('#F8E3BD', colors.warningSurface), marginBottom: 14 },
  warningText: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 12.5, lineHeight: 18, color: colors.tone('#6E5326', colors.body) },
  search: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 54, paddingHorizontal: 16, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: 18 },
  searchActive: { borderColor: colors.primary, borderWidth: 2, paddingHorizontal: 15 },
  searchInput: { flex: 1, fontFamily: typography.fontFamily.ui, fontSize: 15, color: colors.textPrimary, paddingVertical: 10 },
  searchClear: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.muted },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800', color: colors.ink },
  resultsCount: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, fontWeight: '800', letterSpacing: .8, color: colors.secondary },
  link: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.primary },
  helper: { fontFamily: typography.fontFamily.ui, fontSize: 13, lineHeight: 18, color: colors.secondary, marginTop: 3, marginBottom: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 36, paddingLeft: 13, paddingRight: 10, borderRadius: radius.pill, backgroundColor: colors.tone('#E4F1FF', colors.surfaceTint), borderWidth: 1, borderColor: colors.tone('#B7D6FF', colors.primary) },
  chipText: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '800', color: colors.tone('#0B3F86', colors.primary) },
  chipParent: { fontWeight: '500', color: colors.secondary },
  everything: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: 10 },
  domain: { borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14 },
  domainHead: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 74 },
  domainMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  domainIcon: { width: 44, height: 44, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  domainName: { fontFamily: typography.fontFamily.ui, fontSize: 15.5, fontWeight: '800', color: colors.ink },
  domainCount: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary, marginTop: 2 },
  bar: { height: 4, width: '80%', borderRadius: 2, backgroundColor: colors.track, marginTop: 7, overflow: 'hidden' },
  barFill: { height: 4, borderRadius: 2 },
  chevron: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceSoft },
  domainBody: { borderTopWidth: 1, borderTopColor: colors.divider, paddingVertical: 6, paddingLeft: 36 },
  selectAll: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '800' },
  subject: { flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: colors.divider },
  subjectMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 50, paddingVertical: 6 },
  subjectName: { fontFamily: typography.fontFamily.ui, fontSize: 14, fontWeight: '700', color: colors.ink },
  subjectText: { fontFamily: typography.fontFamily.ui, fontSize: 11.5, color: colors.secondary, marginTop: 1 },
  subjectToggle: { width: 40, height: 44, alignItems: 'center', justifyContent: 'center' },
  more: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  moreText: { fontFamily: typography.fontFamily.ui, fontSize: 13, fontWeight: '700', color: colors.primary },
  results: { borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginTop: 10 },
  result: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  resultDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  resultName: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.ink },
  resultPath: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary, marginTop: 2 },
  footer: { paddingHorizontal: 18, paddingTop: 8, paddingBottom: 12, backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.divider },
  error: { fontFamily: typography.fontFamily.ui, color: colors.danger, fontSize: 13, textAlign: 'center', marginBottom: 6 },
  pending: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, marginBottom: 8 },
  pendingDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.sun },
  pendingText: { fontFamily: typography.fontFamily.ui, fontSize: 12.5, color: colors.secondary },
  save: { minHeight: 54, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  saveDisabled: { backgroundColor: colors.surfaceTint },
  saveText: { fontFamily: typography.fontFamily.ui, fontSize: 16, fontWeight: '800', color: colors.onPrimary },
  saveTextDisabled: { color: colors.muted },
  backdrop: { flex: 1, backgroundColor: colors.tone('#0A1E4466', colors.scrim), alignItems: 'center', justifyContent: 'center', padding: 24 },
  dialog: { width: '100%', maxWidth: 380, borderRadius: 24, backgroundColor: colors.surface, padding: 22, gap: 4 },
  dialogIcon: { alignSelf: 'center', width: 56, height: 56, borderRadius: 28, backgroundColor: colors.surfaceTint, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  dialogTitle: { textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 19, fontWeight: '800', color: colors.ink },
  dialogBody: { textAlign: 'center', fontFamily: typography.fontFamily.ui, fontSize: 14, lineHeight: 20, color: colors.secondary, marginTop: 4, marginBottom: 14 },
  dialogSecondary: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
});
