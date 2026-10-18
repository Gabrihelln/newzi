import React, { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StatusBar, StyleSheet, Text, TextInput, useWindowDimensions, View } from 'react-native';
import Svg, { Circle, Path, Polyline, Rect } from 'react-native-svg';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { User as FirebaseUser } from '@react-native-firebase/auth';
import { ClientError, CONNECTION_ERROR_MESSAGE } from '../api/client';
import { useStyles, useTheme, type Palette } from '../theme';
import { BrandStack, Glows, Lockup } from './BrandStack';
import type { User } from '../types/api';
import { appleSignInAvailable, friendlyFirebaseAuthError, loginWithApple, loginWithFirebase, loginWithGoogle, registerWithFirebase, resetPasswordWithFirebase } from '../services/firebaseAuth';
import { passwordChecks } from '../services/passwordRules';

export type AuthStackParamList = { AuthEntry: undefined; Login: undefined; CreateAccount: undefined; ForgotPassword: undefined };
type AuthRoute<T extends keyof AuthStackParamList> = NativeStackScreenProps<AuthStackParamList, T>;
type SessionHandler = (user: User) => Promise<void>;

type IconName = 'back' | 'next' | 'mail' | 'lock' | 'person' | 'eye' | 'eyeOff' | 'check' | 'info' | 'apple';
function Icon({ name, size = 22, color: requested }: { name: IconName; size?: number; color?: string }) {
  const { colors } = useTheme();
  const color = requested ?? colors.tone('#102A58', colors.ink);
  const stroke = { stroke: color, strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return <Svg width={size} height={size} viewBox="0 0 24 24">
    {name === 'back' && <Path d="M14.5 3.5 6 12l8.5 8.5" {...stroke} />}
    {name === 'next' && <Path d="m9 5 7 7-7 7" {...stroke} strokeWidth={2.1} />}
    {name === 'mail' && <><Rect x="3" y="5" width="18" height="14" rx="2" {...stroke} /><Path d="m4 7 8 6 8-6" {...stroke} /></>}
    {name === 'lock' && <><Rect x="5" y="10" width="14" height="11" rx="2" {...stroke} /><Path d="M8 10V7a4 4 0 0 1 8 0v3" {...stroke} /></>}
    {name === 'person' && <><Circle cx="12" cy="7" r="4" {...stroke} /><Path d="M4 21v-2a8 8 0 0 1 16 0v2" {...stroke} /></>}
    {name === 'eye' && <><Path d="M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6-10-6-10-6Z" {...stroke} /><Circle cx="12" cy="12" r="2.5" {...stroke} /></>}
    {name === 'eyeOff' && <><Path d="M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6-10-6-10-6Z" {...stroke} /><Path d="m3 21 18-18" {...stroke} /></>}
    {name === 'check' && <Polyline points="5 12 9 16 19 6" {...stroke} strokeWidth={2.4} />}
    {name === 'info' && <><Circle cx="12" cy="12" r="9" {...stroke} /><Path d="M12 11v6" {...stroke} /><Circle cx="12" cy="7.5" r=".9" fill={color} /></>}
    {name === 'apple' && <><Path d="M16.9 12.6c.1 2 1.5 2.7 1.6 2.8-.8 2.1-2.2 4.2-3.9 4.2-.9 0-1.3-.5-2.4-.5s-1.6.5-2.4.5c-1.7.1-3.2-2.3-4-4.4-1.6-3.5-.7-8.5 3.2-8.6 1 0 1.9.6 2.5.6.7 0 1.8-.7 3-.6 1.3.1 2.2.6 2.8 1.5-2.4 1.3-2.3 4.3-.2 5.5Z" fill={color} /><Path d="M14.5 5.5c.7-.8 1.1-1.9 1-3-1 .1-2.1.8-2.8 1.6-.7.8-1.1 1.8-1 2.8 1.1.1 2.1-.5 2.8-1.4Z" fill={color} /></>}
  </Svg>;
}

function Screen({ children, entry = false }: { children: React.ReactNode; entry?: boolean }) {
  const s = useStyles(makeStyles);
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return <SafeAreaView style={s.safe} edges={['top', 'bottom']}><StatusBar barStyle={theme.statusBar} backgroundColor={theme.colors.background} />
    {!entry && <Glows />}
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.scroll, { paddingBottom: Math.max(16, (entry ? 40 : 34) - insets.bottom) }, entry && s.entryScroll]}>{children}</ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
function Back({ onPress }: { onPress: () => void }) { const s = useStyles(makeStyles); return <Pressable accessibilityRole="button" accessibilityLabel="Voltar" hitSlop={10} onPress={onPress} style={s.back}><Icon name="back" size={25} /></Pressable>; }
function Header({ title, subtitle, back, compact = false }: { title: string; subtitle: string; back: () => void; compact?: boolean }) {
  const s = useStyles(makeStyles);
  return <><Back onPress={back} /><Lockup height={compact ? 40 : 50} style={compact ? s.lockupCompact : s.lockup} />
    <Text accessibilityRole="header" style={[s.title, compact && s.titleCompact]}>{title}</Text><Text style={[s.subtitle, compact && s.subtitleCompact]}>{subtitle}</Text></>;
}
function MainButton({ title, onPress, busy, disabled, style }: { title: string; onPress: () => void; busy?: boolean; disabled?: boolean; style?: object }) { const s = useStyles(makeStyles); const { colors } = useTheme(); return <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityState={{ disabled: busy || disabled, busy }} disabled={busy || disabled} onPress={onPress} style={({ pressed }) => [s.mainButton, style, (busy || disabled) && s.disabledButton, pressed && s.pressed]}>{busy ? <ActivityIndicator color={colors.onPrimary} /> : <><Text style={s.mainButtonText}>{title}</Text><View style={s.buttonArrow}><Icon name="next" size={20} color={colors.onPrimary} /></View></>}</Pressable>; }
function SecondaryButton({ title, onPress }: { title: string; onPress: () => void }) { const s = useStyles(makeStyles); return <Pressable accessibilityRole="button" accessibilityLabel={title} onPress={onPress} style={({ pressed }) => [s.secondaryButton, pressed && s.pressed]}><Text style={s.secondaryButtonText}>{title}</Text></Pressable>; }
function Field({ icon, placeholder, value, onChangeText, secure = false, autoComplete, keyboardType, testID }: { icon: IconName; placeholder: string; value: string; onChangeText: (text: string) => void; secure?: boolean; autoComplete?: 'email' | 'name' | 'password' | 'new-password'; keyboardType?: 'email-address'; testID?: string }) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState(false);
  return <View style={[s.field, (focused || !!value) && s.fieldFilled]}><Icon name={icon} size={21} /><TextInput testID={testID} accessibilityLabel={placeholder} style={[s.fieldInput, secure && !visible && !!value && s.fieldSecret]} placeholder={placeholder} placeholderTextColor={colors.tone('#59719B', colors.muted)} value={value} onChangeText={onChangeText} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} autoCapitalize={icon === 'mail' ? 'none' : icon === 'person' ? 'words' : 'none'} autoCorrect={false} keyboardType={keyboardType} autoComplete={autoComplete} secureTextEntry={secure && !visible} returnKeyType="next" />{secure && <Pressable accessibilityRole="button" accessibilityLabel={visible ? 'Ocultar senha' : 'Mostrar senha'} onPress={() => setVisible(!visible)} hitSlop={8}><Icon name={visible ? 'eyeOff' : 'eye'} size={21} /></Pressable>}</View>;
}
function ErrorMessage({ error }: { error: string }) { const s = useStyles(makeStyles); return error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null; }
function errorText(error: unknown) {
  if (error instanceof ClientError) return ({ AUTH_REQUIRED: 'Não foi possível validar sua sessão. Confira a data e hora do dispositivo e tente novamente.', TOKEN_ERROR: 'Não foi possível validar sua sessão.', BACKEND_UNREACHABLE: CONNECTION_ERROR_MESSAGE, BACKEND_401: 'Sua sessão terminou. Entre novamente na sua conta.', BACKEND_403: 'Não foi possível acessar sua conta agora.', BACKEND_500: 'O Newzi está instável no momento. Tente novamente em instantes.', PROFILE_LOAD_ERROR: 'Não foi possível carregar seu perfil.', ONBOARDING_LOAD_ERROR: 'Não foi possível carregar seu onboarding.', TIMEOUT: 'A conexão demorou demais. Tente novamente.', OFFLINE: 'Você está offline. Tente novamente.' } as Record<string, string>)[error.code] || error.message;
  return friendlyFirebaseAuthError(error);
}
function asAppUser(firebaseUser: FirebaseUser, fallbackEmail = '', fallbackName = ''): User { return { id: firebaseUser.uid, email: firebaseUser.email || fallbackEmail, display_name: firebaseUser.displayName || fallbackName, onboarding_status: 'NOT_STARTED' }; }
async function finishAuth(firebaseUser: FirebaseUser, onAuthenticated: SessionHandler, email = '', name = '') { await onAuthenticated(asAppUser(firebaseUser, email, name)); }
const emailLooksValid = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export function AuthEntryScreen({ navigation, bootstrapError, onRetrySession }: AuthRoute<'AuthEntry'> & { bootstrapError: string; onRetrySession: () => void }) {
  const s = useStyles(makeStyles);
  const { height } = useWindowDimensions();
  const compact = height < 730;
  return <Screen entry>
    <View style={s.entryHero}><BrandStack size={compact ? 110 : 132} />
      <View style={[s.entryCopy, { marginTop: compact ? 44 : 64 }]}><Text accessibilityRole="header" style={s.entryTitle}>Notícias que fazem{'\n'}parte do seu dia.</Text><Text style={s.entrySubtitle}>Um resumo diário, claro e{'\n'}personalizado, do seu jeito.</Text></View>
    </View>
    <View style={s.entryActions}>{!!bootstrapError && <View style={s.retryCard}><Text accessibilityRole="alert" style={s.retryText}>{bootstrapError}</Text><Pressable accessibilityRole="button" onPress={onRetrySession}><Text style={s.retryAction}>Tentar novamente</Text></Pressable></View>}<MainButton title="Entrar" onPress={() => navigation.navigate('Login')} /><SecondaryButton title="Criar conta" onPress={() => navigation.navigate('CreateAccount')} /></View>
  </Screen>;
}

