import { defineConfig } from 'astro/config';
import proseDev from './scripts/prose-dev.mjs';

export default defineConfig({
  site: 'https://alcaras.github.io',
  base: '/owreference/',
  build: { format: 'directory' },
  trailingSlash: 'ignore',
  vite: { plugins: [proseDev()] },   // dev-only in-page prose editor (see scripts/prose-dev.mjs)
});
