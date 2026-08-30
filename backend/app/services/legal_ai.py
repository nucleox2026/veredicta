import json
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class LegalAnalysisOutput(BaseModel):
    dano_moral: Literal[
        "sim",
        "nao",
        "indeterminado",
    ]

    direito_personalidade: str | None = None

    empresa_re: str | None = None

    resultado: Literal[
        "procedente",
        "improcedente",
        "parcialmente_procedente",
        "extinto",
        "acordo",
        "indeterminado",
    ] = "indeterminado"

    valor_indenizacao_centavos: int | None = Field(
        default=None,
        ge=0,
    )

    resumo: str

    fundamentos: list[str] = Field(
        default_factory=list
    )

    limitacoes: list[str] = Field(
        default_factory=list
    )

    confianca: int = Field(
        ge=0,
        le=100,
    )


class VeredictaLegalAI:

    def __init__(
        self,
        api_key: str,
        model: str,
    ):
        self.client = genai.Client(
            api_key=api_key
        )

        self.model = model


    def analyze_process(
        self,
        process_data: dict,
    ) -> LegalAnalysisOutput:

        system_instruction = """
Você é o agente de análise jurídica da plataforma
Veredicta.

Sua função é analisar metadados processuais públicos
provenientes do DataJud/CNJ, especialmente processos
do TJMT relacionados a danos morais e direitos da
personalidade.

OBJETIVOS:

- identificar se o processo envolve dano moral;
- identificar direitos da personalidade;
- identificar pessoa jurídica ré, quando possível;
- identificar resultado processual;
- identificar eventual valor indenizatório;
- identificar fundamentos;
- produzir resumo jurídico objetivo.

REGRAS OBRIGATÓRIAS:

1. Não invente fatos.

2. Não invente nomes de pessoas ou empresas.

3. Só informe empresa ré quando os dados fornecidos
   realmente permitirem essa conclusão.

4. Não invente valor de indenização.

5. A existência do assunto TPU
   "Indenização por Dano Moral" não significa que
   houve condenação.

6. Não presuma procedência ou improcedência apenas
   pela existência de movimentações genéricas.

7. Diferencie metadados processuais do conteúdo de
   sentença, decisão ou acórdão.

8. Quando os dados não forem suficientes, use
   "indeterminado", null ou registre explicitamente
   a limitação.

9. O campo resumo deve conter apenas informações
   sustentadas pelos dados recebidos.

10. A confiança deve refletir a qualidade e
    quantidade das evidências presentes nos dados.

11. Esta análise é auxiliar e deverá ser revisada
    por profissional do Direito.
"""

        payload = json.dumps(
            process_data,
            ensure_ascii=False,
            default=str,
        )

        prompt = f"""
Analise o seguinte registro processual da base
DataJud/TJMT.

DADOS DO PROCESSO:

{payload}
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=LegalAnalysisOutput,
                temperature=0.1,
            ),
        )

        if not response.text:
            raise RuntimeError(
                "O Gemini não retornou conteúdo."
            )

        return LegalAnalysisOutput.model_validate_json(
            response.text
        )