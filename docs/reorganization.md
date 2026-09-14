# Reorganização estrutural

A reorganização foi feita com uma regra principal: **preservar a interface e o comportamento atual do Veredicta**.

## Frontend

Os arquivos de interface não tiveram seu conteúdo visual alterado. Foram apenas agrupados:

| Antes | Depois |
|---|---|
| `frontend/styles.css` | `frontend/assets/css/styles.css` |
| `frontend/config.js` | `frontend/assets/js/config.js` |
| `frontend/app.js` | `frontend/assets/js/pages/pesquisa.js` |
| `frontend/analises.js` | `frontend/assets/js/pages/historico.js` |
| `frontend/processo.js` | `frontend/assets/js/pages/processo.js` |

Os HTMLs continuam na raiz do frontend para manter as URLs atuais:

- `index.html`
- `historico.html`
- `processo.html`

Os únicos ajustes nos HTMLs foram os caminhos de `src` e `href` dos assets.

## Backend

Os serviços antes concentrados em um único diretório foram separados por domínio:

| Domínio | Diretório |
|---|---|
| IA e evidências | `app/services/analysis/` |
| DataJud | `app/services/datajud/` |
| DJEN/CNJ | `app/services/djen/` |
| Monitoramento | `app/services/monitoring/` |

As rotas HTTP permanecem em `app/routers/`.

## Scripts

| Antes | Depois |
|---|---|
| `run_djen_value_probe.py` | `scripts/djen/probe.py` |
| `run_djen_value_persist_once.py` | `scripts/djen/persist_once.py` |
| `run_process_watch_once.py` | `scripts/monitoring/run_once.py` |
| `run_process_watch_scheduler.py` | `scripts/monitoring/scheduler.py` |

## Banco

`sql/` foi renomeado para `database/`, deixando explícito que o diretório documenta a estrutura de persistência.

## Arquivos removidos do pacote reorganizado

O pacote de entrega não inclui:

- `.git/`;
- `.venv/`;
- `__pycache__/`;
- arquivos compilados `.pyc`;
- bancos locais e caches.

Esses itens não pertencem ao código-fonte distribuível e eram responsáveis pela maior parte do tamanho do arquivo original.

## Repositório de GitHub Pages

`veredicta-pages` continua existindo como espelho de publicação, mas agora usa a mesma estrutura de `assets/` do frontend canônico. O script `tools/sync-pages.ps1` sincroniza os arquivos sem tocar no `.git` do repositório de páginas.
