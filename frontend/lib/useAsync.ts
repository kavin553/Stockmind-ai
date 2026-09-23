"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Minimal data-fetching hook with cancellation, used by every page. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const cancelled = useRef(false);

  const run = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    cancelled.current = false;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (!cancelled.current) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled.current) setError(err instanceof Error ? err.message : "Request failed.");
      })
      .finally(() => {
        if (!cancelled.current) setLoading(false);
      });
    return () => {
      cancelled.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, loading, error, reload: run };
}
