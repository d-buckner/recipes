import { useEffect, useMemo, useRef, useState } from 'react'
import { discoverSite, getSites, getSupportedSites, startScrape } from '../api'

interface AddSiteModalProps {
  onClose: () => void
  onDiscovered: () => void
}

type ModalStatus = 'idle' | 'running' | 'done' | 'error'

export function AddSiteModal({ onClose, onDiscovered }: AddSiteModalProps) {
  const [inputValue, setInputValue] = useState('')
  const [selectedHost, setSelectedHost] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [supportedSites, setSupportedSites] = useState<string[]>([])
  const [indexedSites, setIndexedSites] = useState<Set<string>>(new Set())
  const [status, setStatus] = useState<ModalStatus>('idle')
  const [discovered, setDiscovered] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [addedSite, setAddedSite] = useState('')

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getSupportedSites().then(setSupportedSites).catch(() => null)
    getSites().then((sites) => setIndexedSites(new Set(sites))).catch(() => null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
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

  const handleInputChange = (val: string) => {
    setInputValue(val)
    setSelectedHost('')
    setOpen(true)
    setActiveIdx(-1)
  }

  const handleSelect = (host: string) => {
    setInputValue(host)
    setSelectedHost(host)
    setOpen(false)
    setActiveIdx(-1)
    inputRef.current?.focus()
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
        void handleAdd()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  // Scroll highlighted item into view
  useEffect(() => {
    if (activeIdx < 0 || !listRef.current) return
    const el = listRef.current.children[activeIdx] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  const handleAdd = async () => {
    const host = selectedHost || inputValue.trim()
    if (!host || status === 'running') return
    const url = host.startsWith('http') ? host : `https://${host}`
    setAddedSite(host)
    setStatus('running')
    try {
      const res = await discoverSite(url)
      await startScrape()
      setDiscovered(res.discovered)
      setStatus('done')
      onDiscovered()
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong')
      setStatus('error')
    }
  }

  const canAdd = (selectedHost || inputValue.trim()).length > 0 && status === 'idle'

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add Recipe Site</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="add-site-form">
          {status === 'idle' || status === 'running' ? (
            <>
              <div className="form-field" ref={containerRef}>
                <label htmlFor="site-search">Recipe site</label>
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
                    disabled={status === 'running'}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onFocus={() => setOpen(true)}
                    onKeyDown={handleKeyDown}
                  />
                  {open && filtered.length > 0 && (
                    <ul ref={listRef} className="site-dropdown" role="listbox">
                      {filtered.map((host, i) => (
                        <li
                          key={host}
                          role="option"
                          className={[
                            'site-dropdown-item',
                            i === activeIdx ? 'is-active' : '',
                            indexedSites.has(host) ? 'is-indexed' : '',
                          ].filter(Boolean).join(' ')}
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
                    ? `${supportedSites.length} sites supported`
                    : 'Loading supported sites…'}
                </span>
              </div>

              {status === 'running' && (
                <div className="add-site-progress">
                  <div className="spinner" style={{ width: 24, height: 24, borderWidth: 2, marginBottom: 0 }} />
                  <span>Scanning sitemaps on <strong>{addedSite}</strong>… this may take a minute</span>
                </div>
              )}

              <div className="form-actions">
                <button className="btn ghost" onClick={onClose}>Cancel</button>
                <button className="btn primary" onClick={handleAdd} disabled={!canAdd}>
                  Add Site
                </button>
              </div>
            </>
          ) : status === 'done' ? (
            <div className="add-site-result">
              <div className="add-site-result-icon">✓</div>
              <div>
                <strong>{addedSite}</strong> added.{' '}
                {discovered > 0
                  ? <>{discovered.toLocaleString()} URLs queued — scraping in the background.</>
                  : <>No new URLs found (all may already be indexed).</>}
              </div>
              <button className="btn primary" style={{ marginTop: 12 }} onClick={onClose}>Done</button>
            </div>
          ) : (
            <div className="add-site-error">
              <strong>Failed to add {addedSite}</strong>
              <p>{errorMsg}</p>
              <div className="form-actions" style={{ marginTop: 8 }}>
                <button className="btn ghost" onClick={onClose}>Cancel</button>
                <button className="btn primary" onClick={() => setStatus('idle')}>Try Again</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
