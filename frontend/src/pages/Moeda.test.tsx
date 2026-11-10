import { expect, test, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { createChart } from "lightweight-charts";
import { render } from "@/test/render";
import { mockApi, SEED, SEED_ARB_COST_UNKNOWN } from "@/test/fixtures";
import { Moeda } from "./Moeda";

const page = (symbol: string, api: typeof fetch) =>
  render(<Routes><Route path="/moeda/:symbol" element={<Moeda />} /></Routes>, { api, route: `/moeda/${symbol}` });

test("sete sinais com valor medido e 'sem dado'", async () => {
  page("BTC", mockApi(SEED));
  const list = await screen.findByRole("list", { name: "Os 7 sinais" });
  const items = within(list).getAllByRole("listitem");
  expect(items).toHaveLength(7);
  expect(items[0]).toHaveTextContent("Força contra o BTC");
  expect(items[0]).toHaveTextContent("sem dado");
  expect(items[1]).toHaveTextContent("−8% da máxima");
});

test("fala do analista mostra data, tópico e minuto da live", async () => {
  page("ARB", mockApi(SEED));
  const quotes = await screen.findByRole("region", { name: "O que o analista disse" });
  expect(within(quotes).getByText("Dez fechamentos semanais seguidos abaixo da média de 50 semanas. Meu limite é oito.")).toBeInTheDocument();
  expect(within(quotes).getByText("25/09 · tópico MARKET UPDATES · live no YouTube, minuto 33")).toBeInTheDocument();
  expect(within(quotes).getByText("14/10 · tópico ON-CHAIN DATA · texto")).toBeInTheDocument();
});

test("formulário de custo envia e atualiza", async () => {
  const api = vi.fn(mockApi(SEED_ARB_COST_UNKNOWN));
  page("ARB", api);
  const form = await screen.findByRole("group", { name: "Ajustar preço médio" });
  expect(form).toHaveAttribute("open"); // aberto porque o custo é desconhecido
  expect(screen.getByLabelText("Resultado")).toHaveTextContent("custo desconhecido");

  fireEvent.change(within(form).getByLabelText("Preço médio de compra (US$)"), { target: { value: "1,65" } });
  fireEvent.click(within(form).getByRole("button", { name: "Salvar preço médio" }));

  expect(await screen.findByText("Preço médio salvo.")).toBeInTheDocument();
  const post = api.mock.calls.find(([url]) => url === "/api/cost-overrides")!;
  expect(JSON.parse(String(post[1]!.body))).toMatchObject({ symbol: "ARB", avg_cost_usd: 1.65 });
  expect(await screen.findByLabelText("Preço médio de compra")).toHaveTextContent("US$ 1,65");
  expect(screen.getByLabelText("Resultado")).toHaveTextContent("−US$ 5.208");
  expect(createChart).toHaveBeenCalledTimes(1); // a consulta nova não recria o gráfico
});

test("custo rejeitado pelo backend mostra a mensagem em português", async () => {
  page("ARB", mockApi(SEED_ARB_COST_UNKNOWN));
  const form = await screen.findByRole("group", { name: "Ajustar preço médio" });
  fireEvent.change(within(form).getByLabelText("Preço médio de compra (US$)"), { target: { value: "0" } });
  fireEvent.click(within(form).getByRole("button", { name: "Salvar preço médio" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/^O preço médio precisa ser um número maior que zero\.$/);
});

test("custo que não é número nem sai da tela", async () => {
  const api = vi.fn(mockApi(SEED_ARB_COST_UNKNOWN));
  page("ARB", api);
  const form = await screen.findByRole("group", { name: "Ajustar preço médio" });
  fireEvent.change(within(form).getByLabelText("Preço médio de compra (US$)"), { target: { value: "abc" } });
  fireEvent.click(within(form).getByRole("button", { name: "Salvar preço médio" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Informe o preço médio só com números, por exemplo 1,65.");
  expect(api.mock.calls.some(([url]) => url === "/api/cost-overrides")).toBe(false);
});

test("editar o preço depois de salvar apaga a confirmação e mantém o formulário aberto", async () => {
  page("ARB", mockApi(SEED_ARB_COST_UNKNOWN));
  const form = await screen.findByRole("group", { name: "Ajustar preço médio" });
  const input = within(form).getByLabelText("Preço médio de compra (US$)");
  fireEvent.change(input, { target: { value: "1,65" } });
  fireEvent.click(within(form).getByRole("button", { name: "Salvar preço médio" }));
  expect(await screen.findByText("Preço médio salvo.")).toBeInTheDocument();
  expect(await screen.findByLabelText("Preço médio de compra")).toHaveTextContent("US$ 1,65"); // custo agora conhecido
  fireEvent.change(input, { target: { value: "1,7" } });
  expect(screen.queryByText("Preço médio salvo.")).toBeNull();
  expect(form).toHaveAttribute("open");
});

test("lista lateral troca de moeda sem recriar o gráfico", async () => {
  page("BTC", mockApi(SEED));
  const nav = await screen.findByRole("navigation", { name: "Moedas da carteira" });
  expect(await within(nav).findAllByRole("link")).toHaveLength(8);
  fireEvent.click(within(nav).getByRole("link", { name: /^ARB/ }));
  expect(screen.getByTestId("location")).toHaveTextContent("/moeda/ARB");
  expect(await screen.findByRole("heading", { level: 1, name: "Arbitrum" })).toBeInTheDocument();
  expect(screen.getByText(/Binance · Gate/)).toBeInTheDocument();
  expect(createChart).toHaveBeenCalledTimes(1);
});

test("cabeçalho mostra veredito com ícone, régua e IA, e a contagem da régua", async () => {
  page("ARB", mockApi(SEED));
  const head = await screen.findByRole("region", { name: "Resumo da moeda" });
  const verdict = within(head).getByRole("status", { name: "Veredito" });
  expect(verdict).toHaveTextContent("Sair");
  expect(verdict).toHaveTextContent("Régua: Sair · IA: Sair");
  expect(within(head).getByRole("meter", { name: /Confiança 78%/ })).toBeInTheDocument();
  const signals = screen.getByRole("region", { name: "Régua de 7 sinais" });
  expect(signals).toHaveTextContent("5 de 7");
});

test("quantidade por corretora com barra da fatia", async () => {
  page("ARB", mockApi(SEED));
  const hold = await screen.findByRole("region", { name: "Quantidade por corretora" });
  const rows = within(hold).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Binance");
  expect(within(rows[0]).getByRole("meter")).toHaveAttribute("aria-valuenow");
});
