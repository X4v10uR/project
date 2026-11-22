import { useEffect, useState, type ReactNode } from 'react'
import {
  Bell, CalendarDays, ChartNoAxesCombined, Check, ChevronDown, CreditCard,
  LayoutGrid, Menu, Pause, Play, Plus, ShieldCheck, Smile, Sparkles, UsersRound, X, Zap,
} from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { ServiceIcon } from '../ServiceIcon'
import { useAuth } from '../accounts'
import './landing.css'

function Logo() {
  return <Link className="lp-logo" to="/" aria-label="Subly home"><Zap fill="currentColor" strokeWidth={2.5} aria-hidden="true"/>subly<span>.</span></Link>
}

function Sticker({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`lp-sticker ${className}`}>{children}</span>
}

type LandingService = { name: string; label: string; brand: string; wordmark?: string; suffix?: string }

const landingServices: LandingService[] = [
  { name: 'Spotify', label: 'Spotify', brand: 'spotify' },
  { name: 'Netflix', label: 'NETFLIX', brand: 'netflix' },
  { name: 'Paramount+', label: 'Paramount+', brand: 'paramount' },
  { name: 'Prime Video', label: 'Prime Video', brand: 'prime-video', wordmark: 'service-icons/prime-video.svg' },
  { name: 'Apple TV+', label: 'Apple TV+', brand: 'apple-tv', wordmark: 'service-marks/apple-tv.svg', suffix: '+' },
  { name: 'Disney+', label: 'Disney+', brand: 'disney', wordmark: 'service-icons/disney-plus.svg' },
  { name: 'Hulu', label: 'hulu', brand: 'hulu', wordmark: 'service-marks/hulu.svg' },
  { name: 'HBO Max', label: 'HBO Max', brand: 'hbo-max', wordmark: 'service-marks/hbo.svg', suffix: 'Max' },
  { name: 'Peacock', label: 'Peacock', brand: 'peacock', wordmark: 'service-icons/peacock.svg' },
  { name: 'Crunchyroll', label: 'Crunchyroll', brand: 'crunchyroll' },
  { name: 'Figma', label: 'Figma', brand: 'figma' },
  { name: 'Notion', label: 'Notion', brand: 'notion' },
  { name: 'iCloud', label: 'iCloud', brand: 'icloud' },
  { name: 'YouTube', label: 'YouTube', brand: 'youtube' },
]

function ServicesMarquee() {
  const [paused, setPaused] = useState(false)
  const MotionIcon = paused ? Play : Pause

  return <section className="lp-services-section" aria-label="Track the services you use">
    <div className="lp-divider-label"><span/>ALL YOUR FAVORITES. EVEN THE ONES YOU FORGOT.<span/><button className="lp-marquee-control" type="button" aria-label={paused ? 'Play logo animation' : 'Pause logo animation'} onClick={() => setPaused(!paused)}><MotionIcon size={13} aria-hidden="true"/></button></div>
    <div className="lp-service-marquee">
      <div className={`lp-service-track${paused ? ' is-paused' : ''}`}>
        {[0, 1].map(copy => <div className="lp-service-logo-group" key={copy} aria-hidden={copy === 1 ? true : undefined}>
          {landingServices.map(service => <div className={`lp-service-logo lp-service-logo-${service.brand}`} key={service.name}>
            {service.wordmark ? <>
              <img className="lp-service-wordmark" src={`${import.meta.env.BASE_URL}${service.wordmark}`} alt="" draggable={false}/>
              {service.suffix && <span className="lp-service-wordmark-suffix" aria-hidden="true">{service.suffix}</span>}
              <span className="sr-only">{service.name}</span>
            </> : <><ServiceIcon name={service.name}/><span>{service.label}</span></>}
          </div>)}
        </div>)}
      </div>
    </div>
  </section>
}

const personal = [
  { name: 'Spotify', plan: 'Premium Individual', amount: 11.99, day: 22 },
  { name: 'Netflix', plan: 'Standard', amount: 15.49, day: 24 },
  { name: 'iCloud+', plan: '200 GB storage', amount: 2.99, day: 28 },
  { name: 'Figma', plan: 'Professional', amount: 12, day: 29 },
  { name: 'Notion', plan: 'Plus', amount: 10, day: 30 },
]
const shared = [
  { name: 'Figma', plan: 'Professional · 3 people', amount: 45, day: 21 },
  { name: 'Notion', plan: 'Plus · 3 people', amount: 30, day: 25 },
  { name: 'Spotify', plan: 'Duo · 2 people', amount: 16.99, day: 29 },
]

