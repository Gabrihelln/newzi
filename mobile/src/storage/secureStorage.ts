import * as Keychain from 'react-native-keychain';

/** Native secure storage boundary: Android Keystore and iOS Keychain. */
export const secureStorage = {
  async getItem(key: string): Promise<string | null> {
    const credentials = await Keychain.getGenericPassword({ service: key });
    return credentials ? credentials.password : null;
  },
  async setItem(key: string, value: string): Promise<void> {
    await Keychain.setGenericPassword('newzi', value, {
      service: key,
      accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  },
  async removeItem(key: string): Promise<void> {
    await Keychain.resetGenericPassword({ service: key });
  },
};
