import {
  ArrowRight,
  BarChart3,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/cn";

export default function LandingPage() {
  return (
    <main className="flex min-h-screen w-full flex-col">
      <Hero />

      <section className="mx-auto flex w-full max-w-5xl flex-1 items-center px-6 pb-16">
        <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-2">
          <OptionCard
            href="/chat"
            icon={<MessageSquare className="h-6 w-6" />}
            title="Chatear con los datos"
            description={
              "Hacé preguntas en lenguaje natural sobre métricas operativas " +
              "de los 9 mercados LATAM. Rankings, comparaciones, tendencias, " +
              "cruces multivariable — sin escribir una línea de SQL."
            }
            bullets={[
              "Top zonas por cualquier métrica, con filtros por país / tipo / prioridad",
              "Tendencias semanales (hasta 9 semanas atrás)",
              "Comparaciones Wealthy vs Non Wealthy y cross-country",
              "Memoria conversacional entre preguntas",
            ]}
            cta="Abrir chat"
            accent="primary"
          />

          <OptionCard
            href="/insights"
            icon={<BarChart3 className="h-6 w-6" />}
            title="Generar reporte de insights"
            description={
              "Reporte ejecutivo automático con los hallazgos más relevantes: " +
              "anomalías, tendencias preocupantes, benchmarking, correlaciones " +
              "y oportunidades — con gráficos y recomendaciones accionables."
            }
            bullets={[
              "Detección automática de cambios WoW > 10%",
              "Regresiones sobre series de 9 semanas para flagear deterioros",
              "Benchmarking vs peer group (mismo país + zone_type)",
              "Matriz de correlaciones entre las 13 métricas",
            ]}
            cta="Generar reporte"
            accent="secondary"
            badge="Beta"
          />
        </div>
      </section>

      <Footer />
    </main>
  );
}

// ---------------------------------------------------------------------------
// Internal building blocks
// ---------------------------------------------------------------------------

function Hero() {
  return (
    <header className="border-b border-ink-100 bg-white">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-10 md:py-14">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 text-white shadow-elev-2">
            <Sparkles className="h-5 w-5" />
          </div>
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-ink-500">
            Rappi · Data Bot
          </span>
        </div>

        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-ink-900 md:text-4xl">
          Consultá métricas operativas de 9 mercados LATAM en lenguaje natural.
        </h1>
        <p className="max-w-2xl text-base text-ink-600">
          Elegí un flujo para empezar: chat interactivo con el bot de datos, o
          un reporte ejecutivo generado automáticamente sobre la base
          cargada.
        </p>
      </div>
    </header>
  );
}

interface OptionCardProps {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  bullets: string[];
  cta: string;
  accent: "primary" | "secondary";
  badge?: string;
}

function OptionCard({
  href,
  icon,
  title,
  description,
  bullets,
  cta,
  accent,
  badge,
}: Readonly<OptionCardProps>) {
  const accentStyles =
    accent === "primary"
      ? {
          iconBg: "bg-brand-500 text-white",
          cta:
            "bg-brand-500 text-white hover:bg-brand-600 shadow-elev-2",
          ring: "hover:border-brand-400",
        }
      : {
          iconBg: "bg-ink-900 text-white",
          cta:
            "bg-ink-900 text-white hover:bg-ink-700 shadow-elev-2",
          ring: "hover:border-ink-400",
        };

  return (
    <Link
      href={href}
      className={cn(
        "group relative flex flex-col gap-5 rounded-2xl border border-ink-200 bg-white p-7 shadow-elev-1 transition",
        accentStyles.ring,
      )}
    >
      {badge && (
        <span className="absolute right-5 top-5 rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-700">
          {badge}
        </span>
      )}

      <div
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-xl",
          accentStyles.iconBg,
        )}
      >
        {icon}
      </div>

      <div className="space-y-2">
        <h2 className="text-xl font-semibold text-ink-900">{title}</h2>
        <p className="text-sm leading-relaxed text-ink-600">{description}</p>
      </div>

      <ul className="space-y-1.5 text-xs text-ink-600">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-2">
            <span className="mt-[5px] h-1 w-1 shrink-0 rounded-full bg-ink-400" />
            <span>{b}</span>
          </li>
        ))}
      </ul>

      <div
        className={cn(
          "mt-2 inline-flex w-fit items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition",
          accentStyles.cta,
        )}
      >
        {cta}
        <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
      </div>
    </Link>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink-100 bg-white">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4 text-xs text-ink-500">
        <span>
          Datos: 11.610 filas de métricas · 13 KPIs · 9 países · últimas 9
          semanas
        </span>
        <span className="font-mono text-[11px]">v0.1.0</span>
      </div>
    </footer>
  );
}
