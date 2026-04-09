/* global fetch */
(async function init() {
  const gridEl = document.getElementById("grid");
  const emptyEl = document.getElementById("empty");
  const updatedDateEl = document.getElementById("updatedDate");
  const updatedRelEl = document.getElementById("updatedRel");
  const updatedSepEl = document.getElementById("updatedSep");

  const filterLb = document.getElementById("filterLb");
  const filterBoth = document.getElementById("filterBoth");
  const filterImdb = document.getElementById("filterImdb");
  const countLb = document.getElementById("countLb");
  const countBoth = document.getElementById("countBoth");
  const countImdb = document.getElementById("countImdb");

  const sortTitleBtn = document.getElementById("sortTitleBtn");
  const sortYearBtn = document.getElementById("sortYearBtn");
  const sortRatingBtn = document.getElementById("sortRatingBtn");
  const sortTitleUp = document.getElementById("sortTitleUp");
  const sortTitleDown = document.getElementById("sortTitleDown");
  const sortYearUp = document.getElementById("sortYearUp");
  const sortYearDown = document.getElementById("sortYearDown");
  const sortRatingUp = document.getElementById("sortRatingUp");
  const sortRatingDown = document.getElementById("sortRatingDown");

  const genreBtn = document.getElementById("genreBtn");
  const genrePopup = document.getElementById("genrePopup");

  const SOURCE_KEYS = ["letterboxd", "both", "imdb"];
  const filterBySource = { letterboxd: filterLb, both: filterBoth, imdb: filterImdb };

  let dataUpdatedAtMs = null;

  function relativePhrase(targetMs) {
    const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    const diffSec = Math.round((targetMs - Date.now()) / 1000);
    const a = Math.abs(diffSec);
    if (a < 45) return rtf.format(0, "second");
    if (a < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
    if (a < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
    if (a < 604800) return rtf.format(Math.round(diffSec / 86400), "day");
    if (a < 2629800) return rtf.format(Math.round(diffSec / 604800), "week");
    if (a < 31557600 * 2) return rtf.format(Math.round(diffSec / 2629800), "month");
    return rtf.format(Math.round(diffSec / 31557600), "year");
  }

  function updateFooterDates() {
    if (!dataUpdatedAtMs || !updatedDateEl) return;
    const d = new Date(dataUpdatedAtMs);
    updatedDateEl.textContent = d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    if (updatedRelEl && updatedSepEl) {
      updatedRelEl.textContent = `Updated ${relativePhrase(dataUpdatedAtMs)}`;
      updatedRelEl.hidden = false;
      updatedSepEl.hidden = false;
    }
  }

  function clearLoadingState() {
    gridEl.classList.remove("grid--loading");
    gridEl.removeAttribute("aria-busy");
  }

  function failLoad(message) {
    clearLoadingState();
    gridEl.innerHTML = "";
    if (updatedDateEl) updatedDateEl.textContent = message;
    if (updatedRelEl) {
      updatedRelEl.textContent = "";
      updatedRelEl.hidden = true;
    }
    if (updatedSepEl) updatedSepEl.hidden = true;
  }

  const res = await fetch("./data/watchlist.json", { cache: "no-store" });
  if (!res.ok) {
    failLoad("Failed to load list.");
    return;
  }
  let data;
  try {
    data = await res.json();
  } catch {
    failLoad("Invalid list data.");
    return;
  }
  const movies = Array.isArray(data.movies) ? data.movies : [];

  if (data.updated_at) {
    dataUpdatedAtMs = new Date(data.updated_at).getTime();
    if (!Number.isFinite(dataUpdatedAtMs)) dataUpdatedAtMs = null;
  }

  if (dataUpdatedAtMs) {
    updateFooterDates();
  } else if (updatedDateEl) {
    updatedDateEl.textContent = "Unknown date";
    if (updatedRelEl) updatedRelEl.hidden = true;
    if (updatedSepEl) updatedSepEl.hidden = true;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") updateFooterDates();
  });

  let lbCount = 0;
  let bothCount = 0;
  let imdbCount = 0;
  for (const m of movies) {
    if (m.source === "letterboxd") lbCount++;
    else if (m.source === "both") bothCount++;
    else if (m.source === "imdb") imdbCount++;
  }
  countLb.textContent = lbCount;
  countBoth.textContent = bothCount;
  countImdb.textContent = imdbCount;

  const allGenres = new Set();
  for (const m of movies) {
    for (const g of m.genres || []) allGenres.add(String(g));
  }
  const sortedGenres = [...allGenres].sort((a, b) => a.localeCompare(b));

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  genrePopup.innerHTML =
    `<button type="button" class="genre-option active" data-genre="all" role="option" aria-selected="true">All Genres</button>` +
    sortedGenres
      .map(
        (g) =>
          `<button type="button" class="genre-option" data-genre="${escapeAttr(g)}" role="option" aria-selected="false">${escapeAttr(g)}</button>`,
      )
      .join("");

  let selectedGenre = "all";
  let sortField = "title";
  let sortDir = "asc";

  const genreTruncateMq = window.matchMedia("(max-width: 640px)");

  function isGenreOpen() {
    return !genrePopup.classList.contains("hidden");
  }

  function setGenreOpen(open, opts) {
    const focusFirstOption = opts && opts.focusFirstOption;
    const focusButtonOnClose = opts && opts.focusButtonOnClose;
    genrePopup.classList.toggle("hidden", !open);
    genreBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && focusFirstOption) {
      const first = genrePopup.querySelector(".genre-option");
      if (first) first.focus();
    }
    if (!open && focusButtonOnClose) {
      genreBtn.focus({ preventScroll: true });
    }
  }

  function syncGenreAriaSelected() {
    genrePopup.querySelectorAll(".genre-option").forEach((el) => {
      const on = el.dataset.genre === selectedGenre;
      el.classList.toggle("active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function allSourcesActive() {
    return filterLb.classList.contains("active") &&
      filterBoth.classList.contains("active") &&
      filterImdb.classList.contains("active");
  }

  function isDefaultState() {
    return (
      selectedGenre === "all" &&
      sortField === "title" &&
      sortDir === "asc" &&
      allSourcesActive()
    );
  }

  function applyUrlState() {
    const params = new URLSearchParams(window.location.search);
    const srcRaw = params.get("src");
    if (srcRaw !== null && srcRaw !== "") {
      const want = new Set(
        srcRaw
          .split(",")
          .map((s) => s.trim().toLowerCase())
          .filter((s) => SOURCE_KEYS.includes(s)),
      );
      if (want.size > 0) {
        for (const key of SOURCE_KEYS) {
          filterBySource[key].classList.toggle("active", want.has(key));
        }
      }
    }

    const gRaw = params.get("genre");
    if (gRaw) {
      const decoded = decodeURIComponent(gRaw.trim());
      if (decoded === "all" || decoded === "") {
        selectedGenre = "all";
      } else if (sortedGenres.includes(decoded)) {
        selectedGenre = decoded;
      }
    }

    const s = params.get("sort");
    if (s === "title" || s === "year" || s === "rating") sortField = s;
    const d = params.get("dir");
    if (d === "asc" || d === "desc") sortDir = d;
  }

  function syncUrl() {
    if (isDefaultState()) {
      const url = `${window.location.pathname}${window.location.hash}`;
      if (window.location.search) {
        history.replaceState(null, "", url);
      }
      return;
    }
    const p = new URLSearchParams();
    if (!allSourcesActive()) {
      const active = [];
      if (filterLb.classList.contains("active")) active.push("letterboxd");
      if (filterBoth.classList.contains("active")) active.push("both");
      if (filterImdb.classList.contains("active")) active.push("imdb");
      if (active.length) p.set("src", active.join(","));
    }
    if (selectedGenre !== "all") p.set("genre", selectedGenre);
    if (sortField !== "title" || sortDir !== "asc") {
      p.set("sort", sortField);
      p.set("dir", sortDir);
    }
    const qs = p.toString();
    const url = qs ? `${window.location.pathname}?${qs}${window.location.hash}` : `${window.location.pathname}${window.location.hash}`;
    history.replaceState(null, "", url);
  }

  applyUrlState();
  syncGenreAriaSelected();

  function sourceBadge(m) {
    if (m.source === "both") return '<span class="badge both">Both</span>';
    if (m.source === "letterboxd") return '<span class="badge lb">Letterboxd</span>';
    return '<span class="badge im">IMDb</span>';
  }

  const STAR_PATH =
    "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z";

  function buildStarsInner(avg5) {
    if (avg5 == null || Number.isNaN(Number(avg5))) return "";
    const rating = Math.max(0, Math.min(5, Number(avg5)));
    let html = "";
    for (let i = 0; i < 5; i++) {
      const fill = Math.max(0, Math.min(1, rating - i));
      html += `
        <span class="star">
          <svg viewBox="0 0 24 24">
            <path class="star-empty" d="${STAR_PATH}"/>
          </svg>
          <svg viewBox="0 0 24 24" style="clip-path: inset(0 ${(1 - fill) * 100}% 0 0);">
            <path class="star-fill" d="${STAR_PATH}"/>
          </svg>
        </span>`;
    }
    return html;
  }

  function formatCompactCount(n) {
    if (n == null || n === "") return null;
    const v = Number(n);
    if (!Number.isFinite(v) || v <= 0) return null;
    if (v >= 1e6) {
      const x = v / 1e6;
      const s = x >= 10 ? x.toFixed(0) : x.toFixed(1).replace(/\.0$/, "");
      return `${s}M`;
    }
    if (v >= 1000) return `${Math.round(v / 1000)}k`;
    return String(Math.round(v));
  }

  /** Compact "2k rates" from combined IMDb + Letterboxd vote counts (for star overlay). */
  function ratingOverlayRatesText(m) {
    const ni = Number(m.rating_count_imdb);
    const nl = Number(m.rating_count_letterboxd);
    const hasIm = Number.isFinite(ni) && ni > 0;
    const hasLb = Number.isFinite(nl) && nl > 0;
    if (!hasIm && !hasLb) return "— rates";
    const total = Math.round((hasIm ? ni : 0) + (hasLb ? nl : 0));
    const t = formatCompactCount(total);
    return t ? `${t} rates` : "— rates";
  }

  function ratingBlockHtml(m) {
    const avg5 = m.rating_avg_5;
    if (avg5 == null || Number.isNaN(Number(avg5))) return "";
    const inner = buildStarsInner(avg5);
    if (!inner) return "";

    const avgNum = Number(avg5).toFixed(2);
    const ratesText = ratingOverlayRatesText(m);

    return `
      <div class="rating-block">
        <button type="button" class="rating-stars-toggle" aria-expanded="false" aria-label="Show or hide average rating">
          <span class="rating-stars-inner">
            <span class="stars">${inner}</span>
          </span>
          <span class="rating-value-overlay" aria-hidden="true">
            <span class="rating-value-pill">
              <span class="rating-value-line">
                <span class="rating-value-score-wrap">
                  <span class="rating-value-num">${avgNum}</span><span class="rating-value-scale">/5</span><span class="rating-value-sep" aria-hidden="true"> · </span>
                </span>
                <span class="rating-value-rates">${ratesText}</span>
              </span>
            </span>
          </span>
        </button>
      </div>`;
  }

  function formatGenreButtonLabel(genre) {
    if (genre === "all") return "Genre";
    const s = String(genre);
    if (!genreTruncateMq.matches) return s;
    return s.length > 4 ? `${s.slice(0, 4)}...` : s;
  }

  function updateSortUi() {
    sortTitleBtn.classList.toggle("active", sortField === "title");
    sortYearBtn.classList.toggle("active", sortField === "year");
    sortRatingBtn.classList.toggle("active", sortField === "rating");

    [sortTitleUp, sortTitleDown, sortYearUp, sortYearDown, sortRatingUp, sortRatingDown].forEach((el) =>
      el.classList.remove("active"),
    );

    if (sortField === "title") {
      (sortDir === "asc" ? sortTitleUp : sortTitleDown).classList.add("active");
    } else if (sortField === "year") {
      (sortDir === "asc" ? sortYearUp : sortYearDown).classList.add("active");
    } else if (sortField === "rating") {
      (sortDir === "asc" ? sortRatingUp : sortRatingDown).classList.add("active");
    }

    genreBtn.textContent = formatGenreButtonLabel(selectedGenre);
    genreBtn.title = selectedGenre === "all" ? "Filter by genre" : selectedGenre;
    genreBtn.classList.toggle("active", selectedGenre !== "all");
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

  function getActiveSources() {
    const sources = [];
    if (filterLb.classList.contains("active")) sources.push("letterboxd");
    if (filterBoth.classList.contains("active")) sources.push("both");
    if (filterImdb.classList.contains("active")) sources.push("imdb");
    return sources;
  }

  function render() {
    const activeSources = getActiveSources();

    let rows = movies.filter((m) => {
      if (activeSources.length === 0 || activeSources.length === 3) {
        /* show all */
      } else if (!activeSources.includes(m.source)) {
        return false;
      }
      if (selectedGenre !== "all" && !(m.genres || []).includes(selectedGenre)) {
        return false;
      }
      return true;
    });

    sortRows(rows);

    if (!rows.length) {
      gridEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      syncUrl();
      return;
    }
    emptyEl.classList.add("hidden");
    gridEl.innerHTML = rows
      .map(
        (m) => `
      <article class="card">
        <div class="poster">
          ${m.poster_url ? `<img src="${m.poster_url}" alt="${m.title} poster" loading="lazy" referrerpolicy="no-referrer">` : "No poster"}
        </div>
        <div>
          <div class="title">${m.title || ""}</div>
          <div class="meta">${m.year || "Year ?"} · ${(m.genres || []).slice(0, 2).join(", ") || "Genre ?"}</div>
          <div class="card-rating-row">
            ${ratingBlockHtml(m)}
            ${sourceBadge(m)}
          </div>
        </div>
      </article>
    `,
      )
      .join("");
    syncUrl();
  }

  gridEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".rating-stars-toggle");
    if (!btn || !gridEl.contains(btn)) return;
    const block = btn.closest(".rating-block");
    const overlay = block?.querySelector(".rating-value-overlay");
    if (!block || !overlay) return;
    const open = !block.classList.contains("rating-block--open");
    block.classList.toggle("rating-block--open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    overlay.setAttribute("aria-hidden", open ? "false" : "true");
  });

  clearLoadingState();
  updateSortUi();
  render();

  [filterLb, filterBoth, filterImdb].forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      btn.blur();
      render();
    });
  });

  genreBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const next = !isGenreOpen();
    setGenreOpen(next, {});
  });

  genreBtn.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      const next = !isGenreOpen();
      setGenreOpen(next, { focusFirstOption: next });
    }
  });

  genrePopup.addEventListener("click", (e) => {
    const opt = e.target.closest(".genre-option");
    if (!opt) return;
    selectedGenre = opt.dataset.genre;
    syncGenreAriaSelected();
    setGenreOpen(false, {});
    updateSortUi();
    render();
  });

  document.addEventListener("click", (e) => {
    if (!genrePopup.contains(e.target) && e.target !== genreBtn) {
      if (isGenreOpen()) setGenreOpen(false, {});
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isGenreOpen()) {
      e.preventDefault();
      setGenreOpen(false, { focusButtonOnClose: true });
    }
  });

  sortTitleBtn.addEventListener("click", () => {
    if (sortField === "title") sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortField = "title";
      sortDir = "asc";
    }
    updateSortUi();
    render();
  });
  sortYearBtn.addEventListener("click", () => {
    if (sortField === "year") sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortField = "year";
      sortDir = "desc";
    }
    updateSortUi();
    render();
  });
  sortRatingBtn.addEventListener("click", () => {
    if (sortField === "rating") sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortField = "rating";
      sortDir = "desc";
    }
    updateSortUi();
    render();
  });

  function onGenreTruncateMqChange() {
    updateSortUi();
  }
  if (genreTruncateMq.addEventListener) {
    genreTruncateMq.addEventListener("change", onGenreTruncateMqChange);
  } else {
    genreTruncateMq.addListener(onGenreTruncateMqChange);
  }
})();
