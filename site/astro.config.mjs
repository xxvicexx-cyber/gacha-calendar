import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  output: 'static',
  site: 'https://gacha-calendar-20p.pages.dev',
  build: {
    assets: '_assets',
  },
  integrations: [sitemap()],
});
