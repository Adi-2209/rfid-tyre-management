import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/auth': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/health': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/tags': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/observations': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/readers': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/tyres': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
