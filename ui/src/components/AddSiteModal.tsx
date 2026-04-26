import { useEffect, useState } from 'react'
import { discoverSite, getSites, startScrape } from '../api'
import type { DiscoverResponse } from '../types'

interface AddSiteModalProps {
  onClose: () => void
  onDiscovered: () => void
}

export function AddSiteModal({ onClose, onDiscovered }: AddSiteModalProps) {
  const [siteUrl, setSiteUrl] = useState('')
  const [sitemapUrl, setSitemapUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DiscoverResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scrapeStarted, setScrapeStarted] = useState(false)
  const [existingSites, setExistingSites] = useState<string[]>([])

  useEffect(() => {
    getSites().then(setExistingSites).catch(() => null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const handleDiscover = async () => {
    if (!siteUrl.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await discoverSite(siteUrl.trim(), sitemapUrl.trim() || undefined)
      setResult(res)
      onDiscovered()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discovery failed')
    } finally {
      setLoading(false)
    }
  }

  const handleScrape = async () => {
    await startScrape()
    setScrapeStarted(true)
  }

  const canSubmit = siteUrl.trim().length > 0 && !loading

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add Recipe Site</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="add-site-form">
          {existingSites.length > 0 && (
            <div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px', fontWeight: 600 }}>
                Currently indexed sites
              </p>
              <ul className="sites-list">
                {existingSites.map((s) => <li key={s}>{s}</li>)}
              </ul>
            </div>
          )}

          <div className="form-field">
            <label htmlFor="site-url">Site URL *</label>
            <input
              id="site-url"
              type="url"
              placeholder="https://www.seriouseats.com"
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleDiscover() }}
              disabled={loading}
            />
            <span className="hint">Homepage of the recipe site. Used for automatic sitemap discovery.</span>
          </div>

          <div className="form-field">
            <label htmlFor="sitemap-url">Sitemap URL (optional)</label>
            <input
              id="sitemap-url"
              type="url"
              placeholder="https://www.seriouseats.com/sitemap_1.xml"
              value={sitemapUrl}
              onChange={(e) => setSitemapUrl(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleDiscover() }}
              disabled={loading}
            />
            <span className="hint">Provide a specific sitemap XML to skip homepage crawling.</span>
          </div>

          {error && (
            <div className="discover-error">
              ⚠️ {error}
            </div>
          )}

          {result && (
            <div className="discover-result">
              <div className="result-count">{result.discovered.toLocaleString()} URLs discovered</div>
              <p>
                Found <strong>{result.discovered}</strong> new recipe URLs from <strong>{result.site}</strong>.
                {result.discovered === 0 && ' All URLs may already be in the database.'}
              </p>
              {result.discovered > 0 && !scrapeStarted && (
                <button
                  className="btn primary"
                  style={{ marginTop: '10px' }}
                  onClick={handleScrape}
                >
                  ⚙️ Start Scraping Now
                </button>
              )}
              {scrapeStarted && (
                <p style={{ marginTop: '8px', fontWeight: 600 }}>
                  ✅ Scraping started in background! Check stats for progress.
                </p>
              )}
            </div>
          )}

          <div className="form-actions">
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button
              className="btn primary"
              onClick={handleDiscover}
              disabled={!canSubmit}
            >
              {loading ? 'Discovering…' : '🔍 Discover Recipes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
