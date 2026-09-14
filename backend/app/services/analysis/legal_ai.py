import json
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


PROMPT_VERSION = "veredicta-evidencias-v1"


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

    confianca_resultado: int = Field(
        ge=0,
        le=100,
    )

    valor_primeiro_grau_centavos: int | None = Field(
        default=None,
        ge=0,
    )

    valor_final_centavos: int | None = Field(
        default=None,
        ge=0,
    )

    situacao_valor: Literal[
        "fixado",
        "mantido",
        "reduzido",
        "majorado",
        "afastado",
        "indeterminado",
        "nao_identificado",
    ] = "nao_identificado"

    fonte_valor: str | None = None

    confianca_valor: int = Field(
        ge=0,
        le=100,
    )

    resumo: str

    fundamentos: list[str] = Field(
        default_factory=list
    )

    limitacoes: list[str] = Field(
        default_factory=list
    )

    # Mantido como visão geral da análise.
    # Não deve ser usado como substituto das
    # confianças específicas de resultado e valor.
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

Sua função é interpretar exclusivamente os dados
processuais fornecidos à sua entrada.

A entrada pode conter dois blocos:

1. dados processuais provenientes do DataJud/CNJ;
2. evidencias_veredicta, extraídas de forma
   determinística pelo próprio sistema antes da
   chamada à IA.

A camada evidencias_veredicta não é uma conclusão
judicial. Ela é um conjunto de sinais encontrados
nos dados originais. Você deve conferir o contexto
e classificá-los juridicamente.

OBJETIVOS:

- identificar se os dados sustentam discussão de
  dano moral;
- identificar eventual direito da personalidade;
- identificar pessoa jurídica ré apenas quando os
  dados realmente permitirem;
- identificar resultado processual;
- atribuir confiança específica ao resultado;
- identificar valor judicial de primeiro grau,
  quando houver evidência explícita;
- identificar o valor judicial mais recente após
  eventual julgamento recursal, quando houver
  evidência explícita;
- indicar se o valor foi fixado, mantido, reduzido,
  majorado, afastado ou permanece indeterminado;
- atribuir confiança específica à identificação dos
  valores;
- produzir resumo, fundamentos e limitações sem
  extrapolar a fonte.

HIERARQUIA DE EVIDÊNCIA:

A. Evidência forte de resultado:
   movimentação/complemento que contenha
   expressamente procedência, procedência parcial,
   improcedência, homologação de acordo ou extinção.

B. Evidência forte de valor:
   texto que contenha valor monetário explícito e
   contexto suficiente para vinculá-lo a condenação,
   indenização, danos morais, arbitramento, fixação,
   majoração ou redução judicial.

C. Evidência insuficiente:
   simples existência de "Sentença", "Decisão",
   "Julgamento", "Acórdão" ou "Baixa" sem conteúdo
   que revele o resultado ou o valor.

REGRAS SOBRE RESULTADO:

1. Não conclua procedência ou improcedência somente
   porque existe uma sentença.

2. Quando evidencias_veredicta trouxer uma expressão
   explícita como "Procedência", "Procedência em
   Parte" ou "Improcedência", examine a evidência e
   dê preferência a ela sobre inferências genéricas.

3. Em caso de sinais contraditórios em momentos
   diferentes do processo, considere a cronologia e
   eventual reforma/confirmacão recursal.

4. confianca_resultado deve refletir somente a
   robustez da conclusão sobre o resultado.

   Orientação:
   - 90 a 100: resultado textual e explicitamente
     identificado em evidência estruturada;
   - 70 a 89: forte evidência, mas com alguma
     limitação de contexto;
   - 40 a 69: inferência parcial ou sinais
     incompletos;
   - 0 a 39: informação insuficiente.

REGRAS SOBRE VALORES:

5. Antes de concluir que não há valor, examine
   integralmente:
   - mencoes_monetarias;
   - mencoes_monetarias_com_contexto_judicial;
   - eventos_recursais;
   - movimentações e complementos originais
     recebidos.

