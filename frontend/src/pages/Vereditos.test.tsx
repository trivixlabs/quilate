import { expect, test, vi } from "vitest";
import { fireEvent, render as rtlRender, screen, within } from "@testing-library/react";
import { createChart } from "lightweight-charts";
import { render } from "@/test/render";
import { mockApi, SEED, SEED_COST_UNKNOWN, SEED_FET_NO_ANALYST_IA_PAUSADA, SEED_MANUAL_PENDENTE } from "@/test/fixtures";
import { PortfolioHero } from "@/components/PortfolioHero";
import { Vereditos } from "./Vereditos";

test("colunas na ordem Sair, Reduzir, Manter", async () => {
  render(<Vereditos />, { api: mockApi(SEED) });
  expect(await screen.findByRole("heading", { level: 1, name: "Visão geral" })).toBeInTheDocument();
  const hoje = screen.getByRole("region", { name: "Veredito de hoje" });
  expect(within(hoje).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Sair", "Reduzir", "Manter"]);
});

test("resultado do dia, investido e divisão por corretora", async () => {
  render(<Vereditos />, { api: mockApi(SEED) });
  const hero = await screen.findByRole("region", { name: "Patrimônio" });
  // soma de valor menos valor de ontem pela variação de 24 h de cada moeda
  expect(within(hero).getByText(/^Hoje/).closest("span")).toHaveTextContent("+US$ 978 (+1,45%)");
  expect(hero).toHaveTextContent("Investido");
  const ex = screen.getByRole("region", { name: "Por corretora" });
  expect(within(ex).getAllByRole("listitem").map((li) => li.querySelector("[data-name]")?.textContent))
    .toEqual(["Binance", "Bybit", "Gate", "MEXC"]);
});

test("período do gráfico troca a série", async () => {
  render(<Vereditos />, { api: mockApi(SEED) });
  const seven = await screen.findByRole("button", { name: "7 dias" });
  fireEvent.click(seven);
  expect(seven).toHaveAttribute("aria-pressed", "true");
  const series = vi.mocked(createChart).mock.results.at(-1)!.value.addSeries();
  expect(series.setData.mock.calls.at(-1)[0]).toHaveLength(7);
});

test("termômetro do mercado na visão geral", async () => {
  render(<Vereditos />, { api: mockApi(SEED) });
  const market = await screen.findByRole("region", { name: "Mercado hoje" });
  expect(await within(market).findByText("62")).toBeInTheDocument();
  expect(market).toHaveTextContent("57,31%");
});

test("aviso de moeda sem análise do analista e de IA pausada", async () => {
  render(<Vereditos />, { api: mockApi(SEED_FET_NO_ANALYST_IA_PAUSADA) });
  expect(await screen.findByText("Sem análise direta do analista · confiança menor")).toBeInTheDocument();
  expect(screen.getByText("IA pausada por limite de gasto")).toBeInTheDocument();
});

test("custo desconhecido no lugar do resultado", async () => {
  render(<Vereditos />, { api: mockApi(SEED_COST_UNKNOWN) });
  const pepe = await screen.findByRole("link", { name: "PEPE, veredito Sair" });
  expect(within(pepe).getByText("custo desconhecido")).toBeInTheDocument();
  const arb = screen.getByRole("link", { name: "ARB, veredito Sair" });
  expect(within(arb).getByText("−US$ 5.208")).toBeInTheDocument();
  expect(within(arb).queryByText("custo desconhecido")).toBeNull();
});

test("cartão abre o foco da moeda", async () => {
  render(<Vereditos />, { api: mockApi(SEED) });
  fireEvent.click(await screen.findByRole("link", { name: "ARB, veredito Sair" }));
  expect(screen.getByTestId("location")).toHaveTextContent("/moeda/ARB");
});

test("manual não revisado, régua diferente da IA, corretora desatualizada e sem câmbio", async () => {
  render(<Vereditos />, { api: mockApi(SEED_MANUAL_PENDENTE) });
  expect(await screen.findByText("Manual do analista ainda não revisado")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Revisar regras" })).toHaveAttribute("href", "/analista");
  const link = screen.getByRole("link", { name: "LINK, veredito Reduzir" });
  expect(within(link).getByText("régua: Manter, IA: Reduzir")).toBeInTheDocument();
  const gate = within(screen.getByRole("region", { name: "Por corretora" })).getByText("Gate").closest("li");
  expect(gate).toHaveTextContent("desatualizada");
  expect(screen.queryByText(/R\$/)).toBeNull();
});

test("gráfico do patrimônio não é recriado quando a consulta volta", () => {
  const ov = SEED.overview;
  const { rerender } = rtlRender(<PortfolioHero ov={ov} liveDelta={0} livePnlDelta={0} />);
  rerender(<PortfolioHero ov={{ ...ov, history: ov.history.map((h) => ({ ...h })) }} liveDelta={0} livePnlDelta={0} />);
  expect(createChart).toHaveBeenCalledTimes(1);
  const series = vi.mocked(createChart).mock.results[0].value.addSeries();
  expect(series.setData).toHaveBeenCalledTimes(2);
});
