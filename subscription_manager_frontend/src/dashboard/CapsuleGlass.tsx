import { useEffect, useId, useRef, useState, type CSSProperties } from 'react'
import './capsule-glass.css'

type DisplacementMap = { width: number; height: number; url: string }

function createDisplacementMap(width: number, height: number, radius: number): DisplacementMap | null {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return null

  const image = context.createImageData(width, height)
  const rimWidth = Math.min(16, height / 3)
  const halfWidth = width / 2
  const halfHeight = height / 2
  for (let row = 0; row < height; row++) {
    const y = row + 0.5 - halfHeight
    const edgeY = Math.abs(y) - halfHeight + radius
    for (let column = 0; column < width; column++) {
      const x = column + 0.5 - halfWidth
      const edgeX = Math.abs(x) - halfWidth + radius
      const curveX = Math.max(0, edgeX)
      const curveY = Math.max(0, edgeY)
      const curveLength = Math.hypot(curveX, curveY)
      // Signed distance to the straight sides and rounded corners.
      const depth = radius - curveLength - Math.min(0, Math.max(edgeX, edgeY))
      const falloff = 1 - Math.max(0, depth) / rimWidth
      const bend = Math.max(0, falloff) ** 1.7 * 0.46
      const normalX = curveLength ? curveX / curveLength : Number(edgeX >= edgeY)
      const normalY = curveLength ? curveY / curveLength : Number(edgeY > edgeX)
      const index = (row * width + column) * 4

      // R and G encode X and Y. A neutral channel is 0.5. The edge
      // samples toward the interior so no empty pixels show at the rim.
      image.data[index] = 255 * (0.5 - Math.sign(x) * normalX * bend)
      image.data[index + 1] = 255 * (0.5 - Math.sign(y) * normalY * bend)
      image.data[index + 3] = 255
    }
  }

  context.putImageData(image, 0, 0)
  return { width, height, url: canvas.toDataURL() }
}

/** A transparent optical layer. The dock supplies its own tint and highlights. */
export function CapsuleGlass() {
  const filterId = useId()
  const surface = useRef<HTMLSpanElement>(null)
  const [map, setMap] = useState<DisplacementMap | null>(null)

  useEffect(() => {
    const element = surface.current
    // Firefox and Safari can parse URL filters here without applying displacement.
    if (!element || !/\bChrom(?:e|ium)\//.test(navigator.userAgent) || !CSS.supports('backdrop-filter', 'url(#capsule)')) return

    const reducedTransparency = matchMedia('(prefers-reduced-transparency: reduce)')
    let lastGeometry = ''
    let frame = 0

    function update() {
      if (!element) return
      if (reducedTransparency.matches) {
        lastGeometry = ''
        setMap(null)
        return
      }

      const width = element.offsetWidth
      const height = element.offsetHeight
      if (!width || !height) return
      const cssRadius = parseFloat(getComputedStyle(element).borderTopLeftRadius) || 0
      const radius = Math.min(cssRadius, width / 2, height / 2)
      const geometry = `${width}/${height}/${radius}`
      if (geometry === lastGeometry) return
      lastGeometry = geometry
      setMap(createDisplacementMap(width, height, radius))
    }

    function scheduleUpdate() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(update)
    }

    const observer = new ResizeObserver(scheduleUpdate)
    observer.observe(element)
    reducedTransparency.addEventListener('change', scheduleUpdate)
    scheduleUpdate()
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      reducedTransparency.removeEventListener('change', scheduleUpdate)
    }
  }, [])

  return <span ref={surface} className="capsule-glass" aria-hidden="true"
    style={map ? { '--capsule-refraction': `url("#${filterId}")` } as CSSProperties : undefined}>
    {map && <svg className="capsule-glass-definitions" width="0" height="0">
      <defs>
        <filter id={filterId} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feImage href={map.url} width={map.width} height={map.height} preserveAspectRatio="none" result="rimMap" />
          <feDisplacementMap in="SourceGraphic" in2="rimMap" scale="36" xChannelSelector="R" yChannelSelector="G" />
          <feGaussianBlur stdDeviation="2" edgeMode="duplicate" />
        </filter>
      </defs>
    </svg>}
  </span>
}