function MiniChart() {
  return <div className="lp-mini-chart" aria-label="Illustrative monthly spending" role="img">
    {[38, 54, 43, 69, 59, 81, 71, 62, 88, 76, 64, 53].map((height, index) => <span key={index} style={{ height: `${height}%` }}/>)}
  </div>
}

function ProductPreview() {
  const [workspace, setWorkspace] = useState<'personal' | 'shared'>('personal')
  const [view, setView] = useState<'overview' | 'calendar'>('overview')
  const [yearly, setYearly] = useState(false)
  const services = workspace === 'personal' ? personal : shared
  const total = services.reduce((sum, service) => sum + service.amount, 0)

  return <div className="lp-demo" id="preview">
    <div className="lp-demo-top"><Logo/><span className="lp-demo-tag">Interactive demo</span><span className="lp-demo-avatar">J</span></div>
    <div className="lp-demo-body">
      <div className="lp-demo-greeting"><span>YOUR MONEY, AT A GLANCE</span><h3>Hey Jamie, you’re all set<span>✳</span></h3></div>
      <div className="lp-demo-toolbar">
        <div className="lp-segment" aria-label="Demo workspace"><button type="button" aria-pressed={workspace === 'personal'} onClick={() => setWorkspace('personal')}>Personal</button><button type="button" aria-pressed={workspace === 'shared'} onClick={() => setWorkspace('shared')}>Shared</button></div>
        <span className="lp-demo-month">November 2026</span>
      </div>
      <div className="lp-demo-view" aria-live="polite" aria-atomic="true">
        {view === 'overview' ? <>
          <div className="lp-demo-stats"><div><button className="lp-period" type="button" onClick={() => setYearly(!yearly)} aria-label={`Show ${yearly ? 'monthly' : 'yearly'} spending`}>{yearly ? 'Yearly' : 'Monthly'} spending<ChevronDown size={13}/></button><strong>${(total * (yearly ? 12 : 1)).toFixed(2)}<small>/{yearly ? 'yr' : 'mo'}</small></strong><span>Every little thing, accounted for.</span></div><div><span>Active subscriptions</span><strong>{services.length}<small>services</small></strong><div className="lp-demo-service-stack">{services.slice(0, 4).map(service => <ServiceIcon key={service.name} name={service.name}/>)}</div></div></div>
          <MiniChart/>
        </> : <div className="lp-demo-calendar"><div className="lp-weekdays">{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => <span key={index}>{day}</span>)}</div><div className="lp-days">{Array.from({ length: 6 }, (_, index) => <span key={`blank-${index}`}/>)}{Array.from({ length: 30 }, (_, index) => <span className={services.some(service => service.day === index + 1) ? 'lp-calendar-charge' : ''} key={index}>{index + 1}</span>)}</div></div>}
        <div className="lp-demo-table-title"><strong>Upcoming renewals</strong><span>Example data · USD</span></div>
        <div className="lp-demo-table">{services.slice(0, 3).map(service => <div className="lp-demo-row" key={service.name}><ServiceIcon name={service.name}/><div><strong>{service.name}</strong><span>{service.plan}</span></div><span className="lp-renewal-date">Nov {service.day}</span><strong>${service.amount.toFixed(2)}</strong></div>)}</div>
      </div>
      <nav className="lp-demo-dock" aria-label="Demo views"><button type="button" onClick={() => setView('overview')} aria-pressed={view === 'overview'}><LayoutGrid size={15}/>Overview</button><button type="button" onClick={() => setView('calendar')} aria-pressed={view === 'calendar'}><CalendarDays size={15}/>Calendar</button><Link to="/accounts/signup/" aria-label="Create an account to add a subscription"><Plus size={17}/></Link></nav>
    </div>
  </div>
}

function ReminderPreview() {
  return <div className="lp-reminder-scene"><div className="lp-scene-caption">A HEADS-UP GOES A LONG WAY.</div><div className="lp-bell-art"><Bell size={100} strokeWidth={1.3}/><span>3</span></div><div className="lp-notification"><span className="lp-notification-app"><Zap size={14} fill="currentColor"/>SUBLY<span>now</span></span><strong>Tomorrow’s looking a little Netflix.</strong><p>Your $15.49 renewal is coming up. Still a keeper?</p><div><ServiceIcon name="Netflix"/><span>Netflix · Standard</span><span>Nov 24</span></div></div><span className="lp-scene-footnote">Illustrative reminder · Renewals, trials, and deadlines.</span></div>
}

