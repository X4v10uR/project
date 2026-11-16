import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.BACKEND_URL || 'http://127.0.0.1:8000'
  const proxy = {
    '/api/': { target },
    '/media/': { target },
    '/accounts/password-reset/': { target },
    '/admin/': { target },
    '/static/admin/': { target },
    '/static/css/dist/': { target },
    '/static/dashboard/': { target },
    '/static/female_memoji/': { target },
    '/static/male_memoji/': { target },
    '/ws/': { target, ws: true },
  }

  return {
    plugins: [react(), tailwindcss()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  }
})
