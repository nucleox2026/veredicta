(() => {
  const API_BASE = String(
    (window.VEREDICTA_CONFIG || {}).API_BASE_URL ||
      "http://127.0.0.1:8000"
  ).replace(/\/$/, "");

  const $a = (id) => document.getElementById(id);

  function authHeadersAnalytics() {
    const token =
      sessionStorage.getItem("veredicta_google_token") || "";
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function money(cents) {
    if (cents == null || !Number.isFinite(Number(cents))) {
      return "—";
    }

    return (Number(cents) / 100).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL"
    });
  }

  function sentenceText(value) {
    if (value === true) return "Sim";
    if (value === false) return "Não";
    return "Aguardando atualização";
  }

  function createSection() {
    if ($a("analysisDashboard")) return;

    const main = document.querySelector("main");
    if (!main) return;

    const section = document.createElement("section");
    section.id = "analysisDashboard";
    section.className = "card analytics-card";

    section.innerHTML = `
      <div class="section-heading">
        <div>
          <span class="eyebrow">ANÁLISES SALVAS</span>
          <h2>Jurimetria das análises</h2>
          <p>
            Filtros e estatísticas somente sobre processos
            já analisados e salvos no Veredicta.
          </p>
        </div>
        <button type="button" class="secondary" id="analyticsRefresh">
          Atualizar
        </button>
      </div>

      <div class="analytics-filters">
        <label class="analytics-check">
          <input id="filterSentence" type="checkbox" />
          Somente com sentença
        </label>

        <label>
          Leitura
          <select id="filterRead">
            <option value="todas">Todas</option>
            <option value="lidas">Somente lidas</option>
            <option value="nao_lidas">Somente não lidas</option>
          </select>
        </label>

        <label>
          Empresa
          <select id="filterCompany">
            <option value="">Todas</option>
          </select>
        </label>

        <label>
          Conduta
          <select id="filterConduct">
            <option value="">Todas</option>
          </select>
        </label>

        <label class="analytics-check">
          <input id="filterRepeatCompanies" type="checkbox" />
          Somente empresas reincidentes
        </label>
      </div>

      <div class="metrics-grid analytics-metrics">
        <article class="metric-card">
          <span>Análises no filtro</span>
          <strong id="analyticsTotal">—</strong>
          <small>Processos já analisados</small>
        </article>
        <article class="metric-card">
          <span>Com sentença</span>
          <strong id="analyticsSentence">—</strong>
          <small>Dentro do filtro atual</small>
        </article>
        <article class="metric-card">
          <span>Empresas reincidentes</span>
          <strong id="analyticsRepeatCompanies">—</strong>
          <small>Dentro do filtro atual</small>
        </article>
        <article class="metric-card">
          <span>Valor mediano</span>
          <strong id="analyticsMedian">—</strong>
          <small>Conforme filtro atual</small>
        </article>
      </div>

      <div class="analytics-panels">
        <div>
          <h3>Empresas reincidentes</h3>
          <div id="companyRecurrence"></div>
        </div>
        <div>
          <h3>Condutas recorrentes</h3>
          <div id="conductRecurrence"></div>
        </div>
      </div>

      <div class="analytics-capacity">
        <h3>Valores × capacidade econômica</h3>
        <div id="capacityRelation"></div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Processo</th>
              <th>Empresa ré</th>
              <th>Sentença</th>
              <th>Condutas</th>
              <th>Valor</th>
              <th>Leitura</th>
            </tr>
          </thead>
          <tbody id="analyticsBody"></tbody>
        </table>
      </div>

      <p id="analyticsInfo" class="analytics-info"></p>
    `;

    main.appendChild(section);

    $a("analyticsRefresh").addEventListener("click", loadAnalytics);

    [
      "filterSentence",
      "filterRead",
      "filterCompany",
      "filterConduct",
      "filterRepeatCompanies"
    ].forEach((id) => {
      $a(id).addEventListener("change", loadAnalytics);
    });

    $a("analyticsBody").addEventListener("click", handleReadToggle);
  }

  function queryString() {
    const params = new URLSearchParams();

    if ($a("filterSentence").checked) {
      params.set("somente_sentenca", "true");
    }

    params.set("leitura", $a("filterRead").value || "todas");

    if ($a("filterCompany").value) {
      params.set("empresa", $a("filterCompany").value);
    }

    if ($a("filterConduct").value) {
      params.set("conduta", $a("filterConduct").value);
    }

    if ($a("filterRepeatCompanies").checked) {
      params.set("somente_reincidentes", "true");
      params.set("min_reincidencia", "2");
    }

    params.set("limit", "500");
    return params.toString();
  }

  function renderFilterOptions(payload) {
    const companySelect = $a("filterCompany");
    const currentCompany = companySelect.value;
    const companies = Array.isArray(payload.companies)
      ? payload.companies
      : [];

    companySelect.innerHTML = `
      <option value="">Todas</option>
      ${companies.map((item) => `
        <option value="${esc(item.empresa_normalizada || "")}">
          ${esc(item.empresa || item.empresa_normalizada || "—")}
          (${Number(item.processos || 0)})
        </option>
      `).join("")}
    `;

    if (
      Array.from(companySelect.options)
        .some((option) => option.value === currentCompany)
    ) {
      companySelect.value = currentCompany;
    }

    const conductSelect = $a("filterConduct");
    const currentConduct = conductSelect.value;
    const conducts = Array.isArray(payload.conducts)
      ? payload.conducts
      : [];

    conductSelect.innerHTML = `
      <option value="">Todas</option>
      ${conducts.map((item) => `
        <option value="${esc(item.conduta || "")}">
          ${esc(item.conduta || "—")}
          (${Number(item.processos || 0)})
        </option>
      `).join("")}
    `;

    if (
      Array.from(conductSelect.options)
        .some((option) => option.value === currentConduct)
    ) {
      conductSelect.value = currentConduct;
    }
  }

  function renderMetrics(payload) {
    const metrics = payload.metrics || {};

    $a("analyticsTotal").textContent =
      Number(metrics.analisadas || 0).toLocaleString("pt-BR");
    $a("analyticsSentence").textContent =
      Number(metrics.com_sentenca || 0).toLocaleString("pt-BR");
    $a("analyticsRepeatCompanies").textContent =
      Number(metrics.empresas_reincidentes || 0).toLocaleString("pt-BR");
    $a("analyticsMedian").textContent =
      money(metrics.valor_mediano_centavos);
  }

  function renderRecurrence(payload) {
    const companiesSource = Array.isArray(payload.filtered_companies)
      ? payload.filtered_companies
      : (Array.isArray(payload.companies) ? payload.companies : []);

    const companies = companiesSource.filter(
      (item) => Number(item.processos || 0) >= 2
    );

    $a("companyRecurrence").innerHTML = companies.length
      ? companies.slice(0, 10).map((item) => `
          <div class="analytics-stat-row">
            <strong>${esc(item.empresa || "—")}</strong>
            <span>${Number(item.processos || 0)} processos</span>
            <small>mediana ${esc(money(item.valor_mediano_centavos))}</small>
          </div>
        `).join("")
      : `<p class="empty-note">Nenhuma reincidência identificada no filtro.</p>`;

    const conducts = Array.isArray(payload.filtered_conducts)
      ? payload.filtered_conducts
      : (Array.isArray(payload.conducts) ? payload.conducts : []);

    $a("conductRecurrence").innerHTML = conducts.length
      ? conducts.slice(0, 10).map((item) => `
          <div class="analytics-stat-row">
            <strong>${esc(item.conduta || "—")}</strong>
            <span>${Number(item.processos || 0)} processos</span>
            <small>mediana ${esc(money(item.valor_mediano_centavos))}</small>
          </div>
        `).join("")
      : `<p class="empty-note">Nenhuma conduta classificada no filtro.</p>`;
  }

  function renderCapacity(payload) {
    const relation = payload.capacity_relation || {};
    const groups = Array.isArray(relation.grupos)
      ? relation.grupos
      : [];

    if (!groups.length) {
      $a("capacityRelation").innerHTML = `
        <p class="empty-note">
          Ainda não há dados objetivos de capacidade econômica
          vinculados às empresas analisadas neste filtro.
        </p>
        <small>
          O Veredicta não presume capacidade econômica pelo nome
          ou pela quantidade de processos.
        </small>
      `;
      return;
    }

    $a("capacityRelation").innerHTML = groups.map((item) => `
      <div class="analytics-stat-row">
        <strong>${esc(item.faixa || "—")}</strong>
        <span>
          ${Number(item.processos_com_valor || 0)} processos com valor
        </span>
        <small>mediana ${esc(money(item.valor_mediano_centavos))}</small>
      </div>
    `).join("");
  }

  function renderRows(payload) {
    const rows = Array.isArray(payload.items)
      ? payload.items
      : [];
    const body = $a("analyticsBody");

    if (!rows.length) {
      body.innerHTML = `
        <tr>
          <td colspan="6" class="empty-row">
            Nenhuma análise corresponde aos filtros.
          </td>
        </tr>
      `;
      return;
    }

    body.innerHTML = rows.map((row) => {
      const params = new URLSearchParams();
      params.set("tribunal", row.tribunal || "");
      params.set("numero", row.numero_processo || "");
      const href = `./processo.html?${params.toString()}`;

      const conducts = Array.isArray(row.condutas)
        ? row.condutas.join("; ")
        : "";

      return `
        <tr class="${row.lida ? "analysis-read" : "analysis-unread"}">
          <td class="process-number">
            <a href="${esc(href)}">
              ${esc(row.numero_processo || "—")}
            </a>
            <small>${esc(row.tribunal || "—")}</small>
          </td>
          <td>${esc(row.empresa_re || "—")}</td>
          <td>
            <span class="grade-badge">
              ${esc(sentenceText(row.tem_sentenca))}
            </span>
          </td>
          <td>${esc(conducts || "Não classificada")}</td>
          <td>${esc(money(row.valor_centavos))}</td>
          <td>
            <button
              type="button"
              class="secondary analytics-read-button"
              data-tribunal="${esc(row.tribunal || "")}"
              data-numero="${esc(row.numero_processo || "")}"
              data-read="${row.lida ? "true" : "false"}"
            >
              ${row.lida ? "Marcar não lida" : "Marcar lida"}
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function handleReadToggle(event) {
    const button = event.target.closest(".analytics-read-button");
    if (!button) return;

    const current = button.dataset.read === "true";
    const tribunal = button.dataset.tribunal || "";
    const numero = button.dataset.numero || "";

    button.disabled = true;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/analytics/analyses/` +
          `${encodeURIComponent(tribunal)}/` +
          `${encodeURIComponent(numero)}/read?value=${!current}`,
        {
          method: "POST",
          headers: authHeadersAnalytics()
        }
      );

      if (!response.ok) {
        throw new Error(`Erro HTTP ${response.status}`);
      }

      await loadAnalytics();
    } catch (error) {
      console.error(error);
      button.disabled = false;
    }
  }

  async function loadAnalytics() {
    const info = $a("analyticsInfo");
    info.textContent = "Carregando análises salvas...";

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/analytics/analyses?${queryString()}`,
        { headers: authHeadersAnalytics() }
      );

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(
          payload.detail || `Erro HTTP ${response.status}`
        );
      }

      renderFilterOptions(payload);
      renderMetrics(payload);
      renderRecurrence(payload);
      renderCapacity(payload);
      renderRows(payload);

      info.textContent =
        `${Number(payload.total || 0).toLocaleString("pt-BR")} ` +
        `análises correspondem aos filtros atuais.`;
    } catch (error) {
      console.error(error);
      info.textContent =
        "Não foi possível carregar a jurimetria das análises.";
    }
  }

  function init() {
    createSection();
    loadAnalytics();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
