interface SearchBarProps {
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  placeholder?: string
}

export function SearchBar({ value, onChange, disabled, placeholder }: SearchBarProps) {
  return (
    <div className="search-bar">
      <span className="search-icon">🔍</span>
      <input
        type="search"
        placeholder={placeholder ?? 'Search recipes, ingredients…'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  )
}
