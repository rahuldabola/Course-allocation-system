"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Meta } from "./api";

export interface AsyncState<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (updater: (prev: T | undefined) => T | undefined) => void;
}

/**
 * Run an async loader on mount and whenever `key` changes; expose its
 * result, error and a `reload()` trigger. Stale responses are ignored.
 */
export function useAsync<T>(loader: () => Promise<T>, key: string = ""): AsyncState<T> {
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    let cancelled = false;
    loaderRef.current().then(
      (result) => {
        if (cancelled) return;
        setDataState(result);
        setError(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, nonce]);

  const reload = useCallback(() => {
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);

  const setData = useCallback(
    (updater: (prev: T | undefined) => T | undefined) => setDataState(updater),
    [],
  );

  return { data, error, loading, reload, setData };
}

/** A value that trails `value` by `delay` ms (for search boxes). */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

let metaPromise: Promise<Meta> | null = null;

/** Public app metadata (demo mode, LLM provider); fetched once per page load. */
export function useMeta() {
  return useAsync(() => {
    metaPromise ??= api.meta().catch((e) => {
      metaPromise = null;
      throw e;
    });
    return metaPromise;
  });
}
