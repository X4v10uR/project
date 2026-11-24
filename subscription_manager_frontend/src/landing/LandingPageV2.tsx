import { useEffect, useRef, useState } from 'react'
import {
  CalendarDays, Check, ChevronDown, FileText, LayoutGrid,
  Menu, Plus, ShieldCheck, X, Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../accounts'
import { ServiceIcon } from '../ServiceIcon'
import { LandingFooter } from './LandingPage'
import { useLandingMotion } from './useLandingMotion'
import { useSmoothPageScroll } from './useSmoothPageScroll'
import './landing-v2.css'

const asset = `${import.meta.env.BASE_URL}landing-v2/campaign.webp`
const heroImage = `${import.meta.env.BASE_URL}landing-v2/hero-hand.webp`
const featurePortrait = `${import.meta.env.BASE_URL}landing-v2/feature-portrait.webp`
const teamPortrait = `${import.meta.env.BASE_URL}landing-v2/team-portrait.webp`

// The campaign sheet contains two square photos. This viewport isolates the
// lifestyle photo before cropping it, so the phone panel never bleeds into it.
function LifestylePhoto({ className, alt }: { className: string; alt?: string }) {
  return <svg className={className} viewBox="100 0 100 100" preserveAspectRatio="xMidYMid slice" role={alt ? 'img' : undefined} aria-label={alt} aria-hidden={!alt}><image href={asset} width="200" height="100"/></svg>
}
const personal = [
  { name: 'Netflix', plan: 'Standard', amount: 15.49, day: 24 },
  { name: 'Spotify', plan: 'Premium Individual', amount: 11.99, day: 25 },
  { name: 'Figma', plan: 'Professional', amount: 12, day: 27 },
  { name: 'Notion', plan: 'Plus', amount: 10, day: 28 },
  { name: 'iCloud+', plan: '200 GB', amount: 2.99, day: 30 },
]
const team = [
  { name: 'Figma', plan: 'Professional · 3 people', amount: 45, day: 24 },
  { name: 'Notion', plan: 'Plus · 3 people', amount: 30, day: 28 },
  { name: 'Spotify', plan: 'Duo · 2 people', amount: 16.99, day: 30 },
]

function Brand() {
  return <a className="lv-brand" href="#top" aria-label="DUES home"><span><Zap size={18} fill="currentColor"/></span>DUES<b>.</b></a>
}

const headlineServices = ['Netflix', 'Spotify', 'YouTube', 'hulu', 'HBO Max', 'Dropbox', 'Paramount+', 'AppleTV+', 'Prime Video']

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

function Phone() {
  const [workspace, setWorkspace] = useState<'personal' | 'team'>('personal')
  const [calendar, setCalendar] = useState(false)
  const [annual, setAnnual] = useState(false)
  const services = workspace === 'personal' ? personal : team
  const total = services.reduce((sum, service) => sum + service.amount, 0)

  return <div className="lv-phone">
    <div className="lv-phone-status" aria-hidden="true"><span>9:41</span><i/><span>▮▮▮ ▰</span></div>
    <div className="lv-phone-body">
      <div className="lv-phone-title"><strong>{calendar ? 'Renewals' : 'Insights'}</strong><LayoutGrid size={18}/></div>
      <div className="lv-workspaces" role="group" aria-label="Demo workspace"><button type="button" aria-pressed={workspace === 'personal'} onClick={() => setWorkspace('personal')}>Personal</button><button type="button" aria-pressed={workspace === 'team'} onClick={() => setWorkspace('team')}>Team</button></div>
      <div className="lv-phone-summary" aria-live="polite" aria-atomic="true">
        <button type="button" onClick={() => setAnnual(!annual)} aria-label={`Show ${annual ? 'monthly' : 'yearly'} spending`}>{annual ? 'Yearly' : 'Monthly'} spending <ChevronDown size={13}/></button>
        <strong>${(total * (annual ? 12 : 1)).toFixed(2)}</strong><small>{services.length} subscriptions · {annual ? 'per year' : 'per month'}</small>
        {!calendar && <Bars/>}
        {calendar && <div className="lv-calendar" role="img" aria-label={`November 2026 example renewals: ${services.map(s => `${s.name} on November ${s.day}`).join(', ')}`}><div>{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => <b key={i}>{d}</b>)}{Array.from({ length: 6 }, (_, i) => <span key={`blank-${i}`}/>)}{Array.from({ length: 30 }, (_, i) => <span className={services.some(s => s.day === i + 1) ? 'is-renewal' : ''} key={i}>{i + 1}</span>)}</div></div>}
      </div>
      <div className="lv-phone-list-title"><strong>Upcoming payments</strong><span>November</span></div>
      <div className="lv-phone-services">{services.slice(0, 3).map(s => <div key={s.name}><ServiceIcon name={s.name}/><span className="lv-phone-service-name"><strong>{s.name}</strong><small>{s.plan}</small></span><b>${s.amount.toFixed(2)}<small>Nov {s.day}</small></b></div>)}</div>
      <div className="lv-phone-nav" role="group" aria-label="Demo views"><button type="button" aria-pressed={!calendar} onClick={() => setCalendar(false)}><LayoutGrid size={16}/>Overview</button><button type="button" aria-pressed={calendar} onClick={() => setCalendar(true)}><CalendarDays size={16}/>Calendar</button></div>
      <span className="lv-demo-label">Illustrative demo · USD</span>
    </div>
    <div className="lv-phone-home"/>
  </div>
}

