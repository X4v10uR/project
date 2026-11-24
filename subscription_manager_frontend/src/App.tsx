import {
  CalendarRange, ChartNoAxesCombined, CreditCard, LayoutGrid, List,
  ReceiptText, UsersRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  InviteAcceptPage, LoginPage, SettingsPage, SignupPage, TeamCreatePage, TeamDetailPage,
  TeamsPage, useAuth,
} from './accounts'
import { NotificationBell, NotificationsPage, NotificationsProvider } from './dashboard/notifications'
import { HistoryPage } from './dashboard/HistoryPage'
import { DashboardNavigation } from './dashboard/DashboardNavigation'
import { ImportPage } from './subscriptions/ImportPage'
import { BalanceStatsPage, DashboardPage } from './dashboard/pages'
import { CardsPage } from './subscriptions/CardsPage'
import { SubscriptionFormPage } from './subscriptions/SubscriptionFormPage'
import { SubscriptionsPage } from './subscriptions/SubscriptionsPage'
import { MissingPage } from './MissingPage'
import { InsightsPage, RenewalCalendarPage, ReviewInboxPage, SettlementsPage } from './subscriptions/PlanningPages'
import { QuickAddPage } from './subscriptions/QuickAddPage'
import { ActivityPage, BudgetsPage, ReceiptsPage, ReportsPage } from './finance/FinancePages'
import { ConnectionsPage } from './finance/ConnectionsPage'
import { NotificationSettingsPage } from './finance/NotificationSettings'
import { DataPage } from './finance/DataPage'
import { LandingPage } from './landing/LandingPage'

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

function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <p className="p-8 text-center text-slate-600" role="status">Loading DUES…</p>
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
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
        {!isDashboard && <header className="app-shell-header">
          <Brand />
          <NotificationBell />
        </header>}
        {error && <p className="mx-auto max-w-6xl px-5 text-red-700" role="alert">{error}</p>}
        <main id="app-content"><Outlet /></main>
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

export function App() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <Routes>
      <Route index element={<LandingPage />} />
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
