const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const root = document.documentElement;
const body = document.body;
const currentView = document.querySelector("[data-dashboard-view]")?.dataset.dashboardView || "";

function applyTheme(theme) {
  const value = theme || "aurora";
  body.dataset.theme = value;
  window.localStorage.setItem("amonora-dashboard-theme", value);
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.classList.toggle("active", button.dataset.themeValue === value);
  });
}

function initTheme() {
  const saved = window.localStorage.getItem("amonora-dashboard-theme") || "aurora";
  applyTheme(saved);

  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeValue));
  });

  const toggle = document.querySelector("[data-settings-toggle]");
  const panel = document.querySelector("[data-settings-panel]");
  if (!toggle || !panel) return;

  toggle.addEventListener("click", () => {
    const open = panel.hidden;
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("click", (event) => {
    if (panel.hidden) return;
    if (panel.contains(event.target) || toggle.contains(event.target)) return;
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  });
}

function initReveal() {
  const revealNodes = [...document.querySelectorAll(".reveal")];
  revealNodes.forEach((node, index) => {
    node.style.transitionDelay = `${Math.min(index * 40, 260)}ms`;
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
      }
    });
  }, { threshold: 0.1 });

  revealNodes.forEach((node) => observer.observe(node));
}

function initClock() {
  const timeTargets = document.querySelectorAll("[data-live-time]");
  const dateTargets = document.querySelectorAll("[data-live-date]");
  if (!timeTargets.length && !dateTargets.length) return;

  const timeFormatter = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const render = () => {
    const now = new Date();
    const timeValue = timeFormatter.format(now);
    const dateValue = dateFormatter.format(now);

    timeTargets.forEach((node) => {
      node.textContent = timeValue;
    });
    dateTargets.forEach((node) => {
      node.textContent = dateValue;
    });
  };

  render();
  window.setInterval(render, 1_000);
}

function initLiveSearch() {
  document.querySelectorAll("[data-live-search]").forEach((form) => {
    const textInputs = form.querySelectorAll('input[type="text"], input[type="search"]');
    const selects = form.querySelectorAll("select");
    let timer = null;

    const submitForm = () => form.requestSubmit();

    textInputs.forEach((input) => {
      input.addEventListener("input", () => {
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(submitForm, 180);
      });
    });

    selects.forEach((select) => {
      select.addEventListener("change", submitForm);
    });
  });
}

function initRowLinks() {
  document.querySelectorAll("[data-row-link]").forEach((row) => {
    row.addEventListener("click", (event) => {
      const interactive = event.target.closest("a, button, input, select, textarea, label, form");
      if (interactive) return;
      const href = row.dataset.rowLink;
      if (href) {
        window.location.href = href;
      }
    });
  });
}

function initModals() {
  const openModal = (id) => {
    const modal = document.querySelector(`[data-modal="${id}"]`);
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("modal-open");
  };

  const closeModal = (id) => {
    const modal = document.querySelector(`[data-modal="${id}"]`);
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove("modal-open");
  };

  document.querySelectorAll("[data-modal-open]").forEach((button) => {
    button.addEventListener("click", () => openModal(button.dataset.modalOpen));
  });

  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.modalClose));
  });

  document.querySelectorAll("[data-modal]").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal || event.target.classList.contains("modal-backdrop")) {
        modal.hidden = true;
        document.body.classList.remove("modal-open");
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-modal]").forEach((modal) => {
      if (!modal.hidden) {
        modal.hidden = true;
      }
    });
    document.body.classList.remove("modal-open");
  });
}

