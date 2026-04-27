import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { addFavorite, getRecipe, listCollections, removeFavorite, removeRecipeFromCollection } from '../api'
import { CollectionPicker } from '../components/CollectionPicker'
import type { Collection, RecipeDetail } from '../types'

interface RecipePageParams extends Record<string, string | undefined> {
  id: string
}

function formatTime(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export function RecipePage() {
  const { id } = useParams<RecipePageParams>()
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [fav, setFav] = useState(false)
  const [collections, setCollections] = useState<string[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [allCollections, setAllCollections] = useState<Collection[]>([])
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!id) return
    getRecipe(Number(id))
      .then((r) => {
        setRecipe(r)
        setCollections(r.collections)
      })
      .catch(() => navigate('/'))
      .finally(() => setLoading(false))
    listCollections().then(setAllCollections).catch(() => null)
  }, [id, navigate])

  // Close picker on outside click
  useEffect(() => {
    if (!pickerOpen) return
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [pickerOpen])

  const handleRemoveFromCollection = async (collectionName: string) => {
    if (!recipe) return
    const col = allCollections.find((c) => c.name === collectionName)
    if (!col) return
    await removeRecipeFromCollection(col.id, recipe.id)
    setCollections((prev) => prev.filter((n) => n !== collectionName))
  }

  const handleFav = async () => {
    if (!recipe) return
    if (fav) {
      await removeFavorite(recipe.id)
    } else {
      await addFavorite(recipe.id)
    }
    setFav((f) => !f)
  }

  const rj = recipe?.recipe_json
  const instructions: string[] = rj?.instructions_list?.length
    ? rj.instructions_list
    : rj?.instructions
      ? [rj.instructions]
      : []

  if (loading) {
    return (
      <div className="recipe-page">
        <header className="recipe-page-header">
          <Link to="/" className="btn-back">← Recipes</Link>
        </header>
        <div className="state-message"><div className="spinner" /></div>
      </div>
    )
  }

  if (!rj) {
    return (
      <div className="recipe-page">
        <header className="recipe-page-header">
          <Link to="/" className="btn-back">← Recipes</Link>
        </header>
        <div className="state-message">
          <div className="state-icon">😕</div>
          <h3>Recipe not available</h3>
        </div>
      </div>
    )
  }

  return (
    <div className="recipe-page">
      <header className="recipe-page-header">
        <Link to="/" className="btn-back">← Recipes</Link>
        <span className="recipe-page-breadcrumb">{recipe?.site}</span>
      </header>

      {rj.image && (
        <img className="recipe-page-hero" src={rj.image} alt={rj.title} />
      )}

      <div className="recipe-page-content">
        <h1 className="recipe-page-title">{rj.title || 'Recipe'}</h1>

        <div className="recipe-modal-pills" style={{ marginBottom: '16px' }}>
          {rj.total_time != null && rj.total_time > 0 && (
            <span className="pill">⏱ {formatTime(rj.total_time)}</span>
          )}
          {rj.yields && <span className="pill">🍽 {rj.yields}</span>}
          {rj.cuisine?.map((c) => (
            <Link key={c} to={`/?cuisine=${encodeURIComponent(c)}`} className="pill pill-filter">🗺 {c}</Link>
          ))}
          {rj.category?.map((c) => (
            <Link key={c} to={`/?category=${encodeURIComponent(c)}`} className="pill pill-filter">📂 {c}</Link>
          ))}
          {rj.author && (
            <Link to={`/?author=${encodeURIComponent(rj.author)}`} className="pill pill-filter">👤 {rj.author}</Link>
          )}
        </div>

        <div className="recipe-page-actions">
          <button
            onClick={handleFav}
            className="btn ghost"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', border: '1.5px solid var(--border)' }}
          >
            {fav ? '❤️ Saved' : '🤍 Save'}
          </button>
          <div className="recipe-collection-wrap" ref={pickerRef}>
            <button
              className="btn ghost"
              style={{ border: '1.5px solid var(--border)' }}
              onClick={() => setPickerOpen((o) => !o)}
            >
              📁 Add to collection
            </button>
            {pickerOpen && (
              <CollectionPicker
                recipeId={recipe!.id}
                recipeCollections={collections}
                onUpdate={setCollections}
              />
            )}
          </div>
          <a
            href={recipe?.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-link primary"
          >
            View Original ↗
          </a>
        </div>

        {collections.length > 0 && (
          <div className="recipe-page-collections">
            {collections.map((name) => (
              <span key={name} className="collection-chip">
                {name}
                <button
                  className="collection-chip-remove"
                  onClick={() => handleRemoveFromCollection(name)}
                  title={`Remove from ${name}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {rj.description && (
          <p className="recipe-page-desc">{rj.description}</p>
        )}

        <div className="recipe-columns">
          {rj.ingredients && rj.ingredients.length > 0 && (
            <div className="recipe-section">
              <h3>Ingredients</h3>
              <ul className="ingredients-list">
                {rj.ingredients.map((ing, i) => (
                  <li key={i}>{ing}</li>
                ))}
              </ul>
            </div>
          )}

          {instructions.length > 0 && (
            <div className="recipe-section">
              <h3>Instructions</h3>
              {instructions.length === 1 ? (
                <p className="instructions-text">{instructions[0]}</p>
              ) : (
                <div className="instructions-steps">
                  {instructions.map((step, i) => (
                    <div key={i} className="step">
                      <span className="step-num">{i + 1}</span>
                      <p className="step-text">{step}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
