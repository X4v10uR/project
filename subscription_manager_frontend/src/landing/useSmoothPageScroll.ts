import { useEffect } from 'react'
import Lenis from 'lenis'
import 'lenis/dist/lenis.css'

export function useSmoothPageScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let scroll: Lenis | undefined

    function updateScroll() {
      scroll?.destroy()
      scroll = undefined
      if (reducedMotion.matches) return

      scroll = new Lenis({
        autoRaf: true,
        lerp: 0.12,
        smoothWheel: true,
        syncTouch: false,
        anchors: true,
        stopInertiaOnNavigate: true,
      })
    }

    updateScroll()
    reducedMotion.addEventListener('change', updateScroll)

    return () => {
      reducedMotion.removeEventListener('change', updateScroll)
      scroll?.destroy()
    }
  }, [enabled])
}
