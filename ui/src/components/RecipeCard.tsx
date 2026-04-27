import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import type { SearchResult } from '../types'

interface RecipeCardProps {
  recipe: SearchResult
  onFavorite: (id: number, isFavorite: boolean) => void
  onRemoveFromCollection?: (id: number) => void
}

function formatTime(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

const FADE_IN_STYLE: CSSProperties = { opacity: 0, transition: 'opacity 0.3s ease' }
const FADE_IN_LOADED_STYLE: CSSProperties = { opacity: 1, transition: 'opacity 0.3s ease' }

export function RecipeCard({ recipe, onFavorite, onRemoveFromCollection }: RecipeCardProps) {
  const [imgLoaded, setImgLoaded] = useState(false)

  const imageSrc = recipe.has_thumbnail
    ? `/api/recipes/${recipe.id}/thumbnail`
    : recipe.image

  const handleFavoriteClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    onFavorite(recipe.id, recipe.is_favorite)
  }

  return (
    <Link
        to={`/recipe/${recipe.site}/${recipe.id}`}
        className="recipe-card"
      >
        <div className={`card-image-wrap${imageSrc ? '' : ' no-image'}`}>
          {imageSrc ? (
            <img
              src={imageSrc}
              alt={recipe.title}
              loading="lazy"
              style={imgLoaded ? FADE_IN_LOADED_STYLE : FADE_IN_STYLE}
              onLoad={() => setImgLoaded(true)}
              onError={(e) => {
                const img = e.target as HTMLImageElement
                img.style.display = 'none'
                const wrap = img.parentElement
                if (wrap) {
                  wrap.classList.add('no-image')
                  const icon = document.createElement('span')
                  icon.textContent = '🍽️'
                  wrap.prepend(icon)
                }
              }}
            />
          ) : (
            <span>🍽️</span>
          )}
          <button
            className={`card-favorite${recipe.is_favorite ? ' is-fav' : ''}`}
            onClick={handleFavoriteClick}
            title={recipe.is_favorite ? 'Remove from favorites' : 'Save to favorites'}
          >
            {recipe.is_favorite ? '❤️' : '🤍'}
          </button>
        </div>

        <div className="card-body">
          <div className="card-title">{recipe.title || 'Untitled Recipe'}</div>
          <div className="card-meta">
            <span className="card-site">{recipe.site}</span>
            {recipe.total_time != null && recipe.total_time > 0 && (
              <span className="card-time">⏱ {formatTime(recipe.total_time)}</span>
            )}
            {recipe.yields && (
              <span className="card-time">🍽 {recipe.yields}</span>
            )}
          </div>
          {recipe.collections.length > 0 && (
            <div className="card-collections">
              {recipe.collections.map((name) => (
                <span key={name} className="collection-chip">
                  {name}
                  {onRemoveFromCollection && (
                    <button
                      className="collection-chip-remove"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        onRemoveFromCollection(recipe.id)
                      }}
                      title={`Remove from ${name}`}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          {recipe.description && (
            <div className="card-desc">{recipe.description}</div>
          )}
        </div>
    </Link>
  )
}
