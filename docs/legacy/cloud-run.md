# Deploy do backend no Google Cloud Run + Cloud SQL

Região recomendada: `southamerica-east1` (São Paulo).

## Recursos

- Cloud Run: `jurisia-api`
- Cloud SQL PostgreSQL: `jurisia-db`
- Database: `jurisia`
- Secret Manager: `DATAJUD_API_KEY`, senha do PostgreSQL e futuros segredos da OpenAI

## Exemplo de build/deploy

A partir da pasta `backend/`:

```bash
gcloud builds submit --tag southamerica-east1-docker.pkg.dev/SEU_PROJETO/jurisia/jurisia-api:latest

gcloud run deploy jurisia-api \
  --image southamerica-east1-docker.pkg.dev/SEU_PROJETO/jurisia/jurisia-api:latest \
  --region southamerica-east1 \
  --platform managed \
  --allow-unauthenticated
```

`--allow-unauthenticated` torna a URL HTTP acessível, mas **não torna os endpoints privados**: a aplicação exige o Google ID Token quando `AUTH_REQUIRED=true`. Para uma implantação corporativa mais restrita, também podemos colocar um gateway/proxy e políticas IAM na frente.

## Variáveis relevantes

```text
ENVIRONMENT=production
AUTH_REQUIRED=true
GOOGLE_CLIENT_ID=...
ALLOWED_EMAILS=...
CORS_ORIGINS=https://SEU_USUARIO.github.io
DATAJUD_TJMT_URL=https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search
DATABASE_URL=...
```

Não armazene valores secretos em arquivos versionados. Use Secret Manager.

## Cloud SQL

Crie PostgreSQL em `southamerica-east1` e anexe a instância ao serviço Cloud Run. Depois use uma conexão segura por Cloud SQL Connector/socket.

Quando avançarmos para o deploy real, vale migrar a criação automática das tabelas para Alembic e criar contas de banco com privilégios mínimos.
