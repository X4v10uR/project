import { expect, test } from '@playwright/test'

test('the subscription list paginates and deep-links to a subscription off the current page', async ({ page }) => {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(`pagination-${crypto.randomUUID()}@example.test`)
  await page.locator('[name=password1]').fill('Browser-Example42!')
  await page.locator('[name=password2]').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Monthly Spending' })).toBeVisible()

  await page.goto('/subscriptions/import/')
  const rows = Array.from({ length: 25 }, (_, i) => `Page bill ${String(i).padStart(2, '0')},monthly,10,USD,2026-01-01`)
  await page.getByLabel('CSV file').setInputFiles({
    name: 'subscriptions.csv', mimeType: 'text/csv',
    buffer: Buffer.from(['Service Name,Billing Cycle,Total Cost,Currency,Start Date', ...rows].join('\n')),
  })
  await page.getByRole('button', { name: 'Preview import' }).click()
  await page.getByRole('button', { name: 'Confirm import' }).click()
  await expect(page.getByRole('heading', { name: 'Subscriptions', exact: true })).toBeVisible()

  await page.getByLabel('Search subscriptions').fill('Page bill')
  await page.getByLabel('Sort by').selectOption('service_name')
  await page.getByRole('button', { name: 'Apply' }).click()
  const pages = page.getByRole('navigation', { name: 'Subscription pages' })
  await expect(pages).toContainText('Showing 1–24 of 25 subscriptions')
  await expect(page.getByRole('button', { name: /Page bill 24/ })).toHaveCount(0)

  await pages.getByRole('button', { name: 'Next' }).click()
  await expect(pages).toContainText('Showing 25–25 of 25 subscriptions')
  const exportLink = page.getByRole('link', { name: 'Export CSV' })
  await expect(exportLink).toHaveAttribute('href', '/api/subscriptions/export/csv/?q=Page+bill&sort=service_name')
  await page.getByRole('button', { name: /Page bill 24/ }).click()
  const drawer = page.getByRole('dialog', { name: 'Page bill 24' })
  await expect(drawer.getByRole('heading', { name: 'Payment history' })).toBeVisible()

  const deepLink = new URL(page.url())
  deepLink.searchParams.delete('page')
  await page.goto(deepLink.toString())
  await expect(drawer.getByRole('heading', { name: 'Payment history' })).toBeVisible()
  await drawer.getByRole('button', { name: 'Close dialog' }).click()
  await expect(pages).toContainText('Showing 1–24 of 25 subscriptions')
  await expect(page.getByRole('button', { name: /Page bill 24/ })).toHaveCount(0)
})
