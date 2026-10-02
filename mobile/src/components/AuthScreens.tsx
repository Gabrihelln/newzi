import React, { useState } from 'react';
import { ActivityIndicator, Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StatusBar, StyleSheet, Text, TextInput, useWindowDimensions, View } from 'react-native';
import Svg, { Circle, Path, Polyline, Rect } from 'react-native-svg';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { User as FirebaseUser } from '@react-native-firebase/auth';
import { ClientError } from '../api/client';
import { colors } from '../theme';
import type { User } from '../types/api';
import { ensureUserProfile } from '../services/firestoreUser';
import { friendlyFirebaseAuthError, loginWithApple, loginWithFirebase, loginWithGoogle, registerWithFirebase, resetPasswordWithFirebase } from '../services/firebaseAuth';

export type AuthStackParamList = { AuthEntry: undefined; Login: undefined; CreateAccount: undefined; ForgotPassword: undefined };
type AuthRoute<T extends keyof AuthStackParamList> = NativeStackScreenProps<AuthStackParamList, T>;
type SessionHandler = (user: User) => Promise<void>;
const logo = require('../../assets/onboarding/newzi-lockup-reference.png');
const readingMascot = require('../../assets/onboarding/new-reading.png');
const envelopeMascot = require('../../assets/auth/new-envelope.png');

