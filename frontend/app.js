const CONFIG = window.VEREDICTA_CONFIG || {};

const API = String(
  CONFIG.API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const SEARCH_STATE_KEY =
  "veredicta_search_state_v3";

const SELECTED_PROCESS_KEY =
  "veredicta_selected_process_v3";

let authToken =
  sessionStorage.getItem("veredicta_google_token") || "";

let tribunalCatalog = [];
let selectedTribunals = new Set();
let loadedRows = [];
let nextSearchAfterByTribunal = {};
let lastSearchRequest = null;
let searchSummary = [];
let totalFound = 0;
let errorCount = 0;
let searchInProgress = false;

const $ = (id) => document.getElementById(id);


function authHeaders() {
  if (!authToken) {
    return {};
  }

  return {
    Authorization: `Bearer ${authToken}`
  };
}


async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch (_) {
    return {};
  }
}


async function checkHealth() {
  try {
    const response = await fetch(`${API}/health`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await parseJsonResponse(response);

    $("healthStatus").textContent =
      data.status === "ok"
        ? "online"
        : (data.status || "online");

    $("statusDot").classList.add("online");
  } catch (_) {
    $("healthStatus").textContent = "offline";
    $("statusDot").classList.remove("online");
  }
}


function initGoogleIdentity() {
  const clientId = CONFIG.GOOGLE_CLIENT_ID;

  if (!clientId) {
    $("authStatus").textContent = "Modo local";
    return;
  }

  const script = document.createElement("script");
  script.src = "https://accounts.google.com/gsi/client";
  script.async = true;
  script.defer = true;

  script.onload = () => {
    if (!window.google || !window.google.accounts) {
      $("authStatus").textContent = "Google indisponível";
      return;
    }

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => {
        authToken = response.credential || "";

        if (authToken) {
          sessionStorage.setItem(
            "veredicta_google_token",
            authToken
          );
        }

        $("authStatus").textContent =
          "Autenticado com Google";
      }
    });

    window.google.accounts.id.renderButton(
      $("googleButton"),
      {
        theme: "outline",
        size: "medium",
        text: "signin_with"
      }
    );
  };

  script.onerror = () => {
    $("authStatus").textContent = "Google indisponível";
  };

  document.head.appendChild(script);
}


function showError(message) {
  $("errorText").textContent = message || "Erro inesperado.";
  $("errorCard").hidden = false;
}


function clearError() {
  $("errorCard").hidden = true;
  $("errorText").textContent = "";
}


function showPartialErrors(errors) {
  const safeErrors = Array.isArray(errors) ? errors : [];

  if (!safeErrors.length) {
    $("partialErrorCard").hidden = true;
    $("partialErrorText").innerHTML = "";
    return;
  }

  $("partialErrorCard").hidden = false;
  $("partialErrorText").innerHTML = safeErrors
    .map((item) => {
      return `
        <p>
          <strong>${escapeHtml(item.tribunal || "Tribunal")}:</strong>
          ${escapeHtml(item.error || "Falha na consulta.")}
        </p>
      `;
    })
    .join("");
}


function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}


function subjectsText(assuntos) {
  const list = Array.isArray(assuntos) ? assuntos : [];

  return list
    .map((item) => {
      if (item && typeof item === "object") {
        return item.nome || item.codigo || "";
      }

      return item || "";
    })
    .filter(Boolean)
    .join("; ");
}


function formatDate(value) {
  if (!value) {
    return "—";
  }

  const text = String(value);

  // DataJud: YYYYMMDDHHMMSS
  if (/^\d{8,14}$/.test(text)) {
    const year = text.slice(0, 4);
    const month = text.slice(4, 6);
    const day = text.slice(6, 8);
    return `${day}/${month}/${year}`;
  }

  // ISO: YYYY-MM-DD...
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return `${text.slice(8, 10)}/${text.slice(5, 7)}/${text.slice(0, 4)}`;
  }

  return text;
}


function formatNumber(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return number.toLocaleString("pt-BR");
}


function setDefaultDates() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");

  $("dateFrom").value = `${year}-01-01`;
  $("dateTo").value = `${year}-${month}-${day}`;
}



