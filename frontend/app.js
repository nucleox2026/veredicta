const CONFIG = window.VEREDICTA_CONFIG || {};

const API = (
  CONFIG.API_BASE_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

let authToken =
  sessionStorage.getItem(
    "veredicta_google_token"
  ) || "";

let currentPage = 1;
let totalPages = 1;
let lastRows = [];

const $ = (id) =>
  document.getElementById(id);


function authHeaders() {
  return authToken
    ? {
        Authorization:
          `Bearer ${authToken}`
      }
    : {};
}


async function checkHealth() {
  try {
    const response =
      await fetch(`${API}/health`);

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      );
    }

    const data = await response.json();

    $("healthStatus").textContent =
      data.status === "ok"
        ? "online"
        : data.status;

    $("statusDot")
      .classList
      .add("online");

  } catch (error) {
    $("healthStatus").textContent =
      "offline";

    $("statusDot")
      .classList
      .remove("online");
  }
}


function initGoogleIdentity() {
  const clientId =
    CONFIG.GOOGLE_CLIENT_ID;

  if (!clientId) {
    $("authStatus").textContent =
      "Modo local";

    return;
  }

  const script =
    document.createElement("script");

  script.src =
    "https://accounts.google.com/gsi/client";

  script.async = true;
  script.defer = true;

  script.onload = () => {

    google.accounts.id.initialize({
      client_id: clientId,

      callback: (response) => {

        authToken =
          response.credential;

        sessionStorage.setItem(
          "veredicta_google_token",
          authToken
        );

        $("authStatus").textContent =
          "Autenticado com Google";
      }
    });

    google.accounts.id.renderButton(
      $("googleButton"),
      {
        theme: "outline",
        size: "medium",
        text: "signin_with"
      }
    );
  };

  document.head.appendChild(script);
}


function showError(message) {
  $("errorText").textContent =
    message;

  $("errorCard").hidden = false;
}


function clearError() {
  $("errorCard").hidden = true;

  $("errorText").textContent = "";
}


function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function subjectsText(
  assuntos = []
) {
  return assuntos
    .map(
      (item) =>
        item.nome ||
        item.codigo
    )
    .filter(Boolean)
    .join("; ");
}


function formatDate(value) {
  if (!value) {
    return "—";
  }

  const datePart =
    String(value)
      .slice(0, 10);

  const parts =
    datePart.split("-");

  if (parts.length !== 3) {
    return datePart;
  }

  return (
    `${parts[2]}/` +
    `${parts[1]}/` +
    `${parts[0]}`
  );
}


function buildProcessUrl(
  page = 1,
  overrides = {}
) {
  const params =
    new URLSearchParams();

  params.set(
    "page",
    overrides.page ??
    page
  );

  params.set(
    "page_size",
    overrides.page_size ??
    $("pageSize").value
  );

  const filters = {
    search:
      $("search").value.trim(),

    date_from:
      $("dateFrom").value,

    date_to:
      $("dateTo").value,

    grau:
      $("grau").value,

    classe:
      $("classe").value.trim(),

    orgao_julgador:
      $("orgaoJulgador")
        .value
        .trim(),
  };

  for (
    const [key, value]
    of Object.entries(filters)
  ) {
    if (value) {
      params.set(key, value);
    }
  }

  for (
    const [key, value]
    of Object.entries(overrides)
  ) {
    if (
      key === "page" ||
      key === "page_size"
    ) {
      continue;
    }

    if (
      value === null ||
      value === ""
    ) {
      params.delete(key);
    } else {
      params.set(key, value);
    }
  }

  return (
    `${API}/api/v1/processes?` +
    params.toString()
  );
}


async function loadProcesses(
  page = 1
) {
  clearError();

  $("resultsTitle")
    .textContent =
    "Carregando processos...";

  try {

    const response =
      await fetch(
        buildProcessUrl(page),
        {
          headers: {
            ...authHeaders()
          }
        }
      );

    const payload =
      await response
        .json()
        .catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        payload.detail ||
        `Erro HTTP ${response.status}`
      );
    }

    currentPage =
      payload.page || 1;

    totalPages =
      payload.pages || 1;

    lastRows =
      payload.items || [];

    renderProcesses(payload);

  } catch (error) {

    showError(
      error.message ||
      "Erro inesperado"
    );

    $("resultsTitle")
      .textContent =
      "Não foi possível carregar";
  }
}