type IconName = 'back' | 'next' | 'mail' | 'lock' | 'person' | 'eye' | 'eyeOff' | 'check' | 'info' | 'apple';
function Icon({ name, size = 22, color = '#102A58' }: { name: IconName; size?: number; color?: string }) {
  const stroke = { stroke: color, strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return <Svg width={size} height={size} viewBox="0 0 24 24">
    {name === 'back' && <Path d="M14.5 3.5 6 12l8.5 8.5" {...stroke} />}
    {name === 'next' && <Path d="m9 4 8 8-8 8" {...stroke} />}
    {name === 'mail' && <><Rect x="3" y="5" width="18" height="14" rx="2" {...stroke} /><Path d="m4 7 8 6 8-6" {...stroke} /></>}
    {name === 'lock' && <><Rect x="5" y="10" width="14" height="11" rx="2" {...stroke} /><Path d="M8 10V7a4 4 0 0 1 8 0v3" {...stroke} /><Circle cx="12" cy="15.5" r="1" fill={color} /></>}
    {name === 'person' && <><Circle cx="12" cy="7" r="4" {...stroke} /><Path d="M4 21v-2a8 8 0 0 1 16 0v2" {...stroke} /></>}
    {name === 'eye' && <><Path d="M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6-10-6-10-6Z" {...stroke} /><Circle cx="12" cy="12" r="2.5" {...stroke} /></>}
    {name === 'eyeOff' && <><Path d="M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6-10-6-10-6Z" {...stroke} /><Path d="m3 21 18-18" {...stroke} /></>}
    {name === 'check' && <Polyline points="4 12 9 17 20 6" {...stroke} />}
    {name === 'info' && <><Circle cx="12" cy="12" r="10" fill="#C9E4FF" /><Path d="M12 10v7" {...stroke} /><Circle cx="12" cy="6.7" r="1" fill={color} /></>}
    {name === 'apple' && <><Path d="M16.9 12.6c.1 2 1.5 2.7 1.6 2.8-.8 2.1-2.2 4.2-3.9 4.2-.9 0-1.3-.5-2.4-.5s-1.6.5-2.4.5c-1.7.1-3.2-2.3-4-4.4-1.6-3.5-.7-8.5 3.2-8.6 1 0 1.9.6 2.5.6.7 0 1.8-.7 3-.6 1.3.1 2.2.6 2.8 1.5-2.4 1.3-2.3 4.3-.2 5.5Z" fill={color} /><Path d="M14.5 5.5c.7-.8 1.1-1.9 1-3-1 .1-2.1.8-2.8 1.6-.7.8-1.1 1.8-1 2.8 1.1.1 2.1-.5 2.8-1.4Z" fill={color} /></>}
  </Svg>;
}

function Screen({ children, entry = false }: { children: React.ReactNode; entry?: boolean }) {
  const insets = useSafeAreaInsets();
  return <SafeAreaView style={s.safe} edges={['top', 'bottom']}><StatusBar barStyle="dark-content" backgroundColor="#F7FBFF" />
    <View pointerEvents="none" style={s.topGlow} />
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.scroll, { paddingBottom: Math.max(insets.bottom, 18) + 10 }, entry && s.entryScroll]}>{children}</ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
function Brand({ wide = false, compact = false }: { wide?: boolean; compact?: boolean }) { return <Image source={logo} resizeMode="contain" style={[s.logo, wide && s.logoWide, compact && s.logoCompact]} accessibilityLabel="newzi" />; }
function Back({ onPress }: { onPress: () => void }) { return <Pressable accessibilityRole="button" accessibilityLabel="Voltar" hitSlop={10} onPress={onPress} style={s.back}><Icon name="back" size={25} /></Pressable>; }
function Header({ title, subtitle, back, compact = false }: { title: string; subtitle: string; back: () => void; compact?: boolean }) { return <><Back onPress={back} /><Brand compact={compact} /><Text style={s.title}>{title}</Text><Text style={s.subtitle}>{subtitle}</Text></>; }
function MainButton({ title, onPress, busy, disabled }: { title: string; onPress: () => void; busy?: boolean; disabled?: boolean }) { return <Pressable accessibilityRole="button" accessibilityLabel={title} disabled={busy || disabled} onPress={onPress} style={({ pressed }) => [s.mainButton, (busy || disabled) && s.disabledButton, pressed && s.pressed]}>{busy ? <ActivityIndicator color="#FFF" /> : <><Text style={s.mainButtonText}>{title}</Text><View style={s.buttonArrow}><Icon name="next" color="#FFF" /></View></>}</Pressable>; }
function SecondaryButton({ title, onPress }: { title: string; onPress: () => void }) { return <Pressable accessibilityRole="button" accessibilityLabel={title} onPress={onPress} style={s.secondaryButton}><Text style={s.secondaryButtonText}>{title}</Text></Pressable>; }
function Field({ icon, placeholder, value, onChangeText, secure = false, autoComplete, keyboardType, testID }: { icon: IconName; placeholder: string; value: string; onChangeText: (text: string) => void; secure?: boolean; autoComplete?: 'email' | 'name' | 'password' | 'new-password'; keyboardType?: 'email-address'; testID?: string }) {
  const [visible, setVisible] = useState(false);
  return <View style={s.field}><Icon name={icon} size={21} /><TextInput testID={testID} accessibilityLabel={placeholder} style={s.fieldInput} placeholder={placeholder} placeholderTextColor="#7E92B5" value={value} onChangeText={onChangeText} autoCapitalize={icon === 'mail' ? 'none' : icon === 'person' ? 'words' : 'none'} autoCorrect={false} keyboardType={keyboardType} autoComplete={autoComplete} secureTextEntry={secure && !visible} returnKeyType="next" />{secure && <Pressable accessibilityRole="button" accessibilityLabel={visible ? 'Ocultar senha' : 'Mostrar senha'} onPress={() => setVisible(!visible)} hitSlop={8}><Icon name={visible ? 'eyeOff' : 'eye'} size={21} /></Pressable>}</View>;
}
function ErrorMessage({ error }: { error: string }) { return error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null; }
function errorText(error: unknown) {
  if (error instanceof ClientError) return ({ AUTH_REQUIRED: 'Não foi possível validar sua sessão. Confira a data e hora do dispositivo e tente novamente.', TOKEN_ERROR: 'Não foi possível validar sua sessão.', BACKEND_UNREACHABLE: 'Não foi possível conectar ao backend.', BACKEND_401: 'O backend recusou sua sessão.', BACKEND_403: 'O backend bloqueou esta sessão.', BACKEND_500: 'O backend apresentou um erro.', PROFILE_LOAD_ERROR: 'Não foi possível carregar seu perfil.', ONBOARDING_LOAD_ERROR: 'Não foi possível carregar seu onboarding.', TIMEOUT: 'A conexão demorou demais. Tente novamente.', OFFLINE: 'Você está offline. Tente novamente.' } as Record<string, string>)[error.code] || error.message;
  return friendlyFirebaseAuthError(error);
}
function asAppUser(firebaseUser: FirebaseUser, fallbackEmail = '', fallbackName = ''): User { return { id: firebaseUser.uid, email: firebaseUser.email || fallbackEmail, display_name: firebaseUser.displayName || fallbackName, onboarding_status: 'NOT_STARTED' }; }
async function finishAuth(firebaseUser: FirebaseUser, onAuthenticated: SessionHandler, email = '', name = '', createProfile = false) { if (createProfile) await ensureUserProfile(firebaseUser); await onAuthenticated(asAppUser(firebaseUser, email, name)); }
const emailLooksValid = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export function AuthEntryScreen({ navigation, bootstrapError, onRetrySession }: AuthRoute<'AuthEntry'> & { bootstrapError: string; onRetrySession: () => void }) {
  const { width, height } = useWindowDimensions();
  return <Screen entry><View style={s.entryTop}><Brand wide /><Text style={s.entryTitle}>Notícias que{'\n'}fazem parte{'\n'}do seu dia.</Text><Text style={s.entrySubtitle}>Um briefing diário, claro e{'\n'}personalizado, do seu jeito.</Text></View>
    <View style={[s.entryArt, { height: Math.min(width * .82, height * .37) }]}><View style={s.artHalo} /><Image source={readingMascot} resizeMode="contain" style={s.entryMascot} /></View>
    <View style={s.dots}><View style={s.dotActive} /><View style={s.dot} /><View style={s.dot} /></View>
    <View style={s.entryActions}>{!!bootstrapError && <View style={s.retryCard}><Text accessibilityRole="alert" style={s.retryText}>{bootstrapError}</Text><Pressable accessibilityRole="button" onPress={onRetrySession}><Text style={s.retryAction}>Tentar novamente</Text></Pressable></View>}<MainButton title="Entrar" onPress={() => navigation.navigate('Login')} /><SecondaryButton title="Criar conta" onPress={() => navigation.navigate('CreateAccount')} /></View>
  </Screen>;
}