function saveSearchState() {
  const state = {
    selectedTribunals: Array.from(selectedTribunals),
    dateFrom: $("dateFrom").value,
    dateTo: $("dateTo").value,
    subjectCode: $("subjectCode").value,
    pageSizePerTribunal: $("pageSizePerTribunal").value,
    loadedRows: loadedRows,
    nextSearchAfterByTribunal: nextSearchAfterByTribunal,
    lastSearchRequest: lastSearchRequest,
    searchSummary: searchSummary,
    totalFound: totalFound,
    errorCount: errorCount
  };

  try {
    sessionStorage.setItem(
      SEARCH_STATE_KEY,
      JSON.stringify(state)
    );
  } catch (error) {
    console.warn(
      "Não foi possível salvar a pesquisa:",
      error
    );
  }
}


function readSearchState() {
  try {
    const raw =
      sessionStorage.getItem(SEARCH_STATE_KEY);

    if (!raw) {
      return null;
    }

    const state = JSON.parse(raw);

    if (!state || typeof state !== "object") {
      return null;
    }

    return state;
  } catch (error) {
    console.warn(
      "Estado de pesquisa inválido:",
      error
    );
    return null;
  }
}


function restoreSearchState() {
  const state = readSearchState();

  if (!state) {
    return false;
  }

  const available = new Set(
    tribunalCatalog.map((item) => item.sigla)
  );

  selectedTribunals = new Set(
    (Array.isArray(state.selectedTribunals)
      ? state.selectedTribunals
      : []
    ).filter((sigla) => available.has(sigla))
  );

  if (!selectedTribunals.size && available.has("TJMT")) {
    selectedTribunals.add("TJMT");
  }

  if (state.dateFrom) {
    $("dateFrom").value = state.dateFrom;
  }

  if (state.dateTo) {
    $("dateTo").value = state.dateTo;
  }

  if (state.subjectCode) {
    $("subjectCode").value = String(state.subjectCode);
  }

  if (state.pageSizePerTribunal) {
    $("pageSizePerTribunal").value =
      String(state.pageSizePerTribunal);
  }

  loadedRows = Array.isArray(state.loadedRows)
    ? state.loadedRows
    : [];

  nextSearchAfterByTribunal =
    state.nextSearchAfterByTribunal &&
    typeof state.nextSearchAfterByTribunal === "object"
      ? state.nextSearchAfterByTribunal
      : {};

  lastSearchRequest =
    state.lastSearchRequest &&
    typeof state.lastSearchRequest === "object"
      ? state.lastSearchRequest
      : null;

  searchSummary = Array.isArray(state.searchSummary)
    ? state.searchSummary
    : [];

  totalFound = Number(state.totalFound || 0);
  errorCount = Number(state.errorCount || 0);

  return true;
}


function saveSelectedProcess(row) {
  if (!row) {
    return;
  }

  try {
    sessionStorage.setItem(
      SELECTED_PROCESS_KEY,
      JSON.stringify(row)
    );
  } catch (error) {
    console.warn(
      "Não foi possível salvar o processo selecionado:",
      error
    );
  }
}


function handleProcessLinkClick(event) {
  const link = event.target.closest(".process-link");

  if (!link) {
    return;
  }

  const index = Number(link.dataset.rowIndex);

  if (Number.isInteger(index) && loadedRows[index]) {
    saveSelectedProcess(loadedRows[index]);
  }

  saveSearchState();
}


async function loadTribunals() {
  try {
    const response = await fetch(
      `${API}/api/v1/searches/tribunals`,
      {
        headers: authHeaders()
      }
    );

    const payload = await parseJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        payload.detail || `Erro HTTP ${response.status}`
      );
    }

    tribunalCatalog = Array.isArray(payload.items)
      ? payload.items
      : [];

    if (!tribunalCatalog.length) {
      throw new Error(
        "Nenhum tribunal foi retornado pela API."
      );
    }

    const restored = restoreSearchState();

    if (!restored) {
      selectedTribunals.clear();

      if (
        tribunalCatalog.some((item) => item.sigla === "TJMT")
      ) {
        selectedTribunals.add("TJMT");
      }
    }

    renderTribunals();

    if (
      restored &&
      (lastSearchRequest || loadedRows.length)
    ) {
      renderSearchResults();
    }
  } catch (error) {
    $("tribunalSelectionInfo").textContent =
      "Não foi possível carregar os tribunais.";

    showError(
      error.message || "Falha ao carregar tribunais."
    );
  }
}


