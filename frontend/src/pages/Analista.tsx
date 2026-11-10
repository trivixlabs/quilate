import { useState, type ReactNode } from "react";
import { of } from "@/lib/analyst";
import { approveRule, getOverview, getPlaybook } from "@/lib/api";
import { useLiveQuery } from "@/lib/live";
import type { LiveJob, Playbook, Rule, Source } from "@/lib/types";
import { KIND, quoteMeta } from "@/components/AnalystQuotes";
import { LoadState, StaleError } from "@/components/LoadState";

const CATEGORY: Record<string, string> = {
  entrada: "Entrada", saida: "Saída", stop: "Stop", realizacao: "Realização", ciclo: "Ciclo", setores: "Setores", moedas: "Moedas",
};
const LIVE_STATUS: Record<string, string> = { pendente: "pendente", baixado: "baixada, falta transcrever", transcrito: "transcrita", erro: "erro" };
const DAY_TIME = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const DAY = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
const panel = "flex min-w-0 flex-col gap-3.5 rounded-[18px] border border-borda bg-painel p-5";

/** Aba Analista: regras com fontes e o botão Aprovar, o manual em Markdown, análises do tópico do gatilho e fila de lives. */
export function Analista() {
  const { data: pb, error, setData } = useLiveQuery(getPlaybook);
  const { data: ov } = useLiveQuery(getOverview);  // só o nome de exibição: sem ele, o termo genérico
  const owner = of(ov?.analyst_name);
  if (!pb) return <LoadState what={`o manual ${owner}`} error={error} />;

  const approved = pb.rules.filter((r) => r.approved).length;
  const onApproved = (id: number, playbookApproved: boolean) => setData((p) => p && {
    ...p, approved: playbookApproved, rules: p.rules.map((r) => (r.id === id ? { ...r, approved: true } : r)),
  });
  // pendentes primeiro, na ordem do manual: é o que pede ação
  const rules = [...pb.rules].sort((a, b) => Number(a.approved) - Number(b.approved));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-3xl flex-col gap-1.5">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">Manual {owner}</h1>
          <p className="m-0 text-sm leading-relaxed text-texto-2">
            As regras da estratégia, tiradas das mensagens e lives do grupo. A IA só usa no veredito as regras que você aprovou.
            Cada regra mostra de onde veio.
          </p>
        </div>
        {pb.version_id !== null && (
          <span className={`rounded-full px-3 py-1.5 text-[13px] ${pb.approved ? "bg-manter/10 text-manter" : "bg-reduzir/10 text-[#fcd34d]"}`}>
            {pb.approved ? "Manual aprovado" : `Manual ${owner} ainda não revisado`}
          </span>
        )}
      </header>
      <StaleError error={error} />

      <div className="flex flex-wrap items-start gap-5">
        {pb.version_id === null
          ? <p className="m-0 min-w-0 flex-[3_1_520px] rounded-[18px] border border-borda bg-painel p-5 text-texto-2">O manual {owner} ainda não foi gerado.</p>
          : (
            <section aria-labelledby="regras" className="flex min-w-0 flex-[3_1_520px] flex-col gap-4">
              <div className="fade-in flex flex-col gap-3 rounded-[18px] border border-borda bg-painel p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 id="regras" className="m-0 text-lg font-semibold">Regras</h2>
                  <span className="text-[13px] text-texto-2">{approved} de {pb.rules.length} regras aprovadas</span>
                </div>
                <span role="meter" aria-label="Regras aprovadas" aria-valuemin={0} aria-valuemax={pb.rules.length} aria-valuenow={approved}
                  className="block h-1.5 overflow-hidden rounded-full bg-borda">
                  <span className="block h-full rounded-full bg-manter transition-[width] duration-700"
                    style={{ width: `${pb.rules.length ? (approved / pb.rules.length) * 100 : 0}%` }} />
                </span>
                <span className="text-[13px] text-texto-2">Leia a fonte antes de aprovar. Regra pendente não entra no veredito.</span>
              </div>
              <ul aria-label="Regras do manual" className="m-0 flex list-none flex-col gap-3 p-0">
                {rules.map((r, i) => <RuleItem key={r.id} rule={r} sources={pb.sources} onApproved={onApproved} index={i} />)}
              </ul>
            </section>
          )}

        <div className="flex min-w-0 flex-[2_1_340px] flex-col gap-5">
          {pb.version_id !== null && (
            <section aria-label={`Manual das estratégias ${owner}`} className={`${panel} fade-in leading-relaxed [animation-delay:80ms]`}>
              <Markdown text={pb.markdown} />
            </section>
          )}
          <Timeline items={pb.timeline} topic={pb.trigger_topic_name} owner={owner} />
          <Lives lives={pb.lives} count={pb.lives_count} />
        </div>
      </div>
    </div>
  );
}

