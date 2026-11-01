import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Fetch `path` on mount / when it changes. Returns {data, error, loading, reload, setData}. */
export function useApi(path, { poll } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const alive = useRef(true);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api(path);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    setLoading(Boolean(path));
    reload();
    return () => {
      alive.current = false;
    };
  }, [reload, path]);

  useEffect(() => {
    if (!poll) return;
    const id = setInterval(reload, poll);
    return () => clearInterval(id);
  }, [poll, reload]);

  return { data, error, loading, reload, setData };
}
