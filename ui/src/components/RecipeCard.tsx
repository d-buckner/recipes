import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { SearchResult } from '../types'
import { CollectionPicker } from './CollectionPicker'

interface RecipeCardProps {
  recipe: SearchResult
  onFavorite: (id: number, isFavorite: boolean) => void
  onCollectionUpdate: () => void
}

function formatTime(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export function RecipeCard({ recipe, onFavorite, onCollectionUpdate }: RecipeCardProps) {
  const [pickerAnchor, setPickerAnchor] = useState<DOMRect | null>(null)
  const folderBtnRef = useRef<HTMLButtonElement>(null)

  const handleFavoriteClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    onFavorite(recipe.id, recipe.is_favorite)
  }

  const handleFolderClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (pickerAnchor) {
      setPickerAnchor(null)
      return
    }
    const rect = folderBtnRef.current?.getBoundingClientRect()
    if (rect) setPickerAnchor(rect)
  }

  return (
    <>
      <Link
        to={`/recipe/${recipe.site}/${recipe.id}`}
        className="recipe-card"
      >
        <div className={`card-image-wrap${recipe.image ? '' : ' no-image'}`}>
          {recipe.image ? (
            <img
              src={recipe.image}
              alt={recipe.title}
              loading="lazy"
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
          <button
            ref={folderBtnRef}
            className="card-collection-btn"
            onClick={handleFolderClick}
            title="Add to collection"
          >
            📁
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
          {(recipe.collections ?? []).length > 0 && (
            <div className="card-collections">
              {(recipe.collections ?? []).map((name) => (
                <span key={name} className="collection-chip">{name}</span>
              ))}
            </div>
          )}
          {recipe.description && (
            <div className="card-desc">{recipe.description}</div>
          )}
        </div>
      </Link>

      {pickerAnchor && (
        <CollectionPicker
          recipeId={recipe.id}
          recipeCollections={recipe.collections}
          anchorRect={pickerAnchor}
          onUpdate={onCollectionUpdate}
          onClose={() => setPickerAnchor(null)}
        />
      )}
    </>
  )
}
