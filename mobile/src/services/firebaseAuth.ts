import { createUserWithEmailAndPassword, getAuth, GoogleAuthProvider, OAuthProvider, onAuthStateChanged, sendPasswordResetEmail, signInWithCredential, signInWithEmailAndPassword, signInWithPopup, signOut, updateProfile, type User as FirebaseUser } from '@react-native-firebase/auth';
import { GoogleSignin, isSuccessResponse } from '@react-native-google-signin/google-signin';
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

export async function loginWithGoogle() {
  if (!GOOGLE_WEB_CLIENT_ID) throw new Error('GOOGLE_SIGN_IN_NOT_CONFIGURED');
  authOperationInProgress = true;
  try {
    GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn();
    if (!isSuccessResponse(response)) throw new Error('AUTH_CANCELLED');
    const idToken = response.data.idToken;
    if (!idToken) throw new Error('GOOGLE_ID_TOKEN_MISSING');
    const credential = GoogleAuthProvider.credential(idToken);
    const result = await signInWithCredential(firebaseAuth, credential);
    await getFirebaseIdToken(true);
    return result.user;
  } finally { authOperationInProgress = false; }
}

export async function loginWithApple() {
  authOperationInProgress = true;
  try {
    const provider = new OAuthProvider('apple.com');
    provider.addScope('email');
    provider.addScope('name');
    // RNFirebase's OAuthProvider carries providerId at runtime, but its modular type marks it private.
    const result = await signInWithPopup(firebaseAuth, provider as unknown as Parameters<typeof signInWithPopup>[1]);
    await getFirebaseIdToken(true);
    return result.user;
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
    'auth/operation-not-allowed': 'Este método de acesso ainda não está habilitado no Firebase.',
    'auth/popup-closed-by-user': 'A autenticação foi cancelada.',
    'auth/web-context-cancelled': 'A autenticação foi cancelada.',
  };
  if (error instanceof Error && error.message === 'GOOGLE_SIGN_IN_NOT_CONFIGURED') return 'O acesso com Google precisa ser configurado neste build.';
  if (error instanceof Error && error.message === 'AUTH_CANCELLED') return 'A autenticação foi cancelada.';
  if (error instanceof Error && error.message === 'GOOGLE_ID_TOKEN_MISSING') return 'Não foi possível obter o token do Google. Confira a configuração do Firebase.';
  return messages[code] || 'Não foi possível concluir a operação. Tente novamente.';
}
