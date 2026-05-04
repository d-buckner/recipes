import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addGroceryItem,
  clearGroceryList,
  deleteGroceryItem,
  getGroceryList,
  updateGroceryItem,
} from '../api'
import type { GroceryListItem } from '../types'

// ---------------------------------------------------------------------------
// Category classification
// ---------------------------------------------------------------------------

const CATEGORY_KEYWORDS: Record<string, string[]> = {
  Produce: [
    'apple', 'apples', 'banana', 'bananas', 'berry', 'berries', 'broccoli',
    'cabbage', 'carrot', 'carrots', 'celery', 'cherry', 'cherries', 'corn',
    'cucumber', 'garlic', 'ginger', 'grape', 'grapes', 'herb', 'herbs',
    'kale', 'lemon', 'lemons', 'lettuce', 'lime', 'limes', 'mango', 'mangoes',
    'mint', 'mushroom', 'mushrooms', 'onion', 'onions', 'orange', 'oranges',
    'parsley', 'peach', 'peaches', 'pepper', 'peppers', 'pineapple',
    'potato', 'potatoes', 'scallion', 'scallions', 'shallot', 'shallots',
    'spinach', 'squash', 'strawberry', 'strawberries', 'thyme', 'tomato',
    'tomatoes', 'zucchini', 'basil', 'cilantro', 'dill', 'rosemary', 'sage',
    'avocado', 'avocados', 'beet', 'beets', 'eggplant', 'fennel', 'leek',
    'leeks', 'pear', 'pears', 'plum', 'plums', 'radish', 'radishes',
    'arugula', 'asparagus', 'watercress',
  ],
  Dairy: [
    'butter', 'cheese', 'cream', 'egg', 'eggs', 'ghee', 'milk', 'parmesan',
    'ricotta', 'sour cream', 'yogurt', 'mozzarella', 'cheddar', 'feta',
    'brie', 'gouda', 'gruyere', 'half-and-half', 'whipped cream',
    'crème fraîche', 'buttermilk', 'condensed milk', 'evaporated milk',
  ],
  Meat: [
    'bacon', 'beef', 'chicken', 'clam', 'clams', 'cod', 'crab', 'fish',
    'ham', 'lamb', 'lobster', 'pork', 'prosciutto', 'salmon', 'sausage',
    'shrimp', 'steak', 'tilapia', 'tuna', 'turkey', 'veal', 'anchovy',
    'anchovies', 'duck', 'ground beef', 'ground turkey', 'scallop', 'scallops',
  ],
  Bakery: [
    'bagel', 'bagels', 'baguette', 'bread', 'brioche', 'bun', 'buns',
    'ciabatta', 'croissant', 'croissants', 'flatbread', 'naan', 'pita',
    'roll', 'rolls', 'sourdough', 'tortilla', 'tortillas', 'wrap', 'wraps',
  ],
  Pantry: [
    'almond', 'almonds', 'balsamic', 'barley', 'bean', 'beans', 'broth',
    'brown sugar', 'buckwheat', 'bulgur', 'cashew', 'cashews', 'chickpea',
    'chickpeas', 'chili', 'chocolate', 'cinnamon', 'cocoa', 'coconut',
    'cornstarch', 'couscous', 'cumin', 'curry', 'extract', 'flour', 'honey',
    'jam', 'ketchup', 'lentil', 'lentils', 'maple', 'mayonnaise', 'mustard',
    'noodle', 'noodles', 'nut', 'nuts', 'oat', 'oats', 'oil', 'olive oil',
    'oregano', 'paprika', 'pasta', 'peanut', 'peanuts', 'pecan', 'pecans',
    'pine nut', 'pine nuts', 'powder', 'quinoa', 'raisin', 'raisins', 'rice',
    'salt', 'sauce', 'sesame', 'soy sauce', 'spice', 'spices', 'stock',
    'sugar', 'syrup', 'tahini', 'tamari', 'tomato paste', 'turmeric',
    'vanilla', 'vinegar', 'walnut', 'walnuts', 'wine', 'yeast', 'pepper',
    'black pepper', 'cayenne', 'cardamom', 'clove', 'cloves', 'nutmeg',
    'allspice', 'bay leaf', 'bay leaves', 'lentils', 'canned', 'can of',
    'can', 'jar', 'broth', 'stock', 'bouillon', 'worcestershire',
  ],
}

