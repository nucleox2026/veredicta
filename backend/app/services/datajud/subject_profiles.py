from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectProfile:
    key: str
    label: str
    primary_code: int
    equivalent_codes: tuple[int, ...]
    exact_names: tuple[str, ...]


DANO_MORAL_DIREITO_PUBLICO = SubjectProfile(
    key="dano_moral_direito_publico",
    label="Indenização por Dano Moral — Direito Público",
    primary_code=9992,
    equivalent_codes=(9992,),
    exact_names=("Indenização por Dano Moral",),
)

DANO_MORAL_DIREITO_CIVIL = SubjectProfile(
    key="dano_moral_direito_civil",
    label="Indenização por Dano Moral — Direito Civil",
    primary_code=10433,
    equivalent_codes=(10433,),
    exact_names=("Indenização por Dano Moral",),
)

DANO_MORAL_DIREITO_CONSUMIDOR = SubjectProfile(
    key="dano_moral_direito_consumidor",
    label="Indenização por Dano Moral — Direito do Consumidor",
    primary_code=7779,
    equivalent_codes=(7779,),
    exact_names=("Indenização por Dano Moral",),
)


DANO_MORAL_CODES: tuple[int, ...] = (9992, 10433, 7779)


_PROFILES_BY_CODE = {
    DANO_MORAL_DIREITO_PUBLICO.primary_code:
        DANO_MORAL_DIREITO_PUBLICO,
    DANO_MORAL_DIREITO_CIVIL.primary_code:
        DANO_MORAL_DIREITO_CIVIL,
    DANO_MORAL_DIREITO_CONSUMIDOR.primary_code:
        DANO_MORAL_DIREITO_CONSUMIDOR,
}


def get_subject_profile(
    subject_code: int | None,
) -> SubjectProfile | None:
    if subject_code is None:
        return None

    try:
        code = int(subject_code)
    except (TypeError, ValueError):
        return None

    return _PROFILES_BY_CODE.get(code)


def build_subject_filter(
    subject_code: int | None,
) -> dict | None:
    """Monta o filtro de assunto da Pesquisa.

    O código 0 representa o filtro único "Danos morais" da interface e
    consulta os três códigos TPU usados pelo produto: Direito Público
    (9992), Direito Civil (10433) e Direito do Consumidor (7779).
    """
    if subject_code is None:
        return None

    code = int(subject_code)

    if code == 0:
        return {
            "terms": {
                "assuntos.codigo": list(DANO_MORAL_CODES),
            }
        }

    profile = get_subject_profile(code)
    exact_code = profile.primary_code if profile else code

    return {
        "term": {
            "assuntos.codigo": exact_code,
        }
    }

def build_health_plan_filter() -> dict:
    """Filtro público para saúde suplementar/planos de saúde.

    A API Pública do DataJud não expõe os nomes das partes. Por isso,
    a Pesquisa faz o recorte pelos assuntos TPU, enquanto o nome da
    operadora é confirmado posteriormente pelo DJEN/CNJ na ficha.
    """
    return {
        "bool": {
            "should": [
                {
                    "terms": {
                        "assuntos.codigo": list(
                            HEALTH_PLAN_SUBJECT_CODES
                        )
                    }
                },
                {
                    "match_phrase": {
                        "assuntos.nome": "Planos de Saúde"
                    }
                },
                {
                    "match_phrase": {
                        "assuntos.nome": "Saúde Suplementar"
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }
