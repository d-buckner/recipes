/**
 * Ingredient scaling utilities — TypeScript port of the Python
 * recipes.ingredients module used by the backend.
 */

// ---------------------------------------------------------------------------
// Fraction arithmetic (simple numerator/denominator pairs)
// ---------------------------------------------------------------------------

interface Frac {
  n: number  // numerator
  d: number  // denominator
}

function gcd(a: number, b: number): number {
  a = Math.abs(a)
  b = Math.abs(b)
  while (b) {
    const t = b
    b = a % b
    a = t
  }
  return a
}

function frac(n: number, d: number): Frac {
  if (d === 0) throw new Error('Division by zero')
  const g = gcd(Math.abs(n), Math.abs(d))
  return { n: n / g, d: d / g }
}

function fracAdd(a: Frac, b: Frac): Frac {
  return frac(a.n * b.d + b.n * a.d, a.d * b.d)
}

function fracMul(a: Frac, b: Frac): Frac {
  return frac(a.n * b.n, a.d * b.d)
}

// ---------------------------------------------------------------------------
// Unicode fraction glyph tables
// ---------------------------------------------------------------------------

const UNICODE_FRACTIONS: Record<string, Frac> = {
  '½': frac(1, 2),
  '⅓': frac(1, 3),
  '⅔': frac(2, 3),
  '¼': frac(1, 4),
  '¾': frac(3, 4),
  '⅕': frac(1, 5),
  '⅖': frac(2, 5),
  '⅗': frac(3, 5),
  '⅘': frac(4, 5),
  '⅙': frac(1, 6),
  '⅚': frac(5, 6),
  '⅛': frac(1, 8),
  '⅜': frac(3, 8),
  '⅝': frac(5, 8),
  '⅞': frac(7, 8),
}

// Reverse map: serialised "n/d" → unicode glyph
const REVERSE_UNICODE: Record<string, string> = {}
for (const [glyph, f] of Object.entries(UNICODE_FRACTIONS)) {
  REVERSE_UNICODE[`${f.n}/${f.d}`] = glyph
}

// ---------------------------------------------------------------------------
// Parse a single token as a fraction
// ---------------------------------------------------------------------------

function parseQtyToken(token: string): Frac | null {
  if (token in UNICODE_FRACTIONS) return UNICODE_FRACTIONS[token]

  if (token.includes('/')) {
    const parts = token.split('/')
    if (parts.length === 2) {
      const n = parseInt(parts[0], 10)
      const d = parseInt(parts[1], 10)
      if (!isNaN(n) && !isNaN(d) && d !== 0) return frac(n, d)
    }
    return null
  }

  const num = parseFloat(token)
  if (!isNaN(num)) {
    // Convert decimal to fraction with denominator ≤ 1000
    const precision = 1000
    const n = Math.round(num * precision)
    return frac(n, precision)
  }

  return null
}

// ---------------------------------------------------------------------------
// Format a fraction as a human-readable string
// ---------------------------------------------------------------------------

function formatFraction(f: Frac): string {
  const whole = Math.floor(f.n / f.d)
  const remN = f.n - whole * f.d
  const remD = f.d

  if (remN === 0) return String(whole)

  const remKey = `${remN}/${remD}`
  const glyph = REVERSE_UNICODE[remKey]
  const fracStr = glyph ?? `${remN}/${remD}`

  return whole === 0 ? fracStr : `${whole}${fracStr}`
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Scale the leading quantity in *ingredient* by *factor*.
 *
 * Handles unicode fraction glyphs, ASCII fractions, mixed numbers (both
 * "1 ½" and "1½" forms), and decimal quantities.  Returns the string
 * unchanged when no leading numeric quantity is found.
 */
export function scaleIngredient(ingredient: string, factor: number): string {
  if (factor === 1) return ingredient

  // Insert space between a digit and a unicode fraction glyph: "1½" → "1 ½"
  let normalized = ingredient
  for (const glyph of Object.keys(UNICODE_FRACTIONS)) {
    normalized = normalized.replace(new RegExp(`(\\d)(${escapeRegExp(glyph)})`, 'g'), '$1 $2')
  }

  const tokens = normalized.split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return ingredient

  let qty: Frac | null = null
  let qtyTokens = 0

  // Try mixed number: whole integer + proper fraction (e.g. "1 ½", "1 1/2")
  if (tokens.length >= 2) {
    const first = parseQtyToken(tokens[0])
    const second = parseQtyToken(tokens[1])
    if (
      first !== null &&
      second !== null &&
      first.n % first.d === 0 &&           // first is a whole number
      second.n < second.d                   // second is a proper fraction
    ) {
      qty = fracAdd(first, second)
      qtyTokens = 2
    }
  }

  if (qty === null) {
    const first = parseQtyToken(tokens[0])
    if (first !== null) {
      qty = first
      qtyTokens = 1
    }
  }

  if (qty === null) return ingredient

  const factorFrac = frac(Math.round(factor * 1000), 1000)
  const scaled = fracMul(qty, factorFrac)
  const scaledStr = formatFraction(scaled)
  const rest = tokens.slice(qtyTokens).join(' ')
  return rest ? `${scaledStr} ${rest}` : scaledStr
}

/**
 * Parse the number of servings from a recipe yields string.
 *
 * Returns the first integer found, or the midpoint of a range ("4-6" → 5),
 * or 1 as a fallback.
 */
export function parseServings(yields: string | null | undefined): number {
  if (!yields) return 1

  // Range: "4-6 servings"
  const rangeMatch = yields.match(/(\d+)\s*[-–]\s*(\d+)/)
  if (rangeMatch) {
    return Math.floor((parseInt(rangeMatch[1], 10) + parseInt(rangeMatch[2], 10)) / 2)
  }

  // Single number anywhere in the string
  const numMatch = yields.match(/\d+/)
  if (numMatch) return parseInt(numMatch[0], 10)

  return 1
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
