import { AppRegistry } from 'react-native';
import { getMessaging, setBackgroundMessageHandler } from '@react-native-firebase/messaging';
import App from './App';

// Pushes carry a system notification, which Android and iOS show on their own while the app is in the
// background or closed; the handler only has to exist so Firebase does not drop or warn about them.
setBackgroundMessageHandler(getMessaging(), async () => undefined);

AppRegistry.registerComponent('Newzi', () => App);
