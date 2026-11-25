import youAvatar from '../../../subscription_manager_backend/avatars/male_memoji/Person=Alfred, Skin Tone=Black, Posture=1 Happy.svg'
import alexAvatar from '../../../subscription_manager_backend/avatars/male_memoji/Person=Chris, Skin Tone=White, Posture=1 Happy.svg'
import morganAvatar from '../../../subscription_manager_backend/avatars/female_memoji/Character=Ezra, Skin tone=Black, Posture=1 Happy.svg'
import jamieAvatar from '../../../subscription_manager_backend/avatars/female_memoji/Character=Kate, Skin tone=White, Posture=1 Happy.svg'
import samAvatar from '../../../subscription_manager_backend/avatars/male_memoji/Person=Michael, Skin Tone=Black, Posture=1 Happy.svg'
import './landing-avatar.css'

// Reuse the account avatar artwork and background palette for sample people.
const avatars = {
  You: { src: youAvatar, background: '#C0CFF5' },
  Alex: { src: alexAvatar, background: '#A8F0D4' },
  Morgan: { src: morganAvatar, background: '#D4C6F5' },
  Jamie: { src: jamieAvatar, background: '#F5C9DD' },
  Sam: { src: samAvatar, background: '#F7D9A0' },
}

export const demoPeople = ['You', 'Alex', 'Morgan', 'Jamie', 'Sam'] as const
export type DemoPerson = (typeof demoPeople)[number]

export function LandingAvatar({ person, className = '' }: { person: DemoPerson; className?: string }) {
  const avatar = avatars[person]
  return <span className={`lv-landing-avatar ${className}`} style={{ backgroundColor: avatar.background }} aria-hidden="true">
    <img src={avatar.src} alt="" width="36" height="36" loading="lazy" decoding="async"/>
  </span>
}
