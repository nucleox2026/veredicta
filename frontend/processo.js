const CONFIG =
  window.VEREDICTA_CONFIG || {};

const API = (
  CONFIG.API_BASE_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");


const $ = (id) =>
  document.getElementById(id);


function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function formatDate(value) {

  if (!value) {
    return "—";
  }

  const text =
    String(value);

  const datePart =
    text.slice(0, 10);

  const parts =
    datePart.split("-");

  if (parts.length !== 3) {
    return text;
  }

  return (
    `${parts[2]}/` +
    `${parts[1]}/` +
    `${parts[0]}`
  );
}


function formatMovementDate(value) {

  if (!value) {
    return "Data não informada";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return value;
  }

  return date.toLocaleString(
    "pt-BR"
  );
}


async function checkHealth() {

  try {

    const response =
      await fetch(
        `${API}/health`
      );

    if (!response.ok) {
      throw new Error();
    }

    const payload =
      await response.json();

    $("healthStatus")
      .textContent =
      payload.status === "ok"
        ? "online"
        : payload.status;

    $("statusDot")
      .classList
      .add("online");

  } catch {

    $("healthStatus")
      .textContent =
      "offline";
  }
}


function getProcessId() {

  const params =
    new URLSearchParams(
      window.location.search
    );

  return params.get("id");
}


function renderSubjects(
  subjects = []
) {

  if (!subjects.length) {

    $("subjectsList")
      .innerHTML =
      `<span class="subject-chip">
        Nenhum assunto informado
      </span>`;

    return;
  }

  $("subjectsList")
    .innerHTML =
    subjects
      .map(
        (subject) => `
          <span class="subject-chip">

            ${escapeHtml(
              subject.nome ||
              subject.codigo
            )}

            ${
              subject.codigo
                ? `<small>
                    TPU ${escapeHtml(
                      subject.codigo
                    )}
                  </small>`
                : ""
            }

          </span>
        `
      )
      .join("");
}


function renderMovements(
  movements = []
) {

  $("movementCount")
    .textContent =
    movements.length
      .toLocaleString("pt-BR");


  if (!movements.length) {

    $("movementsList")
      .innerHTML =
      "<p>Nenhuma movimentação encontrada.</p>";

    return;
  }


  const sorted =
    [...movements]
      .sort(
        (a, b) =>
          new Date(
            b.dataHora || 0
          ) -
          new Date(
            a.dataHora || 0
          )
      );


  $("movementsList")
    .innerHTML =
    sorted
      .map(
        (movement) => `

          <article class="timeline-item">

            <div class="timeline-dot">
            </div>

            <div class="timeline-content">

              <span class="timeline-date">
                ${escapeHtml(
                  formatMovementDate(
                    movement.dataHora
                  )
                )}
              </span>

              <strong>
                ${escapeHtml(
                  movement.nome ||
                  "Movimentação"
                )}
              </strong>

              ${
                movement.codigo
                  ? `
                    <small>
                      Código:
                      ${escapeHtml(
                        movement.codigo
                      )}
                    </small>
                  `
                  : ""
              }

            </div>

          </article>

        `
      )
      .join("");
}

function renderPartyGroup(
  elementId,
  parties = []
) {
  const element =
    $(elementId);

  if (!parties.length) {
    element.innerHTML = `
      <span class="party-empty">
        Não identificado
      </span>
    `;

    return;
  }

  element.innerHTML =
    parties
      .map(
        (party) => `
          <div class="party-item">

            <strong>
              ${escapeHtml(
                party.nome ||
                "Parte não identificada"
              )}
            </strong>

            ${
              party.documento
                ? `
                  <small>
                    ${escapeHtml(
                      party.documento
                    )}
                  </small>
                `
                : ""
            }

            ${
              party.tipo_pessoa
                ? `
                  <small>
                    ${escapeHtml(
                      party.tipo_pessoa
                    )}
                  </small>
                `
                : ""
            }

          </div>
        `
      )
      .join("");
}

function renderProcess(
  process
) {

  document.title =
    `${process.numero_processo} — Veredicta`;

  $("processNumber")
    .textContent =
    process.numero_processo;


  $("processSubtitle")
    .textContent =
    `${process.classe || "Processo"} · ${
      process.orgao_julgador ||
      process.tribunal
    }`;


  $("processTribunal")
    .textContent =
    process.tribunal || "—";


  $("processGrade")
    .textContent =
    process.grau || "—";


  $("processDate")
    .textContent =
    formatDate(
      process.data_ajuizamento
    );


  $("processClass")
    .textContent =
    process.classe || "—";


  $("processCourt")
    .textContent =
    process.orgao_julgador || "—";


  renderSubjects(
    process.assuntos || []
  );

  const parties =
  process.partes || {};

  renderPartyGroup(
    "activeParties",
    parties.ativo || []
  );

  renderPartyGroup(
    "passiveParties",
    parties.passivo || []
  );

  renderMovements(
    process.movimentos || []
  );
}


function showError(message) {

  $("errorText")
    .textContent =
    message;

  $("errorCard")
    .hidden = false;
}


async function loadProcess() {

  const id =
    getProcessId();


  if (!id) {

    showError(
      "Nenhum processo foi informado."
    );

    return;
  }


  try {

    const response =
      await fetch(
        `${API}/api/v1/processes/${id}`
      );


    const payload =
      await response
        .json()
        .catch(
          () => ({})
        );


    if (!response.ok) {

      throw new Error(
        payload.detail ||
        `Erro HTTP ${response.status}`
      );
    }


    renderProcess(
      payload
    );


  } catch (error) {

    showError(
      error.message ||
      "Erro inesperado."
    );
  }
}

function formatMoneyFromCents(cents) {
  if (
    cents === null ||
    cents === undefined
  ) {
    return "Não identificado";
  }

  return (
    Number(cents) / 100
  ).toLocaleString(
    "pt-BR",
    {
      style: "currency",
      currency: "BRL",
    }
  );
}


function friendlyValue(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "Não identificado";
  }

  return String(value)
    .replaceAll("_", " ");
}


