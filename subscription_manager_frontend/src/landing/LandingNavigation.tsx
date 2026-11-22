import { useEffect, useState, type RefObject } from 'react'
import { LayoutGrid, Plus, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

export function LandingNavigation({ pageRef }: { pageRef: RefObject<HTMLDivElement | null> }) {
  const [visible, setVisible] = useState(false)
  const [active, setActive] = useState('features')

  useEffect(() => {
    const page = pageRef.current
    if (!page || !('IntersectionObserver' in window)) return

    let heroVisible = true
    const endingsVisible = new Set<Element>()
    const visibility = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.target.matches('.lp-hero')) heroVisible = entry.isIntersecting
        else if (entry.isIntersecting) endingsVisible.add(entry.target)
        else endingsVisible.delete(entry.target)
      }
      setVisible(!heroVisible && endingsVisible.size === 0)
    })
    page.querySelectorAll('.lp-hero, .lp-final-cta, .lp-footer').forEach(element => visibility.observe(element))

    const sections = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) setActive(entry.target.id)
      }
    }, { rootMargin: '-20% 0px -55% 0px' })
    page.querySelectorAll('#features, #how-it-works, #pricing').forEach(element => sections.observe(element))

    return () => { visibility.disconnect(); sections.disconnect() }
  }, [pageRef])

  return <nav className="lp-floating-nav" aria-label="Page sections" data-visible={visible} aria-hidden={!visible} inert={!visible}>
    <a href="#features" aria-current={active === 'features' ? 'location' : undefined}><LayoutGrid size={16} aria-hidden="true"/><span>Features</span></a>
    <a href="#how-it-works" aria-current={active === 'how-it-works' ? 'location' : undefined}><Sparkles size={16} aria-hidden="true"/><span>How it works</span></a>
    <a href="#pricing" aria-current={active === 'pricing' ? 'location' : undefined}><span className="lp-nav-price" aria-hidden="true">$0</span><span>Pricing</span></a>
    <Link className="lp-floating-signup" to="/accounts/signup/"><span>Get started</span><Plus size={16} aria-hidden="true"/></Link>
  </nav>
}
