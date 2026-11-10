import { expect, test, vi } from "vitest";
import { ApiError, getCoin } from "./api";

const reply = (status: number, detail: unknown) =>
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail }), { status }));

test("erro da API chega à tela em português, sem código nem inglês", async () => {
  reply(404, "Moeda sem veredito.");
  await expect(getCoin("ZZZ")).rejects.toMatchObject({ status: 404, message: "Moeda sem veredito." });
  reply(404, "Not Found");
  await expect(getCoin("ZZZ")).rejects.toMatchObject({ status: 404, message: "o sistema local recusou o pedido" });
  reply(422, [{ msg: "Input should be greater than 0" }]);
  await expect(getCoin("ZZZ")).rejects.toMatchObject({ status: 422, message: "dados recusados pelo sistema" });
  vi.stubGlobal("fetch", async () => { throw new TypeError("Failed to fetch"); });
  const e = await getCoin("ZZZ").catch((x: unknown) => x);
  expect(e).toBeInstanceOf(ApiError);
  expect(e).toMatchObject({ status: 0, message: "o sistema local não respondeu" });
});
