import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, createChart, LastPriceAnimationMode, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { exchangeName, pct, signedUsd, usd } from "@/lib/format";
import type { Overview } from "@/lib/types";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
const SHARE = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 0 });
const PERIODS = [7, 30];
/** Cores das corretoras no gráfico de rosca, na ordem em que o backend as devolve (maior primeiro). */
const EX_COLORS = ["#a78bfa", "#22d3ee", "#f0abfc", "#fdba74", "#86efac"];

function Pill({ value, children }: { value: number; children: React.ReactNode }) {
  const up = value >= 0;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] ${up ? "bg-alta/10 text-[#6ee7b7]" : "bg-sair/10 text-[#fda4af]"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span>{children}
    </span>
  );
}

/**
 * Patrimônio total, resultado do dia e desde a compra, com o gráfico dos últimos 7 ou 30 dias.
 * `liveDelta` soma ao total e `livePnlDelta` ao resultado a variação dos ticks desde a consulta.
 * `day` é o resultado das últimas 24 h somado moeda a moeda.
 */
export function PortfolioHero({ ov, liveDelta, livePnlDelta, day }:
  { ov: Overview; liveDelta: number; livePnlDelta: number; day?: { usd: number; pct: number | null } }) {
  const [days, setDays] = useState(30);
  const history = useMemo(() => ov.history.slice(-days), [ov.history, days]);  // tick ao vivo não reenvia a série
  const total = ov.total_usd + liveDelta;
  const pnl = ov.pnl_usd + livePnlDelta;
  const pnlPct = ov.invested_usd ? pnl / ov.invested_usd : null;
  return (
    <section aria-label="Patrimônio" className="fade-in relative flex min-w-0 flex-[2_1_560px] flex-col gap-5 overflow-hidden rounded-[20px] border border-borda bg-painel p-6">
      <div aria-hidden="true" className="absolute left-0 top-0 h-px w-full overflow-hidden">
        <div className="beam h-px w-1/4 bg-linear-to-r from-transparent via-violeta to-transparent" />
      </div>
      <div className="flex flex-wrap justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="text-[13px] text-texto-2">Patrimônio nas 4 corretoras</span>
          <span className="font-mono text-[clamp(32px,4vw,46px)] font-semibold leading-none tracking-tight">{usd(total)}</span>
          {ov.total_brl !== null && ov.total_usd > 0 && (
            <span className="font-mono text-[15px] text-texto-2">{BRL.format(total * (ov.total_brl / ov.total_usd))}</span>
          )}
        </div>
        <div role="group" aria-label="Período do gráfico" className="flex h-fit gap-0.5 rounded-xl border border-borda bg-[#0a0c12] p-1">
          {PERIODS.map((d) => (
            <button key={d} type="button" aria-pressed={d === days} onClick={() => setDays(d)}
              className={`min-h-9 rounded-[9px] px-3.5 text-[13px] outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                d === days ? "bg-borda font-semibold text-white" : "text-texto-2 hover:text-texto"}`}>{d} dias</button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {day && <Pill value={day.usd}>Hoje <b className="font-mono font-semibold">{signedUsd(day.usd)}{day.pct !== null && ` (${pct(day.pct * 100)})`}</b></Pill>}
        <Pill value={pnl}>Resultado <b className="font-mono font-semibold">{signedUsd(pnl)}{pnlPct !== null && ` (${pct(pnlPct * 100)})`}</b></Pill>
        {ov.invested_usd > 0 && <span className="rounded-full bg-[#131722] px-3 py-1.5 text-[13px] text-texto-2">Investido {usd(ov.invested_usd)}</span>}
      </div>
      <HistoryChart history={history} last={total} />
    </section>
  );
}

/** Divisão do patrimônio por corretora: rosca e lista. Corretora com saldo velho fica marcada. */
export function ExchangeSplit({ ov }: { ov: Overview }) {
  let offset = 0;
  return (
    <section aria-labelledby="por-corretora" className="fade-in flex min-w-0 flex-col gap-4 rounded-[20px] border border-borda bg-painel p-6 [animation-delay:80ms]">
      <div className="flex flex-col gap-1">
        <h2 id="por-corretora" className="m-0 text-base font-semibold">Por corretora</h2>
        <span className="text-[13px] text-texto-2">Onde está o dinheiro hoje.</span>
      </div>
      <div className="flex items-center gap-5">
        <svg width="124" height="124" viewBox="0 0 42 42" aria-hidden="true" className="shrink-0 -rotate-90">
          <circle cx="21" cy="21" r="15.9" fill="none" stroke="#151a26" strokeWidth="5" />
          {ov.by_exchange.map((e, i) => {
            const share = e.share * 100, el = (
              <circle key={e.exchange} cx="21" cy="21" r="15.9" fill="none" stroke={EX_COLORS[i % EX_COLORS.length]} strokeWidth="5"
                pathLength={100} strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-offset} />
            );
            offset += share;
            return el;
          })}
        </svg>
        <ul className="m-0 flex min-w-0 grow list-none flex-col gap-2.5 p-0">
          {ov.by_exchange.map((e, i) => (
            <li key={e.exchange} className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-sm">
              <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: EX_COLORS[i % EX_COLORS.length] }} />
              <span data-name className="grow">{exchangeName(e.exchange)}</span>
              <span className="font-mono text-[13px] text-texto-2">{SHARE.format(e.share)} · {usd(e.usd)}</span>
              {e.stale && <span className="w-full pl-5 text-xs text-[#fcd34d]">corretora desatualizada</span>}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** Série de área do lightweight-charts. O último ponto acompanha o total ao vivo. */
function HistoryChart({ history, last }: { history: Overview["history"]; last: number }) {
  const el = useRef<HTMLDivElement>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const chart = useRef<IChartApi | null>(null);

  useEffect(() => {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const c = createChart(el.current!, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#9aa3b5", fontFamily: "Geist Mono Variable, monospace" },
      grid: { vertLines: { visible: false }, horzLines: { color: "#151a26" } },
      rightPriceScale: { visible: false }, timeScale: { visible: false },
      crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
      handleScroll: false, handleScale: false,
    });
    const s = c.addSeries(AreaSeries, {
      lineColor: "#a78bfa", topColor: "rgba(167,139,250,0.28)", bottomColor: "rgba(167,139,250,0)", lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      lastPriceAnimation: still ? LastPriceAnimationMode.Disabled : LastPriceAnimationMode.Continuous,
    });
    series.current = s;
    chart.current = c;
    return () => { series.current = null; chart.current = null; c.remove(); };
  }, []);

  // Consulta nova ou troca de período muda só os dados: recriar o gráfico piscaria a tela.
  useEffect(() => {
    series.current?.setData(history.map((h) => ({ time: h.ts, value: h.usd })));
    chart.current?.timeScale().fitContent();
  }, [history]);

  useEffect(() => {
    const day = history.at(-1)?.ts;
    if (day) series.current?.update({ time: day, value: last });
  }, [history, last]);

  return (
    <div ref={el} role="img" aria-label={`Evolução do patrimônio nos últimos ${history.length} dias`} className="h-[170px] min-w-0" />
  );
}
