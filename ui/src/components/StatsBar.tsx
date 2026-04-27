import type { ScrapeRunStats } from '../types'

interface StatsBarProps {
  stats: ScrapeRunStats
}

export function StatsBar({ stats }: StatsBarProps) {
  const importing = stats.discovered + stats.processing
  return (
    <div className="stats-bar">
      <span className="stat-item">📖 <strong>{stats.complete.toLocaleString()}</strong> recipes</span>
      {importing > 0 && (
        <span className="stat-item stat-item--active">⚡ <strong>{importing.toLocaleString()}</strong> being added</span>
      )}
      <span className="stat-item">♥ <strong>{stats.favorites.toLocaleString()}</strong> saved</span>
    </div>
  )
}
