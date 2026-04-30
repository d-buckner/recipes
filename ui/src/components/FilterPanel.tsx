import { useEffect, useState } from 'react'
import { getFilterOptions } from '../api'
import type { ActiveFilters, FilterOption, FilterOptions, TagFilterType } from '../types'

const SECTIONS: { type: TagFilterType; label: string; emoji: string }[] = [
  { type: 'cuisine', label: 'Cuisine', emoji: '🗺' },
  { type: 'category', label: 'Category', emoji: '📂' },
  { type: 'author', label: 'Author', emoji: '👤' },
  { type: 'site', label: 'Site', emoji: '🌐' },
]

const TOP_N = 8

interface FilterPanelProps {
  activeFilters: ActiveFilters
  onToggle: (type: TagFilterType, value: string) => void
}

export function FilterPanel({ activeFilters, onToggle }: FilterPanelProps) {
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState<Partial<Record<TagFilterType, string>>>({})
  const [expanded, setExpanded] = useState<Set<TagFilterType>>(
    () => new Set(SECTIONS.map(s => s.type).filter(t => (activeFilters[t]?.length ?? 0) > 0))
  )
  const [showAll, setShowAll] = useState<Set<TagFilterType>>(new Set())

  useEffect(() => {
    getFilterOptions()
      .then(setOptions)
      .catch(() => setOptions(null))
      .finally(() => setLoading(false))
  }, [])

  const toggleSection = (type: TagFilterType) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const toggleShowAll = (type: TagFilterType) => {
    setShowAll((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const getVisible = (type: TagFilterType, opts: FilterOption[]): FilterOption[] => {
    const q = search[type]?.toLowerCase() ?? ''
    const filtered = q ? opts.filter((o) => o.value.toLowerCase().includes(q)) : opts
    if (q || showAll.has(type)) return filtered
    return filtered.slice(0, TOP_N)
  }

  if (loading) return <div className="filter-panel-loading">Loading…</div>
  if (!options) return <div className="filter-panel-loading">Failed to load filters.</div>

  return (
    <div className="filter-panel-sections">
      {SECTIONS.map(({ type, label, emoji }) => {
        const isExpanded = expanded.has(type)
        const isShowingAll = showAll.has(type)
        const activeVals = activeFilters[type] ?? []
        const allOpts = options[type] ?? []
        const q = search[type]?.toLowerCase() ?? ''
        const filtered = q ? allOpts.filter((o) => o.value.toLowerCase().includes(q)) : allOpts
        const visible = getVisible(type, allOpts)
        const hiddenCount = filtered.length - TOP_N

        return (
          <div key={type} className={`filter-section${isExpanded ? ' is-expanded' : ''}`}>
            <button className="filter-section-header" onClick={() => toggleSection(type)}>
              <span className="filter-section-label">{emoji} {label}</span>
              {activeVals.length > 0 && !isExpanded && (
                <span className="filter-section-count">{activeVals.length} selected</span>
              )}
              <span className="filter-section-chevron">{isExpanded ? '▾' : '▸'}</span>
            </button>

            {!isExpanded && activeVals.length > 0 && (
              <div className="filter-section-active">
                {activeVals.map((val) => (
                  <button
                    key={val}
                    className="filter-section-chip"
                    onClick={(e) => { e.stopPropagation(); onToggle(type, val) }}
                  >
                    {val} ×
                  </button>
                ))}
              </div>
            )}

            {isExpanded && (
              <div className="filter-section-body">
                {allOpts.length > TOP_N && (
                  <input
                    className="filter-section-search"
                    type="text"
                    placeholder={`Search ${label.toLowerCase()}…`}
                    value={search[type] ?? ''}
                    onChange={(e) => {
                      setSearch((s) => ({ ...s, [type]: e.target.value }))
                      setShowAll((prev) => { const next = new Set(prev); next.delete(type); return next })
                    }}
                  />
                )}
                {visible.length === 0 ? (
                  <span className="filter-section-empty">No options</span>
                ) : (
                  <ul className="filter-option-list">
                    {visible.map((opt) => (
                      <li key={opt.value}>
                        <button
                          className={`filter-option-btn${activeVals.includes(opt.value) ? ' is-active' : ''}`}
                          onClick={() => onToggle(type, opt.value)}
                          title={opt.value}
                        >
                          <span className="filter-option-value">{opt.value}</span>
                          <span className="filter-option-count">{opt.count}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {!q && hiddenCount > 0 && !isShowingAll && (
                  <button className="filter-show-more" onClick={() => toggleShowAll(type)}>
                    + {hiddenCount} more
                  </button>
                )}
                {!q && isShowingAll && (
                  <button className="filter-show-more" onClick={() => toggleShowAll(type)}>
                    Show less
                  </button>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
