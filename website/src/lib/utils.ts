// Base path for assets (set at build time via next.config.js)
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH || ''

export function assetPath(path: string): string {
  return `${basePath}${path}`
}
