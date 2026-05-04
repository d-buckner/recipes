export interface Collection {
  id: number
  name: string
  recipe_count: number
  created_at: string
}

export type TagFilterType = 'author' | 'cuisine' | 'category' | 'site'

export interface TagFilter {
  type: TagFilterType
  value: string
}

export type ActiveFilters = Partial<Record<TagFilterType, string[]>>

export interface FilterOption {
  value: string
  count: number
}

export type FilterOptions = Record<TagFilterType, FilterOption[]>

export interface SearchResult {
  id: number
  url: string
  site: string
  title: string
  description: string
  total_time: number | null
  yields: string | null
  image: string | null
  site_name: string | null
  author: string | null
  cuisines: string[]
  categories: string[]
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
  cuisine?: string[]
  category?: string[]
  keywords?: string[]
}

export interface RecipeDetail {
  id: number
  url: string
  site: string
  status: string
  recipe_json: RecipeJson | null
  collections: string[]
  has_thumbnail: boolean
  has_image: boolean
  ingredients_template: string[] | null
  instructions_list_template: string[] | null
}

export interface GroceryListItem {
  id: number
  qty_num: number | null
  qty_den: number
  qty_display: string | null
  unit: string | null
  ingredient: string
  original_raw: string[]
  recipe_ids: number[]
  recipe_titles: Record<string, string>
  checked: boolean
  approximate: boolean
  sort_order: number
  created_at: string
  updated_at: string
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
