/**
 * Stored files need the sign-in token, which an <img src> cannot send. Each
 * file is fetched once, turned into a blob the browser can show, and kept, so
 * a list of dishes does not fetch the same photograph twice.
 */
import { getToken } from './api'

const cache = new Map<string, string>()

export async function fileUrl(id: string, thumb = false): Promise<string> {
  const key = `${id}${thumb ? '-t' : ''}`
  const held = cache.get(key)
  if (held) return held
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
  const response = await fetch(`${base}/settings/files/${id}${thumb ? '?thumb=true' : ''}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!response.ok) throw new Error('not available')
  const url = URL.createObjectURL(await response.blob())
  cache.set(key, url)
  return url
}

export function forgetFile(id: string) {
  for (const key of [id, `${id}-t`]) {
    const url = cache.get(key)
    if (url) URL.revokeObjectURL(url)
    cache.delete(key)
  }
}
