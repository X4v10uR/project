import { ServiceIcon } from '../ServiceIcon'
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, ArrowUpRight, CalendarDays, ChartNoAxesCombined, ChevronDown, Layers3, ListChecks, PanelsTopLeft, Pencil, Plus, UsersRound, Wallet, Zap } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../accounts';
import { currencyAmount, displayDate, Modal } from '../subscriptions/shared';
import { DashboardBrand } from './DashboardNavigation';
import { NotificationBell } from './notifications';
import './dashboard.css';

export { NotificationsPage } from './notifications';

type Scope = 'personal' | 'teams';
type Balance = {
  balance_display: string;
  balance_adjusted_amount: number;
  balance_base_display: string;
  balance_adjustment_display: string;
};
type ServiceCard = {
  id?: number;
  is_placeholder: boolean;
  bg_style: string;
  edit_url: string;
  amount: string;
};
type UpcomingBill = ServiceCard & {
  date: string; currency: string; service_name: string; days_until: number; description: string; payment_card: string;
};
type ActiveSubscription = ServiceCard & {
  title: string;
  duration_label: string;
  payment_info: string;
  plan_details: string;
};
type Transaction = { id: number; title: string; timestamp: string; amount: string; payment_status: string };
type Dashboard = Balance & {
  as_of_date: string;
  balance_currency: string;
  currency_options: string[];
  monthly_limit: string | null;
  over_budget: boolean;
  monthly_spend_by_currency: Record<string, string>;
  yearly_spend: string;
  team_label: string;
  show_get_started: boolean;
  needs_attention: {
    id: string; kind: 'deadline' | 'payment' | 'approval' | 'trial' | 'price' | 'decision' | 'charge_difference';
    service: string; workspace: string | null; date: string; amount: string | null;
    currency: string | null; action: string; url: string;
    difference?: { payment_id: number; expected: string; delta: string; price_url: string | null };
  }[];
  needs_attention_count?: number;
  total_active: number;
  total_shared: number;
  total_paused: number;
  total_cancelled: number;
  upcoming_week: {
    amount: string;
    next_bill: { service: string; days_until: number; reminders_enabled: boolean } | null;
  };
  upcoming_week_count?: number;
  upcoming_week_days?: { count: number; items: string[] }[];
  upcoming_count?: number;
  subscriptions_view_all_url: string;
  upcoming_bills: UpcomingBill[];
  active_subscriptions_panel: ActiveSubscription[];
  recent_transactions: Transaction[];
  stats_upcoming_bill_balance_display: string;
  stats_total_subscriptions_balance_display: string;
  stats_total_active: string;
  stats_total_paused: string;
  stats_total_cancelled: string;
  balance_trend_points: number[];
  balance_trend_start_label: string;
  balance_trend_end_label: string;
  balance_trend_has_activity: boolean;
  balance_trend_currency: string;
  balance_trend_note: string;
};

const createPath = '/subscriptions/add/';
const dashboardPath = '/dashboard/';
const statsPath = '/dashboard/balance-stats/';
const panelClass = 'rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6';

function useDashboard() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const scope: Scope = params.get('scope') === 'teams' ? 'teams' : 'personal';
  const currency = params.get('currency') || user?.preferred_currency || 'USD';
  const query = new URLSearchParams({ scope, currency }).toString();
  const [loaded, setLoaded] = useState<{ query: string; data?: Dashboard; error?: string }>();
  const [request, setRequest] = useState(0);
  const [fullQuery, setFullQuery] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api<Dashboard>(`/api/dashboard/?${query}${fullQuery === query ? '' : '&preview=1'}`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setLoaded({ query, data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoaded(previous => ({
          query, data: previous?.query === query ? previous.data : undefined,
          error: error instanceof Error ? error.message : 'Could not load your dashboard.',
        }));
      });
    return () => controller.abort();
  }, [query, request, fullQuery]);

  function updateBalance(balance: Balance) {
    setLoaded((current) => current?.query === query && current.data
      ? { query, data: { ...current.data, ...balance } } : current);
  }

  return {
    scope, query,
    data: loaded?.query === query ? loaded.data : undefined,
    error: loaded?.query === query ? loaded.error : undefined,
    updateBalance,
    loadFull: () => setFullQuery(query),
    retry: () => setRequest((count) => count + 1),
  };
}

