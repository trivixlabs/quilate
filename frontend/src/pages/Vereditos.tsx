import { useEffect, useState } from "react";
import { Link } from "react-router";
import { of } from "@/lib/analyst";
import { getMarket, getOverview, getVerdicts } from "@/lib/api";
import { usd } from "@/lib/format";
import { useLive, withLive } from "@/lib/live";
import type { Market, Overview, Verdict, Verdicts } from "@/lib/types";
import { ExchangeSplit, PortfolioHero } from "@/components/PortfolioHero";
import { VERDICT, VerdictCard } from "@/components/VerdictCard";

const GROUPS: Verdict[] = ["Sair", "Reduzir", "Manter"];
const DAY = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });
const N2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Aba Visão geral: patrimônio, corretoras, termômetro do mercado e o veredito de hoje em três colunas. */
export function Vereditos() {
  const { prices, lastEvent } = useLive();
  const [data, setData] = useState<{ ov: Overview; v: Verdicts } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let off = false;
    Promise.all([getOverview(), getVerdicts()]).then(
      ([ov, v]) => { if (!off) { setData({ ov, v }); setError(null); } },
      (e: Error) => { if (!off) setError(e.message); },
    );
    return () => { off = true; };
  }, [lastEvent]);

  if (!data) {
    return error
      ? <p role="alert" className="text-sair">Não consegui carregar a visão geral ({error}).</p>
      : <p className="text-texto-2">Carregando…</p>;
  }

  const now = Date.now();
  let delta = 0, pnlDelta = 0, dayUsd = 0, dayBase = 0, index = 0;
  const columns = GROUPS.map((verdict) => {
    const cards = data.v.groups[verdict].map((c) => {
      const live = prices[c.symbol];
      const card = live ? withLive(c, live.price) : c;
      const gain = card.value_usd - c.value_usd;
      delta += gain;
      if (c.pnl_usd !== null && !c.cost_unknown) pnlDelta += gain; // o resultado do overview só soma custo conhecido
      if (card.change_24h !== null && card.change_24h > -1) {  // moeda sem fechamento de ontem fica fora do dia
        const before = card.value_usd / (1 + card.change_24h);
        dayUsd += card.value_usd - before;
        dayBase += before;
      }
      return { card, flash: live && live.flashUntil > now ? live.dir : 0, flashKey: live?.flashUntil ?? 0, index: index++ };
    });
    return { verdict, cards, value: cards.reduce((a, x) => a + x.card.value_usd, 0) };
  });
  const counts = columns.map((c) => c.cards.length);
  const day = new Date(`${data.v.day}T00:00:00Z`);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <span className="text-[13px] text-texto-2">{DAY.format(day).replace(/^./, (c) => c.toUpperCase())}</span>
        <h1 className="m-0 text-[28px] font-semibold tracking-tight">Visão geral</h1>
      </header>
      {!data.ov.playbook_approved && (
        <p className="m-0 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-reduzir/35 bg-reduzir/10 px-4 py-3 text-sm text-[#fcd34d]">
          Manual {of(data.ov.analyst_name)} ainda não revisado
          <Link to="/analista" className="font-semibold text-[#fcd34d] underline">Revisar regras</Link>
        </p>
      )}
      {error && <p role="alert" className="m-0 text-sm text-sair">Falha ao atualizar ({error}). Mostrando a última consulta.</p>}

      <div className="flex flex-wrap gap-5">
        <PortfolioHero ov={data.ov} liveDelta={delta} livePnlDelta={pnlDelta}
          day={{ usd: dayUsd, pct: dayBase > 0 ? dayUsd / dayBase : null }} />
        <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-5">
          <ExchangeSplit ov={data.ov} />
          <MarketStrip />
        </div>
      </div>

      <section aria-labelledby="hoje" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2 id="hoje" className="m-0 text-xl font-semibold">Veredito de hoje</h2>
            <span className="text-[13px] text-texto-2">A régua de 7 sinais e a IA leram a análise {of(data.ov.analyst_name)}. O bot avisa só quando um veredito muda.</span>
          </div>
          {counts.some(Boolean) && (
            <div aria-hidden="true" className="flex h-2.5 w-[260px] max-w-full gap-[3px] overflow-hidden rounded-full">
              {columns.map((c) => c.cards.length > 0 && <span key={c.verdict} className={VERDICT[c.verdict].bg} style={{ flex: c.cards.length }} />)}
            </div>
          )}
        </div>
        <div className="grid items-start gap-5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))" }}>
          {columns.map((col) => {
            const v = VERDICT[col.verdict];
            return (
              <section key={col.verdict} aria-label={col.verdict} className="flex min-w-0 flex-col gap-3">
                <div className="flex items-center gap-2.5 px-1">
                  <span aria-hidden="true" className={`inline-flex size-[26px] items-center justify-center rounded-lg ${v.tint} ${v.text}`}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d={v.icon} /></svg>
                  </span>
                  <h3 className={`m-0 text-[15px] font-semibold ${v.text}`}>{col.verdict}</h3>
                  <span className="text-[13px] text-texto-2">{col.cards.length} {col.cards.length === 1 ? "moeda" : "moedas"}</span>
                  <span className="ml-auto flex flex-col items-end">
                    <span className="font-mono text-[13px] text-texto-2">{usd(col.value)}</span>
                    <span className="text-[11px] text-[#8a93a6]">{v.hint}</span>
                  </span>
                </div>
                {col.cards.length === 0 && <p className="m-0 rounded-2xl border border-dashed border-borda px-4 py-6 text-center text-sm text-texto-2">Nenhuma moeda neste grupo.</p>}
                {col.cards.map((x) => <VerdictCard key={x.card.symbol} {...x} analyst={data.ov.analyst_name} />)}
              </section>
            );
          })}
        </div>
      </section>
    </div>
  );
}

