import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/scenarios': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/pipeline': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/drift': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/detection': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/analyst': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/system': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/reports': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          'maplibre-vendor': ['maplibre-gl'],
          'export-vendor': ['html2canvas', 'dompurify'],
          'ui-vendor': ['lucide-react'],
        },
      },
    },
  },
});
