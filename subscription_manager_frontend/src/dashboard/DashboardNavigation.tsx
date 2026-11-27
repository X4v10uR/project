import { useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Ellipsis, LogOut, UserRound, Zap, type LucideIcon } from 'lucide-react'
import { CapsuleGlass } from './CapsuleGlass'
import { useAuth } from '../accounts/auth'
import { Modal } from '../subscriptions/shared'
import './dashboard-dock.css'

type Destination = { label: string; to: string; active: boolean; icon: LucideIcon }
type Props = { tabs: Destination[]; signingOut: boolean; onSignOut: () => void }

const primaryDestinations = ['Dashboard', 'Subscriptions', 'History']

function useDockMotion(pathname: string) {
  const dockRef = useRef<HTMLElement>(null)

  useLayoutEffect(() => {
    const dock = dockRef.current
    if (!dock) return

    const items = Array.from(dock.querySelectorAll<HTMLElement>('[data-dock-item]'))
    const allowMotion = matchMedia('(prefers-reduced-motion: no-preference)')
    let pointer: { x: number; y: number } | null = null
    let frame = 0
    let surfacesChanged = true

    function paint() {
      if (!dock) return
      const bounds = dock.getBoundingClientRect()
      const x = (pointer?.x ?? bounds.left + bounds.width / 2) - bounds.left
      const y = (pointer?.y ?? bounds.top + bounds.height / 2) - bounds.top
      const visibleItems = items.map(item => ({ item, left: item.offsetLeft, width: item.offsetWidth, distance: 0 }))
        .filter(entry => entry.width > 0)
      if (surfacesChanged) {
        surfacesChanged = false
        const darkSurfaces = Array.from(document.querySelectorAll('[data-dock-surface="dark"]'), surface => surface.getBoundingClientRect())
        const centerY = bounds.top + bounds.height / 2
        for (const { item, left, width } of visibleItems) {
          const centerX = bounds.left + left + width / 2
          item.toggleAttribute('data-on-dark', darkSurfaces.some(rect =>
            rect.left <= centerX && centerX < rect.right && rect.top <= centerY && centerY < rect.bottom,
          ))
        }
      }
      for (const entry of visibleItems) entry.distance = Math.abs(x - entry.left - entry.width / 2)
      const keyboardItem = visibleItems.find(({ item }) => item.matches(':focus-visible'))
      const activeItem = visibleItems.find(({ item }) => item.matches('[aria-current], [data-current]'))
      const closest = pointer && visibleItems.reduce<(typeof visibleItems)[number] | undefined>(
        (nearest, entry) => !nearest || entry.distance < nearest.distance ? entry : nearest, undefined,
      )
      const target = closest || keyboardItem || activeItem
      const moving = Boolean(pointer) && allowMotion.matches

      if (target) {
        const { left, width } = target
        const dx = x - left - width / 2
        dock.style.setProperty('--lens-x', `${left + (moving ? Math.max(-4, Math.min(4, dx * .1)) : 0)}px`)
        dock.style.setProperty('--lens-width', `${width}px`)
        dock.style.setProperty('--lens-y', moving ? `${(y - bounds.height / 2) * .09}px` : '0px')
        dock.style.setProperty('--lens-glint', moving ? `${Math.max(10, Math.min(90, 50 + dx / width * 80))}%` : '50%')
      }

      dock.style.setProperty('--lens-opacity', target ? '1' : '0')
      dock.style.setProperty('--light-x', `${x}px`)
      dock.style.setProperty('--light-y', `${y}px`)
      dock.style.setProperty('--light-opacity', moving ? '1' : '0')

      for (const { item, distance, width } of visibleItems) {
        const proximity = moving ? Math.max(0, 1 - distance / (width + 20)) : 0
        item.style.setProperty('--icon-lift', `${proximity * -6}px`)
        item.style.setProperty('--icon-scale', String(1 + proximity * .22))
      }
    }

    function schedulePaint() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(paint)
    }

    function move(event: PointerEvent) {
      if (event.pointerType === 'touch' || !allowMotion.matches) return
      pointer = { x: event.clientX, y: event.clientY }
      schedulePaint()
    }

    function leave() {
      pointer = null
      schedulePaint()
    }

    function updateSurfaces() {
      surfacesChanged = true
      schedulePaint()
    }

    paint()
    const observer = new ResizeObserver(updateSurfaces)
    observer.observe(dock)
    const content = document.getElementById('app-content')
    if (content) observer.observe(content)
    window.addEventListener('scroll', updateSurfaces, { passive: true })
    window.addEventListener('resize', updateSurfaces)
    dock.addEventListener('pointermove', move)
    dock.addEventListener('pointerleave', leave)
    dock.addEventListener('focusin', leave)
    dock.addEventListener('focusout', schedulePaint)
    allowMotion.addEventListener('change', leave)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('scroll', updateSurfaces)
      window.removeEventListener('resize', updateSurfaces)
      dock.removeEventListener('pointermove', move)
      dock.removeEventListener('pointerleave', leave)
      dock.removeEventListener('focusin', leave)
      dock.removeEventListener('focusout', schedulePaint)
      allowMotion.removeEventListener('change', leave)
    }
  }, [pathname])

  return dockRef
}