function RuleItem({ rule: r, sources, onApproved, index }: {
  rule: Rule; sources: Playbook["sources"]; onApproved: (id: number, playbookApproved: boolean) => void; index: number;
}) {
  const [state, setState] = useState<{ busy?: boolean; error?: string }>({});
  async function approve() {
    setState({ busy: true });
    try {
      const res = await approveRule(r.id);
      onApproved(r.id, res.playbook_approved);
    } catch (e) {
      setState({ error: `Não consegui aprovar a regra (${(e as Error).message}).` });
    }
  }
  return (
    <li className={`fade-in flex flex-col gap-3 rounded-2xl border p-5 transition-colors ${r.approved ? "border-borda bg-painel" : "border-reduzir/30 bg-[#0f0e0b]"}`}
      style={{ animationDelay: `${60 * index}ms` }}>
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-full bg-[#131722] px-2.5 py-1 text-xs text-[#c3c9d6]">{CATEGORY[r.category] ?? r.category}</span>
        {r.approved
          ? <span className="inline-flex items-center gap-1.5 rounded-lg bg-manter/12 px-2.5 py-1 text-xs font-semibold text-[#5eead4]">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
              Aprovada
            </span>
          : (
            <button type="button" onClick={approve} disabled={state.busy}
              className="min-h-10 rounded-xl bg-texto px-4 text-[13px] font-semibold text-fundo outline-offset-2 outline-violeta transition-colors hover:bg-white focus-visible:outline-2 disabled:opacity-60">
              Aprovar
            </button>
          )}
      </div>
      <p className="m-0 text-[15px] leading-relaxed">{r.text}</p>
      {r.source_ids.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-texto-2">Fontes</span>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {r.source_ids.map((id) => <SourceItem key={id} source={sources[id]} />)}
          </ul>
        </div>
      )}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </li>
  );
}

const linkLabel = (s: Source) =>
  s.kind === "link" ? "Abrir o link" : s.t_start === null ? "Abrir a live" : `Abrir a live no minuto ${Math.floor(s.t_start / 60)}`;

