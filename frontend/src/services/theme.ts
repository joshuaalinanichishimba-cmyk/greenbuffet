/**
 * Light, dark, or whatever Windows is set to.
 *
 * The demo's colours come in both themes and follow the computer's setting by
 * default, which is how the till turned dark on a laptop in dark mode. This
 * lets each screen choose. It is a per-device setting on purpose: the kitchen
 * wall might want dark while the counter wants light.
 *
 * The choice is applied in main.ts before the first paint, so the screen
 * never flashes the wrong colours on the way in.
 */
export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'gb-theme'

export function savedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(choice: ThemeChoice) {
  const root = document.documentElement
  if (choice === 'system') delete root.dataset.theme
  else root.dataset.theme = choice
  try {
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch {
    /* a private window keeps the choice until it closes */
  }
}

/** System, then light, then dark, then back to system. */
export function nextTheme(choice: ThemeChoice): ThemeChoice {
  return choice === 'system' ? 'light' : choice === 'light' ? 'dark' : 'system'
}

export const THEME_LABELS: Record<ThemeChoice, string> = {
  system: 'Colours: match Windows',
  light: 'Colours: always light',
  dark: 'Colours: always dark',
}
