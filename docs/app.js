/* global fetch */
(async function init() {
  const statsEl = document.getElementById("stats");
  const gridEl = document.getElementById("grid");
  const emptyEl = document.getElementById("empty");
  const updatedAtEl = document.getElementById("updatedAt");

  const qEl = document.getElementById("q");
  const sourceEl = document.getElementById("source");
  const genreEl = document.getElementById("genre");
  const yearEl = document.getElementById("year");
  const resetBtn = document.getElementById("resetBtn");
  const sortTitleBtn = document.getElementById("sortTitleBtn");
  const sortYearBtn = document.getElementById("sortYearBtn");
  const sortTitleArrow = document.getElementById("sortTitleArrow");
  const sortYearArrow = document.getElementById("sortYearArrow");
  const sortHint = document.getElementById("sortHint");

  const res = await fetch("./data/watchlist.json", { cache: "no-store" });
  if (!res.ok) {
    updatedAtEl.textContent = "Failed to load watchlist.json";
    return;
  }
  const data = await res.json();
  const movies = Array.isArray(data.movies) ? data.movies : [];
  const stats = data.stats || {};
  const allGenres = new Set();
  const allYears = new Set();
  for (const m of movies) {
    for (const g of (m.genres || [])) allGenres.add(String(g));
    if (m.year) allYears.add(Number(m.year));
  }

  updatedAtEl.textContent = "Last updated: " + (data.updated_at || "unknown");

  const statEntries = [
    ["Unique titles", stats.total || movies.length],
    ["On both", stats.both || 0],
    ["Letterboxd only", stats.letterboxd_only || 0],
    ["IMDb only", stats.imdb_only || 0],
    ["Posters resolved", stats.posters_resolved || 0],
    ["With year", stats.metadata_with_year || 0],
    ["With genre", stats.metadata_with_genres || 0]
  ];
  statsEl.innerHTML = statEntries.map(([k, v]) => (
    `<div class="stat"><strong>${v}</strong><span class="muted small">${k}</span></div>`
  )).join("");

  function sourceBadge(m) {
    if (m.source === "both") return '<span class="badge both">Both</span>';
    if (m.source === "letterboxd") return '<span class="badge lb">Letterboxd</span>';
    return '<span class="badge im">IMDb</span>';
  }

  function starBar(avg5) {
    if (avg5 == null || Number.isNaN(Number(avg5))) return "";
    const clamped = Math.max(0, Math.min(5, Number(avg5)));
    const pct = (clamped / 5) * 100;
    return `
      <div class="rating">
        <div class="rating-row">Avg: ${clamped.toFixed(2)} / 5</div>
        <div class="rating-bar"><div class="rating-fill" style="width:${pct}%"></div></div>
      </div>
    `;
  }

  let sortField = "title";
  let sortDir = "asc";

  function updateSortUi() {
    sortTitleBtn.classList.toggle("active", sortField === "title");
    sortYearBtn.classList.toggle("active", sortField === "year");
    sortTitleArrow.textContent = sortField === "title" ? (sortDir === "asc" ? "▲" : "▼") : "·";
    sortYearArrow.textContent = sortField === "year" ? (sortDir === "asc" ? "▲" : "▼") : "·";
    const fieldName = sortField === "title" ? "Name" : "Year";
    const dirLabel = sortDir === "asc" ? "ascending" : "descending";
    sortHint.textContent = `Sorting by ${fieldName} (${dirLabel})`;
  }

  function sortRows(rows) {
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortField === "year") {
        const ay = Number(a.year || 0);
        const by = Number(b.year || 0);
        cmp = ay - by;
        if (cmp === 0) cmp = String(a.title || "").localeCompare(String(b.title || ""));
      } else {
        cmp = String(a.title || "").localeCompare(String(b.title || ""));
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }

  function render() {
    const q = (qEl.value || "").trim().toLowerCase();
    const source = sourceEl.value;
    const genre = genreEl.value;
    const year = yearEl.value;

    let rows = movies.filter((m) => {
      if (source !== "all" && m.source !== source) return false;
      if (q && !String(m.title || "").toLowerCase().includes(q)) return false;
      if (genre !== "all" && !(m.genres || []).includes(genre)) return false;
      if (year !== "all" && Number(m.year || 0) !== Number(year)) return false;
      return true;
    });

    sortRows(rows);

    if (!rows.length) {
      gridEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      return;
    }
    emptyEl.classList.add("hidden");
    gridEl.innerHTML = rows.map((m) => `
      <article class="card">
        <div class="poster">
          ${m.poster_url ? `<img src="${m.poster_url}" alt="${m.title} poster" loading="lazy" referrerpolicy="no-referrer">` : "No poster"}
        </div>
        <div>
          <div class="title">${m.title || ""}</div>
          <div class="meta">${m.year || "Year ?"} · ${(m.genres || []).slice(0, 2).join(", ") || "Genre ?"}</div>
          <div class="meta">IMDb: ${m.rating_imdb_10 != null ? Number(m.rating_imdb_10).toFixed(1) + "/10" : "N/A"} · Letterboxd: ${m.rating_letterboxd_5 != null ? Number(m.rating_letterboxd_5).toFixed(2) + "/5" : "N/A"}</div>
          ${starBar(m.rating_avg_5)}
          ${sourceBadge(m)}
        </div>
      </article>
    `).join("");
  }

  genreEl.innerHTML += [...allGenres].sort((a, b) => a.localeCompare(b)).map((g) => `<option value="${g}">${g}</option>`).join("");
  yearEl.innerHTML += [...allYears].sort((a, b) => b - a).map((y) => `<option value="${y}">${y}</option>`).join("");

  [qEl, sourceEl, genreEl, yearEl].forEach((el) => el.addEventListener("input", render));
  sortTitleBtn.addEventListener("click", () => {
    if (sortField === "title") sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortField = "title"; sortDir = "asc"; }
    updateSortUi();
    render();
  });
  sortYearBtn.addEventListener("click", () => {
    if (sortField === "year") sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortField = "year"; sortDir = "desc"; }
    updateSortUi();
    render();
  });
  resetBtn.addEventListener("click", () => {
    qEl.value = "";
    sourceEl.value = "all";
    genreEl.value = "all";
    yearEl.value = "all";
    sortField = "title";
    sortDir = "asc";
    updateSortUi();
    render();
  });
  updateSortUi();
  render();
})();
