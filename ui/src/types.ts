export interface Collection {
  id: number
  name: string
  recipe_count: number
  created_at: string
}

export interface SearchResult {
  id: number
  url: string
  site: string
  title: string
  description: string
  total_time: number | null
  yields: string | null
  image: string | null
  has_thumbnail: boolean
  is_favorite: boolean
  collections: string[]
}

export interface RecipeJson {
  title?: string
  description?: string
  image?: string
  total_time?: number
  yields?: string
  ingredients?: string[]
  instructions?: string
  instructions_list?: string[]
  nutrients?: Record<string, string>
  author?: string
  cuisine?: string
  category?: string
  keywords?: string[]
}

export interface RecipeDetail {
  id: number
  url: string
  site: string
  status: string
  recipe_json: RecipeJson | null
  collections: string[]
}

export interface ScrapeRunStats {
  total: number
  discovered: number
  processing: number
  complete: number
  failed: number
  unavailable: number
  favorites: number
}

export interface DiscoverResponse {
  discovered: number
  site: string
}
