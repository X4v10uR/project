import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Bell, CalendarDays, ChartNoAxesCombined, Check, ChevronDown, Mail, Plus, RotateCcw, UsersRound, X, Zap } from 'lucide-react'
import { ServiceIcon } from '../ServiceIcon'
import { demoPeople, LandingAvatar } from './LandingAvatar'
import './product-demo.css'

const presets = [
  { name: 'Netflix', amount: 15.49, category: 'Entertainment', color: '#ef6868', days: 7 },
  { name: 'iCloud+', amount: 2.99, category: 'Storage', color: '#67b5de', days: 9 },
  { name: 'Spotify', amount: 11.99, category: 'Entertainment', color: '#63bca4', days: 11 },
  { name: 'Notion', amount: 10, category: 'Productivity', color: '#9b91cb', days: 14 },
] as const

type DemoSubscription = { name: string; amount: number; annual: boolean; category: string; color: string; days: number }
type DemoStep = 'add' | 'reminders' | 'explore'
type DemoView = 'budget' | 'calendar' | 'sharing'
type EmailPreview = { subscription: DemoSubscription; days: number }

const steps = [
  { id: 'add', label: 'Add a subscription', detail: 'Start with a favorite', icon: Plus },
  { id: 'reminders', label: 'Set a reminder', detail: 'Meet your next heads-up', icon: Bell },
  { id: 'explore', label: 'See the bigger picture', detail: 'Make it all add up', icon: ChartNoAxesCombined },
] as const
const initialSubscriptions = (): DemoSubscription[] => [{ ...presets[2], annual: false }]
const money = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
const monthlyCost = (subscription: DemoSubscription) => subscription.amount / (subscription.annual ? 12 : 1)

function renewalDate(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date
}

