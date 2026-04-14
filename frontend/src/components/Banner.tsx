import cx from 'classnames';
import { useGlobalStatus, type BannerLevel } from '../app/GlobalStatus';
import styles from './Banner.module.css';

export function BannerStack() {
  const { banners, dismissBanner } = useGlobalStatus();
  if (banners.length === 0) return null;
  return (
    <div className={styles.stack} role="region" aria-label="System notices">
      {banners.map((b) => (
        <div
          key={b.id}
          className={cx(styles.banner, styles[levelClass(b.level)])}
          role={b.level === 'error' ? 'alert' : 'status'}
        >
          <span>{b.message}</span>
          <button
            type="button"
            aria-label="Dismiss notice"
            className={styles.dismiss}
            onClick={() => dismissBanner(b.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function levelClass(level: BannerLevel): 'info' | 'warn' | 'error' {
  return level;
}
