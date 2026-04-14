import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from './app/AppShell';
import { GlobalStatusProvider } from './app/GlobalStatus';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RouterProvider } from './lib/router';
import './styles/tokens.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
});

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('#root element not found');

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <GlobalStatusProvider>
          <RouterProvider>
            <AppShell />
          </RouterProvider>
        </GlobalStatusProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
