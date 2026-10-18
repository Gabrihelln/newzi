import { Platform } from 'react-native';
import { AppleAuthProvider, createUserWithEmailAndPassword, EmailAuthProvider, getAuth, GoogleAuthProvider, onAuthStateChanged, reauthenticateWithCredential, revokeToken, sendPasswordResetEmail, signInWithCredential, signInWithEmailAndPassword, signOut, updatePassword, updateProfile, type User as FirebaseUser } from '@react-native-firebase/auth';
import { appleAuth } from '@invertase/react-native-apple-authentication';
import { GoogleSignin, isErrorWithCode, isSuccessResponse, statusCodes } from '@react-native-google-signin/google-signin';
import { devLog } from '../config/env';
import { GOOGLE_WEB_CLIENT_ID } from '../config/socialAuth';

export const firebaseAuth = getAuth();
let authOperationInProgress = false;
let tokenLogUid = '';

export function isAuthOperationInProgress() { return authOperationInProgress; }

export function observeFirebaseUser(listener: (user: FirebaseUser | null) => void) {
  return onAuthStateChanged(firebaseAuth, listener);
}

export async function registerWithFirebase(email: string, password: string, displayName: string) {
  authOperationInProgress = true;
  try {
    const credential = await createUserWithEmailAndPassword(firebaseAuth, email.trim().toLowerCase(), password);
    await updateProfile(credential.user, { displayName: displayName.trim() });
    // The token minted at sign-up has no name claim; a fresh one lets the backend save the name.
    await getFirebaseIdToken(true);
    return credential.user;
  } finally { authOperationInProgress = false; }
}

export async function loginWithFirebase(email: string, password: string) {
  authOperationInProgress = true;
  devLog('[Auth] login:start');
  try {
    const credential = await signInWithEmailAndPassword(firebaseAuth, email.trim().toLowerCase(), password);
    if (!firebaseAuth.currentUser?.uid || !credential.user.uid) throw new Error('Firebase user was not available after login');
    devLog('[Auth] firebase:success');
    await getFirebaseIdToken(true);
    return credential.user;
  } finally { authOperationInProgress = false; }
}

export async function resetPasswordWithFirebase(email: string) {
  await sendPasswordResetEmail(firebaseAuth, email.trim().toLowerCase());
}

/** Whether the signed-in account has an e-mail password (Google and Apple accounts do not). */
export function hasPasswordSignIn() {
  return Boolean(firebaseAuth.currentUser?.providerData.some(provider => provider.providerId === 'password'));
}

/**
 * Change the password from inside the app. The current password is checked first, so a phone left
 * unlocked is not enough to take over the account; Firebase then ends the account's other sessions.
 */
export async function changePasswordWithFirebase(currentPassword: string, newPassword: string) {
  const user = firebaseAuth.currentUser;
  if (!user?.email || !hasPasswordSignIn()) throw new Error('NO_PASSWORD_ACCOUNT');
  await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, currentPassword));
  await updatePassword(user, newPassword);
}

export async function loginWithGoogle() {
  if (!GOOGLE_WEB_CLIENT_ID) throw new Error('GOOGLE_SIGN_IN_NOT_CONFIGURED');
  authOperationInProgress = true;
  try {
    GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn().catch(error => {
      if (isErrorWithCode(error) && error.code === statusCodes.SIGN_IN_CANCELLED) throw new Error('AUTH_CANCELLED');
      if (isErrorWithCode(error) && error.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) throw new Error('GOOGLE_PLAY_SERVICES_MISSING');
      throw error;
    });
    if (!isSuccessResponse(response)) throw new Error('AUTH_CANCELLED');
    const idToken = response.data.idToken;
    if (!idToken) throw new Error('GOOGLE_ID_TOKEN_MISSING');
    const credential = GoogleAuthProvider.credential(idToken);
    const result = await signInWithCredential(firebaseAuth, credential);
    await getFirebaseIdToken(true);
    return result.user;
  } finally { authOperationInProgress = false; }
}

/** Sign in with Apple exists only on iPhone; Android offers Google alone. */
export const appleSignInAvailable = Platform.OS === 'ios' && appleAuth.isSupported;

/**
 * Native Sign in with Apple (iOS 13+). The library sends Apple a hashed nonce and returns the raw one, which
 * Firebase checks against the identity token. Apple shares the person's name only on the first sign-in.
 */
/**
 * Apple requires that deleting an account also revokes the app's Sign in with Apple access. Apple asks the
 * person to confirm with Face ID/passcode and returns a fresh authorization code for Firebase to revoke.
 */