function CurrencyPicker({ data, compact = false }: { data: Dashboard; compact?: boolean }) {
  const [params, setParams] = useSearchParams();
  function select(code: string) {
    const next = new URLSearchParams(params);
    next.set('currency', code);
    setParams(next);
  }
  return (
    <label className={compact ? 'workspace-currency' : 'inline-flex items-center gap-2 text-sm font-semibold'}>
      <span className={compact ? 'sr-only' : undefined}>Dashboard currency</span>
      <select className="rounded-lg border p-2" value={data.balance_currency} onChange={(event) => select(event.target.value)}>
        {data.currency_options.map((code) => <option key={code}>{code}</option>)}
      </select>
      {compact && <ChevronDown size={11} aria-hidden />}
    </label>
  );
}

function BudgetEditor({ data, scope, reload }: { data: Dashboard; scope: Scope; reload: () => void }) {
  const [limit, setLimit] = useState(data.monthly_limit ?? '');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      await api('/api/dashboard/budget/', {
        method: 'PUT', body: JSON.stringify({ scope, currency: data.balance_currency, monthly_limit: limit || null }),
      });
      reload();
      setMessage(limit ? 'Budget saved.' : 'Budget removed.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save budget.');
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="detail-panel" id="monthly-budget">
      <h2 className="text-lg font-bold">Monthly budget</h2>
      <p className="my-2 text-sm">Get an alert when monthly recurring spend exceeds your limit.</p>
      {data.over_budget && <p role="alert" className="mb-2 font-semibold text-red-700">Monthly spend exceeds your {data.balance_currency} {data.monthly_limit} limit.</p>}
      <form onSubmit={save} className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-sm font-semibold">Spending limit ({data.balance_currency})
          <input className="rounded-lg border p-2" type="number" min="0" max="9999999999.99" step="0.01" placeholder="No limit" value={limit} onChange={(event) => setLimit(event.target.value)} />
        </label>
        <button className="secondary-link" disabled={saving}>{saving ? 'Saving…' : 'Save budget'}</button>
      </form>
      {message && <p role="status" className="mt-2 text-sm">{message}</p>}
    </section>
  );
}

function LoadStatus({ error, retry }: { error?: string; retry: () => void }) {
  if (!error) return <p className="text-sm text-slate-600" role="status">Loading your dashboard…</p>;
  return (
    <div className="rounded-xl bg-red-50 p-4 text-sm text-red-800" role="alert">
      {error} <button className="font-semibold underline" onClick={retry} type="button">Try again</button>
    </div>
  );
}

