import { useState } from 'react'
import { rescrapeAll } from '../api'
import { Modal } from './Modal'
import type { ScrapeRunStats } from '../types'

interface SettingsModalProps {
  stats: ScrapeRunStats | null
  onClose: () => void
}

type RescrapeState = 'idle' | 'confirming' | 'started'

export function SettingsModal({ stats, onClose }: SettingsModalProps) {
  const [rescrapeState, setRescrapeState] = useState<RescrapeState>('idle')
  const [queuedCount, setQueuedCount] = useState(0)

  const handleRescrape = async () => {
    if (rescrapeState === 'idle') {
      setRescrapeState('confirming')
      return
    }
    const result = await rescrapeAll()
    setQueuedCount(result.queued)
    setRescrapeState('started')
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
              {stats.failed > 0 && (
                <div className="settings-stat settings-stat--warn">
                  <span className="settings-stat-value">{stats.failed.toLocaleString()}</span>
                  <span className="settings-stat-label">failed</span>
                </div>
              )}
            </div>
          ) : (
            <p className="settings-empty">Loading…</p>
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
