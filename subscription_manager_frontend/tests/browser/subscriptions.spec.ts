import { expect, test, type Page } from '@playwright/test'

async function signUp(page: Page) {
  const email = `browser-${crypto.randomUUID()}@example.test`
  await page.route((url) => url.protocol === 'https:', (route) => route.abort())
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(email)
  await page.locator('[name=password1]').fill('Browser-Example42!')
  await page.locator('[name=password2]').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Monthly recurring spend' })).toBeVisible()
  return email
}

test('create a card and team, open notifications, and sign back in', async ({ page }) => {
  const email = await signUp(page)
  await page.goto('/subscriptions/cards/add/')
  await page.getByLabel('Card nickname').fill('Work card')
  await page.getByLabel('Last four digits').fill('0123')
  await page.getByRole('button', { name: 'Save card' }).click()
  await expect(page.getByRole('heading', { name: 'Work card' })).toBeVisible()

  await page.goto('/accounts/teams/create/')
  await page.locator('input[name=name]').fill('Design team')
  await page.getByRole('button', { name: 'Create team', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Design team' })).toBeVisible()
  await page.goto('/dashboard/notifications/')
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/accounts\/login\//)
  await page.locator('[name=email]').fill(email)
  await page.locator('[name=password]').fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/dashboard\//)
})

test('preview an import, navigate history, and keep a charge after deletion', async ({ page }) => {
  const today = new Date().toISOString().slice(0, 10)
  await signUp(page)
  const nav = page.getByRole('navigation', { name: 'Application navigation' })
  await nav.getByRole('link', { name: 'Subscriptions' }).click()
  await page.getByRole('link', { name: 'Import CSV' }).click()
  const row = `Cloud,monthly,1250,PKR,${today}`
  await page.getByLabel('CSV file').setInputFiles({
    name: 'plans.csv', mimeType: 'text/csv',
    buffer: Buffer.from(`Service Name,Billing Cycle,Total Cost,Currency,Start Date\n${row}\n${row}`),
  })
  await page.getByRole('button', { name: 'Preview import' }).click()
  await expect(page.getByText('1 ready · 1 duplicates · 0 invalid')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm import' }).click()
  await expect(page.getByText('Imported 1. Skipped 1 duplicates.')).toBeVisible()

  await nav.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByText('PKR 1,250.00', { exact: true })).toBeVisible()
  await nav.getByRole('link', { name: 'Subscriptions' }).click()
  await page.getByRole('button', { name: /Cloud/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Cloud' })
  await expect(dialog).toBeVisible()
  await page.goBack()
  await expect(dialog).toHaveCount(0)
  await page.goForward()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Delete', exact: true }).click()
  await page.getByRole('button', { name: 'Delete subscription' }).click()
  await expect(page.getByRole('heading', { name: 'No subscriptions yet' })).toBeVisible()

  await nav.getByRole('link', { name: 'History' }).click()
  await page.getByLabel('Service', { exact: true }).fill('Cloud')
  await page.getByLabel('From', { exact: true }).fill(today)
  await page.getByLabel('Through', { exact: true }).fill(today)
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page.getByRole('row', { name: /Cloud/ })).toContainText('Scheduled renewal')
  await expect(page.getByText('PKR 1250.00', { exact: true })).toBeVisible()
})