const featureSlides = [
  { title: 'Smarter subscription management.', body: 'Your streaming, software, and everyday essentials. Track every plan, cost, and renewal in one place.', label: 'Your subscriptions', services: ['Netflix', 'Spotify', 'Notion'], kind: 'subscriptions' },
  { title: 'A little notice. A lot less surprise.', body: 'Get a heads-up before renewals, trial endings, and cancellation deadlines. Choose the reminders that work for you.', label: 'Your reminders', services: ['Spotify', 'Netflix', 'Figma'], kind: 'reminders' },
  { title: 'Shared plans. Clearer shares.', body: 'Bring your team or your people together. Split costs, record payments, and keep track of repayments.', label: 'Your shared workspace', services: ['Figma', 'Notion', 'Spotify'], kind: 'teams' },
]

function FeaturePortrait({ kind }: { kind: string }) {
  return kind === 'reminders'
    ? <LifestylePhoto className="lv-feature-portrait lv-feature-portrait-music"/>
    : <img className={`lv-feature-portrait lv-feature-portrait-${kind}`} src={kind === 'teams' ? teamPortrait : featurePortrait} alt="" width="1086" height="1448" loading="lazy"/>
}

function FeatureCarousel({ slide, onChange }: { slide: number; onChange: (index: number) => void }) {
  const current = featureSlides[slide]
  return <>
    <div className="lv-carousel" role="region" aria-roledescription="carousel" aria-label="DUES features">
      {[-2, -1, 1, 2].map(offset => {
        const index = (slide + offset + featureSlides.length) % featureSlides.length
        return <button key={offset} type="button" data-lp-reveal className={`lv-carousel-peek lv-peek-${offset < 0 ? 'left' : 'right'}${Math.abs(offset) === 2 ? ' lv-peek-outer' : ''}`} onClick={() => onChange(index)} aria-label={`Show ${featureSlides[index].label.toLowerCase()}`}><FeaturePortrait kind={featureSlides[index].kind}/></button>
      })}
      <article className="lv-feature-slide" data-lp-reveal aria-live="polite" aria-atomic="true">
        <div key={current.kind} className="lv-feature-slide-copy">
          <h3>{current.title}</h3><p>{current.body}</p>
          <div className="lv-feature-slide-footer"><span>{current.label}</span><a href={slide === 2 ? '#planning' : '#preview'} className="lv-text-link">{slide === 2 ? 'Explore planning tools' : 'Take a closer look'}</a></div>
        </div>
        <div className={`lv-slide-visual lv-slide-${current.kind}`}><FeaturePortrait key={current.kind} kind={current.kind}/></div>
      </article>
    </div>
    <div className="lv-carousel-controls" data-lp-reveal role="group" aria-label="Choose a feature">{featureSlides.map((s, i) => <button type="button" key={s.kind} aria-label={`View ${s.label.toLowerCase()}`} aria-pressed={slide === i} onClick={() => onChange(i)}><span/></button>)}</div>
  </>
}