function renderTribunals() {
  const container = $("tribunalList");

  container.innerHTML = tribunalCatalog
    .map((tribunal) => {
      const sigla = tribunal.sigla || "";
      const checked = selectedTribunals.has(sigla)
        ? "checked"
        : "";

      const ufText = tribunal.uf ? ` · ${tribunal.uf}` : "";

      return `
        <label class="tribunal-option">
          <input
            type="checkbox"
            class="tribunal-checkbox"
            value="${escapeHtml(sigla)}"
            ${checked}
          />
          <span>
            <strong>${escapeHtml(sigla + ufText)}</strong>
            <small>${escapeHtml(tribunal.nome || "")}</small>
          </span>
        </label>
      `;
    })
    .join("");

  container
    .querySelectorAll(".tribunal-checkbox")
    .forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          selectedTribunals.add(checkbox.value);
        } else {
          selectedTribunals.delete(checkbox.value);
        }

        updateTribunalSelectionInfo();
        saveSearchState();
      });
    });

  updateTribunalSelectionInfo();
}


function updateTribunalSelectionInfo() {
  $("tribunalSelectionInfo").textContent =
    `${selectedTribunals.size} de ${tribunalCatalog.length} selecionados`;
}


function selectAllTribunals() {
  selectedTribunals = new Set(
    tribunalCatalog.map((item) => item.sigla)
  );

  renderTribunals();
  saveSearchState();
}


function clearTribunalSelection() {
  selectedTribunals.clear();
  renderTribunals();
  saveSearchState();
}


function validateSearch() {
  if (!selectedTribunals.size) {
    throw new Error("Selecione pelo menos um tribunal.");
  }

  const dateFrom = $("dateFrom").value;
  const dateTo = $("dateTo").value;

  if (!dateFrom || !dateTo) {
    throw new Error(
      "Informe a data inicial e a data final."
    );
  }

  if (dateFrom > dateTo) {
    throw new Error(
      "A data inicial não pode ser posterior à data final."
    );
  }
}


function buildInitialSearchRequest() {
  validateSearch();

  return {
    tribunais: Array.from(selectedTribunals),
    date_from: $("dateFrom").value,
    date_to: $("dateTo").value,
    subject_code: Number($("subjectCode").value),
    page_size_per_tribunal: Number(
      $("pageSizePerTribunal").value
    ),
    search_after_by_tribunal: null
  };
}


function buildLoadMoreRequest() {
  if (!lastSearchRequest) {
    throw new Error(
      "Faça uma pesquisa antes de carregar mais resultados."
    );
  }

  const activeTribunals = Object.keys(
    nextSearchAfterByTribunal
  );

  if (!activeTribunals.length) {
    throw new Error(
      "Não há mais resultados disponíveis."
    );
  }

  const cursorMap = {};

  activeTribunals.forEach((tribunal) => {
    cursorMap[tribunal] =
      nextSearchAfterByTribunal[tribunal];
  });

  return {
    tribunais: activeTribunals,
    date_from: lastSearchRequest.date_from,
    date_to: lastSearchRequest.date_to,
    subject_code: lastSearchRequest.subject_code,
    page_size_per_tribunal:
      lastSearchRequest.page_size_per_tribunal,
    search_after_by_tribunal: cursorMap
  };
}


function setSearchLoading(loading, append) {
  searchInProgress = loading;

  $("searchButton").disabled = loading;
  $("loadMore").disabled = loading;

  if (loading) {
    if (append) {
      $("loadMore").textContent = "Carregando...";
    } else {
      $("searchButton").textContent = "Pesquisando...";
    }

    return;
  }

  $("searchButton").textContent = "Pesquisar";
  updateLoadMoreButton();
}


function rowKey(row) {
  return `${row.tribunal || ""}:${row.numero_processo || ""}`;
}


function mergeUniqueRows(currentRows, newRows) {
  const map = new Map();

  currentRows.concat(newRows).forEach((row) => {
    const key = rowKey(row);

    if (!map.has(key)) {
      map.set(key, row);
    }
  });

  return Array.from(map.values()).sort((a, b) => {
    return String(b.data_ajuizamento || "").localeCompare(
      String(a.data_ajuizamento || "")
    );
  });
}


