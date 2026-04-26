import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { addFavorite, getRecipe, removeFavorite } from '../api'
import type { RecipeDetail } from '../types'

function formatTime(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export function RecipePage() {
  const { id } = useParams<{ site: string; id: string }>()
  const navigate = useNavigate()
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [fav, setFav] = useState(false)

  useEffect(() => {
    if (!id) return
    getRecipe(Number(id))
      .then((r) => {
        setRecipe(r)
        // is_favorite not on RecipeDetail — would need to check via another route
        // For now just default false; grid keeps its own state
      })
      .catch(() => navigate('/'))
      .finally(() => setLoading(false))
  }, [id, navigate])

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
          {rj.cuisine && <span className="pill">🗺 {rj.cuisine}</span>}
          {rj.category && <span className="pill">📂 {rj.category}</span>}
          {rj.author && <span className="pill">👤 {rj.author}</span>}
        </div>

        <div className="recipe-page-actions">
          <button
            onClick={handleFav}
            className={`btn${fav ? ' ghost' : ' ghost'}`}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', border: '1.5px solid var(--border)' }}
          >
            {fav ? '❤️ Saved' : '🤍 Save'}
          </button>
          <a
            href={recipe?.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-link primary"
          >
            View Original ↗
          </a>
        </div>

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
