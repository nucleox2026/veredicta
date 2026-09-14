# Arquitetura do Veredicta

## Fluxo principal

```text
Pesquisa (DataJud)
    ↓
Ficha do processo
    ↓
Analisar com IA
    ├── contexto processual
    ├── análise jurídica
    └── enriquecimento DJEN/CNJ
            ↓
     sentença/publicação
     valores documentais
     link oficial do PJe
            ↓
ProcessAnalysis persistido
    ↓
Histórico + Jurimetria
```

## Backend

### `app/routers`
Camada HTTP. Mantém validação de entrada, dependências FastAPI e serialização de resposta.

### `app/services/analysis`
Análise jurídica, evidências, enriquecimento e persistência da análise automática/manual.

### `app/services/datajud`
Acesso ao DataJud, catálogo multi-tribunal, proteção de chamadas e adaptação do monitoramento.

### `app/services/djen`
Consulta ao DJEN/Comunica PJe, identificação de documentos decisórios, extração determinística de valores e persistência do snapshot oficial.

### `app/services/monitoring`
Controle de `process_watches`, detecção de mudanças, debounce e execução do monitoramento.

## Frontend

As páginas continuam independentes e estáticas:

- `index.html`: pesquisa.
- `processo.html`: ficha individual, IA, DJEN e teor oficial.
- `historico.html`: análises salvas, filtros e jurimetria.

Os recursos estáticos foram agrupados em `assets/` sem alteração de conteúdo visual.

## Persistência

`ProcessAnalysis` é a fonte do histórico. O snapshot DJEN é armazenado separadamente nos campos `djen_*`, evitando que reanálises de IA sobrescrevam evidência documental oficial.

`ProcessWatch` controla monitoramento por processo e não substitui a análise persistida.