async function executeSearch(options) {
  const append = Boolean(options && options.append);

  if (searchInProgress) {
    return;
  }

  clearError();
  showPartialErrors([]);

  let requestBody;

  try {
    requestBody = append
      ? buildLoadMoreRequest()
      : buildInitialSearchRequest();
  } catch (error) {
    showError(error.message);
    return;
  }

  const previousCursors = Object.assign(
    {},
    nextSearchAfterByTribunal
  );

  setSearchLoading(true, append);

  if (!append) {
    $("resultsCard").hidden = false;
    $("resultsTitle").textContent =
      "Pesquisando no DataJud...";
    $("resultsSubtitle").textContent = "";
    $("resultsBody").innerHTML = `
      <tr>
        <td colspan="7" class="empty-row">
          Consultando os tribunais selecionados...
        </td>
      </tr>
    `;
  }

  try {
    const response = await fetch(
      `${API}/api/v1/searches/multi`,
      {
        method: "POST",
        headers: Object.assign(
          {
            "Content-Type": "application/json"
          },
          authHeaders()
        ),
        body: JSON.stringify(requestBody)
      }
    );

    const payload = await parseJsonResponse(response);

    if (!response.ok) {
      throw new Error(
        payload.detail || `Erro HTTP ${response.status}`
      );
    }

    const incomingRows = Array.isArray(payload.items)
      ? payload.items
      : [];

    if (!append) {
      lastSearchRequest = Object.assign({}, requestBody, {
        search_after_by_tribunal: null
      });

      loadedRows = [];
      totalFound = Number(payload.total_found || 0);
      searchSummary = Array.isArray(payload.por_tribunal)
        ? payload.por_tribunal
        : [];
      nextSearchAfterByTribunal = Object.assign(
        {},
        payload.next_search_after_by_tribunal || {}
      );
    } else {
      const errors = Array.isArray(payload.errors)
        ? payload.errors
        : [];

      const errorTribunals = new Set(
        errors.map((item) => item.tribunal)
      );

      const returnedCursors =
        payload.next_search_after_by_tribunal || {};

      const updatedCursors = {};

      requestBody.tribunais.forEach((tribunal) => {
        if (errorTribunals.has(tribunal)) {
          if (previousCursors[tribunal]) {
            updatedCursors[tribunal] =
              previousCursors[tribunal];
          }

          return;
        }

        if (returnedCursors[tribunal]) {
          updatedCursors[tribunal] =
            returnedCursors[tribunal];
        }
      });

      nextSearchAfterByTribunal = updatedCursors;
    }

    loadedRows = mergeUniqueRows(
      loadedRows,
      incomingRows
    );

    errorCount = Number(
      payload.tribunais_com_erro || 0
    );

    renderSearchResults();
    showPartialErrors(payload.errors || []);
    saveSearchState();
  } catch (error) {
    showError(
      error.message ||
        "Erro inesperado durante a pesquisa."
    );

    if (!append) {
      $("resultsTitle").textContent =
        "Não foi possível concluir a pesquisa";
    }
  } finally {
    setSearchLoading(false, append);
  }
}


function renderSearchResults() {
  $("resultsCard").hidden = false;

  $("resultsTitle").textContent =
    `${formatNumber(totalFound)} registros encontrados no DataJud`;

  $("resultsSubtitle").textContent =
    `${formatNumber(loadedRows.length)} registros únicos carregados nesta tela.`;

  renderMetrics();
  renderTribunalSummary();
  renderRows();
  updateLoadMoreButton();

  $("downloadCsv").disabled = !loadedRows.length;
}


function renderMetrics() {
  const successfulTribunals = searchSummary.filter(
    (item) => item.ok
  ).length;

  $("metricTotal").textContent = formatNumber(totalFound);
  $("metricTribunals").textContent = formatNumber(
    successfulTribunals
  );
  $("metricLoaded").textContent = formatNumber(
    loadedRows.length
  );
  $("metricErrors").textContent = formatNumber(errorCount);
}


function renderTribunalSummary() {
  if (!searchSummary.length) {
    $("tribunalSummary").innerHTML = "";
    return;
  }

  $("tribunalSummary").innerHTML = searchSummary
    .map((item) => {
      return `
        <div class="metric-card tribunal-summary-card">
          <span>${escapeHtml(item.tribunal || "—")}</span>
          <strong>${formatNumber(item.total || 0)}</strong>
          <small>
            ${item.ok
              ? "registros encontrados"
              : "falha na consulta"}
          </small>
        </div>
      `;
    })
    .join("");
}


function renderRows() {
  if (!loadedRows.length) {
    $("resultsBody").innerHTML = `
      <tr>
        <td colspan="7" class="empty-row">
          Nenhum registro encontrado com os parâmetros informados.
        </td>
      </tr>
    `;

    return;
  }

  $("resultsBody").innerHTML = loadedRows
    .map((row, index) => {
      const params = new URLSearchParams();
      params.set("tribunal", row.tribunal || "");
      params.set("numero", row.numero_processo || "");

      const processUrl =
        `./processo.html?${params.toString()}`;

      return `
        <tr>
          <td class="process-number">
            <a
              class="process-link"
              href="${escapeHtml(processUrl)}"
              data-row-index="${index}"
            >
              ${escapeHtml(row.numero_processo || "—")}
            </a>
          </td>

          <td>
            <span class="grade-badge">
              ${escapeHtml(row.tribunal || "—")}
            </span>
          </td>

          <td>
            ${escapeHtml(formatDate(row.data_ajuizamento))}
          </td>

          <td>
            <span class="grade-badge">
              ${escapeHtml(row.grau || "—")}
            </span>
          </td>

          <td>${escapeHtml(row.classe_nome || "—")}</td>

          <td>
            ${escapeHtml(row.orgao_julgador_nome || "—")}
          </td>

          <td>
            ${escapeHtml(subjectsText(row.assuntos) || "—")}
          </td>
        </tr>
      `;
    })
    .join("");
}


