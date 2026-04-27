import { useEffect, useRef, useState, useCallback } from 'react'
import {
  addFavorite,
  createCollection,
  deleteCollection,
  getFavorites,
  getStats,
  listCollectionRecipes,
  listCollections,
  listRecipes,
  removeFavorite,
  removeRecipeFromCollection,
  searchRecipes,
} from '../api'

import { AddSiteDropdown } from '../components/AddSiteDropdown'
import { RecipeGrid } from '../components/RecipeGrid'
import { SearchBar } from '../components/SearchBar'
import { StatsBar } from '../components/StatsBar'
import type { Collection, SearchResult, ScrapeRunStats } from '../types'

type Tab = 'explore' | 'favorites' | 'collections'

const LIMIT = 20

export function HomePage() {
  const [tab, setTab] = useState<Tab>('explore')
  const [query, setQuery] = useState('')
  const [recipes, setRecipes] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [showAddSite, setShowAddSite] = useState(false)
  const [stats, setStats] = useState<ScrapeRunStats | null>(null)

  // Collections state
  const [collections, setCollections] = useState<Collection[]>([])
  const [selectedCollection, setSelectedCollection] = useState<Collection | null>(null)
  const [newCollectionName, setNewCollectionName] = useState('')
  const [creatingCollection, setCreatingCollection] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const addSiteAnchorRef = useRef<HTMLDivElement>(null)

  const refreshStats = useCallback(() => getStats().then(setStats).catch(() => null), [])

  const refreshCollections = () => listCollections().then(setCollections).catch(() => null)

  useEffect(() => {
    refreshStats()
    const interval = setInterval(refreshStats, 15_000)
    return () => clearInterval(interval)
  }, [refreshStats])

  // Close the add-site dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (addSiteAnchorRef.current && !addSiteAnchorRef.current.contains(e.target as Node)) {
        setShowAddSite(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Load favorites when on that tab
  useEffect(() => {
    if (tab !== 'favorites') return
    setLoading(true)
    setHasMore(false)
    getFavorites()
      .then(setRecipes)
      .catch(() => setRecipes([]))
      .finally(() => setLoading(false))
  }, [tab])

  // Load collections list when on collections tab
  useEffect(() => {
    if (tab !== 'collections') return
    refreshCollections()
  }, [tab])

  // Load collection recipes when a collection is selected
  useEffect(() => {
    if (tab !== 'collections' || !selectedCollection) return
    setLoading(true)
    setPage(0)
    listCollectionRecipes(selectedCollection.id, LIMIT, 0)
      .then((results) => {
        setRecipes(results)
        setHasMore(results.length === LIMIT)
      })
      .catch(() => setRecipes([]))
      .finally(() => setLoading(false))
  }, [tab, selectedCollection])

  // All-recipes or search when on explore tab
  useEffect(() => {
    if (tab !== 'explore') return
    if (debounceRef.current) clearTimeout(debounceRef.current)

    // Don't clear recipes here — keep stale results visible (dimmed) while
    // the new fetch is in flight so the grid stays mounted and avoids a
    // 1-column layout flash on remount.
    setPage(0)

    if (!query.trim()) {
      setLoading(true)
      listRecipes(LIMIT, 0)
        .then((results) => {
          setRecipes(results)
          setHasMore(results.length === LIMIT)
        })
        .catch(() => setRecipes([]))
        .finally(() => setLoading(false))
      return
    }

    setLoading(true)
    debounceRef.current = setTimeout(() => {
      searchRecipes(query, LIMIT, 0)
        .then((results) => {
          setRecipes(results)
          setHasMore(results.length === LIMIT)
        })
        .catch(() => setRecipes([]))
        .finally(() => setLoading(false))
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, tab])

  const handleLoadMore = async () => {
    const nextPage = page + 1
    setLoadingMore(true)
    try {
      let results: SearchResult[]
      if (tab === 'collections' && selectedCollection) {
        results = await listCollectionRecipes(selectedCollection.id, LIMIT, nextPage * LIMIT)
      } else if (query.trim()) {
        results = await searchRecipes(query, LIMIT, nextPage * LIMIT)
      } else {
        results = await listRecipes(LIMIT, nextPage * LIMIT)
      }
      setRecipes((prev) => [...prev, ...results])
      setHasMore(results.length === LIMIT)
      setPage(nextPage)
    } finally {
      setLoadingMore(false)
    }
  }

  const handleFavorite = async (id: number, wasFavorite: boolean) => {
    if (wasFavorite) {
      await removeFavorite(id)
    } else {
      await addFavorite(id)
    }
    setRecipes((prev) =>
      prev.map((r) => r.id === id ? { ...r, is_favorite: !wasFavorite } : r)
    )
    if (tab === 'favorites' && wasFavorite) {
      setRecipes((prev) => prev.filter((r) => r.id !== id))
    }
    refreshStats()
  }

  const handleTabChange = (next: Tab) => {
    setTab(next)
    setRecipes([])
    setQuery('')
    setPage(0)
    setHasMore(false)
    setSelectedCollection(null)
  }

  const handleCreateCollection = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newCollectionName.trim()
    if (!name) return
    setCreatingCollection(true)
    try {
      await createCollection(name)
      setNewCollectionName('')
      refreshCollections()
    } finally {
      setCreatingCollection(false)
    }
  }

  const handleDeleteCollection = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    await deleteCollection(id)
    refreshCollections()
  }

  const handleRemoveFromCollection = async (recipeId: number) => {
    if (!selectedCollection) return
    await removeRecipeFromCollection(selectedCollection.id, recipeId)
    setRecipes((prev) => prev.filter((r) => r.id !== recipeId))
  }

  const emptyState = tab === 'favorites'
    ? { icon: '♥', title: 'No saved recipes', body: 'Heart a recipe card to save it here.' }
    : tab === 'collections' && selectedCollection
      ? { icon: '📁', title: 'No recipes in this collection', body: 'Use the folder button on recipe cards to add recipes.' }
      : query.trim()
        ? { icon: '🔎', title: `No results for "${query}"`, body: 'Try different keywords or check your spelling.' }
        : { icon: '🍳', title: 'No recipes yet', body: 'Add a site to start discovering recipes.' }

  const showRecipeGrid = tab !== 'collections' || selectedCollection !== null

  return (
    <>
      <header className="header">
        <span className="logo">🍴 Recipes</span>
        <SearchBar value={query} onChange={setQuery} disabled={tab !== 'explore'} />
        <div className="add-site-anchor" ref={addSiteAnchorRef}>
          <button className="btn-add" onClick={() => setShowAddSite((v) => !v)}>+ Add Site</button>
          {showAddSite && (
            <AddSiteDropdown
              onClose={() => setShowAddSite(false)}
              onDiscovered={refreshStats}
            />
          )}
        </div>
      </header>

      {stats && <StatsBar stats={stats} />}

      <nav className="tabs">
        <button
          className={tab === 'explore' ? 'active' : ''}
          onClick={() => handleTabChange('explore')}
        >
          Explore
        </button>
        <button
          className={tab === 'favorites' ? 'active' : ''}
          onClick={() => handleTabChange('favorites')}
        >
          ♥ Favorites{stats && stats.favorites > 0 ? ` (${stats.favorites})` : ''}
        </button>
        <button
          className={tab === 'collections' ? 'active' : ''}
          onClick={() => handleTabChange('collections')}
        >
          📁 Collections{collections.length > 0 ? ` (${collections.length})` : ''}
        </button>
      </nav>

      {tab === 'collections' && !selectedCollection && (
        <div className="collections-page">
          <div className="collections-grid">
            {collections.map((c) => (
              <div
                key={c.id}
                className="collection-tile"
                onClick={() => setSelectedCollection(c)}
              >
                <div className="collection-tile-icon">📁</div>
                <div className="collection-tile-name">{c.name}</div>
                <div className="collection-tile-count">{c.recipe_count} recipe{c.recipe_count !== 1 ? 's' : ''}</div>
                <button
                  className="collection-tile-delete"
                  onClick={(e) => handleDeleteCollection(e, c.id)}
                  title="Delete collection"
                >
                  ✕
                </button>
              </div>
            ))}
            <form className="collection-tile collection-tile-new" onSubmit={handleCreateCollection}>
              <div className="collection-tile-icon">➕</div>
              <input
                type="text"
                placeholder="New collection…"
                value={newCollectionName}
                onChange={(e) => setNewCollectionName(e.target.value)}
                disabled={creatingCollection}
                onClick={(e) => e.stopPropagation()}
              />
              <button type="submit" disabled={!newCollectionName.trim() || creatingCollection}>
                Create
              </button>
            </form>
          </div>
          {collections.length === 0 && (
            <div className="state-message">
              <div className="state-icon">📁</div>
              <h3>No collections yet</h3>
              <p>Create a collection above and use the folder button on recipe cards to organise recipes.</p>
            </div>
          )}
        </div>
      )}

      {tab === 'collections' && selectedCollection && (
        <div className="collection-drill-header">
          <button className="btn-back" onClick={() => setSelectedCollection(null)}>← Back</button>
          <span className="collection-drill-title">📁 {selectedCollection.name}</span>
        </div>
      )}

      {showRecipeGrid && (
        <RecipeGrid
          recipes={recipes}
          loading={loading}
          loadingMore={loadingMore}
          hasMore={hasMore && tab !== 'favorites'}
          onLoadMore={handleLoadMore}
          emptyIcon={emptyState.icon}
          emptyTitle={emptyState.title}
          emptyBody={emptyState.body}
          onFavorite={handleFavorite}
          onRemoveFromCollection={selectedCollection ? handleRemoveFromCollection : undefined}
        />
      )}

    </>
  )
}
