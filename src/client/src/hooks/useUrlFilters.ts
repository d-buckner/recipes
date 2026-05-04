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
  minTime: number | null
  maxTime: number | null
  setMinTime: (value: number | null) => void
  setMaxTime: (value: number | null) => void
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

  const minTime = searchParams.get('min_time') !== null ? Number(searchParams.get('min_time')) : null
  const maxTime = searchParams.get('max_time') !== null ? Number(searchParams.get('max_time')) : null

  // Count active filter types (not individual values) for the button label.
  // Time min/max together count as one filter type.
  const activeFilterCount = Object.keys(activeFilters).length + (minTime !== null || maxTime !== null ? 1 : 0)

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

  const setMinTime = (value: number | null) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === null) next.delete('min_time')
      else next.set('min_time', String(value))
      return next
    })
  }

  const setMaxTime = (value: number | null) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === null) next.delete('max_time')
      else next.set('max_time', String(value))
      return next
    })
  }

  return { activeFilters, activeFilterCount, toggleFilter, removeFilter, clearFilters, minTime, maxTime, setMinTime, setMaxTime }
}
