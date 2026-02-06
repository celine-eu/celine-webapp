import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://172.17.0.1:8014',
        changeOrigin: true,
        secure: false
      }
    }

  }
});
