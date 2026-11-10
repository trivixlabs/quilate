import { useState } from "react";
import { Link } from "react-router";
import { getPortfolio, getVerdicts } from "@/lib/api";
import { exchangeName, qty, signedUsd, usd } from "@/lib/format";
import { useLive, useLiveQuery } from "@/lib/live";
import type { Exchange, Portfolio, Verdict } from "@/lib/types";
import { CsvUpload } from "@/components/CsvUpload";
import { LoadState, StaleError } from "@/components/LoadState";
import { hue, VERDICT } from "@/components/VerdictCard";

type Coin = Portfolio["coins"][number];

const DUST_USD = 10; // dust_usd do backend/quilate/config.toml
const SHARE = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });
const COLUMNS = ["Moeda", "Corretora", "Carteira", "Quantidade", "Preço", "Posição", "Preço médio", "Resultado"];
const EXCHANGES: Exchange[] = ["binance", "bybit", "gate", "mexc"];
const EX_COLORS: Record<Exchange, string> = { binance: "#a78bfa", bybit: "#22d3ee", gate: "#f0abfc", mexc: "#fdba74" };
const FILTERS: (Verdict | "Todas")[] = ["Todas", "Sair", "Reduzir", "Manter"];
/** Cores da alocação pela posição: vizinhas sempre diferentes, ao contrário da cor por símbolo. */
const ALLOC = ["#a78bfa", "#22d3ee", "#f0abfc", "#fdba74", "#86efac", "#93c5fd", "#fda4af", "#fde68a", "#c4b5fd", "#67e8f9"];
const card = "min-w-0 rounded-[18px] border border-borda bg-painel";

/** Moeda com o preço do último tick: posição e resultado seguem o preço. */
function withPrice(c: Coin, price: number | undefined): Coin {
  if (price === undefined) return c;
  return { ...c, price_usd: price, value_usd: c.qty * price,
    pnl_usd: c.avg_cost_usd === null ? null : c.qty * (price - c.avg_cost_usd) };
}

