interface SearchBarProps {
  value: string
  onChange: (v: string) => void
  disabled?: boolean
}

export function SearchBar({ value, onChange, disabled }: SearchBarProps) {
  return (
    <div className="search-bar">
      <span className="search-icon">🔍</span>
      <input
        type="search"
        placeholder="Search recipes, ingredients…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  )
}