const FNG: [number, string][] = [[25, "medo extremo"], [45, "medo"], [56, "neutro"], [76, "ganância"], [101, "ganância extrema"]];

/** Três números do mercado. Busca à parte: sem eles a visão geral funciona igual. */
function MarketStrip() {
  const [m, setM] = useState<Market | null>(null);
  useEffect(() => {
    let off = false;
    getMarket().then((x) => { if (!off) setM(x); }, () => { /* o cartão fica com traço */ });
    return () => { off = true; };
  }, []);
  const n = (v: unknown, key?: string) => {
    const x = key && v && typeof v === "object" ? (v as Record<string, unknown>)[key] : v;
    return typeof x === "number" && Number.isFinite(x) ? x : null;
  };
  const fng = n(m?.fng?.value), dom = n(m?.cg_global?.value, "btc_dominance"), alt = n(m?.alt_season?.value);
  const ch = m?.cg_global?.change_7d ?? null;
  const tiles: [string, string, string][] = [
    ["Medo e ganância", fng === null ? "—" : String(fng), fng === null ? "sem dado" : FNG.find(([lim]) => fng < lim)![1]],
    ["Dominância BTC", dom === null ? "—" : `${N2.format(dom)}%`, ch === null ? "7 dias sem dado" : `${ch >= 0 ? "+" : "−"}${N2.format(Math.abs(ch))} pp em 7 d`],
    ["Temporada alt", alt === null ? "—" : String(alt), "de 100"],
  ];
  return (
    <section aria-label="Mercado hoje" className="fade-in grid grid-cols-3 gap-2 [animation-delay:140ms]">
      {tiles.map(([label, value, note]) => (
        <Link key={label} to="/mercado" className="flex min-w-0 flex-col gap-1 rounded-xl border border-borda bg-painel p-3 no-underline outline-offset-2 outline-violeta transition-colors hover:border-[#2b3247] focus-visible:outline-2">
          <span className="truncate text-[11px] text-texto-2">{label}</span>
          <span className="font-mono text-lg font-semibold text-texto">{value}</span>
          <span className="truncate text-[11px] text-texto-2">{note}</span>
        </Link>
      ))}
    </section>
  );
}
