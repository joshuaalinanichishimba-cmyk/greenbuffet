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

/**
 * The demo's headline style: K2,770 rather than K2,770.00. Used for big
 * numbers on cards, where the ngwee are noise. Ngwee still show when there
 * are any, so a total of K94.50 is never rounded into a lie.
 */
export function kwachaShort(ngwee: number): string {
  const whole = ngwee % 100 === 0
  const value = (ngwee / 100).toLocaleString('en-ZM', {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  })
  return `K${value}`
}

/** Axis labels on charts: K0, K500, K1.0k, K1.5k, as the demo writes them. */
export function kwachaAxis(ngwee: number): string {
  const k = ngwee / 100
  return k >= 1000 ? `K${(k / 1000).toFixed(1)}k` : `K${Math.round(k)}`
}
