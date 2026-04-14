import cx from 'classnames';
import { useEffect } from 'react';
import { BannerStack } from '../components/Banner';
import { Grid } from '../features/eligibility/Grid';
import { FileUpload } from '../features/upload/FileUpload';
import { useGlobalStatus } from './GlobalStatus';
import { useRouter } from '../lib/router';
import styles from './AppShell.module.css';

interface NavItem {
  path: string;
  label: string;
}

const NAV: NavItem[] = [
  { path: '/eligibility', label: 'Eligibility' },
  { path: '/upload', label: 'Upload' },
  { path: '/about', label: 'About' },
];

export function AppShell() {
  const { route, navigate } = useRouter();
  const { correlationId } = useGlobalStatus();

  useEffect(() => {
    const saved = localStorage.getItem('bff.theme');
    if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  }, []);

  const activePath = NAV.find((n) => route.path.startsWith(n.path))?.path ?? '/eligibility';

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>Eligibility Console</div>
        <nav aria-label="Primary" className={styles.nav}>
          {NAV.map((item) => (
            <button
              key={item.path}
              type="button"
              className={cx(styles.navItem, activePath === item.path && styles.navItemActive)}
              onClick={() => navigate(item.path)}
              aria-current={activePath === item.path ? 'page' : undefined}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <ThemeToggle />
      </header>
      <BannerStack />
      <main className={styles.main}>
        {activePath === '/eligibility' && <Grid />}
        {activePath === '/upload' && <FileUpload />}
        {activePath === '/about' && <AboutPage />}
      </main>
      <footer className={styles.footer} aria-label="Debug footer">
        <span className={styles.footerCid} title="Last correlation id">
          cid: {correlationId || '—'}
        </span>
      </footer>
    </div>
  );
}

function ThemeToggle() {
  return (
    <button
      type="button"
      className={styles.themeBtn}
      aria-label="Toggle dark mode"
      onClick={() => {
        const root = document.documentElement;
        const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        if (next === 'dark') root.setAttribute('data-theme', 'dark');
        else root.removeAttribute('data-theme');
        localStorage.setItem('bff.theme', next);
      }}
    >
      Theme
    </button>
  );
}

function AboutPage() {
  return (
    <div className={styles.about}>
      <h1>Eligibility Console</h1>
      <p>
        A bitemporal eligibility data console: search, upload enrollment files, and audit
        membership changes. Built with React 18, TanStack Table, and a GraphQL BFF.
      </p>
    </div>
  );
}
