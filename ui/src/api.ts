import type { Collection, DiscoverResponse, RecipeDetail, ScrapeRunStats, SearchResult } from './types'

const BASE = '/api'

export async function listRecipes(limit = 20, offset = 0): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/recipes?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('Failed to fetch recipes')
  return res.json() as Promise<SearchResult[]>
}

export async function searchRecipes(q: string, limit = 20, offset = 0): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/search?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`)
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
