(function () {
  "use strict";

  function parseData(canvas, name) {
    try { return JSON.parse(canvas.dataset[name] || "[]"); }
    catch (_error) { return []; }
  }

  function renderCharts() {
    if (typeof Chart === "undefined") return;
    const statusCanvas = document.getElementById("statusChart");
    if (statusCanvas) {
      const labels = parseData(statusCanvas, "labels");
      const values = parseData(statusCanvas, "values");
      new Chart(statusCanvas, {
        type: "doughnut",
        data: { labels, datasets: [{ data: values, borderWidth: 2, borderColor: "#ffffff" }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { usePointStyle: true, padding: 18 } } },
          cutout: "62%"
        }
      });
    }
    const seoCanvas = document.getElementById("seoChart");
    if (seoCanvas) {
      new Chart(seoCanvas, {
        type: "bar",
        data: { labels: parseData(seoCanvas, "labels"), datasets: [{ label: "Pages", data: parseData(seoCanvas, "values"), borderRadius: 7, maxBarThickness: 48 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#edf0f6" } }, x: { grid: { display: false } } }
        }
      });
    }
  }

  function enhanceTable(table) {
    if (!table || table.dataset.enhanced === "true") return;
    table.dataset.enhanced = "true";
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const allRows = Array.from(tbody.rows);
    // Do not paginate the single-cell empty-state row.
    if (allRows.length === 1 && allRows[0].cells.length === 1) return;

    const tableId = table.id;
    const footer = document.querySelector(`[data-table-footer="${CSS.escape(tableId)}"]`);
    let page = 0;
    const pageSize = 10;
    let sortColumn = -1;
    let sortDirection = 1;

    function currentRows() {
      const search = document.querySelector(`[data-table-search="${CSS.escape(tableId)}"]`);
      const filter = document.querySelector(`[data-table-filter="${CSS.escape(tableId)}"]`);
      const term = search ? search.value.trim().toLowerCase() : "";
      const filterValue = filter ? filter.value : "";
      return allRows.filter((row) => {
        const matchesText = !term || row.innerText.toLowerCase().includes(term);
        let matchesFilter = true;
        if (filterValue) {
          if (row.hasAttribute("data-status-group")) {
            const group = row.dataset.statusGroup;
            matchesFilter = filterValue === "unknown" ? group === "unknown" : group === filterValue;
          } else if (row.hasAttribute("data-link-type")) {
            matchesFilter = row.dataset.linkType === filterValue;
          }
        }
        return matchesText && matchesFilter;
      });
    }

    function render() {
      const filtered = currentRows();
      const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
      page = Math.max(0, Math.min(page, pages - 1));
      const visible = new Set(filtered.slice(page * pageSize, (page + 1) * pageSize));
      allRows.forEach((row) => { row.hidden = !visible.has(row); });
      if (footer) {
        footer.replaceChildren();
        const label = document.createElement("span");
        const start = filtered.length ? page * pageSize + 1 : 0;
        const end = Math.min((page + 1) * pageSize, filtered.length);
        label.textContent = `Showing ${start}–${end} of ${filtered.length}`;
        const buttons = document.createElement("div");
        buttons.className = "pagination-buttons";
        const prev = document.createElement("button");
        prev.type = "button"; prev.textContent = "Previous"; prev.disabled = page <= 0;
        prev.addEventListener("click", () => { page -= 1; render(); });
        const next = document.createElement("button");
        next.type = "button"; next.textContent = "Next"; next.disabled = page >= pages - 1;
        next.addEventListener("click", () => { page += 1; render(); });
        buttons.append(prev, next);
        footer.append(label, buttons);
      }
    }

    table.querySelectorAll("thead th[data-sort-type]").forEach((header, column) => {
      header.tabIndex = 0;
      header.setAttribute("role", "button");
      const sort = () => {
        if (sortColumn === column) sortDirection *= -1;
        else { sortColumn = column; sortDirection = 1; }
        const type = header.dataset.sortType;
        allRows.sort((a, b) => {
          const av = (a.cells[column]?.innerText || "").trim();
          const bv = (b.cells[column]?.innerText || "").trim();
          let comparison;
          if (type === "number") {
            const an = Number.parseFloat(av.replace(/[^\d.-]/g, ""));
            const bn = Number.parseFloat(bv.replace(/[^\d.-]/g, ""));
            comparison = (Number.isNaN(an) ? -Infinity : an) - (Number.isNaN(bn) ? -Infinity : bn);
          } else {
            comparison = av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
          }
          return comparison * sortDirection;
        });
        allRows.forEach((row) => tbody.appendChild(row));
        page = 0;
        render();
      };
      header.addEventListener("click", sort);
      header.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); }
      });
    });
    const search = document.querySelector(`[data-table-search="${CSS.escape(tableId)}"]`);
    const filter = document.querySelector(`[data-table-filter="${CSS.escape(tableId)}"]`);
    if (search) search.addEventListener("input", () => { page = 0; render(); });
    if (filter) filter.addEventListener("change", () => { page = 0; render(); });
    render();
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderCharts();
    document.querySelectorAll("table[data-enhance-table]").forEach(enhanceTable);
    const form = document.getElementById("scanForm");
    if (form) {
      form.addEventListener("submit", function () {
        const button = document.getElementById("scanSubmit");
        const spinner = document.getElementById("scanSpinner");
        const label = button.querySelector(".button-label");
        button.disabled = true;
        if (label) label.textContent = "Scanning website…";
        if (spinner) spinner.classList.remove("d-none");
      });
    }
  });
})();
