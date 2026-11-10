import { expect, test, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { render } from "@/test/render";
import { mockApi, SEED } from "@/test/fixtures";
import { Carteira } from "./Carteira";

const rowsWith = (table: HTMLElement, text: string) =>
  within(table).getAllByRole("row").filter((r) => r.textContent?.includes(text));

test("tabela com corretora, carteira, quantidade, preço, posição, preço médio e resultado", async () => {
  render(<Carteira />, { api: mockApi(SEED) });
  const table = await screen.findByRole("table", { name: "Posições por corretora" });
  expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
    .toEqual(["Moeda", "Corretora", "Carteira", "Quantidade", "Preço", "Posição", "Preço médio", "Resultado"]);
  // ARB: 30% da quantidade na Gate (1.260 a US$ 0,41, comprado a US$ 1,65)
  const [gate] = rowsWith(table, "Gate").filter((r) => r.textContent?.includes("1.260"));
  expect(within(gate).getAllByRole("cell").map((c) => c.textContent))
    .toEqual(["Gate · permissões não verificadas", "spot", "1.260", "US$ 517", "−US$ 1.562"]);
  const [arb] = rowsWith(table, "Arbitrum");
  expect(arb).toHaveTextContent("US$ 0,4100");
  expect(arb).toHaveTextContent("US$ 1,65");
});

test("corretora sem verificação de permissões da chave fica marcada", async () => {
  render(<Carteira />, { api: mockApi(SEED) });
  const table = await screen.findByRole("table", { name: "Posições por corretora" });
  const [gate] = rowsWith(table, "Gate");
  expect(gate).toHaveTextContent("permissões não verificadas");
  const [binance] = rowsWith(table, "Binance");
  expect(binance).not.toHaveTextContent("permissões não verificadas");
});

test("poeira aparece separada", async () => {
  render(<Carteira />, { api: mockApi(SEED) });
  const dust = await screen.findByRole("region", { name: "Poeira (fora do veredito)" });
  expect(within(dust).getByText("Dogecoin")).toBeInTheDocument();
  expect(within(dust).getByText("US$ 9,00")).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Posições por corretora" })).queryByText("Dogecoin")).toBeNull();
});

const csv = (text: string) => new File([text], "operacoes.csv", { type: "text/csv" });

async function upload(file: File, api: typeof fetch) {
  render(<Carteira />, { api });
  const form = await screen.findByRole("form", { name: "Importar CSV de operações" });
  fireEvent.change(within(form).getByLabelText("Corretora"), { target: { value: "bybit" } });
  fireEvent.change(within(form).getByLabelText("Arquivo CSV"), { target: { files: [file] } });
  fireEvent.click(within(form).getByRole("button", { name: "Enviar CSV" }));
  return form;
}

test("upload de CSV por corretora", async () => {
  const api = vi.fn(mockApi(SEED));
  const file = csv("data,par,lado\n2026-10-01,OPUSDT,buy\n2026-10-02,OPUSDT,sell\n");
  const form = await upload(file, api);
  expect(await within(form).findByRole("status")).toHaveTextContent("2 operações novas de 2 lidas no arquivo.");
  const post = api.mock.calls.find(([url]) => url === "/api/csv/bybit")!;
  expect(post[1]).toMatchObject({ method: "POST", body: file });
});

test("CSV fora do formato mostra a mensagem em português", async () => {
  const form = await upload(csv("isto não é csv"), mockApi(SEED));
  expect(await within(form).findByRole("alert")).toHaveTextContent("O arquivo não está no formato de CSV da Bybit.");
});

test("CSV acima de 5 MB nem é enviado", async () => {
  const api = vi.fn(mockApi(SEED));
  const big = csv("a,b\n");
  Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
  const form = await upload(big, api);
  expect(await within(form).findByRole("alert")).toHaveTextContent("O arquivo passa de 5 MB.");
  expect(api.mock.calls.some(([url]) => String(url).startsWith("/api/csv"))).toBe(false);
});

test("alocação por moeda e cartões por corretora", async () => {
  render(<Carteira />, { api: mockApi(SEED) });
  const alloc = await screen.findByRole("region", { name: "Alocação por moeda" });
  const legend = within(alloc).getAllByRole("listitem").map((li) => li.querySelector("[data-symbol]")?.textContent);
  expect(legend[0]).toBe("BTC");  // maior posição primeiro
  expect(legend).not.toContain("DOGE");  // poeira fica fora
  const ex = screen.getByRole("region", { name: "Corretoras" });
  const cards = within(ex).getAllByRole("article");
  expect(cards.map((c) => c.querySelector("h3")?.textContent)).toEqual(["Binance", "Bybit", "Gate", "MEXC"]);
  expect(cards[2]).toHaveTextContent("permissões não verificadas");
  expect(cards[0]).toHaveTextContent("Somente leitura checada pela API");
});

test("filtro por veredito na tabela de posições", async () => {
  render(<Carteira />, { api: mockApi(SEED) });
  const table = await screen.findByRole("table", { name: "Posições por corretora" });
  const filters = screen.getByRole("group", { name: "Filtrar por veredito" });
  fireEvent.click(await within(filters).findByRole("button", { name: /^Sair/ }));
  expect(within(filters).getByRole("button", { name: /^Sair/ })).toHaveAttribute("aria-pressed", "true");
  const coins = within(table).getAllByRole("rowheader").map((h) => h.querySelector("[data-name]")?.textContent);
  expect(coins).toEqual(["Arbitrum", "Pepe"]);
  expect(within(table).getAllByText("Sair").length).toBeGreaterThan(0);
});
