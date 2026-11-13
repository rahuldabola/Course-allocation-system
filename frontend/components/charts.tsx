"use client";

// Dashboard charts. Palette: the dataviz reference instance (validated with
// validate_palette.js against this app's card surfaces — white in light mode,
// slate-900 in dark): categorical blue/orange for two series, a one-hue blue
// ordinal ramp for 1st/2nd/3rd choice, neutral gray for "no data"/capacity.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CourseStat, DashboardStats } from "@/lib/api";
import { ordinal, pct } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { cx } from "./ui";

const TOKENS = {
  light: {
    surface: "#ffffff",
    series1: "#2a78d6",
    series2: "#eb6834",
    ordinal: ["#1c5cab", "#3987e5", "#86b6ef"],
    track: "#e2e8f0",
    deemphasis: "#cbd5e1",
    ink: "#0f172a",
    muted: "#64748b",
  },
  dark: {
    surface: "#0f172a",
    series1: "#3987e5",
    series2: "#d95926",
    ordinal: ["#86b6ef", "#3987e5", "#1c5cab"],
    track: "#334155",
    deemphasis: "#475569",
    ink: "#f1f5f9",
    muted: "#94a3b8",
  },
};

function useTokens() {
  return TOKENS[useTheme()];
}

function Swatch({ color }: { color: string }) {
  return (
    <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: color }} />
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <Swatch color={item.color} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

interface TipRow {
  label: string;
  value: string;
  color?: string;
}

function TooltipCard({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="min-w-[10rem] rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <p className="mb-1 font-medium text-slate-900 dark:text-slate-100">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
          {r.color && <Swatch color={r.color} />}
          <span className="flex-1">{r.label}</span>
          <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">
            {r.value}
          </span>
        </p>
      ))}
    </div>
  );
}

// Recharts passes tooltip props loosely typed; read the hovered row safely.
interface TipProps {
  active?: boolean;
  payload?: readonly { payload?: unknown }[];
}

function tooltip<T>(render: (row: T) => React.ReactNode) {
  return ({ active, payload }: TipProps) => {
    const row = payload?.[0]?.payload as T | undefined;
    return active && row ? render(row) : null;
  };
}

const AXIS_TICK = { fontSize: 12 };

/** Single-line, truncated category label for horizontal bar charts (full name on hover). */
function CategoryTick({ x = 0, y = 0, payload }: { x?: number | string; y?: number | string; payload?: { value?: string } }) {
  const full = String(payload?.value ?? "");
  const label = full.length > 17 ? `${full.slice(0, 16)}…` : full;
  return (
    <text x={Number(x)} y={Number(y)} dy={4} textAnchor="end" fontSize={12} className="fill-slate-500 dark:fill-slate-400">
      <title>{full}</title>
      {label}
    </text>
  );
}

