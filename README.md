# Veredicta

Aplicação web de pesquisa processual, análise jurídica assistida por IA, monitoramento e jurimetria.

## Arquitetura atual

- **Frontend:** HTML, CSS e JavaScript estáticos, publicados no GitHub Pages.
- **API:** FastAPI/Python.
- **Banco:** PostgreSQL (produção) e SQLite apenas para desenvolvimento local.
- **Pesquisa processual:** DataJud/CNJ.
- **Publicações e teor oficial:** DJEN / Comunica PJe.
- **IA jurídica:** Gemini, acionada manualmente na primeira análise e automaticamente apenas pelo fluxo de monitoramento já persistido.
- **Monitoramento:** `process_watches`, com debounce por processo antes de uma nova análise automática.

## Estrutura do projeto

```text
veredicta-web/
├── backend/
│   ├── app/
│   │   ├── routers/                 # endpoints HTTP
│   │   ├── services/
│   │   │   ├── analysis/            # IA, evidências e enriquecimento
│   │   │   ├── datajud/             # cliente e proteção DataJud
│   │   │   ├── djen/                # cliente, extração e persistência DJEN
│   │   │   └── monitoring/          # watches e monitoramento automático
│   │   ├── auth.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── settings.py
│   │   └── main.py
│   ├── scripts/
│   │   ├── djen/                    # utilitários manuais DJEN
│   │   └── monitoring/              # utilitários de monitoramento
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── assets/
│   │   ├── css/styles.css
│   │   └── js/
│   │       ├── config.js
│   │       └── pages/
│   │           ├── pesquisa.js
│   │           ├── historico.js
│   │           └── processo.js
│   ├── index.html
│   ├── historico.html
│   └── processo.html
├── database/
│   └── schema.sql
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── legacy/
└── tools/
    └── sync-pages.ps1
```

## Backend local

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

API local: `http://127.0.0.1:8000`
Swagger: `http://127.0.0.1:8000/docs`

## Frontend local

A configuração do frontend fica em `frontend/assets/js/config.js`.

Para desenvolvimento local, aponte `API_BASE_URL` para `http://127.0.0.1:8000` e execute:

```powershell
cd frontend
python -m http.server 5500
```

Abra `http://127.0.0.1:5500`.

## Scripts administrativos

### DJEN — consultar valores sem persistir

```powershell
cd backend
python .\scripts\djen\probe.py NUMERO_PROCESSO_CNJ
```

### DJEN — persistir snapshot de um processo já analisado

```powershell
cd backend
python .\scripts\djen\persist_once.py TJMG 50034903520238130572 --apply
```

### Monitoramento — uma rodada

```powershell
cd backend
python .\scripts\monitoring\run_once.py --limit 3
```

### Monitoramento — scheduler local

```powershell
cd backend
python .\scripts\monitoring\scheduler.py
```

## Publicação do frontend

O frontend canônico fica em `veredicta-web/frontend`. Para sincronizá-lo com o repositório irmão `veredicta-pages`, use:

```powershell
.\tools\sync-pages.ps1
```

O script preserva o `.git` do repositório de publicação e remove somente os arquivos legados do layout anterior.

## Regras importantes do produto

- Pesquisa no DataJud é transitória.
- A primeira análise por IA é manual.
- O monitoramento automático atua somente sobre análises já persistidas.
- Valores documentais do DJEN ficam em namespace próprio e não são sobrescritos pela IA.
- Jurimetria de dano moral prioriza evidência documental forte do DJEN quando disponível.
- Valores materiais e estéticos permanecem separados do dano moral.
- O Veredicta não fabrica links de documento PJe; usa o link oficial entregue pelo DJEN/CNJ.

## Segurança

- Nunca versione `.env`, tokens, chaves ou credenciais.
- `frontend/assets/js/config.js` deve conter apenas valores públicos.
- Chaves DataJud, Gemini, banco e monitoramento ficam no backend/ambiente de produção.
- `AUTH_REQUIRED` e CORS devem ser configurados conforme o ambiente.
