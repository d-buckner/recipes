import type { ActiveFilters, SearchResult, TagFilter } from '../types'
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
  onRemoveFromCollection?: (id: number) => void
  onTagFilter?: (filter: TagFilter) => void
  activeFilters?: ActiveFilters
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
  onRemoveFromCollection,
  onTagFilter,
  activeFilters,
}: RecipeGridProps) {
  // Show spinner only when loading with nothing to display yet.
  // When there are stale results, keep the grid mounted (dimmed) to avoid
  // the 1-column flash that occurs when the grid DOM unmounts and remounts.
  if (loading && recipes.length === 0) {
    return (
      <div className="state-message">
        <div className="spinner" />
        <p>Loading recipes…</p>
      </div>
    )
  }

  if (!loading && recipes.length === 0) {
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
      <div className={`recipe-grid${loading ? ' recipe-grid--loading' : ''}`}>
        {recipes.map((recipe) => (
          <RecipeCard
            key={recipe.id}
            recipe={recipe}
            onFavorite={onFavorite}
            onRemoveFromCollection={onRemoveFromCollection}
            onTagFilter={onTagFilter}
            activeFilters={activeFilters}
          />
        ))}
      </div>

      {hasMore && !loading && (
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
