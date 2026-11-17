import { defineConfig } from '@playwright/test'

const host = '127.0.0.1'
const backend = `http://${host}:18183`
const frontend = `http://${host}:14183`
const python = process.env.E2E_PYTHON || 'python'

export default defineConfig({
  testDir: './tests/browser',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: frontend,
    browserName: 'chromium',
    viewport: { width: 390, height: 844 },
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `"${python}" tests/browser/server.py`,
      url: `${backend}/api/accounts/session/`,
      timeout: 90_000,
    },
    {
      command: 'npm run preview -- --port 14183',
      env: { BACKEND_URL: backend },
      url: frontend,
    },
  ],
})
