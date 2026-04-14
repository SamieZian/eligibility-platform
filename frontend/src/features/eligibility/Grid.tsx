import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { searchEnrollments } from '../../api/bff';
import type { SearchFilter, SortOrder } from '../../api/types';
import { useLocalStorage } from '../../lib/useLocalStorage';
import { useDebounce } from '../../lib/useDebounce';
import { Spinner } from '../../components/Spinner';
import { Button } from '../../components/Button';
import { AdvancedSearchModal } from './AdvancedSearchModal';
import { SavedViews } from './SavedViews';
import { MemberDetail } from '../member/Detail';
import styles from './Grid.module.css';

const ALL_COLUMNS = [
  { key: 'cardNumber', label: 'Member ID' },
  { key: 'memberName', label: 'Name' },
  { key: 'dob', label: 'DOB' },
  { key: 'employerName', label: 'Employer' },
  { key: 'planName', label: 'Plan' },
  { key: 'relationship', label: 'Relationship' },
  { key: 'status', label: 'Status' },
  { key: 'effectiveDate', label: 'Effective' },
  { key: 'terminationDate', label: 'Termination' },
] as const;

type ColumnKey = (typeof ALL_COLUMNS)[number]['key'];
const DEFAULT_VISIBLE: ColumnKey[] = ALL_COLUMNS.map((c) => c.key);

export function Grid() {
  const [filter, setFilter] = useState<SearchFilter>({});
  const [quickQuery, setQuickQuery] = useState('');
  const debouncedQ = useDebounce(quickQuery, 250);
  const [cursor, setCursor] = useState<string | null>(null);
  const [sort, setSort] = useState<SortOrder>('effective_date_desc');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [drawerMemberId, setDrawerMemberId] = useState<string | null>(null);
  const [visible, setVisible] = useLocalStorage<ColumnKey[]>('bff.grid.columns', DEFAULT_VISIBLE);
  const [density, setDensity] = useLocalStorage<'comfortable' | 'compact'>('bff.grid.density', 'comfortable');

  const effectiveFilter: SearchFilter = useMemo(
    () => ({ ...filter, q: debouncedQ || filter.q || null }),
    [filter, debouncedQ],
  );

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['search', effectiveFilter, cursor, sort],
    queryFn: () => searchEnrollments(effectiveFilter, { limit: 25, cursor, sort }),
    placeholderData: (prev) => prev,
  });

  const toggleColumn = (key: ColumnKey) =>
    setVisible((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const applyFilter = (next: SearchFilter) => {
    setFilter(next);
    setCursor(null);
  };

  return (
    <div className={styles.wrap} data-density={density}>
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          aria-label="Quick search"
          placeholder="Quick search by name or card…"
          value={quickQuery}
          onChange={(e) => {
            setQuickQuery(e.target.value);
            setCursor(null);
          }}
        />
        <Button onClick={() => setAdvancedOpen(true)}>Advanced Search</Button>
        <SavedViews currentFilter={filter} onApply={applyFilter} />
        <div className={styles.spacer} />
        <select
          aria-label="Sort"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value as SortOrder);
            setCursor(null);
          }}
        >
          <option value="effective_date_desc">Effective ↓</option>
          <option value="effective_date_asc">Effective ↑</option>
        </select>
        <select
          aria-label="Density"
          value={density}
          onChange={(e) => setDensity(e.target.value as 'comfortable' | 'compact')}
        >
          <option value="comfortable">Comfortable</option>
          <option value="compact">Compact</option>
        </select>
        <details className={styles.colMenu}>
          <summary>Columns</summary>
          <ul>
            {ALL_COLUMNS.map((c) => (
              <li key={c.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={visible.includes(c.key)}
                    onChange={() => toggleColumn(c.key)}
                  />
                  {c.label}
                </label>
              </li>
            ))}
          </ul>
        </details>
      </div>

      {isLoading && <Spinner />}
      {error && (
        <div role="alert" className={styles.error}>
          {(error as Error).message}
        </div>
      )}

      <div className={styles.tableWrap} role="region" aria-label="Eligibility results">
        <table className={styles.table}>
          <thead>
            <tr>
              {ALL_COLUMNS.filter((c) => visible.includes(c.key)).map((c) => (
                <th key={c.key} scope="col">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((row) => (
              <tr
                key={row.enrollmentId}
                tabIndex={0}
                onClick={() => setDrawerMemberId(row.memberId)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setDrawerMemberId(row.memberId);
                }}
              >
                {ALL_COLUMNS.filter((c) => visible.includes(c.key)).map((c) => (
                  <td key={c.key}>{renderCell(row as unknown as Record<string, unknown>, c.key)}</td>
                ))}
              </tr>
            ))}
            {!isLoading && data && data.items.length === 0 && (
              <tr>
                <td colSpan={visible.length} className={styles.empty}>
                  No enrollments match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className={styles.pager}>
        <span>
          {isFetching ? 'Loading…' : `${data?.total ?? 0} total`}
        </span>
        <div>
          <Button disabled={!cursor} onClick={() => setCursor(null)}>
            ⇤ First
          </Button>
          <Button disabled={!data?.nextCursor} onClick={() => setCursor(data?.nextCursor ?? null)}>
            Next →
          </Button>
        </div>
      </div>

      {advancedOpen && (
        <AdvancedSearchModal
          initial={filter}
          onClose={() => setAdvancedOpen(false)}
          onApply={(f) => {
            applyFilter(f);
            setAdvancedOpen(false);
          }}
        />
      )}

      {drawerMemberId && (
        <MemberDetail memberId={drawerMemberId} onClose={() => setDrawerMemberId(null)} />
      )}
    </div>
  );
}

function renderCell(row: Record<string, unknown>, key: string): string {
  const v = row[key];
  if (v == null) return '';
  return String(v);
}