function dateLabel(days: number) {
  return renewalDate(days).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function ProductDemo() {
  const [step, setStep] = useState<DemoStep>('add')
  const [selected, setSelected] = useState<string>('Netflix')
  const [amount, setAmount] = useState('15.49')
  const [annual, setAnnual] = useState(false)
  const [subscriptions, setSubscriptions] = useState<DemoSubscription[]>(initialSubscriptions)
  const [reminderService, setReminderService] = useState('Netflix')
  const [reminderDays, setReminderDays] = useState(3)
  const [email, setEmail] = useState<EmailPreview | null>(null)
  const [view, setView] = useState<DemoView>('budget')
  const [budget, setBudget] = useState(50)
  const [people, setPeople] = useState(3)
  const [notice, setNotice] = useState('')
  const controlsRef = useRef<HTMLDivElement>(null)
  const previewRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (controlsRef.current) controlsRef.current.scrollTop = 0
  }, [step, view])

  useEffect(() => {
    if (previewRef.current) previewRef.current.scrollTop = 0
  }, [step, view, email])

  const total = subscriptions.reduce((sum, subscription) => sum + monthlyCost(subscription), 0)
  const currentService = subscriptions.find(subscription => subscription.name === reminderService) ?? subscriptions[0]
  const sharedCents = Math.round((currentService?.amount ?? 0) * 100)
  const shareCents = Math.floor(sharedCents / people)
  const extraCents = sharedCents % people
  const alreadyAdded = subscriptions.some(subscription => subscription.name === selected)
  const validAmount = amount.trim() !== '' && Number.isFinite(Number(amount)) && Number(amount) >= 0 && Number(amount) <= 9999
  const currentStep = steps.find(item => item.id === step)!

  function choosePreset(preset: (typeof presets)[number]) {
    setSelected(preset.name)
    setAmount(preset.amount.toFixed(2))
    setAnnual(false)
    setNotice('')
  }

  function addSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (alreadyAdded || !validAmount) return
    const preset = presets.find(item => item.name === selected)!
    setSubscriptions(current => [...current, { ...preset, amount: Number(amount), annual }])
    setReminderService(selected)
    setEmail(null)
    setNotice(`${selected} added. Your monthly total is now ${money(total + Number(amount) / (annual ? 12 : 1))}.`)
  }

  function removeSubscription(name: string) {
    setSubscriptions(current => current.filter(subscription => subscription.name !== name))
    if (email?.subscription.name === name) setEmail(null)
    setNotice(`${name} removed from the demo.`)
  }

  function reset() {
    setStep('add')
    setSelected('Netflix')
    setAmount('15.49')
    setAnnual(false)
    setSubscriptions(initialSubscriptions())
    setReminderService('Netflix')
    setReminderDays(3)
    setEmail(null)
    setView('budget')
    setBudget(50)
    setPeople(3)
    setNotice('Demo reset. Try adding a subscription.')
  }

  return <section className="lv-demo lv-container" id="how-it-works" aria-labelledby="lv-demo-title">
    <div className="lv-demo-heading" id="product-demo">
      <div><span className="lv-eyebrow">A LITTLE LESS GUESSWORK. A LITTLE MORE HANDS-ON.</span><h2 id="lv-demo-title">Give your subscriptions<br/>a little order.</h2></div>
      <p>Add a plan. Try a reminder. See the full picture.<br/>Take DUES for a spin, no sign-up needed.</p>
    </div>

    <div className="lv-demo-shell" id="preview">
      <div className="lv-demo-toolbar"><span className="lv-demo-wordmark"><Zap size={17} fill="currentColor" aria-hidden="true"/>DUES<span>/ Product demo</span></span><button type="button" onClick={reset}><RotateCcw size={14} aria-hidden="true"/>Start over</button></div>
      <div className="lv-demo-steps" role="group" aria-label="Product demo steps">
        {steps.map(item => {
          const Icon = item.icon
          return <button type="button" key={item.id} aria-pressed={step === item.id} aria-controls="lv-demo-panel" onClick={() => { setStep(item.id); setNotice('') }}>
            <span className="lv-demo-step-icon"><Icon size={20} aria-hidden="true"/></span><span><strong>{item.label}</strong><small>{item.detail}</small></span>
          </button>
        })}
      </div>

      <div className="lv-demo-body" id="lv-demo-panel" role="region" aria-label={currentStep.label}>
        <div className="lv-demo-controls" ref={controlsRef} data-lenis-prevent>
          {step === 'add' && <>
            <div className="lv-demo-copy"><span className="lv-demo-kicker">YOUR LIST STARTS HERE</span><h3>A few favorites?</h3><p>Pick a service and add what you pay. We’ve added Spotify to get you started.</p></div>
            <div className="lv-demo-presets" role="group" aria-label="Choose a sample subscription">
              {presets.map(preset => <button type="button" key={preset.name} aria-pressed={selected === preset.name} onClick={() => choosePreset(preset)}><ServiceIcon name={preset.name}/><span>{preset.name}</span>{subscriptions.some(item => item.name === preset.name) && <Check size={14} aria-label="Added"/>}</button>)}
            </div>
            <form onSubmit={addSubscription} className="lv-demo-form">
              <div className="lv-demo-field-row">
                <label>Cost (USD)<span className="lv-demo-cost"><span aria-hidden="true">$</span><input aria-label="Subscription cost in USD" type="number" min="0" max="9999" step="0.01" required value={amount} onChange={event => setAmount(event.target.value)}/></span></label>
                <label>Billing cycle<span className="lv-demo-select"><select value={annual ? 'yearly' : 'monthly'} onChange={event => setAnnual(event.target.value === 'yearly')}><option value="monthly">Monthly</option><option value="yearly">Yearly</option></select><ChevronDown size={15} aria-hidden="true"/></span></label>
              </div>
              <button className="lv-button lv-button-dark lv-demo-primary" disabled={alreadyAdded || !validAmount} type="submit">{alreadyAdded ? <><Check size={16} aria-hidden="true"/>Already in your list</> : <><Plus size={16} aria-hidden="true"/>Add {selected}</>}</button>
            </form>
            <button type="button" className="lv-demo-next" onClick={() => { setStep('reminders'); setNotice('') }}>Next, try a reminder</button>
          </>}

          {step === 'reminders' && <>
            <div className="lv-demo-copy"><span className="lv-demo-kicker">A HEADS-UP, RIGHT ON TIME</span><h3>Before the next bill.</h3><p>Choose a plan and when to get a reminder. Then take a peek at the email.</p></div>
            {currentService ? <>
              <label className="lv-demo-field">Subscription<span className="lv-demo-select"><select value={currentService.name} onChange={event => { setReminderService(event.target.value); setEmail(null) }}>{subscriptions.map(subscription => <option key={subscription.name}>{subscription.name}</option>)}</select><ChevronDown size={15} aria-hidden="true"/></span></label>
              <div className="lv-demo-delivery"><span className="lv-demo-delivery-icon"><Mail size={20} aria-hidden="true"/></span><div><strong>Email reminder</strong><span>you@example.com · Sample inbox</span></div><Check size={17} aria-label="Email selected"/></div>
              <label className="lv-demo-field">Remind me<span className="lv-demo-select"><select value={reminderDays} onChange={event => { setReminderDays(Number(event.target.value)); setEmail(null) }}>{[1, 3, 7].map(days => <option value={days} key={days}>{days} {days === 1 ? 'day' : 'days'} before renewal</option>)}</select><ChevronDown size={15} aria-hidden="true"/></span></label>
              <button className="lv-button lv-button-dark lv-demo-primary" type="button" onClick={() => { setEmail({ subscription: { ...currentService }, days: reminderDays }); setNotice(`Sample email ready for ${currentService.name}, ${reminderDays} ${reminderDays === 1 ? 'day' : 'days'} before renewal.`) }}><Bell size={16} aria-hidden="true"/>Remind me</button>
              <p className="lv-demo-hint">Just a preview. No email will be sent.</p>
              <button type="button" className="lv-demo-next" onClick={() => { setStep('explore'); setNotice('') }}>Next, explore your spending</button>
            </> : <div className="lv-demo-empty"><p>Add a subscription to try a renewal reminder.</p><button type="button" className="lv-button lv-button-dark" onClick={() => setStep('add')}>Add a plan</button></div>}
          </>}

          {step === 'explore' && <>
            <div className="lv-demo-copy"><span className="lv-demo-kicker">MORE CLARITY, LESS LIFE ADMIN</span><h3>It all comes together.</h3><p>The plans you add power your spending view, upcoming bills, and shared costs.</p></div>
            <div className="lv-demo-explore" role="group" aria-label="Explore demo features">
              {([{ id: 'budget', label: 'Spending & budgets', description: 'See where your money goes', icon: ChartNoAxesCombined }, { id: 'calendar', label: 'Upcoming renewals', description: 'Know what’s coming next', icon: CalendarDays }, { id: 'sharing', label: 'Shared costs', description: 'Split a plan with your people', icon: UsersRound }] as const).map(item => {
                const Icon = item.icon
                return <button type="button" key={item.id} aria-pressed={view === item.id} onClick={() => setView(item.id)}><Icon size={20} aria-hidden="true"/><span><strong>{item.label}</strong><small>{item.description}</small></span><span className="lv-demo-choice" aria-hidden="true">{view === item.id && <Check size={12}/>}</span></button>
              })}
            </div>
            {view === 'budget' && <label className="lv-demo-range">Monthly budget <strong>{money(budget)}</strong><input aria-label="Monthly budget in USD" type="range" min="10" max="100" step="5" value={budget} onChange={event => setBudget(Number(event.target.value))}/><span>Move the slider to find your comfort zone.</span></label>}
            {view === 'sharing' && currentService && <div className="lv-demo-sharing-controls"><label className="lv-demo-field">Shared subscription<span className="lv-demo-select"><select value={currentService.name} onChange={event => { setReminderService(event.target.value); setEmail(null) }}>{subscriptions.map(subscription => <option key={subscription.name}>{subscription.name}</option>)}</select><ChevronDown size={15} aria-hidden="true"/></span></label><label className="lv-demo-field">People, including you<span className="lv-demo-select"><select value={people} onChange={event => setPeople(Number(event.target.value))}>{[2, 3, 4, 5].map(count => <option value={count} key={count}>{count} people</option>)}</select><ChevronDown size={15} aria-hidden="true"/></span></label></div>}
          </>}
          <p className="lv-demo-status" role="status" aria-atomic="true">{notice}</p>
        </div>

        <div className={`lv-demo-preview lv-demo-preview-${step}`} ref={previewRef} role="region" aria-label="Live demo preview" tabIndex={0} data-lenis-prevent>
          <div className="lv-demo-preview-label"><span>{step === 'reminders' ? 'YOUR SAMPLE INBOX' : 'YOUR DUES, AT A GLANCE'}</span><span>Example data</span></div>
          {step === 'add' && <div className="lv-demo-dashboard">
            <div className="lv-demo-summary"><span>Monthly commitment</span><strong>{money(total)}</strong><small>{subscriptions.length} {subscriptions.length === 1 ? 'subscription' : 'subscriptions'} · {money(total * 12)} per year</small></div>
            <div className="lv-demo-list-heading"><strong>Your subscriptions</strong><span>{subscriptions.length} {subscriptions.length === 1 ? 'plan' : 'plans'}</span></div>
            <div className="lv-demo-subscriptions">{subscriptions.map(subscription => <div className="lv-demo-subscription" key={subscription.name}><ServiceIcon name={subscription.name}/><div><strong>{subscription.name}</strong><small>{subscription.category}</small></div><span><b>{money(subscription.amount)}</b><small>/{subscription.annual ? 'year' : 'month'}</small></span><button type="button" aria-label={`Remove ${subscription.name} from demo`} onClick={() => removeSubscription(subscription.name)}><X size={15} aria-hidden="true"/></button></div>)}</div>
            {subscriptions.length === 0 && <div className="lv-demo-empty"><Plus size={24} aria-hidden="true"/><p>A little space for your favorites.<br/>Add a plan to see it here.</p></div>}
            <div className="lv-demo-dashboard-note"><Check size={15} aria-hidden="true"/>One place for every recurring payment.</div>
          </div>}

          {step === 'reminders' && (email ? <article className="lv-demo-email" aria-label="Sample renewal email">
            <div className="lv-demo-email-meta"><span className="lv-demo-email-avatar"><Zap size={19} fill="currentColor" aria-hidden="true"/></span><div><strong>DUES <span>· Sample email</span></strong><small>To: you@example.com</small></div><Mail size={17} aria-hidden="true"/></div>
            <h4>{email.subscription.name} renews in {email.days} {email.days === 1 ? 'day' : 'days'}.</h4>
            <div className="lv-demo-email-content"><span className="lv-demo-email-brand">DUES.</span><p>Hey there,</p><p>A little heads-up: your <strong>{email.subscription.name}</strong> subscription is coming up for renewal.</p><div className="lv-demo-email-bill"><ServiceIcon name={email.subscription.name}/><div><strong>{email.subscription.name}</strong><span>{dateLabel(email.subscription.days)}</span></div><b>{money(email.subscription.amount)}</b></div><p>You’re getting this reminder {email.days} {email.days === 1 ? 'day' : 'days'} before your next payment. A good moment to see if it’s still a keeper.</p><button type="button" className="lv-button lv-button-dark" onClick={() => { setView('calendar'); setStep('explore'); setNotice('') }}>Review upcoming bills</button><small>A little more in control.<br/>The DUES team</small></div>
          </article> : <div className="lv-demo-inbox-empty"><span><Mail size={33} strokeWidth={1.4} aria-hidden="true"/></span><h4>Your next heads-up lives here.</h4><p>Hit “Remind me” to preview a renewal email for your selected subscription.</p><small>Sample inbox · No real emails</small></div>)}

          {step === 'explore' && view === 'budget' && <div className="lv-demo-dashboard">
            <div className="lv-demo-summary"><span>Your monthly picture</span><strong>{money(total)}</strong><small>of your {money(budget)} monthly budget</small></div>
            <div className={`lv-demo-budget${total > budget ? ' is-over' : ''}`}><div role="meter" aria-label="Monthly budget used" aria-valuemin={0} aria-valuemax={budget} aria-valuenow={Math.min(total, budget)} aria-valuetext={`${money(total)} of ${money(budget)} budget`}><span style={{ width: `${Math.min(total / budget * 100, 100)}%` }}/></div><p><strong>{money(Math.abs(budget - total))}</strong> {total > budget ? 'over budget' : 'left in your budget'}</p></div>
            <div className="lv-demo-breakdown"><h4>Where it goes</h4>{subscriptions.map(subscription => <div key={subscription.name}><span><i style={{ background: subscription.color }}/>{subscription.name}</span><b>{money(monthlyCost(subscription))}<small>/mo</small></b></div>)}{subscriptions.length === 0 && <p>Add a plan to start your spending breakdown.</p>}</div>
            <div className="lv-demo-dashboard-note"><CalendarDays size={15} aria-hidden="true"/>{money(total * 12)} committed over a full year.</div>
          </div>}

          {step === 'explore' && view === 'calendar' && <div className="lv-demo-dashboard lv-demo-renewals"><div className="lv-demo-card-heading"><CalendarDays size={22} aria-hidden="true"/><div><h4>On the horizon</h4><p>Your next subscription payments.</p></div></div>{[...subscriptions].sort((a, b) => a.days - b.days).map(subscription => <div className="lv-demo-renewal" key={subscription.name}><span className="lv-demo-date"><small>{renewalDate(subscription.days).toLocaleDateString('en-US', { month: 'short' })}</small><strong>{renewalDate(subscription.days).getDate()}</strong></span><ServiceIcon name={subscription.name}/><div><strong>{subscription.name}</strong><small>{subscription.annual ? 'Yearly' : 'Monthly'} renewal</small></div><b>{money(subscription.amount)}</b></div>)}{subscriptions.length === 0 && <div className="lv-demo-empty"><p>Add a plan to see upcoming renewals.</p></div>}<div className="lv-demo-dashboard-note"><Bell size={15} aria-hidden="true"/>A little time to decide before you’re charged.</div></div>}

          {step === 'explore' && view === 'sharing' && <div className="lv-demo-dashboard lv-demo-sharing"><div className="lv-demo-card-heading"><UsersRound size={22} aria-hidden="true"/><div><h4>Good things, shared.</h4><p>A sample equal split with your people.</p></div></div>{currentService ? <><div className="lv-demo-shared-plan"><ServiceIcon name={currentService.name}/><strong>{currentService.name}</strong><span>{money(currentService.amount)} / {currentService.annual ? 'year' : 'month'}</span></div><div className="lv-demo-shared-amount"><span>{extraCents ? 'Per person, from' : 'Each person’s share'}</span><strong>{money(shareCents / 100)}</strong><small>per {currentService.annual ? 'year' : 'month'} · {people} people</small></div><div className="lv-demo-people">{Array.from({ length: people }, (_, index) => { const cents = shareCents + (index < extraCents ? 1 : 0); return <div key={index}><LandingAvatar person={demoPeople[index]}/><strong>{demoPeople[index]}</strong><b>{money(cents / 100)}</b></div> })}</div><small className="lv-demo-split-note">Any extra cents are shared across the first members.</small></> : <div className="lv-demo-empty"><p>Add a plan to try splitting the cost.</p></div>}</div>}
        </div>
      </div>
      <div className="lv-demo-footer"><span><Check size={14} aria-hidden="true"/>A safe little sandbox. Nothing is saved or sent.</span><span>Illustrative prices in USD</span></div>
    </div>
  </section>
}
