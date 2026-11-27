import { Check } from 'lucide-react'

export function PasswordStrength({ password, id }: { password: string; id: string }) {
  const characterCount = Array.from(password).length
  const checks = [
    { label: '8+ characters', met: characterCount >= 8 },
    { label: 'A number', met: /[0-9]/.test(password) },
    { label: 'A special character', met: /[^\p{L}\p{N}\s]/u.test(password) },
  ]
  const score = checks.filter(check => check.met).length
  const progress = score + (checks[0].met ? 0 : characterCount / 8)
  const status = password ? `${score} of ${checks.length} checks met` : 'Not entered'

  return <div className="auth-strength" id={id} data-score={score} data-entered={Boolean(password)}>
    <div className="auth-strength-heading">
      <span>Password strength</span>
      <span className="auth-strength-status" aria-live="polite" aria-atomic="true">{status}</span>
    </div>
    <div className="auth-strength-track" role="meter" aria-label="Password strength"
      aria-valuemin={0} aria-valuemax={checks.length} aria-valuenow={progress} aria-valuetext={status}>
      <span className="auth-strength-fill" style={{ transform: `scaleX(${progress / checks.length})` }} />
    </div>
    <ul className="auth-password-checks" aria-label="Password checks">
      {checks.map(check => <li key={check.label} data-met={check.met}>
        <span className="auth-password-check-icon" aria-hidden="true"><Check size={12} strokeWidth={3} /></span>
        <span className="sr-only">{check.met ? 'Met: ' : 'Not met: '}</span>{check.label}
      </li>)}
    </ul>
    <p className="auth-field-hint">Avoid common passwords.</p>
  </div>
}
