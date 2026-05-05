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

// Denominators used in cooking measurements, in preference order.
// Snapping to these avoids ugly outputs like "341/500" from AI-stored decimals.
const COOKING_DENOMINATORS = [1, 2, 3, 4, 6, 8]

/**
 * Round a decimal value to the nearest cooking fraction (halves, thirds,
 * quarters, sixths, eighths).  Prefers simpler denominators when tied.
 */
function roundToCookingFraction(value: number): Frac {
  let best: Frac = frac(Math.round(value), 1)
  let bestError = Math.abs(value - Math.round(value))
  for (const d of COOKING_DENOMINATORS) {
    const n = Math.round(value * d)
    const error = Math.abs(value - n / d)
    if (error < bestError - 1e-9) {
      bestError = error
      best = frac(n, d)
    }
  }
  return best
}

// ---------------------------------------------------------------------------
// Unit conversion for renderTemplate
// ---------------------------------------------------------------------------

interface ConvertibleUnit {
  singular: string
  plural: string
  /** Whether to correct singular/plural when keeping this unit. False for abbreviations. */
  applyPluralization: boolean
  matchPattern: RegExp
  smallerFactor: number | null
  smallerSingular: string | null
  convertBelow: number
}

const CONVERTIBLE_UNITS: ConvertibleUnit[] = [
  {
    matchPattern: /^cups?$/i,
    singular: 'cup', plural: 'cups', applyPluralization: true,
    smallerFactor: 16, smallerSingular: 'tablespoon', convertBelow: 0.125,
  },
  {
    matchPattern: /^tablespoons?$/i,
    singular: 'tablespoon', plural: 'tablespoons', applyPluralization: true,
    smallerFactor: 3, smallerSingular: 'teaspoon', convertBelow: 0.5,
  },
  {
    matchPattern: /^tbsp$/i,
    singular: 'tbsp', plural: 'tbsp', applyPluralization: false,
    smallerFactor: 3, smallerSingular: 'tsp', convertBelow: 0.5,
  },
  {
    matchPattern: /^teaspoons?$/i,
    singular: 'teaspoon', plural: 'teaspoons', applyPluralization: true,
    smallerFactor: null, smallerSingular: null, convertBelow: 0,
  },
  {
    matchPattern: /^tsp$/i,
    singular: 'tsp', plural: 'tsp', applyPluralization: false,
    smallerFactor: null, smallerSingular: null, convertBelow: 0,
  },
]

/**
 * Scale a value and convert to a smaller unit when the result would be
 * impractically small (e.g. 1/3 tablespoon → 1 teaspoon).
 * Returns null for unknown units.
 */
function scaleWithUnitConversion(
  scaledValue: number,
  unitWord: string,
): { qty: Frac; unit: string } | null {
  const unitDef = CONVERTIBLE_UNITS.find(u => u.matchPattern.test(unitWord))
  if (!unitDef) return null

  const qty = roundToCookingFraction(scaledValue)

  // Convert when below the threshold or when rounding would give zero
  if (unitDef.smallerFactor !== null && (scaledValue < unitDef.convertBelow || qty.n === 0)) {
    return scaleWithUnitConversion(scaledValue * unitDef.smallerFactor, unitDef.smallerSingular!)
  }

  const unit = unitDef.applyPluralization
    ? (qty.n <= qty.d ? unitDef.singular : unitDef.plural)
    : unitWord  // preserve abbreviation style (tsp, tbsp) unchanged

  return { qty, unit }
}

/**
 * Render an AI-generated template string by replacing {qty:N} placeholders
 * with scaled, formatted quantities.
 *
 * Decimals stored by the AI (e.g. 0.333 for ⅓) are snapped to the nearest
 * cooking fraction.  Known volume units (cup, tablespoon, teaspoon and their
 * abbreviations) are converted to a smaller unit when the scaled quantity
 * would be impractically small, and singular/plural is corrected automatically.
 */
export function renderTemplate(template: string, factor: number): string {
  return template.replace(/\{qty:([\d.]+)\}(\s*)([A-Za-z]+)?/g, (_, n, space, unitWord) => {
    const scaledValue = parseFloat(n) * factor

    if (unitWord) {
      const result = scaleWithUnitConversion(scaledValue, unitWord)
      if (result) return formatFraction(result.qty) + space + result.unit
    }

    // Unknown unit or no unit — just snap and format
    const qty = roundToCookingFraction(scaledValue)
    return unitWord ? formatFraction(qty) + space + unitWord : formatFraction(qty)
  })
}

/**
 * Scale all numeric quantities in an instruction text string by *factor*.
 *
 * Handles the same quantity formats as scaleIngredient (unicode fractions,
 * ASCII fractions, mixed numbers, decimals, integers).  Numbers that are
 * part of temperatures (followed by °) or time durations (followed by
 * minutes/hours/seconds) are left unchanged.
 */
export function scaleInstructionText(text: string, factor: number): string {
  if (factor === 1) return text

  // Normalize digit + unicode-fraction adjacencies: "1½" → "1 ½"
  let normalized = text
  for (const glyph of Object.keys(UNICODE_FRACTIONS)) {
    normalized = normalized.replace(
      new RegExp(`(\\d)(${escapeRegExp(glyph)})`, 'g'),
      '$1 $2',
    )
  }

  const glyphPat = Object.keys(UNICODE_FRACTIONS).map(escapeRegExp).join('|')

  // Order matters: most specific patterns first to avoid partial matches
  const pattern = [
    `\\d+\\s+(?:${glyphPat}|\\d+/\\d+)`, // mixed number: integer + fraction/glyph
    `\\d+\\.\\d+`,                         // decimal
    glyphPat,                              // standalone unicode glyph
    `\\d+/\\d+`,                           // ASCII fraction
    `\\d+`,                                // integer
  ].join('|')

  const re = new RegExp(pattern, 'g')

  return normalized.replace(re, (match, offset) => {
    const afterMatch = normalized.slice(offset + match.length)
    // Skip temperatures (e.g. 350°F)
    if (/^\s*°/.test(afterMatch)) return match
    // Skip time durations (e.g. 30 minutes, 2 hours)
    if (/^\s*(?:minutes?|hours?|seconds?|mins?|hrs?)(?:\s|$|[,.])/i.test(afterMatch)) return match
    return scaleIngredient(match, factor)
  })
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
