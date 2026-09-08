import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://alcaras.github.io',
  base: '/owreference/',
  build: { format: 'directory' },
  trailingSlash: 'ignore',
});
