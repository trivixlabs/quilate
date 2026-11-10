import { expect, test } from "vitest";
import { screen, within } from "@testing-library/react";
import { render } from "@/test/render";
import { mockApi, SEED } from "@/test/fixtures";
import { Mercado } from "./Mercado";

test("cada número com fonte e data", async () => {
  render(<Mercado />, { api: mockApi({ ...SEED, market: { ...SEED.market, etf_flows: null } }) });
  const tile = async (name: string) => screen.findByRole("region", { name });
  const fng = await tile("Medo e Ganância");
  expect(fng).toHaveTextContent("62 de 100");
  expect(fng).toHaveTextContent("ganância");
  expect(fng).toHaveTextContent("Alternative.me · 04/11/2026");
  expect(within(fng).getByRole("img", { name: "Índice 62 de 100, ganância" })).toBeInTheDocument();
  const dom = await tile("Dominância do BTC");
  expect(dom).toHaveTextContent("57,31%");
  expect(dom).toHaveTextContent("+0,84 p.p. em 7 dias");
  expect(dom).toHaveTextContent("CoinGecko · 04/11/2026");
  expect(await tile("Altcoin Season Index")).toHaveTextContent("32 de 100");
  // os três primeiros ficam em destaque; o resto vai para Outros indicadores
  const others = screen.getByRole("region", { name: "Outros indicadores" });
  expect(within(others).getByRole("region", { name: "MVRV do BTC" })).toBeInTheDocument();
  expect(within(others).queryByRole("region", { name: "Medo e Ganância" })).toBeNull();
  expect(await tile("MVRV do BTC")).toHaveTextContent("2,14BGeometrics · 03/11/2026");
  expect(await tile("NUPL do BTC")).toHaveTextContent("0,52");
  expect(await tile("Funding do BTC")).toHaveTextContent(/^Funding do BTC0,0082%.*Coinalyze · 04\/11\/2026$/);
  expect(await tile("Dólar (índice amplo)")).toHaveTextContent(/121,38.*FRED · 31\/10\/2026$/);
  expect(within(await tile("Fluxo dos ETFs de BTC")).getByText("Sem dado coletado.")).toBeInTheDocument();
});

test("fluxo de ETF mostra o último dia", async () => {
  render(<Mercado />, { api: mockApi(SEED) });
  const etf = await screen.findByRole("region", { name: "Fluxo dos ETFs de BTC" });
  expect(etf).toHaveTextContent("+US$ 245,3 mi");
  expect(etf).toHaveTextContent("Fluxo líquido de 03/11.");
  expect(etf).toHaveTextContent("TFTC · 04/11/2026");
});