function ScopePicker({ scope, path }: { scope: Scope; path: string }) {
  const [params] = useSearchParams();
  function destination(item: Scope) {
    const next = new URLSearchParams(params);
    next.set('scope', item);
    return `${path}?${next}`;
  }
  return (
    <nav aria-label="Dashboard scope" className="inline-flex rounded-full border border-slate-200 bg-white p-1">
      {(['personal', 'teams'] as const).map((item) => (
        <Link
          aria-current={scope === item ? 'page' : undefined}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold ${scope === item ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
          key={item}
          to={destination(item)}
        >
          {item === 'personal' ? 'Personal' : 'Teams'}
        </Link>
      ))}
    </nav>
  );
}

function dueIn(days: number) {
  if (days === 0) return 'Due today';
  return days === 1 ? 'In 1 day' : `In ${days} days`;
}

function WorkspaceHeader({ scope, data }: { scope: Scope; data?: Dashboard }) {
  const [params, setParams] = useSearchParams();
  function changeScope(value: string) {
    const next = new URLSearchParams(params);
    next.set('scope', value);
    setParams(next);
  }
  return <header className="dash-topbar">
    <DashboardBrand />
    <label className="workspace-picker">
      <PanelsTopLeft size={17} aria-hidden />
      <select aria-label="Workspace" value={scope} onChange={event => changeScope(event.target.value)}>
        <option value="personal">Personal</option>
        <option value="teams">{data?.team_label || 'Teams'}</option>
      </select>
      <ChevronDown size={14} aria-hidden />
    </label>
    <div className="dash-topbar-actions">{data && <CurrencyPicker compact data={data} />}<NotificationBell /></div>
  </header>;
}

function FundingCard({ data, scope, onUpdate }: { data: Dashboard; scope: Scope; onUpdate: (balance: Balance) => void }) {
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState('');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const balance = await api<Balance>('/api/dashboard/balance/adjust/', {
        method: 'POST', body: JSON.stringify({ target_balance: target, scope, currency: data.balance_currency }),
      });
      onUpdate(balance);
      setEditing(false);
      setStatus('Balance updated.');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Could not update your balance.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="detail-panel funding-panel">
      <div className="panel-heading"><h2>Funding target</h2>
        <button type="button" disabled={saving} className="dash-text-link" aria-label="Edit balance" onClick={() => {
          setStatus('');
          setError('');
          setTarget(data.balance_adjusted_amount.toFixed(2));
          setEditing(true);
        }}>Edit <Pencil size={13} aria-hidden /></button>
      </div>
      <p className="funding-amount">{currencyAmount(data.balance_adjusted_amount, data.balance_currency, 2)}</p>
      <p className="dash-muted">Recurring spend {data.balance_base_display} · Reserve {data.balance_adjustment_display}</p>
      {status && <p className="metric-caption" role="status">{status}</p>}
      {error && !editing && <p className="text-sm text-red-700" role="alert">{error}</p>}
      {editing && <Modal title="Edit funding target" onClose={() => setEditing(false)}>
        <p className="mb-4 text-sm text-slate-600">Your monthly recurring spend is {data.balance_base_display}. Your current reserve is {data.balance_adjustment_display}.</p>
        <form onSubmit={submit} className="grid gap-4">
          <label className="grid gap-1.5 text-sm font-semibold">Funding target ({data.balance_currency})
            <input autoFocus required aria-label={`New balance in ${data.balance_currency}`} className="rounded-xl border border-slate-300 p-2.5" disabled={saving}
              type="number" inputMode="decimal" min="-1000000" max="1000000" step="0.01" value={target} onChange={(event) => setTarget(event.target.value)} />
          </label>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="flex gap-2"><button className="primary-link" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            <button className="secondary-link" type="button" disabled={saving} onClick={() => setEditing(false)}>Cancel</button></div>
        </form>
      </Modal>}
    </section>
  );
}

function SpendingSummary({ data, scope }: { data: Dashboard; scope: Scope }) {
  const currency = data.balance_currency;
  return <section className="spend-hero" data-dock-surface="dark" aria-labelledby="monthly-spending">
    <div className="spend-art" aria-hidden="true" />
    <div className="spend-hero-copy">
      <h2 id="monthly-spending"><Wallet size={17} aria-hidden />Monthly Spending</h2>
      <p className="spend-value">{currencyAmount(data.monthly_spend_by_currency[currency] || 0, currency, 2)}</p>
      <p className="annual-estimate">{currencyAmount(data.yearly_spend, currency, 2)} projected per year</p>
      <div className="spend-actions">
        <Link className="insights-link" to={`/planning/insights/?scope=${scope}`}>Spending insights <ArrowUpRight size={15} aria-hidden /></Link>
        {data.over_budget && <a className="budget-link" href="#monthly-budget">Over budget</a>}
      </div>
    </div>
  </section>;
}