function SpendingPreview() {
  return <div className="lp-spending-scene"><div className="lp-report-heading"><span>THE BIG PICTURE</span><ChartNoAxesCombined size={22}/></div><h3>Know where it all goes.</h3><div className="lp-report-card"><div><span>Monthly commitment</span><span className="lp-example">Example · USD</span></div><strong>$52.47<span>/mo</span></strong><div className="lp-spend-categories"><i/><i/><i/></div><div className="lp-category-row"><span><i/>Entertainment</span><strong>$27.48</strong></div><div className="lp-category-row"><span><i/>Productivity</span><strong>$22.00</strong></div><div className="lp-category-row"><span><i/>Storage</span><strong>$2.99</strong></div></div><div className="lp-report-bottom"><span><Check size={16}/>A budget for every currency.</span><span>No mental math required.</span></div></div>
}

function SharingPreview() {
  return <div className="lp-sharing-scene"><div className="lp-sharing-heading"><span>GOOD THINGS ARE BETTER SHARED.</span><UsersRound size={22}/></div><div className="lp-team-avatars"><span>J</span><span>A</span><span>M</span><span>+</span></div><div className="lp-split-card"><div className="lp-split-heading"><ServiceIcon name="Figma"/><div><strong>The studio’s Figma</strong><span>Professional · $45.00 / month</span></div></div>{[{ name: 'Jamie', initial: 'J', status: 'Paid' }, { name: 'Alex', initial: 'A', status: 'Repaid' }, { name: 'Morgan', initial: 'M', status: 'Owes $15.00' }].map(person => <div className="lp-person-row" key={person.name}><span>{person.initial}</span><strong>{person.name}</strong><span>$15.00</span><span className={person.status.startsWith('Owes') ? 'lp-owed' : 'lp-paid'}>{person.status}</span></div>)}</div><span className="lp-scene-footnote">Example split. Everybody knows where they stand.</span></div>
}

const faqs = [
  ['Is Subly really free?', 'Yes. Subscription tracking, reminders, budgets, planning tools, and shared workspaces are all free. You don’t need a payment card to create an account.'],
  ['Do I have to connect my bank?', 'No. Add a subscription in a few fields or import a CSV. You can use Subly without connecting a bank account.'],
  ['Can I track different currencies?', 'Yes. Subly keeps subscriptions, budgets, and spending separated by currency. Combined totals are also available in Planning when exchange rates are configured.'],
  ['Can I use it with my team?', 'Yes. Create a team, invite members, split subscription costs, and record payments and repayments. Everyone can keep track of their share.'],
  ['Will Subly cancel a subscription for me?', 'Subly helps you review subscriptions, remember deadlines, and record cancellation requests. You’ll still cancel or pause the subscription directly with its provider.'],
]

