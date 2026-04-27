import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { addRecipeToCollection, createCollection, listCollections, removeRecipeFromCollection } from '../api'
import type { Collection } from '../types'

interface CollectionPickerProps {
  recipeId: number
  recipeCollections: string[]
  anchorRect: DOMRect
  onUpdate: () => void
  onClose: () => void
}

export function CollectionPicker({ recipeId, recipeCollections, anchorRect, onUpdate, onClose }: CollectionPickerProps) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listCollections().then(setCollections).catch(() => null)
  }, [])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    const handleScroll = () => onClose()
    document.addEventListener('mousedown', handleClickOutside)
    window.addEventListener('scroll', handleScroll, true)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      window.removeEventListener('scroll', handleScroll, true)
    }
  }, [onClose])

  const isInCollection = (name: string) => (recipeCollections ?? []).includes(name)

  const handleToggle = async (collection: Collection) => {
    if (isInCollection(collection.name)) {
      await removeRecipeFromCollection(collection.id, recipeId)
    } else {
      await addRecipeToCollection(collection.id, recipeId)
    }
    onUpdate()
    const updated = await listCollections()
    setCollections(updated)
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const created = await createCollection(name)
      await addRecipeToCollection(created.id, recipeId)
      setNewName('')
      onUpdate()
      const updated = await listCollections()
      setCollections(updated)
    } finally {
      setCreating(false)
    }
  }

  // Align right edge of picker with right edge of button, open below
  const style: React.CSSProperties = {
    position: 'fixed',
    top: anchorRect.bottom + 4,
    right: window.innerWidth - anchorRect.right,
    zIndex: 1000,
  }

  return createPortal(
    <div className="collection-picker" ref={containerRef} style={style} onClick={(e) => e.stopPropagation()}>
      <div className="collection-picker-header">Collections</div>
      {collections.length === 0 && (
        <div className="collection-picker-empty">No collections yet</div>
      )}
      <ul className="collection-picker-list">
        {collections.map((c) => (
          <li key={c.id}>
            <label className="collection-picker-item">
              <input
                type="checkbox"
                checked={isInCollection(c.name)}
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
    </div>,
    document.body,
  )
}
