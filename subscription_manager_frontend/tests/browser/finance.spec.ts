import { expect, test, type Page } from '@playwright/test'

async function signup(page: Page) {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`finance-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Browser-Example42!')
  await page.locator('[name=password2]').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Monthly recurring spend' })).toBeVisible()
}

async function addSubscription(page: Page) {
  await page.goto('/subscriptions/quick-add/')
  await page.getByLabel('Service', { exact: true }).fill('Studio')
  await page.getByLabel('Cost (USD)', { exact: true }).fill('30')
  await page.getByLabel('Next payment').fill(new Date().toISOString().slice(0, 10))
  await page.getByRole('button', { name: 'Add subscription', exact: true }).click()
  await expect(page.getByRole('button', { name: /Studio/ })).toBeVisible()
}

async function verify(page: Page) {
  await page.getByText('Verify password for sensitive actions', { exact: true }).click()
  await page.getByLabel('Current Subly password').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Verify password', exact: true }).click()
  await expect(page.getByText('Verified for five minutes.')).toBeVisible()
}

test('detailed budgets and combined currency totals work on mobile', async ({ page }) => {
  await signup(page)
  await addSubscription(page)
  await page.goto('/planning/insights/')
  await expect(page.getByRole('heading', { name: 'Combined monthly spending' })).toBeVisible()
  await expect(page.getByText('USD 30.00', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Budgets', exact: true }).click()
  await page.getByLabel('Monthly limit', { exact: true }).fill('35')
  await page.getByLabel('Warn at (%)').fill('80')
  await page.getByRole('button', { name: 'Save detailed budget' }).click()
  await expect(page.getByText(/85.7%/)).toBeVisible()
  await page.reload()
  await expect(page.getByText(/85.7%/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/finance-budgets-mobile.png', fullPage: true })
})

test('receipt uploads stay attached to charge history and reports download', async ({ page }) => {
  await signup(page)
  await addSubscription(page)
  await page.goto('/dashboard/history/')
  await page.getByRole('link', { name: 'Receipts', exact: true }).click()
  await page.getByLabel('Receipt file').setInputFiles({
    name: 'studio.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==', 'base64'),
  })
  await page.getByRole('button', { name: 'Upload receipt' }).click()
  await expect(page.getByRole('heading', { name: 'studio.png' })).toBeVisible()
  await page.getByLabel('Merchant', { exact: true }).fill('Studio')
  await page.getByLabel('Receipt amount').fill('30')
  await page.getByLabel('Receipt currency').fill('USD')
  await page.getByRole('button', { name: 'Save receipt details' }).click()
  await expect(page.getByLabel('Receipt amount')).toHaveValue('30.00')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'studio.png' })).toBeVisible()
  await page.getByLabel('Filter by merchant').fill('Elsewhere')
  await page.getByRole('button', { name: 'Apply receipt filters' }).click()
  await expect(page.getByText('No receipts in this selection.')).toBeVisible()
  await page.getByLabel('Filter by merchant').fill('Studio')
  await page.getByRole('button', { name: 'Apply receipt filters' }).click()
  await expect(page.getByRole('heading', { name: 'studio.png' })).toBeVisible()
  await page.getByRole('link', { name: 'Reports', exact: true }).click()
  const csv = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download CSV report' }).click()
  expect((await csv).suggestedFilename()).toBe('subly-charge-history.csv')
  const pdf = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download PDF report' }).click()
  expect((await pdf).suggestedFilename()).toBe('subly-charge-history.pdf')
})

test('the dashboard opens the failed charge and clears it after confirmation', async ({ page }) => {
  await signup(page)
  await addSubscription(page)
  await page.goto('/dashboard/history/')
  await page.getByLabel('Payment status for Studio').selectOption('failed')
  await expect(page.getByLabel('Payment status for Studio')).toHaveValue('failed')
  await page.goto('/dashboard/')
  const attention = page.getByRole('region', { name: 'Needs attention' })
  await expect(attention).toContainText('Failed payment')
  await attention.getByRole('link', { name: 'Review charge' }).click()
  await expect(page).toHaveURL(/charge=\d+/)
  await page.getByLabel('Payment status for Studio').selectOption('paid')
  await expect(page.getByText(/Confirmed paid/)).toBeVisible()
  await page.goto('/dashboard/')
  await expect(attention).toContainText('Nothing needs your attention')
})

test('older activity appends to the first page', async ({ page }) => {
  await signup(page)
  await page.route('**/api/finance/activity/**', async route => {
    const older = new URL(route.request().url()).searchParams.has('before_id')
    await route.fulfill({ json: {
      next: older ? null : '/api/finance/activity/?before_id=2',
      activity: [{ id: older ? 1 : 2, service: older ? 'Older record' : 'New record', action: 'reviewed',
        changes: {}, actor: 'Test user', created_at: '2026-03-01T12:00:00Z' }],
    } })
  })
  await page.goto('/planning/activity/')
  await page.getByRole('button', { name: 'Load older activity' }).click()
  await expect(page.getByRole('heading', { name: 'Older record · reviewed' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'New record · reviewed' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Load older activity' })).toHaveCount(0)
})

test('calendar subscriptions can be created and revoked', async ({ page }) => {
  await signup(page)
  await addSubscription(page)
  await page.goto('/planning/calendar/')
  await page.getByRole('button', { name: 'Create private calendar URL' }).click()
  const field = page.getByLabel('New calendar subscription URL')
  await expect(field).toBeVisible()
  const url = await field.inputValue()
  const path = new URL(url).pathname
  expect((await page.request.get(path)).status()).toBe(200)
  expect(await (await page.request.get(path)).text()).toContain('Studio')
  await page.getByRole('button', { name: 'Revoke', exact: true }).click()
  await expect(page.getByLabel('New calendar subscription URL')).toHaveCount(0)
  expect((await page.request.get(path)).status()).toBe(404)
})

test('backup can be previewed and restored without losing history', async ({ page }) => {
  await signup(page)
  await addSubscription(page)
  await page.goto('/planning/data/')
  await verify(page)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download backup ZIP' }).click()
  const file = await (await download).path()
  expect(file).toBeTruthy()
  await page.getByLabel('Subly backup ZIP').setInputFiles(file!)
  await page.getByRole('button', { name: 'Preview backup' }).click()
  await expect(page.getByText(/Restore adds new copies/)).toBeVisible()
  await page.getByRole('checkbox', { name: /I understand this adds new copies/ }).check()
  await page.getByRole('button', { name: 'Restore as new copies' }).click()
  await expect(page.getByText('Restored 1 subscriptions, 1 charges, and 0 receipts.')).toBeVisible()
  await page.goto('/dashboard/history/')
  await expect(page.getByRole('row', { name: /Studio/ })).toHaveCount(2)
})

test('notification preferences persist and connections explain setup', async ({ page }) => {
  await signup(page)
  await page.goto('/planning/alerts/')
  await page.getByLabel('Email delivery').selectOption('daily')
  await page.getByLabel('Quiet hours start').fill('22:00')
  await page.getByLabel('Quiet hours end').fill('08:00')
  await page.getByRole('button', { name: 'Save notification preferences' }).click()
  await expect(page.getByText('Notification preferences saved.')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Email delivery')).toHaveValue('daily')
  await expect(page.getByLabel('Quiet hours start')).toHaveValue('22:00')
  await page.getByRole('link', { name: 'Connections', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Connected accounts & discovery' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Subscription suggestions' })).toBeVisible()
  await expect(page.getByText('No recurring patterns found yet.', { exact: false })).toBeVisible()
})
