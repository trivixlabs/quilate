import { useState, type FormEvent } from "react";
import { ApiError, saveCostOverride } from "@/lib/api";

/** "1,65" e "1.234,56" com vírgula decimal; sem vírgula, o ponto é o decimal ("1.65"). */
function parseDecimal(s: string): number {
  const t = s.trim().replace(/\s/g, "");
  return Number(t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t);
}

/**
 * Preço médio informado à mão, para quando a corretora não devolve todas as compras.
 * Abre sozinho com o custo desconhecido e fica aberto depois de salvar, para mostrar a confirmação.
 * Valor que não vira número fica na tela. O 422 do backend vira mensagem em português.
 */
export function CostOverrideForm({ symbol, costUnknown, onSaved }: { symbol: string; costUnknown: boolean; onSaved: () => void }) {
  const [avg, setAvg] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<{ busy?: boolean; ok?: boolean; error?: string }>({});
  const [saved, setSaved] = useState(false); // salvou uma vez: o formulário fica aberto mesmo com o custo já conhecido

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = parseDecimal(avg);
    if (!Number.isFinite(value)) return setState({ error: "Informe o preço médio só com números, por exemplo 1,65." });
    setState({ busy: true });
    try {
      // ponytail: qty fica nula, o backend guarda mas ainda não usa no cálculo do custo.
      await saveCostOverride({ symbol, avg_cost_usd: value, qty: null, note: note.trim() || null });
      setState({ ok: true });
      setSaved(true);
      onSaved();
    } catch (err) {
      setState({ error: err instanceof ApiError && err.status === 422
        ? "O preço médio precisa ser um número maior que zero."
        : `Não consegui salvar (${(err as Error).message}).` });
    }
  }

  const input = "rounded-[10px] border border-[#262c3d] bg-[#11141d] px-3 py-2.5 text-sm text-texto outline-offset-2 outline-violeta focus-visible:outline-2";
  return (
    <details open={costUnknown || saved} aria-labelledby="ajuste-custo"
      className={`rounded-[18px] border bg-painel p-5 ${costUnknown ? "border-reduzir/35" : "border-borda"}`}>
      <summary id="ajuste-custo" className="cursor-pointer rounded text-base font-semibold outline-offset-2 outline-violeta focus-visible:outline-2">
        Ajustar preço médio
      </summary>
      <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
        {costUnknown && (
          <p className="m-0 text-sm text-[#fcd34d]">
            As corretoras não informam todas as compras desta moeda. Informe o preço médio para calcular o resultado.
          </p>
        )}
        <label className="flex flex-col gap-1.5 text-[13px] text-texto-2">
          Preço médio de compra (US$)
          <input required inputMode="decimal" autoComplete="off" placeholder="0,00" value={avg}
            onChange={(e) => { setAvg(e.target.value); setState({}); }} className={`${input} font-mono`} />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] text-texto-2">
          Observação (opcional)
          <input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} className={input} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={state.busy}
            className="min-h-11 rounded-[10px] bg-texto px-4 text-sm font-semibold text-fundo outline-offset-2 outline-violeta hover:bg-white focus-visible:outline-2 disabled:opacity-60">
            Salvar preço médio
          </button>
          {state.ok && <span role="status" className="text-sm text-alta">Preço médio salvo.</span>}
          {state.error && <span role="alert" className="text-sm text-sair">{state.error}</span>}
        </div>
      </form>
    </details>
  );
}
