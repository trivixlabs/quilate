import { expect, test } from "vitest";
import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { render } from "@/test/render";
import { demoApi, mockApi, SEED, SEED_FET_NO_ANALYST_IA_PAUSADA, SEED_MANUAL_PENDENTE } from "@/test/fixtures";
import { AppShell } from "./AppShell";

const shell = (api: typeof fetch) =>
  render(<Routes><Route element={<AppShell />}><Route index element={<p>conteúdo</p>} /></Route></Routes>, { api });

const labels = (nav: HTMLElement) => within(nav).getAllByRole("link").map((l) => l.querySelector("[data-label]")?.textContent);

test("aviso exato e a barra lateral em três grupos", async () => {
  shell(mockApi(SEED));
  expect(screen.getByRole("contentinfo")).toHaveTextContent(/^Material de apoio à decisão, não é recomendação de investimento\.$/);
  const nav = screen.getByRole("navigation", { name: "Seções" });
  expect(labels(nav)).toEqual(["Visão geral", "Carteira", "Mercado", "Manual do analista", "Histórico de acertos", "Configuração"]);
  expect(within(nav).getAllByRole("group").map((g) => g.getAttribute("aria-label"))).toEqual(["Acompanhar", "Entender", "Sistema"]);
  expect(within(nav).getByRole("link", { name: /Visão geral/ })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: /Manual do analista/ })).toHaveAttribute("href", "/analista");
  expect(await screen.findByText(/IA no mês/)).toHaveTextContent(/^IA no mês: US\$ 3,20 de US\$ 50,00$/);
  expect(screen.getByText(/Último ciclo/)).toHaveTextContent("Último ciclo: 04/11 às 11:00");
});

test("Configuração mostra quantos passos faltam", async () => {
  shell(mockApi(SEED));
  const nav = screen.getByRole("navigation", { name: "Seções" });
  // o fetch falso começa com 1 de 12 passos concluídos
  expect(await within(nav).findByRole("link", { name: /Configuração/ })).toHaveTextContent("11 passos pendentes");
});

test("Manual pede revisão quando não está aprovado", async () => {
  shell(mockApi(SEED_MANUAL_PENDENTE));
  const nav = screen.getByRole("navigation", { name: "Seções" });
  expect(await within(nav).findByRole("link", { name: /Manual do analista/ })).toHaveTextContent("revisar");
});

test("gasto bloqueado é legível sem cor", async () => {
  shell(mockApi(SEED_FET_NO_ANALYST_IA_PAUSADA));
  expect(await screen.findByText(/IA no mês/)).toHaveTextContent("IA no mês: US$ 50,10 de US$ 50,00 · IA pausada");
});

test("gasto em alerta é legível sem cor", async () => {
  shell(mockApi({ ...SEED, overview: { ...SEED.overview, budget_state: "alerta", spent_month_usd: 41 } }));
  expect(await screen.findByText(/IA no mês/)).toHaveTextContent("IA no mês: US$ 41,00 de US$ 50,00 · alerta de gasto");
});

test("faixa de instalação incompleta aparece no modo instalação, mas não nos dados de demonstração", async () => {
  const { unmount } = shell(mockApi(SEED));
  expect(await screen.findByText(/Instalação incompleta/)).toBeInTheDocument();
  unmount();
  shell(demoApi);
  // o selo da Configuração vem de /api/setup: só depois dele a ausência da faixa prova algo
  const nav = screen.getByRole("navigation", { name: "Seções" });
  expect(await within(nav).findByRole("link", { name: /Configuração.*passos pendentes/ })).toBeInTheDocument();
  expect(screen.queryByText(/Instalação incompleta/)).toBeNull();
  const setup = await (await demoApi("/api/setup")).json();
  expect(setup.checklist.some((c: { done: boolean }) => c.done)).toBe(true);
  expect(setup.checklist.some((c: { done: boolean }) => !c.done)).toBe(true);
});