function renderList(
  elementId,
  values
) {
  const element = $(elementId);

  if (
    !values ||
    !values.length
  ) {
    element.innerHTML = `
      <li>
        Nenhuma informação identificada.
      </li>
    `;

    return;
  }

  element.innerHTML = values
    .map(
      (value) => `
        <li>
          ${escapeHtml(value)}
        </li>
      `
    )
    .join("");
}


function renderAnalysis(analysis) {
  $("analysisEmpty").hidden = true;
  $("analysisLoading").hidden = true;
  $("analysisContent").hidden = false;

  $("analysisStatus").textContent =
    "Analisado";

  $("analysisMoral").textContent =
    friendlyValue(
      analysis.dano_moral
    );

  $("analysisPersonality").textContent =
    friendlyValue(
      analysis.direito_personalidade
    );

  $("analysisCompany").textContent =
    friendlyValue(
      analysis.empresa_re
    );

  $("analysisResult").textContent =
    friendlyValue(
      analysis.resultado
    );

  $("analysisValue").textContent =
    formatMoneyFromCents(
      analysis.valor_indenizacao_centavos
    );

  $("analysisConfidence").textContent =
    analysis.confianca !== null &&
    analysis.confianca !== undefined
      ? `${analysis.confianca}%`
      : "—";

  $("analysisSummary").textContent =
    analysis.resumo ||
    "Resumo não disponível.";

  const fundamentos =
    analysis.fundamentos || {};

  renderList(
    "analysisFoundations",
    fundamentos.itens || []
  );

  renderList(
    "analysisLimitations",
    fundamentos.limitacoes || []
  );

  $("analysisModel").textContent =
    analysis.model_name
      ? `Modelo: ${analysis.model_name}`
      : "";
}


async function loadExistingAnalysis() {
  const id = getProcessId();

  if (!id) {
    return;
  }

  try {
    const response = await fetch(
      `${API}/api/v1/processes/${id}/analysis`
    );

    if (response.status === 404) {
      $("analysisEmpty").hidden = false;
      $("analysisLoading").hidden = true;
      $("analysisContent").hidden = true;

      $("analysisStatus").textContent =
        "Não analisado";

      return;
    }

    const payload = await response
      .json()
      .catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        payload.detail ||
        "Erro ao carregar análise."
      );
    }

    renderAnalysis(payload);

  } catch (error) {
    console.error(
      "Erro ao carregar análise:",
      error
    );
  }
}


async function runAnalysis(
  force = false
) {
  const id = getProcessId();

  if (!id) {
    return;
  }

  clearError();

  $("analysisEmpty").hidden = true;
  $("analysisContent").hidden = true;
  $("analysisLoading").hidden = false;

  $("analysisStatus").textContent =
    "Analisando...";

  try {
    const url =
      `${API}/api/v1/processes/${id}/analyze` +
      (
        force
          ? "?force=true"
          : ""
      );

    const response = await fetch(
      url,
      {
        method: "POST",
      }
    );

    const payload = await response
      .json()
      .catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        payload.detail ||
        `Erro HTTP ${response.status}`
      );
    }

    renderAnalysis(payload);

  } catch (error) {
    $("analysisLoading").hidden = true;
    $("analysisEmpty").hidden = false;

    $("analysisStatus").textContent =
      "Erro";

    showError(
      error.message ||
      "Erro durante análise."
    );
  }
}


$("analyzeButton")
  .addEventListener(
    "click",
    () => {
      runAnalysis(false);
    }
  );


$("reanalyzeButton")
  .addEventListener(
    "click",
    () => {
      const confirmed =
        window.confirm(
          "Deseja executar uma nova análise com IA?"
        );

      if (confirmed) {
        runAnalysis(true);
      }
    }
  );

function clearError() {
  $("errorCard").hidden = true;
  $("errorText").textContent = "";
}

checkHealth();

loadProcess();

loadExistingAnalysis();