import { useEffect, useId, useState, type ReactNode } from "react";
import { NavLink, useParams } from "react-router";
import { getCoin, getOverview, getVerdicts } from "@/lib/api";
import { exchangeName, pct, qty, signedUsd, usd } from "@/lib/format";
import { useLive, useLiveQuery, withLive, type LiveState } from "@/lib/live";
import type { Card, CoinDetail, Verdict } from "@/lib/types";
import { CostOverrideForm } from "@/components/CostOverrideForm";
import { AnalystQuotes } from "@/components/AnalystQuotes";
import { PriceChart } from "@/components/PriceChart";
import { SignalList } from "@/components/SignalList";
import { FLAGS, hue, VERDICT } from "@/components/VerdictCard";

const ORDER: Verdict[] = ["Sair", "Reduzir", "Manter"];

const flashOf = (prices: LiveState, symbol: string, now: number) => {
  const live = prices[symbol];
  return { flash: live && live.flashUntil > now ? live.dir : 0, flashKey: live?.flashUntil ?? 0 };
};
const flashClass = (f: number) => (f > 0 ? "flash-up" : f < 0 ? "flash-down" : "");

/** Foco por moeda (protótipo C): lista lateral, veredito, indicadores, gráfico, sinais, falas, argumentos e custo. */
export function Moeda() {
  const { symbol = "" } = useParams();
  const { prices, lastEvent } = useLive();
  const [list, setList] = useState<Card[]>([]);
  const [coin, setCoin] = useState<CoinDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(0);
  const { data: ov } = useLiveQuery(getOverview);  // só o nome de exibição do analista: sem ele, o termo genérico

  useEffect(() => {
    let off = false;
    getVerdicts().then((v) => { if (!off) setList(ORDER.flatMap((g) => v.groups[g])); }, () => { /* a lista some, o foco continua */ });
    return () => { off = true; };
  }, [lastEvent]);

  useEffect(() => {
    let off = false;
    setError(null); // o erro de outra moeda não vale para esta
    getCoin(symbol).then(
      (c) => { if (!off) { setCoin(c); setError(null); } },
      (e: Error) => { if (!off) setError(e.message); },
    );
    return () => { off = true; };
  }, [symbol, lastEvent, saved]);

  const now = Date.now();
  return (
    <div className="flex flex-col gap-5">
      <CoinNav list={list} prices={prices} now={now} />
      <div className="flex min-w-0 flex-col gap-5">
        {/* A moeda anterior fica na tela até a nova chegar: assim o gráfico não é desmontado na troca. */}
        {!coin || (error && coin.symbol !== symbol)
          ? error
            ? <p role="alert" className="m-0 text-sair">Não consegui carregar {symbol} ({error}).</p>
            : <p className="m-0 text-texto-2">Carregando…</p>
          : <Focus coin={coin} prices={prices} now={now} error={error} onSaved={() => setSaved((n) => n + 1)} analyst={ov?.analyst_name ?? ""} />}
      </div>
    </div>
  );
}

