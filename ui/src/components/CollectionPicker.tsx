import { useEffect, useState } from 'react'
import { addRecipeToCollection, createCollection, listCollections, removeRecipeFromCollection } from '../api'
import type { Collection } from '../types'

interface CollectionPickerProps {
  recipeId: number
  recipeCollections: string[]
  onUpdate: (updatedCollections: string[]) => void
}

export function CollectionPicker({ recipeId, recipeCollections, onUpdate }: CollectionPickerProps) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [membership, setMembership] = useState<Set<string>>(new Set(recipeCollections))
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    listCollections().then(setCollections).catch(() => null)
  }, [])

  useEffect(() => {
    setMembership(new Set(recipeCollections))
  }, [recipeCollections])

  const handleToggle = async (collection: Collection) => {
    const next = new Set(membership)
    if (next.has(collection.name)) {
      await removeRecipeFromCollection(collection.id, recipeId)
      next.delete(collection.name)
    } else {
      await addRecipeToCollection(collection.id, recipeId)
      next.add(collection.name)
    }
    setMembership(next)
    onUpdate([...next])
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const created = await createCollection(name)
      await addRecipeToCollection(created.id, recipeId)
      const next = new Set(membership)
      next.add(name)
      setMembership(next)
      onUpdate([...next])
      setNewName('')
      const updated = await listCollections()
      setCollections(updated)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="collection-picker">
      <div className="collection-picker-header">Collections</div>
      {collections.length === 0 && (
        <div className="collection-picker-empty">No collections yet — create one below</div>
      )}
      <ul className="collection-picker-list">
        {collections.map((c) => (
          <li key={c.id}>
            <label className="collection-picker-item">
              <input
                type="checkbox"
                checked={membership.has(c.name)}
                onChange={() => handleToggle(c)}
              />
              <span>{c.name}</span>
            </label>
          </li>
        ))}
      </ul>
      <form className="collection-picker-new" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="New collection…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          disabled={creating}
        />
        <button type="submit" disabled={!newName.trim() || creating}>+</button>
      </form>
    </div>
  )
}
