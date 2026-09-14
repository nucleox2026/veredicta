# Backend

API FastAPI do Veredicta.

## Organização

```text
backend/
├── app/
│   ├── routers/              # camada HTTP
│   ├── services/
│   │   ├── analysis/         # IA e evidências
│   │   ├── datajud/          # pesquisa e coleta DataJud
│   │   ├── djen/             # publicações e valores oficiais
│   │   └── monitoring/       # watches e reanálise automática
│   ├── auth.py
│   ├── db.py
│   ├── models.py
│   ├── settings.py
│   └── main.py
├── scripts/                  # ferramentas administrativas
├── .env.example
├── Dockerfile
└── requirements.txt
```

## Execução local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## Observação

Os scripts administrativos foram retirados da raiz para evitar misturar ferramentas operacionais com o código da aplicação. O comando de produção da API continua sendo `uvicorn app.main:app`.
