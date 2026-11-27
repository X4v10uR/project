import { useEffect, useRef, type ReactNode } from 'react'
import { Link, NavLink, useLocation, useSearchParams } from 'react-router-dom'
import { buttonClass, Field, inputClass, primaryClass } from './shared'

export function PlanningLayout({ title, children, workspace = true }: { title: string; children: ReactNode; workspace?: boolean }) {
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const nav = useRef<HTMLElement>(null)
  useEffect(() => {
    const active = nav.current?.querySelector<HTMLElement>('[aria-current="page"]')
    if (active && nav.current) nav.current.scrollLeft = active.offsetLeft - nav.current.offsetLeft - 8
  }, [pathname])
  const scope = params.get('scope') === 'teams' ? 'teams' : 'personal'
  return <div className="mx-auto grid w-full min-w-0 max-w-6xl grid-cols-[minmax(0,1fr)] gap-5 px-4 py-8 pb-28 sm:px-8">
    <header className="flex flex-wrap items-center justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-700">Make room for what matters</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{title}</h1></div><Link className={primaryClass} to="/subscriptions/quick-add/">Quick add</Link></header>
    <div className="flex min-w-0 max-w-full flex-wrap items-center justify-between gap-4"><nav ref={nav} aria-label="Planning tools" className="flex min-w-0 max-w-full w-full gap-2 overflow-x-auto pb-2">{[['insights', 'Insights'], ['calendar', 'Renewal calendar'], ['review', 'Review inbox'], ['settlements', 'Settlements'], ['budgets', 'Budgets'], ['receipts', 'Receipts'], ['reports', 'Reports'], ['connections', 'Connections'], ['alerts', 'Alert settings'], ['data', 'Backup & restore'], ['activity', 'Activity']].map(([path, label]) => <NavLink className={({ isActive }) => `${buttonClass} shrink-0 whitespace-nowrap ${isActive ? 'border-indigo-300 bg-indigo-50 text-indigo-800' : ''}`} key={path} to={`/planning/${path}/?scope=${scope}`}>{label}</NavLink>)}</nav>
    {workspace && <Field label="Workspace"><select className={inputClass} value={scope} onChange={event => { const next = new URLSearchParams(params); next.set('scope', event.target.value); setParams(next) }}><option value="personal">Personal</option><option value="teams">Teams</option></select></Field>}</div>
    {children}
  </div>
}
