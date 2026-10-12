import { StrictMode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { scopedQueryHash } from './features/access/businessScope';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Task B: every cache entry is keyed by user and effective scope.
      queryKeyHashFn: scopedQueryHash,
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>
);
