/* global fetch */
(async function init() {
  const gridEl = document.getElementById("grid");
  const emptyEl = document.getElementById("empty");
  const footerUpdatedLine = document.getElementById("footerUpdatedLine");

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
  const genreMorePopover = document.getElementById("genreMorePopover");
  let genreMoreAnchor = null;

  const SOURCE_KEYS = ["letterboxd", "both", "imdb"];
  const filterBySource = { letterboxd: filterLb, both: filterBoth, imdb: filterImdb };

  let dataUpdatedAtMs = null;

  /** Calendar + plain relative suffix (matches Flask footer; cap relative at 7 days). */
  function footerCalAndRelative(targetMs) {
    const d = new Date(targetMs);
    const cal = d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    const diffMs = Date.now() - targetMs;
    if (diffMs < 0) return { cal, rel: "just now" };
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return { cal, rel: "just now" };
    if (sec < 3600) {
      const m = Math.floor(sec / 60);
      return { cal, rel: `${m} minute${m === 1 ? "" : "s"} ago` };
    }
    if (sec < 86400) {
      const h = Math.floor(sec / 3600);
      return { cal, rel: `${h} hour${h === 1 ? "" : "s"} ago` };
    }
    const days = Math.floor(sec / 86400);
    if (days < 7) return { cal, rel: `${days} day${days === 1 ? "" : "s"} ago` };
    return { cal, rel: null };
  }

  function updateFooterDates() {
    if (!dataUpdatedAtMs || !footerUpdatedLine) return;
    const { cal, rel } = footerCalAndRelative(dataUpdatedAtMs);
    footerUpdatedLine.textContent = rel ? `Updated ${cal}, ${rel}.` : `Updated ${cal}.`;
  }

  function clearLoadingState() {
    gridEl.classList.remove("grid--loading");
    gridEl.removeAttribute("aria-busy");
  }

  function failLoad(message) {
    clearLoadingState();
    gridEl.innerHTML = "";
    if (footerUpdatedLine) footerUpdatedLine.textContent = message;
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
  } else if (footerUpdatedLine) {
    footerUpdatedLine.textContent =
      "No sync time in this export — re-run export_watchlist.py from your machine.";
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

  function escapeHtmlText(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const streamRegion = String(data.stream_region || "US").toUpperCase();
  const streamOwnedIds = new Set(
    Array.isArray(data.stream_owned_provider_ids)
      ? data.stream_owned_provider_ids.map((x) => Number(x)).filter((n) => Number.isFinite(n))
      : [],
  );

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

  function displayGenreOnCard(g) {
    const s = String(g || "").trim();
    if (!s) return s;
    const lower = s.toLowerCase();
    if (lower === "science fiction" || lower === "sci-fi" || lower === "sci fi") return "Sci-Fi";
    return s;
  }

  function cardGenresDisplayedList(m) {
    const raw = Array.isArray(m.genres) ? m.genres.map(String) : [];
    if (!raw.length) return [];
    let ordered = [...raw];
    if (selectedGenre !== "all" && raw.includes(selectedGenre)) {
      ordered = [selectedGenre, ...raw.filter((g) => g !== selectedGenre)];
    }
    const seen = new Set();
    const unique = [];
    for (const g of ordered) {
      if (seen.has(g)) continue;
      seen.add(g);
      unique.push(g);
    }
    return unique.map(displayGenreOnCard);
  }

  function cardMetaLineHtml(m) {
    const year = escapeHtmlText(m.year || "Year ?");
    const genres = cardGenresDisplayedList(m);
    const text = genres.length ? genres.join(", ") : "Genre ?";
    const payload = genres.length ? genres : ["Genre ?"];
    const dataGenres = escapeAttr(JSON.stringify(payload));
    return `
            <div class="card-meta-line">
              <div class="meta meta-row">
                <span class="meta-year">${year}</span><span class="meta-sep"> · </span>
                <span class="meta-genres-clip">
                  <span class="meta-genres-text">${escapeHtmlText(text)}</span>
                  <button type="button" class="genre-more-link hidden" data-genres="${dataGenres}" aria-label="Show genres that do not fit on one line">more...</button>
                </span>
              </div>
            </div>`;
  }

  function hasStreamingProviders(m) {
    const st = m.streaming && typeof m.streaming === "object" ? m.streaming : {};
    const block = st[streamRegion] || {};
    const flatrate = Array.isArray(block.flatrate) ? block.flatrate : [];
    const rent = Array.isArray(block.rent) ? block.rent : [];
    const buy = Array.isArray(block.buy) ? block.buy : [];
    return flatrate.length > 0 || rent.length > 0 || buy.length > 0;
  }

  function watchProvList(items, ownedSet) {
    if (!items.length) return "";
    return items
      .map((p) => {
        const id = Number(p && p.provider_id);
        const name = escapeHtmlText((p && p.provider_name) || (Number.isFinite(id) ? String(id) : "?"));
        const owned = Number.isFinite(id) && ownedSet.has(id);
        return `<li><span class="prov-name${owned ? " prov-owned" : ""}">${name}</span></li>`;
      })
      .join("");
  }

  function watchSectionHtml(label, items, ownedSet) {
    if (!items.length) return "";
    return `
      <div class="prov-section">
        <div class="prov-label">${escapeHtmlText(label)}</div>
        <ul>${watchProvList(items, ownedSet)}</ul>
      </div>`;
  }

  function watchBlockHtml(m, watchDomId) {
    if (!hasStreamingProviders(m)) return "";

    const st = m.streaming && typeof m.streaming === "object" ? m.streaming : {};
    const block = st[streamRegion] || {};
    const flatrate = Array.isArray(block.flatrate) ? block.flatrate : [];
    const rent = Array.isArray(block.rent) ? block.rent : [];
    const buy = Array.isArray(block.buy) ? block.buy : [];
    const bodyInner =
      watchSectionHtml("Included with subscription", flatrate, streamOwnedIds) +
      watchSectionHtml("Rent", rent, streamOwnedIds) +
      watchSectionHtml("Buy", buy, streamOwnedIds);

    const safeTitle = escapeAttr(m.title || "");
    const idAttr = watchDomId ? ` id="${escapeAttr(watchDomId)}"` : "";
    return `
      <details class="watch-details"${idAttr}>
        <summary class="watch-summary" aria-label="Where to watch ${safeTitle}">Watch</summary>
        <div class="watch-body">${bodyInner}</div>
      </details>`;
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

  function buildStarsPlaceholderInner() {
    let html = "";
    for (let i = 0; i < 5; i++) {
      html += `
        <span class="star star--muted">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path class="star-empty star-empty--muted" d="${STAR_PATH}"/>
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
    if (avg5 != null && !Number.isNaN(Number(avg5))) {
      const inner = buildStarsInner(avg5);
      if (inner) {
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
                  <span class="rating-value-x5">${avgNum}/5</span>
                </span>
                <span class="rating-value-sep" aria-hidden="true">·</span>
                <span class="rating-value-rates">${ratesText}</span>
              </span>
            </span>
          </span>
        </button>
      </div>`;
      }
    }

    const ph = buildStarsPlaceholderInner();
    return `
      <div class="rating-block rating-block--placeholder" role="img" aria-label="No average rating">
        <div class="rating-stars-placeholder">
          <span class="stars stars--placeholder">${ph}</span>
        </div>
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

  const watchBackdrop = document.getElementById("watchBackdrop");
  const watchPanelHost = document.getElementById("watchPanelHost");
  const mobileWatchMq = window.matchMedia("(max-width: 640px)");

  function getWatchBodyForDetail(detail) {
    if (!detail) return null;
    const local = detail.querySelector(".watch-body");
    if (local) return local;
    if (!detail.id || !watchPanelHost) return null;
    return watchPanelHost.querySelector(`[data-watch-detail-id="${detail.id}"]`);
  }

  function syncWatchHostVisibility() {
    if (!watchPanelHost) return;
    const has = watchPanelHost.querySelector(".watch-body");
    watchPanelHost.hidden = !has;
    watchPanelHost.setAttribute("aria-hidden", has ? "false" : "true");
  }

  function restoreWatchBodyToDetail(detail) {
    if (!detail?.id || !watchPanelHost) return;
    const body = watchPanelHost.querySelector(`[data-watch-detail-id="${detail.id}"]`);
    if (body) {
      detail.appendChild(body);
      delete body.dataset.watchDetailId;
    }
    syncWatchHostVisibility();
  }

  function portalWatchBodyToHost(detail) {
    if (!detail?.id || !watchPanelHost) return;
    const body = detail.querySelector(".watch-body");
    if (!body) return;
    body.dataset.watchDetailId = detail.id;
    watchPanelHost.appendChild(body);
    syncWatchHostVisibility();
  }

  function flushWatchPortalBeforeRender() {
    if (watchPanelHost) {
      watchPanelHost.replaceChildren();
      watchPanelHost.hidden = true;
      watchPanelHost.setAttribute("aria-hidden", "true");
    }
    document.documentElement.style.overflow = "";
    if (watchBackdrop) {
      watchBackdrop.hidden = true;
      watchBackdrop.setAttribute("aria-hidden", "true");
    }
  }

  function clearWatchPanelLayout(detail) {
    const body = getWatchBodyForDetail(detail);
    if (!body) return;
    body.style.position = "";
    body.style.left = "";
    body.style.top = "";
    body.style.right = "";
    body.style.width = "";
    body.style.maxWidth = "";
    body.style.maxHeight = "";
    body.style.overflowY = "";
    body.style.transform = "";
  }

  function syncWatchBackdrop() {
    if (!watchBackdrop) return;
    const any = gridEl.querySelector("details.watch-details[open]");
    if (!mobileWatchMq.matches || !any) {
      watchBackdrop.hidden = true;
      watchBackdrop.setAttribute("aria-hidden", "true");
      document.documentElement.style.overflow = "";
    } else {
      watchBackdrop.hidden = false;
      watchBackdrop.setAttribute("aria-hidden", "false");
      document.documentElement.style.overflow = "hidden";
    }
  }

  function positionWatchPanel(detail) {
    if (!mobileWatchMq.matches) return;
    const body = getWatchBodyForDetail(detail);
    if (!body) return;
    const pad = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const maxW = Math.min(340, vw - 2 * pad);
    const maxAvail = Math.max(120, vh - 2 * pad);

    body.style.position = "fixed";
    body.style.left = "50%";
    body.style.top = "50%";
    body.style.right = "auto";
    body.style.transform = "translate(-50%, -50%)";
    body.style.width = `${maxW}px`;
    body.style.maxWidth = `${maxW}px`;
    body.style.maxHeight = "none";
    body.style.overflowY = "visible";

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const natural = body.scrollHeight;
        if (natural <= maxAvail) {
          body.style.maxHeight = `${natural}px`;
          body.style.overflowY = "visible";
        } else {
          body.style.maxHeight = `${maxAvail}px`;
          body.style.overflowY = "auto";
        }
      });
    });
  }

  gridEl.addEventListener(
    "toggle",
    (e) => {
      const d = e.target;
      if (!d.classList.contains("watch-details")) return;
      if (d.open) {
        gridEl.querySelectorAll("details.watch-details[open]").forEach((o) => {
          if (o !== d) {
            clearWatchPanelLayout(o);
            o.open = false;
          }
        });
        if (mobileWatchMq.matches) {
          portalWatchBodyToHost(d);
          positionWatchPanel(d);
          syncWatchBackdrop();
        }
      } else {
        restoreWatchBodyToDetail(d);
        clearWatchPanelLayout(d);
        syncWatchBackdrop();
      }
    },
    true,
  );

  if (watchBackdrop) {
    watchBackdrop.addEventListener("click", () => {
      gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
        d.open = false;
      });
      syncWatchBackdrop();
    });
  }

  function onWatchLayoutMqChange() {
    const open = gridEl.querySelector("details.watch-details[open]");
    if (!mobileWatchMq.matches) {
      document.documentElement.style.overflow = "";
      if (watchBackdrop) watchBackdrop.hidden = true;
      gridEl.querySelectorAll("details.watch-details").forEach((d) => {
        restoreWatchBodyToDetail(d);
        clearWatchPanelLayout(d);
      });
    } else if (open && mobileWatchMq.matches) {
      if (open.querySelector(".watch-body")) {
        portalWatchBodyToHost(open);
      }
      positionWatchPanel(open);
      syncWatchBackdrop();
    }
  }
  window.addEventListener("resize", onWatchLayoutMqChange);
  window.addEventListener("resize", () => {
    if (genreMoreAnchor) positionGenreMorePopover(genreMoreAnchor);
  });
  if (mobileWatchMq.addEventListener) {
    mobileWatchMq.addEventListener("change", onWatchLayoutMqChange);
  } else {
    mobileWatchMq.addListener(onWatchLayoutMqChange);
  }

  function syncGenreOverflow() {
    const epsilon = 2;
    gridEl.querySelectorAll(".meta-genres-clip").forEach((clip) => {
      const textEl = clip.querySelector(".meta-genres-text");
      const moreBtn = clip.querySelector(".genre-more-link");
      if (!textEl || !moreBtn) return;
      moreBtn.classList.add("hidden");
      const clippedY = textEl.scrollHeight > textEl.clientHeight + epsilon;
      const clippedX = textEl.scrollWidth > textEl.clientWidth + epsilon;
      if (clippedY || clippedX) {
        moreBtn.classList.remove("hidden");
      }
    });
  }

  function closeGenreMorePopover() {
    if (!genreMorePopover) return;
    genreMorePopover.classList.add("hidden");
    genreMorePopover.innerHTML = "";
    genreMorePopover.setAttribute("aria-hidden", "true");
    genreMoreAnchor = null;
  }

  function positionGenreMorePopover(anchor) {
    if (!genreMorePopover || !anchor) return;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const pad = 8;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const r = anchor.getBoundingClientRect();
        const pr = genreMorePopover.getBoundingClientRect();
        let left = r.left;
        left = Math.max(pad, Math.min(left, vw - pr.width - pad));
        let top = r.bottom + 6;
        if (top + pr.height > vh - pad) {
          top = Math.max(pad, r.top - 6 - pr.height);
        }
        genreMorePopover.style.left = `${left}px`;
        genreMorePopover.style.top = `${top}px`;
      });
    });
  }

  function openGenreMorePopover(anchor) {
    if (!genreMorePopover || !anchor) return;
    let list;
    try {
      list = JSON.parse(anchor.dataset.genres || "[]");
    } catch {
      return;
    }
    if (!Array.isArray(list) || !list.length) return;
    genreMorePopover.innerHTML = list
      .map((g) => `<div class="genre-more-popover__item">${escapeHtmlText(String(g))}</div>`)
      .join("");
    genreMoreAnchor = anchor;
    genreMorePopover.classList.remove("hidden");
    genreMorePopover.setAttribute("aria-hidden", "false");
    positionGenreMorePopover(anchor);
  }

  function toggleGenreMorePopover(anchor) {
    if (genreMorePopover && !genreMorePopover.classList.contains("hidden") && genreMoreAnchor === anchor) {
      closeGenreMorePopover();
    } else {
      openGenreMorePopover(anchor);
    }
  }

  function closeOpenRatingBlocks() {
    gridEl.querySelectorAll(".rating-block--open").forEach((block) => {
      block.classList.remove("rating-block--open");
      const b = block.querySelector(".rating-stars-toggle");
      if (b) {
        b.setAttribute("aria-expanded", "false");
        b.blur();
      }
      block.querySelector(".rating-value-overlay")?.setAttribute("aria-hidden", "true");
    });
  }

  let renderRaf = 0;
  function scheduleRender() {
    if (renderRaf) return;
    renderRaf = requestAnimationFrame(() => {
      renderRaf = 0;
      render();
    });
  }

  function render() {
    closeGenreMorePopover();

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
      flushWatchPortalBeforeRender();
      gridEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      syncUrl();
      return;
    }
    emptyEl.classList.add("hidden");
    flushWatchPortalBeforeRender();
    gridEl.innerHTML = rows
      .map((m, i) => {
        const ratingHtml = ratingBlockHtml(m);
        const watchHtml = watchBlockHtml(m, `watch-card-${i}`);
        const ratingRowHtml =
          ratingHtml || watchHtml
            ? `<div class="card-rating-row">${ratingHtml}${watchHtml}</div>`
            : "";
        return `
      <article class="card">
        <div class="poster">
          ${m.poster_url ? `<img src="${escapeAttr(m.poster_url)}" alt="${escapeAttr(m.title || "")} poster" loading="lazy" referrerpolicy="no-referrer">` : "No poster"}
        </div>
        <div class="movie-content">
          <div class="movie-main">
            <div class="title">${escapeHtmlText(m.title || "")}</div>
            ${cardMetaLineHtml(m)}
            ${ratingRowHtml}
          </div>
        </div>
      </article>
    `;
      })
      .join("");
    syncUrl();
    requestAnimationFrame(() => {
      syncGenreOverflow();
      requestAnimationFrame(syncGenreOverflow);
    });
  }

  if (typeof ResizeObserver !== "undefined") {
    const genreOverflowRo = new ResizeObserver(() => syncGenreOverflow());
    genreOverflowRo.observe(gridEl);
  }

  gridEl.addEventListener("click", (e) => {
    const genreMore = e.target.closest(".genre-more-link");
    if (genreMore && gridEl.contains(genreMore)) {
      e.preventDefault();
      toggleGenreMorePopover(genreMore);
      return;
    }

    const onRatingToggle = e.target.closest(".rating-stars-toggle");
    const onWatchControl = e.target.closest(".watch-summary") || e.target.closest(".watch-body");
    if (!onRatingToggle && !onWatchControl) {
      closeOpenRatingBlocks();
    }

    if (!e.target.closest(".watch-summary") && !e.target.closest(".watch-body")) {
      const card = e.target.closest("article.card");
      if (card && gridEl.contains(card)) {
        const openWatch = card.querySelector("details.watch-details[open]");
        if (openWatch) {
          openWatch.open = false;
          syncWatchBackdrop();
        }
      }
    }

    const btn = e.target.closest(".rating-stars-toggle");
    if (!btn || !gridEl.contains(btn)) return;
    const block = btn.closest(".rating-block");
    const overlay = block?.querySelector(".rating-value-overlay");
    if (!block || !overlay) return;
    const wasOpen = block.classList.contains("rating-block--open");
    if (!wasOpen) closeOpenRatingBlocks();
    const open = !block.classList.contains("rating-block--open");
    block.classList.toggle("rating-block--open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    overlay.setAttribute("aria-hidden", open ? "false" : "true");
    if (!open) btn.blur();
  });

  gridEl.addEventListener(
    "focusout",
    (e) => {
      if (!e.target.classList.contains("rating-stars-toggle")) return;
      const block = e.target.closest(".rating-block");
      if (!block || !gridEl.contains(block) || !block.classList.contains("rating-block--open")) return;
      requestAnimationFrame(() => {
        const ae = document.activeElement;
        if (!block.contains(ae)) {
          block.classList.remove("rating-block--open");
          e.target.setAttribute("aria-expanded", "false");
          block.querySelector(".rating-value-overlay")?.setAttribute("aria-hidden", "true");
        }
      });
    },
    true,
  );

  clearLoadingState();
  updateSortUi();
  scheduleRender();

  [filterLb, filterBoth, filterImdb].forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      btn.blur();
      scheduleRender();
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
    scheduleRender();
  });

  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.target.closest(".rating-block")) return;
      closeOpenRatingBlocks();
    },
    true,
  );

  document.addEventListener("click", (e) => {
    if (!genrePopup.contains(e.target) && e.target !== genreBtn) {
      if (isGenreOpen()) setGenreOpen(false, {});
    }
    if (genreMorePopover && !genreMorePopover.classList.contains("hidden")) {
      if (!genreMorePopover.contains(e.target) && !e.target.closest(".genre-more-link")) {
        closeGenreMorePopover();
      }
    }
    if (!e.target.closest(".rating-block")) {
      closeOpenRatingBlocks();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (genreMorePopover && !genreMorePopover.classList.contains("hidden")) {
      e.preventDefault();
      closeGenreMorePopover();
      return;
    }
    if (gridEl.querySelector("details.watch-details[open]")) {
      e.preventDefault();
      gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
        d.open = false;
      });
      syncWatchBackdrop();
      return;
    }
    if (isGenreOpen()) {
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
    scheduleRender();
  });
  sortYearBtn.addEventListener("click", () => {
    if (sortField === "year") sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortField = "year";
      sortDir = "desc";
    }
    updateSortUi();
    scheduleRender();
  });
  sortRatingBtn.addEventListener("click", () => {
    if (sortField === "rating") sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortField = "rating";
      sortDir = "desc";
    }
    updateSortUi();
    scheduleRender();
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
