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
    """Monta filtro exato pelo código selecionado na interface.

    A interface expõe separadamente os três ramos de dano moral.
    Portanto, selecionar 9992, 10433 ou 7779 consulta somente aquele
    código, sem unir automaticamente os demais ramos.
    """
    if not subject_code:
        return None

    profile = get_subject_profile(subject_code)

    code = (
        profile.primary_code
        if profile
        else int(subject_code)
    )

    return {
        "term": {
            "assuntos.codigo": code,
        }
    }


# Recorte nacional de saúde suplementar / planos de saúde.
HEALTH_PLAN_SUBJECT_CODES: tuple[int, ...] = (
    12482,  # Saúde suplementar
    12486,  # Planos de saúde
    12487,  # Fornecimento de medicamentos
    12488,  # Reajuste contratual
    12489,  # Tratamento médico-hospitalar
    12490,  # Fornecimento de insumos
    6233,   # Planos de Saúde (TPU histórica)
    12222,  # Fornecimento de medicamentos (histórica)
    12223,  # Tratamento médico-hospitalar (histórica)
    12224,  # UTI/UCI - saúde suplementar (histórica)
    12225,  # Reajuste contratual (histórica)
)


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
