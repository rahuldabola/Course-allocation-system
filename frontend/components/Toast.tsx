"use client";

import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

type Tone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  tone: Tone;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setItems((all) => all.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (tone: Tone, message: string) => {
      const id = nextId++;
      setItems((all) => [...all.slice(-3), { id, tone, message }]);
      setTimeout(() => dismiss(id), tone === "error" ? 7000 : 4000);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [push],
  );

  const icons = {
    success: <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden="true" />,
    error: <XCircle className="h-5 w-5 text-red-500" aria-hidden="true" />,
    info: <Info className="h-5 w-5 text-brand-500" aria-hidden="true" />,
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {items.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className="pointer-events-auto flex w-full max-w-sm animate-slide-up items-start gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-lg dark:border-slate-700 dark:bg-slate-900"
          >
            {icons[t.tone]}
            <p className="flex-1 text-sm text-slate-700 dark:text-slate-200">{t.message}</p>
            <button
              type="button"
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
