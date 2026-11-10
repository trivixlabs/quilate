import type { Signal } from "@/lib/types";

const STATE = (s: Signal) => (s.alert === null ? "sem dado" : s.alert ? "em alerta" : "ok");

/** Os 7 sinais da régua em segmentos: cor do veredito em alerta, cinza ok, tracejado sem dado. */
export function SignalBar({ signals, alerts, tone = "bg-reduzir" }: { signals: Signal[]; alerts: number; tone?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-xs text-texto-2">
        <span>Sinais em alerta</span>
        <span>{alerts} de {signals.length}</span>
      </div>
      <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${signals.length}, minmax(0, 1fr))` }}
        role="img" aria-label={`${alerts} de ${signals.length} sinais em alerta`}>
        {signals.map((s) => (
          <span key={s.code} title={`${s.code} ${s.name}: ${STATE(s)}`}
            className={`h-[5px] rounded-full ${s.alert === null ? "border border-dashed border-[#3a4258]" : s.alert ? tone : "bg-[#1c2130]"}`} />
        ))}
      </div>
    </div>
  );
}
