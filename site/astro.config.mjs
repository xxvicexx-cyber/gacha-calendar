import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  site: 'https://gacha-calendar.pages.dev',
  build: {
    assets: '_assets',
  },
});