const questions = [
  ['Is DUES really free?', 'Yes. Subscription tracking, reminders, budgets, planning tools, and shared workspaces are all free. No payment card is needed to create an account.'],
  ['Do I need to connect my bank?', 'No. Add subscriptions with Quick add or import a CSV. Optional bank, email, and statement discovery tools can help you find recurring payments when configured.'],
  ['Can I manage subscriptions with other people?', 'Yes. Create a team, invite members, assign roles, split subscription costs, and record payments and partial repayments. Personal and team workspaces stay separate.'],
  ['What about different currencies?', 'DUES tracks subscriptions, spending, forecasts, and budgets by currency. Combined totals are available in Planning when exchange rates are configured.'],
  ['Will DUES cancel subscriptions for me?', 'DUES tracks cancellation requests, trial endings, and cancel-by dates. You make any cancellation or pause directly with the provider, then record it in DUES.'],
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
    <main className="lv-content" id="main-content">
      <div className="lv-hero">
        <header className="lv-header"><nav ref={menuRef} className="lv-nav" aria-label="Primary navigation" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setMenuOpen(false) }}>
          <Brand/>
          <div className="lv-nav-links"><a href="#top">Home</a><a href="#features">Features</a><a href="#how-it-works">How it works</a><Link to="/">Original design</Link></div>
          <div className="lv-nav-actions"><Link className="lv-button lv-button-dark" to={start}>{user ? 'Open DUES' : 'Get started'}</Link><button ref={toggleRef} type="button" className="lv-menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="lv-mobile-menu" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20}/> : <Menu size={20}/>}</button></div>
          {menuOpen && <div className="lv-mobile-menu" id="lv-mobile-menu"><a href="#features" onClick={() => setMenuOpen(false)}>Features</a><a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a><a href="#pricing" onClick={() => setMenuOpen(false)}>Free plan</a><a href="#questions" onClick={() => setMenuOpen(false)}>Questions</a><Link to="/">Original design</Link><Link to="/accounts/login/">Log in</Link></div>}
        </nav></header>
        <section className="lv-hero-copy" aria-labelledby="lv-title">
            <h1 id="lv-title">
              <span className="lv-title-line"><span data-lp-reveal>You Can Take Control Of</span></span>{' '}
              <span className="lv-title-line"><span data-lp-reveal>Every <RotatingServiceLogo/> Subscription</span></span>
            </h1>
            <p data-lp-reveal>Track spending, plan for renewals, and see what you pay<br className="lv-desktop-break"/> for your subscriptions with DUES.</p>
            <div className="lv-hero-actions" data-lp-reveal>
              <Link to={start} className="lv-button lv-button-white">{user ? 'Open your dashboard' : 'Get started free'}<span className="lv-button-mark"><Zap size={15} fill="currentColor"/></span></Link>
              <a href="#how-it-works" className="lv-button lv-button-glass">See how it works</a>
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

        <section className="lv-process lv-container" id="how-it-works" aria-labelledby="lv-process-title">
          <div className="lv-section-heading" data-lp-reveal="scroll"><h2 id="lv-process-title">From Subscription Chaos To<br/>Clarity In 3 Steps.</h2></div>
          <div className="lv-process-grid">
            <div id="preview" className="lv-interactive-preview" data-lp-reveal>
              <Phone/>
              <p>Try the demo. Switch workspaces or open the calendar.</p>
            </div>
            <div className="lv-steps">
              <article data-lp-reveal="scroll"><span>01</span><div><h3>Add your subscriptions</h3><p>Enter a plan with Quick add or import your list from a CSV file.</p><Link to={user ? '/subscriptions/quick-add/' : start} className="lv-text-link">Add your first subscription<Plus size={14}/></Link></div></article>
              <article data-lp-reveal="scroll"><span>02</span><div><h3>Review your spending</h3><p>See your monthly commitment and set a budget for personal or shared plans.</p></div></article>
              <article data-lp-reveal="scroll"><span>03</span><div><h3>Set renewal reminders</h3><p>Choose when to hear about renewals and trial endings, or add the dates to your calendar.</p></div></article>
            </div>
          </div>
        </section>

        <section className="lv-planning lv-container" id="planning" aria-labelledby="lv-planning-title"><div className="lv-planning-intro" data-lp-reveal="scroll"><span className="lv-eyebrow">BEYOND THE NEXT PAYMENT</span><h2 id="lv-planning-title">All the little details.<br/>Already thought of.</h2><p>From the first bill to your next subscription review, your planning tools are right here.</p></div><div className="lv-planning-grid"><article data-lp-reveal="scroll"><CalendarDays/><h3>A calendar that keeps up.</h3><p>See renewals, trials, and deadlines. Export to your calendar or subscribe to a live feed.</p></article><article data-lp-reveal="scroll"><FileText/><h3>Records worth keeping.</h3><p>Keep private receipts, track charge history, and export reports. Bring statement payments into the picture.</p></article><article data-lp-reveal="scroll"><LayoutGrid/><h3>A moment to review.</h3><p>Spot duplicate plans, record usage, review price changes, and plan pauses or cancellations.</p></article><article data-lp-reveal="scroll"><ShieldCheck/><h3>Your space. Your control.</h3><p>Optional authenticator security, team roles, protected credentials, and portable backups.</p></article></div></section>

        <section className="lv-free lv-container" data-lp-reveal="scroll" id="pricing" aria-labelledby="lv-free-title"><div><span className="lv-eyebrow">ONE LESS SUBSCRIPTION</span><h2 id="lv-free-title">More clarity.<br/>No monthly bill.</h2><p>Subscriptions, reminders, budgets, shared workspaces,<br className="lv-desktop-break"/> and planning. The whole good thing, free.</p><Link to={start} className="lv-button lv-button-dark">{user ? 'Go to dashboard' : 'Start organizing for free'}</Link></div><div className="lv-free-price"><span>THE DUES PLAN</span><strong>$0<span>/ month</span></strong><p>No credit card. No extra subscription.</p><div><span><Check/>Personal & teams</span><span><Check/>All planning tools</span></div></div></section>

        <section className="lv-questions lv-container" id="questions" aria-labelledby="lv-questions-title"><div className="lv-section-heading" data-lp-reveal="scroll"><span className="lv-eyebrow">A LITTLE MORE CLARITY</span><h2 id="lv-questions-title">Good questions.</h2></div><div className="lv-faqs">{questions.map(([question, answer], index) => <details data-lp-reveal="scroll" key={question} open={index === 0 ? true : undefined}><summary>{question}<Plus size={18}/></summary><p>{answer}</p></details>)}</div></section>
        <section className="lv-last-call" data-lp-reveal="scroll"><span className="lv-eyebrow">LESS LIFE ADMIN. MORE LIVING.</span><h2>Keep what you love.<br/>Know what you pay.</h2><p>A little more in control feels good.</p><Link to={start} className="lv-button lv-button-dark">{user ? 'Open DUES' : 'Get started with DUES'}<span className="lv-button-mark"><Zap size={15} fill="currentColor"/></span></Link></section>
      </div>
    </main>
    <LandingFooter/>
  </div>
}