function CoinNav({ list, prices, now }: { list: Card[]; prices: LiveState; now: number }) {
  return (
    <nav aria-label="Moedas da carteira" className="-mx-1 overflow-x-auto px-1 pb-1">
      <ul className="m-0 flex list-none gap-2 p-0">
        {list.map((card) => {
          const live = prices[card.symbol];
          const c = live ? withLive(card, live.price) : card;
          const { flash, flashKey } = flashOf(prices, c.symbol, now);
          return (
            <li key={c.symbol} className="shrink-0">
              <NavLink to={`/moeda/${c.symbol}`}
                className={({ isActive }) => `flex min-h-11 items-center gap-2.5 rounded-xl border px-3.5 text-texto no-underline outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                  isActive ? "border-[#3a4258] bg-[#171b27]" : "border-borda bg-painel hover:bg-[#121621]"}`}>
                <span aria-hidden="true" className={`size-2 rounded-full ${VERDICT[c.verdict].bg}`} />
                <span className="text-sm font-semibold">{c.symbol}</span>
                <span className="sr-only">, {c.verdict}</span>
                {c.change_24h !== null && (
                  <span key={flashKey} className={`rounded-md px-1 font-mono text-[11px] ${flashClass(flash)} ${c.change_24h >= 0 ? "text-[#6ee7b7]" : "text-[#fda4af]"}`}>{pct(c.change_24h * 100)}</span>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Focus({ coin, prices, now, error, onSaved, analyst }: {
  coin: CoinDetail; prices: LiveState; now: number; error: string | null; onSaved: () => void; analyst: string;
}) {
  const live = prices[coin.symbol];
  const c = live ? withLive(coin, live.price) : coin;
  const { flash, flashKey } = flashOf(prices, c.symbol, now);
  const diverges = c.ai_verdict !== null && c.ai_verdict !== c.rubric_verdict;
  const costUnknown = c.cost_unknown || c.pnl_usd === null;

  return (
    <>
      {error && <p role="alert" className="m-0 text-sm text-sair">Falha ao atualizar ({error}). Mostrando a última consulta.</p>}
      {/* fade-in por fora da moldura: na seção, a borda apareceria através do fundo transparente; na moldura, apagaria o giro. */}
      <div className="fade-in">
        <div className={`rounded-[22px] p-px ${c.verdict === "Sair" ? "glow-sair bg-[#2a1720]" : "glow-foco"}`}>
          <section aria-label="Resumo da moeda" className="flex flex-col gap-5 rounded-[21px] bg-painel p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-5">
              <div className="flex min-w-0 items-center gap-4">
                <span aria-hidden="true" className="flex size-14 shrink-0 items-center justify-center rounded-full text-[22px] font-bold text-white"
                  style={{ background: hue(c.symbol) }}>{c.symbol[0]}</span>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-baseline gap-x-2.5">
                    <h1 className="m-0 text-[26px] font-semibold tracking-tight">{c.name}</h1>
                    <span className="text-lg text-texto-2">{c.symbol}</span>
                  </span>
                  <span className="text-[13px] text-texto-2">
                    {[...c.exchanges.map(exchangeName), `${qty(c.qty)} ${c.symbol}`].join(" · ")}
                  </span>
                </div>
              </div>
              <div role="status" aria-label="Veredito"
                className={`flex min-w-[200px] flex-col gap-1.5 rounded-2xl border px-4 py-3 ${VERDICT[c.verdict].tint} ${
                  c.verdict === "Sair" ? "border-sair/35" : c.verdict === "Reduzir" ? "border-reduzir/35" : "border-manter/35"}`}>
                <span className={`inline-flex items-center gap-2 text-xl font-bold ${VERDICT[c.verdict].text}`}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={VERDICT[c.verdict].icon} /></svg>
                  {c.verdict}
                </span>
                <span className="text-xs text-[#c3c9d6]">Régua: {c.rubric_verdict} · IA: {c.ai_verdict ?? "não opinou"}</span>
                {c.confidence !== null
                  ? <>
                      <span role="meter" aria-label={`Confiança ${Math.round(c.confidence * 100)}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(c.confidence * 100)}
                        className="block h-[5px] overflow-hidden rounded-full bg-black/30">
                        <span className={`block h-full rounded-full transition-[width] duration-700 ${VERDICT[c.verdict].bg}`} style={{ width: `${c.confidence * 100}%` }} />
                      </span>
                      <span className="text-xs text-texto-2">Confiança {Math.round(c.confidence * 100)}% · {c.alerts} de {c.signals.length} sinais em alerta</span>
                    </>
                  : <span className="text-xs text-texto-2">Só a régua · {c.alerts} de {c.signals.length} sinais em alerta</span>}
                {(diverges || c.flag) && (
                  <span className="text-xs text-[#fcd34d]">
                    {[diverges && `régua: ${c.rubric_verdict}, IA: ${c.ai_verdict}`, c.flag && (FLAGS[c.flag] ?? c.flag)].filter(Boolean).join(" · ")}
                  </span>
                )}
              </div>
            </div>

            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
              <Indicator label="Preço agora">
                <span key={flashKey} className={`-ml-1.5 whitespace-nowrap rounded-md px-1.5 py-0.5 ${flashClass(flash)}`}>{usd(c.price_usd)}</span>
                {c.change_24h !== null && (
                  <span className={`ml-2 text-xs ${c.change_24h >= 0 ? "text-[#6ee7b7]" : "text-[#fda4af]"}`}>
                    <span aria-hidden="true">{c.change_24h >= 0 ? "▲ " : "▼ "}</span>{pct(c.change_24h * 100)}
                  </span>
                )}
              </Indicator>
              <Indicator label="Preço médio de compra">
                {c.avg_cost_usd !== null ? usd(c.avg_cost_usd) : <span className="text-texto-2">desconhecido</span>}
              </Indicator>
              <Indicator label="Posição">{usd(c.value_usd)}</Indicator>
              <Indicator label="Resultado">
                {costUnknown
                  ? <span className="text-texto-2">custo desconhecido</span>
                  : <span className={c.pnl_usd! >= 0 ? "text-[#6ee7b7]" : "text-[#fda4af]"}>{signedUsd(c.pnl_usd!)}</span>}
              </Indicator>
            </div>

            <PriceChart candles={coin.candles} avg={c.avg_cost_usd} last={c.price_usd} />
          </section>
        </div>
      </div>

      <div className="grid items-start gap-5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))" }}>
        <div className="flex flex-col gap-5">
          <SignalList signals={c.signals} />
          <Holdings coin={c} />
          <CostOverrideForm key={c.symbol} symbol={c.symbol} costUnknown={c.cost_unknown} onSaved={onSaved} />
        </div>
        <div className="flex flex-col gap-5">
          <Arguments pros={c.pros} cons={c.cons} risk={c.main_risk} />
          <AnalystQuotes quotes={c.quotes} noAnalyst={c.no_analyst} name={analyst} />
        </div>
      </div>
    </>
  );
}

function Indicator({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 rounded-xl bg-[#11141d] p-3.5">
      <span id={id} className="text-xs text-texto-2">{label}</span>
      <span aria-labelledby={id} className="font-mono text-lg">{children}</span>
    </div>
  );
}

function Holdings({ coin: c }: { coin: CoinDetail }) {
  return (
    <section aria-label="Quantidade por corretora" className="fade-in flex flex-col gap-3 rounded-[18px] border border-borda bg-painel p-5 [animation-delay:180ms]">
      <h2 className="m-0 text-base font-semibold">Quantidade por corretora</h2>
      {c.by_exchange.length === 0 && <p className="m-0 text-sm text-texto-2">Nenhuma posição nas corretoras.</p>}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {c.by_exchange.map((p) => {
          const share = c.qty ? Math.round((p.qty / c.qty) * 100) : 0;
          return (
            <li key={`${p.exchange}/${p.wallet}`} className="flex flex-col gap-1.5 text-sm">
              <span className="flex items-center justify-between gap-3">
                <span>{exchangeName(p.exchange)}{p.wallet && <span className="text-texto-2"> · carteira {p.wallet}</span>}</span>
                <span className="font-mono text-[13px] text-[#c9ceda]">{qty(p.qty)}</span>
              </span>
              <span role="meter" aria-label={`${share}% da quantidade`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={share}
                className="block h-1 overflow-hidden rounded-full bg-borda">
                <span className="block h-full rounded-full bg-violeta transition-[width] duration-700" style={{ width: `${share}%` }} />
              </span>
            </li>
          );
        })}
      </ul>
      {c.by_exchange.length > 1 && (
        <p className="m-0 flex items-center justify-between gap-3 border-t border-[#262c3d] pt-2.5 text-sm font-semibold">
          <span>Total</span>
          <span className="font-mono text-[13px]">{qty(c.qty)} {c.symbol}</span>
        </p>
      )}
    </section>
  );
}

function Arguments({ pros, cons, risk }: { pros: string[]; cons: string[]; risk: string | null }) {
  const col = (title: string, color: string, items: string[]) => (
    <div className="flex flex-col gap-2">
      <h3 className={`m-0 text-xs font-semibold uppercase tracking-[0.06em] ${color}`}>{title}</h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] leading-normal text-[#c9ceda]">
        {items.length ? items.map((x) => <li key={x}>{x}</li>) : <li className="text-texto-2">Nenhum.</li>}
      </ul>
    </div>
  );
  return (
    <section aria-label="Argumentos da IA" className="fade-in flex flex-col gap-4 rounded-[18px] border border-borda bg-painel p-5 [animation-delay:80ms]">
      <h2 className="m-0 text-base font-semibold">O que a IA pesou</h2>
      {risk && (
        <p className="m-0 flex flex-col gap-1 rounded-xl border border-sair/25 bg-sair/8 p-3.5 text-sm leading-relaxed">
          <span className="text-xs font-semibold text-[#fda4af]">Risco principal</span>{risk}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {col("A favor de manter", "text-manter", pros)}
        {col("Contra", "text-sair", cons)}
      </div>
    </section>
  );
}