function animateCount(node) {
  const target = Number(node.dataset.value || "0");
  const duration = prefersReducedMotion ? 0 : 950;
  const suffix = node.dataset.suffix || "";

  if (!Number.isFinite(target)) {
    node.textContent = node.dataset.value || "0";
    return;
  }

  if (!duration) {
    node.textContent = `${target}${suffix}`;
    return;
  }

  const start = performance.now();
  const tick = (time) => {
    const progress = Math.min((time - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = `${Math.round(target * eased)}${suffix}`;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function initCounts() {
  document.querySelectorAll(".count-up").forEach(animateCount);
}

function setMeterState(bar, value) {
  bar.classList.remove("state-warning", "state-critical");
  if (value >= 85) {
    bar.classList.add("state-critical");
  } else if (value >= 70) {
    bar.classList.add("state-warning");
  }
}

function initMeterBars(scope = document) {
  scope.querySelectorAll(".meter-fill").forEach((bar, index) => {
    const value = Math.max(0, Math.min(100, Number(bar.dataset.value || "0")));
    const delay = prefersReducedMotion ? 0 : index * 60;
    setMeterState(bar, value);
    window.setTimeout(() => {
      bar.style.width = `${value}%`;
    }, delay);
  });
}

function initRadialRings(scope = document) {
  scope.querySelectorAll(".radial-ring").forEach((ring, index) => {
    const target = Math.max(0, Math.min(100, Number(ring.dataset.progress || "0")));
    if (prefersReducedMotion) {
      ring.style.setProperty("--progress", target);
      return;
    }

    const duration = 900;
    const delay = index * 90;
    window.setTimeout(() => {
      const start = performance.now();
      const step = (time) => {
        const progress = Math.min((time - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        ring.style.setProperty("--progress", `${target * eased}`);
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, delay);
  });
}

function renderSparkChart(chart, animate = true) {
  const rect = chart.getBoundingClientRect();
  if (!chart.isConnected || !rect.width || !rect.height) {
    if (!chart.dataset.chartPending) {
      chart.dataset.chartPending = "true";
      requestAnimationFrame(() => {
        delete chart.dataset.chartPending;
        renderSparkChart(chart, animate);
      });
    }
    return;
  }

  const tone = chart.dataset.tone || "default";
  const values = (chart.dataset.chartValues || "")
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
  const labels = (chart.dataset.chartLabels || "").split(",").map((item) => item.trim());
  const max = Math.max(...values, 1);

  chart.innerHTML = "";

  values.forEach((value, index) => {
    const column = document.createElement("div");
    column.className = "spark-col";

    const bar = document.createElement("span");
    bar.className = "spark-bar";
    bar.title = `${labels[index] || index + 1}: ${value}`;
    if (tone === "load") {
      if (value >= 85) {
        bar.classList.add("critical");
      } else if (value >= 70) {
        bar.classList.add("warning");
      }
    }

    const valueLabel = document.createElement("strong");
    valueLabel.textContent = String(value);

    const textLabel = document.createElement("span");
    textLabel.className = "spark-label";
    textLabel.textContent = labels[index] || String(index + 1);

    column.append(valueLabel, bar, textLabel);
    chart.append(column);

    const height = Math.max(14, (value / max) * 100);
    window.setTimeout(() => {
      bar.style.height = `${height}%`;
    }, !animate || prefersReducedMotion ? 0 : 140 + index * 90);
  });
}

function initSparkCharts(scope = document) {
  scope.querySelectorAll(".spark-chart").forEach((chart) => renderSparkChart(chart, true));
}

function updateHealthBox(box, state) {
  box.classList.remove("healthy", "warning", "critical", "unknown");
  if (state) box.classList.add(state);
}

function serverStateLabel(state) {
  if (state === "critical") return "Критичная нагрузка";
  if (state === "warning") return "Повышенная нагрузка";
  if (state === "healthy") return "Стабильная нагрузка";
  return "Статус неизвестен";
}

function updateServerSummary(summary) {
  const mapping = {
    total: summary.total,
    active: summary.active,
    maintenance: summary.maintenance,
    clients: summary.xui_clients,
    critical: summary.critical,
    warning: summary.warning,
  };

  Object.entries(mapping).forEach(([key, value]) => {
    document.querySelectorAll(`[data-summary-${key}]`).forEach((node) => {
      node.textContent = String(value);
    });
  });

  const overviewChart = document.querySelector("[data-server-overview-chart]");
  if (overviewChart) {
    overviewChart.dataset.chartValues = `${summary.avg_cpu},${summary.avg_memory},${summary.avg_disk},${summary.critical}`;
    renderSparkChart(overviewChart, false);
  }

  const total = Number(summary.total || 0);
  const activePercent = total ? Math.round((Number(summary.active || 0) / total) * 100) : 0;
  const criticalPercent = total ? Math.round((Number(summary.critical || 0) / total) * 100) : 0;
  const activeRing = document.querySelector('[data-summary-ring="active"]');
  const criticalRing = document.querySelector('[data-summary-ring="critical"]');
  if (activeRing) activeRing.style.setProperty("--progress", activePercent);
  if (criticalRing) criticalRing.style.setProperty("--progress", criticalPercent);
}

function updateServerCards(snapshots) {
  const snapshotMap = new Map(snapshots.map((item) => [String(item.id), item]));

  document.querySelectorAll("[data-server-card]").forEach((card) => {
    const server = snapshotMap.get(card.dataset.serverId);
    if (!server) return;

    card.classList.remove("state-healthy", "state-warning", "state-critical", "state-unknown");
    card.classList.add(`state-${server.overall_state || "unknown"}`);

    const statusNode = card.querySelector("[data-server-status]");
    statusNode.textContent = server.status;
    statusNode.className = `status ${server.status}`;

    card.querySelector("[data-server-name]").textContent = server.name;
    card.querySelector("[data-server-country]").textContent = server.country_name;
    card.querySelector("[data-server-ip]").textContent = server.public_ip;
    card.querySelector("[data-server-provider]").textContent = server.provider;

    const warningNode = card.querySelector("[data-server-warning]");
    warningNode.className = `server-warning state-${server.overall_state || "unknown"}`;
    card.querySelector("[data-server-state-label]").textContent = serverStateLabel(server.overall_state);
    card.querySelector("[data-server-message]").textContent = server.status_message;

    const serviceGrid = card.querySelector("[data-server-service-grid]");
    if (serviceGrid && Array.isArray(server.service_pills)) {
      serviceGrid.innerHTML = "";
      server.service_pills.forEach((pill) => {
        const node = document.createElement("span");
        node.className = "micro-pill";
        node.textContent = `${pill.label} · ${pill.value}`;
        serviceGrid.append(node);
      });
    }

    const cpuValue = Number(server.cpu_percent || 0);
    const memoryValue = Number(server.memory_used_percent || 0);
    const diskValue = Number(server.disk_used_percent || 0);

    card.querySelector("[data-server-cpu]").textContent = `${cpuValue}%`;
    card.querySelector("[data-server-memory]").textContent = `${memoryValue}%`;
    card.querySelector("[data-server-disk]").textContent = `${diskValue}%`;
    card.querySelector("[data-server-load]").textContent = server.load || "—";
    card.querySelector("[data-server-uptime]").textContent = server.uptime || "—";
    const pingNode = card.querySelector("[data-server-ping]");
    if (pingNode) pingNode.textContent = server.ping_label || "—";
    const rxNode = card.querySelector("[data-server-rx]");
    if (rxNode) rxNode.textContent = server.rx_label || "—";
    const txNode = card.querySelector("[data-server-tx]");
    if (txNode) txNode.textContent = server.tx_label || "—";

    [["cpu", server.cpu_state, cpuValue], ["memory", server.memory_state, memoryValue], ["disk", server.disk_state, diskValue], ["load", server.overall_state, 0], ["ping", server.ping_state, 0]].forEach(([name, state, value]) => {
      const box = card.querySelector(`[data-health-box="${name}"]`);
      if (box) updateHealthBox(box, state);
      const meter = card.querySelector(`[data-server-meter="${name}"]`);
      if (meter) {
        meter.dataset.value = String(value);
        setMeterState(meter, value);
        meter.style.width = `${Math.max(0, Math.min(100, value))}%`;
      }
    });

    const chart = card.querySelector("[data-server-chart]");
    if (chart) {
      chart.dataset.chartValues = `${cpuValue},${memoryValue},${diskValue},${server.warning_count || 0}`;
      renderSparkChart(chart, false);
    }
  });

  const detailCard = document.querySelector("[data-selected-server]");
  if (detailCard) {
    const server = snapshotMap.get(detailCard.dataset.serverId);
    if (server) {
      detailCard.querySelector("[data-detail-server-name]").textContent = server.name;
      detailCard.querySelector("[data-detail-server-country]").textContent = server.country_name;
      detailCard.querySelector("[data-detail-server-ip]").textContent = server.public_ip;
      detailCard.querySelector("[data-detail-server-provider]").textContent = server.provider;
      detailCard.querySelector("[data-detail-server-status]").textContent = server.status;
      detailCard.querySelector("[data-detail-server-ping]").textContent = server.ping_label || "—";
      detailCard.querySelector("[data-detail-server-uptime]").textContent = server.uptime || "—";
      detailCard.querySelector("[data-detail-server-xui]").textContent = server.xray_service_status || server.awg_service_status || server.xui_service_status || server.xui_status || "n/a";
      detailCard.querySelector("[data-detail-server-cpu]").textContent = `${Number(server.cpu_percent || 0)}%`;
      detailCard.querySelector("[data-detail-server-cpu-count]").textContent = String(server.cpu_count ?? "—");
      detailCard.querySelector("[data-detail-server-memory]").textContent = `${Number(server.memory_used_percent || 0)}%`;
      detailCard.querySelector("[data-detail-server-memory-total]").textContent = String(server.memory_total_gb ?? "—");
      detailCard.querySelector("[data-detail-server-disk]").textContent = `${Number(server.disk_used_percent || 0)}%`;
      detailCard.querySelector("[data-detail-server-disk-total]").textContent = String(server.disk_total_gb ?? "—");
      detailCard.querySelector("[data-detail-server-clients]").textContent = String(server.xui_clients ?? "—");
    }
  }
}

function initServerRefresh() {
  if (currentView !== "servers") return;

  const button = document.querySelector("[data-server-refresh]");
  if (!button) return;

  const refresh = async () => {
    const url = button.dataset.refreshUrl || "/dashboard/api/servers/snapshots?force=1";
    const previousLabel = button.textContent;
    button.disabled = true;
    button.textContent = "Обновляем...";

    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error("Не удалось получить свежие метрики");
      }
      const payload = await response.json();
      updateServerSummary(payload.summary || {});
      updateServerCards(payload.snapshots || []);
      showInlineNotice("Метрики серверов обновлены", "ok");
    } catch {
      showInlineNotice("Не удалось обновить серверные метрики", "error");
    } finally {
      button.disabled = false;
      button.textContent = previousLabel;
    }
  };

  button.addEventListener("click", refresh);
}

function showInlineNotice(message, type = "ok") {
  let banner = document.querySelector("[data-inline-notice]");
  if (!banner) {
    banner = document.createElement("div");
    banner.dataset.inlineNotice = "true";
    banner.className = "flash reveal visible";
    const intro = document.querySelector(".page-intro");
    if (intro?.parentNode) {
      intro.parentNode.insertBefore(banner, intro.nextSibling);
    } else {
      document.querySelector(".dashboard-shell")?.prepend(banner);
    }
  }

  banner.classList.remove("flash-ok", "flash-error");
  banner.classList.add(type === "error" ? "flash-error" : "flash-ok");
  banner.textContent = message;
}

function initServerStatusForms() {
  document.querySelectorAll("[data-server-status-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const button = form.querySelector("[data-status-submit]");
      const action = form.dataset.apiAction;
      if (!action) {
        form.submit();
        return;
      }

      const previousLabel = button?.textContent || "";
      if (button) {
        button.disabled = true;
        button.textContent = "Обновление...";
      }

      try {
        const response = await fetch(action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });

        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Не удалось обновить статус");
        }

        updateServerSummary(payload.summary || {});
        updateServerCards(payload.snapshots || []);
        showInlineNotice(payload.notice || "Статус сервера обновлён", "ok");
      } catch (error) {
        showInlineNotice(error.message || "Не удалось обновить статус", "error");
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = previousLabel;
        }
      }
    });
  });
}

