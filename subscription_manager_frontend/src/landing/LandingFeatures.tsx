import { useState } from 'react'
import {
  Bell, CalendarDays, Check, ChevronDown, CreditCard, FileText,
  FolderArchive, History, Mail, ShieldCheck, UsersRound,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { ServiceIcon } from '../ServiceIcon'
import { LandingAvatar } from './LandingAvatar'
import './landing-features.css'

const featureGroups = [
  {
    name: 'Subscriptions & payment cards',
    summary: 'From a four-field setup to the full details of every plan.',
    path: '/subscriptions/',
    action: 'Manage subscriptions',
    items: [
      ['Add it your way', 'Quick add with common service presets, a full subscription editor, and CSV templates, previews, duplicate checks, imports, and exports.'],
      ['Keep every detail', 'Service, plan, category, currency, billing cycle, start date, status, account email, private provider credentials, and notes. Search, filter, and sort your subscription list.'],
      ['Match your billing', 'Flexible recurring cycles, including 28 days and six months. Track introductory rates, trial end dates, regular prices, and dated future price changes.'],
      ['Organize payment methods', 'Save card nicknames, brands, themes, and last four digits. Choose a primary card, view linked subscriptions and spending, and move plans between cards.'],
    ],
  },
  {
    name: 'Spending, forecasts & budgets',
    summary: 'Understand today’s commitment and plan for the year ahead.',
    path: '/planning/insights/',
    action: 'Explore spending insights',
    items: [
      ['See what’s coming', 'A 30-day charge outlook, recurring monthly commitments, category breakdowns, recorded payments, remaining scheduled charges, and a 12-month forecast.'],
      ['Understand changes', 'Compare months and see which services changed. Keep dated price history while preserving previously recorded charge amounts and participant shares.'],
      ['Set your limits', 'Dashboard spending limits and detailed budgets by currency, category, or team, with configurable warning and full-limit alerts. Keep personal and team spending in view.'],
      ['Plan across currencies', 'View original currency totals or estimated combined spending in a preferred base currency, with exchange-rate dates and sources. Adjust a tracked funding balance and reserve target.'],
    ],
  },
  {
    name: 'Renewals, calendars & notifications',
    summary: 'Choose how much notice you need and where to receive it.',
    path: '/planning/calendar/',
    action: 'Open the renewal calendar',
    items: [
      ['See every important date', 'Browse payments, trial endings, cancellation deadlines, and scheduled pauses and resumptions in the renewal calendar.'],
      ['Take dates with you', 'Download an .ics calendar or create a private, revocable calendar subscription URL that reflects your latest schedule.'],
      ['Choose your delivery', 'Set reminder offsets, use in-app alerts, choose individual emails or daily and weekly summaries, and enable browser push when configured and supported.'],
      ['Make room for quiet', 'Set quiet hours in your profile’s time zone, manage email preferences, mark notifications read, and snooze an unread reminder until tomorrow.'],
    ],
  },
  {
    name: 'Reviews, trials & cancellations',
    summary: 'Turn the next renewal into a considered decision.',
    path: '/planning/review/',
    action: 'Open the review inbox',
    items: [
      ['Find what needs a look', 'A review inbox surfaces duplicate plans, approaching trials and deadlines, long review gaps, low usage, and price changes.'],
      ['Check what you use', 'Record usage check-ins, mark selected plans reviewed, and preview potential monthly savings by currency before changing your tracking.'],
      ['Plan a pause', 'Schedule pause and resume dates while preserving the original billing cadence. Paused periods skip forecast charges.'],
      ['Follow cancellation through', 'Save a provider’s cancellation link, track requests and confirmations, add notes and an access-until date. Arrange the change with the provider, then update DUES.'],
    ],
  },
  {
    name: 'Teams, cost splits & settlements',
    summary: 'Give every shared subscription a clear owner and a clear split.',
    path: '/accounts/teams/',
    action: 'Explore team workspaces',
    items: [
      ['Bring your people', 'Create teams, invite members, manage invitations, and assign Owner, Member, Accountant, or Viewer roles with separate Member credential permissions.'],
      ['Agree before changing', 'Members submit subscription requests for owner review. Assign upcoming renewals and record a keep, change, or cancel decision for that billing date.'],
      ['Share costs fairly', 'Use equal or custom participant shares, link participants to team members, and keep the split recorded with each charge.'],
      ['Track who owes what', 'See settlement balances by participant, payer, team, and currency. Record partial repayments, dates and notes, or mark eligible historical shares reimbursed.'],
    ],
  },
  {
    name: 'Connected accounts & discovery',
    summary: 'Bring in payments, then review what they mean.',
    path: '/planning/connections/',
    action: 'Explore connections',
    items: [
      ['Start with a statement', 'Import a bank statement CSV, map columns and debit signs, choose a date format and account label, and review errors and duplicates before confirming.'],
      ['Connect a bank', 'Where Plaid is configured, connect a supported institution and sync outgoing transactions for recurring-payment discovery.'],
      ['Find email receipts', 'Where Gmail is configured, connect with read-only access to discover receipt and invoice messages and supported attachments.'],
      ['Keep the final say', 'Review editable subscription suggestions, confirm suggested payment matches, or manually match a payment to an eligible same-currency personal or team charge.'],
    ],
  },
  {
    name: 'History, receipts, reports & backups',
    summary: 'Keep a useful record of what was charged, paid, and changed.',
    path: '/planning/reports/',
    action: 'Explore charge reports',
    items: [
      ['Follow every charge', 'Track scheduled, paid, failed, and refunded charges with recorded participant shares. Retain charge history for removed subscriptions and review subscription activity.'],
      ['Keep receipts close', 'Attach private PDF, PNG, and JPEG receipts to subscriptions or charges. Filter by merchant and receipt date, download files, and review extracted details, with image OCR when configured.'],
      ['Export the view you need', 'Download CSV or PDF charge reports filtered by workspace, service, date, and payment status. Export subscription lists separately.'],
      ['Take your records with you', 'Download a finance archive with subscriptions, cards, owned teams, history, splits, repayments, prices, receipts, budgets, activity, and preferences. Preview counts before restoring copies.'],
    ],
  },
  {
    name: 'Account, privacy & security',
    summary: 'Control access to your account and the information inside it.',
    path: '/accounts/settings/',
    action: 'Open account settings',
    items: [
      ['Add sign-in protection', 'Enable authenticator MFA, save one-use recovery codes, reset or change your password, and review sensitive account activity.'],
      ['Protect provider details', 'Stored provider passwords are encrypted and require recent password verification to reveal. Revealed credentials hide after one minute, with access governed by team permissions.'],
      ['Make the account yours', 'Choose an avatar and background, edit your profile and email, set a time zone and preferred currency, and manage account deletion.'],
      ['Control your data', 'Private receipt access follows workspace membership. Backups require password verification, and calendar subscription URLs can be revoked. Restore archives before reconnecting live integrations.'],
    ],
  },
]

export function LandingFeatures({ signedIn }: { signedIn: boolean }) {
  const [scope, setScope] = useState<'personal' | 'team'>('personal')
  const scopeSpending = scope === 'personal' ? 52.47 : 91.99
  const scopeBudget = scope === 'personal' ? 75 : 120
  const destination = (path: string) => signedIn ? path : '/accounts/signup/'

  return <div className="lv-feature-tour" id="planning">
    <nav className="lv-feature-jumps lv-container" aria-label="Explore product features">
      <a href="#spending">Spending</a>
      <a href="#renewals">Renewals</a>
      <a href="#shared-plans">Shared plans</a>
      <a href="#discovery">Discovery</a>
      <a href="#records-security">Records &amp; security</a>
      <a href="#all-features">Every feature</a>
    </nav>

    <section className="lv-product-section lv-container" id="spending" aria-labelledby="lv-spending-title">
      <div className="lv-product-copy" data-lp-reveal="scroll">
        <span className="lv-eyebrow">SPENDING &amp; BUDGETS</span>
        <h2 id="lv-spending-title">Know where it goes.<br/>Decide what stays.</h2>
        <p>See the cost of your subscriptions today, next month, and a year from now. Give every category a budget that works for you.</p>
        <ul className="lv-feature-points">
          <li><Check/>Monthly commitments, category breakdowns, and 12-month forecasts</li>
          <li><Check/>Personal and team budgets with early warning alerts</li>
          <li><Check/>Payment cards, price history, and estimated currency conversions</li>
        </ul>
        <Link to={destination('/planning/insights/')} className="lv-text-link">Get to know your spending</Link>
      </div>
      <div className="lv-product-visual lv-spend-visual" data-lp-reveal="scroll">
        <div className="lv-example-panel">
          <div className="lv-example-heading"><span>Monthly commitment</span><CreditCard size={19} aria-hidden="true"/></div>
          <div className="lv-example-switch" role="group" aria-label="Spending example workspace">
            <button type="button" aria-pressed={scope === 'personal'} onClick={() => setScope('personal')}>Personal</button>
            <button type="button" aria-pressed={scope === 'team'} onClick={() => setScope('team')}>Team</button>
          </div>
          <div className="lv-example-total" aria-live="polite" aria-atomic="true"><strong>${scopeSpending.toFixed(2)}</strong><span>of ${scopeBudget} monthly budget</span></div>
          <div className="lv-budget-track" role="img" aria-label={`${Math.round(scopeSpending / scopeBudget * 100)} percent of example budget used`}><span style={{ width: `${scopeSpending / scopeBudget * 100}%` }}/></div>
          <div className="lv-example-services">
            {(scope === 'personal'
              ? [{ name: 'Netflix', category: 'Entertainment', amount: '15.49' }, { name: 'Spotify', category: 'Music', amount: '11.99' }, { name: 'Figma', category: 'Design', amount: '12.00' }]
              : [{ name: 'Figma', category: '3 people', amount: '45.00' }, { name: 'Notion', category: '3 people', amount: '30.00' }, { name: 'Spotify', category: '2 people', amount: '16.99' }]
            ).map(service => <div key={service.name}><ServiceIcon name={service.name}/><span><strong>{service.name}</strong><small>{service.category}</small></span><b>${service.amount}</b></div>)}
          </div>
          <small className="lv-example-caption">Illustrative example · USD</small>
        </div>
        <div className="lv-visual-note"><CalendarDays size={18} aria-hidden="true"/><span>A full year of renewals in view</span></div>
      </div>
    </section>

    <section className="lv-product-section lv-product-reverse lv-container" id="renewals" aria-labelledby="lv-renewals-title">
      <div className="lv-product-copy" data-lp-reveal="scroll">
        <span className="lv-eyebrow">REMINDERS &amp; REVIEWS</span>
        <h2 id="lv-renewals-title">Before it renews,<br/>make it a choice.</h2>
        <p>A trial ending. A price going up. A plan you barely use. DUES brings the next decision into view while there’s still time to act.</p>
        <ul className="lv-feature-points">
          <li><Check/>Custom reminders, email summaries, push, quiet hours, and snoozing</li>
          <li><Check/>Renewal calendars with .ics export and a private live feed</li>
          <li><Check/>Duplicate reviews, usage check-ins, and potential savings</li>
          <li><Check/>Track pauses, resumptions, and cancellation confirmations</li>
        </ul>
        <Link to={destination('/planning/review/')} className="lv-text-link">Give your plans a second look</Link>
      </div>
      <div className="lv-product-visual lv-renewal-visual" data-lp-reveal="scroll">
        <div className="lv-renewal-header"><span><CalendarDays size={20} aria-hidden="true"/>Your next decisions</span><small>Example schedule</small></div>
        <div className="lv-renewal-event"><span className="lv-event-date">28<small>NOV</small></span><div><strong>Trial ending soon</strong><p>Review the plan before the first bill.</p><span className="lv-event-tag">Trial reminder</span></div><Bell size={20} aria-hidden="true"/></div>
        <div className="lv-renewal-event"><span className="lv-event-date">01<small>DEC</small></span><div><strong>A new price starts</strong><p>See how the change affects your forecast.</p><span className="lv-event-tag">Price review</span></div><History size={20} aria-hidden="true"/></div>
        <div className="lv-renewal-event"><span className="lv-event-date">04<small>DEC</small></span><div><strong>Time for a plan check</strong><p>Keep it, pause it, or track a cancellation.</p><span className="lv-event-tag">Usage check-in</span></div><Check size={20} aria-hidden="true"/></div>
        <p className="lv-example-caption">Provider changes are arranged directly with the service.</p>
      </div>
    </section>

    <section className="lv-shared-section" id="shared-plans" aria-labelledby="lv-shared-title">
      <div className="lv-product-section lv-container">
        <div className="lv-product-copy" data-lp-reveal="scroll">
          <span className="lv-eyebrow">TEAMS &amp; SHARED COSTS</span>
          <h2 id="lv-shared-title">Share the plan.<br/>Know your part.</h2>
          <p>For a household, a side project, or your work team. Agree on the cost, give renewals an owner, and keep repayments easy to follow.</p>
          <ul className="lv-feature-points">
            <li><Check/>Invitations, team roles, and owner approval for requests</li>
            <li><Check/>Equal or custom splits with recorded participant shares</li>
            <li><Check/>Settlement balances and partial repayment records</li>
            <li><Check/>Renewal assignments with keep, change, or cancel decisions</li>
          </ul>
          <Link to={destination('/accounts/teams/')} className="lv-button lv-button-white">Bring your people together</Link>
        </div>
        <div className="lv-team-example" data-lp-reveal="scroll">
          <div className="lv-example-heading"><span><UsersRound size={20} aria-hidden="true"/>Design team</span><span>3 members</span></div>
          <div className="lv-team-plan"><ServiceIcon name="Figma"/><div><strong>Figma Professional</strong><span>$45.00 / month · Equal split</span></div><span className="lv-event-tag">Paid</span></div>
          <div className="lv-split-row"><LandingAvatar person="You" className="lv-person-avatar"/><div><strong>You</strong><small>Paid the provider</small></div><b>$15.00 share</b></div>
          <div className="lv-split-row"><LandingAvatar person="Alex" className="lv-person-avatar"/><div><strong>Alex</strong><small>Awaiting repayment</small></div><b>$15.00</b></div>
          <div className="lv-split-row"><LandingAvatar person="Morgan" className="lv-person-avatar"/><div><strong>Morgan</strong><small>$5.00 repaid</small></div><b>$10.00 left</b></div>
          <div className="lv-settlement-total"><span>Still owed to you</span><strong>$25.00</strong></div>
          <small className="lv-example-caption">Illustrative team and repayments · USD</small>
        </div>
      </div>
    </section>

    <section className="lv-discovery lv-container" id="discovery" aria-labelledby="lv-discovery-title">
      <div className="lv-section-heading" data-lp-reveal="scroll">
        <span className="lv-eyebrow">IMPORTS &amp; DISCOVERY</span>
        <h2 id="lv-discovery-title">A few ways in.<br/>One organized view.</h2>
        <p>Add the plans you know. Find the payments you missed.</p>
      </div>
      <div className="lv-discovery-grid">
        <article data-lp-reveal="scroll">
          <span className="lv-discovery-icon"><FileText aria-hidden="true"/></span>
          <h3>Your list, brought along.</h3>
          <p>Start with Quick add or import subscriptions from a CSV. Preview rows and duplicates before you confirm.</p>
          <Link to={destination('/subscriptions/import/')} className="lv-text-link">Explore subscription imports</Link>
        </article>
        <article data-lp-reveal="scroll">
          <span className="lv-discovery-icon"><CreditCard aria-hidden="true"/></span>
          <h3>Follow the payments.</h3>
          <p>Import a bank statement with column mapping, or connect through Plaid. Review recurring-payment suggestions and match charges.</p>
          <Link to={destination('/planning/connections/')} className="lv-text-link">Explore payment discovery</Link>
        </article>
        <article data-lp-reveal="scroll">
          <span className="lv-discovery-icon"><Mail aria-hidden="true"/></span>
          <h3>Put receipts to work.</h3>
          <p>Upload PDFs and images, or connect Gmail with read-only access to find invoices and receipt attachments.</p>
          <Link to={destination('/planning/receipts/')} className="lv-text-link">Explore receipts</Link>
        </article>
      </div>
      <p className="lv-integration-note">Bank and Gmail connections, image text extraction, and push delivery depend on deployment setup and provider or device support. You review discovered subscriptions and payment matches before confirming.</p>
    </section>

    <section className="lv-records lv-container" id="records-security" aria-labelledby="lv-records-title">
      <div className="lv-records-heading" data-lp-reveal="scroll">
        <span className="lv-eyebrow">RECORDS &amp; ACCOUNT CONTROL</span>
        <h2 id="lv-records-title">Every detail.<br/>Accounted for.</h2>
        <p>Keep the history, find the receipt, and choose who has access.</p>
      </div>
      <div className="lv-records-grid">
        <article data-lp-reveal="scroll"><History aria-hidden="true"/><h3>Know what happened.</h3><p>Track paid, failed, and refunded charges. Keep private receipts, review activity, and export filtered CSV or PDF reports.</p><Link className="lv-text-link" to={destination('/planning/reports/')}>Explore history &amp; reports</Link></article>
        <article data-lp-reveal="scroll"><ShieldCheck aria-hidden="true"/><h3>Choose who gets in.</h3><p>Authenticator MFA, recovery codes, verified credential reveals, and team permissions help protect your account and provider details.</p><Link className="lv-text-link" to={destination('/accounts/settings/')}>Explore account security</Link></article>
        <article data-lp-reveal="scroll"><FolderArchive aria-hidden="true"/><h3>Keep a copy. Keep control.</h3><p>Download your finance archive, preview a restore, and carry subscriptions, repayments, budgets, receipts, and history with you.</p><Link className="lv-text-link" to={destination('/planning/data/')}>Explore backup &amp; restore</Link></article>
      </div>
    </section>

    <section className="lv-feature-directory lv-container" id="all-features" aria-labelledby="lv-directory-title">
      <div className="lv-directory-intro" data-lp-reveal="scroll"><span className="lv-eyebrow">THE COMPLETE TOOLKIT</span><h2 id="lv-directory-title">Explore every feature.</h2><p>From adding your first plan to reconciling the last shared payment.</p><a href="#pricing" className="lv-text-link">See the free plan</a></div>
      <div className="lv-directory-groups">
        {featureGroups.map((group, index) => <details key={group.name} open={index === 0} data-lp-reveal="scroll">
          <summary><span><strong>{group.name}</strong><span>{group.summary}</span></span><ChevronDown size={20} aria-hidden="true"/></summary>
          <div className="lv-directory-content">
            <dl>{group.items.map(([title, description]) => <div key={title}><dt>{title}</dt><dd>{description}</dd></div>)}</dl>
            <Link className="lv-text-link" to={destination(group.path)}>{group.action}</Link>
          </div>
        </details>)}
      </div>
    </section>
  </div>
}
