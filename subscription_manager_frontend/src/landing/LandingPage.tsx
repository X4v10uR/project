import { ServiceIcon } from '../ServiceIcon'
import { useEffect, useId, useState } from 'react'
import {
  Bell, CalendarDays, ChartNoAxesCombined, Check, ChevronDown, CircleHelp,
  CreditCard, LayoutGrid, Menu, Plus, Search, ShieldCheck, SlidersHorizontal,
  Sparkles, UsersRound, Wallet, X, Zap,
} from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../accounts'
import './landing.css'

type Service = 'spotify' | 'netflix' | 'figma' | 'icloud' | 'notion' | 'youtube'

function LandingServiceIcon({ service }: { service: Service }) {
  return <ServiceIcon name={service} className={`lp-service-icon lp-service-${service}`} />
}

function Logo() {
  return <Link className="lp-logo" to="/" aria-label="Subly home"><span><Zap size={21} strokeWidth={2.5} fill="currentColor" aria-hidden="true" /></span>subly<span className="lp-logo-period">.</span></Link>
}

const personalServices: { service: Service; name: string; plan: string; price: string; date: string }[] = [
  { service: 'spotify', name: 'Spotify', plan: 'Premium Individual', price: '$11.99', date: 'Nov 22' },
  { service: 'netflix', name: 'Netflix', plan: 'Standard', price: '$15.49', date: 'Nov 24' },
  { service: 'icloud', name: 'iCloud+', plan: '200 GB storage', price: '$2.99', date: 'Nov 28' },
]
const teamServices: typeof personalServices = [
  { service: 'figma', name: 'Figma', plan: 'Professional · 3 people', price: '$45.00', date: 'Nov 21' },
  { service: 'notion', name: 'Notion', plan: 'Plus · 3 people', price: '$30.00', date: 'Nov 25' },
  { service: 'spotify', name: 'Spotify', plan: 'Premium Duo · 2 people', price: '$16.99', date: 'Nov 29' },
]

function SpendingChart({ shared = false, large = false }: { shared?: boolean; large?: boolean }) {
  const gradientId = useId().replaceAll(':', '')
  return <div className={`lp-chart ${large ? 'lp-chart-large' : ''}`}>
    <svg viewBox="0 0 500 120" role="img" aria-label={shared ? 'Illustrative shared monthly spending trend' : 'Illustrative personal monthly spending trend'} preserveAspectRatio="none">
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#b5d879" stopOpacity=".42"/><stop offset="100%" stopColor="#b5d879" stopOpacity="0"/></linearGradient></defs>
      <path d="M0 25H500M0 65H500M0 105H500" stroke="#dfe5dd" strokeDasharray="3 6" strokeWidth="1"/>
      <path d={shared ? 'M0 86C38 86 40 70 78 70S126 88 158 76 204 28 246 38 287 64 323 50 374 63 414 30 463 34 500 18V120H0Z' : 'M0 77C32 77 30 94 67 90S103 46 142 54 186 90 219 68 254 76 286 49 326 24 356 36 390 58 420 24 470 41 500 13V120H0Z'} fill={`url(#${gradientId})`}/>
      <path d={shared ? 'M0 86C38 86 40 70 78 70S126 88 158 76 204 28 246 38 287 64 323 50 374 63 414 30 463 34 500 18' : 'M0 77C32 77 30 94 67 90S103 46 142 54 186 90 219 68 254 76 286 49 326 24 356 36 390 58 420 24 470 41 500 13'} stroke="#7d9e42" strokeWidth="2.5" fill="none"/>
    </svg>
    <div className="lp-chart-months">{['Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'].map(month => <span key={month}>{month}</span>)}</div>
  </div>
}

