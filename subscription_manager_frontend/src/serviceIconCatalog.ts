declare const __SERVICE_ICON_SLUGS__: string[]

function normalizeName(name: string) {
  return name.normalize('NFKD').toLowerCase().replace(/\+/g, 'plus').replace(/\p{M}/gu, '').replace(/[^\p{L}\p{N}]/gu, '')
}

const catalog = new Map(__SERVICE_ICON_SLUGS__.map(slug => [normalizeName(slug), slug]))
const aliases: Record<string, string> = {
  'Adobe CC': 'adobe-creative-cloud',
  'Amazon Prime Video': 'prime-video',
  'Amex': 'american-express',
  'Apple TV+': 'apple-tv',
  'AWS': 'amazon-web-services',
  'ChatGPT': 'openai-chatgpt',
  'Creative Cloud': 'adobe-creative-cloud',
  'Disney+': 'disney-plus',
  'Duolingo Plus': 'duolingo',
  'EA Play': 'electronic-arts',
  'Google Play Pass': 'google-play',
  'iCloud+': 'icloud',
  'Kindle Unlimited': 'amazon-kindle',
  'Microsoft 365': 'microsoft',
  'Nintendo Switch Online': 'nintendo-switch',
  'Office 365': 'microsoft',
  'PlayStation Plus': 'playstation',
  'Ubisoft+': 'ubisoft',
  'Xbox Game Pass': 'xbox',
}
for (const [name, slug] of Object.entries(aliases)) catalog.set(normalizeName(name), slug)

export function serviceIconSlug(name: string) {
  const normalized = normalizeName(name)
  const service = normalizeName(name.trim().replace(/\s+(premium|pro|plus|family|individual|standard|basic)$/i, ''))
  return catalog.get(normalized) ?? catalog.get(service)
}
