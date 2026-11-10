import { useState, type FormEvent } from "react";
import { ApiError, uploadCsv } from "@/lib/api";
import { exchangeName } from "@/lib/format";
import type { Exchange } from "@/lib/types";

const EXCHANGES: Exchange[] = ["binance", "mexc", "bybit", "gate"];
const MAX_BYTES = 5 * 1024 * 1024; // o mesmo limite do backend

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Importa o CSV de operações exportado no site da corretora. Arquivo acima de 5 MB nem é enviado. */
export function CsvUpload({ onDone }: { onDone: () => void }) {
  const [exchange, setExchange] = useState<Exchange>("binance");
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<{ busy?: boolean; ok?: string; error?: string }>({});

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return setState({ error: "Escolha o arquivo CSV." });
    if (file.size > MAX_BYTES) return setState({ error: "O arquivo passa de 5 MB." });
    setState({ busy: true });
    try {
      const r = await uploadCsv(exchange, file);
      setState({ ok: `${plural(r.imported, "operação nova", "operações novas")} de ${plural(r.read, "lida", "lidas")} no arquivo.` });
      onDone();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setState({ error: status === 413 ? "O arquivo passa de 5 MB."
        : status === 422 ? `O arquivo não está no formato de CSV da ${exchangeName(exchange)}.`
        : `Não consegui enviar o arquivo (${(err as Error).message}).` });
    }
  }

  const input = "rounded-[10px] border border-[#262c3d] bg-[#11141d] px-3 py-2.5 text-sm text-texto outline-offset-2 outline-violeta focus-visible:outline-2";
  return (
    <form aria-label="Importar CSV de operações" onSubmit={submit}
      className="flex flex-col gap-3 rounded-[18px] border border-borda bg-painel p-5">
      <h2 className="m-0 text-base font-semibold">Importar CSV de operações</h2>
      <p className="m-0 text-[13px] leading-relaxed text-texto-2">
        Use quando a corretora não devolve todas as compras pela API. Exporte o histórico de operações no site da corretora.
        Operações repetidas são ignoradas.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-[13px] text-texto-2">
          Corretora
          <select value={exchange} onChange={(e) => { setExchange(e.target.value as Exchange); setState({}); }} className={input}>
            {EXCHANGES.map((x) => <option key={x} value={x}>{exchangeName(x)}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-[13px] text-texto-2">
          Arquivo CSV
          <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setState({}); }}
            className={`${input} min-w-0 file:mr-3 file:rounded-md file:border-0 file:bg-borda file:px-2.5 file:py-1 file:text-texto`} />
        </label>
        <button type="submit" disabled={state.busy}
          className="min-h-11 rounded-[10px] bg-texto px-4 text-sm font-semibold text-fundo outline-offset-2 outline-violeta hover:bg-white focus-visible:outline-2 disabled:opacity-60">
          Enviar CSV
        </button>
      </div>
      {state.ok && <p role="status" className="m-0 text-sm text-alta">{state.ok}</p>}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </form>
  );
}
