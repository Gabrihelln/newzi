import { Alert } from 'react-native';
import { launchCamera, launchImageLibrary, type ImagePickerResponse } from 'react-native-image-picker';
import { updateProfile } from '@react-native-firebase/auth';
import { api } from '../api/client';
import { absolutePhotoUrl } from '../components/SettingsKit';
import { firebaseAuth, getFirebaseIdToken } from './firebaseAuth';

export type PickedPhoto = { uri: string; base64: string };

// Already small on the phone: the server shrinks it to 512 px anyway, and the upload stays well under its limit.
const OPTIONS = { mediaType: 'photo', maxWidth: 720, maxHeight: 720, quality: 0.8, includeBase64: true } as const;

function picked(response: ImagePickerResponse): PickedPhoto | null {
  if (response.didCancel) return null;
  if (response.errorCode) throw new Error(response.errorCode === 'camera_unavailable' ? 'Este aparelho não tem câmera disponível.'
    : response.errorCode === 'permission' ? 'Permita o acesso à câmera ou às fotos nos ajustes do celular.' : 'Não foi possível abrir a foto.');
  const asset = response.assets?.[0];
  return asset?.uri && asset.base64 ? { uri: asset.uri, base64: asset.base64 } : null;
}

/** Asks camera or gallery, then opens it. Resolves null when the person cancels. */
export function choosePhoto(): Promise<PickedPhoto | null> {
  return new Promise((resolve, reject) => {
    const run = (open: typeof launchCamera) => open(OPTIONS).then(response => resolve(picked(response))).catch(reject);
    Alert.alert('Trocar foto', 'Escolha de onde vem a nova foto.', [
      { text: 'Tirar foto', onPress: () => run(launchCamera) },
      { text: 'Escolher da galeria', onPress: () => run(launchImageLibrary) },
      { text: 'Cancelar', style: 'cancel', onPress: () => resolve(null) },
    ], { cancelable: true, onDismiss: () => resolve(null) });
  });
}

/** Uploads the photo and makes it the account's picture everywhere in the app (Firebase photoURL). */
export async function uploadProfilePhoto(photo: PickedPhoto) {
  const { photo_url } = await api.uploadAvatar(photo.base64);
  const url = absolutePhotoUrl(photo_url)!;
  if (firebaseAuth.currentUser) {
    await updateProfile(firebaseAuth.currentUser, { photoURL: url });
    await getFirebaseIdToken(true);
  }
  return url;
}