function initDocsFilter(scope = document) {
  const input = scope.querySelector("[data-docs-filter]");
  if (!input) return;

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    scope.querySelectorAll("[data-docs-group]").forEach((group) => {
      let visible = 0;
      group.querySelectorAll("[data-docs-link]").forEach((link) => {
        const text = link.textContent.toLowerCase();
        const show = !query || text.includes(query);
        link.hidden = !show;
        if (show) visible += 1;
      });
      group.hidden = visible === 0;
    });
  });
}

async function replaceDocsSection(url) {
  const response = await fetch(url, {
    headers: { Accept: "text/html" },
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error("Не удалось загрузить статью");
  }

  const html = await response.text();
  const parser = new DOMParser();
  const nextDocument = parser.parseFromString(html, "text/html");
  const nextSection = nextDocument.querySelector("[data-docs-view]");
  const currentSection = document.querySelector("[data-docs-view]");
  if (!nextSection || !currentSection) {
    window.location.href = url;
    return;
  }

  currentSection.replaceWith(nextSection);
  window.history.pushState({}, "", url);
  initDocsFilter(document);
  initDocsNavigation();
  document.querySelector("[data-docs-view]")?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "start" });
}

function initDocsNavigation() {
  if (currentView !== "docs") return;

  initDocsFilter(document);
  document.querySelectorAll("[data-docs-link]").forEach((link) => {
    if (link.dataset.docsBound === "true") return;
    link.dataset.docsBound = "true";
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await replaceDocsSection(link.href);
      } catch {
        window.location.href = link.href;
      }
    });
  });
}

initTheme();
initReveal();
initClock();
initLiveSearch();
initCounts();
initMeterBars();
initRadialRings();
initSparkCharts();
initServerRefresh();
initServerStatusForms();
initRowLinks();
initModals();
initDocsNavigation();