function WeekOutlook({ data, scope }: { data: Dashboard; scope: Scope }) {
  const bills = data.upcoming_bills.filter(bill => !bill.is_placeholder && bill.currency === data.balance_currency && bill.days_until >= 0 && bill.days_until < 7);
  const nextBill = data.upcoming_week.next_bill;
  const count = data.upcoming_week_count ?? bills.length;
  const firstDay = new Date(data.as_of_date + 'T12:00:00Z');
  const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short', timeZone: 'UTC' });
  const dateLabel = new Intl.DateTimeFormat(undefined, { dateStyle: 'long', timeZone: 'UTC' });
  return <section className="dash-panel week-card" aria-labelledby="week-title">
    <div className="panel-heading"><h2 id="week-title"><CalendarDays size={17} aria-hidden />Next 7 days</h2>
      <Link className="round-link" aria-label="Open renewal calendar" to={`/planning/calendar/?scope=${scope}`}><ArrowUpRight size={16} aria-hidden /></Link>
    </div>
    <div className="week-summary"><strong>{data.upcoming_week.amount}</strong><span>{count} {count === 1 ? 'payment' : 'payments'}</span></div>
    {nextBill && <p className="week-next">Next up <strong>{nextBill.service}</strong> · {dueIn(nextBill.days_until).toLowerCase()}</p>}
    <ol className="week-strip" aria-label="Renewals over the next seven days">
      {Array.from({ length: 7 }, (_, offset) => {
        const day = new Date(firstDay);
        day.setUTCDate(day.getUTCDate() + offset);
        const due = bills.filter(bill => bill.days_until === offset);
        const summary = data.upcoming_week_days?.[offset] ?? { count: due.length, items: due.map(bill => bill.service_name + ' ' + bill.amount) };
        const more = summary.count - summary.items.length;
        const label = dateLabel.format(day) + ' · ' + (summary.count ? summary.items.join(', ') + (more > 0 ? ` and ${more} more` : '') : 'No renewals');
        return <li key={offset} className={summary.count ? 'has-renewal' : ''} title={label} aria-label={label}>
          <small aria-hidden>{weekday.format(day)}</small>
          <time dateTime={day.toISOString().slice(0, 10)} aria-hidden>{day.getUTCDate()}</time>
          <i aria-hidden />
        </li>;
      })}
    </ol>
  </section>;
}

function SubscriptionMix({ data }: { data: Dashboard }) {
  const groups = [
    { label: 'Active', count: data.total_active, color: '#617c39' },
    { label: 'Paused', count: data.total_paused, color: '#d4b47e' },
    { label: 'Cancelled', count: data.total_cancelled, color: '#bbbcc3' },
  ];
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  let start = 0;
  const segments = groups.filter(group => group.count > 0).map(group => {
    const end = start + group.count / total * 100;
    const part = `${group.color} ${start}% ${end}%`;
    start = end;
    return part;
  });
  return <section className="dash-panel mix-card" aria-labelledby="mix-heading">
    <div className="panel-heading"><h2 id="mix-heading">Subscription mix</h2><Layers3 size={18} className="panel-icon" aria-hidden /></div>
    <div className="mix-body">
      <div className="mix-ring" style={total ? { background: `conic-gradient(from -90deg, ${segments.join(', ')})` } : undefined}>
        <div><strong>{total}</strong><span>Total plans</span></div>
      </div>
      <dl className="mix-legend">{groups.map(group => <div key={group.label}>
        <dt><i style={{ background: group.color }} aria-hidden />{group.label}</dt><dd>{group.count}</dd>
      </div>)}</dl>
    </div>
    <div className="mix-footer"><UsersRound size={16} aria-hidden /><span>{data.total_shared} shared {data.total_shared === 1 ? 'subscription' : 'subscriptions'}</span>
      <Link to={data.subscriptions_view_all_url} aria-label="View subscriptions"><ArrowRight size={16} aria-hidden /></Link></div>
  </section>;
}

