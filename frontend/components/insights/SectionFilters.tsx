"use client";

import { cn } from "@/lib/cn";
import type {
  AnomaliesFilters,
  BenchmarksFilters,
  CorrelationsFilters,
  FilterOptions,
  OpportunitiesFilters,
  PeerBy,
  SectionFiltersMap,
  SectionId,
  TrendsFilters,
} from "@/lib/insights-api";

type Props<S extends SectionId> = Readonly<{
  sectionId: S;
  filters: SectionFiltersMap[S];
  onChange: (next: SectionFiltersMap[S]) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>;

export function SectionFilters<S extends SectionId>(props: Props<S>) {
  const { sectionId } = props;

  if (sectionId === "anomalies") {
    return (
      <AnomaliesControls
        filters={props.filters as AnomaliesFilters}
        onChange={props.onChange as (f: AnomaliesFilters) => void}
        options={props.options}
        disabled={props.disabled}
      />
    );
  }
  if (sectionId === "trends") {
    return (
      <TrendsControls
        filters={props.filters as TrendsFilters}
        onChange={props.onChange as (f: TrendsFilters) => void}
        options={props.options}
        disabled={props.disabled}
      />
    );
  }
  if (sectionId === "benchmarks") {
    return (
      <BenchmarksControls
        filters={props.filters as BenchmarksFilters}
        onChange={props.onChange as (f: BenchmarksFilters) => void}
        options={props.options}
        disabled={props.disabled}
      />
    );
  }
  if (sectionId === "correlations") {
    return (
      <CorrelationsControls
        filters={props.filters as CorrelationsFilters}
        onChange={props.onChange as (f: CorrelationsFilters) => void}
        options={props.options}
        disabled={props.disabled}
      />
    );
  }
  return (
    <OpportunitiesControls
      filters={props.filters as OpportunitiesFilters}
      onChange={props.onChange as (f: OpportunitiesFilters) => void}
      options={props.options}
      disabled={props.disabled}
    />
  );
}

// ---------------------------------------------------------------------------
// Reusable primitives
// ---------------------------------------------------------------------------

const FIELD_LABEL =
  "text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-500";

const SELECT_CLASSES = cn(
  "w-full rounded-md border border-ink-200 bg-white px-2.5 py-1.5",
  "font-mono text-xs text-ink-800 shadow-inner",
  "focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-200",
  "disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-400",
);

function Field({
  label,
  children,
  className,
}: Readonly<{ label: string; children: React.ReactNode; className?: string }>) {
  return (
    <label className={cn("flex min-w-[140px] flex-col gap-1", className)}>
      <span className={FIELD_LABEL}>{label}</span>
      {children}
    </label>
  );
}

function MetricSelect({
  value,
  onChange,
  options,
  disabled,
  label = "Métrica",
}: Readonly<{
  value: string;
  onChange: (v: string) => void;
  options: FilterOptions | null;
  disabled?: boolean;
  label?: string;
}>) {
  const metrics = options?.metrics ?? [];
  return (
    <Field label={label} className="min-w-[220px] flex-1">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || metrics.length === 0}
        className={SELECT_CLASSES}
      >
        {!metrics.includes(value) && value && (
          <option value={value}>{value}</option>
        )}
        {metrics.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </Field>
  );
}

// ---------------------------------------------------------------------------
// Anomalies — metric + two week pickers (L{n}W where 1..8 / 0..7)
// ---------------------------------------------------------------------------

const WEEK_LABELS: Record<number, string> = {
  0: "L0W (actual)",
  1: "L1W",
  2: "L2W",
  3: "L3W",
  4: "L4W",
  5: "L5W",
  6: "L6W",
  7: "L7W",
  8: "L8W",
};

function AnomaliesControls({
  filters,
  onChange,
  options,
  disabled,
}: Readonly<{
  filters: AnomaliesFilters;
  onChange: (f: AnomaliesFilters) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>) {
  const startWeeks = [1, 2, 3, 4, 5, 6, 7, 8];
  const endWeeks = [0, 1, 2, 3, 4, 5, 6, 7];
  return (
    <>
      <MetricSelect
        value={filters.metric}
        onChange={(metric) => onChange({ ...filters, metric })}
        options={options}
        disabled={disabled}
      />
      <Field label="Semana anterior">
        <select
          value={filters.start_week_num}
          onChange={(e) =>
            onChange({ ...filters, start_week_num: Number(e.target.value) })
          }
          disabled={disabled}
          className={SELECT_CLASSES}
        >
          {startWeeks.map((w) => (
            <option key={w} value={w}>
              {WEEK_LABELS[w]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Semana comparada">
        <select
          value={filters.end_week_num}
          onChange={(e) =>
            onChange({ ...filters, end_week_num: Number(e.target.value) })
          }
          disabled={disabled}
          className={SELECT_CLASSES}
        >
          {endWeeks.map((w) => (
            <option key={w} value={w}>
              {WEEK_LABELS[w]}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}

// ---------------------------------------------------------------------------
// Trends — metric + num_weeks (3..9)
// ---------------------------------------------------------------------------

function TrendsControls({
  filters,
  onChange,
  options,
  disabled,
}: Readonly<{
  filters: TrendsFilters;
  onChange: (f: TrendsFilters) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>) {
  return (
    <>
      <MetricSelect
        value={filters.metric}
        onChange={(metric) => onChange({ ...filters, metric })}
        options={options}
        disabled={disabled}
      />
      <Field label="Ventana (semanas)">
        <select
          value={filters.num_weeks}
          onChange={(e) =>
            onChange({ ...filters, num_weeks: Number(e.target.value) })
          }
          disabled={disabled}
          className={SELECT_CLASSES}
        >
          {[3, 4, 5, 6, 7, 8, 9].map((n) => (
            <option key={n} value={n}>
              Últimas {n} semanas
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}

// ---------------------------------------------------------------------------
// Benchmarks — metric + peer grouping
// ---------------------------------------------------------------------------

const PEER_LABELS: Record<PeerBy, string> = {
  zone_type: "Zone type",
  zone_prioritization: "Zone prioritization",
};

function BenchmarksControls({
  filters,
  onChange,
  options,
  disabled,
}: Readonly<{
  filters: BenchmarksFilters;
  onChange: (f: BenchmarksFilters) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>) {
  const peerGroups: PeerBy[] = (options?.peer_groups as PeerBy[] | undefined) ?? [
    "zone_type",
    "zone_prioritization",
  ];
  return (
    <>
      <MetricSelect
        value={filters.metric}
        onChange={(metric) => onChange({ ...filters, metric })}
        options={options}
        disabled={disabled}
      />
      <Field label="Peer group">
        <select
          value={filters.peer_by}
          onChange={(e) =>
            onChange({ ...filters, peer_by: e.target.value as PeerBy })
          }
          disabled={disabled}
          className={SELECT_CLASSES}
        >
          {peerGroups.map((pg) => (
            <option key={pg} value={pg}>
              {PEER_LABELS[pg] ?? pg}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}

// ---------------------------------------------------------------------------
// Correlations — metric_x, metric_y, country
// ---------------------------------------------------------------------------

function CorrelationsControls({
  filters,
  onChange,
  options,
  disabled,
}: Readonly<{
  filters: CorrelationsFilters;
  onChange: (f: CorrelationsFilters) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>) {
  const countries = options?.countries ?? [];
  return (
    <>
      <MetricSelect
        label="Métrica X"
        value={filters.metric_x}
        onChange={(metric_x) => onChange({ ...filters, metric_x })}
        options={options}
        disabled={disabled}
      />
      <MetricSelect
        label="Métrica Y"
        value={filters.metric_y}
        onChange={(metric_y) => onChange({ ...filters, metric_y })}
        options={options}
        disabled={disabled}
      />
      <Field label="País">
        <select
          value={filters.country ?? ""}
          onChange={(e) =>
            onChange({
              ...filters,
              country: e.target.value === "" ? null : e.target.value,
            })
          }
          disabled={disabled}
          className={SELECT_CLASSES}
        >
          <option value="">Todos los países</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}

// ---------------------------------------------------------------------------
// Opportunities — metric only
// ---------------------------------------------------------------------------

function OpportunitiesControls({
  filters,
  onChange,
  options,
  disabled,
}: Readonly<{
  filters: OpportunitiesFilters;
  onChange: (f: OpportunitiesFilters) => void;
  options: FilterOptions | null;
  disabled?: boolean;
}>) {
  return (
    <MetricSelect
      value={filters.metric}
      onChange={(metric) => onChange({ ...filters, metric })}
      options={options}
      disabled={disabled}
    />
  );
}
