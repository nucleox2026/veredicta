# Scripts administrativos

Scripts fora do fluxo HTTP normal da API.

- `djen/probe.py`: consulta DJEN e mostra extração sem persistir.
- `djen/persist_once.py`: persiste snapshot DJEN de um processo já analisado.
- `monitoring/run_once.py`: executa uma rodada do monitoramento.
- `monitoring/scheduler.py`: scheduler local de monitoramento.

Execute-os a partir de `backend/`; os scripts também resolvem o diretório do backend automaticamente.
