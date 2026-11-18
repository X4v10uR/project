import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Pencil, Plus } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../accounts';
import { currencyAmount } from '../subscriptions/shared';

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
  icon_url: string;
  icon_fallback: string;
  edit_url: string;
  amount: string;
};
type UpcomingBill = ServiceCard & { date: string; service_name: string; days_left_text: string };
type ActiveSubscription = ServiceCard & {
  title: string;
  duration_label: string;
  payment_info: string;
  plan_details: string;
};
type Transaction = { id: number; title: string; timestamp: string; amount: string; swatch_style: string };
type Dashboard = Balance & {
  balance_currency: string;
  currency_options: string[];
  monthly_limit: string | null;
  over_budget: boolean;
  monthly_spend_by_currency: Record<string, string>;
  greeting_name: string;
  balance_chip_date: string;
  upcoming_count: number;
  total_active: number;
  upcoming_view_all_url: string;
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

  useEffect(() => {
    const controller = new AbortController();
    api<Dashboard>(`/api/dashboard/?${query}`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setLoaded({ query, data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoaded({ query, error: error instanceof Error ? error.message : 'Could not load your dashboard.' });
      });
    return () => controller.abort();
  }, [query, request]);

  function updateBalance(balance: Balance) {
    setLoaded((current) => current?.query === query && current.data
      ? { query, data: { ...current.data, ...balance } } : current);
  }

  return {
    scope, query,
    data: loaded?.query === query ? loaded.data : undefined,
    error: loaded?.query === query ? loaded.error : undefined,
    updateBalance,
    retry: () => setRequest((count) => count + 1),
  };
}

function CurrencyPicker({ data }: { data: Dashboard }) {
  const [params, setParams] = useSearchParams();
  function select(code: string) {
    const next = new URLSearchParams(params);
    next.set('currency', code);
    setParams(next);
  }
  return (
    <label className="inline-flex items-center gap-2 text-sm font-semibold">Dashboard currency
      <select className="rounded-lg border p-2" value={data.balance_currency} onChange={(event) => select(event.target.value)}>
        {data.currency_options.map((code) => <option key={code}>{code}</option>)}
      </select>
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
    <section className={panelClass}>
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

function BalanceEditor({ data, scope, onUpdate }: { data: Dashboard; scope: Scope; onUpdate: (balance: Balance) => void }) {
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
        method: 'POST',
        body: JSON.stringify({ target_balance: target, scope, currency: data.balance_currency }),
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

  function cancel() {
    setError('');
    setEditing(false);
  }

  return (
    <section aria-labelledby="dashboard-balance-heading" className="rounded-3xl bg-linear-to-br from-[#303036] to-[#19191c] p-5 text-white shadow-lg sm:p-8">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-300" id="dashboard-balance-heading">Monthly recurring spend</h2>
        {data.balance_chip_date !== '--/--' && <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-100">Next bill {data.balance_chip_date}</span>}
      </div>
      <ul className="mb-5 flex flex-wrap gap-x-6 gap-y-2 text-3xl font-bold">
        {Object.entries(data.monthly_spend_by_currency).sort(([a], [b]) => a.localeCompare(b)).map(([code, amount]) => (
          <li key={code}>{code} {Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</li>
        ))}
      </ul>
      {!Object.keys(data.monthly_spend_by_currency).length && <p className="mb-4">No active recurring spend.</p>}
      <h3 className="mb-1 text-sm font-semibold text-slate-300">Subscription funding target ({data.balance_currency})</h3>
      {editing ? (
        <form className="flex flex-wrap items-center gap-3" onSubmit={submit} onKeyDown={(event) => { if (event.key === 'Escape' && !saving) cancel(); }}>
          <label className="flex items-center gap-1 rounded-xl border border-white/30 px-2 py-1 text-2xl font-bold">
            {data.balance_currency}
            <input aria-label={`New balance in ${data.balance_currency}`} autoFocus className="w-40 bg-transparent outline-none" disabled={saving} inputMode="decimal" max="1000000" min="-1000000" onChange={(event) => setTarget(event.target.value)} required step="0.01" type="number" value={target} />
          </label>
          <button className="primary-link disabled:opacity-60" disabled={saving} type="submit">{saving ? 'Saving…' : 'Save'}</button>
          <button className="rounded-full border border-white/30 px-4 py-2 text-sm font-semibold hover:bg-white/10 disabled:opacity-60" disabled={saving} onClick={cancel} type="button">Cancel</button>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xl font-semibold">{data.balance_display}</p>
          <button aria-label="Edit balance" className="flex size-9 items-center justify-center rounded-full border border-white/20 bg-white/10 hover:bg-white/20" onClick={() => {
            setStatus('');
            setTarget(data.balance_adjusted_amount.toFixed(2));
            setEditing(true);
          }} type="button"><Pencil aria-hidden="true" className="size-4" /></button>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-300">A monthly funding goal based on your recurring commitment plus a reserve of {data.balance_adjustment_display}. Set this to the amount you want to put aside for subscriptions.</p>
      {status && <p className="mt-2 text-sm text-emerald-200" role="status">{status}</p>}
      {error && <p className="mt-2 text-sm text-red-200" role="alert">{error}</p>}
    </section>
  );
}

function cardBackground(style: string) {
  return style.match(/#[\da-f]{6}/i)?.[0];
}

function ServiceIcon({ url, fallback }: { url: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-white/65 text-lg font-bold text-slate-800">
      {url && !failed ? <img alt="" className="size-6 object-contain" onError={() => setFailed(true)} src={url} /> : fallback}
    </span>
  );
}

function UpcomingBills({ data }: { data: Dashboard }) {
  const bills = data.upcoming_bills.filter((bill) => !bill.is_placeholder);
  return (
    <section aria-labelledby="dashboard-upcoming-heading">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900" id="dashboard-upcoming-heading">
          Upcoming Bills <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-700">{data.upcoming_count}</span>
        </h2>
        <Link className="secondary-link" to={data.upcoming_view_all_url}>View all</Link>
      </div>
      {bills.length ? (
        <div className="grid auto-cols-[12rem] grid-flow-col gap-3 overflow-x-auto pb-2 sm:auto-cols-[minmax(12rem,1fr)]">
          {bills.map((bill) => (
            <Link className="overflow-hidden rounded-2xl border border-slate-200 bg-white hover:border-slate-400" key={bill.id + '-' + bill.date} to={bill.edit_url}>
              <div className="h-2 bg-slate-300" style={{ backgroundColor: cardBackground(bill.bg_style) }} />
              <div className="flex items-center gap-3 p-3">
                <ServiceIcon url={bill.icon_url} fallback={bill.icon_fallback} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-800" title={bill.service_name}>{bill.service_name}</p>
                  <p className="text-base font-bold text-slate-900">{bill.amount}</p>
                  <p className="text-xs text-slate-600">{bill.date} · {bill.days_left_text}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-4 text-sm text-slate-600">No bills due in the next 30 days.</p>
      )}
    </section>
  );
}

function ActiveSubscriptions({ data }: { data: Dashboard }) {
  const subscriptions = data.active_subscriptions_panel.filter((item) => !item.is_placeholder);
  return (
    <section aria-labelledby="dashboard-active-heading" className={panelClass}>
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900" id="dashboard-active-heading">
        Active Subscriptions <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-700">{data.total_active}</span>
      </h2>
      {subscriptions.length ? (
        <div className="max-h-[22rem] space-y-3 overflow-y-auto">
          {subscriptions.map((subscription) => (
            <article className="rounded-2xl bg-slate-100 p-4 text-slate-900" key={subscription.id} style={{ backgroundColor: cardBackground(subscription.bg_style) }}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <ServiceIcon url={subscription.icon_url} fallback={subscription.icon_fallback} />
                  <div className="min-w-0">
                    <p className="truncate font-bold" title={subscription.title}>{subscription.title}</p>
                    <span className="rounded-full bg-white/65 px-2 py-0.5 text-xs">{subscription.duration_label}</span>
                  </div>
                </div>
                <Link aria-label={`Open ${subscription.title}`} className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-900 text-white hover:bg-slate-700" to={subscription.edit_url}><Pencil aria-hidden="true" className="size-4" /></Link>
              </div>
              <p className="text-xl font-bold">{subscription.amount}</p>
              <p className="text-xs">{subscription.payment_info}</p>
              <p className="text-xs">{subscription.plan_details}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-600">No active subscriptions yet.</p>
      )}
      {subscriptions.length > 0 && <Link className="mt-4 inline-flex text-sm font-semibold text-slate-700 hover:underline" to={data.subscriptions_view_all_url}>View subscriptions</Link>}
    </section>
  );
}

function RecentTransactions({ transactions }: { transactions: Transaction[] }) {
  return (
    <section aria-labelledby="dashboard-transactions-heading" className={panelClass}>
      <h2 className="mb-4 text-lg font-bold text-slate-900" id="dashboard-transactions-heading">Recent Transactions</h2>
      {transactions.length ? (
        <ul className="space-y-2">
          {transactions.map((entry) => (
            <li className="flex items-center gap-3 rounded-xl bg-slate-50 p-3" key={entry.id}>
              <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-slate-200 text-sm font-bold text-slate-800" style={{ backgroundColor: cardBackground(entry.swatch_style) }}>{entry.title.slice(0, 1).toUpperCase()}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900" title={entry.title}>{entry.title}</p>
                <p className="text-xs text-slate-600">{entry.timestamp}</p>
              </div>
              <p className="text-sm font-semibold text-slate-900">{entry.amount}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-600">No transactions yet.</p>
      )}
    </section>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const { data, error, retry, scope, query, updateBalance } = useDashboard();
  return (
    <div className="mx-auto max-w-7xl space-y-5 px-4 pt-3 sm:px-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          {user?.avatar_url && <img alt="" className="size-12 shrink-0 rounded-full object-cover" src={user.avatar_url} style={{ backgroundColor: user.avatar_background_color }} />}
          <h1 className="min-w-0 wrap-anywhere text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{data ? `Hello, ${data.greeting_name}!` : 'Dashboard'}</h1>
        </div>
        <Link className="primary-link" to={createPath}><Plus aria-hidden="true" className="size-4" /> Create Subscription</Link>
      </header>
      <nav className="flex flex-wrap gap-2" aria-label="Planning shortcuts"><Link className="secondary-link" to="/subscriptions/quick-add/">Quick add</Link><Link className="secondary-link" to={`/planning/insights/?scope=${scope}`}>Spending insights</Link><Link className="secondary-link" to={`/planning/calendar/?scope=${scope}`}>Renewal calendar</Link><Link className="secondary-link" to={`/planning/review/?scope=${scope}`}>Review inbox</Link></nav>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ScopePicker path={dashboardPath} scope={scope} />{data && <CurrencyPicker data={data} />}
      </div>
      {data ? (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]">
          <div className="min-w-0 space-y-5">
            <BalanceEditor data={data} key={query} onUpdate={updateBalance} scope={scope} />
            <BudgetEditor data={data} key={query + '-budget'} scope={scope} reload={retry} />
            <UpcomingBills data={data} />
            <section className={`${panelClass} flex flex-wrap items-center justify-between gap-3`}>
              <h2 className="text-lg font-bold text-slate-900">Balance &amp; Stats</h2>
              <Link className="secondary-link" to={`${statsPath}?${query}`}>Open stats</Link>
            </section>
          </div>
          <div className="min-w-0 space-y-5">
            <ActiveSubscriptions data={data} />
            <RecentTransactions transactions={data.recent_transactions} />
          </div>
        </div>
      ) : <LoadStatus error={error} retry={retry} />}
    </div>
  );
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
