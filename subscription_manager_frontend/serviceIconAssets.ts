import { readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname } from 'node:path'
import type { Plugin } from 'vite'

// Keep the package's SVGs outside the application JS. Browsers request only
// the marks on the current screen, and can cache them across pages.
export function serviceIconAssets(): Plugin {
  const require = createRequire(import.meta.url)
  const directory = dirname(require.resolve('thesvg/spotify'))
  const slugs = new Set(readdirSync(directory)
    .filter(file => file.endsWith('.cjs') && file !== 'index.cjs')
    .map(file => file.slice(0, -4)))

  return {
    name: 'service-icon-assets',
    config: () => ({ define: { __SERVICE_ICON_SLUGS__: JSON.stringify([...slugs]) } }),
    configureServer(server) {
      server.middlewares.use('/service-icons', (request, response, next) => {
        const slug = /^\/([^/?]+)\.svg(?:\?|$)/.exec(request.url ?? '')?.[1]
        if (!slug || !slugs.has(slug)) return next()
        response.setHeader('Content-Type', 'image/svg+xml')
        response.end(require(`thesvg/${slug}`).svg)
      })
    },
    generateBundle() {
      const icons: Record<string, { slug: string; svg: string }> = require('thesvg')
      for (const { slug, svg } of Object.values(icons)) {
        this.emitFile({ type: 'asset', fileName: `service-icons/${slug}.svg`, source: svg })
      }
    },
  }
}