export function DashboardBrand() {
  return <Link to="/" className="dash-brand" aria-label="DUES home">
    <span className="dash-brand-mark"><Zap size={23} strokeWidth={2.5} fill="currentColor" aria-hidden /></span>
    DUES<span className="brand-period" aria-hidden>.</span>
  </Link>
}

function DockLink({ item, secondary = false }: { item: Destination; secondary?: boolean }) {
  return <Link className="dock-item" data-dock-item data-secondary={secondary || undefined} data-label={item.label}
    to={item.to} aria-label={item.label} aria-current={item.active ? 'page' : undefined}>
    <span className="dock-icon"><item.icon size={22} strokeWidth={1.8} aria-hidden /></span>
    <span className="dock-label" aria-hidden>{item.label}</span>
  </Link>
}

export function DashboardNavigation({ tabs, signingOut, onSignOut }: Props) {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const dock = useDockMotion(pathname)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreButton = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)
  function closeMore(restoreFocus = true) {
    returnFocus.current = restoreFocus
    setMoreOpen(false)
  }
  // Wait for the native modal to unmount before focusing outside of it.
  useLayoutEffect(() => {
    if (!moreOpen && returnFocus.current) {
      moreButton.current?.focus()
      returnFocus.current = false
    }
  }, [moreOpen])
  const primary = primaryDestinations.flatMap(label => tabs.filter(tab => tab.label === label))
  const tools = tabs.filter(tab => !primaryDestinations.includes(tab.label))
  const accountActive = /^\/accounts\/settings\/?$/.test(pathname)
  const selectedTool = tools.find(tab => tab.active)?.label || (accountActive ? 'Account' : undefined)
  const name = user?.display_name || user?.first_name || user?.email.split('@')[0] || 'Profile'
  const avatar = user?.avatar_url
    ? <img className="dock-avatar" src={user.avatar_url} alt="" style={{ backgroundColor: user.avatar_background_color }} />
    : <UserRound size={20} strokeWidth={1.65} aria-hidden />

  return <>
    <div className="dashboard-dock-wrap">
      <nav ref={dock} className="dashboard-dock" aria-label="Application navigation">
        <div className="dock-glass" aria-hidden="true">
          <CapsuleGlass />
        </div>
        <span className="dock-lens" aria-hidden="true" />
        {primary.map(tab => <DockLink key={tab.to} item={tab} />)}
        {tools.map(tab => <DockLink key={tab.to} item={tab} secondary />)}
        <span className="dock-divider" aria-hidden="true" />
        <Link className="dock-item" data-dock-item data-secondary data-label="Account" to="/accounts/settings/"
          aria-label={`Account settings for ${name}`} aria-current={accountActive ? 'page' : undefined}>
          <span className="dock-icon">{avatar}</span><span className="dock-label" aria-hidden>Account</span>
        </Link>
        <button className="dock-item" data-dock-item data-secondary data-label="Log out" type="button"
          aria-label={signingOut ? 'Signing out…' : 'Log out'} onClick={onSignOut} disabled={signingOut}>
          <span className="dock-icon"><LogOut size={21} strokeWidth={1.8} aria-hidden /></span>
        </button>
        <button ref={moreButton} className="dock-item dock-more" data-dock-item data-label="More" data-current={selectedTool ? true : undefined}
          onClick={() => setMoreOpen(true)} type="button" aria-label={selectedTool ? `More, current section ${selectedTool}` : 'More'}
          aria-haspopup="dialog" aria-expanded={moreOpen}>
          <span className="dock-icon"><Ellipsis size={22} aria-hidden /></span><span className="dock-label" aria-hidden>{selectedTool}</span>
        </button>
      </nav>
    </div>
    {moreOpen && <Modal title="Workspace tools" onClose={() => closeMore()}>
      <nav aria-label="More destinations" className="mobile-tool-list">
        {tools.map(({ icon: Icon, ...item }) => <Link key={item.to} to={item.to} aria-current={item.active ? 'page' : undefined}
          onClick={() => closeMore(pathname === item.to)}><Icon size={18} aria-hidden />{item.label}</Link>)}
        <Link to="/accounts/settings/" aria-current={accountActive ? 'page' : undefined} onClick={() => closeMore(accountActive)}>{avatar}Account settings</Link>
        <button type="button" onClick={() => { closeMore(); onSignOut() }} disabled={signingOut}><LogOut size={18} aria-hidden />{signingOut ? 'Signing out…' : 'Log out'}</button>
      </nav>
    </Modal>}
  </>
}
