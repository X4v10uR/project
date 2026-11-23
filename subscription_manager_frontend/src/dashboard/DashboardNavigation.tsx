import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Ellipsis, LogOut, UserRound, Zap, type LucideIcon } from 'lucide-react'
import { useAuth } from '../accounts'
import { Modal } from '../subscriptions/shared'

type Destination = { label: string; to: string; active: boolean; icon: LucideIcon }
type Props = { tabs: Destination[]; signingOut: boolean; onSignOut: () => void }

export function DashboardBrand() {
  return <Link to="/" className="dash-brand" aria-label="DUES home">
    <span className="dash-brand-mark"><Zap size={23} strokeWidth={2.5} fill="currentColor" aria-hidden /></span>
    DUES<span className="brand-period" aria-hidden>.</span>
  </Link>
}

function DestinationLink({ item }: { item: Destination }) {
  return <Link className="rail-link" to={item.to} aria-current={item.active ? 'page' : undefined}>
    <item.icon size={18} strokeWidth={1.7} aria-hidden /><span>{item.label}</span>
  </Link>
}

export function DashboardNavigation({ tabs, signingOut, onSignOut }: Props) {
  const { user } = useAuth()
  const [moreOpen, setMoreOpen] = useState(false)
  const primary = tabs.filter(tab => ['Dashboard', 'Subscriptions', 'History'].includes(tab.label))
  const tools = tabs.filter(tab => !primary.includes(tab))
  const name = user?.display_name || user?.first_name || user?.email.split('@')[0] || 'Profile'
  const profile = <Link className="rail-profile" to="/accounts/settings/" aria-label={`Account settings for ${name}`}>
    <span className="rail-avatar">{user?.avatar_url ? <img src={user.avatar_url} alt="" /> : <UserRound size={18} aria-hidden />}</span>
    <span><strong>{name}</strong><small>Account settings</small></span>
  </Link>
  const logout = <button className="rail-logout" type="button" aria-label="Log out" title="Log out" onClick={onSignOut} disabled={signingOut}><LogOut size={17} aria-hidden /></button>

  return <aside className="dashboard-rail">
    <div className="rail-brand"><DashboardBrand /></div>
    <nav className="rail-nav" aria-label="Application navigation">
      <p className="rail-group-label">Workspace</p>
      {primary.map(item => <DestinationLink key={item.to} item={item} />)}
      <div className="rail-tools">
        <p className="rail-group-label">Tools</p>
        {tools.map(item => <DestinationLink key={item.to} item={item} />)}
      </div>
      <button className="rail-more rail-link" onClick={() => setMoreOpen(true)} type="button" aria-haspopup="dialog"><Ellipsis size={20} aria-hidden />More</button>
    </nav>
    <div className="rail-footer">{profile}{logout}</div>
    {moreOpen && <Modal title="Workspace tools" onClose={() => setMoreOpen(false)}>
      <nav aria-label="More destinations" className="mobile-tool-list">{tools.map(item => <DestinationLink key={item.to} item={item} />)}</nav>
      <div className="mobile-account">{profile}{logout}</div>
    </Modal>}
  </aside>
}
