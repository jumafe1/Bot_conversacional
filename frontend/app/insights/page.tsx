"use client";

import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Lightbulb,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SectionFilters } from "@/components/insights/SectionFilters";
import {
  generateInsights,
  getFilterOptions,
  recomputeSection,
  refreshSectionNarrative,
  type FilterOptions,
  type InsightsReport,
  type InsightsSection,
  type SectionFiltersMap,
  type SectionId,
} from "@/lib/insights-api";
import { cn } from "@/lib/cn";

type Status = "loading" | "ready" | "error";

const SECTION_ICONS: Record<SectionId, string> = {
  anomalies: "⚡",
  trends: "📉",
  benchmarks: "🏁",
  correlations: "🔗",
  opportunities: "🌱",
};

export default function InsightsPage() {
  const [status, setStatus] = useState<Status>("loading");
  const [report, setReport] = useState<InsightsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchReport = useCallback((refresh: boolean) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setStatus("loading");
    setError(null);

    Promise.all([
      generateInsights({ refresh, signal: ac.signal }),
      getFilterOptions({ signal: ac.signal }),
    ])
      .then(([reportData, filterOptions]) => {
        setReport(reportData);
        setOptions(filterOptions);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (ac.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Error desconocido";
        setError(message);
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    fetchReport(false);
    return () => abortRef.current?.abort();
  }, [fetchReport]);

  return (
    <main className="flex min-h-screen w-full flex-col bg-ink-50">
      <TopBar status={status} onRefresh={() => fetchReport(true)} />

      {status === "loading" && <LoadingState />}
      {status === "error" && (
        <ErrorState error={error} onRetry={() => fetchReport(true)} />
      )}
      {status === "ready" && report && options && (
        <ReportView report={report} options={options} />
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Top bar
// ---------------------------------------------------------------------------

function TopBar({
  status,
  onRefresh,
}: Readonly<{ status: Status; onRefresh: () => void }>) {
  return (
    <header className="border-b border-ink-100 bg-white">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-400 hover:text-brand-600"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Inicio
          </Link>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-ink-500">
            <BarChart3 className="h-4 w-4" />
            Reporte de insights
          </div>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={status === "loading"}
          className={cn(
            "flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition",
            "hover:border-brand-400 hover:text-brand-600",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          <RefreshCw
            className={cn("h-3.5 w-3.5", status === "loading" && "animate-spin")}
          />
          Regenerar
        </button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Loading / error
// ---------------------------------------------------------------------------

const LOADING_STEPS = [
  "Analizando anomalías semana a semana…",
  "Corriendo regresiones sobre series de 9 semanas…",
  "Calculando benchmarks por peer group…",
  "Computando matriz de correlaciones…",
  "Pidiendo al bot que narre los hallazgos…",
];

function LoadingState() {
  const [stepIdx, setStepIdx] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setStepIdx((i) => Math.min(i + 1, LOADING_STEPS.length - 1));
    }, 2400);
    return () => clearInterval(id);
  }, []);

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
        <Loader2 className="h-7 w-7 animate-spin" />
      </div>
      <h1 className="mb-2 text-xl font-semibold tracking-tight text-ink-900">
        Generando reporte ejecutivo
      </h1>
      <p className="mb-6 max-w-xl text-sm text-ink-600">
        Esto puede tardar 15–30 segundos la primera vez. Los siguientes
        requests se sirven desde caché en tiempo real.
      </p>

      <ol className="w-full max-w-lg space-y-2 text-left text-sm">
        {LOADING_STEPS.map((step, i) => (
          <li
            key={step}
            className={cn(
              "flex items-center gap-3 rounded-lg border px-3 py-2 transition",
              i < stepIdx && "border-emerald-200 bg-emerald-50 text-emerald-700",
              i === stepIdx && "border-brand-200 bg-brand-50 text-brand-700",
              i > stepIdx && "border-ink-200 bg-white text-ink-500",
            )}
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-[10px] font-semibold">
              {i < stepIdx ? "✓" : i + 1}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ErrorState({
  error,
  onRetry,
}: Readonly<{ error: string | null; onRetry: () => void }>) {
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
        <AlertTriangle className="h-7 w-7" />
      </div>
      <h1 className="mb-2 text-xl font-semibold tracking-tight text-ink-900">
        No se pudo generar el reporte
      </h1>
      <p className="mb-6 max-w-xl font-mono text-sm text-ink-600">
        {error ?? "Error desconocido"}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white shadow-elev-1 transition hover:bg-brand-600"
      >
        Reintentar
      </button>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

function ReportView({
  report,
  options,
}: Readonly<{ report: InsightsReport; options: FilterOptions }>) {
  const generated = new Date(report.generated_at).toLocaleString("es-AR");

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-8">
      <ReportHero snapshot={report.data_snapshot} generatedAt={generated} />
      <ExecutiveSummary summary={report.executive_summary} />
      {report.sections.map((section) => (
        <SectionCard
          key={`${report.generated_at}-${section.id}`}
          section={section}
          options={options}
        />
      ))}
    </div>
  );
}

function ReportHero({
  snapshot,
  generatedAt,
}: Readonly<{
  snapshot: InsightsReport["data_snapshot"];
  generatedAt: string;
}>) {
  return (
    <section className="rounded-2xl border border-ink-200 bg-white p-6 shadow-elev-1">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-ink-500">
        Reporte generado · {generatedAt}
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink-900">
        Insights automáticos
      </h1>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-ink-600">
        <HeroStat label="Zonas analizadas" value={snapshot.total_zones.toLocaleString()} />
        <HeroStat label="Países" value={snapshot.countries.length.toString()} />
        <HeroStat label="Métricas" value={snapshot.n_metrics.toString()} />
        <HeroStat label="Ventana" value={snapshot.week_window} />
      </div>
    </section>
  );
}

function HeroStat({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-ink-400">
        {label}
      </span>
      <span className="font-mono text-sm text-ink-900">{value}</span>
    </div>
  );
}

function ExecutiveSummary({ summary }: Readonly<{ summary: string }>) {
  if (!summary.trim()) return null;
  return (
    <section className="rounded-2xl border border-brand-200 bg-brand-50/50 p-6 shadow-elev-1">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-brand-700">
        <Lightbulb className="h-4 w-4" />
        Resumen ejecutivo
      </div>
      <MarkdownBlock content={summary} className="prose-brand" />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section card — owns filter state + recompute + narrative refresh
// ---------------------------------------------------------------------------

const RECOMPUTE_DEBOUNCE_MS = 350;

function initialFilters<S extends SectionId>(
  sectionId: S,
  section: InsightsSection,
  options: FilterOptions,
): SectionFiltersMap[S] {
  const fallbackMetric = inferMetricForSection(section, options.metrics, 0);
  const firstFinding = section.findings[0] ?? {};
  const metricFromFinding =
    typeof firstFinding.metric === "string" ? firstFinding.metric : undefined;
  const pickMetric = () =>
    metricFromFinding && options.metrics.includes(metricFromFinding)
      ? metricFromFinding
      : fallbackMetric;

  switch (sectionId) {
    case "anomalies":
      return {
        metric: pickMetric(),
        start_week_num: 1,
        end_week_num: 0,
      } as SectionFiltersMap[S];
    case "trends":
      return {
        metric: pickMetric(),
        num_weeks: 9,
      } as SectionFiltersMap[S];
    case "benchmarks":
      return {
        metric: pickMetric(),
        peer_by: "zone_type",
      } as SectionFiltersMap[S];
    case "correlations": {
      const a =
        typeof firstFinding.metric_a === "string" &&
        options.metrics.includes(firstFinding.metric_a)
          ? firstFinding.metric_a
          : fallbackMetric;
      const b =
        typeof firstFinding.metric_b === "string" &&
        options.metrics.includes(firstFinding.metric_b)
          ? firstFinding.metric_b
          : inferSecondMetric(section, options.metrics, a);
      return {
        metric_x: a,
        metric_y: b,
        country: null,
      } as SectionFiltersMap[S];
    }
    case "opportunities":
      return { metric: pickMetric() } as SectionFiltersMap[S];
  }
  return {} as SectionFiltersMap[S];
}

function SectionCard({
  section,
  options,
}: Readonly<{ section: InsightsSection; options: FilterOptions }>) {
  const sectionId = section.id;

  // Initial filters derived from the first finding when possible. If the
  // batch section has narrative but no findings, filters are hydrated once
  // options arrive using the metric mentioned in that narrative.
  const [filters, setFilters] = useState<SectionFiltersMap[typeof sectionId]>(
    () => initialFilters(sectionId, section, options),
  );

  // Chart + findings displayed below. Seeded from the batch report, then
  // replaced by the interactive recompute response when the user tweaks.
  const [chart, setChart] = useState<string | null>(section.chart_png_base64);
  const [findings, setFindings] = useState<Record<string, unknown>[]>(
    section.findings,
  );
  const [totalFlagged, setTotalFlagged] = useState(section.total_flagged);

  // Narrative / recommendation are kept separate from the interactive state
  // so they ONLY update when the user explicitly clicks "Actualizar IA".
  const [narrative, setNarrative] = useState(section.narrative);
  const [recommendation, setRecommendation] = useState(section.recommendation);

  // Snapshot of the filters used to produce the current narrative — lets us
  // show a "desactualizado" badge without diffing the whole filter object.
  const [narrativeFilters, setNarrativeFilters] = useState<
    SectionFiltersMap[typeof sectionId]
  >(() => initialFilters(sectionId, section, options));

  const [recomputing, setRecomputing] = useState(false);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [sectionError, setSectionError] = useState<string | null>(null);

  const recomputeAbort = useRef<AbortController | null>(null);
  const narrativeAbort = useRef<AbortController | null>(null);

  // If the section mounted before filter options were available, the default
  // metric may be "". Hydrate it once ``options`` arrives so the first
  // recompute uses a real metric instead of silently no-oping.
  useEffect(() => {
    if (!options) return;
    setFilters((prev) => {
      const next = hydrateFiltersWithOptions(sectionId, prev, options, section);
      return next === prev ? prev : next;
    });
    setNarrativeFilters((prev) => {
      const next = hydrateFiltersWithOptions(sectionId, prev, options, section);
      return next === prev ? prev : next;
    });
  }, [options, section, sectionId]);

  useEffect(() => {
    if (!filters || !("metric" in filters || "metric_x" in filters)) return;
    if (!hasValidMetric(filters)) return;

    const timer = setTimeout(() => {
      recomputeAbort.current?.abort();
      const ac = new AbortController();
      recomputeAbort.current = ac;

      setRecomputing(true);
      setSectionError(null);
      recomputeSection(sectionId, filters, { signal: ac.signal })
        .then((data) => {
          setChart(data.chart_png_base64);
          setFindings(data.findings);
          setTotalFlagged(data.total_flagged);
        })
        .catch((err: unknown) => {
          if (ac.signal.aborted) return;
          const message =
            err instanceof Error ? err.message : "Error al recalcular";
          setSectionError(message);
        })
        .finally(() => {
          if (!ac.signal.aborted) setRecomputing(false);
        });
    }, RECOMPUTE_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [filters, sectionId]);

  useEffect(() => () => {
    recomputeAbort.current?.abort();
    narrativeAbort.current?.abort();
  }, []);

  const isDirty = useMemo(
    () => !shallowEqual(filters, narrativeFilters),
    [filters, narrativeFilters],
  );

  const handleRefreshNarrative = useCallback(() => {
    narrativeAbort.current?.abort();
    const ac = new AbortController();
    narrativeAbort.current = ac;

    setNarrativeLoading(true);
    setSectionError(null);

    refreshSectionNarrative(sectionId, filters, findings, { signal: ac.signal })
      .then((data) => {
        setNarrative(data.narrative);
        setRecommendation(data.recommendation);
        setNarrativeFilters(filters);
      })
      .catch((err: unknown) => {
        if (ac.signal.aborted) return;
        const message =
          err instanceof Error ? err.message : "Error al actualizar la IA";
        setSectionError(message);
      })
      .finally(() => {
        if (!ac.signal.aborted) setNarrativeLoading(false);
      });
  }, [filters, findings, sectionId]);

  return (
    <section className="rounded-2xl border border-ink-200 bg-white shadow-elev-1">
      <header className="flex items-center justify-between border-b border-ink-100 px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="text-xl" aria-hidden>
            {SECTION_ICONS[sectionId]}
          </span>
          <div>
            <h2 className="text-base font-semibold text-ink-900">
              {section.title}
            </h2>
            <p className="text-[11px] text-ink-500">
              {totalFlagged} hallazgo{totalFlagged === 1 ? "" : "s"} detectado
              {totalFlagged === 1 ? "" : "s"}
            </p>
          </div>
        </div>
        {isDirty && (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
            IA desactualizada
          </span>
        )}
      </header>

      <div className="space-y-5 p-6">
        <div
          className={cn(
            "flex flex-wrap items-end gap-3 rounded-xl border border-ink-200 bg-ink-50/70 p-3",
          )}
        >
          <SectionFilters
            sectionId={sectionId}
            filters={filters}
            onChange={setFilters as (f: SectionFiltersMap[typeof sectionId]) => void}
            options={options}
            disabled={recomputing}
          />
          {recomputing && (
            <div className="flex items-center gap-1.5 text-[11px] text-ink-500">
              <Loader2 className="h-3 w-3 animate-spin" />
              Recalculando…
            </div>
          )}
        </div>

        {sectionError && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            {sectionError}
          </div>
        )}

        {chart ? (
          <figure className="overflow-hidden rounded-xl border border-ink-200 bg-ink-50">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/png;base64,${chart}`}
              alt={`Gráfico de ${section.title}`}
              className={cn(
                "w-full transition-opacity",
                recomputing && "opacity-60",
              )}
            />
          </figure>
        ) : (
          <div className="rounded-xl border border-dashed border-ink-200 bg-ink-50/60 p-6 text-center text-xs text-ink-500">
            Sin datos suficientes para renderizar un gráfico con estos
            filtros.
          </div>
        )}

        <div className="rounded-xl border border-ink-200 bg-white p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
              <Sparkles className="h-3.5 w-3.5" />
              Análisis IA
            </div>
            <button
              type="button"
              onClick={handleRefreshNarrative}
              disabled={narrativeLoading}
              className={cn(
                "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-semibold transition",
                isDirty
                  ? "border-brand-400 bg-brand-500 text-white hover:bg-brand-600"
                  : "border-ink-200 bg-white text-ink-700 hover:border-brand-400 hover:text-brand-600",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {narrativeLoading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              Actualizar análisis IA
            </button>
          </div>
          <MarkdownBlock content={narrative} />
        </div>

        {findings.length > 0 && (
          <FindingsTable findings={findings} total={totalFlagged} />
        )}

        <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4">
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
            <Lightbulb className="h-3.5 w-3.5" />
            Recomendación
          </div>
          <MarkdownBlock content={recommendation} />
        </div>
      </div>
    </section>
  );
}

function hasValidMetric(filters: SectionFiltersMap[SectionId]): boolean {
  const f = filters as unknown as Record<string, unknown>;
  if ("metric_x" in f && "metric_y" in f) {
    return (
      typeof f.metric_x === "string" &&
      f.metric_x !== "" &&
      typeof f.metric_y === "string" &&
      f.metric_y !== ""
    );
  }
  return typeof f.metric === "string" && f.metric !== "";
}

function hydrateFiltersWithOptions<S extends SectionId>(
  sectionId: S,
  current: SectionFiltersMap[S],
  options: FilterOptions,
  section: InsightsSection,
): SectionFiltersMap[S] {
  const metrics = options.metrics ?? [];
  if (metrics.length === 0) return current;

  const c = current as unknown as Record<string, unknown>;
  if (sectionId === "correlations") {
    const x = typeof c.metric_x === "string" ? c.metric_x : "";
    const y = typeof c.metric_y === "string" ? c.metric_y : "";
    const needsX = x === "";
    const needsY = y === "";
    if (!needsX && !needsY) return current;
    const nextX = needsX ? inferMetricForSection(section, metrics, 0) : x;
    return {
      ...current,
      metric_x: nextX,
      metric_y: needsY ? inferSecondMetric(section, metrics, nextX) : y,
    } as SectionFiltersMap[S];
  }
  const m = typeof c.metric === "string" ? c.metric : "";
  if (m !== "") return current;
  return {
    ...current,
    metric: inferMetricForSection(section, metrics, 0),
  } as SectionFiltersMap[S];
}

function inferMetricForSection(
  section: InsightsSection,
  metrics: string[],
  offset: number,
): string {
  const firstFinding = section.findings[0] ?? {};
  const findingMetric =
    offset === 0
      ? firstFinding.metric ?? firstFinding.metric_a
      : firstFinding.metric_b;
  if (typeof findingMetric === "string" && metrics.includes(findingMetric)) {
    return findingMetric;
  }

  const text = `${section.title}\n${section.narrative}\n${section.recommendation}`;
  const mentioned = metrics.filter((metric) => text.includes(metric));
  return mentioned[offset] ?? mentioned[0] ?? metrics[offset] ?? metrics[0] ?? "";
}

function inferSecondMetric(
  section: InsightsSection,
  metrics: string[],
  firstMetric: string,
): string {
  const candidate = inferMetricForSection(section, metrics, 1);
  if (candidate && candidate !== firstMetric) return candidate;
  return metrics.find((metric) => metric !== firstMetric) ?? "";
}

function shallowEqual(a: object, b: object): boolean {
  const ra = a as Record<string, unknown>;
  const rb = b as Record<string, unknown>;
  const ka = Object.keys(ra);
  const kb = Object.keys(rb);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => ra[k] === rb[k]);
}

// ---------------------------------------------------------------------------
// Findings table
// ---------------------------------------------------------------------------

function FindingsTable({
  findings,
  total,
}: Readonly<{ findings: Record<string, unknown>[]; total: number }>) {
  const keys = Array.from(
    findings.reduce<Set<string>>((set, row) => {
      Object.keys(row).forEach((k) => set.add(k));
      return set;
    }, new Set()),
  );

  return (
    <details className="rounded-xl border border-ink-200 bg-ink-50/60 p-3">
      <summary className="cursor-pointer select-none text-xs font-medium text-ink-700">
        Ver datos ({findings.length} de {total} filas)
      </summary>
      <div className="mt-3 max-h-80 overflow-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-500">
              {keys.map((k) => (
                <th
                  key={k}
                  className="sticky top-0 bg-ink-50 px-2 py-1.5 text-left font-medium"
                >
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {findings.map((row, i) => {
              const rowKey = buildRowKey(row, i);
              return (
                <tr key={rowKey} className="border-t border-ink-100 text-ink-700">
                  {keys.map((k) => (
                    <td key={k} className="px-2 py-1 align-top font-mono">
                      {formatCell(row[k])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Math.abs(v) < 0.001 && v !== 0) return v.toExponential(2);
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(3);
  }
  if (typeof v === "string" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return "—";
  }
}

function buildRowKey(row: Record<string, unknown>, index: number): string {
  const candidates = ["zone", "metric", "metric_a", "metric_b", "country"];
  const parts: string[] = [];
  for (const c of candidates) {
    const v = row[c];
    if (typeof v === "string") parts.push(v);
  }
  return parts.length > 0 ? parts.join("|") : `row-${index}`;
}

function MarkdownBlock({
  content,
  className,
}: Readonly<{ content: string; className?: string }>) {
  return (
    <div
      className={cn(
        "prose prose-sm max-w-none text-ink-800",
        "prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-strong:text-ink-900",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