function GoogleMark() { return <Svg width={25} height={25} viewBox="0 0 24 24"><Path fill="#4285F4" d="M21.35 12.24c0-.71-.06-1.23-.2-1.78H12v3.55h5.37a4.8 4.8 0 0 1-1.98 3.14v2.6h3.18c1.86-1.72 2.78-4.25 2.78-7.51Z" /><Path fill="#34A853" d="M12 21.5c2.7 0 4.96-.9 6.62-2.45l-3.18-2.6c-.9.6-2.05.96-3.44.96-2.64 0-4.87-1.78-5.67-4.16H3.05v2.67A9.5 9.5 0 0 0 12 21.5Z" /><Path fill="#FBBC05" d="M6.33 13.25A5.8 5.8 0 0 1 6.03 12c0-.43.1-.85.3-1.25V8.08H3.05A9.5 9.5 0 0 0 2.5 12c0 1.53.37 2.99 1.05 4.25l3.28-3Z" /><Path fill="#EA4335" d="M12 6.59c1.47 0 2.8.5 3.84 1.53l2.86-2.87A9.22 9.22 0 0 0 12 2.5a9.5 9.5 0 0 0-8.95 5.58l3.28 2.67C7.13 8.37 9.36 6.59 12 6.59Z" /></Svg>; }
function SocialButtons({ onGoogle, onApple, busy }: { onGoogle: () => void; onApple: () => void; busy: boolean }) { return <><View style={s.divider}><View style={s.dividerLine} /><Text style={s.dividerText}>ou</Text><View style={s.dividerLine} /></View><Pressable disabled={busy} accessibilityRole="button" accessibilityLabel="Continuar com o Google" onPress={onGoogle} style={s.socialButton}><GoogleMark /><Text style={s.socialText}>Continuar com o Google</Text></Pressable><Pressable disabled={busy} accessibilityRole="button" accessibilityLabel="Continuar com a Apple" onPress={onApple} style={s.socialButton}><Icon name="apple" size={25} color="#080B12" /><Text style={s.socialText}>Continuar com a Apple</Text></Pressable></>; }
function FooterLink({ prompt, action, onPress }: { prompt: string; action: string; onPress: () => void }) { return <View style={s.footer}><Text style={s.footerText}>{prompt} </Text><Pressable accessibilityRole="button" onPress={onPress}><Text style={s.footerAction}>{action}</Text></Pressable></View>; }
function useAuthForm(onAuthenticated: SessionHandler) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (operation: () => Promise<FirebaseUser>, email = '', name = '', createProfile = false) => { if (busy) return; setBusy(true); setError(''); try { await finishAuth(await operation(), onAuthenticated, email, name, createProfile); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); } };
  return { busy, error, setError, run };
}