function ProductPreview() {
  const [workspace, setWorkspace] = useState<'personal' | 'shared'>('personal')
  const [view, setView] = useState<'overview' | 'subscriptions' | 'calendar'>('overview')
  const [yearly, setYearly] = useState(false)
  const shared = workspace === 'shared'
  const services = shared ? teamServices : personalServices
  const monthly = shared ? 91.99 : 84.47
  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutGrid },
    { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard },
    { id: 'calendar', label: 'Calendar', icon: CalendarDays },
  ] as const

  return <div className="lp-product-stage" id="preview">
    <div className="lp-orbit lp-orbit-one" aria-hidden="true"/><div className="lp-orbit lp-orbit-two" aria-hidden="true"/>
    <div className="lp-floating-note lp-renewal-note"><span className="lp-note-icon"><Bell size={18}/></span><div><strong>A little heads-up.</strong><span>{services[0].name} renews on {services[0].date}.</span></div><Check size={16} className="lp-note-check"/></div>
    <div className="lp-product-window">
      <div className="lp-window-bar"><div className="lp-window-dots" aria-hidden="true"><i/><i/><i/></div><span><ShieldCheck size={12} aria-hidden="true"/> Your space. All in order.</span><span className="lp-demo-label">Interactive demo</span></div>
      <div className="lp-demo-app">
        <aside className="lp-demo-sidebar">
          <span className="lp-demo-brand"><span><Zap size={16} fill="currentColor"/></span>subly.</span>
          <div className="lp-demo-nav" aria-label="Demo views">
            {tabs.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => setView(id)} aria-pressed={view === id}><Icon size={17}/><span>{label}</span></button>)}
          </div>
          <div className="lp-sidebar-bottom"><ShieldCheck size={17}/><span>A little more peace of mind.</span></div>
          <div className="lp-demo-profile"><span>JD</span><div><strong>Jamie Davis</strong><small>Personal account</small></div></div>
        </aside>
        <div className="lp-demo-main">
          <div className="lp-demo-heading"><div><span className="lp-eyebrow">YOUR MONEY, AT A GLANCE</span><h3>{view === 'overview' ? 'Looking good, Jamie' : view === 'subscriptions' ? 'Your subscriptions' : 'Your renewal calendar'}<span className="lp-heading-dot">.</span></h3></div><span className="lp-demo-avatar">J</span></div>
          <div className="lp-demo-toolbar"><div className="lp-segment" aria-label="Demo workspace"><button type="button" aria-pressed={!shared} onClick={() => setWorkspace('personal')}>Personal</button><button type="button" aria-pressed={shared} onClick={() => setWorkspace('shared')}><UsersRound size={13}/>Shared</button></div><span className="lp-demo-date">November 2026<ChevronDown size={12}/></span></div>
          <div className="lp-demo-content" aria-live="polite" aria-atomic="true">
            {view === 'overview' ? <>
              <div className="lp-stat-grid"><div className="lp-spend-stat"><span>{yearly ? 'Yearly' : 'Monthly'} spending<button type="button" className="lp-period-toggle" onClick={() => setYearly(!yearly)} aria-label={`Show ${yearly ? 'monthly' : 'yearly'} spending`}><ChevronDown size={13}/></button></span><strong>${(monthly * (yearly ? 12 : 1)).toFixed(2)}<small>/{yearly ? 'yr' : 'mo'}</small></strong><span className="lp-stat-caption">{shared ? 'Shared plans, clearly split.' : 'A clear view of your commitments.'}</span></div><div className="lp-active-stat"><span>Active subscriptions<Wallet size={15}/></span><strong>{shared ? '3' : '8'}<small>services</small></strong><div className="lp-mini-services">{(shared ? ['figma', 'notion', 'spotify'] : ['spotify', 'netflix', 'figma', 'icloud'] as Service[]).map(service => <LandingServiceIcon key={service} service={service as Service}/>)}{!shared && <i>+4</i>}</div></div></div>
              <SpendingChart shared={shared}/>
            </> : view === 'subscriptions' ? <div className="lp-demo-explainer"><CreditCard size={24}/><div><strong>{shared ? 'Shared costs. One clear picture.' : 'All your favorites, accounted for.'}</strong><p>{shared ? 'Keep every plan and participant’s share together.' : 'See each plan, price, and next renewal in one place.'}</p></div></div> : <div className="lp-demo-calendar"><div>{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => <span key={index}>{day}</span>)}</div><div>{Array.from({ length: 14 }, (_, index) => <span className={[shared ? 21 : 22, shared ? 25 : 24, shared ? 29 : 28].includes(index + 16) ? 'has-renewal' : ''} key={index}>{index + 16}</span>)}</div></div>}
            <div className="lp-table-heading"><strong>{view === 'calendar' ? 'Coming up this month' : view === 'subscriptions' ? 'Your active plans' : 'Upcoming renewals'}</strong><span>{shared ? 'Shared workspace' : 'Next 30 days'}</span></div>
            <div className="lp-service-table">{services.map(item => <div className="lp-service-row" key={item.service}><LandingServiceIcon service={item.service}/><div className="lp-service-name"><strong>{item.name}</strong><span>{item.plan}</span></div><span className="lp-service-date">{item.date}</span><strong className="lp-service-price">{item.price}<small>/mo</small></strong></div>)}</div>
          </div>
        </div>
      </div>
    </div>
    <div className="lp-floating-note lp-clarity-note"><span className="lp-clarity-icon"><ChartNoAxesCombined size={21}/></span><div><span>Less guesswork.</span><strong>More peace of mind.</strong></div><Sparkles size={18}/></div>
    <div className="lp-preview-caption"><span className="lp-caption-line"/> A little preview of a calmer financial life <span className="lp-caption-line"/></div>
  </div>
}

