// A phone on USB reaches Metro (8081) and the local API (8090) through `localhost` only when adb
// forwards those ports. Runs before `npm start` / `npm run android`; without adb or a device it is a no-op.
const { execFileSync } = require('node:child_process');

const PORTS = [8081, 8090];

function adb(args) {
  return execFileSync('adb', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
}

let devices = [];
try {
  devices = adb(['devices']).split('\n').slice(1).map(line => line.split('\t')).filter(([, state]) => state?.trim() === 'device').map(([serial]) => serial);
} catch {
  process.exit(0);
}
for (const serial of devices) {
  for (const port of PORTS) {
    try { adb(['-s', serial, 'reverse', `tcp:${port}`, `tcp:${port}`]); } catch { /* emulator or device without reverse support */ }
  }
  console.log(`[adb] ${serial}: localhost:${PORTS.join(', ')} forwarded to this computer`);
}
