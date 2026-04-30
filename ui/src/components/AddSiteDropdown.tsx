import { useEffect, useMemo, useRef, useState } from 'react'
import { getSites, getSupportedSites } from '../api'

interface AddSiteDropdownProps {
  onClose: () => void
  onAdd: (host: string, url: string) => void
}

export function AddSiteDropdown({ onClose, onAdd }: AddSiteDropdownProps) {
  const [inputValue, setInputValue] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [supportedSites, setSupportedSites] = useState<string[]>([])
  const [indexedSites, setIndexedSites] = useState<Set<string>>(new Set())

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const comboRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getSupportedSites().then(setSupportedSites).catch(() => null)
    getSites().then((sites) => setIndexedSites(new Set(sites))).catch(() => null)
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (comboRef.current && !comboRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = useMemo(() => {
    const q = inputValue.toLowerCase().trim()
    if (!q) return supportedSites.slice(0, 80)
    return supportedSites.filter((s) => s.includes(q)).slice(0, 80)
  }, [inputValue, supportedSites])

  const handleSelect = (host: string) => {
    const url = host.startsWith('http') ? host : `https://${host}`
    onAdd(host, url)
    onClose()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) {
      if (e.key === 'ArrowDown') { setOpen(true); setActiveIdx(0) }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && filtered[activeIdx]) {
        handleSelect(filtered[activeIdx])
      } else {
        setOpen(false)
        handleAdd()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  useEffect(() => {
    if (activeIdx < 0 || !listRef.current) return
    const el = listRef.current.children[activeIdx] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  const handleAdd = () => {
    const host = inputValue.trim()
    if (!host) return
    const url = host.startsWith('http') ? host : `https://${host}`
    onAdd(host, url)
    onClose()
  }

  const canAdd = inputValue.trim().length > 0

  return (
    <div className="add-site-form">
      <div className="form-field" ref={comboRef}>
        <label htmlFor="site-search">Add a recipe site</label>
        <div className="site-combobox">
          <input
            ref={inputRef}
            id="site-search"
            type="text"
            className="site-combobox-input"
            placeholder="Search 500+ supported sites…"
            value={inputValue}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => { setInputValue(e.target.value); setOpen(true); setActiveIdx(-1) }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
          />
          {open && filtered.length > 0 && (
            <ul ref={listRef} className="site-dropdown" role="listbox">
              {filtered.map((host, i) => (
                <li
                  key={host}
                  role="option"
                  className={['site-dropdown-item', i === activeIdx ? 'is-active' : ''].filter(Boolean).join(' ')}
                  onMouseDown={(e) => { e.preventDefault(); handleSelect(host) }}
                  onMouseEnter={() => setActiveIdx(i)}
                >
                  <span className="site-dropdown-host">{host}</span>
                  {indexedSites.has(host) && (
                    <span className="site-dropdown-badge">indexed</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
        <span className="hint">
          {supportedSites.length > 0
            ? `${supportedSites.length.toLocaleString()} sites supported`
            : 'Loading…'}
        </span>
      </div>
      <div className="form-actions">
        <button className="btn primary" onClick={handleAdd} disabled={!canAdd}>
          Add Site
        </button>
      </div>
    </div>
  )
}
