import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { DEMO, getOverview, getSetup } from "@/lib/api";
import { usd } from "@/lib/format";
import { useLive } from "@/lib/live";
import type { Overview, Setup } from "@/lib/types";

type Item = { to: string; label: string; icon: string; badge?: (ov: Overview | null, setup: Setup | null) => [string, string] | null };

/** Navegação em três grupos. `badge` devolve o texto visível e o complemento para leitor de tela. */
const GROUPS: [string, Item[]][] = [
  ["Acompanhar", [
    { to: "/", label: "Visão geral", icon: "M3 11.5 12 4l9 7.5M5.5 10v10h13V10" },
    { to: "/carteira", label: "Carteira", icon: "M3 7.5h15a3 3 0 0 1 3 3V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Zm0 0L5.5 4H17M16.5 14h.01" },
    { to: "/mercado", label: "Mercado", icon: "M3 17l5.5-5.5 4 4L21 7M15 7h6v6" },
  ]],
  ["Entender", [
    { to: "/analista", label: "Manual do analista", icon: "M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5v-15ZM5 19.5A1.5 1.5 0 0 0 6.5 21H19M9 7.5h6",
      badge: (ov) => (ov && !ov.playbook_approved ? ["revisar", ": manual com regras para aprovar"] : null) },
    { to: "/historico", label: "Histórico de acertos", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-3.5 9 2.5 2.5 4.5-5" },
  ]],
  ["Sistema", [
    { to: "/configuracao", label: "Configuração", icon: "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4",
      badge: (_, setup) => {
        const n = setup ? setup.checklist.filter((s) => !s.done).length : 0;
        return n ? [String(n), " passos pendentes"] : null;
      } },
  ]],
];
const DISCLAIMER = "Material de apoio à decisão, não é recomendação de investimento.";
const BUDGET: Record<string, [color: string, bar: string, text: string]> = {
  alerta: ["text-reduzir", "bg-reduzir", "alerta de gasto"], bloqueado: ["text-sair", "bg-sair", "IA pausada"],
};
const CYCLE = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const cycle = (iso: string) => CYCLE.format(new Date(iso)).replace(", ", " às ");

/** Moldura de todas as páginas: barra lateral com a navegação e o estado do sistema, o conteúdo e o aviso no rodapé. */
export function AppShell() {
  const { connected, lastEvent } = useLive();
  const [ov, setOv] = useState<Overview | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const onSetupPage = useLocation().pathname === "/configuracao";  // a página já mostra o próprio aviso

  // ponytail: a Visão geral também busca o overview; contexto compartilhado se o custo aparecer.
  useEffect(() => {
    let off = false;
    getOverview().then((o) => { if (!off) setOv(o); }, () => { /* sem gasto na barra; a página mostra o erro */ });
    getSetup().then((s) => { if (!off) setSetup(s); }, () => { /* sem faixa: a página Configuração mostra o erro */ });
    return () => { off = true; };
  }, [lastEvent]);

  const budget = ov ? BUDGET[ov.budget_state] : undefined;
  return (
    <div className="flex min-h-full flex-wrap items-stretch bg-fundo bg-[radial-gradient(50rem_26rem_at_85%_-10%,rgb(34_211_238/0.08),transparent_70%),radial-gradient(40rem_24rem_at_30%_0%,rgb(139_92_246/0.08),transparent_70%)]">
      <aside className="flex max-w-full flex-[1_1_248px] flex-col gap-5 border-borda bg-[#0b0d14]/90 px-3.5 py-5 lg:sticky lg:top-0 lg:h-screen lg:max-w-[264px] lg:border-r">
        <div className="flex items-center gap-2.5 px-2">
          <span aria-hidden="true" className="flex size-[34px] items-center justify-center rounded-[10px] border-[1.5px] border-violeta text-[15px] font-bold text-violeta">C</span>
          <span className="flex flex-col">
            <span className="text-[15px] font-semibold">Quilate</span>
            <span className="text-xs text-texto-2">Só recomenda. Nunca opera.</span>
          </span>
        </div>

        <nav aria-label="Seções" className="flex flex-wrap gap-x-6 gap-y-4 lg:flex-col">
          {GROUPS.map(([group, items]) => (
            <div key={group} role="group" aria-label={group} className="flex min-w-[200px] flex-1 flex-col gap-1 lg:flex-none">
              <span aria-hidden="true" className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8a93a6]">{group}</span>
              {items.map((it) => {
                const badge = it.badge?.(ov, setup);
                return (
                  <NavLink key={it.to} to={it.to} end
                    className={({ isActive }) => `group flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-sm no-underline outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                      isActive ? "bg-[#171b27] font-semibold text-white shadow-[inset_2px_0_0_var(--color-violeta)]" : "text-[#c3c9d6] hover:bg-[#121621]"}`}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0"><path d={it.icon} /></svg>
                    <span data-label className="grow">{it.label}</span>
                    {badge && (
                      <span className="rounded-full bg-reduzir/14 px-2 py-0.5 text-[11px] font-semibold text-[#fcd34d]">
                        {badge[0]}<span className="sr-only">{badge[1]}</span>
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="flex flex-col gap-3 rounded-2xl border border-borda bg-painel p-3.5 lg:mt-auto">
          <span role="status" className="flex items-center gap-2.5 text-[13px]">
            <span aria-hidden="true" className="relative inline-flex size-2">
              {connected && <span className="ping absolute inset-0 rounded-full bg-alta" />}
              <span className={`relative size-2 rounded-full ${connected ? "bg-alta" : "bg-reduzir"}`} />
            </span>
            {connected ? "Ao vivo" : "Reconectando…"}
          </span>
          {ov && (
            <div className="flex flex-col gap-1.5">
              <span className={`text-xs ${budget?.[0] ?? "text-texto-2"}`}>
                IA no mês: {usd(ov.spent_month_usd)} de {usd(ov.budget_usd)}{budget && ` · ${budget[2]}`}
              </span>
              <span aria-hidden="true" className="block h-1.5 overflow-hidden rounded-full bg-borda">
                <span className={`block h-full rounded-full transition-[width] duration-700 ${budget?.[1] ?? "bg-violeta"}`}
                  style={{ width: `${Math.min(100, (ov.spent_month_usd / (ov.budget_usd || 1)) * 100)}%` }} />
              </span>
            </div>
          )}
          {ov?.last_cycle_utc && <span className="text-xs text-texto-2">Último ciclo: {cycle(ov.last_cycle_utc)}</span>}
          {DEMO && (
            <span className="self-start rounded-full border border-[#fcd34d]/35 bg-[#fcd34d]/8 px-2.5 py-1 text-[11px] text-[#fcd34d]">
              Dados de demonstração
            </span>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6 px-4 pb-12 pt-7 sm:px-8">
        <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6">
          {setup?.mode === "setup" && !onSetupPage && (
            <p role="status" className="m-0 rounded-[14px] border border-reduzir/40 bg-reduzir/10 px-4 py-3 text-sm text-texto">
              Instalação incompleta: o servidor está no modo instalação, sem corretoras, agendador nem Telegram.{" "}
              <NavLink to="/configuracao" className="font-semibold text-texto underline">Complete em Configuração</NavLink>.
            </p>
          )}
          <main><Outlet /></main>
          <footer className="border-t border-borda pt-4 text-center text-xs text-texto-2">{DISCLAIMER}</footer>
        </div>
      </div>
    </div>
  );
}
