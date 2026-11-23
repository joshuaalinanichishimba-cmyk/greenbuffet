/**
 * Kwacha and ngwee.
 *
 * Prices are whole ngwee everywhere in the system (100 ngwee = K1). These two
 * functions are the only place kwacha and ngwee are converted, so rounding
 * happens once and in a known way.
 */

export function kwacha(ngwee: number, withSymbol = true): string {
  const value = (ngwee / 100).toLocaleString('en-ZM', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return withSymbol ? `K${value}` : value
}

/** Reads what someone typed into a price box. Returns null if it is not a price. */
export function toNgwee(typed: string): number | null {
  const cleaned = typed.replace(/[\s,K]/gi, '')
  if (!cleaned || !/^\d*\.?\d{0,2}$/.test(cleaned)) return null
  const value = Number(cleaned)
  if (!Number.isFinite(value) || value < 0) return null
  return Math.round(value * 100)
}
