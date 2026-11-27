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

test('password checks update during typing, pasting, deletion, and password visibility changes', async ({ page }, testInfo) => {
  await page.route(url => url.protocol === 'https:', route => route.abort())
  await page.route('**/api/accounts/session/', route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify({ user: null }),
  }))
  await page.route('**/api/accounts/signup/', route => route.fulfill({
    status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'Please choose another email.' }),
  }))
  await page.setViewportSize({ width: 1366, height: 820 })
  await page.goto('/accounts/signup/')
  const password = page.getByLabel('Password', { exact: true })
  const meter = page.getByRole('meter', { name: 'Password strength' })
  const checks = page.getByRole('list', { name: 'Password checks' })
  await expect(meter).toHaveAttribute('aria-valuenow', '0')
  await expect(checks.locator('[data-met="true"]')).toHaveCount(0)

  await password.pressSequentially('a')
  await expect(meter.locator('.auth-strength-fill')).toHaveCSS('background-color', 'rgb(217, 45, 32)')
  await expect.poll(() => meter.locator('.auth-strength-fill').evaluate(element => element.getBoundingClientRect().width))
    .toBeGreaterThan(0)
  const initialProgress = Number(await meter.getAttribute('aria-valuenow'))
  expect(initialProgress).toBeGreaterThan(0)
  await expect(checks.locator('[data-met="true"]')).toHaveCount(0)
  await password.pressSequentially('b')
  expect(Number(await meter.getAttribute('aria-valuenow'))).toBeGreaterThan(initialProgress)
  await password.press('Backspace')
  await expect(meter).toHaveAttribute('aria-valuenow', String(initialProgress))
  await password.pressSequentially('bcdefgh')
  await expect(meter).toHaveAttribute('aria-valuenow', '1')
  await expect(checks.getByText('8+ characters')).toHaveAttribute('data-met', 'true')
  await password.pressSequentially('9')
  await expect(meter).toHaveAttribute('aria-valuenow', '2')
  await expect(checks.getByText('A number', { exact: false })).toHaveAttribute('data-met', 'true')
  await password.pressSequentially('!')
  await expect(meter).toHaveAttribute('aria-valuenow', '3')
  await expect(checks.locator('[data-met="true"]')).toHaveCount(3)
  await expect.poll(() => meter.locator('.auth-strength-fill').evaluate(element => element.getBoundingClientRect().width))
    .toBeCloseTo((await meter.boundingBox())!.width, 0)
  await page.getByRole('button', { name: 'Show password', exact: true }).first().click()
  await expect(password).toHaveValue('abcdefgh9!')
  await expect(meter).toHaveAttribute('aria-valuenow', '3')
  await page.screenshot({ path: testInfo.outputPath('signup-strength-desktop.png'), fullPage: true })

  await password.fill('abcdefghé ')
  await expect(meter).toHaveAttribute('aria-valuenow', '1')
  await expect(checks.locator('[data-met="true"]')).toHaveCount(1)
  await password.fill('1!')
  expect(Number(await meter.getAttribute('aria-valuenow'))).toBeGreaterThan(2)
  expect(Number(await meter.getAttribute('aria-valuenow'))).toBeLessThan(3)
  await expect(checks.getByText('8+ characters')).toHaveAttribute('data-met', 'false')
  await password.fill('')
  await expect(meter).toHaveAttribute('aria-valuenow', '0')
  await expect(checks.locator('[data-met="true"]')).toHaveCount(0)
  await expect(meter).toHaveAttribute('aria-valuetext', 'Not entered')
  await expect.poll(() => meter.locator('.auth-strength-fill').evaluate(element => element.getBoundingClientRect().width))
    .toBe(0)

  await password.fill('Browser-Example42!')
  await page.getByLabel('Email', { exact: true }).fill('strength@example.test')
  await page.getByLabel('Confirm password', { exact: true }).fill('Browser-Example42!')
  const request = page.waitForRequest('**/api/accounts/signup/')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ password1: 'Browser-Example42!', password2: 'Browser-Example42!' })
  await expect(page.getByRole('alert')).toContainText('Please choose another email.')
  await expect(meter).toHaveAttribute('aria-valuenow', '3')
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.screenshot({ path: testInfo.outputPath('signup-strength-mobile.png'), fullPage: true })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(meter.locator('.auth-strength-fill')).toHaveCSS('transition-duration', '0s')
})
