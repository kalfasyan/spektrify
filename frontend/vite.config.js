import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The build goes straight into the Python package so `pip install` ships a ready UI and
// users never need Node. During development run the Python server (`spektrify view --demo`)
// and `npm run dev`: Vite proxies /api to it.
export default defineConfig({
  plugins: [svelte()],
  base: './',
  build: {
    outDir: '../src/spektrify/static',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    proxy: { '/api': 'http://localhost:8765' },
  },
});
