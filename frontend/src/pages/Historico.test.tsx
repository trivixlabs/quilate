import { expect, test } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { render } from "@/test/render";
import { mockApi, SEED, SEED_TRACK_EMPTY } from "@/test/fixtures";
import { Historico } from "./Historico";

const row = (table: HTMLElement, first: string) =>
  within(table).getAllByRole("row").find((r) => r.textContent?.startsWith(first))!;

test("ainda sem dados suficientes", async () => {
  render(<Historico />, { api: mockApi(SEED_TRACK_EMPTY) });
  expect(await screen.findByText("Ainda sem dados suficientes")).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});

test("taxa por veredito e por sinal em 7, 30 e 90 dias", async () => {
  render(<Historico />, { api: mockApi(SEED) });
  const byVerdict = await screen.findByRole("table", { name: "Taxa de acerto por veredito" });
  expect(within(byVerdict).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Veredito", "7 dias", "30 dias", "90 dias"]);
  expect(within(row(byVerdict, "Manter")).getAllByRole("cell").map((c) => c.textContent))
    .toEqual(["63% (15 de 24)", "63% (10 de 16)", "sem amostra"]);
  const bySignal = screen.getByRole("table", { name: "Taxa de acerto por sinal" });
  expect(row(bySignal, "S1")).toHaveTextContent("Força contra o BTC");
  expect(row(bySignal, "S1")).toHaveTextContent("64% (9 de 14)");
  expect(within(bySignal).getAllByRole("row")).toHaveLength(8);
});

test("cartões de acerto por veredito trocam de prazo", async () => {
  render(<Historico />, { api: mockApi(SEED) });
  const cards = await screen.findByRole("region", { name: "Acerto por veredito" });
  const manter = within(cards).getByRole("article", { name: "Manter" });
  expect(manter).toHaveTextContent("63%");
  expect(manter).toHaveTextContent("15 de 24");
  fireEvent.click(screen.getByRole("button", { name: "90 dias" }));
  expect(screen.getByRole("button", { name: "90 dias" })).toHaveAttribute("aria-pressed", "true");
  expect(within(cards).getByRole("article", { name: "Manter" })).toHaveTextContent("sem amostra");
});

test("lista dos vereditos com o resultado", async () => {
  render(<Historico />, { api: mockApi(SEED) });
  const list = await screen.findByRole("table", { name: "Vereditos com resultado" });
  const arb = row(list, "28/10/2026ARB");
  expect(arb).toHaveTextContent("Sair");
  expect(arb).toHaveTextContent("Acertou");
  expect(arb).toHaveTextContent("moeda −6,10% · BTC +1,20%");
  expect(row(list, "05/10/2026PEPE")).toHaveTextContent("Acertou");
});

test("explica que o Manter do BTC fica fora da taxa", async () => {
  render(<Historico />, { api: mockApi(SEED) });
  expect(await screen.findByText(/Manter do BTC fica fora das taxas/)).toBeInTheDocument();
});