export function LoginScreen({ navigation, onAuthenticated }: AuthRoute<'Login'> & { onAuthenticated: SessionHandler }) {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const auth = useAuthForm(onAuthenticated);
  const submit = () => { if (!emailLooksValid(email)) return auth.setError('Digite um e-mail válido.'); if (!password) return auth.setError('Digite sua senha.'); void auth.run(() => loginWithFirebase(email, password), email); };
  return <Screen><Header back={() => navigation.goBack()} title="Entre na sua conta" subtitle={'Acesse seu briefing personalizado\ne continue de onde parou.'} />
    <View style={s.form}><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); auth.setError(''); }} autoComplete="email" keyboardType="email-address" testID="login-email" /><Field icon="lock" placeholder="Senha" value={password} onChangeText={text => { setPassword(text); auth.setError(''); }} autoComplete="password" secure testID="login-password" />
      <Pressable accessibilityRole="button" onPress={() => navigation.navigate('ForgotPassword')} style={s.forgotLink}><Text style={s.linkText}>Esqueci minha senha</Text></Pressable><ErrorMessage error={auth.error} /><MainButton title="Entrar" busy={auth.busy} onPress={submit} />
      <SocialButtons busy={auth.busy} onGoogle={() => void auth.run(loginWithGoogle, '', '', true)} onApple={() => void auth.run(loginWithApple, '', '', true)} />
    </View><FooterLink prompt="Não tem uma conta?" action="Criar agora" onPress={() => navigation.replace('CreateAccount')} />
  </Screen>;
}

function PasswordRule({ label, passed, optional }: { label: string; passed: boolean; optional?: boolean }) { return <View style={s.rule}><View style={[s.ruleIcon, passed && s.ruleIconPassed]}>{passed ? <Icon name="check" size={14} /> : <Text style={s.ruleDot}>{optional ? '·' : '○'}</Text>}</View><Text style={[s.ruleText, passed && s.ruleTextPassed]}>{label}</Text></View>; }
export function CreateAccountScreen({ navigation, onAuthenticated }: AuthRoute<'CreateAccount'> & { onAuthenticated: SessionHandler }) {
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const auth = useAuthForm(onAuthenticated);
  const longEnough = password.length >= 8; const letterAndNumber = /[A-Za-zÀ-ÿ]/.test(password) && /\d/.test(password); const special = /[^A-Za-zÀ-ÿ0-9]/.test(password);
  const submit = () => { if (!name.trim()) return auth.setError('Digite seu nome completo.'); if (!emailLooksValid(email)) return auth.setError('Digite um e-mail válido.'); if (!longEnough || !letterAndNumber) return auth.setError('Crie uma senha com 8 caracteres, uma letra e um número.'); void auth.run(() => registerWithFirebase(email, password, name), email, name, true); };
  return <Screen><Header back={() => navigation.goBack()} title="Crie sua conta" subtitle={'É rápido e grátis. Configure seu\nbriefing em poucos passos.'} compact />
    <View style={[s.form, s.registerForm]}><Field icon="person" placeholder="Nome completo" value={name} onChangeText={text => { setName(text); auth.setError(''); }} autoComplete="name" testID="register-name" /><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); auth.setError(''); }} autoComplete="email" keyboardType="email-address" testID="register-email" /><Field icon="lock" placeholder="Senha" value={password} onChangeText={text => { setPassword(text); auth.setError(''); }} autoComplete="new-password" secure testID="register-password" />
      <View style={s.rules}><PasswordRule label="Pelo menos 8 caracteres" passed={longEnough} /><PasswordRule label="Uma letra e um número" passed={letterAndNumber} /><PasswordRule label="Use um caractere especial (opcional)" passed={special} optional /></View><ErrorMessage error={auth.error} /><MainButton title="Criar conta" busy={auth.busy} onPress={submit} />
      <SocialButtons busy={auth.busy} onGoogle={() => void auth.run(loginWithGoogle, '', '', true)} onApple={() => void auth.run(loginWithApple, '', '', true)} />
    </View><FooterLink prompt="Já tem uma conta?" action="Entrar agora" onPress={() => navigation.replace('Login')} />
  </Screen>;
}

