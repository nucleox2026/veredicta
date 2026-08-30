# JurisIA Web — starter

Starter do aplicativo de jurimetria e análise de danos morais.

## Arquitetura

- **Frontend:** GitHub Pages (HTML/CSS/JS estático)
- **API:** FastAPI em Python
- **Backend recomendado:** Google Cloud Run (`southamerica-east1`, São Paulo)
- **Banco:** Cloud SQL for PostgreSQL (`southamerica-east1`, São Paulo)
- **Segredos:** Google Secret Manager
- **Fonte inicial:** API Pública do DataJud/CNJ — TJMT
- **Autenticação:** Google Identity (opcional no desenvolvimento; obrigatória em produção)

```text
GitHub Pages
    |
    | HTTPS + Bearer Google ID Token
    v
Cloud Run / FastAPI
    |---- DataJud/CNJ
    |---- OpenAI (fase 2)
    |---- TJMT jurisprudência (fase 2)
    v
Cloud SQL / PostgreSQL
```

## 1. Rodar o backend localmente

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Abra `http://localhost:8000/docs`.

Para a primeira execução sem PostgreSQL, use a URL SQLite que já vem no `.env.example`.

## 2. Rodar o frontend localmente

Edite `frontend/config.js` e mantenha:

```js
window.JURISIA_CONFIG = {
  API_BASE_URL: "http://localhost:8000",
  GOOGLE_CLIENT_ID: ""
};
```

Depois:

```bash
cd frontend
python -m http.server 5500
```

Abra `http://localhost:5500`.

## 3. DataJud

A chave pública vigente do DataJud pode mudar. Copie a chave vigente da documentação oficial e configure no backend:

```env
DATAJUD_API_KEY=...
```

**Nunca coloque essa configuração no frontend.**

O endpoint TJMT usado pelo starter é:

```text
https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search
```

O starter possui uma busca de prévia por intervalo de ajuizamento e expressão de assunto. Para coleta anual completa, a próxima etapa é implementar paginação robusta (`search_after`), fila de jobs e persistência em lotes.

## 4. Banco PostgreSQL

O schema inicial está em `sql/schema.sql`.

Em produção, use Cloud SQL PostgreSQL em São Paulo e configure `DATABASE_URL` no Cloud Run.

Exemplo TCP local:

```env
DATABASE_URL=postgresql+psycopg://jurisia:SENHA@127.0.0.1:5432/jurisia
```

No Cloud Run, pode-se usar o socket do Cloud SQL após anexar a instância ao serviço.

## 5. Autenticação

Durante desenvolvimento:

```env
AUTH_REQUIRED=false
```

Em produção:

```env
AUTH_REQUIRED=true
GOOGLE_CLIENT_ID=seu-client-id.apps.googleusercontent.com
ALLOWED_EMAILS=diretora@empresa.com.br,seuemail@empresa.com.br
```

No `frontend/config.js`, configure o mesmo `GOOGLE_CLIENT_ID`. O Client ID é identificador público; chaves secretas continuam exclusivamente no backend.

## 6. GitHub Pages

O workflow `.github/workflows/pages.yml` publica a pasta `frontend/`.

No GitHub:

1. `Settings` → `Pages`.
2. Em `Build and deployment`, selecione `GitHub Actions`.
3. Faça push no branch `main`.

Antes de publicar, altere `frontend/config.js` para apontar `API_BASE_URL` para a URL HTTPS do Cloud Run.

## 7. Próximas etapas técnicas

1. Criar ingestão completa DataJud com paginação e retomada.
2. Mapear códigos TPU de dano moral/direitos da personalidade.
3. Criar tabela de empresas e polos processuais disponíveis nas fontes.
4. Criar conector para jurisprudência/decisões do TJMT.
5. Adicionar pipeline OpenAI para classificação e resumo estruturado.
6. Exportar CSV/XLSX e dashboard de jurimetria.
7. Criar trilha de auditoria: fonte, timestamp, modelo, prompt/versionamento e confiança.

## Segurança

- Nenhuma chave de API deve ir para GitHub Pages.
- `OPENAI_API_KEY`, credenciais do banco e demais segredos ficam no Secret Manager/Cloud Run.
- Restringir CORS ao domínio real do GitHub Pages.
- Ativar autenticação antes de inserir dados de clientes ou documentos privados.
- Dados públicos de processos e dados confidenciais de clientes devem ser tratados em camadas/tabelas separadas.
