/* global fetch */
(async function init() {
  const statsEl = document.getElementById("stats");
  const statsToggle = document.getElementById("statsToggle");
  const gridEl = document.getElementById("grid");
  const emptyEl = document.getElementById("empty");
  const updatedAtEl = document.getElementById("updatedAt");

  const qEl = document.getElementById("q");
  const sourceEl = document.getElementById("source");
  const genreEl = document.getElementById("genre");
  const resetBtn = document.getElementById("resetBtn");
  const sortTitleBtn = document.getElementById("sortTitleBtn");
  const sortYearBtn = document.getElementById("sortYearBtn");
  const sortRatingBtn = document.getElementById("sortRatingBtn");
  const sortTitleUp = document.getElementById("sortTitleUp");
  const sortTitleDown = document.getElementById("sortTitleDown");
  const sortYearUp = document.getElementById("sortYearUp");
  const sortYearDown = document.getElementById("sortYearDown");
  const sortRatingUp = document.getElementById("sortRatingUp");
  const sortRatingDown = document.getElementById("sortRatingDown");

  let statsVisible = false;
  statsToggle.addEventListener("click", () => {
    statsVisible = !statsVisible;
    statsEl.classList.toggle("hidden", !statsVisible);
    statsToggle.textContent = statsVisible ? "Hide stats" : "Show stats";
  });

  const res = await fetch("./data/watchlist.json", { cache: "no-store" });
  if (!res.ok) {
    updatedAtEl.textContent = "Failed to load watchlist.json";
    return;
  }
  const data = await res.json();
  const movies = Array.isArray(data.movies) ? data.movies : [];
  const stats = data.stats || {};
  const allGenres = new Set();
  for (const m of movies) {
    for (const g of (m.genres || [])) allGenres.add(String(g));
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

  function starRating(avg5) {
    if (avg5 == null || Number.isNaN(Number(avg5))) return "";
    const rating = Math.max(0, Math.min(5, Number(avg5)));
    const starPath = "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z";
    let html = '<div class="stars">';
    for (let i = 0; i < 5; i++) {
      const fill = Math.max(0, Math.min(1, rating - i));
      const clipId = `clip-${Math.random().toString(36).slice(2, 9)}`;
      html += `
        <span class="star">
          <svg viewBox="0 0 24 24">
            <path class="star-empty" d="${starPath}"/>
          </svg>
          <svg viewBox="0 0 24 24" style="clip-path: inset(0 ${(1 - fill) * 100}% 0 0);">
            <path class="star-fill" d="${starPath}"/>
          </svg>
        </span>`;
    }
    html += '</div>';
    return html;
  }

  let sortField = "title";
  let sortDir = "asc";

  function updateSortUi() {
    sortTitleBtn.classList.toggle("active", sortField === "title");
    sortYearBtn.classList.toggle("active", sortField === "year");
    sortRatingBtn.classList.toggle("active", sortField === "rating");

    // Reset all arrows
    [sortTitleUp, sortTitleDown, sortYearUp, sortYearDown, sortRatingUp, sortRatingDown]
      .forEach(el => el.classList.remove("active"));

    // Highlight active arrow
    if (sortField === "title") {
      (sortDir === "asc" ? sortTitleUp : sortTitleDown).classList.add("active");
    } else if (sortField === "year") {
      (sortDir === "asc" ? sortYearUp : sortYearDown).classList.add("active");
    } else if (sortField === "rating") {
      (sortDir === "asc" ? sortRatingUp : sortRatingDown).classList.add("active");
    }
  }

  function sortRows(rows) {
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortField === "year") {
        const ay = Number(a.year || 0);
        const by = Number(b.year || 0);
        cmp = ay - by;
        if (cmp === 0) cmp = String(a.title || "").localeCompare(String(b.title || ""));
      } else if (sortField === "rating") {
        const ar = a.rating_avg_5 != null ? Number(a.rating_avg_5) : -1;
        const br = b.rating_avg_5 != null ? Number(b.rating_avg_5) : -1;
        cmp = ar - br;
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

    let rows = movies.filter((m) => {
      if (source !== "all" && m.source !== source) return false;
      if (q && !String(m.title || "").toLowerCase().includes(q)) return false;
      if (genre !== "all" && !(m.genres || []).includes(genre)) return false;
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
          ${starRating(m.rating_avg_5)}
          ${sourceBadge(m)}
        </div>
      </article>
    `).join("");
  }

  genreEl.innerHTML += [...allGenres].sort((a, b) => a.localeCompare(b)).map((g) => `<option value="${g}">${g}</option>`).join("");

  [qEl, sourceEl, genreEl].forEach((el) => el.addEventListener("input", render));
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
  sortRatingBtn.addEventListener("click", () => {
    if (sortField === "rating") sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortField = "rating"; sortDir = "desc"; }
    updateSortUi();
    render();
  });
  resetBtn.addEventListener("click", () => {
    qEl.value = "";
    sourceEl.value = "all";
    genreEl.value = "all";
    sortField = "title";
    sortDir = "asc";
    updateSortUi();
    render();
  });
  updateSortUi();
  render();
})();
