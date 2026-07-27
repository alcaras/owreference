import { defineConfig } from 'astro/config';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

// Automatically start Node-based state server in dev mode cross-platform (Mac & Windows)
const isDev = process.argv.some(arg => arg === 'dev' || arg === 'start') || process.env.NODE_ENV === 'development';

if (isDev) {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const scriptPath = resolve(__dirname, 'scripts/state_server.cjs');
  const nodePath = process.execPath; // Use the exact same Node binary running Astro
  
  console.log(`[Astro Config] Starting cross-platform state server: ${scriptPath}`);
  
  const serverProcess = spawn(nodePath, [scriptPath], {
    stdio: 'inherit',
    detached: false
  });
  
  serverProcess.on('error', (err) => {
    console.error('[Astro Config] Failed to start state server:', err.message);
  });
}

export default defineConfig({
  site: 'https://alcaras.github.io',
  base: '/owreference/',
  build: { format: 'directory' },
  trailingSlash: 'ignore',
});
