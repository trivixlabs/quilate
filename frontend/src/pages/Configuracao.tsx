import { useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError, checkKeys, deleteSecret, getSetup, restartServer, saveConfig, saveSecret, telegramSendCode, telegramSignIn,
} from "@/lib/api";
import { exchangeName } from "@/lib/format";
import { useLiveQuery } from "@/lib/live";
import type { Exchange, KeyCheck, SecretName, Setup, SetupConfig, SetupStep } from "@/lib/types";
import { LoadState, StaleError } from "@/components/LoadState";

/** As 6 etapas do assistente. `steps` são os ids do checklist de `backend/quilate/api/setup.py` que cada etapa fecha. */
const STAGES = [
  { title: "Você", heading: "Seus dados", sub: "Nome e analista", steps: ["analista"],
    why: "O sistema precisa saber quem publica as análises no grupo. Só as mensagens dessa pessoa contam para o veredito. Seu nome só aparece na tela.",
    needs: "o usuário do analista no Telegram" },
  { title: "Corretoras", heading: "Corretoras", sub: "Chaves só de leitura", steps: ["corretoras", "confirmacao"],
    why: "Cada corretora dá uma chave de API que deixa o sistema ler saldos e operações. Com ela o painel calcula patrimônio, preço médio e resultado. As corretoras não têm botão de autorizar para apps pessoais: a chave é criada no site e colada aqui.",
    needs: "login em cada corretora e o código de dois fatores" },
  { title: "Telegram", heading: "Telegram", sub: "Leitura do grupo e avisos", steps: ["telegram_app", "telegram_login", "bot"],
    why: "O sistema lê o grupo com a sua conta, transcreve os áudios do analista e avisa você por um bot. Ele nunca escreve no grupo.",
    needs: "o celular com o Telegram, para receber o código" },
  { title: "IA e mercado", heading: "IA e mercado", sub: "Claude, dados e modelo", steps: ["claude", "mercado", "hf"],
    why: "O Claude escreve o veredito de cada moeda a partir da régua de 7 sinais. As chaves de mercado trazem dominância, juros e derivativos. O Hugging Face libera o modelo que organiza as falas do analista.",
    needs: "conta na Anthropic, no Hugging Face e nos serviços de dados" },
  { title: "Primeira carga", heading: "Primeira carga", sub: "Importar, manual e reinício", steps: ["importar", "manual", "servir"],
    why: "Dois passos ficam no Terminal: um demora, o outro gasta dinheiro e pede confirmação. O último liga o servidor completo.",
    needs: "o Terminal aberto na pasta do projeto" },
  { title: "Preferências", heading: "Preferências", sub: "Alertas e frequência", steps: [],
    why: "De quanto em quanto tempo o sistema atualiza, quando o bot avisa e quanto a IA pode gastar por mês. Os valores padrão já funcionam.",
    needs: "só decidir os limites" },
];

/** Onde criar a chave em cada corretora e o que marcar. Caminhos dos sites em 11/2026: podem mudar de nome. */
const EXCHANGES: { id: Exchange; where: string; url: string; verified: boolean; perms: [string, boolean][]; howto?: string[] }[] = [
  { id: "binance", where: "Perfil, Gerenciamento de API, Criar API, Gerada pelo sistema", verified: true,
    url: "https://www.binance.com/pt-BR/my/settings/api-management",
    // Textos da tela de Gerenciamento de API conferidos em 09/11/2026. As telas depois do Próximo podem mudar de nome.
    howto: [
      "Clique em Criar API. A Binance só libera depois da verificação de identidade (KYC) concluída.",
      "Em Escolha o tipo de chave API, marque Gerada pelo sistema e clique em Próximo. Não use Gerada pelo usuário: ela pede um par de chaves Ed25519 ou RSA que o sistema não usa.",
      "Dê um nome à chave, por exemplo quilate.",
      "Confirme com a verificação de segurança: e-mail, SMS, autenticador ou passkey.",
      "Copie a Chave API e a Chave Secreta para os campos do passo 3. A Chave Secreta aparece uma vez só: se fechar a tela sem copiar, apague a chave e crie outra.",
      "Clique em Editar restrições e deixe marcada só Habilitar Leitura, como no passo 2.",
      "Em restrição de acesso por IP, escolha Sem restrição se a internet da sua casa troca de IP. Com IP fixo, restrinja ao IP deste Mac.",
    ],
    perms: [["Habilitar Leitura", true], ["Habilitar Trading Spot e de Margem", false], ["Habilitar Futuros", false], ["Habilitar Saques", false], ["Habilitar Transferência Universal", false]] },
  { id: "bybit", where: "Perfil, API, Criar nova chave, Gerada pelo sistema", verified: true,
    url: "https://www.bybit.com/app/user/api-management",
    perms: [["Somente leitura", true], ["Leitura e escrita", false], ["Saque", false], ["Transferência", false]] },
  { id: "mexc", where: "Perfil, Gerenciamento de API, Criar", verified: false, url: "https://www.mexc.com/user/openapi",
    perms: [["Leitura da conta", true], ["Leitura do spot", true], ["Trade", false], ["Saque", false]] },
  { id: "gate", where: "Perfil, Gerenciamento de API, Criar chave", verified: false, url: "https://www.gate.io/myaccount/api_key_manage",
    perms: [["Spot: somente leitura", true], ["Carteira: somente leitura", true], ["Trade", false], ["Saque", false]] },
];

