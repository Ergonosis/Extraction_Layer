import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react({ compiler: true })],
  server: {
    // 5173 is commonly used by other local apps; portal owns 5175.
    port: 5175,
    strictPort: true,
    proxy: {
      // Forward portal /api/* calls to the Flask API during local development
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        // Keep Set-Cookie on the Vite origin so SSO sessions work in the SPA.
        configure: proxy => {
          proxy.on('proxyRes', proxyRes => {
            const cookies = proxyRes.headers['set-cookie']
            if (!cookies) return
            proxyRes.headers['set-cookie'] = cookies.map(cookie =>
              cookie.replace(/;\s*Domain=[^;]+/i, ''),
            )
          })
        },
      },
    },
  },
  resolve: { alias: { '@': '/src' }, dedupe: ['react', 'react-dom'] },
})
