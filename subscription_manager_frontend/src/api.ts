function csrfToken() {
  const cookie = document.cookie.split('; ').find((item) => item.startsWith('csrftoken='))
  return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : undefined
}

export function errorMessage(data: unknown, fallback: string): string {
  if (typeof data === 'string') return data.trim() || fallback
  if (Array.isArray(data)) return data.map((item) => errorMessage(item, '')).filter(Boolean).join(' ') || fallback
  if (data && typeof data === 'object') {
    const fields = data as Record<string, unknown>
    if (typeof fields.detail === 'string') return fields.detail
    if (typeof fields.error === 'string') return fields.error
    if (typeof fields.message === 'string') return fields.message
    const messages = Object.entries(fields).map(([name, value]) => {
      const message = errorMessage(value, '')
      if (!message || ['errors', 'non_field_errors', '__all__'].includes(name)) return message
      return `${name.replaceAll('_', ' ')}: ${message}`
    })
    return messages.filter(Boolean).join(' ') || fallback
  }
  return fallback
}

export class ApiError extends Error {
  constructor(public status: number, public data: unknown) {
    super(errorMessage(data, `Request failed (${status}).`))
    this.name = 'ApiError'
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (typeof init?.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (!['GET', 'HEAD', 'OPTIONS'].includes((init?.method ?? 'GET').toUpperCase())) {
    const token = csrfToken()
    if (token) headers.set('X-CSRFToken', token)
  }

  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  const contentType = response.headers.get('content-type') || ''
  const data: unknown = response.status !== 204 && contentType.includes('json') ? await response.json() : undefined
  if (!response.ok) throw new ApiError(response.status, data)
  if (response.status !== 204 && data === undefined) {
    throw new Error('Django returned an unexpected response. Check that the backend is running.')
  }
  return data as T
}

export async function downloadFile(path: string, filename: string, init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const token = csrfToken()
  if (token) headers.set('X-CSRFToken', token)
  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => ({})))
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
