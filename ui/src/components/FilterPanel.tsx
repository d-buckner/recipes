import { useEffect, useRef, useState } from 'react'
import { getFilterOptions } from '../api'
import type { ActiveFilters, FilterOption, FilterOptions, TagFilterType } from '../types'

const SECTIONS: { type: TagFilterType; label: string; emoji: string }[] = [
  { type: 'cuisine', label: 'Cuisine', emoji: '🗺' },
  { type: 'category', label: 'Category', emoji: '📂' },
  { type: 'author', label: 'Author', emoji: '👤' },
  { type: 'site', label: 'Site', emoji: '🌐' },
]

interface FilterPanelProps {
  activeFilters: ActiveFilters
  onToggle: (type: TagFilterType, value: string) => void
  onClose: () => void
}

export function FilterPanel({ activeFilters, onToggle, onClose }: FilterPanelProps) {
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState<Partial<Record<TagFilterType, string>>>({})
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getFilterOptions()
      .then(setOptions)
      .catch(() => setOptions(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const filteredOptions = (type: TagFilterType, opts: FilterOption[]): FilterOption[] => {
    const q = search[type]?.toLowerCase() ?? ''
    if (!q) return opts
    return opts.filter((o) => o.value.toLowerCase().includes(q))
  }

  return (
    <>
    <div className="filter-backdrop" onClick={onClose} />
    <div className="filter-panel" ref={panelRef}>
      <div className="filter-panel-header">
        <span className="filter-panel-title">Filters</span>
        <button className="modal-close" onClick={onClose} title="Close">×</button>
      </div>

      {loading && (
        <div className="filter-panel-loading">Loading…</div>
      )}

      {!loading && !options && (
        <div className="filter-panel-loading">Failed to load filters.</div>
      )}

      {!loading && options && (
        <div className="filter-panel-sections">
          {SECTIONS.map(({ type, label, emoji }) => {
            const opts = filteredOptions(type, options[type] ?? [])
            const active = activeFilters[type]
            return (
              <div key={type} className="filter-section">
                <div className="filter-section-label">{emoji} {label}</div>
                {(options[type]?.length ?? 0) > 8 && (
                  <input
                    className="filter-section-search"
                    type="text"
                    placeholder={`Search ${label.toLowerCase()}…`}
                    value={search[type] ?? ''}
                    onChange={(e) => setSearch((s) => ({ ...s, [type]: e.target.value }))}
                  />
                )}
                {opts.length === 0 ? (
                  <span className="filter-section-empty">No options</span>
                ) : (
                  <ul className="filter-option-list">
                    {opts.map((opt) => (
                      <li key={opt.value}>
                        <button
                          className={`filter-option-btn${active === opt.value ? ' is-active' : ''}`}
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
              </div>
            )
          })}
        </div>
      )}
    </div>
    </>
  )
}
