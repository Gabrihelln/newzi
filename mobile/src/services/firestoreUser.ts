import { doc, getDoc, getFirestore, serverTimestamp, setDoc } from '@react-native-firebase/firestore';
import type { User as FirebaseUser } from '@react-native-firebase/auth';
import type { Preferences } from '../types/api';

const firestore = getFirestore();

export async function ensureUserProfile(user: FirebaseUser) {
  const reference = doc(firestore, 'users', user.uid);
  const snapshot = await getDoc(reference);
  const base = { uid: user.uid, email: user.email || '', displayName: user.displayName || '', updatedAt: serverTimestamp() };
  if (!snapshot.exists()) {
    await setDoc(reference, { ...base, onboardingCompleted: false, createdAt: serverTimestamp(), preferences: {}, notifications: { dailyBriefingEnabled: true } });
  } else {
    await setDoc(reference, base, { merge: true });
  }
  return reference;
}

export async function saveUserPreferences(user: FirebaseUser, preferences: Preferences) {
  await setDoc(doc(firestore, 'users', user.uid), {
    uid: user.uid,
    email: user.email || '',
    displayName: user.displayName || '',
    preferences: { topics: preferences.topics, language: preferences.language, countryScope: preferences.country_scope, briefingSize: preferences.briefing_size, deliveryTime: preferences.briefing_time, timezone: preferences.timezone },
    onboardingCompleted: true,
    updatedAt: serverTimestamp(),
  }, { merge: true });
}

export async function saveUserProfile(user: FirebaseUser, displayName: string) {
  await setDoc(doc(firestore, 'users', user.uid), {
    uid: user.uid,
    email: user.email || '',
    displayName: displayName.trim(),
    updatedAt: serverTimestamp(),
  }, { merge: true });
}
