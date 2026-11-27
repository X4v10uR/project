import { expect, test, type Page } from '@playwright/test'

async function fillQuickAdd(page: Page, day: string) {
  await page.getByLabel('Service', { exact: true }).fill('Lost response example')
  await page.getByLabel('Cost (USD)').fill('30')
  await page.getByLabel('Next payment').fill(day)
}

test('refreshing after a lost create response and retrying records one charge', async ({ page }) => {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`retry-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Browser-Example42!')
  await page.locator('[name=password2]').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Monthly Spending' })).toBeVisible()
  await page.goto('/subscriptions/quick-add/')
  const day = new Date().toISOString().slice(0, 10)
  await fillQuickAdd(page, day)
  const keys: string[] = []
  const replayHeaders: string[] = []
  await page.route('**/api/subscriptions/', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    keys.push(route.request().headers()['idempotency-key'])
    const response = await route.fetch({ maxRetries: 0 })
    expect(response.status()).toBe(201)
    if (keys.length === 1) return route.abort('failed')
    replayHeaders.push(response.headers()['idempotency-replayed'])
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: 'Add subscription' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await page.reload()
  await fillQuickAdd(page, day)
  await page.getByRole('button', { name: 'Add subscription' }).click()
  await expect(page).toHaveURL(/\/subscriptions\/$/)
  expect(keys).toHaveLength(2)
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/)
  expect(keys[1]).toBe(keys[0])
  expect(replayHeaders).toEqual(['true'])
  const plans = await (await page.request.get('/api/subscriptions/')).json()
  const history = await (await page.request.get('/api/dashboard/history/')).json()
  expect(plans.subscriptions).toHaveLength(1)
  expect(history.count).toBe(1)
})
