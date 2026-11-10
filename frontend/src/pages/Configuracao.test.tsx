import { expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { render } from "@/test/render";
import { mockApi, SEED } from "@/test/fixtures";
import { Configuracao } from "./Configuracao";

/** Abre uma etapa do assistente pela trilha lateral. */
async function openStage(name: RegExp) {
  const nav = await screen.findByRole("navigation", { name: "Etapas da configuração" });
  fireEvent.click(within(nav).getByRole("button", { name }));
}

async function saveSecret(label: string, value: string) {
  const form = await screen.findByRole("form", { name: label });
  fireEvent.change(within(form).getByLabelText(new RegExp(label)), { target: { value } });
  fireEvent.click(within(form).getByRole("button", { name: "Gravar" }));
  await within(form).findByText("gravado no Keychain");
  return form;
}

test("assistente em 6 etapas, progresso e aviso do modo instalação", async () => {
  render(<Configuracao />, { api: mockApi(SEED) });
  const nav = await screen.findByRole("navigation", { name: "Etapas da configuração" });
  expect(within(nav).getAllByRole("button").map((b) => b.querySelector("[data-stage-title]")?.textContent))
    .toEqual(["Você", "Corretoras", "Telegram", "IA e mercado", "Primeira carga", "Preferências"]);
  // a confirmação da MEXC e Gate já conta sem chave
  expect(within(nav).getByText("1 de 12")).toBeInTheDocument();
  expect(within(nav).getByRole("button", { name: /Corretoras/ })).toHaveTextContent("1 de 2");
  expect(within(nav).getByRole("button", { name: /Preferências/ })).toHaveTextContent("Opcional");
  expect(screen.getByText(/Servidor no modo instalação/)).toHaveTextContent("Falta: anthropic_api_key");
  // começa na primeira etapa com pendência: o analista ainda não foi gravado
  expect(screen.getByRole("heading", { level: 2, name: "Seus dados" })).toBeInTheDocument();
  const steps = screen.getByRole("list", { name: "Nesta etapa" });
  expect(within(steps).getByText("Usuário do analista no Telegram")).toBeInTheDocument();
});

test("próxima e anterior trocam de etapa", async () => {
  render(<Configuracao />, { api: mockApi(SEED) });
  fireEvent.click(await screen.findByRole("button", { name: "Próxima etapa" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Corretoras" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Etapa anterior" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Seus dados" })).toBeInTheDocument();
});

test("etapa Você grava o usuário e o nome de exibição do analista", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  const form = await screen.findByRole("form", { name: "Seus dados" });
  expect(within(form).getByText(/aparece no lugar de “o analista” nas telas e nos avisos/)).toHaveTextContent("Pode ficar em branco.");
  fireEvent.change(within(form).getByLabelText(/Usuário do analista no Telegram/), { target: { value: "@ana_grafico" } });
  fireEvent.change(within(form).getByLabelText(/Nome de exibição do analista/), { target: { value: " Ana " } });
  fireEvent.click(within(form).getByRole("button", { name: "Gravar dados" }));
  await within(form).findByText("Gravado. Vale depois de reiniciar o servidor.");
  const put = api.mock.calls.find(([url, init]) => String(url) === "/api/setup/config" && init?.method === "PUT");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ analyst_username: "@ana_grafico", analyst_name: "Ana" });
});

test("nome de exibição sozinho vale sem reiniciar", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  const form = await screen.findByRole("form", { name: "Seus dados" });
  fireEvent.change(within(form).getByLabelText(/Nome de exibição do analista/), { target: { value: "Ana" } });
  fireEvent.click(within(form).getByRole("button", { name: "Gravar dados" }));
  await within(form).findByText("Gravado e já em uso.");
  const put = api.mock.calls.find(([url, init]) => String(url) === "/api/setup/config" && init?.method === "PUT");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ analyst_name: "Ana" });
});

test("segredo vai para a API e some da tela", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  await openStage(/IA e mercado/);
  const form = await screen.findByRole("form", { name: "Chave da API do Claude" });
  expect(within(form).getByText("falta")).toBeInTheDocument();
  const field = within(form).getByLabelText(/Chave da API do Claude/) as HTMLInputElement;
  expect(field.type).toBe("password");
  fireEvent.change(field, { target: { value: "sk-ant-valor-secreto" } });
  fireEvent.click(within(form).getByRole("button", { name: "Gravar" }));
  await within(form).findByText("Gravado. O valor não fica na tela.");
  const call = api.mock.calls.find(([url]) => String(url) === "/api/setup/secrets/anthropic_api_key");
  expect(call?.[1]).toMatchObject({ method: "POST", body: JSON.stringify({ value: "sk-ant-valor-secreto" }) });
  expect(field.value).toBe("");
  await within(form).findByText("gravado no Keychain");
  expect(document.body.textContent).not.toContain("sk-ant-valor-secreto");
  const nav = screen.getByRole("navigation", { name: "Etapas da configuração" });
  await within(nav).findByText("2 de 12");
  expect(within(nav).getByRole("button", { name: /IA e mercado/ })).toHaveTextContent("1 de 3");
});

