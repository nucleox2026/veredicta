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
