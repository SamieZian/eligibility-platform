import { useState } from 'react';
import type { SearchFilter } from '../../api/types';
import { useLocalStorage } from '../../lib/useLocalStorage';
import { Button } from '../../components/Button';

interface Saved {
  name: string;
  filter: SearchFilter;
}

interface Props {
  currentFilter: SearchFilter;
  onApply: (f: SearchFilter) => void;
}

export function SavedViews({ currentFilter, onApply }: Props) {
  const [views, setViews] = useLocalStorage<Saved[]>('bff.views', []);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');

  function save() {
    if (!name.trim()) return;
    setViews([...views.filter((v) => v.name !== name), { name, filter: currentFilter }]);
    setName('');
    setOpen(false);
  }

  function remove(n: string) {
    setViews(views.filter((v) => v.name !== n));
  }

  return (
    <div style={{ position: 'relative' }}>
      <Button variant="secondary" onClick={() => setOpen(!open)}>
        Saved Views {views.length ? `(${views.length})` : ''}
      </Button>
      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            zIndex: 5,
            background: 'var(--color-surface, #fff)',
            border: '1px solid var(--color-border, #d0d0d0)',
            borderRadius: 6,
            padding: 8,
            minWidth: 260,
            boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
          }}
        >
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <input
              placeholder="Save current as…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ flex: 1, padding: '4px 6px' }}
            />
            <Button onClick={save}>Save</Button>
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {views.map((v) => (
              <li
                key={v.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '4px 0',
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    onApply(v.filter);
                    setOpen(false);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'inherit',
                  }}
                >
                  {v.name}
                </button>
                <button
                  type="button"
                  onClick={() => remove(v.name)}
                  aria-label={`Delete ${v.name}`}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
                >
                  ✕
                </button>
              </li>
            ))}
            {views.length === 0 && <li style={{ color: '#888' }}>No saved views yet</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
