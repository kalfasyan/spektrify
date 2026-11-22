import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The build goes straight into the Python package so `pip install` ships a ready UI and
// users never need Node. During development run the Python server (`spektrify view --demo`)
// and `npm run dev`: Vite proxies /api to it.
//
// `--mode site` builds the online learn-mode demo instead (no server; see docs/site.md) into
// build/site, which scripts/build-site.sh then fills with the precomputed data.
export default defineConfig(({ mode }) => ({
  plugins: [svelte()],
  base: './',
  build: {
    outDir: mode === 'site' ? '../build/site' : '../src/spektrify/static',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    proxy: { '/api': 'http://localhost:8765' },
  },
}));
