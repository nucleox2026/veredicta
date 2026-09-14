# Deploy

## Backend

O backend é um serviço FastAPI executado a partir da pasta `backend/`.

Comando de inicialização:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Variáveis de ambiente sensíveis devem ser configuradas no provedor de hospedagem, nunca no repositório.

## Banco

Produção utiliza PostgreSQL. O arquivo `database/schema.sql` serve como referência estrutural; alterações de produção devem ser aplicadas de maneira controlada e, em evolução futura, preferencialmente via ferramenta de migrations.

## Frontend

O frontend é estático. O diretório canônico é `frontend/`.

A publicação atual pode ser feita no repositório separado `veredicta-pages`. Para evitar cópia manual inconsistente, use:

```powershell
.\tools\sync-pages.ps1
```

Depois revise `git diff --check`, faça commit e push no repositório de páginas.

## Configuração pública do frontend

Arquivo:

```text
frontend/assets/js/config.js
```

Ele deve apontar para a URL pública da API e não deve conter segredos.
