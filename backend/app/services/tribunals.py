DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"


TRIBUNAIS_ESTADUAIS = {
    "TJAC": {
        "nome": "Tribunal de Justiça do Acre",
        "uf": "AC",
        "alias": "api_publica_tjac",
    },
    "TJAL": {
        "nome": "Tribunal de Justiça de Alagoas",
        "uf": "AL",
        "alias": "api_publica_tjal",
    },
    "TJAP": {
        "nome": "Tribunal de Justiça do Amapá",
        "uf": "AP",
        "alias": "api_publica_tjap",
    },
    "TJAM": {
        "nome": "Tribunal de Justiça do Amazonas",
        "uf": "AM",
        "alias": "api_publica_tjam",
    },
    "TJBA": {
        "nome": "Tribunal de Justiça da Bahia",
        "uf": "BA",
        "alias": "api_publica_tjba",
    },
    "TJCE": {
        "nome": "Tribunal de Justiça do Ceará",
        "uf": "CE",
        "alias": "api_publica_tjce",
    },
    "TJDFT": {
        "nome": "Tribunal de Justiça do Distrito Federal e dos Territórios",
        "uf": "DF",
        "alias": "api_publica_tjdft",
    },
    "TJES": {
        "nome": "Tribunal de Justiça do Espírito Santo",
        "uf": "ES",
        "alias": "api_publica_tjes",
    },
    "TJGO": {
        "nome": "Tribunal de Justiça de Goiás",
        "uf": "GO",
        "alias": "api_publica_tjgo",
    },
    "TJMA": {
        "nome": "Tribunal de Justiça do Maranhão",
        "uf": "MA",
        "alias": "api_publica_tjma",
    },
    "TJMT": {
        "nome": "Tribunal de Justiça de Mato Grosso",
        "uf": "MT",
        "alias": "api_publica_tjmt",
    },
    "TJMS": {
        "nome": "Tribunal de Justiça de Mato Grosso do Sul",
        "uf": "MS",
        "alias": "api_publica_tjms",
    },
    "TJMG": {
        "nome": "Tribunal de Justiça de Minas Gerais",
        "uf": "MG",
        "alias": "api_publica_tjmg",
    },
    "TJPA": {
        "nome": "Tribunal de Justiça do Pará",
        "uf": "PA",
        "alias": "api_publica_tjpa",
    },
    "TJPB": {
        "nome": "Tribunal de Justiça da Paraíba",
        "uf": "PB",
        "alias": "api_publica_tjpb",
    },
    "TJPR": {
        "nome": "Tribunal de Justiça do Paraná",
        "uf": "PR",
        "alias": "api_publica_tjpr",
    },
    "TJPE": {
        "nome": "Tribunal de Justiça de Pernambuco",
        "uf": "PE",
        "alias": "api_publica_tjpe",
    },
    "TJPI": {
        "nome": "Tribunal de Justiça do Piauí",
        "uf": "PI",
        "alias": "api_publica_tjpi",
    },
    "TJRJ": {
        "nome": "Tribunal de Justiça do Rio de Janeiro",
        "uf": "RJ",
        "alias": "api_publica_tjrj",
    },
    "TJRN": {
        "nome": "Tribunal de Justiça do Rio Grande do Norte",
        "uf": "RN",
        "alias": "api_publica_tjrn",
    },
    "TJRS": {
        "nome": "Tribunal de Justiça do Rio Grande do Sul",
        "uf": "RS",
        "alias": "api_publica_tjrs",
    },
    "TJRO": {
        "nome": "Tribunal de Justiça de Rondônia",
        "uf": "RO",
        "alias": "api_publica_tjro",
    },
    "TJRR": {
        "nome": "Tribunal de Justiça de Roraima",
        "uf": "RR",
        "alias": "api_publica_tjrr",
    },
    "TJSC": {
        "nome": "Tribunal de Justiça de Santa Catarina",
        "uf": "SC",
        "alias": "api_publica_tjsc",
    },
    "TJSP": {
        "nome": "Tribunal de Justiça de São Paulo",
        "uf": "SP",
        "alias": "api_publica_tjsp",
    },
    "TJSE": {
        "nome": "Tribunal de Justiça de Sergipe",
        "uf": "SE",
        "alias": "api_publica_tjse",
    },
    "TJTO": {
        "nome": "Tribunal de Justiça do Tocantins",
        "uf": "TO",
        "alias": "api_publica_tjto",
    },
}


def normalize_tribunal(sigla: str) -> str:
    return sigla.strip().upper()


def get_tribunal(sigla: str) -> dict:
    sigla = normalize_tribunal(sigla)

    tribunal = TRIBUNAIS_ESTADUAIS.get(sigla)

    if not tribunal:
        raise ValueError(
            f"Tribunal não suportado: {sigla}"
        )

    return {
        "sigla": sigla,
        **tribunal,
    }


def get_datajud_endpoint(sigla: str) -> str:
    tribunal = get_tribunal(sigla)

    return (
        f"{DATAJUD_BASE_URL}/"
        f"{tribunal['alias']}/_search"
    )


def list_tribunais() -> list[dict]:
    return [
        {
            "sigla": sigla,
            **dados,
        }
        for sigla, dados
        in TRIBUNAIS_ESTADUAIS.items()
    ]