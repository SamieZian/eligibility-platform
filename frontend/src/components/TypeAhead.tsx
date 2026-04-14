import { useEffect, useMemo, useRef, useState } from 'react';
import { useDebounce } from '../lib/useDebounce';
import styles from './TypeAhead.module.css';

export interface TypeAheadOption<V> {
  value: V;
  label: string;
  meta?: string;
}

export interface TypeAheadProps<V> {
  id?: string;
  label?: string;
  placeholder?: string;
  initialInput?: string;
  value?: V | null;
  /** Resolves options for a search query (may throw; caller is responsible for error UI). */
  search: (q: string) => Promise<Array<TypeAheadOption<V>>>;
  onChange: (option: TypeAheadOption<V> | null) => void;
  debounceMs?: number;
  disabled?: boolean;
}

export function TypeAhead<V extends string | number>({
  id,
  label,
  placeholder,
  initialInput = '',
  search,
  onChange,
  debounceMs = 250,
  disabled,
}: TypeAheadProps<V>) {
  const [input, setInput] = useState(initialInput);
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<Array<TypeAheadOption<V>>>([]);
  const [loading, setLoading] = useState(false);
  const debounced = useDebounce(input, debounceMs);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    if (!debounced) {
      setOptions([]);
      return;
    }
    setLoading(true);
    search(debounced)
      .then((opts) => {
        if (!cancelled.current) setOptions(opts);
      })
      .catch(() => {
        if (!cancelled.current) setOptions([]);
      })
      .finally(() => {
        if (!cancelled.current) setLoading(false);
      });
    return () => {
      cancelled.current = true;
    };
  }, [debounced, search]);

  const listId = useMemo(() => id ? `${id}-list` : undefined, [id]);

  return (
    <div className={styles.wrap}>
      {label && (
        <label htmlFor={id} className={styles.label}>
          {label}
        </label>
      )}
      <input
        id={id}
        type="text"
        className={styles.input}
        placeholder={placeholder}
        value={input}
        disabled={disabled}
        autoComplete="off"
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open}
        role="combobox"
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => {
          setInput(e.target.value);
          setOpen(true);
          if (e.target.value === '') onChange(null);
        }}
      />
      {open && (options.length > 0 || loading) && (
        <ul id={listId} className={styles.list} role="listbox">
          {loading && <li className={styles.empty}>Loading…</li>}
          {!loading &&
            options.map((o) => (
              <li
                key={String(o.value)}
                role="option"
                aria-selected="false"
                className={styles.option}
                onMouseDown={(e) => {
                  e.preventDefault();
                  setInput(o.label);
                  onChange(o);
                  setOpen(false);
                }}
              >
                <span>{o.label}</span>
                {o.meta && <span className={styles.meta}>{o.meta}</span>}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