export function ForgotPasswordScreen({ navigation }: AuthRoute<'ForgotPassword'>) {
  const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [sent, setSent] = useState(false); const { width, height } = useWindowDimensions();
  const submit = async () => { if (!emailLooksValid(email)) return setError('Digite um e-mail válido.'); setBusy(true); setError(''); try { await resetPasswordWithFirebase(email); setSent(true); } catch (cause) { setError(errorText(cause)); } finally { setBusy(false); } };
  return <Screen><Header back={() => navigation.goBack()} title="Esqueceu sua senha?" subtitle={'Digite seu e-mail para receber\nas instruções de redefinição.'} />
    <View style={s.forgotForm}><Field icon="mail" placeholder="E-mail" value={email} onChangeText={text => { setEmail(text); setSent(false); setError(''); }} autoComplete="email" keyboardType="email-address" testID="reset-email" /><ErrorMessage error={error} /><MainButton title={sent ? 'Reenviar instruções' : 'Enviar instruções'} busy={busy} onPress={() => void submit()} /></View>
    <View style={[s.forgotArt, { height: Math.min(width * .7, height * .28) }]}><View style={s.artHalo} /><Image source={envelopeMascot} resizeMode="contain" style={{ width: Math.min(width * .72, 310), height: Math.min(width * .72, 310) }} /></View>
    <View style={s.infoCard}><Icon name="info" size={28} color={colors.primary} /><Text style={s.infoText}>{sent ? 'Enviamos um link seguro para o seu e-mail. Confira também a pasta de spam.' : 'Enviaremos um link seguro para o seu e-mail.'}</Text></View>
  </Screen>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F8FBFF' }, topGlow: { position: 'absolute', top: -160, left: -75, width: 290, height: 340, borderRadius: 170, backgroundColor: '#EAF4FF', opacity: .55 },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingTop: 18 }, entryScroll: { justifyContent: 'space-between' },
  back: { width: 44, height: 44, justifyContent: 'center', alignItems: 'flex-start' }, logo: { alignSelf: 'center', width: 230, height: 74, marginTop: 5, marginBottom: 35 }, logoWide: { width: 240, height: 82, marginBottom: 2 }, logoCompact: { height: 64, marginBottom: 20 },
  title: { color: '#081D43', fontFamily: 'Inter', fontSize: 28, fontWeight: '700', textAlign: 'center', letterSpacing: -.9, lineHeight: 34 }, subtitle: { color: '#5E749A', fontFamily: 'Inter', fontSize: 16, lineHeight: 24, textAlign: 'center', marginTop: 11 },
  entryTop: { alignItems: 'center', paddingTop: 48 }, entryTitle: { color: '#081D43', fontFamily: 'Inter', fontSize: 31, lineHeight: 38, fontWeight: '700', textAlign: 'center', letterSpacing: -1 }, entrySubtitle: { color: '#5D7498', fontFamily: 'Inter', textAlign: 'center', fontSize: 16, lineHeight: 24, marginTop: 12 },
  entryArt: { justifyContent: 'center', alignItems: 'center', marginHorizontal: -24, overflow: 'hidden' }, artHalo: { position: 'absolute', width: '90%', aspectRatio: 1, borderRadius: 999, backgroundColor: '#E4F2FF', bottom: -145, alignSelf: 'center' }, entryMascot: { width: '100%', height: '105%' }, dots: { flexDirection: 'row', justifyContent: 'center', gap: 7, marginTop: 2, marginBottom: 8 }, dot: { width: 11, height: 6, borderRadius: 4, backgroundColor: '#CFDFF4' }, dotActive: { width: 16, height: 6, borderRadius: 4, backgroundColor: '#087CF0' }, entryActions: { gap: 9 }, retryCard: { backgroundColor: '#FFF0F2', borderRadius: 15, padding: 12, alignItems: 'center' }, retryText: { color: '#A73E50', fontFamily: 'Inter', fontSize: 13, lineHeight: 18, textAlign: 'center' }, retryAction: { color: '#0069FA', fontFamily: 'Inter', fontWeight: '700', marginTop: 6, fontSize: 14 },
  mainButton: { minHeight: 56, borderRadius: 28, backgroundColor: '#0868F7', justifyContent: 'center', alignItems: 'center', marginTop: 19, paddingHorizontal: 20 }, disabledButton: { opacity: .65 }, pressed: { opacity: .82 }, mainButtonText: { color: '#FFF', fontFamily: 'Inter', fontSize: 18, fontWeight: '600' }, buttonArrow: { position: 'absolute', right: 18 }, secondaryButton: { minHeight: 54, borderRadius: 27, backgroundColor: '#FFF', borderWidth: 1, borderColor: '#DCEAF8', alignItems: 'center', justifyContent: 'center' }, secondaryButtonText: { color: '#0B2149', fontFamily: 'Inter', fontSize: 17, fontWeight: '600' },
  form: { marginTop: 44 }, registerForm: { marginTop: 20 }, field: { height: 59, borderRadius: 23, borderWidth: 1, borderColor: '#D8E6F6', backgroundColor: '#F5F9FD', flexDirection: 'row', alignItems: 'center', gap: 18, paddingHorizontal: 20, marginBottom: 10 }, fieldInput: { flex: 1, fontFamily: 'Inter', fontSize: 16, color: '#0A2149', paddingVertical: 0 }, forgotLink: { alignSelf: 'flex-end', minHeight: 34, justifyContent: 'center', marginTop: 1 }, linkText: { color: '#0069FA', fontFamily: 'Inter', fontSize: 15, fontWeight: '600' }, error: { color: '#B43B48', fontFamily: 'Inter', fontSize: 13, lineHeight: 19, marginTop: 5, marginBottom: 2 },
  divider: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 18, marginBottom: 14 }, dividerLine: { flex: 1, height: 1, backgroundColor: '#D5E3F2' }, dividerText: { color: '#455C82', fontFamily: 'Inter', fontSize: 15 }, socialButton: { height: 50, backgroundColor: '#FFF', borderWidth: 1, borderColor: '#E2ECF7', borderRadius: 27, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 20, marginBottom: 6 }, socialText: { color: '#0A2047', fontFamily: 'Inter', fontSize: 15, fontWeight: '600' }, footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: 16, paddingBottom: 8 }, footerText: { color: '#617699', fontFamily: 'Inter', fontSize: 14 }, footerAction: { color: '#0067F5', fontFamily: 'Inter', fontSize: 14, fontWeight: '700' },
  rules: { marginTop: 2, marginBottom: -8 }, rule: { minHeight: 21, flexDirection: 'row', alignItems: 'center', gap: 9 }, ruleIcon: { width: 19, height: 19, borderRadius: 10, backgroundColor: '#EBF3FB', justifyContent: 'center', alignItems: 'center' }, ruleIconPassed: { backgroundColor: '#D9ECFF' }, ruleDot: { color: '#8CA0BE', fontSize: 13, lineHeight: 16 }, ruleText: { color: '#62799D', fontFamily: 'Inter', fontSize: 13 }, ruleTextPassed: { color: '#2E5B91' },
  forgotForm: { marginTop: 43 }, forgotArt: { marginTop: 28, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }, infoCard: { backgroundColor: '#EFF7FF', minHeight: 65, borderRadius: 20, paddingHorizontal: 17, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 13, marginTop: 2 }, infoText: { flex: 1, color: '#58729A', fontFamily: 'Inter', fontSize: 13, lineHeight: 19 },
});