function GoogleMark() { return <Svg width={22} height={22} viewBox="0 0 24 24"><Path fill="#4285F4" d="M21.35 12.24c0-.71-.06-1.23-.2-1.78H12v3.55h5.37a4.8 4.8 0 0 1-1.98 3.14v2.6h3.18c1.86-1.72 2.78-4.25 2.78-7.51Z" /><Path fill="#34A853" d="M12 21.5c2.7 0 4.96-.9 6.62-2.45l-3.18-2.6c-.9.6-2.05.96-3.44.96-2.64 0-4.87-1.78-5.67-4.16H3.05v2.67A9.5 9.5 0 0 0 12 21.5Z" /><Path fill="#FBBC05" d="M6.33 13.25A5.8 5.8 0 0 1 6.03 12c0-.43.1-.85.3-1.25V8.08H3.05A9.5 9.5 0 0 0 2.5 12c0 1.53.37 2.99 1.05 4.25l3.28-3Z" /><Path fill="#EA4335" d="M12 6.59c1.47 0 2.8.5 3.84 1.53l2.86-2.87A9.22 9.22 0 0 0 12 2.5a9.5 9.5 0 0 0-8.95 5.58l3.28 2.67C7.13 8.37 9.36 6.59 12 6.59Z" /></Svg>; }
function SocialButtons({ onGoogle, onApple, busy }: { onGoogle: () => void; onApple: () => void; busy: boolean }) { const s = useStyles(makeStyles); const { colors } = useTheme(); return <><View style={s.divider}><View style={s.dividerLine} /><Text style={s.dividerText}>ou</Text><View style={s.dividerLine} /></View><Pressable disabled={busy} accessibilityRole="button" accessibilityLabel="Continuar com o Google" onPress={onGoogle} style={({ pressed }) => [s.socialButton, !appleSignInAvailable && s.socialLast, pressed && s.pressed]}><GoogleMark /><Text style={s.socialText}>Continuar com o Google</Text></Pressable>{/* Apple only on iPhone: Android offers Google alone. */}{appleSignInAvailable && <Pressable disabled={busy} accessibilityRole="button" accessibilityLabel="Continuar com a Apple" onPress={onApple} style={({ pressed }) => [s.socialButton, s.socialLast, pressed && s.pressed]}><Icon name="apple" size={22} color={colors.tone('#080B12', colors.ink)} /><Text style={s.socialText}>Continuar com a Apple</Text></Pressable>}</>; }
function FooterLink({ prompt, action, onPress }: { prompt: string; action: string; onPress: () => void }) { const s = useStyles(makeStyles); return <View style={s.footer}><Text style={s.footerText}>{prompt} </Text><Pressable accessibilityRole="button" onPress={onPress} hitSlop={8}><Text style={s.footerAction}>{action}</Text></Pressable></View>; }
function useAuthForm(onAuthenticated: SessionHandler) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (operation: () => Promise<FirebaseUser>, email = '', name = '') => { if (busy) return; setBusy(true); setError(''); try { await finishAuth(await operation(), onAuthenticated, email, name); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); } };
  return { busy, error, setError, run };
}

