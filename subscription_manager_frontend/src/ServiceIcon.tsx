import { useState } from 'react'
import { Dumbbell, Layers } from 'lucide-react'

import { serviceIconSlug } from './serviceIconCatalog'

type ServiceIconProps = { name: string; className?: string; accent?: string }

export function ServiceIcon({ name, className = '', accent }: ServiceIconProps) {
  const slug = serviceIconSlug(name)
  const [failed, setFailed] = useState<string>()
  const Fallback = name.trim().toLowerCase() === 'gym membership' ? Dumbbell : Layers

  return (
    <span className={`service-icon ${className}`} style={accent ? { border: `2px solid ${accent}` } : undefined} aria-hidden="true">
      {slug && slug !== failed
        ? <img src={`${import.meta.env.BASE_URL}service-icons/${slug}.svg`} alt="" draggable={false} onError={() => setFailed(slug)} />
        : <Fallback />}
    </span>
  )
}
