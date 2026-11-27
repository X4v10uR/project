import { expect, test, type Page } from '@playwright/test'

test.use({ locale: 'en-US' })

async function signUp(page: Page) {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`planning-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Planning-Test42!')
  await page.locator('[name=password2]').fill('Planning-Test42!')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(/dashboard\//)
}

test('quick add assigns the category of the actual service name', async ({ page }) => {
  await signUp(page)
  await page.goto('/subscriptions/quick-add/')
  await page.getByRole('button', { name: 'Netflix', exact: true }).click()
  await expect(page.getByText('Category: Streaming')).toBeVisible()
  await page.getByLabel('Service', { exact: true }).fill('Root Canal Dental Service')
  await expect(page.getByText('Category: Other')).toBeVisible()
  await page.getByLabel('Cost (USD)').fill('15')
  await page.getByLabel('Next payment').fill(new Date().toISOString().slice(0, 10))
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/subscriptions/'))
  await page.getByRole('button', { name: 'Add subscription', exact: true }).click()
  expect(await (await response).json()).toMatchObject({ service_name: 'Root Canal Dental Service', category: 'Other' })
})

test('calendar uses forecast bounds and long planning names stay in view', async ({ page }) => {
  await signUp(page)
  const calendar = await (await page.request.get('/api/subscriptions/calendar/')).json()
  const monthLabel = (date: string) => new Date(`${date.slice(0, 7)}-01T12:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  const nextMonth = new Date(`${calendar.start.slice(0, 7)}-01T12:00:00`)
  nextMonth.setMonth(nextMonth.getMonth() + 1)
  // Give the browser a different month without changing the backend’s billing window.
  const previousMonth = new Date(`${calendar.start.slice(0, 7)}-01T12:00:00`)
  previousMonth.setDate(0)
  await page.clock.setFixedTime(previousMonth)
  const name = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.repeat(4).slice(0, 100)
  await page.goto('/subscriptions/quick-add/')
  await page.getByLabel('Service', { exact: true }).fill(name)
  await page.getByLabel('Cost (USD)').fill('15')
  await page.getByLabel('Next payment').fill(calendar.start)
  await page.getByRole('button', { name: 'Add subscription', exact: true }).click()
  await expect(page).toHaveURL(/\/subscriptions\/$/)
  await page.goto('/planning/calendar/')
  await expect(page.getByRole('heading', { name: `Events in ${monthLabel(calendar.start)}` })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Previous month' })).toBeDisabled()
  await expect(page.getByRole('link', { name })).toBeVisible()
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 800 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  }
  await page.getByRole('button', { name: 'Next month' }).click()
  await expect(page.getByRole('heading', { name: `Events in ${nextMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}` })).toBeVisible()
  for (let index = 0; index < 12 && await page.getByRole('button', { name: 'Next month' }).isEnabled(); index++) {
    await page.getByRole('button', { name: 'Next month' }).click()
  }
  await expect(page.getByRole('heading', { name: `Events in ${monthLabel(calendar.end)}` })).toBeVisible()
  await page.goto('/planning/insights/')
  await expect(page.getByText(name, { exact: true })).toBeVisible()
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 800 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  }
})

test('mobile More restores its opener on dismissal and focuses content on navigation', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await signUp(page)
  await page.goto('/subscriptions/')
  await expect(page.getByRole('main')).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  const more = page.getByRole('button', { name: /^More/ })
  await more.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog', { name: 'Workspace tools' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(more).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await expect(more).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByRole('navigation', { name: 'More destinations' }).getByRole('link', { name: 'Planning' }).click()
  await expect(page).toHaveTitle('Spending insights | DUES')
  await expect(page.getByRole('main')).toBeFocused()
})

test('landing spending toggle contains the visible label in its accessible name', async ({ page }) => {
  await page.goto('/')
  const toggle = page.locator('.lp-period')
  await expect(toggle).toHaveAccessibleName('Monthly spending, switch to yearly')
  await toggle.click()
  await expect(toggle).toHaveAccessibleName('Yearly spending, switch to monthly')
})
