# Como contribuir com o Quilate

[English](CONTRIBUTING.md)

Obrigado pelo interesse. Issues e pull requests são bem-vindos, em português ou inglês, de qualquer pessoa. Siga o [Código de Conduta](CODE_OF_CONDUCT.md).

## Antes de começar

- Leia o [README](README.pt-BR.md) e o [docs/architecture.md](docs/architecture.md), que está em inglês.
- Para um bug ou uma ideia, abra primeiro uma issue com os modelos. Para uma correção pequena, basta o pull request.
- Para uma falha de segurança, não abra issue pública. Siga o [SECURITY.md](SECURITY.md).
- Nunca coloque chave, token, senha, id de chat, usuário ou dado de carteira real em issue, commit, teste ou captura de tela. Use valores inventados.

## Preparar o ambiente

O Quilate tem três partes. Você só precisa preparar a que vai mudar.

### Dashboard (`frontend/`)

Node 22.12 ou mais novo.

```sh
cd frontend
npm ci
npm run dev        # http://127.0.0.1:5173, com proxy de /api e /ws para 127.0.0.1:8000
npm test           # vitest
npm run build      # confere os tipos e gera backend/quilate/api/static
```

Abra <http://127.0.0.1:5173/?demo=1> para trabalhar com dados fictícios, sem backend.

### Backend (`backend/`)

Um Mac com Apple Silicon, o [uv](https://docs.astral.sh/uv/) e o Python 3.12 do Homebrew. O Python que o uv baixa sozinho não carrega o `sqlite-vec`.

```sh
brew install python@3.12
cd backend
uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"
uv run pytest -q                      # sem rede, sem Keychain, sem baixar modelo
uv run pytest -q ../scripts/tests
uv run ruff check . ../scripts
```

Os testes não precisam de segredo. Para rodar o sistema de verdade, veja o [docs/install.md](docs/install.md).

### App do notch (`notch/`)

macOS 15 ou mais novo e Swift 6 (Xcode ou Command Line Tools).

```sh
cd notch
swift test
./build.sh && open Quilate.app
./demo.sh          # backend de mentira em 127.0.0.1:8000
```

## Fluxo de trabalho

1. Faça um fork do repositório e crie uma branch a partir da `main`.
2. Escreva primeiro um teste que falha. Depois escreva o menor código que faz o teste passar.
3. Rode os testes do lado que você mudou.
4. Abra um pull request para a `main` e preencha o modelo.

Cada pull request precisa de:

- O check `ci-ok` verde. O CI roda só os trabalhos das pastas que você mudou, mais uma varredura de segredos.
- A aprovação de um dos dois mantenedores.
- Teste para comportamento novo.
- Nenhum segredo e nenhum dado pessoal.
- Documentação atualizada quando muda comportamento, configuração ou campo da API. Se mudar campo de `/api/overview`, `/api/verdicts` ou `/api/costs`, ajuste o app do notch no mesmo pull request ([docs/api.md](docs/api.md)).

Os pull requests entram por squash ou rebase. Alguns tipos de mudança não entram:

- código que envia ordem ou move dinheiro
- código que escreve em grupo do Telegram
- servidor que escuta fora de `127.0.0.1`
- chamada de IA que não passa por `backend/quilate/ai/claude.py`

A lista completa das regras fixas está no [AGENTS.md](AGENTS.md).

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/pt-br/), em português ou inglês:

```
feat: add Kraken read-only sync
fix: corrige preço médio com taxa em BNB
docs: explain trigger_topic
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`. Uma mudança por commit. Assunto com até 72 caracteres, sem ponto final.

Um aparte, fora da regra: um commit chamado "ajustes" às 23h59 de sexta não conta como mensagem.

## Estilo de código

- Identificadores em inglês. A interface, os comandos da CLI, os comentários e as docstrings que já existem estão em português. Comentário novo pode ser em português ou inglês. Texto para o usuário continua em português até a interface ser traduzida.
- Python: tipos nas funções públicas, dataclasses `frozen=True` para configuração e resultados, `ruff` limpo.
- TypeScript: modo strict, um componente por arquivo, com o teste ao lado.
- Dependência nova só quando a biblioteca padrão e as já instaladas não resolvem. As versões ficam travadas em `uv.lock` e `package-lock.json`.

As regras de cada lado estão em [backend/AGENTS.md](backend/AGENTS.md), [frontend/AGENTS.md](frontend/AGENTS.md) e [notch/AGENTS.md](notch/AGENTS.md), em inglês.

## Opcional: o gancho contra vazamento

```sh
scripts/install-hooks.sh
```

O script instala os ganchos `pre-commit` e `commit-msg`, que rodam o `scripts/forbidden_terms.py`. Ele procura termos privados de uma lista que só os mantenedores têm, num repositório privado separado. Sem essa lista, ele mostra um aviso e deixa o commit passar. Para a maioria das pessoas, o gancho não faz nada.

## Onde pedir ajuda

Abra uma issue com o modelo "Idea", ou comente na issue em que você está trabalhando. Ainda não há canal de conversa.

Toda contribuição entra sob a [AGPL-3.0-or-later](LICENSE), a mesma licença do projeto. Não há termo de contribuição separado.
