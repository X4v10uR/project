import { expect, test, type Page } from '@playwright/test'

async function signup(page: Page) {
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`notifications-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Mango-River73!Quartz')
  await page.locator('[name=password2]').fill('Mango-River73!Quartz')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(/dashboard\//)
}

function notification(id: number) {
  return { id, title: `Renewal alert ${id}`, body: 'Upcoming renewal', is_read: false,
    link_url: '/planning/alerts/', created_at: '2026-11-23T12:00:00Z' }
}

test('notifications keep polling while the websocket is open', async ({ page }) => {
  await page.addInitScript(() => {
    window.WebSocket = class {
      onopen: (() => void) | null = null
      onmessage = null
      onclose = null
      constructor() { setTimeout(() => this.onopen?.(), 0) }
      close() {}
    } as unknown as typeof WebSocket
  })
  let items = [notification(1)]
  await page.route(/\/api\/dashboard\/notifications\/(?:\?.*)?$/, (route) => route.fulfill({ json: {
    notifications: items, unread_count: items.length, next: null, notifications_ws_enabled: true,
  } }))
  await signup(page)
  await page.goto('/dashboard/notifications/')
  await expect(page.locator('article')).toHaveCount(1)
  await page.clock.install()
  items = [notification(2), notification(1)]
  await page.clock.fastForward(16_000)
  await expect(page.locator('article')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Notifications, 2 unread', exact: true })).toBeVisible()
})

test('older notifications stay accessible after refresh and opening one marks it read', async ({ page }) => {
  const items = Array.from({ length: 55 }, (_, index) => notification(55 - index))
  await page.route(/\/api\/dashboard\/notifications\/(?:\?.*)?$/, (route) => {
    const second = new URL(route.request().url()).searchParams.get('page') === '2'
    return route.fulfill({ json: { notifications: second ? items.slice(50) : items.slice(0, 50),
      unread_count: items.filter((item) => !item.is_read).length,
      next: second ? null : 'http://backend.invalid/api/dashboard/notifications/?page=2', notifications_ws_enabled: false } })
  })
  await page.route('**/api/dashboard/notifications/1/read/', (route) => {
    items[54].is_read = true
    return route.fulfill({ json: { unread_count: 54 } })
  })
  await signup(page)
  await page.goto('/dashboard/notifications/')
  await expect(page.locator('article')).toHaveCount(50)
  await page.getByRole('button', { name: 'Load older notifications' }).click()
  await expect(page.locator('article')).toHaveCount(55)
  await page.clock.install()
  await page.clock.fastForward(16_000)
  await expect(page.locator('article')).toHaveCount(55)
  await page.locator('article').filter({ has: page.getByText('Renewal alert 1', { exact: true }) }).getByRole('link', { name: 'Open', exact: true }).click()
  await expect(page).toHaveURL(/planning\/alerts\//)
  await expect(page.getByRole('button', { name: 'Notifications, 54 unread', exact: true })).toBeVisible()
})

test('push can be disabled without browser push support', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true })
    delete (navigator as unknown as Record<string, unknown>).serviceWorker
    // Hide the API inherited from Navigator.prototype as well.
    delete (Object.getPrototypeOf(navigator) as Record<string, unknown>).serviceWorker
  })
  const preferences = { email_enabled: true, push_enabled: true, digest: 'off', quiet_start: null,
    quiet_end: null, vapid_public_key: '', push_configured: false, timezone: 'UTC' }
  let update: unknown
  await page.route('**/api/finance/notifications/preferences/', (route) => {
    if (route.request().method() === 'PUT') {
      update = route.request().postDataJSON()
      Object.assign(preferences, update)
    }
    return route.fulfill({ json: preferences })
  })
  await signup(page)
  await page.goto('/planning/alerts/')
  await page.getByRole('button', { name: 'Disable push notifications' }).click()
  await expect(page.getByRole('status')).toHaveText('Push notifications disabled.')
  expect(update).toEqual({ push_enabled: false })
})

test('blocked websocket construction falls back to a working notification page', async ({ page }) => {
  await page.addInitScript(() => {
    window.WebSocket = class {
      constructor() { throw new DOMException('Blocked by browser policy', 'SecurityError') }
    } as unknown as typeof WebSocket
  })
  await page.route(/\/api\/dashboard\/notifications\/(?:\?.*)?$/, (route) => route.fulfill({ json: {
    notifications: [notification(1)], unread_count: 1, next: null, notifications_ws_enabled: true,
  } }))
  await signup(page)
  await page.goto('/dashboard/notifications/')
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible()
  await expect(page.locator('article')).toHaveCount(1)
})
