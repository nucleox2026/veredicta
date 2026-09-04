from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Header,
    HTTPException,
    status,
)

from ..services.process_monitor_http import (
    monitor_is_running,
    monitor_token_configured,
    run_monitor_task,
    validate_monitor_token,
)


router = APIRouter()


@router.post(
    "/internal/process-monitor/run",
    include_in_schema=False,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_process_monitor(
    background_tasks: BackgroundTasks,
    x_veredicta_monitor_token: str | None = Header(
        default=None,
        alias="X-Veredicta-Monitor-Token",
    ),
):
    """
    Endpoint privado para um agendador HTTP externo.

    Responde rapidamente e executa a rodada depois que
    a resposta HTTP é enviada.
    """
    if not monitor_token_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Monitor interno não configurado."
            ),
        )

    if not validate_monitor_token(
        x_veredicta_monitor_token
    ):
        raise HTTPException(
            status_code=401,
            detail="Não autorizado.",
        )

    already_running = (
        monitor_is_running()
    )

    if not already_running:
        background_tasks.add_task(
            run_monitor_task
        )

    return {
        "accepted": (
            not already_running
        ),
        "already_running": (
            already_running
        ),
    }
