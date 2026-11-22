import { useEffect, useRef } from 'react'

function animateStatement(page: HTMLElement) {
  const statement = page.querySelector<HTMLElement>('.lp-scroll-copy')
  if (!statement) return () => {}
  const words = Array.from(statement.querySelectorAll<HTMLElement>('[data-lp-word]'))
  let frame = 0
  let inView = false

  function update() {
    frame = 0
    const top = statement!.getBoundingClientRect().top
    const progress = Math.max(0, Math.min(1, (window.innerHeight * .85 - top) / (window.innerHeight * .55)))
    const count = Math.ceil(progress * words.length)
    words.forEach((word, index) => { word.style.opacity = index < count ? '1' : '.24' })
  }

  function scheduleUpdate() {
    if (inView && !frame) frame = requestAnimationFrame(update)
  }

  const observer = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting
    scheduleUpdate()
  })
  observer.observe(statement)
  update()
  window.addEventListener('scroll', scheduleUpdate, { passive: true })
  window.addEventListener('resize', scheduleUpdate)

  return () => {
    observer.disconnect()
    cancelAnimationFrame(frame)
    window.removeEventListener('scroll', scheduleUpdate)
    window.removeEventListener('resize', scheduleUpdate)
    words.forEach(word => word.style.removeProperty('opacity'))
  }
}

export function useLandingMotion(enabled: boolean) {
  const pageRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const page = pageRef.current
    if (!enabled || !page || !('IntersectionObserver' in window) || !page.animate) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const revealed = new Set<Element>()
    const animations = new Set<Animation>()
    let observer: IntersectionObserver | undefined
    let stopStatement: (() => void) | undefined

    function stopMotion() {
      observer?.disconnect()
      animations.forEach(animation => animation.cancel())
      animations.clear()
      stopStatement?.()
      stopStatement = undefined
    }

    function updateMotion() {
      stopMotion()
      if (reducedMotion.matches) return
      stopStatement = animateStatement(page!)

      observer = new IntersectionObserver(entries => {
        for (const { target, isIntersecting } of entries) {
          if (!isIntersecting) continue
          observer?.unobserve(target)
          revealed.add(target)

          // Animate on entry without leaving content hidden while waiting for JS.
          // Individual translate preserves the existing rotations on the artwork.
          const animation = target.animate([
            { opacity: 0, translate: '0 12px' },
            { opacity: 1, translate: '0 0' },
          ], { duration: 480, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' })
          animations.add(animation)
          animation.onfinish = () => animations.delete(animation)
        }
      }, { rootMargin: '0px 0px 24px 0px' })

      page?.querySelectorAll('[data-lp-reveal]').forEach(element => {
        if (!revealed.has(element)) observer?.observe(element)
      })
    }

    updateMotion()
    reducedMotion.addEventListener('change', updateMotion)
    return () => {
      reducedMotion.removeEventListener('change', updateMotion)
      stopMotion()
    }
  }, [enabled])

  return pageRef
}
