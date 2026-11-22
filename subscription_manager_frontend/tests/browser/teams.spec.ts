import { expect, test, type Page } from '@playwright/test'

const password = 'Team-Browser42!'

async function signup(page: Page, email: string) {
  await page.goto('/accounts/signup/')
  await page.locator('[name=email]').fill(email)
  await page.locator('[name=password1]').fill(password)
  await page.locator('[name=password2]').fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(/dashboard\//)
}

async function createTeam(page: Page) {
  await signup(page, `team-owner-${crypto.randomUUID()}@example.test`)
  await page.goto('/accounts/teams/create/')
  await page.getByLabel('Team name').fill('Invitation test team')
  await page.getByRole('button', { name: 'Create team', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Invitation test team' })).toBeVisible()
}

async function sendInvite(page: Page, email: string) {
  const section = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Invite member', exact: true }) })
  await section.locator('[name=email]').fill(email)
  await section.getByRole('button', { name: 'Send invite', exact: true }).click()
  await expect(section.getByLabel('Invitation link')).toBeVisible()
  return section.getByLabel('Invitation link').inputValue()
}

test('an unregistered invitee creates an account and signs in again', async ({ page, browser }) => {
  await createTeam(page)
  const teamUrl = page.url()
  const email = `invitee-${crypto.randomUUID()}@example.test`
  const inviteUrl = await sendInvite(page, email)
  const context = await browser.newContext()
  const guest = await context.newPage()
  try {
    await guest.goto(inviteUrl)
    await expect(guest.getByRole('heading', { name: 'Accept invitation' })).toBeVisible()
    await guest.locator('[name=password1]').fill(password)
    await guest.locator('[name=password2]').fill('Wrong-Confirmation42!')
    await guest.getByRole('button', { name: 'Create account and join team' }).click()
    await expect(guest.getByRole('alert')).toContainText('match')
    await guest.locator('[name=password2]').fill(password)
    await guest.getByRole('button', { name: 'Create account and join team' }).click()
    await expect(guest.getByRole('heading', { name: 'Invitation test team' })).toBeVisible()
    await expect(guest.getByRole('heading', { name: 'Invite member' })).toHaveCount(0)
    await guest.getByRole('button', { name: 'Log out' }).click()
    await guest.locator('[name=email]').fill(email)
    await guest.locator('[name=password]').fill(password)
    await guest.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(guest).toHaveURL(teamUrl)
    await expect(guest.getByRole('heading', { name: 'Invitation test team' })).toBeVisible()
    await guest.goto(inviteUrl)
    await expect(guest.getByRole('heading', { name: 'Invite already used' })).toBeVisible()
    await page.reload()
    await expect(page.getByText('No pending invitations.', { exact: true })).toBeVisible()
  } finally {
    await context.close()
  }
})

test('owners resend and revoke links and existing users accept from notifications', async ({ page, browser, baseURL }) => {
  await createTeam(page)
  const context = await browser.newContext({ baseURL })
  const recipient = await context.newPage()
  const email = `registered-${crypto.randomUUID()}@example.test`
  try {
    await signup(recipient, email)
    const firstUrl = await sendInvite(page, email)
    await page.getByRole('button', { name: 'Resend invite', exact: true }).click()
    await expect(page.getByLabel('Invitation link')).toBeVisible()
    const secondUrl = await page.getByLabel('Invitation link').inputValue()
    expect(secondUrl).not.toBe(firstUrl)
    await recipient.goto(firstUrl)
    await expect(recipient.getByRole('heading', { name: 'Invite revoked' })).toBeVisible()
    await recipient.goto('/dashboard/notifications/')
    await recipient.locator('article').filter({ hasText: 'Invitation to join Invitation test team' }).first().getByRole('link', { name: 'Open', exact: true }).click()
    await expect(recipient.getByRole('heading', { name: 'Invitations to join' })).toBeVisible()
    await recipient.getByRole('button', { name: 'Accept invitation', exact: true }).click()
    await expect(recipient.getByRole('heading', { name: 'Invitation test team' })).toBeVisible()
    await page.reload()
    await expect(page.getByText('No pending invitations.', { exact: true })).toBeVisible()
    const revokeUrl = await sendInvite(page, `revoked-${crypto.randomUUID()}@example.test`)
    await page.getByRole('button', { name: 'Revoke invite', exact: true }).click()
    await expect(page.getByText('No pending invitations.', { exact: true })).toBeVisible()
    await recipient.goto(revokeUrl)
    await expect(recipient.getByRole('heading', { name: 'Invite revoked' })).toBeVisible()
  } finally {
    await context.close()
  }
})
