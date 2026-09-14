from __future__ import annotations

import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.djen.client import DjenClient, DjenRateLimitError
from app.services.djen.document_summary import build_relevant_documents
from app.services.djen.value_extractor import extract_process_awards


def brl(centavos: int | None) -> str:
    if centavos is None:
        return "—"
    value = centavos / 100
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python scripts/djen/probe.py NUMERO_PROCESSO_CNJ")

    client = DjenClient()
    try:
        result = client.get_communications(sys.argv[1])
    except DjenRateLimitError as exc:
        raise SystemExit(f"DJEN rate limit: aguarde {exc.retry_after_seconds}s.") from exc

    awards = extract_process_awards(result.items)
    documents = build_relevant_documents(result.items, awards)
    principal = documents.get("documento_principal") or {}

    print(f"Processo: {result.numero_processo}")
    print(f"Comunicações DJEN: {len(result.items)}")
    print(f"Count informado pelo DJEN: {result.count}")
    print(f"Rate limit restante: {result.rate_limit_remaining}")

    if principal:
        print(f"Documento principal: {principal.get('tipo_documento') or '—'}")
        print(f"Resultado documental: {principal.get('resultado_documental') or '—'}")
        print(f"Teor oficial: {principal.get('link') or '—'}")

    print("\nValores indenizatórios VERIFICADOS no dispositivo:")
    print("Dano moral (1º grau):", brl(awards["valor_dano_moral_primeiro_grau_centavos"]))
    print("Dano moral (final):", brl(awards["valor_dano_moral_final_centavos"]))
    print("Dano estético (1º grau):", brl(awards["valor_dano_estetico_primeiro_grau_centavos"]))
    print("Total moral + estético (1º grau):", brl(awards["valor_total_indenizacao_primeiro_grau_centavos"]))

    print("\nDocumentos com valor judicial verificado:")
    if awards["documentos_com_valor"]:
        for doc in awards["documentos_com_valor"]:
            print(f"- {doc['data']} | {doc['tipo_documento']} | {doc['values']} | {doc['link'] or ''}")
    else:
        print("- nenhum")

    candidates = awards.get("candidatos_nao_verificados") or []
    print("\nCandidatos NÃO verificados (não entram na jurimetria):")
    if candidates:
        for ev in candidates:
            print(
                "- "
                f"{ev.get('categoria')} | "
                f"{brl(ev.get('valor_centavos'))} | "
                f"{ev.get('secao')} | "
                f"confiança {ev.get('confianca')} | "
                f"{ev.get('link') or ''}"
            )
    else:
        print("- nenhum")

    print("\nJSON estruturado:")
    print(json.dumps(awards, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
