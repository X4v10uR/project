import {
  ArrowRight, ChartNoAxesCombined, CreditCard, LayoutGrid, List, LogOut,
  ReceiptText, UserRound, UsersRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  InviteAcceptPage, LoginPage, SettingsPage, SignupPage, TeamCreatePage, TeamDetailPage,
  TeamsPage, useAuth,
} from './accounts'
import { NotificationBell, NotificationsPage, NotificationsProvider } from './dashboard/notifications'
import { BalanceStatsPage, DashboardPage } from './dashboard/pages'
import { CardsPage } from './subscriptions/CardsPage'
import { SubscriptionFormPage } from './subscriptions/SubscriptionFormPage'
import { SubscriptionsPage } from './subscriptions/SubscriptionsPage'

function Brand() {
  return (
    <Link to="/" className="inline-flex items-center gap-2.5 text-lg font-bold tracking-tight">
      <span className="grid size-8 place-items-center rounded-[10px] bg-lime-accent text-slate-950" aria-hidden="true">
        S
      </span>
      Subly
    </Link>
  )
}

function PublicLayout() {
  const { user } = useAuth()
  return (
    <>
      <header className="border-b border-slate-200/80 bg-white/75">
        <nav aria-label="Primary navigation" className="mx-auto flex min-h-16 max-w-6xl items-center justify-between gap-3 px-5">
          <Brand />
          {user ? (
            <Link className="primary-link" to="/dashboard/">Dashboard</Link>
          ) : (
            <div className="flex items-center gap-2">
              <Link className="secondary-link" to="/accounts/login/">Log in</Link>
              <Link className="primary-link" to="/accounts/signup/">Sign up</Link>
            </div>
          )}
        </nav>
      </header>
      <main><Outlet /></main>
    </>
  )
}

