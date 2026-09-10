from __future__ import annotations

import json
import sys
from app.services.djen_client import DjenClient, DjenRateLimitError
from app.services.djen_value_extractor import extract_process_awards


def brl(centavos: int | None) -> str:
    if centavos is None:
        return "—"
    value = centavos / 100
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python run_djen_value_probe.py NUMERO_PROCESSO_CNJ")
    client = DjenClient()
    try:
        result = client.get_communications(sys.argv[1])
    except DjenRateLimitError as exc:
        raise SystemExit(f"DJEN rate limit: aguarde {exc.retry_after_seconds}s.") from exc
    awards = extract_process_awards(result.items)
    print(f"Processo: {result.numero_processo}")
    print(f"Comunicações DJEN: {len(result.items)}")
    print(f"Count informado pelo DJEN: {result.count}")
    print(f"Rate limit restante: {result.rate_limit_remaining}")
    print("Dano moral (1º grau):", brl(awards["valor_dano_moral_primeiro_grau_centavos"]))
    print("Dano moral (final):", brl(awards["valor_dano_moral_final_centavos"]))
    print("Dano estético (1º grau):", brl(awards["valor_dano_estetico_primeiro_grau_centavos"]))
    print("Total moral + estético (1º grau):", brl(awards["valor_total_indenizacao_primeiro_grau_centavos"]))
    print("\nDocumentos com valor:")
    for doc in awards["documentos_com_valor"]:
        print(f"- {doc['data']} | {doc['tipo_documento']} | {doc['values']} | {doc['link'] or ''}")
    print("\nJSON estruturado:")
    print(json.dumps(awards, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
