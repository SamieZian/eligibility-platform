import type { ChangeEvent } from 'react';
import styles from './DateRange.module.css';

export interface DateRangeValue {
  from?: string;
  to?: string;
}

export interface DateRangeProps {
  value: DateRangeValue;
  onChange: (v: DateRangeValue) => void;
  label?: string;
  fromLabel?: string;
  toLabel?: string;
  id?: string;
}

export function DateRange({
  value,
  onChange,
  label,
  fromLabel = 'From',
  toLabel = 'To',
  id,
}: DateRangeProps) {
  const fromId = id ? `${id}-from` : undefined;
  const toId = id ? `${id}-to` : undefined;
  const handle = (key: 'from' | 'to') => (e: ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, [key]: e.target.value || undefined });
  };
  return (
    <fieldset className={styles.wrap}>
      {label && <legend className={styles.legend}>{label}</legend>}
      <div className={styles.row}>
        <label htmlFor={fromId} className={styles.cell}>
          <span className={styles.cellLabel}>{fromLabel}</span>
          <input
            id={fromId}
            type="date"
            value={value.from ?? ''}
            onChange={handle('from')}
            aria-label={`${label ?? 'Date'} ${fromLabel}`}
          />
        </label>
        <label htmlFor={toId} className={styles.cell}>
          <span className={styles.cellLabel}>{toLabel}</span>
          <input
            id={toId}
            type="date"
            value={value.to ?? ''}
            onChange={handle('to')}
            aria-label={`${label ?? 'Date'} ${toLabel}`}
          />
        </label>
      </div>
    </fieldset>
  );
}
