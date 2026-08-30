const CONFIG =
  window.VEREDICTA_CONFIG || {};

const API = String(
  CONFIG.API_BASE_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const SELECTED_PROCESS_KEY =
  "veredicta_selected_process_v3";

let authToken =
  sessionStorage.getItem(
    "veredicta_google_token"
  ) || "";

let currentProcessRef = null;
let currentProcess = null;

const $ = (id) =>
  document.getElementById(id);


function authHeaders() {
  if (!authToken) {
    return {};
  }

  return {
    Authorization:
      `Bearer ${authToken}`
  };
}


async function parseJsonResponse(
  response
) {
  try {
    return await response.json();
  } catch (_) {
    return {};
  }
}


function escapeHtml(value) {
  return String(
    value == null
      ? ""
      : value
  )
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}


function normalizeProcessNumber(
  value
) {
  return String(
    value || ""
  ).replace(/\D/g, "");
}


function getProcessReference() {
  const params =
    new URLSearchParams(
      window.location.search
    );

  const tribunal = String(
    params.get("tribunal") || ""
  )
    .trim()
    .toUpperCase();

  const numero =
    normalizeProcessNumber(
      params.get("numero")
    );

  if (!tribunal || !numero) {
    return null;
  }

  return {
    tribunal,
    numero
  };
}


function processBaseUrl() {
  if (!currentProcessRef) {
    throw new Error(
      "Referência do processo não informada."
    );
  }

  return (
    `${API}/api/v1/processes/lookup/` +
    `${encodeURIComponent(
      currentProcessRef.tribunal
    )}/` +
    `${encodeURIComponent(
      currentProcessRef.numero
    )}`
  );
}


function formatDate(value) {
  if (!value) {
    return "—";
  }

  const text =
    String(value);

  if (/^\d{8,14}$/.test(text)) {
    const year =
      text.slice(0, 4);

    const month =
      text.slice(4, 6);

    const day =
      text.slice(6, 8);

    return (
      `${day}/${month}/${year}`
    );
  }

  if (
    /^\d{4}-\d{2}-\d{2}/
      .test(text)
  ) {
    return (
      `${text.slice(8, 10)}/` +
      `${text.slice(5, 7)}/` +
      `${text.slice(0, 4)}`
    );
  }

  return text;
}


function formatDateTime(value) {
  if (!value) {
    return "Data não informada";
  }

  const text =
    String(value);

  if (/^\d{14}$/.test(text)) {
    const date =
      formatDate(text);

    const hour =
      text.slice(8, 10);

    const minute =
      text.slice(10, 12);

    return (
      `${date} · ${hour}:${minute}`
    );
  }

  if (/^\d{8}$/.test(text)) {
    return formatDate(text);
  }

  const date =
    new Date(text);

  if (
    !Number.isNaN(
      date.getTime()
    )
  ) {
    return date.toLocaleString(
      "pt-BR"
    );
  }

  return text;
}


function formatMoneyFromCents(
  cents
) {
  if (
    cents === null ||
    cents === undefined
  ) {
    return "Não identificado";
  }

  const value =
    Number(cents);

  if (!Number.isFinite(value)) {
    return "Não identificado";
  }

  return (
    value / 100
  ).toLocaleString(
    "pt-BR",
    {
      style: "currency",
      currency: "BRL"
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

  const labels = {
    sim: "Sim",
    nao: "Não",
    indeterminado: "Indeterminado",
    procedente: "Procedente",
    improcedente: "Improcedente",
    parcialmente_procedente:
      "Parcialmente procedente",
    extinto: "Extinto",
    acordo: "Acordo"
  };

  const key =
    String(value);

  if (labels[key]) {
    return labels[key];
  }

  return key
    .replace(/_/g, " ");
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
      await parseJsonResponse(
        response
      );

    $("healthStatus")
      .textContent =
      payload.status === "ok"
        ? "online"
        : (
          payload.status ||
          "online"
        );

    $("statusDot")
      .classList
      .add("online");

  } catch (_) {
    $("healthStatus")
      .textContent =
      "offline";

    $("statusDot")
      .classList
      .remove("online");
  }
}


function showError(message) {
  $("errorText")
    .textContent =
    message ||
    "Erro inesperado.";

  $("errorCard")
    .hidden = false;
}


function clearError() {
  $("errorCard")
    .hidden = true;

  $("errorText")
    .textContent = "";
}



function readSelectedProcess() {
  try {
    const raw =
      sessionStorage.getItem(SELECTED_PROCESS_KEY);

    if (!raw) {
      return null;
    }

    const row = JSON.parse(raw);

    if (!row || typeof row !== "object") {
      return null;
    }

    const tribunal = String(row.tribunal || "")
      .trim()
      .toUpperCase();

    const numero = normalizeProcessNumber(
      row.numero_processo
    );

    if (
      !currentProcessRef ||
      tribunal !== currentProcessRef.tribunal ||
      numero !== currentProcessRef.numero
    ) {
      return null;
    }

    return row;
  } catch (_) {
    return null;
  }
}


function renderProcessSnapshot(row) {
  if (!row) {
    return;
  }

  document.title =
    "Processo — Veredicta";

  $("processBadge").textContent =
    `FICHA PROCESSUAL · ${
      row.tribunal || currentProcessRef.tribunal
    }`;

  $("processNumber").textContent =
    row.numero_processo || currentProcessRef.numero;

  const classe =
    row.classe_nome || row.classe || "Processo";

  const orgao =
    row.orgao_julgador_nome ||
    row.orgao_julgador ||
    row.tribunal ||
    "DataJud";

  $("processSubtitle").textContent =
    `${classe} · ${orgao}`;

  $("processTribunal").textContent =
    row.tribunal || currentProcessRef.tribunal;

  $("processGrade").textContent =
    row.grau || "—";

  $("processDate").textContent =
    formatDate(row.data_ajuizamento);

  $("processClass").textContent = classe;
  $("processCourt").textContent = orgao;

  renderSubjects(row.assuntos || []);

  $("movementCount").textContent = "…";
  $("movementCountNote").textContent =
    "Consultando DataJud";
  $("movementMeta").textContent =
    "Carregando os detalhes e o histórico processual.";
}


function renderSubjects(
  subjects
) {
  const safeSubjects =
    Array.isArray(subjects)
      ? subjects
      : [];

  if (!safeSubjects.length) {
    $("subjectsList")
      .innerHTML = `
        <span class="subject-chip muted-chip">
          Nenhum assunto informado
        </span>
      `;

    return;
  }

  $("subjectsList")
    .innerHTML =
    safeSubjects
      .map(
        (subject) => `
          <span class="subject-chip">
            <span>
              ${escapeHtml(
                subject.nome ||
                subject.codigo ||
                "Assunto"
              )}
            </span>

            ${
              subject.codigo
                ? `
                  <small>
                    TPU ${escapeHtml(
                      subject.codigo
                    )}
                  </small>
                `
                : ""
            }
          </span>
        `
      )
      .join("");
}


function renderPartyGroup(
  elementId,
  parties
) {
  const element =
    $(elementId);

  const safeParties =
    Array.isArray(parties)
      ? parties
      : [];

  if (!safeParties.length) {
    element.innerHTML = `
      <span class="party-empty">
        Não identificado no DataJud
      </span>
    `;

    return;
  }

  element.innerHTML =
    safeParties
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


function renderMovementComplements(
  complements
) {
  const safeComplements =
    Array.isArray(complements)
      ? complements
      : [];

  if (!safeComplements.length) {
    return "";
  }

  const items =
    safeComplements
      .map((item) => {
        const text =
          item.descricao ||
          item.nome;

        if (!text) {
          return "";
        }

        return `
          <span class="movement-complement">
            ${escapeHtml(text)}
          </span>
        `;
      })
      .filter(Boolean)
      .join("");

  if (!items) {
    return "";
  }

  return `
    <div class="movement-complements">
      ${items}
    </div>
  `;
}


function renderMovements(
  process
) {
  const movements =
    Array.isArray(
      process.movimentos
    )
      ? process.movimentos
      : [];

  const total =
    Number(
      process.movimentos_total
    );

  const displayed =
    Number(
      process.movimentos_exibidos
    );

  const safeTotal =
    Number.isFinite(total)
      ? total
      : movements.length;

  const safeDisplayed =
    Number.isFinite(displayed)
      ? displayed
      : movements.length;

  $("movementCount")
    .textContent =
    safeTotal.toLocaleString(
      "pt-BR"
    );

  if (
    safeTotal >
    safeDisplayed
  ) {
    $("movementCountNote")
      .textContent =
      `${safeDisplayed} mais recentes exibidos`;

    $("movementMeta")
      .textContent =
      `Exibindo os ${safeDisplayed} movimentos mais recentes de ${safeTotal} informados pelo DataJud.`;

  } else {
    $("movementCountNote")
      .textContent =
      "Histórico disponível";

    $("movementMeta")
      .textContent =
      `${safeDisplayed} movimentação(ões) disponível(is) no DataJud.`;
  }

  if (!movements.length) {
    $("movementsList")
      .innerHTML = `
        <div class="empty-panel">
          Nenhuma movimentação encontrada.
        </div>
      `;

    return;
  }

  $("movementsList")
    .innerHTML =
    movements
      .map(
        (movement) => `
          <article class="timeline-item">
            <div class="timeline-dot"></div>

            <div class="timeline-content">
              <span class="timeline-date">
                ${escapeHtml(
                  formatDateTime(
                    movement.data_hora ||
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

              <div class="movement-meta-row">
                ${
                  movement.codigo
                    ? `
                      <small>
                        Código ${escapeHtml(
                          movement.codigo
                        )}
                      </small>
                    `
                    : ""
                }

                ${
                  movement.orgao_julgador
                    ? `
                      <small>
                        ${escapeHtml(
                          movement.orgao_julgador
                        )}
                      </small>
                    `
                    : ""
                }
              </div>

              ${renderMovementComplements(
                movement.complementos
              )}
            </div>
          </article>
        `
      )
      .join("");
}


function renderProcess(
  process
) {
  currentProcess =
    process;

  document.title =
    "Processo — Veredicta";

  $("processBadge")
    .textContent =
    `FICHA PROCESSUAL · ${
      process.tribunal || ""
    }`;

  $("processNumber")
    .textContent =
    process.numero_processo ||
    currentProcessRef.numero;

  const classe =
    process.classe_nome ||
    process.classe ||
    "Processo";

  const orgao =
    process.orgao_julgador_nome ||
    process.orgao_julgador ||
    process.tribunal ||
    "DataJud";

  $("processSubtitle")
    .textContent =
    `${classe} · ${orgao}`;

  $("processTribunal")
    .textContent =
    process.tribunal ||
    currentProcessRef.tribunal ||
    "—";

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
    classe;

  $("processCourt")
    .textContent =
    orgao;

  renderSubjects(
    process.assuntos
  );

  const parties =
    process.partes &&
    typeof process.partes === "object"
      ? process.partes
      : {};

  renderPartyGroup(
    "activeParties",
    parties.ativo
  );

  renderPartyGroup(
    "passiveParties",
    parties.passivo
  );

  renderMovements(
    process
  );
}


async function loadProcess() {
  if (!currentProcessRef) {
    showError(
      "A URL não contém tribunal e número de processo válidos."
    );

    $("processNumber")
      .textContent =
      "Processo não informado";

    $("processSubtitle")
      .textContent =
      "Volte para a pesquisa e selecione um processo.";

    return false;
  }

  clearError();

  try {
    const response =
      await fetch(
        processBaseUrl(),
        {
          headers:
            authHeaders()
        }
      );

    const payload =
      await parseJsonResponse(
        response
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

    return true;

  } catch (error) {
    showError(
      `Não foi possível carregar os detalhes do processo no DataJud: ${
        error.message || "erro inesperado"
      }. Endpoint consultado: ${processBaseUrl()}`
    );

    $("movementCountNote")
      .textContent =
      "Detalhes indisponíveis";

    $("movementMeta")
      .textContent =
      "Os dados resumidos da pesquisa foram preservados acima.";

    $("movementsList")
      .innerHTML = `
        <div class="empty-panel">
          Tente atualizar a página para consultar
          novamente os detalhes no DataJud.
        </div>
      `;

    return false;
  }
}


function renderList(
  elementId,
  values
) {
  const element =
    $(elementId);

  const safeValues =
    Array.isArray(values)
      ? values
      : [];

  if (!safeValues.length) {
    element.innerHTML = `
      <li>
        Nenhuma informação identificada.
      </li>
    `;

    return;
  }

  element.innerHTML =
    safeValues
      .map(
        (value) => `
          <li>
            ${escapeHtml(value)}
          </li>
        `
      )
      .join("");
}


function showAnalysisEmpty() {
  $("analysisEmpty")
    .hidden = false;

  $("analysisLoading")
    .hidden = true;

  $("analysisContent")
    .hidden = true;

  $("analysisStatus")
    .textContent =
    "Não analisado";
}


function renderAnalysis(
  analysis
) {
  $("analysisEmpty")
    .hidden = true;

  $("analysisLoading")
    .hidden = true;

  $("analysisContent")
    .hidden = false;

  $("analysisStatus")
    .textContent =
    "Analisado";

  $("analysisMoral")
    .textContent =
    friendlyValue(
      analysis.dano_moral
    );

  $("analysisPersonality")
    .textContent =
    friendlyValue(
      analysis
        .direito_personalidade
    );

  $("analysisCompany")
    .textContent =
    friendlyValue(
      analysis.empresa_re
    );

  $("analysisResult")
    .textContent =
    friendlyValue(
      analysis.resultado
    );

  $("analysisValue")
    .textContent =
    formatMoneyFromCents(
      analysis
        .valor_indenizacao_centavos
    );

  $("analysisConfidence")
    .textContent =
    (
      analysis.confianca !== null &&
      analysis.confianca !== undefined
    )
      ? `${analysis.confianca}%`
      : "—";

  $("analysisSummary")
    .textContent =
    analysis.resumo ||
    "Resumo não disponível.";

  renderList(
    "analysisFoundations",
    analysis.fundamentos
  );

  renderList(
    "analysisLimitations",
    analysis.limitacoes
  );

  $("analysisModel")
    .textContent =
    analysis.model_name
      ? `Modelo: ${analysis.model_name}`
      : "";
}


async function loadExistingAnalysis() {
  if (!currentProcessRef) {
    return;
  }

  $("analysisStatus")
    .textContent =
    "Verificando...";

  try {
    const response =
      await fetch(
        `${processBaseUrl()}/analysis`,
        {
          headers:
            authHeaders()
        }
      );

    if (
      response.status === 404
    ) {
      showAnalysisEmpty();
      return;
    }

    const payload =
      await parseJsonResponse(
        response
      );

    if (!response.ok) {
      throw new Error(
        payload.detail ||
        "Erro ao carregar análise."
      );
    }

    renderAnalysis(
      payload
    );

  } catch (error) {
    console.error(
      "Erro ao carregar análise:",
      error
    );

    showAnalysisEmpty();
  }
}


async function runAnalysis(
  force
) {
  if (
    !currentProcessRef ||
    !currentProcess
  ) {
    showError(
      "Carregue o processo antes de solicitar a análise."
    );

    return;
  }

  clearError();

  $("analysisEmpty")
    .hidden = true;

  $("analysisContent")
    .hidden = true;

  $("analysisLoading")
    .hidden = false;

  $("analysisStatus")
    .textContent =
    "Analisando...";

  $("analyzeButton")
    .disabled = true;

  $("reanalyzeButton")
    .disabled = true;

  try {
    const url =
      `${processBaseUrl()}/analyze` +
      `?force=${
        force
          ? "true"
          : "false"
      }`;

    const response =
      await fetch(
        url,
        {
          method: "POST",
          headers:
            authHeaders()
        }
      );

    const payload =
      await parseJsonResponse(
        response
      );

    if (!response.ok) {
      throw new Error(
        payload.detail ||
        `Erro HTTP ${response.status}`
      );
    }

    renderAnalysis(
      payload
    );

  } catch (error) {
    $("analysisLoading")
      .hidden = true;

    $("analysisStatus")
      .textContent =
      "Erro";

    showAnalysisEmpty();

    showError(
      error.message ||
      "Erro durante a análise."
    );

  } finally {
    $("analyzeButton")
      .disabled = false;

    $("reanalyzeButton")
      .disabled = false;
  }
}


function bindEvents() {
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
            "Deseja executar uma nova análise com IA? Isso fará uma nova chamada ao provedor."
          );

        if (confirmed) {
          runAnalysis(true);
        }
      }
    );
}


async function initializePage() {
  bindEvents();
  checkHealth();

  currentProcessRef =
    getProcessReference();

  if (currentProcessRef) {
    $("processBadge").textContent =
      `FICHA PROCESSUAL · ${currentProcessRef.tribunal}`;

    $("processNumber").textContent =
      currentProcessRef.numero;

    $("processTribunal").textContent =
      currentProcessRef.tribunal;
  }

  const snapshot =
    readSelectedProcess();

  if (snapshot) {
    renderProcessSnapshot(snapshot);
  }

  const loaded =
    await loadProcess();

  // A análise armazenada pode ser exibida mesmo se
  // a consulta de detalhe ao DataJud falhar.
  await loadExistingAnalysis();

  if (!loaded) {
    $("analyzeButton").disabled = true;

    if ($("analysisContent").hidden) {
      $("analysisStatus").textContent =
        "Detalhe indisponível";

      $("analysisEmpty").hidden = true;
    }
  }
}


document.addEventListener(
  "DOMContentLoaded",
  initializePage
);