/** Aba Carteira: alocação, corretoras, posições com filtro por veredito, poeira e importação de CSV. */
export function Carteira() {
  const { prices } = useLive();
  const [imports, setImports] = useState(0);
  const [filter, setFilter] = useState<Verdict | "Todas">("Todas");
  const { data, error } = useLiveQuery(getPortfolio, imports);
  const { data: verdicts } = useLiveQuery(getVerdicts);  // só para cor e filtro: sem ela a tabela funciona igual
  if (!data) return <LoadState what="a carteira" error={error} />;

  const verdictOf: Record<string, Verdict> = {};
  if (verdicts) for (const v of ["Sair", "Reduzir", "Manter"] as Verdict[]) for (const c of verdicts.groups[v]) verdictOf[c.symbol] = v;

  const coins = data.coins.map((c) => withPrice(c, prices[c.symbol]?.price));
  const isDust = (c: Coin) => c.value_usd !== null && c.value_usd < DUST_USD;
  const main = coins.filter((c) => !isDust(c)).sort((a, b) => (b.value_usd ?? 0) - (a.value_usd ?? 0));
  const dust = coins.filter(isDust);
  const total = coins.reduce((a, c) => a + (c.value_usd ?? 0), 0);
  const shown = filter === "Todas" ? main : main.filter((c) => verdictOf[c.symbol] === filter);

  return (
    <div className="flex flex-col gap-6">
      <StaleError error={error} />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-2xl flex-col gap-1.5">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">Carteira</h1>
          <p className="m-0 text-sm leading-relaxed text-texto-2">Saldos lidos das 4 corretoras, com preço médio e resultado por moeda. Clique numa moeda para ver o veredito completo.</p>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-[28px] font-semibold">{usd(total)}</span>
          <span className="text-[13px] text-texto-2">{main.length} {main.length === 1 ? "moeda" : "moedas"}{dust.length > 0 && ` · ${dust.length} em poeira`}</span>
        </div>
      </header>

      <section aria-labelledby="alocacao" className={`${card} fade-in flex flex-col gap-4 p-5`}>
        <div className="flex flex-col gap-1">
          <h2 id="alocacao" className="m-0 text-base font-semibold">Alocação por moeda</h2>
          <span className="text-[13px] text-texto-2">Quanto cada moeda pesa no patrimônio. O anel em volta do quadrado mostra o veredito de hoje.</span>
        </div>
        <div aria-hidden="true" className="flex h-4 gap-[3px] overflow-hidden rounded-full">
          {main.map((c, i) => <span key={c.symbol} className="transition-[flex-grow] duration-700" style={{ flex: c.value_usd ?? 0, background: ALLOC[i % ALLOC.length] }} />)}
        </div>
        <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-2 p-0">
          {main.map((c, i) => {
            const v = verdictOf[c.symbol];
            return (
              <li key={c.symbol} className="inline-flex items-center gap-2 text-[13px]">
                <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: ALLOC[i % ALLOC.length], boxShadow: v ? `0 0 0 2px var(--color-${v === "Sair" ? "sair" : v === "Reduzir" ? "reduzir" : "manter"})` : undefined }} />
                <span data-symbol>{c.symbol}</span>
                <span className="font-mono text-texto-2">{c.share !== null ? SHARE.format(c.share) : "—"}</span>
                {v && <span className="sr-only">, {v}</span>}
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label="Corretoras" className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-3.5">
        {EXCHANGES.map((ex, i) => {
          const pos = coins.flatMap((c) => c.positions.filter((p) => p.exchange === ex).map((p) => ({ ...p, value: c.price_usd === null ? 0 : p.qty * c.price_usd })));
          const value = pos.reduce((a, p) => a + p.value, 0);
          const verified = pos.length > 0 && pos.every((p) => p.permissions_verified);
          const stale = pos.some((p) => p.stale);
          return (
            <article key={ex} className={`${card} fade-in flex flex-col gap-2.5 p-4`} style={{ animationDelay: `${60 * i}ms` }}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="m-0 text-[15px] font-semibold">{exchangeName(ex)}</h3>
                <span className="font-mono text-[13px] text-texto-2">{total ? SHARE.format(value / total) : "—"}</span>
              </div>
              <span className="font-mono text-xl font-semibold">{pos.length ? usd(value) : <span className="text-base font-normal text-texto-2">sem posição</span>}</span>
              <span aria-hidden="true" className="block h-1 overflow-hidden rounded-full bg-borda">
                <span className="block h-full rounded-full transition-[width] duration-700" style={{ width: `${total ? (value / total) * 100 : 0}%`, background: EX_COLORS[ex] }} />
              </span>
              {pos.length > 0 && (
                <span className={`text-xs ${verified ? "text-[#5eead4]" : "text-[#fcd34d]"}`}>
                  {verified ? "Somente leitura checada pela API" : "permissões não verificadas"}
                </span>
              )}
              {stale && <span className="text-xs text-[#fcd34d]">saldo desatualizado</span>}
            </article>
          );
        })}
      </section>

      <section aria-labelledby="posicoes" className={card}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-borda px-5 py-[18px]">
          <div className="flex flex-col gap-1">
            <h2 id="posicoes" className="m-0 text-base font-semibold">Posições por corretora</h2>
            <span className="text-[13px] text-texto-2">Uma linha por corretora e carteira. Moedas abaixo de {usd(DUST_USD)} ficam na poeira.</span>
          </div>
          {verdicts && (
            <div role="group" aria-label="Filtrar por veredito" className="flex flex-wrap gap-1.5">
              {FILTERS.map((f) => {
                const n = f === "Todas" ? main.length : main.filter((c) => verdictOf[c.symbol] === f).length;
                return (
                  <button key={f} type="button" aria-pressed={f === filter} onClick={() => setFilter(f)}
                    className={`min-h-9 rounded-[10px] border px-3 text-[13px] outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                      f === filter ? "border-violeta bg-[#151226] font-semibold text-white" : "border-borda text-[#c3c9d6] hover:bg-[#121621]"}`}>
                    {f} <span className="font-mono text-texto-2">{n}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        {shown.length
          ? <PositionsTable label="Posições por corretora" coins={shown} verdictOf={verdictOf} />
          : <p className="m-0 px-5 py-6 text-sm text-texto-2">Nenhuma moeda com este veredito.</p>}
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <CsvUpload onDone={() => setImports((n) => n + 1)} />
        <section aria-labelledby="poeira" className={`${card} flex flex-col`}>
          <div className="flex flex-col gap-1 border-b border-borda px-5 py-[18px]">
            <h2 id="poeira" className="m-0 text-base font-semibold">Poeira (fora do veredito)</h2>
            <span className="text-[13px] text-texto-2">Moedas abaixo de {usd(DUST_USD)} ficam fora do veredito. O limite muda em Configuração, Preferências.</span>
          </div>
          {dust.length
            ? <PositionsTable label="Poeira" coins={dust} verdictOf={verdictOf} />
            : <p className="m-0 px-5 py-4 text-sm text-texto-2">Nenhuma moeda abaixo de {usd(DUST_USD)}.</p>}
        </section>
      </div>
    </div>
  );
}

function PositionsTable({ label, coins, verdictOf }: { label: string; coins: Coin[]; verdictOf: Record<string, Verdict> }) {
  const td = "px-3 py-3.5 text-right font-mono";
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full min-w-[920px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-[0.04em] text-texto-2">
            {COLUMNS.map((h, i) => (
              <th key={h} scope="col" className={`py-3 font-medium ${i === 0 ? "px-5" : "px-3"} ${i >= 3 ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        {coins.map((c) => {
          const unknown = c.cost_unknown || c.avg_cost_usd === null;
          const span = Math.max(c.positions.length, 1);
          const rows = c.positions.length ? c.positions : [null];
          const v = verdictOf[c.symbol];
          return (
            <tbody key={c.symbol} className="border-t border-[#161a26]">
              {rows.map((p, i) => {
                const value = p && c.price_usd !== null ? p.qty * c.price_usd : null;
                const pnl = p && !unknown && c.price_usd !== null ? p.qty * (c.price_usd - c.avg_cost_usd!) : null;
                return (
                  <tr key={p ? `${p.exchange}/${p.wallet}` : "sem-posicao"} className="align-top transition-colors hover:bg-[#11141d]">
                    {i === 0 && (
                      <th scope="rowgroup" rowSpan={span} className="px-5 py-3 text-left font-normal">
                        <Link to={`/moeda/${c.symbol}`} className="group flex items-start gap-3 text-texto no-underline outline-offset-2 outline-violeta focus-visible:outline-2">
                          <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white transition-transform group-hover:scale-105"
                            style={{ background: hue(c.symbol) }}>{c.symbol[0]}</span>
                          <span className="flex flex-col gap-1">
                            <span className="whitespace-nowrap font-semibold"><span data-name>{c.name}</span> <span className="font-normal text-texto-2">{c.symbol}</span></span>
                            <span className="flex flex-wrap items-center gap-1.5">
                              {v && (
                                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${VERDICT[v].tint} ${VERDICT[v].text}`}>
                                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={VERDICT[v].icon} /></svg>{v}
                                </span>
                              )}
                              {c.share !== null && c.share >= 0.001 && <span className="whitespace-nowrap text-xs text-texto-2">{SHARE.format(c.share)} da carteira</span>}
                            </span>
                          </span>
                        </Link>
                      </th>
                    )}
                    <td className="px-3 py-3.5">
                      {p ? exchangeName(p.exchange) : <span className="text-texto-2">sem posição</span>}
                      {p?.stale && <span className="text-xs text-[#fcd34d]"> · desatualizada</span>}
                      {p && !p.permissions_verified && <span className="text-xs text-texto-2"> · permissões não verificadas</span>}
                    </td>
                    <td className="px-3 py-3.5 text-texto-2">{p?.wallet ?? ""}</td>
                    <td className={td}>{p ? qty(p.qty) : ""}</td>
                    {i === 0 && (
                      <td rowSpan={span} className={td}>
                        {c.price_usd !== null ? usd(c.price_usd) : <span className="text-texto-2">sem preço</span>}
                      </td>
                    )}
                    <td className={td}>{value !== null ? usd(value) : <span className="text-texto-2">sem preço</span>}</td>
                    {i === 0 && (
                      <td rowSpan={span} className={`${td} text-texto-2`}>
                        {c.avg_cost_usd !== null ? usd(c.avg_cost_usd) : <span className="text-texto-2">desconhecido</span>}
                      </td>
                    )}
                    <td className={td}>
                      {unknown
                        ? <span className="text-texto-2">custo desconhecido</span>
                        : pnl !== null && <span className={pnl >= 0 ? "text-[#6ee7b7]" : "text-[#fda4af]"}>{signedUsd(pnl)}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
