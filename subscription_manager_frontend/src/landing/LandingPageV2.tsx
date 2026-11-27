import { useEffect, useRef, useState } from 'react'
import {
  CalendarDays, Check, Files, LayoutGrid, Menu, Plus, ShieldCheck, UsersRound, X, Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../accounts/auth'
import { ServiceIcon } from '../ServiceIcon'
import { LandingFooter } from './LandingPage'
import { LandingFeatures } from './LandingFeatures'
import { ProductDemo } from './ProductDemo'
import { LandingAvatar } from './LandingAvatar'
import { useLandingMotion } from './useLandingMotion'
import { useSmoothPageScroll } from './useSmoothPageScroll'
import './landing-v2.css'

const asset = `${import.meta.env.BASE_URL}landing-v2/campaign.webp`
const heroImage = `${import.meta.env.BASE_URL}landing-v2/hero-hand.webp`
const teamPortrait = `${import.meta.env.BASE_URL}landing-v2/team-portrait.webp`

// The campaign sheet contains two square photos. This viewport isolates the
// lifestyle photo before cropping it, so the phone panel never bleeds into it.
function LifestylePhoto({ className, alt }: { className: string; alt?: string }) {
  return <svg className={className} viewBox="100 0 100 100" preserveAspectRatio="xMidYMid slice" role={alt ? 'img' : undefined} aria-label={alt} aria-hidden={!alt}><image href={asset} width="200" height="100"/></svg>
}
function Brand() {
  return <a className="lv-brand" href="#top" aria-label="DUES home"><span><Zap size={18} fill="currentColor"/></span>DUES<b>.</b></a>
}

const headlineServices = ['iCloud','Netflix', 'Spotify', 'YouTube', 'hulu', 'HBO Max', 'Dropbox', 'Paramount+', 'AppleTV+', 'Prime Video', 'adobe-creative-cloud' ,'AWS', 'Google One', 'cloudflare']

function RotatingServiceLogo() {
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveIndex(index => (index + 1) % headlineServices.length)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  return <span className="lv-title-logo" aria-hidden="true">
    {headlineServices.map((name, index) =>
      <ServiceIcon key={name} name={name} className={index === activeIndex ? 'is-current' : ''}/>
    )}
  </span>
}

function Bars({ small = false }: { small?: boolean }) {
  const heights = small
    ? [12, 26, 15, 32, 21, 44, 31, 16, 48, 64, 39, 77, 51, 34, 65, 43, 24, 40, 57, 29, 16, 21]
    : [42, 65, 56, 90, 76, 68]
  return <div className={`lv-bars${small ? ' lv-bars-small' : ''}`} role="img" aria-label="Illustrative spending chart">
    {heights.map((height, index) => <div key={index}><i style={{ height: `${height}%` }}/>{!small && <span>{['Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'][index]}</span>}</div>)}
  </div>
}

function SpendingCard() {
  return <div className="lv-spending-card" data-lp-reveal>
    <span>Monthly spending</span>
    <LayoutGrid size={15} aria-hidden="true"/>
    <div><strong>$52.47</strong><small>5 subscriptions · Example USD</small></div>
    <Bars small/>
  </div>
}

function Payment({ name, amount, className }: { name: string; amount: string; className: string }) {
  return <div className={`lv-payment ${className}`} data-lp-reveal><ServiceIcon name={name}/><div><strong>{name}</strong><span>Subscription</span></div><b>{amount}<small>/mo</small></b></div>
}

const featureSlides = [
  {
    kind: 'spending', label: 'Spending', icon: LayoutGrid, anchor: '#spending', action: 'Explore spending',
    title: 'See where your money goes.',
    body: 'Bring your plans into one view. Set a budget and see how much you’re committed to spending.',
    metric: '$52.47', detail: 'Monthly commitment',
    rows: [['Netflix', '$15.49'], ['Spotify', '$11.99']],
  },
  {
    kind: 'renewals', label: 'Renewals', icon: CalendarDays, anchor: '#renewals', action: 'Explore renewals',
    title: 'Know what’s due next.',
    body: 'See upcoming bills, trial endings, and price changes in time to decide what to keep.',
    metric: 'Nov 24', detail: 'Next renewal',
    rows: [['Netflix', 'Nov 24'], ['Spotify', 'Nov 25']],
  },
  {
    kind: 'teams', label: 'Shared costs', icon: UsersRound, anchor: '#shared-plans', action: 'Explore shared costs',
    title: 'See who owes what.',
    body: 'Split shared plans, record repayments, and see what’s still outstanding for each person.',
    metric: '$25.00', detail: 'Still owed to you',
    rows: [['Alex', '$15.00'], ['Morgan', '$10.00']],
  },
  {
    kind: 'discovery', label: 'Discovery', icon: Files, anchor: '#discovery', action: 'Explore discovery',
    title: 'Find recurring payments.',
    body: 'Bring in a statement or connect an account. Review what DUES finds before you add a plan.',
    metric: '2 matches', detail: 'Recurring payments to review',
    rows: [['Netflix', 'Monthly'], ['Spotify', 'Monthly']],
  },
  {
    kind: 'records', label: 'Records & security', icon: ShieldCheck, anchor: '#records-security', action: 'Explore records',
    title: 'Keep the proof of payment.',
    body: 'Attach private receipts, export filtered charge reports, and back up your records.',
    metric: '2 receipts', detail: 'Linked to charges',
    rows: [['Figma', 'PDF'], ['Notion', 'PDF']],
  },
]

function FeaturePreview({ feature }: { feature: (typeof featureSlides)[number] }) {
  const Icon = feature.icon

  return <div className={`lv-slide-visual lv-slide-${feature.kind}`}>
    <div className="lv-preview-card">
      <div className="lv-preview-header"><Icon size={18} aria-hidden="true"/><span>{feature.label}</span></div>
      <div className="lv-preview-metric"><span>{feature.detail}</span><strong>{feature.metric}</strong></div>
      {feature.kind === 'spending' && <Bars small/>}
      <ul className="lv-preview-rows">{feature.rows.map(([name, value]) => (
        <li key={name}>
          {feature.kind === 'teams' ? <LandingAvatar person={name === 'Alex' ? 'Alex' : 'Morgan'} className="lv-preview-initial"/> : <ServiceIcon name={name}/>}
          <span>{name}</span><b>{value}</b>
        </li>
      ))}</ul>
      <small>Example data</small>
    </div>
  </div>
}

function FeatureCarousel({ slide, onChange }: { slide: number; onChange: (index: number) => void }) {
  const current = featureSlides[slide]
  return <>
    <div className="lv-carousel" role="region" aria-roledescription="carousel" aria-label="DUES features">
      {[-2, -1, 1, 2].map(offset => {
        const index = (slide + offset + featureSlides.length) % featureSlides.length
        const feature = featureSlides[index]
        const Icon = feature.icon
        return <button
          key={offset}
          type="button"
          data-lp-reveal="scroll"
          className={`lv-carousel-peek lv-slide-${feature.kind} lv-peek-${offset < 0 ? 'left' : 'right'}${Math.abs(offset) === 2 ? ' lv-peek-outer' : ''}`}
          onClick={() => onChange(index)}
          aria-label={`Show ${feature.label.toLowerCase()}`}
        >
          <Icon size={20} aria-hidden="true"/>
          <span>{feature.label}</span>
        </button>
      })}
      <article className="lv-feature-slide" data-lp-reveal="scroll" aria-live="polite" aria-atomic="true">
        <div key={`copy-${current.kind}`} className="lv-feature-slide-copy">
          <h3>{current.title}</h3><p>{current.body}</p>
          <a href={current.anchor} className="lv-text-link">{current.action}</a>
        </div>
        <FeaturePreview key={current.kind} feature={current}/>
      </article>
    </div>
    <div className="lv-carousel-controls" data-lp-reveal="scroll" role="group" aria-label="Choose a feature">
      {featureSlides.map((feature, index) => (
        <button type="button" key={feature.kind} aria-pressed={slide === index} onClick={() => onChange(index)}>
          {feature.label}
        </button>
      ))}
    </div>
  </>
}

const questions = [
  ['Is DUES really free?', 'Yes. Subscription tracking, reminders, budgets, planning tools, and shared workspaces are all free. No payment card is needed to create an account.'],
  ['How can I bring my subscriptions into DUES?', 'Use Quick add, the full subscription form, or a CSV import. You can also import a bank statement and review recurring-payment suggestions. Plaid bank connections and read-only Gmail receipt discovery are available when configured for your deployment.'],
  ['Can I manage subscriptions with other people?', 'Yes. Create a team, invite members, assign roles, split subscription costs, and record payments and partial repayments. Personal and team workspaces stay separate.'],
  ['What about different currencies?', 'DUES tracks subscriptions, spending, forecasts, budgets, and settlements by currency. Spending insights can also show estimated combined commitments in your preferred base currency using saved reference exchange rates, with dates and sources shown.'],
  ['Will DUES cancel subscriptions for me?', 'DUES tracks cancellation requests, trial endings, and cancel-by dates. You make any cancellation or pause directly with the provider, then record it in DUES.'],
  ['Can I take my data with me?', 'Export subscription lists, download filtered charge reports as CSV or PDF, or create a finance backup with receipts, history, budgets, and repayments. Restore lets you preview the archive before adding copies of its records.'],
  ['How do reminders fit around my day?', 'Choose reminder offsets, individual emails or daily and weekly summaries, and quiet hours in your time zone. In-app notifications remain available, and you can snooze unread reminders until tomorrow. Browser push depends on deployment setup, permission, and device support.'],
]

export function LandingPageV2() {
  const { user } = useAuth()
  const pageRef = useLandingMotion(true, '0px 0px -16px 0px')
  useSmoothPageScroll(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [slide, setSlide] = useState(0)
  const menuRef = useRef<HTMLElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const start = user ? '/dashboard/' : '/accounts/signup/'

  useEffect(() => {
    const previous = document.title
    document.title = 'DUES — Take control of every subscription'
    return () => { document.title = previous }
  }, [])

  useEffect(() => {
    if (!menuOpen) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') { setMenuOpen(false); toggleRef.current?.focus() } }
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !menuRef.current?.contains(event.target)) setMenuOpen(false) }
    const desktop = window.matchMedia('(min-width: 761px)')
    const resize = () => { if (desktop.matches) setMenuOpen(false) }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', outside)
    desktop.addEventListener('change', resize)
    return () => { document.removeEventListener('keydown', close); document.removeEventListener('pointerdown', outside); desktop.removeEventListener('change', resize) }
  }, [menuOpen])

  return <div className="lp-page lp-v2" id="top" ref={pageRef}>
    <a className="lp-skip-link" href="#main-content">Skip to content</a>
    <main className="lv-content" id="main-content" tabIndex={-1}>
      <div className="lv-hero">
        <header className="lv-header"><nav ref={menuRef} className="lv-nav" aria-label="Primary navigation" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setMenuOpen(false) }}>
          <Brand/>
          <div className="lv-nav-links"><a href="#top">Home</a><a href="#features">Features</a><a href="#product-demo">Try the demo</a><a href="#all-features">Every feature</a></div>
          <div className="lv-nav-actions"><Link className="lv-button lv-button-dark" to={start}>{user ? 'Open DUES' : 'Get started'}</Link><button ref={toggleRef} type="button" className="lv-menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="lv-mobile-menu" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20}/> : <Menu size={20}/>}</button></div>
          {menuOpen && <div className="lv-mobile-menu" id="lv-mobile-menu" data-lenis-prevent><a href="#features" onClick={() => setMenuOpen(false)}>Features</a><a href="#product-demo" onClick={() => setMenuOpen(false)}>Try the demo</a><a href="#pricing" onClick={() => setMenuOpen(false)}>Free plan</a><a href="#questions" onClick={() => setMenuOpen(false)}>Questions</a><a href="#all-features">Every feature</a><Link to="/accounts/login/">Log in</Link></div>}
        </nav></header>
        <section className="lv-hero-copy" aria-labelledby="lv-title">
            <h1 id="lv-title">
              <span className="lv-title-line"><span data-lp-reveal>You Can Take Control Of</span></span>{' '}
              <span className="lv-title-line"><span data-lp-reveal>Every <RotatingServiceLogo/> Subscription</span></span>
            </h1>
            <p data-lp-reveal>Track every plan, see what you spend, and share costs.<br className="lv-desktop-break"/> Make room for more with DUES.</p>
            <div className="lv-hero-actions" data-lp-reveal>
              <Link to={start} className="lv-button lv-button-white">{user ? 'Open your dashboard' : 'Get started free'}<span className="lv-button-mark"><Zap size={15} fill="currentColor"/></span></Link>
              <a href="#product-demo" className="lv-button lv-button-glass">Try the demo</a>
            </div>
        </section>
        <div className="lv-hero-art" aria-label="An illustrative preview of subscription spending in DUES" role="img">
          <div className="lv-hero-illustration">
            <img className="lv-hero-photo" data-lp-reveal src={heroImage} alt="" fetchPriority="high"/>
            <Payment name="Netflix" amount="$15.49" className="lv-payment-netflix"/>
            <Payment name="Spotify" amount="$11.99" className="lv-payment-spotify"/>
          </div>
        </div>
      </div>

      <div className="lv-main">
        <section className="lv-about lv-container" aria-labelledby="lv-about-title">
          <div className="lv-about-aside" data-lp-reveal="scroll">
            <span className="lv-eyebrow">About DUES</span>
            <div className="lv-about-stats">
              <div><strong>12 months</strong><span>Of upcoming renewals in view</span></div>
              <div><strong>$0</strong><span>Monthly cost to use DUES</span></div>
            </div>
          </div>
          <article className="lv-about-copy" data-lp-reveal="scroll">
            <h2 id="lv-about-title">Taking Control Of Your Subscriptions.</h2>
            <div className="lv-about-body">
              <p>Subscriptions are easy to start and easy to forget. DUES shows what you’re paying for, when you’ll be charged, and how much each plan costs.</p>
              <p>Keep everyday subscriptions and shared team plans together in one dashboard.</p>
            </div>
            <a href="#features" className="lv-button lv-button-dark">Explore features</a>
          </article>
          <div className="lv-about-photo" data-lp-reveal="scroll">
            <LifestylePhoto className="lv-lifestyle" alt="A woman enjoying music in the sunshine"/>
            <SpendingCard/>
          </div>
        </section>

        <section className="lv-life lv-container" aria-labelledby="lv-life-title">
          <div className="lv-life-large" data-lp-reveal="scroll">
            <img className="lv-life-person" src={teamPortrait} alt="" loading="lazy"/>
            <div className="lv-life-copy">
              <h2 id="lv-life-title">Understand Your Spending at a Glance.</h2>
              <p>See your subscriptions, upcoming bills, and monthly budget together.</p>
            </div>
          </div>
          <div className="lv-life-small" data-lp-reveal="scroll" aria-hidden="true"><img src={heroImage} alt="" loading="lazy"/></div>
        </section>

        <section className="lv-benefits" id="features" aria-labelledby="lv-benefits-title">
          <div className="lv-container">
            <div className="lv-section-heading" data-lp-reveal="scroll">
              <h2 id="lv-benefits-title">Less Subscription Stress. More Financial Control.</h2>
              <p>Track recurring payments and see how they fit into your budget.</p>
            </div>
            <div className="lv-benefit-grid">
              <article data-lp-reveal="scroll" className="lv-benefit-featured">
                <h3>All in One Place</h3><p>Every subscription, organized in one dashboard.</p>
                <ul><li><Check/>Keep personal and team plans together</li><li><Check/>Add subscriptions or import a CSV</li><li><Check/>See cards and payment history</li></ul>
              </article>
              <article data-lp-reveal="scroll"><h3>Know Before Renewal</h3><p>Get reminders for upcoming charges, trial endings, and cancel-by dates.</p></article>
              <article data-lp-reveal="scroll"><h3>Shared Plans &amp; Costs</h3><p>Split costs with your team and track each person’s repayments.</p></article>
              <article data-lp-reveal="scroll"><h3>Spending Insights</h3><p>Set budgets, forecast bills, and review spending by currency.</p></article>
            </div>
          </div>
        </section>

        <section className="lv-feature-stage" aria-labelledby="lv-stage-title">
          <div className="lv-section-heading" data-lp-reveal="scroll"><h2 id="lv-stage-title">A Smarter Way To Manage<br/>Subscriptions.</h2></div>
          <FeatureCarousel slide={slide} onChange={setSlide}/>
        </section>

        <ProductDemo/>

        <LandingFeatures signedIn={Boolean(user)}/>

        <section className="lv-free lv-container" data-lp-reveal="scroll" id="pricing" aria-labelledby="lv-free-title"><div><span className="lv-eyebrow">ONE LESS SUBSCRIPTION</span><h2 id="lv-free-title">More clarity.<br/>No monthly bill.</h2><p>Tracking, discovery, budgets, teams, reports, and backups.<br className="lv-desktop-break"/> Every current feature is included.</p><Link to={start} className="lv-button lv-button-dark">{user ? 'Go to dashboard' : 'Start organizing for free'}</Link></div><div className="lv-free-price"><span>THE DUES PLAN</span><strong>$0<span>/ month</span></strong><p>No credit card. No extra subscription.</p><div><span><Check/>Personal & teams</span><span><Check/>Every current feature</span></div></div></section>

        <section className="lv-questions lv-container" id="questions" aria-labelledby="lv-questions-title"><div className="lv-section-heading" data-lp-reveal="scroll"><span className="lv-eyebrow">A LITTLE MORE CLARITY</span><h2 id="lv-questions-title">Good questions.</h2></div><div className="lv-faqs">{questions.map(([question, answer], index) => <details data-lp-reveal="scroll" key={question} open={index === 0 ? true : undefined}><summary>{question}<Plus size={18}/></summary><p>{answer}</p></details>)}</div></section>
        <section className="lv-last-call" data-lp-reveal="scroll"><span className="lv-eyebrow">LESS LIFE ADMIN. MORE LIVING.</span><h2>Keep what you love.<br/>Know what you pay.</h2><p>A little more in control feels good.</p><Link to={start} className="lv-button lv-button-dark">{user ? 'Open DUES' : 'Get started with DUES'}<span className="lv-button-mark"><Zap size={15} fill="currentColor"/></span></Link></section>
      </div>
    </main>
    <LandingFooter/>
  </div>
}
