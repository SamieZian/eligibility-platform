import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

/**
 * Tiny hash router. Keeps bundle light. Route format: `#/<path>`.
 */
export type Route = { path: string; params: Record<string, string> };

interface RouterValue {
  route: Route;
  navigate: (path: string, params?: Record<string, string>) => void;
}

const RouterContext = createContext<RouterValue | null>(null);

function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, '').trim() || '/eligibility';
  const [pathPart, queryPart = ''] = raw.split('?');
  const params: Record<string, string> = {};
  for (const part of queryPart.split('&').filter(Boolean)) {
    const [k, v = ''] = part.split('=');
    params[decodeURIComponent(k)] = decodeURIComponent(v);
  }
  return { path: pathPart.startsWith('/') ? pathPart : `/${pathPart}`, params };
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(typeof window === 'undefined' ? '' : window.location.hash),
  );

  useEffect(() => {
    function onHash() {
      setRoute(parseHash(window.location.hash));
    }
    window.addEventListener('hashchange', onHash);
    if (!window.location.hash) {
      window.location.hash = '#/eligibility';
    }
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const value = useMemo<RouterValue>(
    () => ({
      route,
      navigate: (path, params) => {
        const qs =
          params && Object.keys(params).length > 0
            ? '?' +
              Object.entries(params)
                .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
                .join('&')
            : '';
        window.location.hash = `#${path}${qs}`;
      },
    }),
    [route],
  );

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter(): RouterValue {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error('useRouter must be used within <RouterProvider>');
  return ctx;
}