function updateLoadMoreButton() {
  const activeTribunals = Object.keys(
    nextSearchAfterByTribunal
  );

  const hasMore = activeTribunals.length > 0;

  $("loadMore").hidden = !hasMore;
  $("loadMore").disabled = !hasMore || searchInProgress;

  if (!searchInProgress) {
    $("loadMore").textContent = hasMore
      ? "Carregar mais"
      : "Sem mais resultados";
  }

  if (hasMore) {
    $("loadMoreInfo").textContent =
      `${activeTribunals.length} tribunal(is) ainda possuem resultados para carregar.`;
  } else if (lastSearchRequest) {
    $("loadMoreInfo").textContent =
      "Não há mais resultados disponíveis para esta pesquisa.";
  } else {
    $("loadMoreInfo").textContent =
      "Os resultados são carregados sob demanda.";
  }
}


function resetSearchResults() {
  loadedRows = [];
  nextSearchAfterByTribunal = {};
  lastSearchRequest = null;
  searchSummary = [];
  totalFound = 0;
  errorCount = 0;
  searchInProgress = false;

  $("resultsCard").hidden = true;
  $("downloadCsv").disabled = true;

  $("metricTotal").textContent = "—";
  $("metricTribunals").textContent = "—";
  $("metricLoaded").textContent = "—";
  $("metricErrors").textContent = "—";

  showPartialErrors([]);
  clearError();
  updateLoadMoreButton();
}


function clearSearch() {
  selectedTribunals.clear();

  if (
    tribunalCatalog.some((item) => item.sigla === "TJMT")
  ) {
    selectedTribunals.add("TJMT");
  }

  renderTribunals();
  setDefaultDates();

  $("subjectCode").value = "9992";
  $("pageSizePerTribunal").value = "10";

  resetSearchResults();
  sessionStorage.removeItem(SEARCH_STATE_KEY);
}


function csvCell(value) {
  const text = String(value == null ? "" : value)
    .replace(/"/g, '""');

  return `"${text}"`;
}


function downloadCsv() {
  if (!loadedRows.length) {
    return;
  }

  const header = [
    "tribunal",
    "numero_processo",
    "data_ajuizamento",
    "grau",
    "classe",
    "orgao_julgador",
    "assuntos"
  ];

  const lines = [header.join(";")];

  loadedRows.forEach((row) => {
    const values = [
      row.tribunal,
      row.numero_processo,
      row.data_ajuizamento,
      row.grau,
      row.classe_nome,
      row.orgao_julgador_nome,
      subjectsText(row.assuntos)
    ].map(csvCell);

    lines.push(values.join(";"));
  });

  const blob = new Blob(
    ["\ufeff" + lines.join("\n")],
    {
      type: "text/csv;charset=utf-8"
    }
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "veredicta_resultados_carregados.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}


function bindEvents() {
  $("searchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    executeSearch({ append: false });
  });

  $("selectAllTribunals").addEventListener(
    "click",
    selectAllTribunals
  );

  $("clearTribunals").addEventListener(
    "click",
    clearTribunalSelection
  );

  $("clearSearch").addEventListener("click", clearSearch);

  $("loadMore").addEventListener("click", () => {
    executeSearch({ append: true });
  });

  $("downloadCsv").addEventListener("click", downloadCsv);

  $("resultsBody").addEventListener(
    "click",
    handleProcessLinkClick
  );

  [
    "dateFrom",
    "dateTo",
    "subjectCode",
    "pageSizePerTribunal"
  ].forEach((id) => {
    $(id).addEventListener(
      "change",
      saveSearchState
    );
  });
}


function initializeApp() {
  bindEvents();
  setDefaultDates();
  resetSearchResults();
  checkHealth();
  initGoogleIdentity();
  loadTribunals();
}


document.addEventListener("DOMContentLoaded", initializeApp);