/** Serviços da etapa IA e mercado. Links de 11/2026, abrem em aba nova; o site pode redirecionar. */
const SERVICES: { name: string; secret: SecretName; label: string; required: boolean; cost: string; use: string; links: [string, string][] }[] = [
  { name: "Claude", secret: "anthropic_api_key", label: "Chave da API do Claude", required: true, cost: "pago por uso",
    use: "Escreve o veredito e o manual do analista. Para no limite mensal das Preferências.",
    links: [["Abrir chaves do Claude", "https://console.anthropic.com/settings/keys"]] },
  { name: "CoinGecko", secret: "coingecko_key", label: "Chave da CoinGecko", required: true, cost: "plano gratuito",
    use: "Preço histórico, dominância do BTC e temporada de altcoins.",
    links: [["Abrir CoinGecko", "https://www.coingecko.com/en/developers/dashboard"]] },
  { name: "Coinalyze", secret: "coinalyze_key", label: "Chave da Coinalyze", required: true, cost: "plano gratuito",
    use: "Juros de financiamento e posições em aberto dos derivativos.", links: [["Abrir Coinalyze", "https://coinalyze.net/account/api/"]] },
  { name: "FRED", secret: "fred_key", label: "Chave da FRED", required: true, cost: "gratuita",
    use: "Índice do dólar (DXY) e juros dos EUA.", links: [["Abrir FRED", "https://fredaccount.stlouisfed.org/apikeys"]] },
  { name: "Hugging Face", secret: "hf_token", label: "Token de leitura do Hugging Face", required: true, cost: "gratuito",
    use: "Libera o modelo EmbeddingGemma. Aceite a licença do modelo antes de criar o token.",
    links: [["Abrir a licença do modelo", "https://huggingface.co/google/embeddinggemma-300m"], ["Abrir tokens", "https://huggingface.co/settings/tokens"]] },
  { name: "CoinGlass", secret: "coinglass_key", label: "Chave da CoinGlass", required: false, cost: "paga",
    use: "Fluxo dos ETFs com mais detalhe. Ligue só depois de medir o custo da primeira semana.",
    links: [["Ver planos", "https://www.coinglass.com/pricing"]] },
];

const KEY_STATUS: Record<KeyCheck["status"], [string, string]> = {
  ok: ["text-alta", "ok"], unsafe: ["text-sair", "insegura"], unconfirmed: ["text-reduzir", "falta confirmar"],
  missing: ["text-texto-2", "sem chave"], error: ["text-reduzir", "não verificou"],
};
const IMPORT_CMD = "cd ~/quilate/backend && uv run quilate importar --meses 12";
const PLAYBOOK_CMD = "cd ~/quilate/backend && uv run quilate manual-inicial";

const card = "min-w-0 rounded-[18px] border border-borda bg-painel";
const input = "min-h-11 rounded-xl border border-[#262c3d] bg-[#0a0c12] px-3.5 text-sm text-texto outline-offset-2 outline-violeta focus-visible:outline-2";
const button = "min-h-11 rounded-xl bg-texto px-4 text-sm font-semibold text-fundo outline-offset-2 outline-violeta transition-colors hover:bg-white focus-visible:outline-2 disabled:opacity-50";
const ghost = "inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#2b3247] px-4 text-sm text-texto no-underline outline-offset-2 outline-violeta transition-colors hover:bg-[#161a26] focus-visible:outline-2 disabled:opacity-50";
const chip = (kind: "done" | "part" | "todo" | "opt") => `shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${{
  done: "bg-manter/15 text-[#5eead4]", part: "bg-reduzir/15 text-[#fcd34d]", todo: "bg-sair/12 text-[#fda4af]", opt: "bg-[#131722] text-texto-2" }[kind]}`;

const message = (err: unknown) => (err instanceof ApiError || err instanceof Error ? err.message : "falha desconhecida");

/** Estado de cada etapa a partir do checklist do backend. */
function stageStatus(steps: string[], byId: Record<string, SetupStep>) {
  const items = steps.map((id) => byId[id]).filter(Boolean);
  const done = items.filter((s) => s.done).length;
  if (!items.length) return { items, done, label: "Opcional", kind: "opt" as const };
  if (done === items.length) return { items, done, label: "Concluída", kind: "done" as const };
  return { items, done, label: `${done} de ${items.length}`, kind: done ? "part" as const : "todo" as const };
}

