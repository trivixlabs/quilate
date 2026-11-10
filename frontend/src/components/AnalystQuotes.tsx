import { mention, of, subject } from "@/lib/analyst";
import type { Quote } from "@/lib/types";

const DAY = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
export const KIND: Record<string, string> = { texto: "texto", foto: "print do gráfico", audio: "áudio transcrito", link: "texto do link" };

/** "14/10 · tópico ON-CHAIN DATA · texto". Trecho de live mostra o minuto em vez do tipo. */
export function quoteMeta(q: Omit<Quote, "id">): string {
  const kind = q.kind === "transcricao"
    ? `live no YouTube${q.t_start === null ? "" : `, minuto ${Math.floor(q.t_start / 60)}`}`
    : KIND[q.kind] ?? q.kind;
  return [DAY.format(new Date(q.date_utc)), q.topic && `tópico ${q.topic}`, kind].filter(Boolean).join(" · ");
}

/** Falas do analista sobre a moeda, da mais nova para a mais antiga. `name` é o nome de exibição, vazio para o termo genérico. */
export function AnalystQuotes({ quotes, noAnalyst, name }: { quotes: Quote[]; noAnalyst: boolean; name: string }) {
  return (
    <section aria-label={`O que ${mention(name)} disse`} className="flex flex-col gap-3.5 rounded-[18px] border border-borda bg-painel p-5">
      <h2 className="m-0 text-base font-semibold">O que {mention(name)} disse</h2>
      {quotes.map((q, i) => (
        <figure key={q.id ?? i} className="m-0 flex gap-3">
          <span aria-hidden="true" className="w-0.5 flex-none rounded-sm bg-linear-to-b from-violeta to-ciano" />
          <div className="flex flex-col gap-1">
            <blockquote className="m-0 text-sm leading-relaxed">{q.text}</blockquote>
            <figcaption className="text-xs text-texto-2">{quoteMeta(q)}</figcaption>
          </div>
        </figure>
      ))}
      {noAnalyst && (
        <p className="m-0 text-sm text-[#fcd34d]">
          {subject(name)} nunca comentou esta moeda. O veredito usa as regras gerais do manual e os dados de mercado.
        </p>
      )}
      {!noAnalyst && quotes.length === 0 && <p className="m-0 text-sm text-texto-2">Nenhuma fala recente {of(name)} sobre esta moeda.</p>}
    </section>
  );
}
