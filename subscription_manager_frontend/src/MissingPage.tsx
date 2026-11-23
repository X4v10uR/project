import { ServiceIcon } from './ServiceIcon'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from './accounts'
import './MissingPage.css'

const SERVICES = [
  'Netflix', 'Disney+', 'Amazon Prime Video', 'Hulu', 'HBO Max',
  'Apple TV+', 'Paramount+', 'Peacock', 'Crunchyroll', 'Twitch',
  'Vimeo', 'Figma', 'GitHub', 'YouTube Premium', 'Nebula',
  'Spotify', 'Apple Music', 'YouTube Music', 'Amazon Music', 'Tidal',
  'Deezer', 'Google One', 'iCloud+', 'Dropbox', 'Microsoft 365',
  'Notion', 'Evernote', 'Canva Pro', 'Adobe Creative Cloud', 'Xbox Game Pass',
  'PlayStation Plus', 'Nintendo Switch Online', 'EA Play', 'Ubisoft+', 'Apple Arcade',
  'Google Play Pass', 'Audible', 'Kindle Unlimited', 'Coursera Plus', 'Skillshare',
  'LinkedIn', 'Duolingo Plus', 'Patreon', 'Substack',
]

const FOUR = ['10010', '10010', '10010', '11111', '00010', '00010', '00010']
const ZERO = ['01110', '10001', '10001', '10001', '10001', '10001', '01110']

function createDigits() {
  const services = [...SERVICES]
  for (let index = services.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1))
    ;[services[index], services[other]] = [services[other], services[index]]
  }

  let tile = 0
  return [FOUR, ZERO, FOUR].map((rows) => rows.join('').split('').map((cell) => {
    if (cell === '0') return null
    const index = tile++
    return { service: services[index % services.length], index }
  }))
}

function ServiceTile({ service, index }: { service: string; index: number }) {
  return (
    <div
      className="missing-page-tile"
      title={service}
      style={{ animationDelay: `${index * 38}ms` }}
      onAnimationEnd={(event) => { event.currentTarget.style.animationName = 'none' }}
    >
      <ServiceIcon name={service} className="size-full" />
    </div>
  )
}

export function MissingPage() {
  const { user } = useAuth()
  const [digits] = useState(createDigits)

  useEffect(() => {
    const previousTitle = document.title
    document.title = '404 - Not Found | DUES'
    return () => { document.title = previousTitle }
  }, [])

  return (
    <main className="missing-page" aria-labelledby="missing-page-title">
      <div className="missing-page-content">
        <h1 id="missing-page-title" className="sr-only">404 - Page not found</h1>
        <div className="missing-page-art" aria-hidden="true">
          {digits.map((cells, digit) => (
            <div className="missing-page-digit" key={digit}>
              {cells.map((cell, position) => cell ? (
                <ServiceTile key={position} {...cell} />
              ) : <div key={position} />)}
            </div>
          ))}
        </div>
        <div className="missing-page-message">
          <p>Oops! The page you're looking for doesn't exist.</p>
          <Link className="missing-page-home" to={user ? '/dashboard/' : '/'}>
            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16" aria-hidden="true">
              <path fillRule="evenodd" d="M9.293 2.293a1 1 0 0 1 1.414 0l7 7A1 1 0 0 1 17 11h-1v6a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1v-3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-6H3a1 1 0 0 1-.707-1.707l7-7Z" clipRule="evenodd" />
            </svg>
            {user ? 'Go To Dashboard' : 'Go Back Home'}
          </Link>
        </div>
      </div>
    </main>
  )
}
