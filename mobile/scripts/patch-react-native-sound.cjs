// react-native-sound 0.11.2 loads this React Native module with require(),
// while React Native 0.86 exports the resolver as its default property.
const fs = require('node:fs');
const path = require('node:path');

const file = path.join(__dirname, '..', 'node_modules', 'react-native-sound', 'sound.js');
const original = 'var resolveAssetSource = require("react-native/Libraries/Image/resolveAssetSource");';
const replacement = 'var assetSourceModule = require("react-native/Libraries/Image/resolveAssetSource");\n' +
  'var resolveAssetSource = assetSourceModule.default || assetSourceModule;';

const source = fs.readFileSync(file, 'utf8');
if (source.includes(replacement)) {
  process.exit(0);
}
if (!source.includes(original)) {
  throw new Error('react-native-sound resolver changed; review the local compatibility patch');
}
fs.writeFileSync(file, source.replace(original, replacement));
