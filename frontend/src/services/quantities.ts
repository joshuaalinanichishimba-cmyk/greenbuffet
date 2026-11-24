/**
 * Recipe quantities.
 *
 * The database stores thousandths of the ingredient's own unit, so an
 * ingredient bought by the kilogram records 180 for 180 g, one bought by the
 * litre records 150 for 150 ml, and one counted singly records 1000 for one.
 * The kitchen types grams, millilitres or a count; these two functions are the
 * only place that translation happens.
 */

/** What the person should type for this ingredient, in words. */
export function entryUnit(unit: string): string {
  if (unit === 'kg' || unit === 'g') return 'g'
  if (unit === 'l' || unit === 'ml') return 'ml'
  return 'how many'
}

export function toMilli(unit: string, typed: string): number | null {
  const value = Number(typed.trim())
  if (!typed.trim() || !Number.isFinite(value) || value <= 0) return null
  // Bought by the kilo or the litre: what is typed is already thousandths.
  if (unit === 'kg' || unit === 'l') return Math.round(value)
  return Math.round(value * 1000)
}

export function fromMilli(unit: string, quantityMilli: number): string {
  if (unit === 'kg' || unit === 'l') return String(quantityMilli)
  return String(quantityMilli / 1000)
}

/**
 * A stock amount for reading, in the unit it is bought in: 1.25 kg, 3 l, 12.
 * Stock levels are kept in thousandths of that unit, like recipe lines.
 */
export function stockAmount(unit: string, quantityMilli: number): string {
  const value = quantityMilli / 1000
  const shown = value.toLocaleString('en-ZM', { maximumFractionDigits: 2 })
  return unit === 'each' ? shown : `${shown} ${unit}`
}