/** Aba Configuração: assistente em 6 etapas com o checklist da instalação na trilha lateral. */
export function Configuracao() {
  const [version, setVersion] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const { data, error } = useLiveQuery(getSetup, version);
  if (!data) return <LoadState what="a configuração" error={error} />;
  const refresh = () => setVersion((v) => v + 1);

  const byId = Object.fromEntries(data.checklist.map((s) => [s.id, s]));
  const statuses = STAGES.map((s) => stageStatus(s.steps, byId));
  // sem escolha do usuário, abre a primeira etapa com pendência
  const firstPending = statuses.findIndex((s) => s.kind === "todo" || s.kind === "part");
  const current = picked ?? (firstPending < 0 ? STAGES.length - 1 : firstPending);
  const stage = STAGES[current];
  const done = data.checklist.filter((s) => s.done).length;
  const pct = Math.round((done / data.checklist.length) * 100);
  const go = (i: number) => setPicked(Math.min(STAGES.length - 1, Math.max(0, i)));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-3xl flex-col gap-1.5">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">Configuração</h1>
          <p className="m-0 text-sm leading-relaxed text-texto-2">
            Seis etapas ligam o sistema às suas corretoras, ao grupo do Telegram e à IA. Pare e volte quando quiser: o que já foi
            gravado fica salvo.
          </p>
        </div>
        {data.mode === "setup"
          ? <p role="status" className="m-0 flex min-h-11 max-w-xl items-center gap-2.5 rounded-xl border border-reduzir/30 bg-reduzir/8 px-4 py-2 text-[13px] text-[#fcd34d]">
              <span aria-hidden="true" className="relative inline-flex size-2 shrink-0"><span className="ping absolute inset-0 rounded-full bg-reduzir" /><span className="relative size-2 rounded-full bg-reduzir" /></span>
              <span>Servidor no modo instalação: só esta página e a API funcionam.
                {data.missing_for_serve.length ? ` Falta: ${data.missing_for_serve.join(", ")}.` : " Tudo gravado: reinicie o servidor em Primeira carga."}</span>
            </p>
          : <p role="status" className="m-0 flex min-h-11 items-center gap-2.5 rounded-xl border border-alta/30 bg-alta/8 px-4 text-[13px] text-[#6ee7b7]">
              <span aria-hidden="true" className="size-2 rounded-full bg-alta" />Servidor completo no ar.
            </p>}
      </header>
      <StaleError error={error} />

      <section aria-label="Segurança" className={`${card} fade-in flex flex-wrap items-center gap-4 px-5 py-4`}>
        <span aria-hidden="true" className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-manter/10 text-manter">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z" /><path d="m9 12 2 2 4-4.5" /></svg>
        </span>
        <div className="flex min-w-[240px] flex-1 flex-col gap-0.5">
          <strong className="text-[15px] font-semibold">Suas chaves ficam só neste Mac</strong>
          <span className="text-[13px] text-texto-2">O sistema lê saldos e operações. Ele nunca compra, vende, saca nem transfere.</span>
        </div>
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0 text-xs text-[#c3c9d6]">
          {["Gravadas no Keychain do macOS", "Nunca voltam para a tela", "Chave com trade ou saque é recusada"].map((t) =>
            <li key={t} className="rounded-full bg-[#131722] px-3 py-1.5">{t}</li>)}
        </ul>
      </section>

      <div className="flex flex-wrap items-start gap-6">
        <nav aria-label="Etapas da configuração" className={`${card} fade-in flex max-w-full flex-[1_1_280px] flex-col gap-4 p-5 lg:sticky lg:top-6`}>
          <div className="flex items-center gap-4">
            <svg width="60" height="60" viewBox="0 0 36 36" aria-hidden="true" className="-rotate-90 shrink-0">
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1c2130" strokeWidth="3.2" />
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--color-violeta)" strokeWidth="3.2" strokeLinecap="round"
                pathLength={100} strokeDasharray={`${pct} 100`} className="transition-[stroke-dasharray] duration-700 ease-out" />
            </svg>
            <div className="flex flex-col">
              <span className="font-mono text-[22px] font-semibold">{done} de {data.checklist.length}</span>
              <span className="text-[13px] text-texto-2">passos concluídos</span>
            </div>
          </div>
          <ol className="m-0 flex list-none flex-col gap-1 p-0">
            {STAGES.map((s, i) => {
              const st = statuses[i], on = i === current;
              return (
                <li key={s.title}>
                  <button type="button" aria-current={on ? "step" : undefined} onClick={() => go(i)}
                    className={`flex min-h-14 w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left outline-offset-2 outline-violeta transition-colors focus-visible:outline-2 ${
                      on ? "border-[#3b3366] bg-[#151226]" : "border-transparent hover:bg-[#121621]"}`}>
                    <span aria-hidden="true" className={`inline-flex size-[30px] shrink-0 items-center justify-center rounded-full font-mono text-[13px] font-semibold transition-colors ${
                      st.kind === "done" ? "bg-manter text-fundo" : on ? "bg-violeta text-fundo" : "bg-[#171b27] text-[#c3c9d6]"}`}>
                      {st.kind === "done" ? "✓" : i + 1}
                    </span>
                    <span className="flex min-w-0 grow flex-col">
                      <span data-stage-title className="text-sm font-semibold text-texto">{s.title}</span>
                      <span className="text-xs text-texto-2">{s.sub}</span>
                    </span>
                    <span className={chip(st.kind)}>{st.label}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <section aria-labelledby="etapa" className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <div key={`h${current}`} className={`${card} slide-in flex flex-col gap-3 p-6`}>
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-violeta">Etapa {current + 1} de {STAGES.length}</span>
            <h2 id="etapa" className="m-0 text-[22px] font-semibold">{stage.heading}</h2>
            <p className="m-0 max-w-3xl text-sm leading-relaxed text-[#c3c9d6]">{stage.why}</p>
            <span className="self-start rounded-full bg-[#131722] px-3 py-1.5 text-xs text-texto-2">
              Você vai precisar de: <b className="font-medium text-texto">{stage.needs}</b>
            </span>
            {statuses[current].items.length > 0 && (
              <ul aria-label="Nesta etapa" className="m-0 mt-1 flex list-none flex-col gap-2 p-0">
                {statuses[current].items.map((s) => (
                  <li key={s.id} className="flex items-start gap-2.5 text-sm">
                    <span aria-hidden="true" className={`mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border text-[11px] transition-colors ${
                      s.done ? "border-manter bg-manter/15 text-manter" : "border-[#2b3247] text-transparent"}`}>✓</span>
                    <span className="flex flex-col">
                      <span className={s.done ? "text-texto-2" : "font-medium"}>{s.label}<span className="sr-only">{s.done ? ", concluído" : ", pendente"}</span></span>
                      {!s.done && <span className="text-[13px] text-texto-2">{s.how}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div key={`c${current}`} className="slide-in flex flex-col gap-5">
            {current === 0 && <StageYou config={data.config} onSaved={refresh} />}
            {current === 1 && <StageExchanges setup={data} onChange={refresh} />}
            {current === 2 && <StageTelegram setup={data} onChange={refresh} />}
            {current === 3 && <StageServices setup={data} onChange={refresh} />}
            {current === 4 && <StageFirstLoad setup={data} onDone={refresh} />}
            {current === 5 && <StagePrefs config={data.config} onSaved={refresh} />}
          </div>

          <div className="flex flex-wrap justify-between gap-3">
            <button type="button" onClick={() => go(current - 1)} disabled={current === 0} className={ghost}>
              <span aria-hidden="true">←</span>Etapa anterior
            </button>
            <button type="button" onClick={() => go(current + 1)} disabled={current === STAGES.length - 1}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-violeta px-5 text-sm font-semibold text-fundo outline-offset-2 outline-violeta transition-colors hover:bg-[#c4b5fd] focus-visible:outline-2 disabled:opacity-50">
              Próxima etapa<span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

/** Link para a página de chaves do serviço, em aba nova. O usuário cria a chave lá e cola aqui. */
function Open({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`${ghost} w-fit`}>
      {children}
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8" /></svg>
    </a>
  );
}

function Step({ n, title, children }: { n: number | string; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-4">
      <span aria-hidden="true" className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-full bg-[#171b27] font-mono text-[13px] font-semibold">{n}</span>
      <div className="flex min-w-0 grow flex-col gap-2.5">
        <h3 className="m-0 text-[15px] font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}

const hint = "m-0 text-[13px] leading-relaxed text-texto-2";

/** Um segredo: campo de senha que vai para o Keychain e volta vazio. A tela só sabe se está gravado. */
function SecretField({ name, label, saved, onChange, optional = false }:
  { name: SecretName; label: string; saved: boolean; onChange: (kind: "saved" | "removed") => void; optional?: boolean }) {
  const [value, setValue] = useState("");
  const [state, setState] = useState<{ busy?: boolean; ok?: boolean; error?: string }>({});

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim()) return setState({ error: "Cole o valor antes de gravar." });
    setState({ busy: true });
    try {
      await saveSecret(name, value.trim());
      setValue("");
      setState({ ok: true });
      onChange("saved");
    } catch (err) {
      setState({ error: `Não gravou (${message(err)}).` });
    }
  }

  async function remove() {
    setState({ busy: true });
    try { await deleteSecret(name); setState({}); onChange("removed"); } catch (err) { setState({ error: `Não apagou (${message(err)}).` }); }
  }

  return (
    <form aria-label={label} onSubmit={submit} className="flex min-w-0 flex-col gap-1.5">
      <label className="flex flex-col gap-1.5 text-[13px] text-texto-2">
        <span className="flex items-center justify-between gap-2">
          {label}
          <span className={`text-xs font-medium ${saved ? "text-manter" : optional ? "text-texto-2" : "text-reduzir"}`}>
            {saved ? "gravado no Keychain" : optional ? "opcional" : "falta"}
          </span>
        </span>
        <span className="flex gap-2">
          <input type="password" autoComplete="off" spellCheck={false} value={value} onChange={(e) => { setValue(e.target.value); setState({}); }}
            placeholder={saved ? "cole um valor novo para trocar" : "cole aqui"} className={`${input} min-w-0 grow font-mono`} />
          <button type="submit" disabled={state.busy} className={button}>Gravar</button>
        </span>
      </label>
      {saved && <button type="button" disabled={state.busy} onClick={remove} className="self-start text-xs text-texto-2 underline-offset-2 hover:underline">Apagar</button>}
      {state.ok && <p role="status" className="m-0 text-sm text-alta">Gravado. O valor não fica na tela.</p>}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </form>
  );
}

function StageYou({ config, onSaved }: { config: SetupConfig; onSaved: () => void }) {
  const [name, setName] = useState(config.owner_name);
  const [user, setUser] = useState(config.analyst_username);
  const [display, setDisplay] = useState(config.analyst_name);
  const [state, setState] = useState<{ busy?: boolean; ok?: string; error?: string }>({});

  async function submit(e: FormEvent) {
    e.preventDefault();
    const changes: Partial<SetupConfig> = {};
    if (name.trim() !== config.owner_name) changes.owner_name = name.trim();
    if (user.trim() !== config.analyst_username) changes.analyst_username = user.trim();
    if (display.trim() !== config.analyst_name) changes.analyst_name = display.trim();
    if (!Object.keys(changes).length) return setState({ ok: "Nada mudou." });
    setState({ busy: true });
    try {
      const r = await saveConfig(changes);
      setState({ ok: r.restart_required ? "Gravado. Vale depois de reiniciar o servidor." : "Gravado e já em uso." });
      onSaved();
    } catch (err) {
      setState({ error: `Não gravou (${message(err)}).` });
    }
  }

  return (
    <form aria-label="Seus dados" onSubmit={submit} className={`${card} flex flex-col gap-5 p-6`}>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="flex flex-col gap-2 text-[13px] text-texto-2">
          <span className="font-medium text-texto">Seu nome</span>
          <input type="text" value={name} onChange={(e) => { setName(e.target.value); setState({}); }} placeholder="Como o painel deve chamar você" className={input} />
          <span>Aparece só na tela. CPF e documentos não são pedidos: o sistema não faz cadastro em corretora.</span>
        </label>
        <label className="flex flex-col gap-2 text-[13px] text-texto-2">
          <span className="flex justify-between font-medium text-texto">Usuário do analista no Telegram
            {config.analyst_username && <span className="text-xs text-manter">gravado</span>}</span>
          <span className="flex min-h-11 items-center rounded-xl border border-[#262c3d] bg-[#0a0c12] focus-within:outline-2 focus-within:outline-violeta">
            <span aria-hidden="true" className="pl-3.5 pr-1 text-[#8a93a6]">@</span>
            <input type="text" value={user} onChange={(e) => { setUser(e.target.value); setState({}); }} placeholder="usuario_do_analista"
              className="h-11 min-w-0 grow border-0 bg-transparent pr-3.5 text-sm text-texto outline-none" />
          </span>
          <span>Só as mensagens dessa pessoa contam como análise. As dos outros membros viram contexto.</span>
        </label>
        <label className="flex flex-col gap-2 text-[13px] text-texto-2">
          <span className="font-medium text-texto">Nome de exibição do analista</span>
          <input type="text" value={display} onChange={(e) => { setDisplay(e.target.value); setState({}); }} placeholder="Ex.: Ana" maxLength={80} className={input} />
          <span>O nome aparece no lugar de “o analista” nas telas e nos avisos. Pode ficar em branco.</span>
        </label>
      </div>
      <div><button type="submit" disabled={state.busy} className={button}>Gravar dados</button></div>
      {state.ok && <p role="status" className="m-0 text-sm text-alta">{state.ok}</p>}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </form>
  );
}

function StageExchanges({ setup, onChange }: { setup: Setup; onChange: () => void }) {
  const [selected, setSelected] = useState<Exchange>("binance");
  const [checks, setChecks] = useState<Partial<Record<Exchange, { busy?: boolean; result?: KeyCheck; error?: string }>>>({});
  const [confirmState, setConfirmState] = useState<{ busy?: boolean; error?: string }>({});
  const ex = EXCHANGES.find((e) => e.id === selected)!;
  const name = exchangeName(ex.id);
  const hasPair = (id: Exchange) => setup.secrets[`${id}_key`] && setup.secrets[`${id}_secret`];
  const confirmed = (id: Exchange) => setup.config.confirmed_read_only.includes(id);
  const tileStatus = (e: typeof EXCHANGES[number]) =>
    !hasPair(e.id) ? ["Falta", "todo"] as const : !e.verified && !confirmed(e.id) ? ["Falta confirmar", "part"] as const : ["Gravada", "done"] as const;
  const check = checks[ex.id] ?? {};

  /** Assim que o par chave e segredo está gravado, pergunta à corretora o que a chave pode fazer. */
  async function afterSecret(saved: SecretName, kind: "saved" | "removed") {
    onChange();
    const id = ex.id;
    if (kind === "removed") return setChecks((c) => ({ ...c, [id]: {} }));
    const other = saved === `${id}_key` ? setup.secrets[`${id}_secret`] : setup.secrets[`${id}_key`];
    if (!other) return;
    setChecks((c) => ({ ...c, [id]: { busy: true } }));
    try {
      const r = await checkKeys();
      setChecks((c) => ({ ...c, [id]: { result: r.exchanges.find((x) => x.exchange === id) } }));
    } catch (err) {
      setChecks((c) => ({ ...c, [id]: { error: `Não consegui checar (${message(err)}).` } }));
    }
  }

  async function toggle(checked: boolean) {
    setConfirmState({ busy: true });
    const list = setup.config.confirmed_read_only.filter((e) => e !== ex.id);
    try {
      await saveConfig({ confirmed_read_only: checked ? [...list, ex.id] : list });
      setConfirmState({});
      onChange();
    } catch (err) {
      setConfirmState({ error: `Não gravou (${message(err)}).` });
    }
  }

  return (
    <>
      <div role="tablist" aria-label="Corretoras" className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,170px),1fr))] gap-3">
        {EXCHANGES.map((e) => {
          const [label, kind] = tileStatus(e), on = e.id === selected;
          return (
            <button key={e.id} type="button" role="tab" aria-selected={on} onClick={() => setSelected(e.id)}
              className={`flex min-h-[76px] flex-col gap-2 rounded-2xl border px-4 py-3.5 text-left outline-offset-2 outline-violeta transition-[border-color,background-color,transform] duration-200 hover:-translate-y-px focus-visible:outline-2 ${
                on ? "border-violeta bg-[#151226]" : "border-borda bg-painel hover:border-[#2b3247]"}`}>
              <span className="flex items-center justify-between gap-2">
                <span className="text-[15px] font-semibold">{exchangeName(e.id)}</span>
                <span className={chip(kind)}>{label}</span>
              </span>
              <span className="text-xs text-texto-2">{e.verified ? "Permissão checada pela API" : "Confirmação manual"}</span>
            </button>
          );
        })}
      </div>

      <div role="tabpanel" aria-label={name} key={ex.id} className={`${card} slide-in flex flex-col gap-6 p-6`}>
        <Step n={1} title={`Abra a página de chaves da ${name}`}>
          <p className={hint}>Entre com a sua senha e o código de dois fatores. No menu: {ex.where}.</p>
          <Open href={ex.url}>Abrir chaves de API da {name}</Open>
          {ex.howto && (
            <ol aria-label={`Passo a passo na ${name}`} className="m-0 mt-1 flex list-decimal flex-col gap-2 rounded-xl bg-[#0a0c12] py-3.5 pl-9 pr-4 text-[13px] leading-relaxed text-[#c3c9d6] marker:font-mono marker:text-violeta">
              {ex.howto.map((t) => <li key={t} className="pl-1">{t}</li>)}
            </ol>
          )}
        </Step>
        <Step n={2} title="Crie a chave só com leitura">
          <p className={hint}>Marque só o que está ligado abaixo. Se a chave puder operar ou sacar, o servidor recusa e não sobe.</p>
          <ul aria-label="Permissões da chave" className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-2 p-0">
            {ex.perms.map(([label, on]) => (
              <li key={label} className={`flex min-h-11 items-center gap-2.5 rounded-xl border px-3.5 text-[13px] ${
                on ? "border-manter/30 bg-manter/8 text-[#5eead4]" : "border-borda bg-[#0a0c12] text-[#8a93a6]"}`}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={on ? "M5 12.5l4.5 4.5L19 7.5" : "M6 6l12 12M18 6 6 18"} /></svg>
                <span className="grow">{label}</span>
                <span className="text-xs font-semibold">{on ? "Ligar" : "Desligado"}</span>
              </li>
            ))}
          </ul>
        </Step>
        <Step n={3} title="Cole a chave e o segredo">
          <div className="grid gap-3 lg:grid-cols-2">
            <SecretField name={`${ex.id}_key`} label={`Chave da API da ${name}`} saved={setup.secrets[`${ex.id}_key`]}
              onChange={(kind) => afterSecret(`${ex.id}_key`, kind)} />
            <SecretField name={`${ex.id}_secret`} label={`Segredo da API da ${name}`} saved={setup.secrets[`${ex.id}_secret`]}
              onChange={(kind) => afterSecret(`${ex.id}_secret`, kind)} />
          </div>
          {!check.busy && !check.result && !check.error && <p className={hint}>Com o par gravado, a checagem roda sozinha.</p>}
          {check.busy && <p role="status" className="m-0 text-sm text-texto-2">Checando a chave na {name}…</p>}
          {check.result && (
            <p role="status" className={`m-0 text-sm ${KEY_STATUS[check.result.status][0]}`}>
              Checagem: {KEY_STATUS[check.result.status][1]}. {check.result.detail}.
            </p>
          )}
          {check.error && <p role="alert" className="m-0 text-sm text-sair">{check.error}</p>}
          {!ex.verified && (
            <label className="flex items-start gap-3 rounded-xl border border-reduzir/30 bg-reduzir/6 p-3.5 text-[13px] leading-relaxed">
              <input type="checkbox" checked={confirmed(ex.id)} disabled={confirmState.busy} onChange={(e) => toggle(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-[#a78bfa]" />
              <span><b className="font-semibold">Confirmação manual.</b> Conferi no site da {name} que esta chave é somente leitura, sem trade, saque nem transferência.</span>
            </label>
          )}
          {confirmState.error && <p role="alert" className="m-0 text-sm text-sair">{confirmState.error}</p>}
        </Step>
      </div>
      <KeyCheckPanel />
    </>
  );
}

function KeyCheckPanel() {
  const [state, setState] = useState<{ busy?: boolean; result?: KeyCheck[]; safe?: boolean; error?: string }>({});

  async function run() {
    setState({ busy: true });
    try {
      const r = await checkKeys();
      setState({ result: r.exchanges, safe: r.safe });
    } catch (err) {
      setState({ error: `Não consegui checar (${message(err)}).` });
    }
  }

  return (
    <div className={`${card} flex flex-col gap-3 p-5`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="m-0 text-sm font-semibold">Checar as 4 corretoras</h3>
          <p className={hint}>Pergunta a cada corretora o que a chave pode fazer. Chave com trade ou saque impede o servidor de subir.</p>
        </div>
        <button type="button" onClick={run} disabled={state.busy} className={button}>Checar chaves</button>
      </div>
      {state.result && (
        <ul aria-label="Resultado da checagem" className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
          {state.result.map((r) => (
            <li key={r.exchange} className="fade-in flex flex-wrap gap-x-3 rounded-lg bg-[#0a0c12] px-3 py-2">
              <span className="w-20 font-medium">{exchangeName(r.exchange)}</span>
              <span className={KEY_STATUS[r.status][0]}>{KEY_STATUS[r.status][1]}</span>
              <span className="text-texto-2">{r.detail}</span>
            </li>
          ))}
        </ul>
      )}
      {state.result && !state.safe && <p role="alert" className="m-0 text-sm text-sair">Há chave insegura ou sem confirmação: o servidor completo não sobe até corrigir.</p>}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </div>
  );
}

function StageTelegram({ setup, onChange }: { setup: Setup; onChange: () => void }) {
  const s = setup.secrets;
  return (
    <ol className="m-0 flex list-none flex-col gap-4 p-0">
      <li className={`${card} flex flex-col gap-4 p-6`}>
        <Step n="A" title="Aplicativo do Telegram">
          <p className={hint}>Em API development tools, crie um aplicativo com qualquer nome. Copie o api_id e o api_hash. O id do grupo é negativo e começa com -100.</p>
          <Open href="https://my.telegram.org/apps">Abrir my.telegram.org</Open>
          <div className="grid gap-3 lg:grid-cols-3">
            <SecretField name="telegram_api_id" label="api_id do aplicativo" saved={s.telegram_api_id} onChange={onChange} />
            <SecretField name="telegram_api_hash" label="api_hash do aplicativo" saved={s.telegram_api_hash} onChange={onChange} />
            <SecretField name="telegram_group_id" label="id do grupo" saved={s.telegram_group_id} onChange={onChange} />
          </div>
        </Step>
      </li>
      <li className={`${card} flex flex-col gap-4 p-6`}>
        <Step n="B" title="Login da sua conta">
          <p className={hint}>O sistema lê o grupo com a sua conta, como um leitor. Ele nunca escreve no grupo. A sessão fica no Keychain.</p>
          <TelegramLogin ready={s.telegram_api_id && s.telegram_api_hash} saved={s.telegram_session} onChange={onChange} />
        </Step>
      </li>
      <li className={`${card} flex flex-col gap-4 p-6`}>
        <Step n="C" title="Bot dos avisos">
          <p className={hint}>Crie o bot com /newbot, mande um "oi" para ele e pegue o id do seu chat (ex.: pelo @userinfobot). O bot fala só com você, quando um veredito muda.</p>
          <Open href="https://t.me/BotFather">Abrir o BotFather</Open>
          <div className="grid gap-3 lg:grid-cols-2">
            <SecretField name="telegram_bot_token" label="Token do bot" saved={s.telegram_bot_token} onChange={onChange} />
            <SecretField name="telegram_chat_id" label="Chat id do seu chat com o bot" saved={s.telegram_chat_id} onChange={onChange} />
          </div>
        </Step>
      </li>
    </ol>
  );
}

function TelegramLogin({ ready, saved, onChange }: { ready: boolean; saved: boolean; onChange: () => void }) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"phone" | "code" | "password">("phone");
  const [state, setState] = useState<{ busy?: boolean; ok?: string; error?: string }>({});
  const order = ["phone", "code", "password"] as const;

  async function go(e: FormEvent) {
    e.preventDefault();
    setState({ busy: true });
    try {
      if (step === "phone") {
        await telegramSendCode(phone.trim());
        setStep("code");
        setState({ ok: "Código enviado. Veja o Telegram." });
      } else {
        const r = await telegramSignIn(code.trim(), step === "password" ? password : undefined);
        if (r.needs_password) { setStep("password"); setState({ ok: "A conta tem senha de duas etapas. Informe a senha." }); return; }
        setStep("phone"); setPhone(""); setCode(""); setPassword("");
        setState({ ok: `Sessão de @${r.username ?? "você"} gravada no Keychain.` });
        onChange();
      }
    } catch (err) {
      setState({ error: `O Telegram recusou (${message(err)}).` });
    }
  }

  return (
    <form aria-label="Login do Telegram" onSubmit={go} className="flex flex-col gap-3">
      <p className={`m-0 text-xs font-medium ${saved ? "text-manter" : "text-reduzir"}`}>{saved ? "Sessão gravada no Keychain. Faça o login de novo só se ela expirar." : "Sem sessão."}</p>
      <ol aria-label="Etapas do login" className="m-0 flex list-none flex-wrap items-center gap-2 p-0 text-xs text-texto-2">
        {(["1 Telefone", "2 Código", "3 Senha de duas etapas"] as const).map((label, i) => (
          <li key={label} className={`rounded-full px-2.5 py-1 transition-colors ${order.indexOf(step) === i ? "bg-violeta/15 font-semibold text-[#ddd6fe]" : "bg-[#131722]"}`}>{label}</li>
        ))}
      </ol>
      <div className="flex flex-wrap items-end gap-3">
        {step === "phone" && (
          <label className="flex min-w-[220px] flex-1 flex-col gap-1.5 text-[13px] text-texto-2">Telefone com DDI
            <input type="tel" autoComplete="off" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+55 11 99999 0000" className={input} disabled={!ready} /></label>
        )}
        {step === "code" && (
          <label className="flex min-w-[220px] flex-1 flex-col gap-1.5 text-[13px] text-texto-2">Código recebido no Telegram
            <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} className={input} /></label>
        )}
        {step === "password" && (
          <label className="flex min-w-[220px] flex-1 flex-col gap-1.5 text-[13px] text-texto-2">Senha de duas etapas
            <input type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} className={input} /></label>
        )}
        <button type="submit" disabled={state.busy || !ready} className={button}>
          {step === "phone" ? "Enviar código" : step === "code" ? "Confirmar código" : "Entrar"}</button>
      </div>
      {!ready && <p className={hint}>Grave o api_id e o api_hash no passo A antes.</p>}
      {state.ok && <p role="status" className="m-0 text-sm text-alta">{state.ok}</p>}
      {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
    </form>
  );
}

function StageServices({ setup, onChange }: { setup: Setup; onChange: () => void }) {
  return (
    <ul aria-label="Serviços" className="m-0 flex list-none flex-col gap-3 p-0">
      {SERVICES.map((sv) => (
        <li key={sv.name} className={`${card} flex flex-col gap-4 p-5 lg:flex-row lg:items-start`}>
          <div className="flex min-w-0 flex-col gap-2 lg:flex-[1_1_0]">
            <span className="flex flex-wrap items-center gap-2">
              <h3 className="m-0 text-[15px] font-semibold">{sv.name}</h3>
              <span className={sv.required ? "rounded-full bg-violeta/15 px-2 py-0.5 text-[11px] font-semibold text-[#ddd6fe]" : "rounded-full bg-[#131722] px-2 py-0.5 text-[11px] font-semibold text-texto-2"}>
                {sv.required ? "obrigatória" : "opcional"}</span>
              <span className="rounded-full bg-[#131722] px-2 py-0.5 text-[11px] text-texto-2">{sv.cost}</span>
            </span>
            <p className={hint}>{sv.use}</p>
            <div className="flex flex-wrap gap-2">{sv.links.map(([label, href]) => <Open key={href} href={href}>{label}</Open>)}</div>
          </div>
          <div className="lg:flex-[1_1_0]">
            <SecretField name={sv.secret} label={sv.label} saved={setup.secrets[sv.secret]} onChange={onChange} optional={!sv.required} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function StageFirstLoad({ setup, onDone }: { setup: Setup; onDone: () => void }) {
  return (
    <ol className="m-0 flex list-none flex-col gap-4 p-0">
      <li><Command n={1} title="Importar o histórico do grupo" tag="no Terminal · demora" cmd={IMPORT_CMD}
        why="Baixa os últimos 12 meses de mensagens. O histórico mais antigo entra depois, sozinho, um lote por hora."
        status={setup.data.messages ? `${setup.data.messages.toLocaleString("pt-BR")} mensagens no banco` : "ainda sem mensagens"} /></li>
      <li><Command n={2} title="Criar o manual inicial do analista" tag="no Terminal · gasta" cost cmd={PLAYBOOK_CMD}
        why="Mostra a estimativa em US$ e só continua se você responder s. É um custo único, fora do limite mensal."
        status={setup.data.playbook ? "manual criado" : "ainda sem manual"} /></li>
      <li><Restart setup={setup} onDone={onDone} /></li>
    </ol>
  );
}

function Command({ n, title, tag, cost = false, why, cmd, status }:
  { n: number; title: string; tag: string; cost?: boolean; why: string; cmd: string; status: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className={`${card} flex flex-col gap-3 p-6`}>
      <Step n={n} title={title}>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded-full px-2.5 py-1 font-semibold ${cost ? "bg-reduzir/15 text-[#fcd34d]" : "bg-[#131722] text-texto-2"}`}>{tag}</span>
          <span className="text-texto-2">{status}</span>
        </span>
        <p className={hint}>{why}</p>
        <div className="flex flex-wrap items-center gap-2">
          <code className="min-w-0 flex-[1_1_320px] overflow-x-auto whitespace-nowrap rounded-xl border border-borda bg-[#0a0c12] px-3.5 py-3 font-mono text-[13px] text-[#c4b5fd]">{cmd}</code>
          <button type="button" className={ghost} onClick={() => navigator.clipboard?.writeText(cmd).then(() => setCopied(true))}>
            {copied ? "Copiado" : "Copiar"}
          </button>
        </div>
      </Step>
    </div>
  );
}

function Restart({ setup, onDone }: { setup: Setup; onDone: () => void }) {
  const [state, setState] = useState<{ busy?: boolean; ok?: boolean; error?: string }>({});
  const blocked = setup.missing_for_serve.length > 0;

  async function run() {
    setState({ busy: true });
    try {
      await restartServer();
      setState({ ok: true });
      setTimeout(onDone, 4000);  // o processo troca de lugar; a próxima consulta já pega o modo novo
    } catch (err) {
      setState({ error: `Não reiniciou (${message(err)}).` });
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-[18px] border border-violeta/35 bg-violeta/6 p-6">
      <Step n={3} title="Reiniciar o servidor completo">
        <p className="m-0 text-[13px] leading-relaxed text-[#c3c9d6]">
          {blocked ? `Liga corretoras, agendador e Telegram. Antes, grave: ${setup.missing_for_serve.join(", ")}.`
            : setup.restart_required ? "Há configuração esperando o reinício." : "Aplica segredos e configuração novos e sobe o servidor completo."}
        </p>
        <div><button type="button" onClick={run} disabled={state.busy || blocked}
          className="min-h-11 rounded-xl bg-violeta px-5 text-sm font-semibold text-fundo outline-offset-2 outline-violeta transition-colors hover:bg-[#c4b5fd] focus-visible:outline-2 disabled:opacity-50">
          Reiniciar o servidor</button></div>
        {state.ok && <p role="status" className="m-0 text-sm text-alta">Reiniciando. A página volta sozinha em alguns segundos.</p>}
        {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
      </Step>
    </div>
  );
}

/** Controles deslizantes. `scale` converte o valor da tela para o do config (10% → 0,1). */
const PREFS: { key: keyof Omit<SetupConfig, "tz" | "data_dir" | "confirmed_read_only" | "owner_name" | "analyst_username" | "analyst_name">;
  label: string; min: number; max: number; step: number; scale: number; fmt: (v: number) => string; help: string; restart?: boolean }[] = [
  { key: "sync_minutes", label: "Atualizar saldos e preços a cada", min: 1, max: 60, step: 1, scale: 1, fmt: (v) => `${v} min`, restart: true,
    help: "Abaixo de 5 minutos a corretora pode limitar as chamadas." },
  { key: "intraday_move", label: "Avisar alta ou queda no dia acima de", min: 1, max: 50, step: 1, scale: 100, fmt: (v) => `${v}%`,
    help: "O bot avisa mesmo sem mudar o veredito quando uma moeda se move mais que isso no dia." },
  { key: "cutoff_hour", label: "Hora limite do ciclo diário", min: 0, max: 23, step: 1, scale: 1, fmt: (v) => `${v}h`,
    help: "Se o analista não postar até essa hora, o ciclo roda sem a análise do dia." },
  { key: "budget_usd", label: "Limite mensal de gasto com IA", min: 5, max: 200, step: 5, scale: 1, fmt: (v) => `US$ ${v}`,
    help: "No limite a IA pausa e o veredito usa só a régua de 7 sinais." },
  { key: "budget_alert_ratio", label: "Alertar gasto de IA a partir de", min: 50, max: 95, step: 5, scale: 100, fmt: (v) => `${v}% do limite`,
    help: "O bot avisa quando o gasto do mês passa dessa fração do limite." },
  { key: "dust_usd", label: "Moeda abaixo de, fora do veredito", min: 0, max: 100, step: 1, scale: 1, fmt: (v) => `US$ ${v}`,
    help: "Saldos pequenos aparecem como poeira na Carteira." },
];

function StagePrefs({ config, onSaved }: { config: SetupConfig; onSaved: () => void }) {
  const shown = (k: typeof PREFS[number]) => Math.round(Number(config[k.key]) * k.scale);
  const [values, setValues] = useState<Record<string, number>>(Object.fromEntries(PREFS.map((p) => [p.key, shown(p)])));
  const [state, setState] = useState<{ busy?: boolean; ok?: string; error?: string }>({});

  async function submit(e: FormEvent) {
    e.preventDefault();
    const changes = Object.fromEntries(PREFS.filter((p) => values[p.key] !== shown(p)).map((p) => [p.key, values[p.key] / p.scale]));
    if (!Object.keys(changes).length) return setState({ ok: "Nada mudou." });
    setState({ busy: true });
    try {
      const r = await saveConfig(changes);
      setState({ ok: r.restart_required ? "Gravado. Vale depois de reiniciar o servidor." : "Gravado e já em uso." });
      onSaved();
    } catch (err) {
      setState({ error: `Não gravou (${message(err)}).` });
    }
  }

  return (
    <form aria-label="Preferências" onSubmit={submit} className={`${card} grid gap-x-8 gap-y-6 p-6 sm:grid-cols-2`}>
      {PREFS.map((p) => (
        <label key={p.key} className="flex flex-col gap-2 text-[13px] text-texto-2">
          <span className="flex justify-between gap-3">
            <span className="font-medium text-texto">{p.label}</span>
            <b className="font-mono font-semibold text-texto">{p.fmt(values[p.key])}</b>
          </span>
          <input type="range" min={p.min} max={p.max} step={p.step} value={values[p.key]} aria-valuetext={p.fmt(values[p.key])}
            onChange={(e) => { setValues({ ...values, [p.key]: Number(e.target.value) }); setState({}); }}
            className="h-7 w-full accent-[#a78bfa]" />
          <span className="leading-relaxed">{p.help}</span>
          {p.restart && <span className="self-start rounded-full bg-reduzir/12 px-2 py-0.5 text-[11px] text-[#fcd34d]">vale depois de reiniciar</span>}
        </label>
      ))}
      <div className="sm:col-span-2 flex flex-col gap-2">
        <div><button type="submit" disabled={state.busy} className={button}>Gravar preferências</button></div>
        {state.ok && <p role="status" className="m-0 text-sm text-alta">{state.ok}</p>}
        {state.error && <p role="alert" className="m-0 text-sm text-sair">{state.error}</p>}
      </div>
    </form>
  );
}