export function LandingPage() {
  const { user, loading } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState<number | null>(0)

  useEffect(() => {
    const previousTitle = document.title
    document.title = 'Subly — Small subscriptions. Big picture.'
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.title = previousTitle; document.removeEventListener('keydown', closeOnEscape) }
  }, [])

  if (!loading && user) return <Navigate replace to="/dashboard/"/>

  return <div className="lp-page" id="top">
    <a className="lp-skip-link" href="#main-content">Skip to content</a>
    <header className="lp-header"><nav className="lp-nav" aria-label="Primary navigation"><Logo/><div className="lp-nav-links"><a href="#features">The good stuff</a><a href="#how-it-works">How it works</a><a href="#pricing">Pricing</a></div><div className="lp-nav-actions"><Link className="lp-login" to="/accounts/login/">Log in</Link><Link className="lp-button lp-button-dark" to="/accounts/signup/">Get started free<Plus size={15}/></Link><button className="lp-menu-toggle" type="button" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="lp-mobile-nav">{menuOpen ? <X/> : <Menu/>}</button></div>{menuOpen && <div className="lp-mobile-nav" id="lp-mobile-nav"><a href="#features" onClick={() => setMenuOpen(false)}>The good stuff</a><a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a><a href="#pricing" onClick={() => setMenuOpen(false)}>Pricing</a><a href="#questions" onClick={() => setMenuOpen(false)}>FAQs</a><Link to="/accounts/login/">Log in</Link></div>}</nav></header>

    <main id="main-content">
      <section className="lp-hero" aria-labelledby="lp-hero-title"><div className="lp-hero-pill"><span/>Less life admin. More living.<span className="lp-pill-divider"/><a href="#preview">Meet Subly<Plus size={13}/></a></div><div className="lp-hero-headline"><h1 id="lp-hero-title">SMALL SUBSCRIPTIONS.<br/>BIG PICTURE.</h1><Sticker className="lp-sticker-orange lp-hero-sticker">Get your money’s worth</Sticker><span className="lp-smile-sticker" aria-hidden="true"><Smile strokeWidth={1.65}/></span><span className="lp-starburst" aria-label="100 percent free"><span>100%<small>FREE. REALLY.</small></span></span><Sticker className="lp-sticker-pink lp-hero-sticker-right">A little more in control.</Sticker></div><p>All your subscriptions, spending, and renewals in one happy place.<br className="lp-desktop-break"/> Less “wait, I’m still paying for that?” More peace of mind.</p><div className="lp-hero-actions"><Link className="lp-button lp-button-dark" to="/accounts/signup/">Get my subscriptions together<Plus size={16}/></Link><a className="lp-button lp-button-outline" href="#preview">Take a look inside</a></div><span className="lp-hero-note">Free to use. No credit card. No extra subscription.</span></section>

      <ServicesMarquee/>

      <section className="lp-showcase lp-container" id="features" aria-labelledby="lp-features-title"><div className="lp-showcase-heading"><h2 id="lp-features-title">A PLACE FOR EVERY PAYMENT.</h2><span>A little order. A lot of headspace.</span></div><div className="lp-showcase-grid"><article className="lp-showcase-card"><div className="lp-showcase-visual lp-dashboard-visual"><ProductPreview/></div><div className="lp-card-caption"><h3>Everything. Together.</h3><span>Your dashboard</span></div></article><article className="lp-showcase-card"><div className="lp-showcase-visual"><ReminderPreview/></div><div className="lp-card-caption"><h3>Heads-up. Always.</h3><span>Renewal reminders</span></div></article><article className="lp-showcase-card"><div className="lp-showcase-visual"><SpendingPreview/></div><div className="lp-card-caption"><h3>See the bigger picture.</h3><span>Spending & budgets</span></div></article><article className="lp-showcase-card"><div className="lp-showcase-visual"><SharingPreview/></div><div className="lp-card-caption"><h3>Share the good stuff.</h3><span>Teams & cost splitting</span></div></article></div><div className="lp-showcase-cta"><a href="#how-it-works" className="lp-button lp-button-outline">Sounds good. How does it work?<Plus size={15}/></a></div></section>

      <section className="lp-manifesto lp-container"><div><span className="lp-eyebrow">SOUND FAMILIAR?</span><span className="lp-manifesto-scribble" aria-hidden="true">a little too<br/>familiar?</span></div><div><h2>“It’s only a few dollars<br/>a month.”<br/><span>Until it’s a few dollars.<br/>Everywhere.</span></h2><p>Your music. Your movies. That app you used once. <br/>Subly brings it all into focus, so you can decide what stays.</p></div></section>

      <div className="lp-dark-section"><section className="lp-about lp-container" aria-labelledby="lp-about-title"><div><span className="lp-eyebrow">LESS MESS. MORE YES.</span><span className="lp-about-mark" aria-hidden="true"><Zap fill="currentColor" strokeWidth={1.5}/></span></div><div><h2 id="lp-about-title">Life’s too good to spend it<br/>managing subscriptions.<br/><span>Keep what you love.<br/>Know what you pay.<br/>Make room for the rest.</span></h2><div className="lp-about-facts"><span><ShieldCheck size={17}/>Your space. Your decisions.</span><span><UsersRound size={17}/>For you and your people.</span><span><CreditCard size={17}/>No bank connection required.</span><span><Sparkles size={17}/>One less thing on your mind.</span></div></div></section>

      <section className="lp-process lp-container" id="how-it-works" aria-labelledby="lp-process-title"><div className="lp-dark-heading"><span className="lp-eyebrow">A LITTLE SETUP. A LOT MORE SORTED.</span><h2 id="lp-process-title">GET TOGETHER.<br/>GET ON WITH LIFE.</h2></div><div className="lp-process-cards"><article className="lp-process-card lp-step-lime"><Plus size={29}/><div><h3>BRING IT IN.</h3><p>Add a subscription in a few fields, or bring your list with a CSV import.</p></div><Sticker className="lp-sticker-orange">Your favorites, all here</Sticker></article><article className="lp-process-card lp-step-pink"><ChartNoAxesCombined size={29}/><div><h3>SEE IT CLEAR.</h3><p>Your spending, your budgets, your next payment. Finally, the full picture.</p></div></article><article className="lp-process-card lp-step-blue"><Bell size={29}/><div><h3>STAY AHEAD.</h3><p>Set a reminder before a renewal, a trial ending, or a cancel-by date.</p></div><span className="lp-step-spark" aria-hidden="true">✳</span></article><article className="lp-process-card lp-step-orange"><UsersRound size={29}/><div><h3>SPLIT IT FAIR.</h3><p>Invite your people. Share the cost. Keep the “who owes what?” in one place.</p></div><Sticker className="lp-sticker-blue">Everybody’s in.</Sticker></article></div></section>

      <section className="lp-pricing lp-container" id="pricing" aria-labelledby="lp-pricing-title"><div className="lp-pricing-heading"><span className="lp-eyebrow">ONE LESS BILL. YOU’RE WELCOME.</span><h2 id="lp-pricing-title">A subscription manager.<br/>Without the subscription.</h2></div><div className="lp-pricing-grid"><div className="lp-pricing-side"><span className="lp-pricing-icon"><LayoutGrid size={29}/></span><h3>FOR YOUR EVERYDAY.</h3><p>From your morning playlist to your late-night watchlist. Get a handle on every recurring payment.</p><ul><li><Check/>Track plans in different currencies</li><li><Check/>See upcoming renewals</li><li><Check/>Set budgets and review spending</li></ul></div><div className="lp-price-card"><Sticker className="lp-sticker-lime">The whole good thing</Sticker><span className="lp-eyebrow">THE SUBLY PLAN</span><div className="lp-price">$0<span>Free to use.</span></div><p>All the clarity. None of the monthly bill.</p><ul>{['All your subscriptions in one place', 'Renewal and trial reminders', 'Spending insights and budgets', 'Shared teams and cost splitting', 'CSV imports and calendar exports'].map(item => <li key={item}><Check size={16}/>{item}</li>)}</ul><Link className="lp-button lp-button-dark" to="/accounts/signup/">Count me in<Plus size={16}/></Link><small>No credit card needed.</small></div><div className="lp-pricing-side"><span className="lp-pricing-icon"><UsersRound size={29}/></span><h3>FOR YOUR PEOPLE.</h3><p>Roommates, family, or your work crew. Bring shared subscriptions out of the group chat.</p><ul><li><Check/>Create a shared workspace</li><li><Check/>Keep track of everyone’s share</li><li><Check/>Record payments and repayments</li></ul></div></div></section>

      <section className="lp-faq-section lp-container" id="questions" aria-labelledby="lp-faq-title"><div><span className="lp-eyebrow">A LITTLE MORE CLARITY</span><h2 id="lp-faq-title">GOOD<br/>QUESTIONS.</h2></div><div className="lp-faq-list">{faqs.map(([question, answer], index) => <article className="lp-faq" key={question}><h3><button type="button" onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index} aria-controls={`lp-answer-${index}`} id={`lp-question-${index}`}>{question}<Plus size={19}/></button></h3><div id={`lp-answer-${index}`} role="region" aria-labelledby={`lp-question-${index}`} hidden={openFaq !== index}><p>{answer}</p></div></article>)}</div></section></div>

      <section className="lp-final-cta" aria-labelledby="lp-final-title"><Sticker className="lp-sticker-orange">Your money. Your call.</Sticker><h2 id="lp-final-title">GET IT TOGETHER.</h2><span className="lp-final-star" aria-hidden="true">✦</span><div><p>Less subscription chaos. More room for life.</p><Link className="lp-button lp-button-dark" to="/accounts/signup/">Let’s do this. It’s free.<Plus size={17}/></Link></div><Sticker className="lp-sticker-lime">Feels good to be in control.</Sticker></section>
    </main>

    <footer className="lp-footer"><div className="lp-footer-top lp-container"><div><Logo/><p>Small subscriptions.<br/>Big picture.</p></div><div><span className="lp-eyebrow">TAKE A LOOK</span><a href="#features">The good stuff</a><a href="#how-it-works">How it works</a><a href="#pricing">Free. Really.</a></div><div><span className="lp-eyebrow">MAKE YOURSELF AT HOME</span><Link to="/accounts/signup/">Create an account</Link><Link to="/accounts/login/">Log in</Link><a href="#questions">Good questions</a></div><div className="lp-footer-note"><Smile size={34} strokeWidth={1.5}/><span>A little less life admin.<br/>A little more living.</span></div></div><div className="lp-footer-bottom lp-container"><span>© {new Date().getFullYear()} Subly</span><span>Made for a little peace of mind.</span><a href="#top">Back to top</a></div></footer>
  </div>
}
