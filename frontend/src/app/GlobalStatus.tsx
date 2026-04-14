import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type BannerLevel = 'info' | 'warn' | 'error';

export interface StatusBanner {
  id: string;
  level: BannerLevel;
  message: string;
}

interface GlobalStatusValue {
  banners: StatusBanner[];
  pushBanner: (level: BannerLevel, message: string) => string;
  dismissBanner: (id: string) => void;
  correlationId: string;
  setCorrelationId: (id: string) => void;
}

const GlobalStatusContext = createContext<GlobalStatusValue | null>(null);

export function GlobalStatusProvider({ children }: { children: ReactNode }) {
  const [banners, setBanners] = useState<StatusBanner[]>([]);
  const [correlationId, setCorrelationId] = useState<string>('');

  const pushBanner = useCallback((level: BannerLevel, message: string): string => {
    const id = `b-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setBanners((prev) => [...prev, { id, level, message }]);
    return id;
  }, []);

  const dismissBanner = useCallback((id: string) => {
    setBanners((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const value = useMemo<GlobalStatusValue>(
    () => ({ banners, pushBanner, dismissBanner, correlationId, setCorrelationId }),
    [banners, pushBanner, dismissBanner, correlationId],
  );

  return <GlobalStatusContext.Provider value={value}>{children}</GlobalStatusContext.Provider>;
}

export function useGlobalStatus(): GlobalStatusValue {
  const ctx = useContext(GlobalStatusContext);
  if (!ctx) throw new Error('useGlobalStatus must be used within <GlobalStatusProvider>');
  return ctx;
}