export function LoginScreen({ navigation, onAuthenticated }: AuthRoute<'Login'> & { onAuthenticated: SessionHandler }) {
  const s = useStyles(makeStyles);
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const auth = useAuthForm(onAuthenticated);
  const submit = () => { if (!emailLooksValid(email)) return auth.setError('Digite um e-mail válido.'); if (!password) return auth.setError('Digite sua senha.'); void auth.run(() => loginWithFirebase(email, password), email); };
  return <Screen><Header back={() => navigation.goBack()} title="Entre na sua conta" subtitle={'Acesse seu resumo personalizado\ne continue de onde parou.'} />
    <View style={s.form}><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); auth.setError(''); }} autoComplete="email" keyboardType="email-address" testID="login-email" /><Field icon="lock" placeholder="Senha" value={password} onChangeText={text => { setPassword(text); auth.setError(''); }} autoComplete="password" secure testID="login-password" />
      <Pressable accessibilityRole="button" onPress={() => navigation.navigate('ForgotPassword')} style={s.forgotLink}><Text style={s.linkText}>Esqueci minha senha</Text></Pressable><ErrorMessage error={auth.error} /><MainButton title="Entrar" busy={auth.busy} onPress={submit} />
      <SocialButtons busy={auth.busy} onGoogle={() => void auth.run(loginWithGoogle)} onApple={() => void auth.run(loginWithApple)} />
    </View><FooterLink prompt="Não tem uma conta?" action="Criar agora" onPress={() => navigation.replace('CreateAccount')} />
  </Screen>;
}