function renderProcesses(
  payload
) {
  const rows =
    payload.items || [];

  $("resultsTitle")
    .textContent =
    `${payload.total ?? 0}` +
    " processos encontrados";

  $("pageInfo")
    .textContent =
    `Página ${payload.page}` +
    ` de ${payload.pages || 1}`;

  $("paginationText")
    .textContent =
    `Página ${payload.page}` +
    ` de ${payload.pages || 1}`;

  $("previousPage")
    .disabled =
    payload.page <= 1;

  $("nextPage")
    .disabled =
    payload.page >=
    (payload.pages || 1);

  if (!rows.length) {

    $("resultsBody").innerHTML = `
      <tr>
        <td
          colspan="6"
          class="empty-row"
        >
          Nenhum processo encontrado
          com estes filtros.
        </td>
      </tr>
    `;

    return;
  }

  $("resultsBody").innerHTML =
    rows
      .map(
        (row) => `
          <tr>

            <td class="process-number">
              <a
                class="process-link"
                href="./processo.html?id=${encodeURIComponent(
                  row.id
                )}"
              >

                ${escapeHtml(
                  row.numero_processo
                )}

              </a>
            </td>

            <td>
              ${escapeHtml(
                formatDate(
                  row.data_ajuizamento
                )
              )}
            </td>

            <td>
              <span class="grade-badge">
                ${escapeHtml(
                  row.grau || "—"
                )}
              </span>
            </td>

            <td>
              ${escapeHtml(
                row.classe || "—"
              )}
            </td>

            <td>
              ${escapeHtml(
                row.orgao_julgador ||
                "—"
              )}
            </td>

            <td>
              ${escapeHtml(
                subjectsText(
                  row.assuntos
                )
              )}
            </td>

          </tr>
        `
      )
      .join("");
}


async function fetchTotal(
  grau = null
) {
  const params =
    new URLSearchParams();

  params.set("page", "1");
  params.set("page_size", "1");

  if (grau) {
    params.set(
      "grau",
      grau
    );
  }

  const response =
    await fetch(
      `${API}/api/v1/processes?` +
      params.toString(),
      {
        headers: {
          ...authHeaders()
        }
      }
    );

  if (!response.ok) {
    return "—";
  }

  const payload =
    await response.json();

  return payload.total ?? 0;
}


async function loadMetrics() {
  try {

    const [
      total,
      g1,
      g2,
      je
    ] = await Promise.all([
      fetchTotal(),
      fetchTotal("G1"),
      fetchTotal("G2"),
      fetchTotal("JE")
    ]);

    $("metricTotal")
      .textContent =
      Number(total)
        .toLocaleString("pt-BR");

    $("metricG1")
      .textContent =
      Number(g1)
        .toLocaleString("pt-BR");

    $("metricG2")
      .textContent =
      Number(g2)
        .toLocaleString("pt-BR");

    $("metricJE")
      .textContent =
      Number(je)
        .toLocaleString("pt-BR");

  } catch (error) {

    $("metricTotal")
      .textContent = "—";

    $("metricG1")
      .textContent = "—";

    $("metricG2")
      .textContent = "—";

    $("metricJE")
      .textContent = "—";
  }
}


function clearFilters() {

  $("search").value = "";
  $("dateFrom").value = "";
  $("dateTo").value = "";
  $("grau").value = "";
  $("classe").value = "";
  $("orgaoJulgador").value = "";
  $("pageSize").value = "25";

  currentPage = 1;

  loadProcesses(1);
}


function csvCell(value) {
  const text =
    String(value ?? "")
      .replaceAll(
        '"',
        '""'
      );

  return `"${text}"`;
}


function downloadCsv() {

  if (!lastRows.length) {
    return;
  }

  const header = [
    "numero_processo",
    "data_ajuizamento",
    "grau",
    "classe",
    "orgao_julgador",
    "assuntos"
  ];

  const lines = [
    header.join(";")
  ];

  for (
    const row of lastRows
  ) {

    const values = [

      row.numero_processo,

      row.data_ajuizamento,

      row.grau,

      row.classe,

      row.orgao_julgador,

      subjectsText(
        row.assuntos
      )

    ].map(csvCell);

    lines.push(
      values.join(";")
    );
  }

  const blob =
    new Blob(
      [
        "\ufeff" +
        lines.join("\n")
      ],
      {
        type:
          "text/csv;charset=utf-8"
      }
    );

  const url =
    URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = url;

  link.download =
    `veredicta_processos_pagina_${currentPage}.csv`;

  link.click();

  URL.revokeObjectURL(url);
}


$("filterForm")
  .addEventListener(
    "submit",
    (event) => {

      event.preventDefault();

      currentPage = 1;

      loadProcesses(1);
    }
  );


$("clearFilters")
  .addEventListener(
    "click",
    clearFilters
  );


$("previousPage")
  .addEventListener(
    "click",
    () => {

      if (currentPage > 1) {
        loadProcesses(
          currentPage - 1
        );
      }
    }
  );


$("nextPage")
  .addEventListener(
    "click",
    () => {

      if (
        currentPage <
        totalPages
      ) {
        loadProcesses(
          currentPage + 1
        );
      }
    }
  );


$("downloadCsv")
  .addEventListener(
    "click",
    downloadCsv
  );


checkHealth();

initGoogleIdentity();

loadMetrics();

loadProcesses(1);