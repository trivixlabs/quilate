import { useState, type ReactNode } from "react";
import { getTrack } from "@/lib/api";
import { day, pct } from "@/lib/format";
import { useLiveQuery } from "@/lib/live";
import type { HitRate, Outcome, TrackedVerdict, Verdict } from "@/lib/types";
import { LoadState, StaleError } from "@/components/LoadState";
import { VERDICT } from "@/components/VerdictCard";

const HORIZONS = ["7", "30", "90"];
const VERDICTS: [Verdict, string, string][] = [["Sair", "bg-sair", "text-sair"], ["Reduzir", "bg-reduzir", "text-reduzir"], ["Manter", "bg-manter", "text-manter"]];
// Os mesmos nomes de backend/quilate/signals/rubric.py.
const SIGNALS: [string, string][] = [
  ["S1", "Força contra o BTC"], ["S2", "Tendência de queda"], ["S3", "Liquidez"], ["S4", "Oferta nova"],
  ["S5", "Risco de deslistagem"], ["S6", "Analista"], ["S7", "Atenção do grupo"],
];
const panel = "min-w-0 rounded-[18px] border border-borda bg-painel";
const th = "px-3 py-3 font-medium";

const rate = (h: HitRate | undefined) => (h && h.n ? `${Math.round(h.rate * 100)}% (${h.hits} de ${h.n})` : "sem amostra");

/** Aba Histórico de acertos: cartões por veredito no prazo escolhido, taxas por veredito e por sinal e a lista dos vereditos. */
export function Historico() {
  const { data, error } = useLiveQuery(getTrack);
  const [horizon, setHorizon] = useState("7");
  if (!data) return <LoadState what="o histórico de acertos" error={error} />;

  // Até o primeiro horizonte de 7 dias fechar, nenhuma combinação tem amostra.
  const hasData = [...Object.values(data.by_verdict), ...Object.values(data.by_signal)]
    .some((byH) => Object.values(byH ?? {}).some((h) => h.n > 0));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-3xl flex-col gap-1.5">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">Histórico de acertos</h1>
          <p className="m-0 text-sm leading-relaxed text-texto-2">
            Reduzir e Sair acertam quando seguir o veredito rendeu mais que segurar a moeda. Manter acerta quando a moeda rendeu
            pelo menos o mesmo que o BTC. A conta desconta 0,2% de taxa por operação. Manter do BTC fica fora das taxas: o BTC
            é a própria referência e acertaria sempre.
          </p>
        </div>
        {hasData && (
          <div role="group" aria-label="Prazo" className="flex gap-0.5 rounded-xl border border-borda bg-[#0a0c12] p-1">
            {HORIZONS.map((h) => (
              <button key={h} type="button" aria-pressed={h === horizon} onClick={() => setHorizon(h)}
                className={`min-h-9 rounded-[9px] px-3.5 text-[13px] outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                  h === horizon ? "bg-borda font-semibold text-white" : "text-texto-2 hover:text-texto"}`}>{h} dias</button>
            ))}
          </div>
        )}
      </header>
      <StaleError error={error} />

      {!hasData ? (
        <section className="fade-in flex flex-wrap items-center gap-4 rounded-2xl border border-violeta/30 bg-violeta/6 p-5">
          <span aria-hidden="true" className="inline-flex size-11 shrink-0 animate-pulse items-center justify-center rounded-xl bg-violeta/14 text-[#c4b5fd] motion-reduce:animate-none">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          </span>
          <div className="flex min-w-[240px] flex-1 flex-col gap-1">
            <h2 className="m-0 text-base font-semibold">Ainda sem dados suficientes</h2>
            <p className="m-0 text-sm text-[#c3c9d6]">O primeiro resultado aparece 7 dias depois do primeiro veredito. As taxas entram aqui sozinhas.</p>
          </div>
        </section>
      ) : (
        <>
          <section aria-label="Acerto por veredito" className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))" }}>
            {VERDICTS.map(([v], i) => <RateCard key={v} verdict={v} hr={data.by_verdict[v]?.[horizon]} horizon={horizon} index={i} />)}
          </section>
          <div className="grid items-start gap-5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(440px, 100%), 1fr))" }}>
            <RateTable title="Taxa de acerto por veredito" first="Veredito"
              rows={VERDICTS.map(([v, dot]) => ({
                key: v, byH: data.by_verdict[v],
                head: <span className="flex items-center gap-2"><span aria-hidden="true" className={`size-2 rounded-full ${dot}`} />{v}</span>,
              }))} />
            <RateTable title="Taxa de acerto por sinal" first="Sinal" note="Conta só os vereditos em que o sinal estava em alerta."
              rows={SIGNALS.map(([code, name]) => ({
                key: code, byH: data.by_signal[code],
                head: <><span className="mr-2 font-mono text-xs text-[#c4b5fd]">{code}</span>{name}</>,
              }))} />
          </div>
          <VerdictList list={data.verdicts} />
        </>
      )}
    </div>
  );
}

