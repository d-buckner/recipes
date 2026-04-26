import type { ScrapeRunStats } from '../types'

interface StatsBarProps {
  stats: ScrapeRunStats
}

export function StatsBar({ stats }: StatsBarProps) {
  return (
    <div className="stats-bar">
      <span className="stat-item">📚 <strong>{stats.total.toLocaleString()}</strong> total</span>
      <span className="stat-item">✅ <strong>{stats.complete.toLocaleString()}</strong> scraped</span>
      {stats.discovered > 0 && (
        <span className="stat-item">🔍 <strong>{stats.discovered.toLocaleString()}</strong> queued</span>
      )}
      {stats.processing > 0 && (
        <span className="stat-item">⚙️ <strong>{stats.processing}</strong> processing</span>
      )}
      {stats.failed > 0 && (
        <span className="stat-item">❌ <strong>{stats.failed}</strong> failed</span>
      )}
      <span className="stat-item">♥ <strong>{stats.favorites.toLocaleString()}</strong> saved</span>
    </div>
  )
}
