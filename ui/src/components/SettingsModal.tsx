import { useEffect, useState } from 'react'
import { deleteSite, discoverSite, getSites, rescrapeAll, startScrape } from '../api'
import { Modal } from './Modal'
import type { ScrapeRunStats } from '../types'

interface SettingsModalProps {
  stats: ScrapeRunStats | null
  onClose: () => void
  onSiteDeleted?: () => void
}

type RescrapeState = 'idle' | 'confirming' | 'started'

type SiteAction =
  | { type: 'idle' }
  | { type: 'refreshing' }
  | { type: 'refreshed'; discovered: number }
  | { type: 'confirming-delete' }
  | { type: 'deleting' }

export function SettingsModal({ stats, onClose, onSiteDeleted }: SettingsModalProps) {
  const [rescrapeState, setRescrapeState] = useState<RescrapeState>('idle')
  const [queuedCount, setQueuedCount] = useState(0)
  const [sites, setSites] = useState<string[] | null>(null)
  const [siteActions, setSiteActions] = useState<Map<string, SiteAction>>(new Map())

  useEffect(() => {
    getSites().then(setSites).catch(() => setSites([]))
  }, [])

  function setSiteAction(hostname: string, action: SiteAction) {
    setSiteActions((prev) => new Map(prev).set(hostname, action))
  }

  function getSiteAction(hostname: string): SiteAction {
    return siteActions.get(hostname) ?? { type: 'idle' }
  }

  const handleRescrape = async () => {
    if (rescrapeState === 'idle') {
      setRescrapeState('confirming')
      return
    }
    const result = await rescrapeAll()
    setQueuedCount(result.queued)
    setRescrapeState('started')
  }

  const handleRefreshSite = async (hostname: string) => {
    setSiteAction(hostname, { type: 'refreshing' })
    try {
      const result = await discoverSite(`https://${hostname}`)
      if (result.discovered > 0) startScrape()
      setSiteAction(hostname, { type: 'refreshed', discovered: result.discovered })
    } catch {
      setSiteAction(hostname, { type: 'idle' })
    }
  }

  const handleDeleteSite = async (hostname: string) => {
    const action = getSiteAction(hostname)
    if (action.type !== 'confirming-delete') {
      setSiteAction(hostname, { type: 'confirming-delete' })
      return
    }
    setSiteAction(hostname, { type: 'deleting' })
    try {
      await deleteSite(hostname)
      setSites((prev) => prev ? prev.filter((s) => s !== hostname) : [])
      onSiteDeleted?.()
    } catch {
      setSiteAction(hostname, { type: 'idle' })
    }
  }

  return (
    <Modal title="Settings" onClose={onClose}>
      <div className="settings-body">
        <section className="settings-section">
          <h3 className="settings-section-title">Library</h3>
          {stats ? (
            <div className="settings-stats">
              <div className="settings-stat">
                <span className="settings-stat-value">{stats.complete.toLocaleString()}</span>
                <span className="settings-stat-label">complete</span>
              </div>
              {stats.discovered > 0 && (
                <div className="settings-stat">
                  <span className="settings-stat-value">{stats.discovered.toLocaleString()}</span>
                  <span className="settings-stat-label">pending</span>
                </div>
              )}
              {stats.processing > 0 && (
                <div className="settings-stat settings-stat--active">
                  <span className="settings-stat-value">{stats.processing.toLocaleString()}</span>
                  <span className="settings-stat-label">scraping</span>
                </div>
              )}
            </div>
          ) : (
            <p className="settings-empty">Loading…</p>
          )}
        </section>

        <section className="settings-section">
          <h3 className="settings-section-title">Sites</h3>
          {sites === null ? (
            <p className="settings-empty">Loading…</p>
          ) : sites.length === 0 ? (
            <p className="settings-empty">No sites indexed</p>
          ) : (
            <ul className="settings-site-list">
              {sites.map((site) => {
                const action = getSiteAction(site)
                return (
                  <li key={site} className="settings-site-item">
                    <span className="settings-site-name">{site}</span>
                    {action.type === 'confirming-delete' ? (
                      <div className="settings-action-confirm">
                        <button className="btn primary" onClick={() => handleDeleteSite(site)}>
                          Delete
                        </button>
                        <button className="btn ghost" onClick={() => setSiteAction(site, { type: 'idle' })}>
                          Cancel
                        </button>
                      </div>
                    ) : action.type === 'refreshed' ? (
                      <div className="settings-site-actions">
                        <span className="settings-action-done">
                          {action.discovered > 0 ? `✓ ${action.discovered} new` : '✓ Up to date'}
                        </span>
                        <button className="btn ghost" onClick={() => handleDeleteSite(site)}>
                          Delete
                        </button>
                      </div>
                    ) : (
                      <div className="settings-site-actions">
                        <button
                          className="btn ghost"
                          onClick={() => handleRefreshSite(site)}
                          disabled={action.type === 'refreshing' || action.type === 'deleting'}
                        >
                          {action.type === 'refreshing' ? 'Refreshing…' : 'Refresh'}
                        </button>
                        <button
                          className="btn ghost"
                          onClick={() => handleDeleteSite(site)}
                          disabled={action.type === 'refreshing' || action.type === 'deleting'}
                        >
                          {action.type === 'deleting' ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="settings-section">
          <h3 className="settings-section-title">Actions</h3>
          <div className="settings-action">
            <div className="settings-action-info">
              <p className="settings-action-label">Re-scrape all recipes</p>
              <p className="settings-action-desc">
                Re-fetches all {stats ? `${stats.complete.toLocaleString()} ` : ''}recipes to refresh content and download images locally.
              </p>
            </div>
            {rescrapeState === 'started' ? (
              <span className="settings-action-done">
                ✓ {queuedCount.toLocaleString()} queued
              </span>
            ) : rescrapeState === 'confirming' ? (
              <div className="settings-action-confirm">
                <button className="btn primary" onClick={handleRescrape}>Confirm</button>
                <button className="btn ghost" onClick={() => setRescrapeState('idle')}>Cancel</button>
              </div>
            ) : (
              <button
                className="btn ghost"
                onClick={handleRescrape}
                disabled={!stats || stats.complete === 0}
              >
                Re-scrape
              </button>
            )}
          </div>
        </section>
      </div>
    </Modal>
  )
}
