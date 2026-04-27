import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ActiveFilters, TagFilterType } from '../types'

const FILTER_TYPES: TagFilterType[] = ['author', 'cuisine', 'category', 'site']

interface UseUrlFiltersResult {
  activeFilters: ActiveFilters
  activeFilterCount: number
  toggleFilter: (type: TagFilterType, value: string) => void
  removeFilter: (type: TagFilterType) => void
  clearFilters: () => void
}

export function useUrlFilters(): UseUrlFiltersResult {
  const [searchParams, setSearchParams] = useSearchParams()

  const activeFilters = useMemo((): ActiveFilters => {
    const filters: ActiveFilters = {}
    for (const type of FILTER_TYPES) {
      const value = searchParams.get(type)
      if (value) filters[type] = value
    }
    return filters
  }, [searchParams])

  const activeFilterCount = Object.keys(activeFilters).length

  const toggleFilter = (type: TagFilterType, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (next.get(type) === value) {
        next.delete(type)
      } else {
        next.set(type, value)
      }
      return next
    })
  }

  const removeFilter = (type: TagFilterType) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete(type)
      return next
    })
  }

  const clearFilters = () => {
    setSearchParams(new URLSearchParams())
  }

  return { activeFilters, activeFilterCount, toggleFilter, removeFilter, clearFilters }
}