6. NUNCA interprete números crus de campos chamados
   "valor" do DataJud como dinheiro. Na API pública,
   esses números podem ser códigos de complementos.

7. Não trate como indenização judicial:
   - valor da causa;
   - valor pedido pela parte;
   - custas;
   - honorários;
   - depósito;
   - multa de natureza não demonstrada;
   - RPV;
   - precatório;
   - acordo ou proposta de acordo;
   - qualquer quantia cuja natureza não esteja
     suficientemente demonstrada.

8. valor_primeiro_grau_centavos:
   preencha apenas quando os dados permitirem
   relacionar explicitamente a quantia a uma fixação
   judicial em primeiro grau.

9. valor_final_centavos:
   representa o valor judicial mais recente
   explicitamente sustentado pelos dados após
   eventual julgamento recursal.

   Não presuma trânsito em julgado.

   Se houver recurso posterior, mas os dados não
   permitirem conhecer o valor depois do recurso,
   deixe valor_final_centavos como null.

10. Se os dados mostrarem:
    primeiro grau = R$ 10.000,00
    e recurso = reduzido para R$ 5.000,00,
    então:
    - valor_primeiro_grau_centavos = 1000000
    - valor_final_centavos = 500000
    - situacao_valor = "reduzido"

11. Se apenas um valor judicial de primeiro grau for
    explicitamente identificado e não houver prova
    suficiente do valor posterior, preencha somente
    valor_primeiro_grau_centavos.

12. fonte_valor deve descrever de forma curta e
    verificável a evidência que sustenta a quantia.
    Não invente número de página, trecho de decisão
    ou documento inexistente na entrada.

13. confianca_valor deve refletir somente a robustez
    da identificação monetária.

    Orientação:
    - 90 a 100: valor explícito + natureza judicial
      explícita + contexto suficiente;
    - 70 a 89: valor e contexto fortes, com alguma
      limitação;
    - 40 a 69: valor aparece, mas a natureza ou
      etapa processual não está totalmente clara;
    - 0 a 30: nenhum valor judicial confiável foi
      identificado.

14. Se nenhum valor monetário explícito aparecer nos
    dados fornecidos:
    - valor_primeiro_grau_centavos = null;
    - valor_final_centavos = null;
    - fonte_valor = null;
    - situacao_valor = "nao_identificado";
    - confianca_valor deve ser baixa.

REGRAS GERAIS:

15. Não invente fatos, fundamentos, pedidos,
    decisões, partes, datas ou valores.

16. Não invente nomes de pessoas ou empresas.

17. A existência do assunto TPU "Indenização por
    Dano Moral" demonstra vínculo temático, mas não
    significa procedência ou condenação.

18. Diferencie metadados processuais de inteiro teor
    de sentença, decisão ou acórdão.

19. Quando a informação não estiver sustentada,
    use "indeterminado", null ou registre a
    limitação.

20. O campo fundamentos deve listar apenas elementos
    concretamente presentes ou diretamente
    sustentados pela entrada.

21. O campo limitacoes deve registrar especialmente
    ausência de inteiro teor, partes, resultado,
    valores ou contexto suficiente.

22. O resumo deve distinguir fatos identificáveis de
    questões que permanecem indeterminadas.

23. A confiança geral não deve ser artificialmente
    reduzida apenas porque o valor monetário não foi
    encontrado. Resultado e valor possuem métricas
    próprias.

24. Esta análise é auxiliar e não substitui revisão
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

VERSÃO DO PROMPT:
{PROMPT_VERSION}

DADOS E EVIDÊNCIAS:

{payload}

PROCEDIMENTO:

1. Examine primeiro evidencias_veredicta.
2. Confira as evidências contra os dados processuais.
3. Determine o resultado processual e sua confiança.
4. Procure valores monetários explícitos e determine
   se realmente representam fixação judicial.
5. Distinga valor de primeiro grau de eventual valor
   posterior ao recurso.
6. Registre limitações quando os metadados do
   DataJud não forem suficientes.

Produza exclusivamente a saída estruturada exigida
pelo schema.
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
