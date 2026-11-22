import { useEffect, useState, type RefObject } from 'react'
import LiquidGlass from 'liquid-glass-react'

const stillPointer = { x: 0, y: 0 }

/** A decorative surface: navigation and focus rings remain outside the filter. */
export function LandingGlass({
  tone = 'light',
  mouseContainer,
  active = false,
}: {
  tone?: 'light' | 'dark'
  mouseContainer?: RefObject<HTMLElement | null>
  active?: boolean
}) {
  const [allowPointer, setAllowPointer] = useState(false)

  useEffect(() => {
    if (!active) return
    const preference = window.matchMedia('(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)')
    const update = () => setAllowPointer(preference.matches)
    update()
    preference.addEventListener('change', update)
    return () => preference.removeEventListener('change', update)
  }, [active])

  const trackPointer = active && allowPointer && Boolean(mouseContainer)

  return <div className="lp-liquid-surface" data-tone={tone} aria-hidden="true">
    <LiquidGlass
      className="lp-liquid-body"
      mode="standard"
      displacementScale={tone === 'dark' ? 70 : 42}
      blurAmount={.025}
      saturation={155}
      aberrationIntensity={1.8}
      elasticity={0}
      cornerRadius={100}
      padding="0"
      mouseContainer={mouseContainer}
      globalMousePos={trackPointer ? undefined : stillPointer}
      mouseOffset={trackPointer ? undefined : stillPointer}
      style={{ position: 'absolute', top: '50%', left: '50%', width: '100%', height: '100%' }}
    ><span/></LiquidGlass>
  </div>
}
