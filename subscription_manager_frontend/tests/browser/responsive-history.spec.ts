import { expect, test, type Locator, type Page } from '@playwright/test'

async function signUp(page: Page) {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`reflow-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Responsive-Test42!')
  await page.locator('[name=password2]').fill('Responsive-Test42!')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(/dashboard\//)
}

async function addCharge(page: Page, name: string) {
  await page.goto('/subscriptions/quick-add/')
  await page.getByLabel('Service', { exact: true }).fill(name)
  await page.getByLabel('Cost (USD)').fill('15')
  await page.getByLabel('Next payment').fill(new Date().toISOString().slice(0, 10))
  await page.getByRole('button', { name: 'Add subscription', exact: true }).click()
  await expect(page).toHaveURL(/\/subscriptions\/$/)
}

async function expectNoPageOverflow(page: Page, controls: Locator[]) {
  const width = await page.evaluate(() => document.documentElement.clientWidth)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  for (const control of controls) {
    await expect(control).toBeVisible()
    const rect = await control.boundingBox()
    expect(rect!.x).toBeGreaterThanOrEqual(0)
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(width + 1)
  }
}

test('ordinary charge history keeps controls in view and confines phone scrolling to the table', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await signUp(page)
  await addCharge(page, 'Spotify')
  await page.goto('/dashboard/history/')
  await expect(page.getByRole('row', { name: /Spotify/ })).toBeVisible()
  const region = page.getByRole('region', { name: 'Charge history table' })
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 740 })
    await expectNoPageOverflow(page, [
      page.getByRole('link', { name: 'Export charge history' }),
      page.getByRole('button', { name: 'Apply filters' }),
    ])
    expect(await region.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true)
  }
  await region.focus()
  await expect(region).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => region.evaluate(node => node.scrollLeft)).toBeGreaterThan(0)
  await page.getByRole('combobox', { name: 'Payment status for Spotify' }).selectOption('paid')
  await expect(page.getByText(/Confirmed paid/)).toBeVisible()
  await expectNoPageOverflow(page, [page.getByRole('link', { name: 'Export charge history' })])
})

test('long saved subscription names reflow across the schedule, cards and history', async ({ page }) => {
  const name = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.repeat(4).slice(0, 100)
  await page.setViewportSize({ width: 320, height: 740 })
  await signUp(page)
  await addCharge(page, name)
  await expect(page.getByRole('heading', { name: `${name} payment schedule` })).toBeVisible()
  const controls = () => [
    page.getByRole('link', { name: 'Export CSV' }),
    page.getByRole('link', { name: 'Add subscription', exact: true }),
  ]
  await expectNoPageOverflow(page, controls())
  await page.reload()
  const card = page.getByRole('button', { name: new RegExp(name) })
  await expect(card).toBeVisible()
  for (const width of [320, 768, 1280]) {
    await page.setViewportSize({ width, height: 800 })
    await expectNoPageOverflow(page, controls())
  }
  await page.goto('/dashboard/history/')
  await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible()
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 800 })
    await expectNoPageOverflow(page, [page.getByRole('link', { name: 'Export charge history' })])
  }
})
