import {
  CalendarRange, ChartNoAxesCombined, CreditCard, LayoutGrid, List,
  ReceiptText, UsersRound,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from './accounts/auth'
import { NotificationBell, NotificationsPage, NotificationsProvider } from './dashboard/notifications'
import { DashboardNavigation } from './dashboard/DashboardNavigation'
import { MissingPage } from './MissingPage'
import { LandingPage } from './landing/LandingPage'
import { LandingPageV2 } from './landing/LandingPageV2'

const LoginPage = lazy(() => import('./accounts/PublicPages').then(m => ({ default: m.LoginPage })))
const SignupPage = lazy(() => import('./accounts/PublicPages').then(m => ({ default: m.SignupPage })))
const InviteAcceptPage = lazy(() => import('./accounts/PublicPages').then(m => ({ default: m.InviteAcceptPage })))
const SettingsPage = lazy(() => import('./accounts/SettingsPage').then(m => ({ default: m.SettingsPage })))
const TeamDetailPage = lazy(() => import('./accounts/TeamDetailPage').then(m => ({ default: m.TeamDetailPage })))
const TeamsPage = lazy(() => import('./accounts/TeamPages').then(m => ({ default: m.TeamsPage })))
const TeamCreatePage = lazy(() => import('./accounts/TeamPages').then(m => ({ default: m.TeamCreatePage })))
const HistoryPage = lazy(() => import('./dashboard/HistoryPage').then(m => ({ default: m.HistoryPage })))
const DashboardPage = lazy(() => import('./dashboard/pages').then(m => ({ default: m.DashboardPage })))
const BalanceStatsPage = lazy(() => import('./dashboard/pages').then(m => ({ default: m.BalanceStatsPage })))
const ImportPage = lazy(() => import('./subscriptions/ImportPage').then(m => ({ default: m.ImportPage })))
const CardsPage = lazy(() => import('./subscriptions/CardsPage').then(m => ({ default: m.CardsPage })))
const SubscriptionFormPage = lazy(() => import('./subscriptions/SubscriptionFormPage').then(m => ({ default: m.SubscriptionFormPage })))
const SubscriptionsPage = lazy(() => import('./subscriptions/SubscriptionsPage').then(m => ({ default: m.SubscriptionsPage })))
const QuickAddPage = lazy(() => import('./subscriptions/QuickAddPage').then(m => ({ default: m.QuickAddPage })))
const InsightsPage = lazy(() => import('./subscriptions/PlanningPages').then(m => ({ default: m.InsightsPage })))
const RenewalCalendarPage = lazy(() => import('./subscriptions/PlanningPages').then(m => ({ default: m.RenewalCalendarPage })))
const ReviewInboxPage = lazy(() => import('./subscriptions/PlanningPages').then(m => ({ default: m.ReviewInboxPage })))
const SettlementsPage = lazy(() => import('./subscriptions/PlanningPages').then(m => ({ default: m.SettlementsPage })))
const ActivityPage = lazy(() => import('./finance/FinancePages').then(m => ({ default: m.ActivityPage })))
const BudgetsPage = lazy(() => import('./finance/FinancePages').then(m => ({ default: m.BudgetsPage })))
const ReceiptsPage = lazy(() => import('./finance/FinancePages').then(m => ({ default: m.ReceiptsPage })))
const ReportsPage = lazy(() => import('./finance/FinancePages').then(m => ({ default: m.ReportsPage })))
const ConnectionsPage = lazy(() => import('./finance/ConnectionsPage').then(m => ({ default: m.ConnectionsPage })))
const NotificationSettingsPage = lazy(() => import('./finance/NotificationSettings').then(m => ({ default: m.NotificationSettingsPage })))
const DataPage = lazy(() => import('./finance/DataPage').then(m => ({ default: m.DataPage })))

function Brand() {
  return (
    <Link to="/" className="inline-flex items-center gap-2.5 text-lg font-bold tracking-tight">
      <span className="grid size-8 place-items-center rounded-[10px] bg-lime-accent text-slate-950" aria-hidden="true">
        D
      </span>
      DUES
    </Link>
  )
}

function SkipToContent() {
  return <a className="fixed left-3 top-3 z-[100] -translate-y-40 rounded-lg bg-white px-4 py-3 font-semibold text-indigo-800 shadow focus:translate-y-0" href="#app-content" onClick={event => {
    event.preventDefault()
    const content = document.getElementById('app-content')
    content?.focus({ preventScroll: true })
    content?.scrollIntoView()
  }}>Skip to content</a>
}

function PageContent() {
  return <main id="app-content" tabIndex={-1}>
    <Suspense fallback={<p className="p-8 text-center text-slate-600" role="status">Loading page…</p>}>
      <Outlet />
    </Suspense>
  </main>
}

function PublicLayout() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const isAuthPage = /^\/accounts\/(login|signup)\/?$/.test(pathname)
  return (
    <>
      <SkipToContent />
      {!isAuthPage && <header className="border-b border-slate-200/80 bg-white/75">
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
      </header>}
      <PageContent />
    </>
  )
}

function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <p className="p-8 text-center text-slate-600" role="status">Loading DUES…</p>
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search + location.hash)
    return <Navigate replace to={`/accounts/login/?next=${next}`} />
  }
  return <Outlet />
}