export async function revokeAppleAccessIfLinked() {
  if (!appleSignInAvailable || !firebaseAuth.currentUser?.providerData.some(provider => provider.providerId === 'apple.com')) return;
  try {
    const response = await appleAuth.performRequest({ requestedOperation: appleAuth.Operation.REFRESH });
    if (!response.authorizationCode) throw new Error('APPLE_REVOKE_FAILED');
    await revokeToken(firebaseAuth, response.authorizationCode);
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && (error as { code?: string }).code === appleAuth.Error.CANCELED) throw new Error('AUTH_CANCELLED');
    throw error;
  }
}

export async function loginWithApple() {
  if (!appleSignInAvailable) throw new Error('APPLE_SIGN_IN_UNAVAILABLE');
  authOperationInProgress = true;
  try {
    const response = await appleAuth.performRequest({ requestedOperation: appleAuth.Operation.LOGIN, requestedScopes: [appleAuth.Scope.FULL_NAME, appleAuth.Scope.EMAIL] });
    if (!response.identityToken) throw new Error('APPLE_ID_TOKEN_MISSING');
    const result = await signInWithCredential(firebaseAuth, AppleAuthProvider.credential(response.identityToken, response.nonce));
    const name = [response.fullName?.givenName, response.fullName?.familyName].filter(Boolean).join(' ');
    if (name && !result.user.displayName) await updateProfile(result.user, { displayName: name });
    await getFirebaseIdToken(true);
    return result.user;
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && (error as { code?: string }).code === appleAuth.Error.CANCELED) throw new Error('AUTH_CANCELLED');
    throw error;
  } finally { authOperationInProgress = false; }
}

export async function getFirebaseIdToken(forceRefresh = false) {
  const user = firebaseAuth.currentUser;
  if (!user) return null;
  const token = await user.getIdToken(forceRefresh);
  if (!token) throw new Error('Firebase ID token was not available');
  if (tokenLogUid !== user.uid || forceRefresh) { devLog('[Auth] token:acquired'); tokenLogUid = user.uid; }
  return token;
}

export async function logoutFromFirebase() {
  await signOut(firebaseAuth);
  tokenLogUid = '';
}

export function friendlyFirebaseAuthError(error: unknown) {
  const code = typeof error === 'object' && error && 'code' in error ? String((error as { code?: string }).code) : '';
  const messages: Record<string, string> = {
    'auth/email-already-in-use': 'Este e-mail já está cadastrado.',
    'auth/invalid-email': 'Digite um e-mail válido.',
    'auth/weak-password': 'Escolha uma senha com pelo menos 8 caracteres.',
    'auth/wrong-password': 'E-mail ou senha inválidos.',
    'auth/invalid-credential': 'E-mail ou senha inválidos.',
    'auth/too-many-requests': 'Muitas tentativas. Tente novamente mais tarde.',
    'auth/network-request-failed': 'Sem conexão. Verifique sua internet e tente novamente.',
    'auth/user-not-found': 'Não encontramos uma conta com este e-mail.',
    'auth/user-disabled': 'Esta conta está desativada.',
    'auth/account-exists-with-different-credential': 'Este e-mail já usa outro método de acesso.',
    'auth/operation-not-allowed': 'Este método de acesso não está disponível no momento.',
    'auth/popup-closed-by-user': 'A autenticação foi cancelada.',
    'auth/web-context-cancelled': 'A autenticação foi cancelada.',
  };
  if (error instanceof Error && error.message === 'GOOGLE_SIGN_IN_NOT_CONFIGURED') return 'O acesso com Google não está disponível no momento.';
  if (error instanceof Error && error.message === 'AUTH_CANCELLED') return 'A autenticação foi cancelada.';
  if (error instanceof Error && error.message === 'GOOGLE_ID_TOKEN_MISSING') return 'Não foi possível entrar com o Google. Tente novamente.';
  if (error instanceof Error && error.message === 'GOOGLE_PLAY_SERVICES_MISSING') return 'Atualize o Google Play Services para entrar com o Google.';
  // DEVELOPER_ERROR: the app's signing key (SHA-1) or the Web client ID is not registered in Firebase.
  if (code === '10' || code === 'DEVELOPER_ERROR') return 'O acesso com Google não está disponível no momento.';
  if (error instanceof Error && (error.message === 'APPLE_SIGN_IN_UNAVAILABLE' || error.message === 'APPLE_ID_TOKEN_MISSING')) return 'Não foi possível entrar com a Apple neste aparelho.';
  return messages[code] || 'Não foi possível concluir a operação. Tente novamente.';
}
