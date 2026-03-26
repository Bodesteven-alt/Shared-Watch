/* global fetch */
(async function init() {
  const statsEl = document.getElementById("stats");
  const gridEl = document.getElementById("grid");
  const emptyEl = document.getElementById("empty");
  const updatedAtEl = document.getElementById("updatedAt");

  const qEl = document.getElementById("q");
  const sourceEl = document.getElementById("source");
  const sortEl = document.getElementById("sort");
  const resetBtn = document.getElementById("resetBtn");

  const res = await fetch("./data/watchlist.json", { cache: "no-store" });
  if (!res.ok) {
    updatedAtEl.textContent = "Failed to load watchlist.json";
    return;
  }
  const data = await res.json();
  const movies = Array.isArray(data.movies) ? data.movies : [];
  const stats = data.stats || {};

  updatedAtEl.textContent = "Last updated: " + (data.updated_at || "unknown");

  const statEntries = [
    ["Unique titles", stats.total || movies.length],
    ["On both", stats.both || 0],
    ["Letterboxd only", stats.letterboxd_only || 0],
    ["IMDb only", stats.imdb_only || 0],
    ["Posters resolved", stats.posters_resolved || 0]
  ];
  statsEl.innerHTML = statEntries.map(([k, v]) => (
    `<div class="stat"><strong>${v}</strong><span class="muted small">${k}</span></div>`
  )).join("");

  function sourceBadge(m) {
    if (m.source === "both") return '<span class="badge both">Both</span>';
    if (m.source === "letterboxd") return '<span class="badge lb">Letterboxd</span>';
    return '<span class="badge im">IMDb</span>';
  }

  function render() {
    const q = (qEl.value || "").trim().toLowerCase();
    const source = sourceEl.value;
    const sort = sortEl.value;

    let rows = movies.filter((m) => {
      if (source !== "all" && m.source !== source) return false;
      if (q && !String(m.title || "").toLowerCase().includes(q)) return false;
      return true;
    });

    if (sort === "title") {
      rows.sort((a, b) => String(a.title).localeCompare(String(b.title)));
    } else if (sort === "source") {
      const rank = { both: 0, letterboxd: 1, imdb: 2 };
      rows.sort((a, b) => {
        const ra = rank[a.source] ?? 9;
        const rb = rank[b.source] ?? 9;
        if (ra !== rb) return ra - rb;
        return String(a.title).localeCompare(String(b.title));
      });
    }

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
          ${sourceBadge(m)}
        </div>
      </article>
    `).join("");
  }

  [qEl, sourceEl, sortEl].forEach((el) => el.addEventListener("input", render));
  resetBtn.addEventListener("click", () => {
    qEl.value = "";
    sourceEl.value = "all";
    sortEl.value = "title";
    render();
  });
  render();
})();
