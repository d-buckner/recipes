import { describe, expect, it } from 'vitest'
import { parseServings, scaleIngredient } from './scaleIngredient'

// ---------------------------------------------------------------------------
// scaleIngredient — mirrors the Python _scale_ingredient behaviour
// ---------------------------------------------------------------------------

describe('scaleIngredient', () => {
  // integer quantities
  it('scales an integer quantity', () => {
    expect(scaleIngredient('6 radishes (thinly sliced)', 4)).toBe('24 radishes (thinly sliced)')
  })

  it('halves an integer quantity', () => {
    expect(scaleIngredient('6 cups flour', 0.5)).toBe('3 cups flour')
  })

  // unicode fraction glyphs
  it('scales a standalone unicode fraction', () => {
    expect(scaleIngredient('¼ cup Lemon Garlic Dressing', 4)).toBe('1 cup Lemon Garlic Dressing')
  })

  it('scales ½ tsp x4', () => {
    expect(scaleIngredient('½ tsp salt', 4)).toBe('2 tsp salt')
  })

  it('scales ⅓ cup x3', () => {
    expect(scaleIngredient('⅓ cup sugar', 3)).toBe('1 cup sugar')
  })

  // unicode mixed numbers (digit immediately adjacent to glyph)
  it('scales unicode mixed number "1½"', () => {
    expect(scaleIngredient('1½ cups pearl couscous', 4)).toBe('6 cups pearl couscous')
  })

  it('scales "1½ cups broth" ×2', () => {
    expect(scaleIngredient('1½ cups broth (low sodium)', 2)).toBe('3 cups broth (low sodium)')
  })

  // ASCII mixed numbers
  it('scales space-separated mixed number "1 ½"', () => {
    expect(scaleIngredient('1 ½ cups milk', 4)).toBe('6 cups milk')
  })

  it('scales slash mixed number "1 1/2" ×3', () => {
    expect(scaleIngredient('1 1/2 cups broth', 3)).toBe('4½ cups broth')
  })

  it('scales ASCII fraction "1/2" ×2', () => {
    expect(scaleIngredient('1/2 cup cream', 2)).toBe('1 cup cream')
  })

  // scaling produces a fraction
  it('scales 1 cup × 0.5 → ½ cup', () => {
    expect(scaleIngredient('1 cup flour', 0.5)).toBe('½ cup flour')
  })

  // no quantity — pass through unchanged
  it('passes through an ingredient with no quantity', () => {
    expect(scaleIngredient('black pepper (to taste)', 4)).toBe('black pepper (to taste)')
  })

  it('passes through word-only ingredient', () => {
    expect(scaleIngredient('salt to taste', 4)).toBe('salt to taste')
  })

  // decimal quantities
  it('scales decimal quantity', () => {
    expect(scaleIngredient('1.5 cups oats', 2)).toBe('3 cups oats')
  })

  // scale factor of 1 is a no-op
  it('scale by 1 leaves string unchanged', () => {
    expect(scaleIngredient('2 cups rice', 1)).toBe('2 cups rice')
  })

  // multi-word rest is preserved
  it('preserves multi-word description', () => {
    expect(scaleIngredient('15 oz white beans (canned, drained and rinsed)', 4)).toBe(
      '60 oz white beans (canned, drained and rinsed)'
    )
  })

  it('scales plain count without unit', () => {
    expect(scaleIngredient('4 eggs', 3)).toBe('12 eggs')
  })
})

// ---------------------------------------------------------------------------
// parseServings — extract integer count from a yields string
// ---------------------------------------------------------------------------

describe('parseServings', () => {
  it('parses "4 servings"', () => {
    expect(parseServings('4 servings')).toBe(4)
  })

  it('parses "2 servings"', () => {
    expect(parseServings('2 servings')).toBe(2)
  })

  it('parses "Makes 6"', () => {
    expect(parseServings('Makes 6')).toBe(6)
  })

  it('parses "Serves 8"', () => {
    expect(parseServings('Serves 8')).toBe(8)
  })

  it('parses a range "4-6 servings" → midpoint rounded down', () => {
    expect(parseServings('4-6 servings')).toBe(5)
  })

  it('returns 1 for unparseable string', () => {
    expect(parseServings('')).toBe(1)
    expect(parseServings('one batch')).toBe(1)
  })

  it('returns 1 for null/undefined', () => {
    expect(parseServings(null)).toBe(1)
    expect(parseServings(undefined)).toBe(1)
  })
})
