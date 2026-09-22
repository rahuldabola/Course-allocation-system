"use client";

import { Bot, Code2, Database, Send, Sparkles, Trash2, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cx, PageHeader, Spinner } from "@/components/ui";
import { api, type AssistantResponse } from "@/lib/api";
import { useMeta } from "@/lib/hooks";

const SUGGESTIONS = [
  "How many students were allocated to each course?",
  "Which students did not receive their first preference?",
  "Which course had the highest rejection rate?",
  "Category-wise allocation summary",
  "Who are the top 5 students by marks and where did they get in?",
  "How many SC students got a reserved seat versus an open seat?",
];

interface Turn {
  id: number;
  question: string;
  response?: AssistantResponse;
  error?: string;
}

const PREVIEW_ROWS = 8;

function ResultTable({ res }: { res: AssistantResponse }) {
  const [expanded, setExpanded] = useState(false);
  if (res.rows.length === 0) return null;
  const columns = res.columns.length ? res.columns : Object.keys(res.rows[0]);
  const rows = expanded ? res.rows : res.rows.slice(0, PREVIEW_ROWS);
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
      <div className="max-h-80 overflow-auto">
        <table className="table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => {
                  const v = row[c];
                  return (
                    <td key={c} className={typeof v === "number" ? "text-right tabular-nums" : undefined}>
                      {v === null || v === undefined ? (
                        <span className="text-slate-400">—</span>
                      ) : typeof v === "number" && !Number.isInteger(v) ? (
                        v.toFixed(2)
                      ) : (
                        String(v)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(res.rows.length > PREVIEW_ROWS || res.truncated) && (
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400">
          <span>
            {expanded ? res.rows.length : Math.min(PREVIEW_ROWS, res.rows.length)} of{" "}
            {res.rows.length}
            {res.truncated ? "+" : ""} rows
          </span>
          {res.rows.length > PREVIEW_ROWS && (
            <button
              type="button"
              className="font-medium text-brand-600 hover:underline dark:text-brand-400"
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? "Show less" : "Show all"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SourceBadge({ source }: { source: AssistantResponse["source"] }) {
  if (source === "llm")
    return (
      <span className="badge-brand">
        <Sparkles className="h-3 w-3" /> AI-generated query
      </span>
    );
  if (source === "fallback")
    return (
      <span className="badge-green">
        <Database className="h-3 w-3" /> Built-in report
      </span>
    );
  return <span className="badge-gray">No query run</span>;
}

function Answer({ res }: { res: AssistantResponse }) {
  const [showSql, setShowSql] = useState(false);
  return (
    <div className="space-y-3">
      <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800 dark:text-slate-100">
        {res.answer}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <SourceBadge source={res.source} />
        {res.sql && (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            onClick={() => setShowSql((s) => !s)}
            aria-expanded={showSql}
          >
            <Code2 className="h-3.5 w-3.5" /> {showSql ? "Hide SQL" : "View SQL"}
          </button>
        )}
      </div>
      {showSql && res.sql && (
        <pre className="relative overflow-x-auto rounded-lg bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100 dark:border dark:border-slate-800">
          {res.sql}
        </pre>
      )}
      <ResultTable res={res} />
    </div>
  );
}

let turnId = 1;

export default function AssistantPage() {
  const { data: meta } = useMeta();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const ask = async (q: string) => {
    const text = q.trim();
    if (text.length < 3 || busy) return;
    const id = turnId++;
    setTurns((t) => [...t, { id, question: text }]);
    setQuestion("");
    setBusy(true);
    try {
      const response = await api.ask(text);
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, response } : turn)));
    } catch (e) {
      const error = e instanceof Error ? e.message : "Request failed";
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, error } : turn)));
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const providerLabel =
    meta?.llm_provider === "gemini"
      ? `Google Gemini · ${meta.llm_model}`
      : meta?.llm_provider === "ollama"
        ? `Ollama · ${meta.llm_model}`
        : meta
          ? "Built-in reports only (no LLM configured)"
          : null;

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col gap-6 lg:min-h-[calc(100vh-4rem)]">
      <PageHeader
        title="AI Assistant"
        subtitle="Ask about students, courses, quotas and allocations in plain English."
        actions={
          <>
            {providerLabel && (
              <span className={meta?.llm_provider === "none" ? "badge-gray" : "badge-brand"}>
                <Sparkles className="h-3 w-3" /> {providerLabel}
              </span>
            )}
            {turns.length > 0 && (
              <button type="button" className="btn-ghost btn-sm" onClick={() => setTurns([])} disabled={busy}>
                <Trash2 className="h-3.5 w-3.5" /> Clear
              </button>
            )}
          </>
        }
      />

      <div className="card flex flex-1 flex-col">
        <div className="flex-1 space-y-6 overflow-y-auto p-5 sm:p-6" aria-live="polite">
          {turns.length === 0 && (
            <div className="mx-auto flex max-w-2xl flex-col items-center py-8 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-300">
                <Bot className="h-6 w-6" />
              </span>
              <h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">
                What would you like to know?
              </h2>
              <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
                Questions become a single read-only SQL query, validated before it runs. You
                can inspect the SQL and the rows behind every answer.
              </p>
              <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="rounded-lg border border-slate-200 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-brand-300 hover:bg-brand-50/50 dark:border-slate-800 dark:text-slate-300 dark:hover:border-brand-700 dark:hover:bg-brand-950/30"
                    onClick={() => ask(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <div key={turn.id} className="space-y-4 animate-slide-up">
              <div className="flex justify-end gap-3">
                <p className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">
                  {turn.question}
                </p>
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                  <User className="h-4 w-4" />
                </span>
              </div>
              <div className="flex gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-300">
                  <Bot className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1 pt-1">
                  {!turn.response && !turn.error && (
                    <p className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                      <Spinner /> Thinking…
                    </p>
                  )}
                  {turn.error && (
                    <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                      {turn.error}
                    </p>
                  )}
                  {turn.response && <Answer res={turn.response} />}
                </div>
              </div>
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <form
          className="border-t border-slate-100 p-4 dark:border-slate-800"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
        >
          {turns.length > 0 && (
            <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
              {SUGGESTIONS.slice(0, 4).map((s) => (
                <button
                  key={s}
                  type="button"
                  className="shrink-0 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-brand-300 hover:text-brand-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-700 dark:hover:text-brand-300"
                  onClick={() => ask(s)}
                  disabled={busy}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              rows={1}
              maxLength={500}
              className={cx("input max-h-40 min-h-[2.5rem] resize-none")}
              placeholder="Ask a question…  (Enter to send, Shift+Enter for a new line)"
              aria-label="Your question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask(question);
                }
              }}
            />
            <button
              type="submit"
              className="btn-primary h-10"
              disabled={busy || question.trim().length < 3}
              aria-label="Send"
            >
              {busy ? <Spinner /> : <Send className="h-4 w-4" />}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
