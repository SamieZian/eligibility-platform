import styles from './Spinner.module.css';

export interface SpinnerProps {
  size?: number;
  label?: string;
}

export function Spinner({ size = 16, label = 'Loading' }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={label}
      className={styles.spinner}
      style={{ width: size, height: size }}
    />
  );
}
