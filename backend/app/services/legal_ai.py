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

    # Campo legado, mantido temporariamente
    # por compatibilidade com análises antigas.
    valor_indenizacao_centavos: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Valor indenizatório identificável nos dados, "
            "sem afirmar por si só que foi arbitrado judicialmente."
        ),
    )

    valor_arbitrado_juiz_centavos: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Valor de indenização efetivamente fixado por decisão "
            "judicial, em centavos. Deve ser null quando os dados "
            "não comprovarem o arbitramento."
        ),
    )

    fonte_valor_arbitrado: str | None = Field(
        default=None,
        description=(
            "Descrição curta da evidência presente nos dados que "
            "sustenta o valor arbitrado. Deve ser null quando o "
            "valor arbitrado não puder ser identificado."
        ),
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
- identificar eventual valor indenizatório;
- identificar, de forma separada e conservadora,
  eventual valor de indenização efetivamente
  arbitrado pelo juiz ou tribunal;
- apontar a evidência que sustenta o valor
  arbitrado, quando ela existir nos dados;
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

5. O campo valor_indenizacao_centavos é legado e
   pode ser preenchido somente quando houver
   evidência suficiente de que o montante se refere
   a uma indenização identificada nos dados.

6. O campo valor_arbitrado_juiz_centavos é mais
   restritivo: só o preencha quando os próprios
   dados fornecidos sustentarem que aquele montante
   foi efetivamente fixado judicialmente por juiz,
   juízo, turma, câmara ou tribunal.

7. Não trate como valor arbitrado judicialmente:
   - valor da causa;
   - valor pedido pela parte;
   - custas;
   - honorários;
   - depósito;
   - multa sem relação demonstrada com dano moral;
   - RPV;
   - precatório;
   - acordo;
   - proposta de acordo;
   - qualquer outro valor cuja natureza não esteja
     suficientemente demonstrada.

8. Uma movimentação chamada apenas "Sentença",
   "Decisão", "Acórdão" ou semelhante, sem conteúdo
   que indique o montante e sua natureza, não é
   suficiente para preencher
   valor_arbitrado_juiz_centavos.

9. fonte_valor_arbitrado só deve ser preenchida
   quando valor_arbitrado_juiz_centavos também for
   preenchido. Descreva de forma curta a evidência
   efetivamente presente nos dados, por exemplo a
   movimentação e o complemento que contêm o valor.
   Não invente número de página, trecho de sentença
   ou informação que não esteja na entrada.

10. Se houver mais de um valor nos dados e não for
    possível determinar com segurança qual deles
    corresponde ao arbitramento judicial de dano
    moral, retorne valor_arbitrado_juiz_centavos
    como null.

11. A existência do assunto TPU
    "Indenização por Dano Moral" demonstra vínculo
    temático, mas não significa que tenha havido
    condenação ou procedência.

12. Não presuma procedência, improcedência, acordo,
    extinção ou condenação apenas pela existência de
    movimentações genéricas como "Sentença",
    "Decisão", "Julgamento" ou "Baixa".

13. Diferencie claramente metadados processuais do
    conteúdo efetivo de sentença, decisão ou acórdão.

14. Quando os dados não forem suficientes para uma
    conclusão, use "indeterminado", null ou registre
    expressamente a limitação.

15. O campo direito_personalidade só deve conter
    direito que esteja sustentado pelos elementos
    recebidos. Se não for possível determinar qual
    direito foi afetado, retorne null.

16. O campo fundamentos deve listar somente
    elementos concretamente presentes ou
    diretamente sustentados pelos dados fornecidos.

17. O campo limitacoes deve registrar as principais
    restrições da análise, especialmente ausência
    de inteiro teor ou insuficiência de informação
    sobre partes, decisão, resultado ou valores.
    Quando não for possível identificar o valor
    arbitrado, registre essa limitação quando ela
    for relevante para a análise.

18. O resumo deve conter apenas informações
    sustentadas pelos dados recebidos e deve
    distinguir o que é identificável do que
    permanece indeterminado.

19. A confiança deve refletir a qualidade, a
    quantidade e a especificidade das evidências
    disponíveis. Dados apenas cadastrais ou
    movimentações genéricas exigem confiança menor.

20. Não trate a análise como decisão judicial,
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

Para valor_arbitrado_juiz_centavos e
fonte_valor_arbitrado, seja especialmente
conservador: na ausência de evidência suficiente,
retorne null.
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