function LandingPage() {
  const { user, loading } = useAuth()
  if (!loading && user) return <Navigate replace to="/dashboard/" />
  return (
    <div className="mx-auto max-w-6xl px-5 pb-16 pt-14 sm:pt-20">
      <section className="grid items-center gap-10 lg:grid-cols-[0.9fr_1.1fr]">
        <div>
          <h1 className="max-w-xl text-5xl font-semibold leading-[1.03] tracking-[-0.06em] sm:text-6xl">
            Take control of your subscriptions
          </h1>
          <p className="mt-5 max-w-md text-lg leading-relaxed text-slate-600">
            See what you spend, know when each service renews, and manage subscriptions you share with your team.
          </p>
          <Link className="primary-link mt-7" to="/accounts/signup/">
            Get started <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
        <img
          className="w-full rounded-3xl border border-white bg-white shadow-xl shadow-slate-300/50"
          src="/static/images/hero-demo.png"
          alt="Subly dashboard showing spending, upcoming renewals, and subscriptions"
        />
      </section>
      <section aria-labelledby="features" className="mt-20">
        <h2 id="features" className="text-3xl font-semibold tracking-tight">Everything you need to stay in control</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {[
            ['Track expenses', 'View recurring costs and see how spending changes over time.'],
            ['Plan for renewals', 'Set reminders so you have time to review a subscription before it renews.'],
            ['Organize cards', 'See which subscriptions renew on each card and manage shared costs.'],
          ].map(([title, description]) => (
            <article key={title} className="rounded-3xl border border-slate-200/75 bg-white p-6">
              <h3 className="text-lg font-semibold">{title}</h3>
              <p className="mt-2 leading-relaxed text-slate-600">{description}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <p className="p-8 text-center text-slate-600" role="status">Loading Subly…</p>
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate replace to={`/accounts/login/?next=${next}`} />
  }
  return <Outlet />
}

function AppLayout() {
  const { user, logout } = useAuth()
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState('')

  if (!user) return null

  const path = pathname.endsWith('/') ? pathname : `${pathname}/`
  const history = path === '/subscriptions/' && new URLSearchParams(search).get('sort') === 'renewal_date'
  const inCards = path.startsWith('/subscriptions/cards/')
  const tabs = [
    { label: 'Dashboard', to: '/dashboard/', active: path === '/dashboard/', icon: LayoutGrid },
    { label: 'Stats', to: '/dashboard/balance-stats/', active: path === '/dashboard/balance-stats/', icon: ChartNoAxesCombined },
    { label: 'Subscriptions', to: '/subscriptions/', active: path.startsWith('/subscriptions/') && !history && !inCards, icon: List },
    { label: 'Cards', to: '/subscriptions/cards/', active: inCards, icon: CreditCard },
    { label: 'Teams', to: '/accounts/teams/', active: path.startsWith('/accounts/teams/'), icon: UsersRound },
    { label: 'History', to: '/subscriptions/?sort=renewal_date', active: history, icon: ReceiptText },
  ]

  async function signOut() {
    setSigningOut(true)
    setError('')
    try {
      await logout()
      navigate('/accounts/login/', { replace: true })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not log out.')
      setSigningOut(false)
    }
  }

  const profileName = user.first_name || 'Profile'
  const profileActive = path === '/accounts/settings/'

  return (
    <NotificationsProvider>
      <div className="app-shell">
        <header className="app-shell-header">
          <Brand />
          <NotificationBell />
        </header>
        {error && <p className="mx-auto max-w-6xl px-5 text-red-700" role="alert">{error}</p>}
        <main id="app-content"><Outlet /></main>
        <div className="app-dock-wrap">
          <nav className="app-dock" aria-label="Application navigation">
            <Link className="app-dock-link" to="/accounts/settings/" aria-current={profileActive ? 'page' : undefined} title={profileName}>
              {user.avatar_url ? (
                <img className="size-6 rounded-lg object-contain" src={user.avatar_url} alt="" style={{ backgroundColor: user.avatar_background_color }} />
              ) : <UserRound size={19} aria-hidden="true" />}
              <span className="max-w-18 truncate">{profileName}</span>
            </Link>
            {tabs.map(({ label, to, active, icon: Icon }) => (
              <Link className="app-dock-link" key={to} to={to} aria-current={active ? 'page' : undefined}>
                <Icon size={19} aria-hidden="true" />
                <span>{label}</span>
              </Link>
            ))}
            <button type="button" className="app-dock-link" onClick={() => void signOut()} disabled={signingOut}>
              <LogOut size={19} aria-hidden="true" />
              <span>{signingOut ? 'Logging out…' : 'Log out'}</span>
            </button>
          </nav>
        </div>
      </div>
    </NotificationsProvider>
  )
}

function MissingPage() {
  const { user } = useAuth()
  return (
    <section className="mx-auto max-w-xl px-5 py-24 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">Page not found</h1>
      <p className="mb-6 mt-3 text-slate-600">Check the address or return to Subly.</p>
      <Link className="primary-link" to={user ? '/dashboard/' : '/'}>
        {user ? 'Open dashboard' : 'Back to home'}
      </Link>
    </section>
  )
}

function CardRoute({ action }: { action: 'add' | 'edit' | 'delete' }) {
  const { id } = useParams()
  const params = new URLSearchParams({ modal: action })
  if (id) params.set('card', id)
  return <Navigate replace to={`/subscriptions/cards/?${params}`} />
}

export function App() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<LandingPage />} />
        <Route path="accounts/login/" element={<LoginPage />} />
        <Route path="accounts/signup/" element={<SignupPage />} />
        <Route path="accounts/invites/accept/:token/" element={<InviteAcceptPage />} />
        <Route path="*" element={<MissingPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="dashboard/" element={<DashboardPage />} />
          <Route path="dashboard/balance-stats/" element={<BalanceStatsPage />} />
          <Route path="dashboard/notifications/" element={<NotificationsPage />} />
          <Route path="subscriptions/" element={<SubscriptionsPage />} />
          <Route path="subscriptions/add/" element={<SubscriptionFormPage />} />
          <Route path="subscriptions/:id/edit/" element={<SubscriptionFormPage />} />
          <Route path="subscriptions/cards/" element={<CardsPage />} />
          <Route path="subscriptions/cards/add/" element={<CardRoute action="add" />} />
          <Route path="subscriptions/cards/:id/edit/" element={<CardRoute action="edit" />} />
          <Route path="subscriptions/cards/:id/delete/" element={<CardRoute action="delete" />} />
          <Route path="accounts/settings/" element={<SettingsPage />} />
          <Route path="accounts/teams/" element={<TeamsPage />} />
          <Route path="accounts/teams/create/" element={<TeamCreatePage />} />
          <Route path="accounts/teams/:teamId/" element={<TeamDetailPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
