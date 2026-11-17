import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from './accounts'
import './MissingPage.css'

const ICON_BASE = 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/'

// Keep the service tiles and digit shapes from the original Django 404 page.
const SERVICES = [
  ['Netflix', 'netflix'],
  ['Disney+', 'disney-plus'],
  ['Amazon Prime Video', 'amazon-prime-video', 'amazon-prime', 'amazon'],
  ['Hulu', 'hulu'],
  ['HBO Max', 'hbo-max', 'max'],
  ['Apple TV+', 'apple-tv-plus', 'apple-tv', 'apple'],
  ['Paramount+', 'paramount-plus'],
  ['Peacock', 'peacock'],
  ['Crunchyroll', 'crunchyroll'],
  ['Discovery+', 'discovery-plus', 'hbo-max', 'paramount-plus'],
  ['Viu', 'viu', 'youtube'],
  ['Shudder', 'shudder', 'hbo-max'],
  ['BritBox', 'britbox', 'paramount-plus'],
  ['YouTube Premium', 'youtube-premium', 'youtube'],
  ['CuriosityStream', 'curiositystream', 'youtube'],
  ['Spotify', 'spotify'],
  ['Apple Music', 'apple-music', 'apple'],
  ['YouTube Music', 'youtube-music', 'youtube'],
  ['Amazon Music', 'amazon-music', 'amazon'],
  ['Tidal', 'tidal'],
  ['Deezer', 'deezer'],
  ['Google One', 'google-one', 'google'],
  ['iCloud+', 'icloud-plus', 'icloud', 'apple'],
  ['Dropbox', 'dropbox'],
  ['Microsoft 365', 'microsoft-365', 'microsoft'],
  ['Notion', 'notion'],
  ['Evernote', 'evernote', 'notion'],
  ['Canva Pro', 'canva-pro', 'canva', 'adobe'],
  ['Adobe Creative Cloud', 'adobe-creative-cloud', 'adobe'],
  ['Xbox Game Pass', 'xbox-game-pass', 'xbox'],
  ['PlayStation Plus', 'playstation-plus', 'playstation'],
  ['Nintendo Switch Online', 'nintendo-switch-online', 'nintendo-switch', 'nintendo'],
  ['EA Play', 'ea-play', 'electronic-arts'],
  ['Ubisoft+', 'ubisoft-plus', 'ubisoft', 'playstation'],
  ['Apple Arcade', 'apple-arcade', 'apple'],
  ['Google Play Pass', 'google-play-pass', 'google-play', 'google'],
  ['Audible', 'audible'],
  ['Kindle Unlimited', 'kindle-unlimited', 'amazon'],
  ['Coursera Plus', 'coursera-plus', 'coursera'],
  ['Skillshare', 'skillshare', 'coursera'],
  ['MasterClass', 'masterclass', 'coursera'],
  ['Duolingo Plus', 'duolingo-plus', 'duolingo'],
  ['Patreon', 'patreon'],
  ['Substack', 'substack', 'patreon'],
]

const FALLBACK_ICONS = [
  'google', 'youtube', 'amazon', 'apple', 'microsoft', 'dropbox', 'spotify',
  'patreon', 'coursera', 'adobe', 'playstation', 'xbox', 'hbo-max',
  'paramount-plus', 'disney-plus', 'paypal', 'docker', 'cloudflare', 'github', 'discord',
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

function ServiceTile({ service: [name, ...preferred], index }: { service: string[]; index: number }) {
  const [candidate, setCandidate] = useState(0)
  const offset = (index + 1) % FALLBACK_ICONS.length
  const icons = [...new Set([
    ...preferred, ...FALLBACK_ICONS.slice(offset), ...FALLBACK_ICONS.slice(0, offset),
  ])]
  const exhausted = candidate >= icons.length

  return (
    <div
      className="missing-page-tile"
      title={name}
      style={{
        animationDelay: `${index * 38}ms`,
        backgroundColor: exhausted ? `hsl(${((index + 1) * 47) % 360} 55% 88%)` : undefined,
      }}
      onAnimationEnd={(event) => { event.currentTarget.style.animationName = 'none' }}
    >
      {!exhausted && (
        <img
          src={`${ICON_BASE}${icons[candidate]}.svg`}
          alt=""
          draggable={false}
          onError={() => setCandidate((current) => current + 1)}
        />
      )}
    </div>
  )
}

export function MissingPage() {
  const { user } = useAuth()
  const [digits] = useState(createDigits)

  useEffect(() => {
    const previousTitle = document.title
    document.title = '404 - Not Found | Subly'
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