function categorize(ingredient: string): string {
  const lower = ingredient.toLowerCase()
  for (const [cat, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    if (keywords.some((k) => lower.includes(k))) return cat
  }
  return 'Other'
}

const CATEGORY_ORDER = ['Produce', 'Dairy', 'Meat', 'Bakery', 'Pantry', 'Other']

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface GroceryRowProps {
  item: GroceryListItem
  onCheck: (id: number, checked: boolean) => void
  onDelete: (id: number) => void
}

function GroceryRow({ item, onCheck, onDelete }: GroceryRowProps) {
  const qtyStr = item.approximate && item.qty_display
    ? `≈${item.qty_display}`
    : item.qty_display ?? ''
  const unitStr = item.unit ?? ''
  const label = [qtyStr, unitStr, item.ingredient].filter(Boolean).join(' ')

  return (
    <li className={`grocery-row${item.checked ? ' grocery-row--checked' : ''}`}>
      <input
        type="checkbox"
        className="grocery-checkbox"
        checked={item.checked}
        onChange={(e) => onCheck(item.id, e.target.checked)}
        aria-label={`${item.checked ? 'Uncheck' : 'Check'} ${item.ingredient}`}
      />
      <span
        className="grocery-label"
        title={item.approximate ? 'Quantity estimated by AI' : undefined}
      >
        {label}
      </span>
      <span className="grocery-sources">
        {item.recipe_ids.map((rid) => {
          const title = item.recipe_titles[String(rid)] ?? `Recipe #${rid}`
          return (
            <Link key={rid} to={`/recipes/${rid}`} className="grocery-source-chip">
              {title}
            </Link>
          )
        })}
      </span>
      <button
        className="grocery-delete"
        onClick={() => onDelete(item.id)}
        aria-label={`Remove ${item.ingredient}`}
        title="Remove"
      >
        ✕
      </button>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function GroceryListPage() {
  const [items, setItems] = useState<GroceryListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [addInput, setAddInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [checkedCollapsed, setCheckedCollapsed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const refresh = async () => {
    const data = await getGroceryList()
    setItems(data)
  }

  useEffect(() => {
    setLoading(true)
    refresh().finally(() => setLoading(false))
  }, [])

  const handleCheck = async (id: number, checked: boolean) => {
    // Optimistic update
    setItems((prev) => prev.map((it) => it.id === id ? { ...it, checked } : it))
    await updateGroceryItem(id, { checked })
  }

  const handleDelete = async (id: number) => {
    setItems((prev) => prev.filter((it) => it.id !== id))
    await deleteGroceryItem(id)
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const raw = addInput.trim()
    if (!raw) return
    setAdding(true)
    try {
      const newItem = await addGroceryItem(raw)
      setAddInput('')
      // Refresh to get merged state if deduplication happened
      await refresh()
      // If the new item didn't merge, it'll be in the list; either way list is fresh
      void newItem
    } finally {
      setAdding(false)
      inputRef.current?.focus()
    }
  }

  const handleClearChecked = async () => {
    await clearGroceryList(true)
    await refresh()
  }

  const handleClearAll = async () => {
    await clearGroceryList(false)
    setItems([])
  }

  const unchecked = items.filter((it) => !it.checked)
  const checked = items.filter((it) => it.checked)

  // Group unchecked items by category
  const grouped: Record<string, GroceryListItem[]> = {}
  for (const item of unchecked) {
    const cat = categorize(item.ingredient)
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(item)
  }

  return (
    <div className="grocery-page">
      <div className="grocery-header">
        <form className="grocery-add-form" onSubmit={handleAdd}>
          <input
            ref={inputRef}
            className="grocery-add-input"
            type="text"
            placeholder="Add item…"
            value={addInput}
            onChange={(e) => setAddInput(e.target.value)}
            disabled={adding}
            aria-label="Add grocery item"
          />
          <button
            type="submit"
            className="btn ghost"
            disabled={!addInput.trim() || adding}
          >
            {adding ? '…' : 'Add'}
          </button>
        </form>
        <div className="grocery-header-actions">
          {checked.length > 0 && (
            <button className="btn ghost" onClick={handleClearChecked}>
              Clear checked ({checked.length})
            </button>
          )}
          {items.length > 0 && (
            <button className="btn ghost" onClick={handleClearAll}>
              Clear all
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="state-message"><div className="spinner" /></div>
      )}

      {!loading && items.length === 0 && (
        <div className="state-message">
          <div className="state-icon">🛒</div>
          <h3>Your list is empty</h3>
          <p>Add items above, or use the "Add to grocery list" button on a recipe.</p>
        </div>
      )}

      {!loading && unchecked.length > 0 && (
        <div className="grocery-list">
          {CATEGORY_ORDER.filter((cat) => grouped[cat]?.length).map((cat) => (
            <section key={cat} className="grocery-category">
              <h4 className="grocery-category-title">{cat}</h4>
              <ul className="grocery-items">
                {grouped[cat].map((item) => (
                  <GroceryRow
                    key={item.id}
                    item={item}
                    onCheck={handleCheck}
                    onDelete={handleDelete}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {!loading && checked.length > 0 && (
        <section className="grocery-checked-section">
          <button
            className="grocery-checked-toggle"
            onClick={() => setCheckedCollapsed((v) => !v)}
            aria-expanded={!checkedCollapsed}
          >
            {checkedCollapsed ? '▶' : '▼'} Checked ({checked.length})
          </button>
          {!checkedCollapsed && (
            <ul className="grocery-items">
              {checked.map((item) => (
                <GroceryRow
                  key={item.id}
                  item={item}
                  onCheck={handleCheck}
                  onDelete={handleDelete}
                />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