function PasswordRule({ label, passed, optional }: { label: string; passed: boolean; optional?: boolean }) { const s = useStyles(makeStyles); return <View accessible accessibilityLabel={`${label}${passed ? ', atendido' : optional ? '' : ', pendente'}`} style={s.rule}><View style={[s.ruleIcon, passed && s.ruleIconPassed]}>{passed ? <Icon name="check" size={12} /> : <Text style={s.ruleDot}>{optional ? '·' : '○'}</Text>}</View><Text style={[s.ruleText, passed && s.ruleTextPassed]}>{label}</Text></View>; }
export function CreateAccountScreen({ navigation, onAuthenticated }: AuthRoute<'CreateAccount'> & { onAuthenticated: SessionHandler }) {
  const s = useStyles(makeStyles);
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const auth = useAuthForm(onAuthenticated);
  const { longEnough, letterAndNumber, special } = passwordChecks(password);
  const submit = () => { if (!name.trim()) return auth.setError('Digite seu nome completo.'); if (!emailLooksValid(email)) return auth.setError('Digite um e-mail válido.'); if (!longEnough || !letterAndNumber) return auth.setError('Crie uma senha com 8 caracteres, uma letra e um número.'); void auth.run(() => registerWithFirebase(email, password, name), email, name); };
  return <Screen><Header back={() => navigation.goBack()} title="Crie sua conta" subtitle={'É rápido e grátis. Configure seu\nresumo em poucos passos.'} compact />
    <View style={[s.form, s.registerForm]}><Field icon="person" placeholder="Nome completo" value={name} onChangeText={text => { setName(text); auth.setError(''); }} autoComplete="name" testID="register-name" /><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); auth.setError(''); }} autoComplete="email" keyboardType="email-address" testID="register-email" /><Field icon="lock" placeholder="Senha" value={password} onChangeText={text => { setPassword(text); auth.setError(''); }} autoComplete="new-password" secure testID="register-password" />
      <View style={s.rules}><PasswordRule label="Pelo menos 8 caracteres" passed={longEnough} /><PasswordRule label="Uma letra e um número" passed={letterAndNumber} /><PasswordRule label="Use um caractere especial (opcional)" passed={special} optional /></View><ErrorMessage error={auth.error} /><MainButton title="Criar conta" busy={auth.busy} onPress={submit} style={s.registerButton} />
      <SocialButtons busy={auth.busy} onGoogle={() => void auth.run(loginWithGoogle)} onApple={() => void auth.run(loginWithApple)} />
    </View><FooterLink prompt="Já tem uma conta?" action="Entrar agora" onPress={() => navigation.replace('Login')} />
  </Screen>;
}