function UpcomingBills({ data, scope, loadFull }: { data: Dashboard; scope: Scope; loadFull: () => void }) {
  const bills = data.upcoming_bills.filter(bill => !bill.is_placeholder);
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? bills : bills.slice(0, 4);
  const total = data.upcoming_count ?? bills.length;
  return <section className="dash-panel renewals-card" aria-labelledby="renewals-heading">
    <div className="panel-heading"><h2 id="renewals-heading">Upcoming renewals</h2>
      <Link className="dash-text-link" to={`/planning/calendar/?scope=${scope}`}>Calendar <ArrowUpRight size={14} aria-hidden /></Link>
    </div>
    {bills.length ? <>
      <div className="renewal-columns" aria-hidden><span>Service</span><span>Renewal date</span><span>Amount</span></div>
      <ul className="renewal-list">{visible.map(bill => <li key={`${bill.id}-${bill.date}`}>
        <Link className="renewal-line" to={bill.edit_url}>
          <span className="bill-service"><ServiceIcon name={bill.service_name} /><span className="bill-name"><strong>{bill.service_name}</strong><small>{bill.description}{bill.payment_card && ` · ${bill.payment_card}`}</small></span></span>
          <span className="bill-date"><time dateTime={bill.date}>{new Date(bill.date + 'T12:00:00Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })}</time><small>{dueIn(bill.days_until)}</small></span>
          <strong className="bill-amount">{bill.amount}</strong>
        </Link></li>)}</ul>
      {total > 4 && <button type="button" className="list-toggle" aria-expanded={expanded} onClick={() => {
        if (!expanded && total > bills.length) loadFull();
        setExpanded(!expanded);
      }}>{expanded ? 'Show fewer' : `View all ${total} renewals`}</button>}
    </> : <p className="dash-empty">No bills due in the next 30 days.</p>}
  </section>;
}

function RecentTransactions({ transactions, scope }: { transactions: Transaction[]; scope: Scope }) {
  const history = `/dashboard/history/?scope=${scope}`;
  return <section className="dash-panel activity-card" aria-labelledby="transactions-heading">
    <div className="panel-heading"><h2 id="transactions-heading">Recent transactions</h2>
      <Link className="dash-text-link" to={history}>History <ArrowUpRight size={14} aria-hidden /></Link></div>
    {transactions.length ? <ul>{transactions.map(entry => <li key={entry.id}>
      <Link className="activity-line" to={`${history}&charge=${entry.id}`}>
        <ServiceIcon name={entry.title} /><span className="bill-name"><strong>{entry.title}</strong><small>{entry.timestamp}</small></span>
        <span className="activity-status">{entry.payment_status}</span><strong className="bill-amount">{entry.amount}</strong>
      </Link></li>)}</ul> : <p className="dash-empty">No transactions yet.</p>}
  </section>;
}

function ActiveSubscriptions({ data }: { data: Dashboard }) {
  const items = data.active_subscriptions_panel.filter(item => !item.is_placeholder);
  return <section className="dash-panel active-card" aria-labelledby="active-heading">
    <div className="panel-heading"><h2 id="active-heading">Active subscriptions</h2><Link className="dash-text-link" to={data.subscriptions_view_all_url}>View all <ArrowUpRight size={14} aria-hidden /></Link></div>
    {items.length ? <ul className="active-list">{items.map(item => <li key={item.id}><Link to={item.edit_url}>
      <ServiceIcon name={item.title} /><span className="bill-name"><strong>{item.title}</strong><small>{item.plan_details.replace(/^Plan details: /, '')} · {item.payment_info.replace(/^Payment info: /, '')}</small></span>
      <span className="active-amount"><strong>{item.amount}</strong><small>per {item.duration_label}</small></span>
    </Link></li>)}</ul> : <p className="dash-empty">No active subscriptions yet.</p>}
  </section>;
}

function ChargeDifferenceActions({ item, onDismiss }: { item: Dashboard['needs_attention'][number]; onDismiss: () => void }) {
  const [status, setStatus] = useState<'idle' | 'busy' | 'done'>('idle');
  const [failure, setFailure] = useState('');
  async function dismiss(paymentId: number, delta: string) {
    setStatus('busy');
    setFailure('');
    try {
      await api(`/api/finance/charge-differences/${paymentId}/dismiss/`, {
        method: 'POST',
        body: JSON.stringify({ delta }),
      });
      setStatus('done');
      onDismiss();
    } catch (error) {
      setStatus('idle');
      setFailure(error instanceof Error ? error.message : 'Could not dismiss this payment difference.');
    }
  }
  const difference = item.difference;
  if (!difference) return null;
  return <div className="flex flex-wrap items-center gap-2">
    <Link className="secondary-link" to={item.url}>{item.action}</Link>
    {difference.price_url && <Link className="secondary-link" to={difference.price_url}>Review price</Link>}
    <button className="secondary-link" disabled={status !== 'idle'}
      onClick={() => void dismiss(difference.payment_id, difference.delta)}>Dismiss as one-off</button>
    {failure && <p role="alert" className="basis-full text-sm text-red-700">{failure}</p>}
  </div>;
}

function NeedsAttention({ items, total, onDismiss, loadFull }: {
  items: Dashboard['needs_attention']; total: number; onDismiss: () => void; loadFull: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, 5);
  const labels = { deadline: 'Cancel by', payment: 'Failed payment', approval: 'Approval requested', trial: 'Trial ends', price: 'Price increases', decision: 'Renewal decision due', charge_difference: 'Payment amount differs' };
  return (
    <section className="detail-panel" aria-labelledby="attention-title">
      <h2 id="attention-title" className="text-lg font-bold text-slate-900">Needs attention</h2>
      <p className="mt-1 text-sm text-slate-600">The next seven days, plus open payment issues and approval requests.</p>
      {items.length ? <ul className="mt-2 divide-y divide-slate-100">{visible.map((item) => (
        <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
          <div>
            <strong>{item.service}</strong>{item.workspace && <span className="ml-2 text-sm text-slate-600">{item.workspace}</span>}
            <p className="text-sm text-slate-600">
              {labels[item.kind]} · <time dateTime={item.date}>{displayDate(item.date)}</time>
              {!item.difference && item.amount != null && item.currency && <> · {currencyAmount(item.amount, item.currency)}</>}
            </p>
            {item.difference && item.currency && item.amount != null && <p className="text-sm text-slate-700">
              Expected {currencyAmount(item.difference.expected, item.currency, 2)} · Paid {currencyAmount(item.amount, item.currency, 2)}
              {' · '}{currencyAmount(Math.abs(Number(item.difference.delta)), item.currency, 2)} {Number(item.difference.delta) > 0 ? 'more' : 'less'} than expected
            </p>}
          </div>
          {item.difference ? <ChargeDifferenceActions item={item} onDismiss={onDismiss} /> : <Link className="secondary-link" to={item.url}>{item.action}</Link>}
        </li>
      ))}</ul> : <p className="mt-2 text-sm text-slate-600">Nothing needs your attention in this workspace.</p>}
      {total > 5 && <button className="secondary-link mt-2" aria-expanded={expanded} onClick={() => {
        if (!expanded && total > items.length) loadFull();
        setExpanded(!expanded);
      }}>{expanded ? 'Show fewer' : `Show all ${total} items`}</button>}
    </section>
  );
}

export function DashboardPage() {
  const { data, error, retry, scope, query, updateBalance, loadFull } = useDashboard();
  const today = data && new Date(data.as_of_date + 'T12:00:00Z');
  return <>
    <WorkspaceHeader data={data} scope={scope} />
    <div className="dash-content">
      <div className="dash-titlebar">
        <div><h1>Overview</h1>{today && <p>{today.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}</p>}</div>
        <Link className="dash-create" to={createPath}><Plus size={17} aria-hidden />Create Subscription</Link>
      </div>
      {data ? <>
        {data.show_get_started && <section className="detail-panel first-bill" aria-labelledby="get-started">
          <h2 id="get-started">Track your first subscription</h2>
          <p className="dash-muted">Add a bill to see its next payment and choose when to get a reminder.</p>
          <div className="onboard-links"><Link className="primary-link" to="/subscriptions/quick-add/">Add my first subscription</Link>
            <Link className="secondary-link" to="/subscriptions/import/">Import a subscription list</Link><Link className="secondary-link" to="/accounts/teams/create/">Set up a team</Link></div>
        </section>}
        <div className="dash-grid hero-grid"><SpendingSummary data={data} scope={scope} /><WeekOutlook data={data} scope={scope} /></div>
        {data.needs_attention.length > 0 && <NeedsAttention key={scope} items={data.needs_attention} total={data.needs_attention_count ?? data.needs_attention.length} onDismiss={retry} loadFull={loadFull} />}
        <div className="dash-grid records-grid"><UpcomingBills data={data} key={query} scope={scope} loadFull={loadFull} /><SubscriptionMix data={data} /></div>
        <div className="dash-grid"><RecentTransactions transactions={data.recent_transactions} scope={scope} /><FundingCard key={query} data={data} onUpdate={updateBalance} scope={scope} /></div>
        <div className="dash-grid dashboard-management">
          <ActiveSubscriptions data={data} /><BudgetEditor data={data} key={query + '-budget'} scope={scope} reload={retry} />
          {data.needs_attention.length === 0 && <NeedsAttention key={scope} items={data.needs_attention} total={0} onDismiss={retry} loadFull={loadFull} />}
          {Object.keys(data.monthly_spend_by_currency).some(code => code !== data.balance_currency) &&
            <section className="detail-panel"><h2>Monthly spending by currency</h2>
              <ul className="mt-2 grid gap-1">{Object.entries(data.monthly_spend_by_currency).sort(([a], [b]) => a.localeCompare(b)).map(([code, amount]) =>
                <li key={code}>{code} {Number(amount).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</li>)}</ul>
            </section>}
        </div>
        <nav className="dash-quick-links" aria-label="Planning shortcuts">
          <Link to="/subscriptions/quick-add/"><Zap size={15} aria-hidden />Quick add</Link>
          <Link to={`/planning/calendar/?scope=${scope}`}><CalendarDays size={15} aria-hidden />Renewal calendar</Link>
          <Link to={`/planning/review/?scope=${scope}`}><ListChecks size={15} aria-hidden />Review inbox</Link>
          <Link to={`${statsPath}?${query}`}><ChartNoAxesCombined size={15} aria-hidden />Open stats</Link>
        </nav>
      </> : <LoadStatus error={error} retry={retry} />}
    </div>
  </>;
}

function ChargeTrend({ data }: { data: Dashboard }) {
  const { balance_trend_points: points, balance_trend_currency: currency } = data;
  const peak = Math.max(1, ...points);
  const formatCharge = (amount: number) => currencyAmount(amount, currency);
  return (
    <section className={panelClass}>
      <h2 className="mb-3 text-lg font-bold text-slate-900">Charges over the last 30 days</h2>
      {data.balance_trend_has_activity ? (
        <>
          <p className="mb-3 text-sm text-slate-700">Total scheduled <strong>{formatCharge(points.reduce((total, value) => total + value, 0))}</strong></p>
          <div aria-hidden="true" className="flex h-28 items-end gap-0.5 border-b border-slate-200 sm:gap-1">
            {points.map((value, index) => (
              <div className="min-h-px flex-1 rounded-t bg-emerald-600 hover:bg-emerald-800" key={index} style={{ height: `${Math.max(0, value / peak) * 100}%` }} title={formatCharge(value)} />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-xs text-slate-600"><span>{data.balance_trend_start_label}</span><span>{data.balance_trend_end_label}</span></div>
          {data.balance_trend_note && <p className="mt-3 text-sm text-slate-600">{data.balance_trend_note}</p>}
        </>
      ) : <p className="text-sm text-slate-600">No scheduled {currency} charges in this period.</p>}
    </section>
  );
}

export function BalanceStatsPage() {
  const { data, error, retry, scope, query } = useDashboard();
  const metrics = data ? [
    ['Scheduled over the next 30 days', data.stats_upcoming_bill_balance_display],
    ['Total subscriptions balance', data.stats_total_subscriptions_balance_display],
    ['Total active', data.stats_total_active],
    ['Total paused', data.stats_total_paused],
    ['Total cancelled', data.stats_total_cancelled],
  ] : [];
  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 pt-3 sm:px-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Balance &amp; Stats</h1>
        <Link className="secondary-link" to={`${dashboardPath}?${query}`}>Back to Dashboard</Link>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ScopePicker path={statsPath} scope={scope} />{data && <CurrencyPicker data={data} />}
      </div>
      {data ? (
        <>
          <section className={panelClass}>
            <h2 className="mb-4 text-lg font-bold text-slate-900">Live Snapshot</h2>
            <dl className="grid gap-3 sm:grid-cols-2">
              {metrics.map(([label, value]) => (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4" key={label}>
                  <dt className="text-sm font-medium text-slate-600">{label}</dt>
                  <dd className="mt-1 break-words text-xl font-bold text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
          </section>
          <ChargeTrend data={data} />
        </>
      ) : <LoadStatus error={error} retry={retry} />}
    </div>
  );
}
