import { useState, type ReactNode } from 'react'
import { ArrowLeft, ArrowRight, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import './auth-pages.css'

const stories = [
  {
    text: 'Love the simplicity of the service and the prompt customer support. We can’t imagine working without it.',
    name: 'Lulu Meyers',
    role: 'PM, Hourglass',
    company: 'Web Design Agency',
    quote: true,
  },
  {
    text: 'More clarity. Fewer surprises. All your subscriptions, in one place.',
    name: 'A little more peace of mind.',
    role: 'Track your spending. Plan your renewals.',
    company: 'Make room for what matters.',
    quote: false,
  },
]

export function AuthLayout({ children }: { children: ReactNode }) {
  const [storyIndex, setStoryIndex] = useState(0)
  const story = stories[storyIndex]

  return <div className="auth-page">
    <div className="auth-form-panel">
      <header className="auth-header">
        <Link to="/" className="auth-brand" aria-label="DUES home">
          <span className="auth-brand-mark"><Zap size={20} fill="currentColor" aria-hidden="true" /></span>
          DUES
        </Link>
      </header>
      <div className="auth-form-region"><div className="auth-form-content">{children}</div></div>
      <footer className="auth-footer">© DUES {new Date().getFullYear()}</footer>
    </div>
    <aside className="auth-story-panel" aria-label="A little inspiration">
      <img className="auth-story-photo" src="/landing-v2/feature-portrait.webp" alt="" fetchPriority="high" />
      <div className="auth-story-shade" />
      <div className="auth-story-content">
        <div className="auth-story-copy" aria-live="polite" aria-atomic="true">
          {story.quote
            ? <blockquote className="auth-story-quote">“{story.text}”</blockquote>
            : <p className="auth-story-quote">{story.text}</p>}
          <p className="auth-story-name">{story.name}</p>
          <p className="auth-story-role">{story.role}<br />{story.company}</p>
        </div>
        <div className="auth-story-controls">
          <button type="button" aria-label="Previous story" onClick={() => setStoryIndex((storyIndex + stories.length - 1) % stories.length)}>
            <ArrowLeft size={23} aria-hidden="true" />
          </button>
          <button type="button" aria-label="Next story" onClick={() => setStoryIndex((storyIndex + 1) % stories.length)}>
            <ArrowRight size={23} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  </div>
}
