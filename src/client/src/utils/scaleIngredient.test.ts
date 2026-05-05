import { describe, expect, it } from 'vitest'
import { parseServings, renderTemplate, scaleIngredient, scaleInstructionText } from './scaleIngredient'

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
// renderTemplate — render {qty:N} placeholders with cooking-fraction snapping
// ---------------------------------------------------------------------------

describe('renderTemplate', () => {
  it('renders whole numbers', () => {
    expect(renderTemplate('{qty:2} cups flour', 1)).toBe('2 cups flour')
  })

  it('snaps 0.333 to ⅓', () => {
    expect(renderTemplate('{qty:0.333} cup sugar', 1)).toBe('⅓ cup sugar')
  })

  it('snaps 0.667 to ⅔', () => {
    expect(renderTemplate('{qty:0.667} cup sugar', 1)).toBe('⅔ cup sugar')
  })

  it('snaps 0.5 to ½', () => {
    expect(renderTemplate('{qty:0.5} tsp salt', 1)).toBe('½ tsp salt')
  })

  it('scales and formats cleanly: 0.333 × 3 = 1', () => {
    expect(renderTemplate('{qty:0.333} cup', 3)).toBe('1 cup')
  })

  it('scales a whole number', () => {
    expect(renderTemplate('{qty:2} cups flour', 2)).toBe('4 cups flour')
  })

  it('renders multiple placeholders in one string', () => {
    expect(renderTemplate('Mix {qty:2} cups flour with {qty:0.5} tsp salt', 2)).toBe(
      'Mix 4 cups flour with 1 tsp salt',
    )
  })

  // singular / plural correction
  it('uses singular for 1 cup', () => {
    expect(renderTemplate('{qty:2} cups flour', 0.5)).toBe('1 cup flour')
  })

  it('uses plural for 2 cups', () => {
    expect(renderTemplate('{qty:1} cup flour', 2)).toBe('2 cups flour')
  })

  it('uses singular for ½ cup (≤1)', () => {
    expect(renderTemplate('{qty:1} cup flour', 0.5)).toBe('½ cup flour')
  })

  // abbreviations are preserved unchanged (no pluralization)
  it('preserves tsp abbreviation', () => {
    expect(renderTemplate('{qty:0.5} tsp salt', 2)).toBe('1 tsp salt')
  })

  it('preserves tbsp abbreviation', () => {
    expect(renderTemplate('{qty:2} tbsp butter', 1)).toBe('2 tbsp butter')
  })

  // unit conversion: tablespoon → teaspoon (scale down)
  it('converts tablespoon to teaspoon when result is < 1 tbsp', () => {
    // 1 tbsp × 0.25 = 0.25 tbsp = 0.75 tsp → ¾ tsp
    expect(renderTemplate('{qty:1} tablespoon oil', 0.25)).toBe('¾ teaspoon oil')
  })

  it('converts tbsp to tsp (abbreviation preserved)', () => {
    expect(renderTemplate('{qty:1} tbsp oil', 0.25)).toBe('¾ tsp oil')
  })

  // unit conversion: cup → tablespoon (scale down)
  it('converts cup to tablespoon when result is < ¼ cup', () => {
    // 1 cup × 0.0625 = 0.0625 cup = 3 tsp = 1 tablespoon
    expect(renderTemplate('{qty:1} cup cream', 0.0625)).toBe('1 tablespoon cream')
  })

  // unit conversion: teaspoon → tablespoon (scale up)
  it('converts teaspoon to tablespoon when result is >= 1 tbsp', () => {
    // 1 tsp × 6 = 6 tsp = 2 tablespoons
    expect(renderTemplate('{qty:1} teaspoon salt', 6)).toBe('2 tablespoons salt')
  })

  it('converts tsp to tbsp (abbreviation preserved)', () => {
    // 1 tsp × 3 = 3 tsp = 1 tbsp
    expect(renderTemplate('{qty:1} tsp salt', 3)).toBe('1 tbsp salt')
  })

  // unit conversion: tablespoon → cup (scale up)
  it('converts tablespoon to cup when result is >= ¼ cup', () => {
    // 1 tbsp × 4 = 4 tbsp = 12 tsp = ¼ cup
    expect(renderTemplate('{qty:1} tablespoon oil', 4)).toBe('¼ cup oil')
  })

  // no unit: just snap and format
  it('formats with no unit', () => {
    expect(renderTemplate('{qty:3} eggs', 0.333)).toBe('1 eggs')
  })
})

// ---------------------------------------------------------------------------
// scaleInstructionText — scale quantities embedded in instruction prose
// ---------------------------------------------------------------------------

describe('scaleInstructionText', () => {
  it('scales an integer quantity in a sentence', () => {
    expect(scaleInstructionText('Add 2 cups of flour.', 2)).toBe('Add 4 cups of flour.')
  })

  it('scales multiple quantities in one step', () => {
    expect(scaleInstructionText('Mix 2 cups flour with 1 teaspoon salt.', 2)).toBe(
      'Mix 4 cups flour with 2 teaspoon salt.',
    )
  })

  it('does not scale temperatures', () => {
    expect(scaleInstructionText('Preheat oven to 350°F.', 2)).toBe('Preheat oven to 350°F.')
  })

  it('does not scale time durations', () => {
    expect(scaleInstructionText('Bake for 30 minutes.', 2)).toBe('Bake for 30 minutes.')
    expect(scaleInstructionText('Rest for 1 hour.', 2)).toBe('Rest for 1 hour.')
  })

  it('scales unicode fractions embedded in text', () => {
    expect(scaleInstructionText('Stir in ½ cup sugar.', 2)).toBe('Stir in 1 cup sugar.')
  })

  it('scales mixed numbers embedded in text', () => {
    expect(scaleInstructionText('Pour in 1½ cups broth.', 2)).toBe('Pour in 3 cups broth.')
  })

  it('scales space-separated mixed numbers', () => {
    expect(scaleInstructionText('Add 1 1/2 cups water.', 2)).toBe('Add 3 cups water.')
  })

  it('scales ASCII fractions embedded in text', () => {
    expect(scaleInstructionText('Add 1/2 cup cream.', 2)).toBe('Add 1 cup cream.')
  })

  it('returns unchanged text when factor is 1', () => {
    expect(scaleInstructionText('Add 2 cups flour.', 1)).toBe('Add 2 cups flour.')
  })

  it('passes through text with no quantities unchanged', () => {
    expect(scaleInstructionText('Season with salt to taste.', 2)).toBe(
      'Season with salt to taste.',
    )
  })

  it('scales quantities but leaves temperatures and times alone', () => {
    expect(scaleInstructionText('Bake 2 pans at 375°F for 20 minutes.', 2)).toBe(
      'Bake 4 pans at 375°F for 20 minutes.',
    )
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