test("corretora: link do site, permissões e confirmação da MEXC", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  await openStage(/Corretoras/);
  const link = await screen.findByRole("link", { name: /Abrir chaves de API da Binance/ });
  expect(link).toHaveAttribute("href", expect.stringContaining("binance.com"));
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  const perms = screen.getByRole("list", { name: "Permissões da chave" });
  expect(within(perms).getByText("Habilitar Leitura").closest("li")).toHaveTextContent("Ligar");
  expect(within(perms).getByText("Habilitar Saques").closest("li")).toHaveTextContent("Desligado");
  // passo a passo do site da Binance, na ordem das telas dela
  const howto = screen.getByRole("list", { name: "Passo a passo na Binance" });
  expect(within(howto).getAllByRole("listitem")[1]).toHaveTextContent("Gerada pelo sistema");
  expect(howto).toHaveTextContent("aparece uma vez só");

  fireEvent.click(screen.getByRole("tab", { name: /MEXC/ }));
  const mexc = await screen.findByRole("checkbox", { name: /Conferi no site da MEXC/ });
  fireEvent.click(mexc);
  await waitFor(() => expect(api.mock.calls.some(([url, init]) => String(url) === "/api/setup/config"
    && init?.method === "PUT" && String(init.body) === JSON.stringify({ confirmed_read_only: ["mexc"] }))).toBe(true));
  await waitFor(() => expect((screen.getByRole("checkbox", { name: /Conferi no site da MEXC/ }) as HTMLInputElement).checked).toBe(true));

  fireEvent.click(screen.getByRole("button", { name: "Checar chaves" }));
  const result = await screen.findByRole("list", { name: "Resultado da checagem" });
  expect(within(result).getAllByRole("listitem")).toHaveLength(4);
  expect(within(result).getAllByText("sem chave no Keychain")).toHaveLength(4);
});

test("gravar o par da corretora dispara a checagem da chave", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  await openStage(/Corretoras/);
  await saveSecret("Chave da API da Binance", "k");
  await saveSecret("Segredo da API da Binance", "s");
  await screen.findByText(/Checagem: ok/);
  expect(api.mock.calls.filter(([url]) => String(url) === "/api/setup/check-keys")).toHaveLength(1);  // só quando o par fecha
  expect(screen.getByRole("tab", { name: /Binance/ })).toHaveTextContent("Gravada");
});

test("login do Telegram: telefone, código, senha de duas etapas e sessão gravada", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  await openStage(/Telegram/);
  const form = await screen.findByRole("form", { name: "Login do Telegram" });
  expect(within(form).getByRole("button", { name: "Enviar código" })).toBeDisabled();  // sem api_id
  await saveSecret("api_id do aplicativo", "1");
  await saveSecret("api_hash do aplicativo", "h");
  await waitFor(() => expect(within(form).getByRole("button", { name: "Enviar código" })).toBeEnabled());
  fireEvent.change(within(form).getByLabelText("Telefone com DDI"), { target: { value: "+55 11 99999 0000" } });
  fireEvent.click(within(form).getByRole("button", { name: "Enviar código" }));
  fireEvent.change(await within(form).findByLabelText("Código recebido no Telegram"), { target: { value: "12345" } });
  fireEvent.click(within(form).getByRole("button", { name: "Confirmar código" }));
  fireEvent.change(await within(form).findByLabelText("Senha de duas etapas"), { target: { value: "senha-2fa" } });
  fireEvent.click(within(form).getByRole("button", { name: "Entrar" }));
  await within(form).findByText("Sessão de @demo_user gravada no Keychain.");
  expect(document.body.textContent).not.toContain("senha-2fa");
  const signIn = api.mock.calls.filter(([url]) => String(url) === "/api/setup/telegram/sign-in").map(([, init]) => JSON.parse(String(init?.body)));
  expect(signIn).toEqual([{ code: "12345" }, { code: "12345", password: "senha-2fa" }]);
});

test("preferências por controle deslizante gravam só o que mudou", async () => {
  const api = vi.fn(mockApi(SEED));
  render(<Configuracao />, { api });
  await openStage(/Preferências/);
  const slider = await screen.findByRole("slider", { name: /Atualizar saldos e preços a cada/ });
  expect(slider).toHaveValue("5");
  fireEvent.change(slider, { target: { value: "10" } });
  expect(screen.getByText("10 min")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("slider", { name: /Avisar alta ou queda no dia/ }), { target: { value: "15" } });
  fireEvent.click(screen.getByRole("button", { name: "Gravar preferências" }));
  await screen.findByText("Gravado. Vale depois de reiniciar o servidor.");
  const put = api.mock.calls.find(([url, init]) => String(url) === "/api/setup/config" && init?.method === "PUT");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ sync_minutes: 10, intraday_move: 0.15 });
});

test("primeira carga mostra os comandos do terminal e o reinício bloqueado", async () => {
  render(<Configuracao />, { api: mockApi(SEED) });
  await openStage(/Primeira carga/);
  expect(await screen.findByText(/importar --meses 12/, { selector: "code" })).toBeInTheDocument();
  expect(screen.getByText(/manual-inicial/, { selector: "code" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reiniciar o servidor" })).toBeDisabled();
});
