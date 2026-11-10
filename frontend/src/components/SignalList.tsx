import type { Signal } from "@/lib/types";

/** Os 7 sinais com o valor medido. Em alerta com borda rosa, ok neutro, tracejado quando não há dado. */
export function SignalList({ signals }: { signals: Signal[] }) {
  const alerts = signals.filter((s) => s.alert).length;
  return (
    <section aria-labelledby="sinais" className="fade-in flex flex-col gap-3.5 rounded-[18px] border border-borda bg-painel p-5 [animation-delay:120ms]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 id="sinais" className="m-0 text-base font-semibold">Régua de 7 sinais</h2>
          <span className="text-[13px] text-texto-2">0 a 2 em alerta: Manter. 3 a 4: Reduzir. 5 ou mais: Sair.</span>
        </div>
        <span className={`font-mono text-xl font-semibold ${alerts >= 5 ? "text-[#fda4af]" : alerts >= 3 ? "text-[#fcd34d]" : "text-[#5eead4]"}`}>
          {alerts} de {signals.length}
        </span>
      </div>
      <ul aria-label="Os 7 sinais" className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-2 p-0">
        {signals.map((s) => (
          <li key={s.code} className={`flex items-center gap-3 rounded-xl border px-3.5 py-2.5 ${
            s.alert === null ? "border-dashed border-[#2b3247] bg-[#0a0c12]" : s.alert ? "border-sair/25 bg-sair/5" : "border-[#161a26] bg-[#0a0c12]"}`}>
            <span aria-hidden="true" className="w-6 font-mono text-xs text-[#8a93a6]">{s.code}</span>
            <span className="flex min-w-0 grow flex-col gap-0.5">
              <span className="text-sm font-medium">{s.name}</span>
              <span className="font-mono text-xs text-texto-2">{s.alert === null ? "sem dado" : String(s.value)}</span>
            </span>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              s.alert === null ? "bg-[#131722] text-texto-2" : s.alert ? "bg-sair/14 text-[#fda4af]" : "bg-manter/12 text-[#5eead4]"}`}>
              {s.alert === null ? "sem dado" : s.alert ? "alerta" : "ok"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
