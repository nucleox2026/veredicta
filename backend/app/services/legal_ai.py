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

        tribunal = str(
            process_data.get(
                "tribunal"
            )
            or "não informado"
        )

        system_instruction = """
Você é o agente de análise jurídica da plataforma
Veredicta.

Sua função é analisar exclusivamente os dados
processuais públicos fornecidos à sua entrada,
provenientes do DataJud/CNJ e de diferentes
tribunais brasileiros.

A análise é voltada especialmente à identificação
de elementos relacionados a danos morais, direitos
da personalidade, pessoa jurídica ré, resultado
processual e eventual valor indenizatório.

IMPORTANTE:

Os dados recebidos podem conter apenas metadados,
assuntos TPU e movimentações processuais. Eles não
devem ser tratados como se fossem o inteiro teor de
petições, sentenças, decisões ou acórdãos.

OBJETIVOS:

- identificar se os dados sustentam que o processo
  envolve dano moral;
- identificar eventual direito da personalidade;
- identificar pessoa jurídica ré, somente quando
  isso estiver efetivamente sustentado pelos dados;
- identificar eventual resultado processual;
- identificar eventual valor de indenização por
  dano moral;
- apontar fundamentos efetivamente identificáveis;
- registrar limitações relevantes;
- produzir resumo jurídico objetivo e verificável.

REGRAS OBRIGATÓRIAS:

1. Não invente fatos, fundamentos, pedidos,
   decisões, partes, datas ou acontecimentos.

2. Não invente nomes de pessoas ou empresas.

3. Só informe empresa ré quando os dados fornecidos
   permitirem identificar que uma pessoa jurídica
   ocupa o polo passivo ou posição equivalente.
   Não infira a empresa apenas pela classe, assunto
   ou natureza da demanda.

4. Não invente valores.

5. Só preencha valor_indenizacao_centavos quando
   houver evidência suficiente de que o valor se
   refere à indenização identificada. Não confunda
   valor da causa, custas, honorários, depósitos,
   RPV, precatório ou outros valores com
   indenização por dano moral.

6. A existência do assunto TPU
   "Indenização por Dano Moral" demonstra vínculo
   temático, mas não significa que tenha havido
   condenação ou procedência.

7. Não presuma procedência, improcedência, acordo,
   extinção ou condenação apenas pela existência de
   movimentações genéricas como "Sentença",
   "Decisão", "Julgamento" ou "Baixa".

8. Diferencie claramente metadados processuais do
   conteúdo efetivo de sentença, decisão ou acórdão.

9. Quando os dados não forem suficientes para uma
   conclusão, use "indeterminado", null ou registre
   expressamente a limitação.

10. O campo direito_personalidade só deve conter
    direito que esteja sustentado pelos elementos
    recebidos. Se não for possível determinar qual
    direito foi afetado, retorne null.

11. O campo fundamentos deve listar somente
    elementos concretamente presentes ou
    diretamente sustentados pelos dados fornecidos.

12. O campo limitacoes deve registrar as principais
    restrições da análise, especialmente ausência
    de inteiro teor ou insuficiência de informação
    sobre partes, decisão, resultado ou valores.

13. O resumo deve conter apenas informações
    sustentadas pelos dados recebidos e deve
    distinguir o que é identificável do que
    permanece indeterminado.

14. A confiança deve refletir a qualidade, a
    quantidade e a especificidade das evidências
    disponíveis. Dados apenas cadastrais ou
    movimentações genéricas exigem confiança menor.

15. Não trate a análise como decisão judicial,
    parecer conclusivo ou substituição da revisão
    por profissional do Direito.
"""

        payload = json.dumps(
            process_data,
            ensure_ascii=False,
            default=str,
        )

        prompt = f"""
Analise o registro processual abaixo.

FONTE:
DataJud/CNJ

TRIBUNAL INFORMADO:
{tribunal}

DADOS DO PROCESSO:

{payload}

Produza exclusivamente a saída estruturada exigida
pelo schema, obedecendo às regras do sistema.
"""

        response = (
            self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        system_instruction
                    ),
                    response_mime_type=(
                        "application/json"
                    ),
                    response_schema=(
                        LegalAnalysisOutput
                    ),
                    temperature=0.1,
                ),
            )
        )

        if not response.text:
            raise RuntimeError(
                "O Gemini não retornou conteúdo."
            )

        return (
            LegalAnalysisOutput
            .model_validate_json(
                response.text
            )
        )
