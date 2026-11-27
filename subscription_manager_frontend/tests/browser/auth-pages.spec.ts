import { expect, test } from '@playwright/test'

test('account forms preserve the destination and recover from signup and login errors', async ({ page }) => {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  const next = '/subscriptions/?scope=personal'
  await page.goto('/accounts/login/?' + new URLSearchParams({ next }))
  await page.getByRole('link', { name: 'Sign up', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/accounts/signup/\\?next='))

  const email = `auth-${crypto.randomUUID()}@example.test`
  const password = 'Browser-Example42!'
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Show password', exact: true }).first().click()
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text')
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue(password)
  await page.getByRole('button', { name: 'Hide password', exact: true }).click()
  await page.getByLabel('Confirm password', { exact: true }).fill('Different-Example42!')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('match')
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email)
  await page.getByLabel('Confirm password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/subscriptions/\\?scope=personal$'))
  await expect(page.getByRole('heading', { name: 'Subscriptions', exact: true })).toBeVisible()

  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrftoken')!
  expect((await page.request.post('/api/accounts/logout/', { headers: { 'X-CSRFToken': csrf.value } })).ok()).toBe(true)
  await page.goto('/accounts/login/?' + new URLSearchParams({ next }))
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill('Incorrect-Password42!')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Remember for 30 days').check()
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/subscriptions/\\?scope=personal$'))
  await expect(page.getByRole('heading', { name: 'Subscriptions', exact: true })).toBeVisible()
})

test('login handles factor errors and both account pages fit narrow and wide screens', async ({ page }, testInfo) => {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.route('**/api/accounts/session/', route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify({ user: null }),
  }))
  await page.goto('/accounts/login/')
  await page.route('**/api/accounts/login/', route => route.fulfill({
    status: 403, contentType: 'application/json',
    body: JSON.stringify({ detail: 'Enter a fresh authenticator code or an unused recovery code.' }),
  }))
  await page.getByLabel('Email', { exact: true }).fill('factor@example.test')
  await page.getByLabel('Password', { exact: true }).fill('Browser-Example42!')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByLabel('Authenticator or recovery code', { exact: true })).toBeVisible()
  await page.getByLabel('Authenticator or recovery code', { exact: true }).fill('123456')
  await page.getByLabel('Remember for 30 days').check()
  const request = page.waitForRequest('**/api/accounts/login/')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ otp: '123456', remember: true })

  for (const width of [320, 390, 1366]) {
    await page.setViewportSize({ width, height: width === 1366 ? 635 : 844 })
    for (const path of ['/accounts/login/', '/accounts/signup/']) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const story = page.getByRole('complementary', { name: 'A little inspiration' })
      if (width > 900) {
        await expect(story).toBeVisible()
        await page.getByRole('button', { name: 'Next story', exact: true }).click()
        await expect(story).toContainText('More clarity. Fewer surprises.')
        await page.getByRole('button', { name: 'Previous story', exact: true }).click()
        await expect(story).toContainText('Lulu Meyers')
      } else {
        await expect(story).toBeHidden()
      }
      if (width === 390 || width === 1366) {
        const pageName = path.includes('signup') ? 'signup' : 'login'
        await page.screenshot({ path: testInfo.outputPath(`${pageName}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true })
      }
    }
  }
})