export function ForgotPasswordScreen({ navigation }: AuthRoute<'ForgotPassword'>) {
  const s = useStyles(makeStyles);
  const { colors } = useTheme();
  const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [sent, setSent] = useState(false);
  const submit = async () => { if (!emailLooksValid(email)) return setError('Digite um e-mail válido.'); setBusy(true); setError(''); try { await resetPasswordWithFirebase(email); setSent(true); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); } };
  return <Screen><Header back={() => navigation.goBack()} title="Esqueceu sua senha?" subtitle={'Digite seu e-mail para receber\nas instruções de redefinição.'} />
    <View style={s.forgotForm}><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); setSent(false); setError(''); }} autoComplete="email" keyboardType="email-address" testID="reset-email" /><ErrorMessage error={error} /><MainButton title={sent ? 'Reenviar instruções' : 'Enviar instruções'} busy={busy} onPress={() => void submit()} style={s.forgotButton} /></View>
    <View accessibilityLiveRegion="polite" style={s.infoCard}><Icon name="info" size={26} color={colors.tone('#087CF0', colors.primary)} /><Text style={s.infoText}>{sent ? 'Enviamos um link seguro para o seu e-mail. Confira também a pasta de spam.' : 'Enviaremos um link seguro para o seu e-mail. Confira também a pasta de spam.'}</Text></View>
    <FooterLink prompt="Lembrou a senha?" action="Voltar para entrar" onPress={() => navigation.goBack()} />
  </Screen>;
}