function AppLayout() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState('')

  if (!user) return null

  const path = pathname.endsWith('/') ? pathname : `${pathname}/`
  const inCards = path.startsWith('/subscriptions/cards/')
  const tabs = [
    { label: 'Dashboard', to: '/dashboard/', active: path === '/dashboard/', icon: LayoutGrid },
    { label: 'Stats', to: '/dashboard/balance-stats/', active: path === '/dashboard/balance-stats/', icon: ChartNoAxesCombined },
    { label: 'Subscriptions', to: '/subscriptions/', active: path.startsWith('/subscriptions/') && !inCards, icon: List },
    { label: 'Cards', to: '/subscriptions/cards/', active: inCards, icon: CreditCard },
    { label: 'Teams', to: '/accounts/teams/', active: path.startsWith('/accounts/teams/'), icon: UsersRound },
    { label: 'History', to: '/dashboard/history/', active: path === '/dashboard/history/', icon: ReceiptText },
    { label: 'Planning', to: '/planning/insights/', active: path.startsWith('/planning/'), icon: CalendarRange },
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

  const isDashboard = path === '/dashboard/'

  return (
    <NotificationsProvider>
      <div className={isDashboard ? 'app-shell dashboard-shell' : 'app-shell'}>
        <SkipToContent />
        {!isDashboard && <header className="app-shell-header">
          <Brand />
          <NotificationBell />
        </header>}
        {error && <p className="mx-auto max-w-6xl px-5 text-red-700" role="alert">{error}</p>}
        <PageContent />
        <DashboardNavigation tabs={tabs} signingOut={signingOut} onSignOut={signOut} />
      </div>
    </NotificationsProvider>
  )
}

function CardRoute({ action }: { action: 'add' | 'edit' | 'delete' }) {
  const { id } = useParams()
  const params = new URLSearchParams({ modal: action })
  if (id) params.set('card', id)
  return <Navigate replace to={`/subscriptions/cards/?${params}`} />
}

const pageTitles: Record<string, string> = {
  '/': 'Subscription manager', '/landing-v2': 'Subscription manager',
  '/accounts/login': 'Log in', '/accounts/signup': 'Sign up', '/accounts/settings': 'Account settings',
  '/accounts/teams': 'Teams', '/accounts/teams/create': 'Create a team',
  '/dashboard': 'Dashboard', '/dashboard/history': 'Charge history', '/dashboard/balance-stats': 'Balance stats',
  '/dashboard/notifications': 'Notifications', '/subscriptions': 'Subscriptions', '/subscriptions/add': 'Add subscription',
  '/subscriptions/quick-add': 'Quick add', '/subscriptions/cards': 'Payment cards', '/subscriptions/import': 'Import subscriptions',
  '/planning/insights': 'Spending insights', '/planning/calendar': 'Renewal calendar', '/planning/review': 'Subscription review inbox',
  '/planning/settlements': 'Shared settlement balances', '/planning/budgets': 'Budgets', '/planning/receipts': 'Receipts',
  '/planning/reports': 'Reports', '/planning/connections': 'Connections', '/planning/alerts': 'Alert settings',
  '/planning/data': 'Backup & restore', '/planning/activity': 'Activity',
}

function titleFor(path: string) {
  if (pageTitles[path]) return pageTitles[path]
  if (/^\/accounts\/teams\/[^/]+$/.test(path)) return 'Team workspace'
  if (/^\/accounts\/invites\/accept\/[^/]+$/.test(path)) return 'Team invitation'
  if (/^\/subscriptions\/[^/]+\/edit$/.test(path)) return 'Edit subscription'
  return 'Page not found'
}

export function App() {
  const { pathname, hash } = useLocation()
  const previousPath = useRef(pathname)
  useEffect(() => {
    document.title = `${titleFor(pathname.replace(/\/+$/, '') || '/')} | DUES`
    if (previousPath.current !== pathname && !hash) {
      window.scrollTo(0, 0)
      // A route change should move keyboard and screen reader users out of the dock.
      document.querySelector<HTMLElement>('main[tabindex="-1"]')?.focus({ preventScroll: true })
    }
    previousPath.current = pathname
  }, [pathname, hash])

  return (
    <Routes>
      <Route index element={<LandingPage />} />
      <Route path="landing-v2/" element={<LandingPageV2 />} />
      <Route element={<PublicLayout />}>
        <Route path="accounts/login/" element={<LoginPage />} />
        <Route path="accounts/signup/" element={<SignupPage />} />
        <Route path="accounts/invites/accept/:token/" element={<InviteAcceptPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="dashboard/" element={<DashboardPage />} />
          <Route path="dashboard/history/" element={<HistoryPage />} />
          <Route path="dashboard/balance-stats/" element={<BalanceStatsPage />} />
          <Route path="dashboard/notifications/" element={<NotificationsPage />} />
          <Route path="subscriptions/" element={<SubscriptionsPage />} />
          <Route path="subscriptions/add/" element={<SubscriptionFormPage />} />
          <Route path="subscriptions/quick-add/" element={<QuickAddPage />} />
          <Route path="planning/insights/" element={<InsightsPage />} />
          <Route path="planning/calendar/" element={<RenewalCalendarPage />} />
          <Route path="planning/review/" element={<ReviewInboxPage />} />
          <Route path="planning/settlements/" element={<SettlementsPage />} />
          <Route path="planning/budgets/" element={<BudgetsPage />} />
          <Route path="planning/receipts/" element={<ReceiptsPage />} />
          <Route path="planning/reports/" element={<ReportsPage />} />
          <Route path="planning/connections/" element={<ConnectionsPage />} />
          <Route path="planning/alerts/" element={<NotificationSettingsPage />} />
          <Route path="planning/data/" element={<DataPage />} />
          <Route path="planning/activity/" element={<ActivityPage />} />
          <Route path="subscriptions/import/" element={<ImportPage />} />
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
      <Route path="*" element={<MissingPage />} />
    </Routes>
  )
}
