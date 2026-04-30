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
      const values = searchParams.getAll(type)
      if (values.length > 0) filters[type] = values
    }
    return filters
  }, [searchParams])

  // Count active filter types (not individual values) for the button label
  const activeFilterCount = Object.keys(activeFilters).length

  const toggleFilter = (type: TagFilterType, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const current = next.getAll(type)
      next.delete(type)
      if (current.includes(value)) {
        // Remove this value, keep the rest
        for (const v of current) {
          if (v !== value) next.append(type, v)
        }
      } else {
        // Add this value alongside existing ones
        for (const v of current) next.append(type, v)
        next.append(type, value)
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