/** Taxa de acerto de um veredito num prazo, com o anel cheio na proporção dos acertos. */
function RateCard({ verdict, hr, horizon, index }: { verdict: Verdict; hr: HitRate | undefined; horizon: string; index: number }) {
  const v = VERDICT[verdict];
  const has = !!hr && hr.n > 0;
  const pctHit = has ? Math.round(hr.rate * 100) : 0;
  return (
    <article aria-label={verdict} className="fade-in flex flex-col items-center gap-3 rounded-[18px] border border-borda bg-painel p-5" style={{ animationDelay: `${60 * index}ms` }}>
      <span className={`inline-flex items-center gap-2 self-start text-[15px] font-semibold ${v.text}`}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={v.icon} /></svg>
        {verdict}
      </span>
      <svg width="104" height="104" viewBox="0 0 36 36" aria-hidden="true" className="-rotate-90">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1c2130" strokeWidth="3" strokeDasharray={has ? undefined : "2 2.2"} />
        {has && <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" pathLength={100}
          strokeDasharray={`${pctHit} 100`} className={`${v.text} transition-[stroke-dasharray] duration-700`} />}
      </svg>
      <span className={`font-mono text-[26px] font-semibold ${has ? "" : "text-texto-2"}`}>{has ? `${pctHit}%` : "—"}</span>
      <span className="text-[13px] text-texto-2">{has ? `${hr.hits} de ${hr.n} em ${horizon} dias` : `sem amostra em ${horizon} dias`}</span>
    </article>
  );
}

function RateTable({ title, first, note, rows }: {
  title: string; first: string; note?: string;
  rows: { key: string; head: ReactNode; byH: Record<string, HitRate> | undefined }[];
}) {
  return (
    <section aria-label={title} className={panel}>
      <div className="flex flex-col gap-1 border-b border-borda px-5 py-4">
        <h2 className="m-0 text-base font-semibold">{title}</h2>
        {note && <span className="text-[13px] text-texto-2">{note}</span>}
      </div>
      <div className="overflow-x-auto">
        <table aria-label={title} className="w-full min-w-[440px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-[0.04em] text-texto-2">
              <th scope="col" className={`${th} pl-5`}>{first}</th>
              {HORIZONS.map((h) => <th key={h} scope="col" className={`${th} text-right last:pr-5`}>{h} dias</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-[#161a26]">
                <th scope="row" className="whitespace-nowrap px-3 py-3 pl-5 text-left font-normal">{r.head}</th>
                {HORIZONS.map((h) => {
                  const text = rate(r.byH?.[h]);
                  return <td key={h} className={`whitespace-nowrap px-3 py-3 text-right font-mono text-[13px] last:pr-5 ${text === "sem amostra" ? "text-texto-2" : ""}`}>{text}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Result({ o }: { o: Outcome | undefined }) {
  if (!o) return <span className="text-texto-2">aguardando</span>;
  return (
    <span className="flex flex-col items-end gap-0.5">
      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${o.hit ? "bg-manter/12 text-[#5eead4]" : "bg-sair/12 text-[#fda4af]"}`}>{o.hit ? "Acertou" : "Errou"}</span>
      <span className="text-[11px] text-texto-2">
        moeda {pct(o.r_hold * 100)} · BTC {pct(o.r_btc * 100)} · seguindo o veredito {pct(o.r_paper * 100)}
      </span>
    </span>
  );
}

function VerdictList({ list }: { list: TrackedVerdict[] }) {
  const color = Object.fromEntries(VERDICTS.map(([v, , text]) => [v, text]));
  return (
    <section aria-labelledby="lista" className={panel}>
      <div className="flex flex-col gap-1 border-b border-borda px-5 py-4">
        <h2 id="lista" className="m-0 text-base font-semibold">Vereditos com resultado</h2>
        <span className="text-[13px] text-texto-2">Os mais recentes primeiro. Retorno de segurar a moeda, do BTC e de seguir o veredito.</span>
      </div>
      <div className="overflow-x-auto">
        <table aria-label="Vereditos com resultado" className="w-full min-w-[920px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-[0.04em] text-texto-2">
              <th scope="col" className={`${th} pl-5`}>Dia</th>
              <th scope="col" className={th}>Moeda</th>
              <th scope="col" className={th}>Veredito</th>
              {HORIZONS.map((h) => <th key={h} scope="col" className={`${th} text-right last:pr-5`}>{h} dias</th>)}
            </tr>
          </thead>
          <tbody>
            {list.map((v) => (
              <tr key={v.id} className="border-t border-[#161a26] align-top">
                <td className="px-3 py-3 pl-5 font-mono text-[13px] text-texto-2">{day(v.day)}</td>
                <th scope="row" className="px-3 py-3 text-left font-semibold">{v.symbol}</th>
                <td className={`px-3 py-3 ${color[v.verdict] ?? ""}`}>{v.verdict}</td>
                {HORIZONS.map((h) => <td key={h} className="px-3 py-3 text-right font-mono text-[13px] last:pr-5"><Result o={v.outcomes[h]} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
