import type { SearchResult } from '../types'
import { RecipeCard } from './RecipeCard'

interface RecipeGridProps {
  recipes: SearchResult[]
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  onLoadMore: () => void
  emptyIcon: string
  emptyTitle: string
  emptyBody: string
  onFavorite: (id: number, isFavorite: boolean) => void
  onCollectionUpdate: () => void
}

export function RecipeGrid({
  recipes,
  loading,
  loadingMore,
  hasMore,
  onLoadMore,
  emptyIcon,
  emptyTitle,
  emptyBody,
  onFavorite,
  onCollectionUpdate,
}: RecipeGridProps) {
  if (loading) {
    return (
      <div className="state-message">
        <div className="spinner" />
        <p>Loading recipes…</p>
      </div>
    )
  }

  if (recipes.length === 0) {
    return (
      <div className="state-message">
        <div className="state-icon">{emptyIcon}</div>
        <h3>{emptyTitle}</h3>
        <p>{emptyBody}</p>
      </div>
    )
  }

  return (
    <>
      <div className="recipe-grid">
        {recipes.map((recipe) => (
          <RecipeCard
            key={recipe.id}
            recipe={recipe}
            onFavorite={onFavorite}
            onCollectionUpdate={onCollectionUpdate}
          />
        ))}
      </div>

      {hasMore && (
        <div className="load-more-wrap">
          <button
            className="btn-load-more"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </>
  )
}