/* ------------------------------------------------------------------ */
/* Seat utilisation: stacked horizontal bars (allocated + free seats)  */
/* ------------------------------------------------------------------ */
export function SeatUtilizationChart({ courses }: { courses: CourseStat[] }) {
  const t = useTokens();
  const data = courses.map((c) => ({
    name: c.course_name,
    allocated: c.allocated,
    free: c.available_seats,
    total: c.total_seats,
  }));
  type Row = (typeof data)[number];
  const height = Math.max(160, data.length * 40 + 40);

  // "allocated/total" at the bar's end: on the free-seat segment, or on the
  // allocated segment when the course is full (a zero-width segment gets no label).
  const seatLabel = (whenFull: boolean) =>
    function SeatLabel(props: unknown) {
      const { x = 0, y = 0, width = 0, height: h = 0, index = 0 } = props as {
        x?: number; y?: number; width?: number; height?: number; index?: number;
      };
      const row = data[index];
      if (!row || (row.free === 0) !== whenFull) return null;
      return (
        <text x={Number(x) + Number(width) + 6} y={Number(y) + Number(h) / 2} dy={4} fontSize={12} fill={t.muted}>
          {row.allocated}/{row.total}
        </text>
      );
    };

  return (
    <div>
      <Legend
        items={[
          { label: "Allocated", color: t.series1 },
          { label: "Free seats", color: t.track },
        ]}
      />
      <div className="mt-3" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal={false} strokeWidth={1} />
            <XAxis type="number" allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis
              type="category"
              dataKey="name"
              width={130}
              tick={<CategoryTick />}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: t.track, opacity: 0.35 }}
              content={tooltip<Row>((row) => (
                  <TooltipCard
                    title={row.name}
                    rows={[
                      { label: "Allocated", value: String(row.allocated), color: t.series1 },
                      { label: "Free seats", value: String(row.free), color: t.track },
                      { label: "Total seats", value: String(row.total) },
                    ]}
                  />
                ))}
            />
            <Bar dataKey="allocated" stackId="seats" fill={t.series1} barSize={20} stroke={t.surface} strokeWidth={2}>
              <LabelList dataKey="total" content={seatLabel(true)} />
            </Bar>
            <Bar dataKey="free" stackId="seats" fill={t.track} barSize={20} radius={[0, 4, 4, 0]} stroke={t.surface} strokeWidth={2}>
              <LabelList dataKey="total" content={seatLabel(false)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Rejection rate: emphasis form — highest course in the accent         */
/* ------------------------------------------------------------------ */
export function RejectionChart({ courses }: { courses: CourseStat[] }) {
  const t = useTokens();
  const data = [...courses]
    .filter((c) => c.applicants > 0)
    .sort((a, b) => b.rejection_rate - a.rejection_rate)
    .map((c) => ({
      name: c.course_name,
      rate: Number((c.rejection_rate * 100).toFixed(1)),
      applicants: c.applicants,
      rejected: c.applicants - c.allocated,
    }));
  type Row = (typeof data)[number];
  const height = Math.max(160, data.length * 40 + 30);

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 52, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} strokeWidth={1} />
          <XAxis
            type="number"
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={130}
            tick={<CategoryTick />}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: t.track, opacity: 0.35 }}
            content={tooltip<Row>((row) => (
                <TooltipCard
                  title={row.name}
                  rows={[
                    { label: "Rejection rate", value: `${row.rate}%` },
                    { label: "Applicants", value: String(row.applicants) },
                    { label: "Not placed here", value: String(row.rejected) },
                  ]}
                />
              ))}
          />
          <Bar dataKey="rate" barSize={20} radius={[0, 4, 4, 0]}>
            {data.map((row, i) => (
              <Cell key={row.name} fill={i === 0 ? t.series1 : t.deemphasis} />
            ))}
            <LabelList
              dataKey="rate"
              position="right"
              formatter={(v: unknown) => `${v}%`}
              style={{ fontSize: 12, fill: t.muted }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Category split: grouped bars, students vs allocated                  */
/* ------------------------------------------------------------------ */
export function CategoryChart({ stats }: { stats: DashboardStats["category_stats"] }) {
  const t = useTokens();
  const data = stats.map((c) => ({ name: c.category_code, students: c.students, allocated: c.allocated }));
  type Row = (typeof data)[number];
  return (
    <div>
      <Legend
        items={[
          { label: "Applicants", color: t.series1 },
          { label: "Allocated", color: t.series2 },
        ]}
      />
      <div className="mt-3 h-60">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: -16 }} barGap={2}>
            <CartesianGrid vertical={false} strokeWidth={1} />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: t.track, opacity: 0.35 }}
              content={tooltip<Row>((row) => (
                  <TooltipCard
                    title={row.name}
                    rows={[
                      { label: "Applicants", value: String(row.students), color: t.series1 },
                      { label: "Allocated", value: String(row.allocated), color: t.series2 },
                      {
                        label: "Placement rate",
                        value: row.students
                          ? pct(row.allocated / row.students)
                          : "—",
                      },
                    ]}
                  />
                ))}
            />
            <Bar dataKey="students" fill={t.series1} barSize={20} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="students" position="top" style={{ fontSize: 11, fill: t.muted }} />
            </Bar>
            <Bar dataKey="allocated" fill={t.series2} barSize={20} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="allocated" position="top" style={{ fontSize: 11, fill: t.muted }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Preference satisfaction: one 100% stacked bar (ordinal ramp + gray) */
/* ------------------------------------------------------------------ */
export function PreferenceBar({
  stats,
  unallocated,
}: {
  stats: DashboardStats["preference_stats"];
  unallocated: number;
}) {
  const t = useTokens();
  const segments = [
    ...stats.map((p, i) => ({
      label: `${ordinal(p.preference_rank)} choice`,
      value: p.allocated,
      color: t.ordinal[i] ?? t.ordinal[t.ordinal.length - 1],
    })),
    { label: "Not allocated", value: unallocated, color: t.track },
  ];
  const total = segments.reduce((s, x) => s + x.value, 0);
  if (total === 0) return null;

  return (
    <div>
      <div className="flex h-5 w-full gap-[2px] overflow-hidden rounded" role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(", ")}>
        {segments.filter((s) => s.value > 0).map((s) => (
          <div
            key={s.label}
            title={`${s.label}: ${s.value} (${pct(s.value / total)})`}
            className="h-full transition-opacity first:rounded-l last:rounded-r hover:opacity-80"
            style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
          />
        ))}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {segments.map((s) => (
          <div key={s.label} className="rounded-lg border border-slate-100 px-3 py-2 dark:border-slate-800">
            <dt className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <Swatch color={s.color} />
              {s.label}
            </dt>
            <dd className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">
              {s.value}
              <span className={cx("ml-1.5 text-xs font-normal text-slate-500 dark:text-slate-400")}>
                {pct(s.value / total)}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