const faqs = [
  ['Is Subly really free?', 'Yes. Subly is free to use, including subscription tracking, renewal reminders, planning tools, and shared workspaces. You don’t need a payment card to create an account.'],
  ['Do I need to connect my bank account?', 'No. You can add subscriptions yourself with quick add or import a CSV. Optional connected-account discovery is available when configured, but you can use Subly without it.'],
  ['Can I track subscriptions in different currencies?', 'Yes. Subly keeps spending and budgets by currency, so your costs stay clear. Planning also supports combined currency totals when exchange rates are available.'],
  ['Can I share subscriptions with my team?', 'Yes. Create a team, invite members, and track shared plans and participant shares. You can also record payments and repayments to see who owes what.'],
  ['Will Subly cancel subscriptions for me?', 'Subly helps you review plans, record cancellation requests, and remember cancellation deadlines. You still cancel or pause the service directly with its provider.'],
]

export function LandingPage() {
  const { user, loading } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState<number | null>(0)
  useEffect(() => {
    const previousTitle = document.title
    document.title = 'Subly — Less managing. More living.'
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.title = previousTitle; document.removeEventListener('keydown', closeOnEscape) }
  }, [])

  if (!loading && user) return <Navigate replace to="/dashboard/"/>
  return <div className="lp-page">
    <a className="lp-skip-link" href="#main-content">Skip to content</a>
    <header className="lp-header"><nav className="lp-nav" aria-label="Primary navigation">
      <Logo/>
      <div className="lp-nav-links"><a href="#features">Features</a><a href="#how-it-works">How it works</a><a href="#questions">FAQs</a></div>
      <div className="lp-nav-actions"><Link to="/accounts/login/" className="lp-login">Log in</Link><Link to="/accounts/signup/" className="lp-button lp-button-dark lp-nav-cta">Get started free</Link><button className="lp-menu-toggle" type="button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="lp-mobile-nav" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={22}/> : <Menu size={22}/>}</button></div>
      {menuOpen && <div className="lp-mobile-nav" id="lp-mobile-nav"><a href="#features" onClick={() => setMenuOpen(false)}>Features</a><a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a><a href="#questions" onClick={() => setMenuOpen(false)}>FAQs</a><Link to="/accounts/login/">Log in</Link></div>}
    </nav></header>

    <main id="main-content">
      <section className="lp-hero" aria-labelledby="lp-hero-title">
        <div className="lp-hero-light" aria-hidden="true"/>
        <div className="lp-hero-copy"><span className="lp-intro-pill"><span><Zap size={13} fill="currentColor"/></span>A little less life admin.</span>
          <h1 id="lp-hero-title">Less managing.<br/><span>More living.</span></h1>
          <p>All your subscriptions. One clear picture.<br className="lp-desktop-break"/> Meet the calmer way to stay on top of what you pay for.</p>
          <div className="lp-hero-actions"><Link className="lp-button lp-button-lime" to="/accounts/signup/">Find your clarity. It’s free.</Link><a className="lp-button lp-button-glass" href="#preview"><LayoutGrid size={16}/>Take a look inside</a></div>
          <div className="lp-hero-assurances"><span><Check size={13}/>Free to use</span><span><Check size={13}/>No credit card needed</span></div>
        </div>
        <ProductPreview/>
      </section>

      <section className="lp-services-section" aria-label="Track the services you use"><p>For everything you’re subscribed to.<br className="lp-mobile-break"/> And everything you might have forgotten.</p><div className="lp-service-logos">{[{ service: 'spotify', name: 'Spotify' }, { service: 'netflix', name: 'NETFLIX' }, { service: 'figma', name: 'Figma' }, { service: 'icloud', name: 'iCloud' }, { service: 'notion', name: 'Notion' }, { service: 'youtube', name: 'YouTube' }].map(({ service, name }) => <div key={service}><LandingServiceIcon service={service as Service}/><span>{name}</span></div>)}</div></section>

      <section className="lp-section lp-features" id="features" aria-labelledby="lp-features-title">
        <div className="lp-section-heading"><span className="lp-eyebrow">A PLACE FOR EVERYTHING</span><h2 id="lp-features-title">A little clarity.<br/><span>A lot more headspace.</span></h2><p>Less digging through statements. Less doing the math.<br/>More knowing exactly where you stand.</p></div>
        <div className="lp-feature-grid">
          <article className="lp-feature-card lp-spending-card"><div className="lp-feature-text"><span className="lp-feature-icon"><ChartNoAxesCombined size={21}/></span><h3>The big picture.<br/>Down to the last subscription.</h3><p>See your recurring spend, spot what’s changed, and make room for what matters.</p></div><div className="lp-feature-spend"><div><span>Your monthly picture</span><span className="lp-example-label">Example</span></div><strong>$84.47<span> / month</span></strong><SpendingChart large/><div className="lp-category-legend"><span><i/>Entertainment</span><span><i/>Productivity</span><span><i/>Storage</span></div></div></article>
          <article className="lp-feature-card lp-reminder-card"><span className="lp-feature-icon"><Bell size={21}/></span><h3>Renewals.<br/>Without the surprises.</h3><p>A timely nudge before your next payment, trial ending, or cancellation deadline.</p><div className="lp-reminder-visual"><div className="lp-reminder-halo"/><div className="lp-reminder-bell"><Bell size={37} strokeWidth={1.5}/><span/></div><div className="lp-reminder-toast"><LandingServiceIcon service="netflix"/><div><strong>Netflix renews soon</strong><span>Nov 24 · $15.49</span></div><Check size={16}/></div></div></article>
          <article className="lp-feature-card lp-sharing-card"><span className="lp-feature-icon"><UsersRound size={21}/></span><h3>Shared plans.<br/>Everyone on the same page.</h3><p>Split costs, track repayments, and keep the “who owes what?” out of the group chat.</p><div className="lp-sharing-visual"><div className="lp-avatar-group"><span>J</span><span>A</span><span>M</span><span>+1</span></div><div className="lp-split-line"><span>One shared workspace</span><span><UsersRound size={14}/>All together</span></div></div></article>
          <article className="lp-feature-card lp-control-card"><div><span className="lp-feature-icon"><SlidersHorizontal size={21}/></span><h3>Your subscriptions.<br/>Your call.</h3><p>Review what you use, plan your budget, and keep the things that earn their place.</p></div><div className="lp-review-visual"><div><LandingServiceIcon service="figma"/><span><strong>Figma</strong><small>Last reviewed 6 months ago</small></span><span className="lp-review-tag">Time to review</span></div><div><LandingServiceIcon service="spotify"/><span><strong>Spotify</strong><small>Usage checked this month</small></span><span className="lp-keep-tag"><Check size={13}/>A keeper</span></div></div></article>
        </div>
      </section>

      <section className="lp-section lp-how-section" id="how-it-works" aria-labelledby="lp-how-title"><div className="lp-how-intro"><span className="lp-eyebrow">LESS SETUP. MORE SORTED.</span><h2 id="lp-how-title">From scattered<br/>to settled.</h2><p>A few minutes to get started.<br/>A little less to think about every day.</p><Link className="lp-text-link" to="/accounts/signup/">Make yourself at home</Link></div><div className="lp-steps"><article><span><Plus size={23}/></span><div><h3>Bring your subscriptions together.</h3><p>Add your favorites in a few fields, or import a CSV to get everything in one place.</p></div></article><article><span><Search size={23}/></span><div><h3>See where your money goes.</h3><p>Explore your spending, upcoming renewals, and shared costs. No spreadsheet required.</p></div></article><article><span><Sparkles size={23}/></span><div><h3>Give yourself some breathing room.</h3><p>Set reminders and budgets. Keep the subscriptions you love, and review the rest.</p></div></article></div></section>

      <section className="lp-free-section" aria-labelledby="lp-free-title"><div className="lp-free-glow" aria-hidden="true"/><div className="lp-free-copy"><span className="lp-eyebrow">ONE LESS SUBSCRIPTION TO THINK ABOUT</span><h2 id="lp-free-title">A subscription manager.<br/>Without the subscription.</h2><p>Clarity shouldn’t come with another monthly payment.<br/>Subly is free, for you and your team.</p><Link to="/accounts/signup/" className="lp-button lp-button-lime">Get started free</Link></div><div className="lp-free-card"><span className="lp-free-badge"><Sparkles size={14}/>The full picture</span><div className="lp-price">$0<span> / forever</span></div><p>Everything you need. Room to breathe.</p><ul>{['All your subscriptions in one place', 'Renewal reminders and spending insights', 'Shared workspaces and cost splitting', 'Budgets, calendar, and CSV import'].map(item => <li key={item}><Check size={16}/>{item}</li>)}</ul><span className="lp-free-footnote">No payment details. No ticking trial.</span></div></section>

      <section className="lp-section lp-faq-section" id="questions" aria-labelledby="lp-faq-title"><div><span className="lp-eyebrow">GOOD TO KNOW</span><h2 id="lp-faq-title">A few things<br/>you might be wondering.</h2><CircleHelp className="lp-faq-decoration" size={44} strokeWidth={1}/></div><div className="lp-faq-list">{faqs.map(([question, answer], index) => <article className={`lp-faq ${openFaq === index ? 'is-open' : ''}`} key={question}><h3><button type="button" onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index} aria-controls={`lp-answer-${index}`} id={`lp-question-${index}`}>{question}<Plus size={19}/></button></h3><div id={`lp-answer-${index}`} role="region" aria-labelledby={`lp-question-${index}`} hidden={openFaq !== index}><p>{answer}</p></div></article>)}</div></section>

      <section className="lp-final-cta"><span className="lp-final-mark"><Zap size={30} fill="currentColor"/></span><h2>Less on your mind.<br/><span>More life in your day.</span></h2><Link to="/accounts/signup/" className="lp-button lp-button-dark">Find your clarity. It’s free.</Link><p>For the subscriptions you keep. And the headspace you get back.</p></section>
    </main>
    <footer className="lp-footer"><div><Logo/><span>A little less life admin.</span></div><p>© {new Date().getFullYear()} Subly</p><div><a href="#features">Features</a><a href="#questions">FAQs</a><Link to="/accounts/login/">Log in</Link></div></footer>
  </div>
}
