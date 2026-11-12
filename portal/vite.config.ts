import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { parseEnv } from 'node:util'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type ResolvedConfig } from 'vite'

const __dirname = import.meta.dirname
const envContent = readFileSync(path.join(__dirname, '../.env.dev'), 'utf8')
const parsedEnv = parseEnv(envContent)

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react({ compiler: { reportDiagnostics: true } }), compressHTML()],
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
            proxyRes.headers['set-cookie'] = cookies.map(cookie => cookie.replace(/;\s*Domain=[^;]+/i, ''))
          })
        },
      },
    },
  },
  resolve: { alias: { '@': '/src' }, dedupe: ['react', 'react-dom'] },
  define: { __UNIFICATION_MCP_SERVER_URL__: parsedEnv['UNIFICATION_MCP_SERVER_URL'] },
})

function compressHTML() {
  let viteConfig: ResolvedConfig
  return {
    name: 'vite-plugin-compress-html',
    configResolved(cfg: typeof viteConfig) {
      viteConfig = cfg
    },
    closeBundle() {
      spawn('bunx', ['html-minifier-next', '--input-dir=.', '--output-dir=.', '--preset=comprehensive'], {
        shell: false,
        env: { ...process.env },
        stdio: 'inherit',
        cwd: viteConfig.build.outDir,
      })
    },
  }
}
