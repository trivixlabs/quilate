import { Link } from "react-router";
import { motion } from "motion/react";
import { exchangeName, pct, signedUsd, usd } from "@/lib/format";
import { of } from "@/lib/analyst";
import type { Card, Verdict } from "@/lib/types";
import { SignalBar } from "./SignalBar";

export const FLAGS: Record<string, string> = { ai_paused: "IA pausada por limite de gasto", ai_failed: "IA falhou nesta moeda" };

/** Cor e ícone de cada veredito. O ícone e a palavra vão sempre junto da cor. */
export const VERDICT: Record<Verdict, { text: string; bg: string; tint: string; icon: string; hint: string }> = {
  Sair: { text: "text-sair", bg: "bg-sair", tint: "bg-sair/12", icon: "M6 6l12 12M18 6 6 18", hint: "5 ou mais sinais" },
  Reduzir: { text: "text-reduzir", bg: "bg-reduzir", tint: "bg-reduzir/12", icon: "M7 7l10 10M17 9v8H9", hint: "3 a 4 sinais" },
  Manter: { text: "text-manter", bg: "bg-manter", tint: "bg-manter/12", icon: "M5 12.5l4.5 4.5L19 7.5", hint: "0 a 2 sinais" },
};

/** Tom das moedas que todo mundo reconhece pela cor. As outras saem do símbolo. */
const KNOWN: Record<string, number> = { BTC: 30, ETH: 228, SOL: 272, BNB: 45, XRP: 200, USDT: 160, USDC: 212 };

/** Cor estável por símbolo para o monograma (o hash do JS muda a cada carga; este não). */
export function hue(symbol: string): string {
  if (symbol in KNOWN) return `hsl(${KNOWN[symbol]} 60% 45%)`;
  const h = [...symbol].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  return `hsl(${(Math.imul(h, 2654435761) >>> 0) % 360} 55% 45%)`;
}

/**
 * Cartão de veredito. O cartão inteiro é o link para o foco da moeda.
 * `flash` é a direção do último tick (1 alta, −1 queda) enquanto a piscada dura, e 0 fora dela.
 * `flashKey` muda a cada tick para reiniciar a animação. `index` escalona a entrada. `analyst` é o nome de exibição do analista.
 */
export function VerdictCard({ card: c, flash = 0, flashKey = 0, index = 0, analyst = "" }: {
  card: Card; flash?: 1 | -1 | 0; flashKey?: number; index?: number; analyst?: string;
}) {
  const diverges = c.ai_verdict !== null && c.ai_verdict !== c.rubric_verdict;
  const up = c.change_24h !== null && c.change_24h >= 0;
  return (
    <motion.div layout="position" layoutId={c.symbol} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: Math.min(index, 10) * 0.06, ease: [0.2, 0.7, 0.2, 1] }}>
      <Link to={`/moeda/${c.symbol}`} aria-label={`${c.symbol}, veredito ${c.verdict}`}
        className="group block rounded-[18px] outline-offset-2 outline-violeta focus-visible:outline-2">
        <div className={`rounded-[18px] p-px ${c.verdict === "Sair" ? "glow-sair bg-[#2a1720]" : "bg-borda"}`}>
          <article className="flex flex-col gap-3.5 rounded-[17px] bg-painel p-4 transition duration-200 group-hover:-translate-y-0.5 group-hover:bg-[#10131c] motion-reduce:group-hover:translate-y-0">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="flex size-[38px] shrink-0 items-center justify-center rounded-full text-[15px] font-bold text-white"
                style={{ background: hue(c.symbol) }}>{c.symbol[0]}</span>
              <div className="flex min-w-0 grow flex-col gap-0.5">
                <span className="truncate text-[15px] font-semibold">{c.symbol} <span className="font-normal text-texto-2 text-[13px]">{c.name}</span></span>
                <span className="truncate text-xs text-texto-2">{c.exchanges.map(exchangeName).join(" · ")}</span>
              </div>
            </div>

            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span key={flashKey} className={`rounded-md font-mono text-lg font-semibold ${flash > 0 ? "flash-up" : flash < 0 ? "flash-down" : ""}`}>
                {usd(c.price_usd)}
              </span>
              {c.change_24h !== null && (
                <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-xs font-semibold ${up ? "bg-alta/12 text-[#6ee7b7]" : "bg-sair/12 text-[#fda4af]"}`}>
                  <span aria-hidden="true">{up ? "▲" : "▼"}</span>{pct(c.change_24h * 100)}<span className="sr-only"> em 24 h</span>
                </span>
              )}
            </div>

            <div className="flex justify-between gap-2 text-[13px]">
              <span className="text-texto-2">Posição <b className="font-mono font-medium text-texto">{usd(c.value_usd)}</b></span>
              {c.cost_unknown || c.pnl_usd === null
                ? <span className="text-texto-2">custo desconhecido</span>
                : <span className={`font-mono ${c.pnl_usd >= 0 ? "text-[#6ee7b7]" : "text-[#fda4af]"}`}>{signedUsd(c.pnl_usd)}</span>}
            </div>

            <SignalBar signals={c.signals} alerts={c.alerts} tone={VERDICT[c.verdict].bg} />

            {c.reason && <p className="m-0 text-[13px] leading-relaxed text-[#c3c9d6]">{c.reason}</p>}

            {(c.no_analyst || c.flag || diverges) && (
              <ul className="m-0 flex list-none flex-col gap-1 rounded-lg bg-reduzir/8 p-2.5 text-xs text-[#fcd34d]">
                {diverges && <li>régua: {c.rubric_verdict}, IA: {c.ai_verdict}</li>}
                {c.no_analyst && <li>Sem análise direta {of(analyst)} · confiança menor</li>}
                {c.flag && <li>{FLAGS[c.flag] ?? c.flag}</li>}
              </ul>
            )}

            <div className="flex items-center justify-between gap-2 border-t border-[#161a26] pt-2.5 text-xs">
              <span className="text-texto-2">
                {c.confidence !== null ? `Confiança ${Math.round(c.confidence * 100)}%` : "Só a régua"}
              </span>
              <span className="text-[13px] text-[#c4b5fd] transition-colors group-hover:text-[#ede9fe]">Ver motivo completo →</span>
            </div>
          </article>
        </div>
      </Link>
    </motion.div>
  );
}