/** Fonte da regra: o botão abre o trecho citado e, quando há, o link da live ou da página. */
function SourceItem({ source }: { source: Source | undefined }) {
  const [open, setOpen] = useState(false);
  if (!source) return <li className="text-xs text-texto-2">fonte não encontrada no banco</li>;
  return (
    <li className="flex flex-col gap-1.5">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="self-start rounded text-left text-xs text-[#c4b5fd] underline-offset-2 outline-offset-2 outline-violeta hover:text-[#ede9fe] hover:underline focus-visible:outline-2">
        {quoteMeta(source)}
      </button>
      {open && (
        <div className="flex gap-3 pb-1">
          <span aria-hidden="true" className="w-0.5 flex-none rounded-sm bg-linear-to-b from-violeta to-ciano" />
          <div className="flex min-w-0 flex-col gap-1.5">
            <blockquote className="m-0 whitespace-pre-line text-[13px] leading-relaxed text-[#c9ceda]">{source.text}</blockquote>
            {source.url && (
              <a href={source.url} target="_blank" rel="noreferrer"
                className="self-start text-xs text-ciano outline-offset-2 outline-violeta focus-visible:outline-2">
                {linkLabel(source)}
              </a>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function Timeline({ items, topic, owner }: { items: Playbook["timeline"]; topic: string | null; owner: string }) {
  return (
    <section aria-labelledby="linha-do-tempo" className={`${panel} fade-in [animation-delay:140ms]`}>
      <div className="flex flex-col gap-1">
        <h2 id="linha-do-tempo" className="m-0 text-base font-semibold">Análises no tópico {topic ?? "do gatilho"}</h2>
        <span className="text-[13px] text-texto-2">A primeira do dia dispara o ciclo do veredito.</span>
      </div>
      {/* nome nulo: sem trigger_topic, ou o tópico existe e só falta o nome em group_topics */}
      {items.length === 0 && (topic === null
        ? <p className="m-0 text-sm text-texto-2">Nenhuma análise para mostrar. Confira trigger_topic e o nome do tópico em [group_topics] no config.local.toml.</p>
        : <p className="m-0 text-sm text-texto-2">Nenhuma análise {owner} neste tópico ainda.</p>)}
      <ol className="m-0 flex list-none flex-col p-0">
        {items.map((t, i) => (
          <li key={t.id} className="flex gap-3.5">
            <span aria-hidden="true" className="flex flex-col items-center">
              <span className={`mt-1.5 size-2.5 flex-none rounded-full ${i === 0 ? "bg-violeta shadow-[0_0_0_4px_rgb(167_139_250/0.18)]" : "bg-[#2b3247]"}`} />
              {i < items.length - 1 && <span className="w-0.5 grow bg-borda" />}
            </span>
            <div className="flex min-w-0 flex-col gap-1 pb-4">
              <span className="text-xs text-texto-2">{DAY_TIME.format(new Date(t.date_utc))} · {KIND[t.kind] ?? t.kind}</span>
              <p className="m-0 line-clamp-4 whitespace-pre-line text-sm leading-relaxed">{t.text || "Sem texto."}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Lives({ lives, count }: { lives: LiveJob[]; count: Record<string, number> }) {
  const n = (s: string) => count[s] ?? 0;
  const counts: [string, number, string][] = [
    ["Pendente", n("pendente") + n("baixado"), "text-[#fcd34d]"], ["Transcrito", n("transcrito"), "text-manter"], ["Erro", n("erro"), "text-sair"],
  ];
  return (
    <section aria-labelledby="lives" className={`${panel} fade-in [animation-delay:200ms]`}>
      <div className="flex flex-col gap-1">
        <h2 id="lives" className="m-0 text-base font-semibold">Fila de lives</h2>
        <span className="text-[13px] text-texto-2">Cada live do analista é baixada e transcrita neste Mac.</span>
      </div>
      <ul aria-label="Lives por status" className="m-0 grid list-none grid-cols-3 gap-2.5 p-0">
        {counts.map(([label, value, color]) => (
          <li key={label} className="flex flex-col gap-0.5 rounded-[10px] bg-[#11141d] p-2.5">
            <span className="text-[11px] text-texto-2">{label}</span>
            <span className={`font-mono text-lg ${value ? color : ""}`}>{value}</span>
          </li>
        ))}
      </ul>
      {lives.length === 0 && <p className="m-0 text-sm text-texto-2">Nenhuma live na fila.</p>}
      <ul className="m-0 flex list-none flex-col p-0">
        {lives.map((l) => (
          <li key={l.url} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-[#161a26] py-2.5 text-sm">
            <a href={l.url} target="_blank" rel="noreferrer"
              className="min-w-0 break-all text-[13px] text-[#c4b5fd] outline-offset-2 outline-violeta focus-visible:outline-2">{l.url}</a>
            <span className="text-xs text-texto-2">
              {l.date_utc && `${DAY.format(new Date(l.date_utc))} · `}
              <span className={l.status === "erro" ? "text-sair" : l.status === "transcrito" ? "text-manter" : "text-[#fcd34d]"}>
                {LIVE_STATUS[l.status] ?? l.status}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Negrito com **texto**. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part);
}

/**
 * Markdown do manual em elementos React (sem HTML cru): títulos #, ## e ###, listas com - * ou 1., parágrafos e negrito.
 * ponytail: só o que o manual usa; trocar por uma biblioteca se o Claude passar a mandar tabela ou link.
 */
function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let para: string[] = [], list: string[] = [];
  const flush = () => {
    if (para.length) blocks.push(<p key={blocks.length} className="m-0 text-sm text-[#c9ceda]">{inline(para.join(" "))}</p>);
    if (list.length) {
      blocks.push(
        <ul key={blocks.length} className="m-0 flex list-disc flex-col gap-1 pl-5 text-sm text-[#c9ceda]">
          {list.map((x, i) => <li key={i}>{inline(x)}</li>)}
        </ul>);
    }
    para = [];
    list = [];
  };
  for (const line of text.split("\n")) {
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    const li = /^\s*(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
    if (h) {
      flush();
      const Tag = (["h2", "h3", "h4"] as const)[h[1].length - 1];
      const size = ["text-lg", "text-base", "text-sm"][h[1].length - 1];
      blocks.push(<Tag key={blocks.length} className={`m-0 mt-1 font-semibold ${size}`}>{inline(h[2])}</Tag>);
    } else if (li) {
      if (para.length) flush();
      list.push(li[1]);
    } else if (!line.trim()) {
      flush();
    } else {
      if (list.length) flush();
      para.push(line.trim());
    }
  }
  flush();
  return <>{blocks}</>;
}