// Light values are the prototype's (design/onboarding); the few whose text fell under 4.5:1 are a shade darker.
const makeStyles = (colors: Palette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingTop: 2 }, entryScroll: { justifyContent: 'space-between', paddingTop: 0 },
  back: { width: 44, height: 44, justifyContent: 'center', alignItems: 'flex-start', marginLeft: -6 },
  lockup: { marginTop: 4 }, lockupCompact: { marginTop: 0 },
  title: { color: colors.tone('#081D43', colors.ink), fontFamily: 'Inter', fontSize: 28, fontWeight: '700', textAlign: 'center', letterSpacing: -1, lineHeight: 34, marginTop: 36 }, titleCompact: { marginTop: 24 },
  subtitle: { color: colors.tone('#56709F', colors.secondary), fontFamily: 'Inter', fontSize: 15.5, lineHeight: 22, textAlign: 'center', marginTop: 12 }, subtitleCompact: { fontSize: 15, marginTop: 8 },
  entryHero: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 24 }, entryCopy: { alignItems: 'center' },
  entryTitle: { color: colors.tone('#081D43', colors.ink), fontFamily: 'Inter', fontSize: 31, lineHeight: 38, fontWeight: '700', textAlign: 'center', letterSpacing: -1 },
  entrySubtitle: { color: colors.tone('#56709F', colors.secondary), fontFamily: 'Inter', textAlign: 'center', fontSize: 16, lineHeight: 24, marginTop: 12 },
  entryActions: { gap: 10, paddingTop: 16 },
  retryCard: { backgroundColor: colors.topicRed.background, borderRadius: 15, padding: 12, alignItems: 'center' }, retryText: { color: colors.tone('#A73E50', colors.topicRed.icon), fontFamily: 'Inter', fontSize: 13, lineHeight: 18, textAlign: 'center' }, retryAction: { color: colors.tone('#0069FA', colors.primary), fontFamily: 'Inter', fontWeight: '700', marginTop: 6, fontSize: 14 },
  mainButton: { height: 56, borderRadius: 28, backgroundColor: colors.tone('#0868F7', colors.primary), justifyContent: 'center', alignItems: 'center', paddingHorizontal: 20, shadowColor: '#0868F7', shadowOpacity: .45, shadowRadius: 11, shadowOffset: { width: 0, height: 10 } },
  disabledButton: { opacity: .65 }, pressed: { opacity: .82 }, mainButtonText: { color: colors.onPrimary, fontFamily: 'Inter', fontSize: 17, fontWeight: '600' }, buttonArrow: { position: 'absolute', right: 20 },
  secondaryButton: { height: 56, borderRadius: 28, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }, secondaryButtonText: { color: colors.tone('#0B2149', colors.ink), fontFamily: 'Inter', fontSize: 17, fontWeight: '600' },
  form: { marginTop: 34 }, registerForm: { marginTop: 22 }, registerButton: { marginTop: 16 }, forgotForm: { marginTop: 36 }, forgotButton: { marginTop: 2 },
  field: { height: 58, borderRadius: 22, borderWidth: 1, borderColor: colors.tone('#D8E6F6', colors.border), backgroundColor: colors.tone('#F5F9FD', colors.surfaceTint), flexDirection: 'row', alignItems: 'center', gap: 16, paddingHorizontal: 20, marginBottom: 10 },
  fieldFilled: { backgroundColor: colors.surface, borderColor: colors.tone('#BFD9F6', colors.borderStrong) },
  fieldInput: { flex: 1, fontFamily: 'Inter', fontSize: 16, color: colors.tone('#0A2149', colors.ink), paddingVertical: 0 }, fieldSecret: { letterSpacing: 3 },
  forgotLink: { alignSelf: 'flex-end', minHeight: 30, justifyContent: 'center', marginTop: 2, marginRight: 4, marginBottom: 14 }, linkText: { color: colors.tone('#0069FA', colors.primary), fontFamily: 'Inter', fontSize: 14.5, fontWeight: '600' },
  error: { color: colors.tone('#B43B48', colors.topicRed.icon), fontFamily: 'Inter', fontSize: 13, lineHeight: 19, marginTop: 2, marginBottom: 10 },
  divider: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 18, marginBottom: 14 }, dividerLine: { flex: 1, height: 1, backgroundColor: colors.tone('#D5E3F2', colors.border) }, dividerText: { color: colors.tone('#455C82', colors.secondary), fontFamily: 'Inter', fontSize: 14 },
  socialButton: { height: 52, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.tone('#E2ECF7', colors.border), borderRadius: 28, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 14, marginBottom: 8 }, socialLast: { marginBottom: 0 },
  socialText: { color: colors.tone('#0A2047', colors.ink), fontFamily: 'Inter', fontSize: 15, fontWeight: '600' },
  footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: 'auto', paddingTop: 20, flexWrap: 'wrap' }, footerText: { color: colors.tone('#56709F', colors.secondary), fontFamily: 'Inter', fontSize: 14 }, footerAction: { color: colors.tone('#0067F5', colors.primary), fontFamily: 'Inter', fontSize: 14, fontWeight: '700' },
  rules: { marginTop: 2, marginHorizontal: 4 }, rule: { height: 23, flexDirection: 'row', alignItems: 'center', gap: 9 }, ruleIcon: { width: 19, height: 19, borderRadius: 10, backgroundColor: colors.surfaceTint, justifyContent: 'center', alignItems: 'center' }, ruleIconPassed: { backgroundColor: colors.tone('#D9ECFF', colors.selected) }, ruleDot: { color: colors.tone('#58709A', colors.secondary), fontSize: 13, lineHeight: 16 },
  ruleText: { color: colors.tone('#58709A', colors.secondary), fontFamily: 'Inter', fontSize: 13 }, ruleTextPassed: { color: colors.tone('#2E5B91', colors.ink) },
  infoCard: { backgroundColor: colors.surfaceTint, borderRadius: 20, paddingHorizontal: 17, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', gap: 13, marginTop: 22 }, infoText: { flex: 1, color: colors.tone('#4F6A93', colors.secondary), fontFamily: 'Inter', fontSize: 13, lineHeight: 19 },
});
