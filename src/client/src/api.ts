import type { ActiveFilters, Collection, DiscoverResponse, FilterOptions, GroceryListItem, RecipeDetail, ScrapeRunStats, SearchResult } from './types'

const BASE = '/api'

function applyFilters(params: URLSearchParams, filters?: ActiveFilters): void {
  if (!filters) return
  for (const [key, values] of Object.entries(filters)) {
    if (values) {
      for (const value of values) params.append(key, value)
    }
  }
}

export async function listRecipes(limit = 20, offset = 0, filters?: ActiveFilters, minTime?: number | null, maxTime?: number | null): Promise<SearchResult[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  applyFilters(params, filters)
  if (minTime != null) params.set('min_time', String(minTime))
  if (maxTime != null) params.set('max_time', String(maxTime))
  const res = await fetch(`${BASE}/recipes?${params}`)
  if (!res.ok) throw new Error('Failed to fetch recipes')
  return res.json() as Promise<SearchResult[]>
}

export async function searchRecipes(q: string, limit = 20, offset = 0, filters?: ActiveFilters, minTime?: number | null, maxTime?: number | null): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset) })
  applyFilters(params, filters)
  if (minTime != null) params.set('min_time', String(minTime))
  if (maxTime != null) params.set('max_time', String(maxTime))
  const res = await fetch(`${BASE}/search?${params}`)
  if (!res.ok) throw new Error('Search failed')
  return res.json() as Promise<SearchResult[]>
}

export async function getFavorites(): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/favorites`)
  if (!res.ok) throw new Error('Failed to fetch favorites')
  return res.json() as Promise<SearchResult[]>
}

export async function addFavorite(id: number): Promise<void> {
  await fetch(`${BASE}/favorites/${id}`, { method: 'POST' })
}

export async function removeFavorite(id: number): Promise<void> {
  await fetch(`${BASE}/favorites/${id}`, { method: 'DELETE' })
}

export async function getRecipe(id: number): Promise<RecipeDetail> {
  const res = await fetch(`${BASE}/recipes/${id}`)
  if (!res.ok) throw new Error('Recipe not found')
  return res.json() as Promise<RecipeDetail>
}

export async function getStats(): Promise<ScrapeRunStats> {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json() as Promise<ScrapeRunStats>
}

export async function getFilterOptions(): Promise<FilterOptions> {
  const res = await fetch(`${BASE}/filters`)
  if (!res.ok) throw new Error('Failed to fetch filter options')
  return res.json() as Promise<FilterOptions>
}

export async function getSites(): Promise<string[]> {
  const res = await fetch(`${BASE}/sites`)
  if (!res.ok) throw new Error('Failed to fetch sites')
  return res.json() as Promise<string[]>
}

export async function getSupportedSites(): Promise<string[]> {
  const res = await fetch(`${BASE}/sites/supported`)
  if (!res.ok) throw new Error('Failed to fetch supported sites')
  return res.json() as Promise<string[]>
}

export async function deleteSite(hostname: string): Promise<{ site: string; deleted: number }> {
  const res = await fetch(`${BASE}/sites/${encodeURIComponent(hostname)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete site')
  return res.json() as Promise<{ site: string; deleted: number }>
}

export async function discoverSite(siteUrl: string, sitemapUrl?: string): Promise<DiscoverResponse> {
  const res = await fetch(`${BASE}/sites/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ site_url: siteUrl, sitemap_url: sitemapUrl || null }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || 'Discovery failed')
  }
  return res.json() as Promise<DiscoverResponse>
}

export async function startScrape(): Promise<void> {
  await fetch(`${BASE}/sites/scrape`, { method: 'POST' })
}

export async function rescrapeAll(): Promise<{ status: string; queued: number }> {
  const res = await fetch(`${BASE}/sites/rescrape`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to start rescrape')
  return res.json() as Promise<{ status: string; queued: number }>
}

export async function reembedAll(): Promise<void> {
  const res = await fetch(`${BASE}/embed/backfill`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start re-embed' }))
    throw new Error(err.detail ?? 'Failed to start re-embed')
  }
}

export async function retemplatizeAll(): Promise<void> {
  const res = await fetch(`${BASE}/templatize/backfill`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start re-templatize' }))
    throw new Error(err.detail ?? 'Failed to start re-templatize')
  }
}

export async function listCollections(): Promise<Collection[]> {
  const res = await fetch(`${BASE}/collections`)
  if (!res.ok) throw new Error('Failed to fetch collections')
  return res.json() as Promise<Collection[]>
}

export async function createCollection(name: string): Promise<Collection> {
  const res = await fetch(`${BASE}/collections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error('Failed to create collection')
  return res.json() as Promise<Collection>
}

export async function deleteCollection(id: number): Promise<void> {
  await fetch(`${BASE}/collections/${id}`, { method: 'DELETE' })
}

export async function renameCollection(id: number, name: string): Promise<Collection> {
  const res = await fetch(`${BASE}/collections/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error('Failed to rename collection')
  return res.json() as Promise<Collection>
}

export async function listCollectionRecipes(id: number, limit = 20, offset = 0): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/collections/${id}/recipes?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('Failed to fetch collection recipes')
  return res.json() as Promise<SearchResult[]>
}

export async function addRecipeToCollection(collectionId: number, recipeId: number): Promise<void> {
  await fetch(`${BASE}/collections/${collectionId}/recipes/${recipeId}`, { method: 'POST' })
}

export async function removeRecipeFromCollection(collectionId: number, recipeId: number): Promise<void> {
  await fetch(`${BASE}/collections/${collectionId}/recipes/${recipeId}`, { method: 'DELETE' })
}

export async function addRecipeToGroceryList(recipeId: number, scaleFactor: number): Promise<GroceryListItem[]> {
  const params = new URLSearchParams({ scale_factor: String(scaleFactor) })
  const res = await fetch(`${BASE}/grocery-list/from-recipe/${recipeId}?${params}`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to add to grocery list')
  return res.json() as Promise<GroceryListItem[]>
}

export async function getGroceryList(): Promise<GroceryListItem[]> {
  const res = await fetch(`${BASE}/grocery-list`)
  if (!res.ok) throw new Error('Failed to fetch grocery list')
  return res.json() as Promise<GroceryListItem[]>
}

export async function addGroceryItem(raw: string): Promise<GroceryListItem> {
  const res = await fetch(`${BASE}/grocery-list/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw }),
  })
  if (!res.ok) throw new Error('Failed to add grocery item')
  return res.json() as Promise<GroceryListItem>
}

export async function updateGroceryItem(id: number, updates: Partial<Pick<GroceryListItem, 'checked' | 'ingredient' | 'qty_num' | 'qty_den' | 'unit'>>): Promise<GroceryListItem> {
  const res = await fetch(`${BASE}/grocery-list/items/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error('Failed to update grocery item')
  return res.json() as Promise<GroceryListItem>
}

export async function deleteGroceryItem(id: number): Promise<void> {
  await fetch(`${BASE}/grocery-list/items/${id}`, { method: 'DELETE' })
}

export async function clearGroceryList(checkedOnly = false): Promise<void> {
  const params = checkedOnly ? '?checked_only=true' : ''
  await fetch(`${BASE}/grocery-list${params}`, { method: 'DELETE' })
}

export async function mergeGroceryItems(itemId: number, otherId: number): Promise<GroceryListItem> {
  const res = await fetch(`${BASE}/grocery-list/items/${itemId}/merge/${otherId}`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to merge grocery items')
  return res.json() as Promise<GroceryListItem>
}
