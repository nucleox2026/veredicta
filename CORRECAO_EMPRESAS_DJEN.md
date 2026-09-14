# Correção: empresas na tela de pesquisa

Esta versão corrige o preenchimento da coluna **Empresa ré** na pesquisa.

## O que foi corrigido

1. O cliente DJEN agora usa por padrão o Worker Cloudflare do Veredicta:
   `https://veredicta-djen-br.guilherme-moussalem.workers.dev`
2. Para Workers, a consulta é enviada para `/comunicacoes`, que é a rota realmente publicada.
3. O extrator agora lê `destinatarios[].nome` quando `destinatarios[].polo == "P"`.
4. O parser textual antigo (`RÉU:`, `REQUERIDO:`, `RECLAMADO:`) continua como fallback.
5. Foram adicionados marcadores de operadoras de saúde que podem aparecer sem sufixo LTDA/S.A.

## Arquivos principais alterados

- `backend/app/services/djen/client.py`
- `backend/app/services/djen/party_extractor.py`
- `backend/.env.example`

## Resultado validado com o JSON informado

- BANCO MASTER S/A
- BANCO PLENO SA
- EFB REGIMES ESPECIAIS DE EMPRESAS LTDA
- PKL ONE PARTICIPACOES S.A.

A DEFENSORIA não é incluída porque veio no polo ativo (`polo: "A"`).
