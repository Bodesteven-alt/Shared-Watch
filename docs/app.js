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
  const countLbFiltered = document.getElementById("countLbFiltered");
  const countBothFiltered = document.getElementById("countBothFiltered");
  const countImdbFiltered = document.getElementById("countImdbFiltered");
  const srcCountLb = document.getElementById("srcCountLb");
  const srcCountBoth = document.getElementById("srcCountBoth");
  const srcCountImdb = document.getElementById("srcCountImdb");
  const genreSheetBackdrop = document.getElementById("genreSheetBackdrop");
  const servicesSheetBackdrop = document.getElementById("servicesSheetBackdrop");
  const sortSheetBackdrop = document.getElementById("sortSheetBackdrop");
  const scrollTopBtn = document.getElementById("scrollTopBtn");
  const mainContentEl = document.getElementById("mainContent");

  const GRID_BATCH_SIZE = 24;
  let gridRowsBuffer = [];
  let gridDisplayedCount = 0;
  let gridRenderGeneration = 0;
  let gridLoadObserver = null;

  function teardownGridLoadObserver() {
    if (gridLoadObserver) {
      gridLoadObserver.disconnect();
      gridLoadObserver = null;
    }
  }

  const sortMobileBtn = document.getElementById("sortMobileBtn");
  const sortPopup = document.getElementById("sortPopup");
  const sortPopupOriginalParent = sortPopup ? sortPopup.parentElement : null;
  const sortPopupOriginalNext = sortPopup ? sortPopup.nextElementSibling : null;

  const genreBtn = document.getElementById("genreBtn");
  const genreBtnLabel = genreBtn && genreBtn.querySelector(".sortbtn-label");
  const genrePopup = document.getElementById("genrePopup");
  const genrePopupOriginalParent = genrePopup ? genrePopup.parentElement : null;
  const genrePopupOriginalNext = genrePopup ? genrePopup.nextElementSibling : null;
  const servicesBtn = document.getElementById("servicesBtn");
  const servicesBtnLabel = servicesBtn && servicesBtn.querySelector(".sortbtn-label");
  const servicesPopup = document.getElementById("servicesPopup");
  const servicesPopupOriginalParent = servicesPopup ? servicesPopup.parentElement : null;
  const servicesPopupOriginalNext = servicesPopup ? servicesPopup.nextElementSibling : null;
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
    gridRenderGeneration += 1;
    teardownGridLoadObserver();
    gridRowsBuffer = [];
    gridDisplayedCount = 0;
    gridEl.innerHTML = "";
    if (footerUpdatedLine) footerUpdatedLine.textContent = message;
  }

  const wlVer = document.querySelector('meta[name="watchlist-version"]')?.getAttribute("content")?.trim();
  const wlUrl = wlVer
    ? `./data/watchlist.json?v=${encodeURIComponent(wlVer)}`
    : "./data/watchlist.json";
  const res = await fetch(wlUrl);
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

  const providerMap = new Map();
  function ingestStreamingProvidersFromMovie(m) {
    const st = m.streaming && typeof m.streaming === "object" ? m.streaming : {};
    const block = st[streamRegion] || {};
    for (const key of ["flatrate", "rent", "buy"]) {
      const arr = Array.isArray(block[key]) ? block[key] : [];
      for (const p of arr) {
        const id = Number(p && p.provider_id);
        if (!Number.isFinite(id)) continue;
        const name = (p && p.provider_name) || String(id);
        if (!providerMap.has(id)) providerMap.set(id, name);
      }
    }
  }
  for (const m of movies) ingestStreamingProvidersFromMovie(m);
  const sortedProviders = [...providerMap.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1])));

  if (servicesPopup) {
    if (!sortedProviders.length) {
      servicesPopup.innerHTML =
        '<p class="watch-muted" style="margin:0;padding:.35rem .5rem;font-size:.78rem;">No streaming providers in this export.</p>';
    } else {
      const listHtml = sortedProviders
        .map(([id, name]) => {
          const sid = escapeAttr(String(id));
          return `<label class="service-option"><input type="checkbox" name="svc" value="${sid}"><span>${escapeHtmlText(name)}</span></label>`;
        })
        .join("");
      servicesPopup.innerHTML =
        `<p class="services-sheet-heading">Streaming services</p>` +
        `<div class="services-sheet-body">${listHtml}</div>` +
        `<div class="services-sheet-footer">` +
        `<button type="button" class="services-sheet-btn services-sheet-btn--clear" data-service-action="clear">Clear selection</button>` +
        `<button type="button" class="services-sheet-btn services-sheet-btn--done" data-service-action="done">Done</button>` +
        `</div>`;
    }
  }

  genrePopup.innerHTML =
    `<div class="genre-popup__inner">` +
    `<div class="genre-popup__search">` +
    `<input type="search" id="genrePopupFilter" class="genre-popup__filter" autocomplete="off" aria-label="Filter genres" placeholder="Search genres…">` +
    `<button type="button" class="genre-popup__clear" aria-label="Clear search" hidden aria-hidden="true">×</button>` +
    `</div>` +
    `<div id="genreListbox" class="genre-popup__list" role="listbox" aria-label="Genres"></div>` +
    `</div>`;

  function getGenreFilterInput() {
    return genrePopup.querySelector(".genre-popup__filter");
  }

  function getGenreClearBtn() {
    return genrePopup.querySelector(".genre-popup__clear");
  }

  function getGenreListEl() {
    return genrePopup.querySelector(".genre-popup__list");
  }

  function syncGenreClearVisibility() {
    const inp = getGenreFilterInput();
    const btn = getGenreClearBtn();
    if (!inp || !btn) return;
    const has = !!inp.value.trim();
    btn.hidden = !has;
    btn.setAttribute("aria-hidden", has ? "false" : "true");
  }

  function genreOptionLabelHtml(g, queryRaw) {
    const esc = escapeHtmlText(g);
    const q = (queryRaw || "").trim();
    if (!q) return esc;
    const low = g.toLowerCase();
    const ql = q.toLowerCase();
    const idx = low.indexOf(ql);
    if (idx < 0) return esc;
    const before = escapeHtmlText(g.slice(0, idx));
    const mid = escapeHtmlText(g.slice(idx, idx + q.length));
    const after = escapeHtmlText(g.slice(idx + q.length));
    return `${before}<mark class="genre-popup__hl">${mid}</mark>${after}`;
  }

  let selectedGenre = "all";

  function renderGenreList() {
    const listEl = getGenreListEl();
    if (!listEl) return;
    const input = getGenreFilterInput();
    const raw = input ? input.value : "";
    const q = raw.trim().toLowerCase();
    const filtered = q ? sortedGenres.filter((g) => g.toLowerCase().includes(q)) : sortedGenres;
    let inner = `<button type="button" class="genre-option${selectedGenre === "all" ? " active" : ""}" data-genre="all" role="option" aria-selected="${selectedGenre === "all" ? "true" : "false"}">All Genres</button>`;
    if (q && filtered.length === 0) {
      inner += `<div class="genre-popup__empty" role="status">No results found</div>`;
    } else {
      inner += filtered
        .map((g) => {
          const active = selectedGenre === g;
          const label = genreOptionLabelHtml(g, raw);
          return `<button type="button" class="genre-option${active ? " active" : ""}" data-genre="${escapeAttr(g)}" role="option" aria-selected="${active ? "true" : "false"}">${label}</button>`;
        })
        .join("");
    }
    listEl.innerHTML = inner;
  }

  renderGenreList();
  syncGenreClearVisibility();
  /** When empty, no service filter. When non-empty, show titles that include any selected provider (region). */
  let selectedServiceIds = new Set();
  let sortField = "title";
  let sortDir = "asc";
  /** "avg" | "votes" — only affects ordering when sortField === "rating" */
  let ratingSortMode = "avg";

  const genreTruncateMq = window.matchMedia("(max-width: 640px)");
  const popupSheetMq = window.matchMedia("(max-width: 640px), (pointer: coarse)");

  function isPopupSheetMode() {
    return popupSheetMq.matches;
  }

  function totalRatingVotes(m) {
    const ni = Number(m.rating_count_imdb);
    const nl = Number(m.rating_count_letterboxd);
    const hasI = Number.isFinite(ni) && ni > 0;
    const hasL = Number.isFinite(nl) && nl > 0;
    if (!hasI && !hasL) return -1;
    return (hasI ? ni : 0) + (hasL ? nl : 0);
  }

  function articleInsensitiveTitleSortKey(title) {
    const full = String(title || "").trim().toLowerCase();
    const primary = full.replace(/^(?:the|an|a)\s+/i, "").trim() || full;
    return { primary, full };
  }

  function compareTitles(aTitle, bTitle) {
    const aKey = articleInsensitiveTitleSortKey(aTitle);
    const bKey = articleInsensitiveTitleSortKey(bTitle);
    const primaryCmp = aKey.primary.localeCompare(bKey.primary);
    if (primaryCmp !== 0) return primaryCmp;
    return aKey.full.localeCompare(bKey.full);
  }

  function getMobileSortFieldLabel() {
    if (sortField === "year") return "Year";
    if (sortField === "rating") return "Rating";
    if (sortField === "popularity") return "Popular";
    return "Name";
  }

  function getDirectionMeta() {
    if (sortField === "title") {
      return sortDir === "asc"
        ? { short: "A-Z", full: "Ascending", icon: "▲" }
        : { short: "Z-A", full: "Descending", icon: "▼" };
    }
    if (sortField === "year") {
      return sortDir === "asc"
        ? { short: "Oldest", full: "Ascending", icon: "▲" }
        : { short: "Newest", full: "Descending", icon: "▼" };
    }
    return sortDir === "asc"
      ? { short: "Low-High", full: "Ascending", icon: "▲" }
      : { short: "High-Low", full: "Descending", icon: "▼" };
  }

  function getSortMobileLabel() {
    const dir = getDirectionMeta();
    return `${getMobileSortFieldLabel()} ${dir.short}`;
  }

  function mountSortPopupForMobileSheet(open, mobile) {
    if (!sortPopup || !sortPopupOriginalParent) return;
    if (open && mobile) {
      if (sortPopup.parentElement !== document.body) {
        document.body.appendChild(sortPopup);
      }
      return;
    }
    if (sortPopup.parentElement === sortPopupOriginalParent) return;
    if (sortPopupOriginalNext && sortPopupOriginalNext.parentElement === sortPopupOriginalParent) {
      sortPopupOriginalParent.insertBefore(sortPopup, sortPopupOriginalNext);
    } else {
      sortPopupOriginalParent.appendChild(sortPopup);
    }
  }

  function mountPopupForMobileSheet(popup, originalParent, originalNext, open, mobile) {
    if (!popup || !originalParent) return;
    if (open && mobile) {
      if (popup.parentElement !== document.body) {
        document.body.appendChild(popup);
      }
      return;
    }
    if (popup.parentElement === originalParent) return;
    if (originalNext && originalNext.parentElement === originalParent) {
      originalParent.insertBefore(popup, originalNext);
    } else {
      originalParent.appendChild(popup);
    }
  }

  function setMobileSortField(field) {
    if (field !== "title" && field !== "year" && field !== "rating" && field !== "popularity") return;
    const changed = sortField !== field;
    sortField = field;
    if (field === "title") {
      if (changed) sortDir = "asc";
      ratingSortMode = "avg";
      return;
    }
    if (field === "year") {
      if (changed) sortDir = "desc";
      ratingSortMode = "avg";
      return;
    }
    if (field === "rating") {
      if (changed) sortDir = "desc";
      ratingSortMode = "avg";
      return;
    }
    if (changed) sortDir = "desc";
    ratingSortMode = "votes";
  }

  function resetDesktopPopupClamp(popup) {
    if (!popup) return;
    popup.style.left = "";
    popup.style.right = "";
    popup.style.top = "";
    popup.style.bottom = "";
  }

  function clampDesktopPopupToViewport(popup) {
    if (!popup || popup.classList.contains("hidden")) return;
    resetDesktopPopupClamp(popup);
    const pad = 8;
    let rect = popup.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (rect.right > vw - pad) {
      popup.style.left = "auto";
      popup.style.right = "0";
      rect = popup.getBoundingClientRect();
    }
    if (rect.left < pad) {
      popup.style.left = "0";
      popup.style.right = "auto";
      rect = popup.getBoundingClientRect();
    }
    if (rect.bottom > vh - pad) {
      popup.style.top = "auto";
      popup.style.bottom = "calc(100% + 0.45rem)";
    }
  }

  function toggleMobileSortDirection() {
    sortDir = sortDir === "asc" ? "desc" : "asc";
  }

  function syncSortPopupState() {
    if (!sortPopup) return;
    sortPopup.querySelectorAll("[data-sort-field]").forEach((btn) => {
      const field = btn.getAttribute("data-sort-field");
      const active = field === sortField;
      const textEl = btn.querySelector(".sort-popup-option__text");
      const arrowEl = btn.querySelector(".sort-popup-option__arrow");
      const label = btn.dataset.label || (textEl && textEl.textContent.trim()) || field;
      btn.dataset.label = label;
      if (textEl) textEl.textContent = label;
      btn.classList.toggle("active", active);
      if (arrowEl) {
        arrowEl.classList.toggle("sort-popup-option__arrow--hidden", !active);
        arrowEl.classList.toggle("sort-popup-option__arrow--asc", active && sortDir === "asc");
        arrowEl.classList.toggle("sort-popup-option__arrow--desc", active && sortDir === "desc");
      }
      const hint = active ? "Tap again to toggle direction." : "Tap to sort by this field.";
      btn.setAttribute("aria-label", `${label}. ${hint}`);
    });
  }

  function isSortOpen() {
    return !!(sortPopup && !sortPopup.classList.contains("hidden"));
  }

  function setSortOpen(open, opts) {
    if (!sortPopup || !sortMobileBtn) return;
    const focusFirst = opts && opts.focusFirst;
    const focusBtn = opts && opts.focusButtonOnClose;
    const mobile = isPopupSheetMode();
    mountSortPopupForMobileSheet(open, mobile);
    sortPopup.classList.toggle("sort-popup--mobile", !!(open && mobile));
    sortPopup.classList.toggle("hidden", !open);
    sortMobileBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (sortSheetBackdrop) {
      const showBackdrop = !!(open && mobile);
      sortSheetBackdrop.classList.toggle("hidden", !showBackdrop);
      sortSheetBackdrop.setAttribute("aria-hidden", showBackdrop ? "false" : "true");
    }
    if (open) {
      syncSortPopupState();
      if (!mobile) {
        requestAnimationFrame(() => clampDesktopPopupToViewport(sortPopup));
      }
      if (focusFirst) {
        const first = sortPopup.querySelector(".sort-popup-option.active") || sortPopup.querySelector("[data-sort-field]");
        if (first) requestAnimationFrame(() => first.focus());
      }
    }
    if (!open) resetDesktopPopupClamp(sortPopup);
    if (!open && focusBtn) {
      sortMobileBtn.focus({ preventScroll: true });
    }
  }

  function isGenreOpen() {
    return !genrePopup.classList.contains("hidden");
  }

  function setGenreOpen(open, opts) {
    const focusFilter = opts && (opts.focusFilter || opts.focusFirstOption);
    const focusButtonOnClose = opts && opts.focusButtonOnClose;
    const mobile = isPopupSheetMode();
    mountPopupForMobileSheet(genrePopup, genrePopupOriginalParent, genrePopupOriginalNext, open, mobile);
    if (!open) {
      const fi = getGenreFilterInput();
      if (fi) {
        fi.value = "";
        syncGenreClearVisibility();
        renderGenreList();
      }
    }
    genrePopup.classList.toggle("hidden", !open);
    genrePopup.classList.toggle("genre-popup--mobile", !!(open && mobile));
    if (open) renderGenreList();
    if (!open) genrePopup.classList.remove("genre-popup--mobile");
    if (genreSheetBackdrop) {
      const showBackdrop = !!(open && mobile);
      genreSheetBackdrop.classList.toggle("hidden", !showBackdrop);
      genreSheetBackdrop.setAttribute("aria-hidden", showBackdrop ? "false" : "true");
    }
    genreBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && focusFilter) {
      const fi = getGenreFilterInput();
      if (fi) requestAnimationFrame(() => fi.focus());
    }
    if (open && !mobile) {
      requestAnimationFrame(() => clampDesktopPopupToViewport(genrePopup));
    }
    if (!open && focusButtonOnClose) {
      genreBtn.focus({ preventScroll: true });
    }
    if (!open) resetDesktopPopupClamp(genrePopup);
  }

  function syncGenreAriaSelected() {
    renderGenreList();
  }

  function allSourcesActive() {
    return filterLb.classList.contains("active") &&
      filterBoth.classList.contains("active") &&
      filterImdb.classList.contains("active");
  }

  function isDefaultState() {
    return (
      selectedGenre === "all" &&
      selectedServiceIds.size === 0 &&
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
    if (s === "title" || s === "year" || s === "rating" || s === "popularity") sortField = s;
    const d = params.get("dir");
    if (d === "asc" || d === "desc") sortDir = d;

    const rm = params.get("ratingMode");
    if (rm === "votes") ratingSortMode = "votes";
    else ratingSortMode = "avg";
    if (sortField === "rating" && ratingSortMode === "votes") {
      sortField = "popularity";
    }

    const svcRaw = params.get("svc");
    selectedServiceIds = new Set();
    if (svcRaw && sortedProviders.length) {
      for (const part of svcRaw.split(",")) {
        const n = Number(String(part).trim());
        if (Number.isFinite(n) && providerMap.has(n)) selectedServiceIds.add(n);
      }
    }
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
    if (selectedServiceIds.size > 0) {
      p.set("svc", [...selectedServiceIds].sort((a, b) => a - b).join(","));
    }
    if (sortField !== "title" || sortDir !== "asc") {
      p.set("sort", sortField);
      p.set("dir", sortDir);
    }
    if (sortField === "rating" && ratingSortMode === "votes") {
      p.set("ratingMode", "votes");
    }
    const qs = p.toString();
    const url = qs ? `${window.location.pathname}?${qs}${window.location.hash}` : `${window.location.pathname}${window.location.hash}`;
    history.replaceState(null, "", url);
  }

  function syncServiceCheckboxUi() {
    if (!servicesPopup) return;
    servicesPopup.querySelectorAll('input[type="checkbox"][name="svc"]').forEach((inp) => {
      const id = Number(inp.value);
      inp.checked = Number.isFinite(id) && selectedServiceIds.has(id);
    });
  }

  function isServicesOpen() {
    return !!(servicesPopup && !servicesPopup.classList.contains("hidden"));
  }

  function setServicesOpen(open, opts) {
    if (!servicesPopup || !servicesBtn) return;
    const focusFirst = opts && opts.focusFirst;
    const focusBtn = opts && opts.focusButtonOnClose;
    const mobile = isPopupSheetMode();
    mountPopupForMobileSheet(
      servicesPopup,
      servicesPopupOriginalParent,
      servicesPopupOriginalNext,
      open,
      mobile,
    );
    if (open && mobile) {
      servicesPopup.classList.add("services-popup--mobile");
    } else {
      servicesPopup.classList.remove("services-popup--mobile");
    }
    servicesPopup.classList.toggle("hidden", !open);
    if (servicesSheetBackdrop) {
      const showBackdrop = !!(open && mobile);
      servicesSheetBackdrop.classList.toggle("hidden", !showBackdrop);
      servicesSheetBackdrop.setAttribute("aria-hidden", showBackdrop ? "false" : "true");
    }
    servicesBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && focusFirst) {
      const first = servicesPopup.querySelector(".services-sheet-body input, input, .genre-option");
      if (first) first.focus();
    } else if (!open && focusBtn) {
      servicesBtn.focus({ preventScroll: true });
    }
    if (open && !mobile) {
      requestAnimationFrame(() => clampDesktopPopupToViewport(servicesPopup));
    }
    if (!open) resetDesktopPopupClamp(servicesPopup);
  }

  function closeOtherFilterSortPopovers(except) {
    if (except !== "sort" && isSortOpen()) setSortOpen(false, {});
    if (except !== "genre" && isGenreOpen()) setGenreOpen(false, {});
    if (except !== "services" && isServicesOpen()) setServicesOpen(false, {});
  }

  applyUrlState();
  syncServiceCheckboxUi();
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

  function movieProviderIds(m) {
    const ids = new Set();
    const st = m.streaming && typeof m.streaming === "object" ? m.streaming : {};
    const block = st[streamRegion] || {};
    for (const key of ["flatrate", "rent", "buy"]) {
      const arr = Array.isArray(block[key]) ? block[key] : [];
      for (const p of arr) {
        const id = Number(p && p.provider_id);
        if (Number.isFinite(id)) ids.add(id);
      }
    }
    return ids;
  }

  function movieMatchesServiceFilter(m) {
    if (selectedServiceIds.size === 0) return true;
    const ids = movieProviderIds(m);
    for (const sid of selectedServiceIds) {
      if (ids.has(sid)) return true;
    }
    return false;
  }

  function movieMatchesSelectedServices(m) {
    if (selectedServiceIds.size === 0) return false;
    const ids = movieProviderIds(m);
    for (const sid of selectedServiceIds) {
      if (ids.has(sid)) return true;
    }
    return false;
  }

  function watchProvList(items, ownedSet, filterPickSet) {
    if (!items.length) return "";
    const usePick = filterPickSet && filterPickSet.size > 0;
    return items
      .map((p) => {
        const id = Number(p && p.provider_id);
        const name = escapeHtmlText((p && p.provider_name) || (Number.isFinite(id) ? String(id) : "?"));
        const owned = Number.isFinite(id) && ownedSet.has(id);
        const pick = usePick && Number.isFinite(id) && filterPickSet.has(id);
        const cls =
          "prov-name" +
          (owned ? " prov-owned" : "") +
          (pick ? " prov-filter-match" : "");
        return `<div class="prov-row"><span class="${cls}">${name}</span></div>`;
      })
      .join("");
  }

  function watchSectionHtml(label, items, ownedSet, filterPickSet) {
    if (!items.length) return "";
    return `
      <div class="prov-section">
        <div class="prov-label">${escapeHtmlText(label)}</div>
        <div class="prov-list">${watchProvList(items, ownedSet, filterPickSet)}</div>
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
      watchSectionHtml("Included With Subscription", flatrate, streamOwnedIds, selectedServiceIds) +
      watchSectionHtml("Rent", rent, streamOwnedIds, selectedServiceIds) +
      watchSectionHtml("Buy", buy, streamOwnedIds, selectedServiceIds);

    const safeTitle = escapeAttr(m.title || "");
    const idAttr = watchDomId ? ` id="${escapeAttr(watchDomId)}"` : "";
    const filterHit = movieMatchesSelectedServices(m);
    return `
      <details class="watch-details${filterHit ? " watch-details--filter-hit" : ""}"${idAttr}>
        <summary class="watch-summary" aria-label="Where to watch ${safeTitle}">Watch</summary>
        <div class="watch-body"><div class="watch-body__content">${bodyInner}</div></div>
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

  /** Compact count (e.g. 12k, 1.2M) from combined IMDb + Letterboxd votes for star overlay; null if none. */
  function ratingOverlayCountText(m) {
    const ni = Number(m.rating_count_imdb);
    const nl = Number(m.rating_count_letterboxd);
    const hasIm = Number.isFinite(ni) && ni > 0;
    const hasLb = Number.isFinite(nl) && nl > 0;
    if (!hasIm && !hasLb) return null;
    const total = Math.round((hasIm ? ni : 0) + (hasLb ? nl : 0));
    return formatCompactCount(total);
  }

  function ratingBlockHtml(m) {
    const avg5 = m.rating_avg_5;
    if (avg5 != null && !Number.isNaN(Number(avg5))) {
      const inner = buildStarsInner(avg5);
      if (inner) {
        const avgNum = Number(avg5).toFixed(2);
        const countCompact = ratingOverlayCountText(m);
        const countSeg = countCompact != null ? countCompact : "—";
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
                <span class="rating-value-rates">${escapeHtmlText(countSeg)}</span>
              </span>
            </span>
          </span>
        </button>
      </div>`;
      }
    }

    const ph = buildStarsPlaceholderInner();
    return `
      <div class="rating-block rating-block--placeholder">
        <button type="button" class="rating-stars-toggle" aria-expanded="false" aria-label="Show or hide rating details">
          <span class="rating-stars-inner">
            <span class="stars stars--placeholder">${ph}</span>
          </span>
          <span class="rating-value-overlay" aria-hidden="true">
            <span class="rating-value-pill">
              <span class="rating-value-line rating-value-line--solo">
                <span class="rating-value-norating" role="status">No ratings</span>
              </span>
            </span>
          </span>
        </button>
      </div>`;
  }

  function formatGenreButtonLabel(genre) {
    if (genre === "all") return "Genre";
    return String(genre);
  }

  function formatServicesButtonTitle() {
    if (selectedServiceIds.size === 0) return "Filter by streaming service";
    return [...selectedServiceIds]
      .map((id) => providerMap.get(id) || String(id))
      .join(", ");
  }

  function updateSortUi() {
    syncSortPopupState();

    if (sortMobileBtn) {
      sortMobileBtn.textContent = getSortMobileLabel();
      sortMobileBtn.classList.toggle("active", true);
    }

    if (genreBtnLabel) {
      genreBtnLabel.textContent = formatGenreButtonLabel(selectedGenre);
    } else {
      genreBtn.textContent = formatGenreButtonLabel(selectedGenre);
    }
    genreBtn.title = selectedGenre === "all" ? "Filter by genre" : selectedGenre;
    genreBtn.classList.toggle("active", selectedGenre !== "all");

    if (servicesBtn) {
      if (servicesBtnLabel) {
        servicesBtnLabel.textContent = formatServicesButtonLabel();
      } else {
        servicesBtn.textContent = formatServicesButtonLabel();
      }
      servicesBtn.title = formatServicesButtonTitle();
      servicesBtn.classList.toggle("active", selectedServiceIds.size > 0);
    }
  }

  function formatServicesButtonLabel() {
    if (selectedServiceIds.size === 0) return "Services";
    if (selectedServiceIds.size === 1) {
      const id = [...selectedServiceIds][0];
      return providerMap.get(id) || "Services";
    }
    return `${selectedServiceIds.size} Services`;
  }

  function sortRows(rows) {
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortField === "year") {
        const ay = Number(a.year || 0);
        const by = Number(b.year || 0);
        cmp = ay - by;
        if (cmp === 0) cmp = compareTitles(a.title, b.title);
      } else if (sortField === "rating" || sortField === "popularity") {
        if (sortField === "popularity" || ratingSortMode === "votes") {
          const av = totalRatingVotes(a);
          const bv = totalRatingVotes(b);
          cmp = av - bv;
        } else {
          const ar = a.rating_avg_5 != null ? Number(a.rating_avg_5) : -1;
          const br = b.rating_avg_5 != null ? Number(b.rating_avg_5) : -1;
          cmp = ar - br;
        }
        if (cmp === 0) cmp = compareTitles(a.title, b.title);
      } else {
        cmp = compareTitles(a.title, b.title);
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

  function moviePassesFilters(m, activeSources) {
    if (activeSources.length === 0) {
      return false;
    }
    if (activeSources.length < 3 && !activeSources.includes(m.source)) {
      return false;
    }
    if (selectedGenre !== "all" && !(m.genres || []).includes(selectedGenre)) {
      return false;
    }
    if (!movieMatchesServiceFilter(m)) return false;
    return true;
  }

  function getPreSortFilteredRows() {
    const activeSources = getActiveSources();
    return movies.filter((mm) => moviePassesFilters(mm, activeSources));
  }

  function countSourcesInRows(list) {
    let lb = 0;
    let both = 0;
    let im = 0;
    for (const m of list) {
      if (m.source === "letterboxd") lb++;
      else if (m.source === "both") both++;
      else if (m.source === "imdb") im++;
    }
    return { lb, both, im };
  }

  function setSrcCountDisplay(wrap, filteredEl, totalEl, visible, total) {
    if (!wrap || !totalEl) return;
    const stale = visible !== total;
    wrap.classList.toggle("srcbtn-count--stale", stale);
    totalEl.textContent = String(total);
    if (filteredEl) {
      if (stale) {
        filteredEl.hidden = false;
        filteredEl.textContent = String(visible);
      } else {
        filteredEl.hidden = true;
        filteredEl.textContent = "";
      }
    }
  }

  function updateSourceCountUi(filteredMovies) {
    const v = countSourcesInRows(filteredMovies);
    setSrcCountDisplay(srcCountLb, countLbFiltered, countLb, v.lb, lbCount);
    setSrcCountDisplay(srcCountBoth, countBothFiltered, countBoth, v.both, bothCount);
    setSrcCountDisplay(srcCountImdb, countImdbFiltered, countImdb, v.im, imdbCount);
  }

  const watchBackdrop = document.getElementById("watchBackdrop");
  const watchPanelHost = document.getElementById("watchPanelHost");
  const mobileWatchMq = window.matchMedia("(max-width: 640px)");
  const ratingHoverDesktopMq = window.matchMedia("(hover: hover) and (pointer: fine)");

  function ratingHoverDesktopActive() {
    return ratingHoverDesktopMq.matches && !mobileWatchMq.matches;
  }

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
    updateWatchScrollDismissListeners();
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

  let watchScrollDismissBound = false;
  function watchScrollDismissHandler(e) {
    if (!mobileWatchMq.matches) return;
    if (!gridEl.querySelector("details.watch-details[open]")) return;
    const t = e && e.target;
    if (t && typeof t.closest === "function" && t.closest(".watch-body")) return;
    gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
      d.open = false;
    });
  }

  function updateWatchScrollDismissListeners() {
    const need = mobileWatchMq.matches && !!gridEl.querySelector("details.watch-details[open]");
    if (need && !watchScrollDismissBound) {
      document.addEventListener("wheel", watchScrollDismissHandler, { capture: true, passive: true });
      document.addEventListener("touchmove", watchScrollDismissHandler, { capture: true, passive: true });
      watchScrollDismissBound = true;
    } else if (!need && watchScrollDismissBound) {
      document.removeEventListener("wheel", watchScrollDismissHandler, { capture: true });
      document.removeEventListener("touchmove", watchScrollDismissHandler, { capture: true });
      watchScrollDismissBound = false;
    }
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
    updateWatchScrollDismissListeners();
  }

  function positionWatchPanel(detail) {
    if (!mobileWatchMq.matches) return;
    const body = getWatchBodyForDetail(detail);
    if (!body) return;
    const pad = 16;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const maxW = Math.min(420, Math.floor(vw * 0.92), vw - 2 * pad);
    const maxAvail = Math.max(140, Math.floor(vh * 0.9) - 2 * pad);

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

  /** Inline card dropdown (tablet/desktop): cap height so the menu stays in the viewport. */
  function clampWatchBodyToViewport(detail) {
    if (!detail || mobileWatchMq.matches) return;
    const body = detail.querySelector(".watch-body");
    if (!body) return;
    body.style.maxHeight = "";
    body.style.overflowY = "";
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const pad = 12;
        const r = body.getBoundingClientRect();
        const natural = body.scrollHeight;
        const availBelow = window.innerHeight - r.top - pad;
        if (availBelow <= 0 || natural <= availBelow) return;
        const cap = Math.max(100, Math.min(natural, availBelow));
        body.style.maxHeight = `${cap}px`;
        body.style.overflowY = "auto";
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
        } else {
          clampWatchBodyToViewport(d);
        }
      } else {
        restoreWatchBodyToDetail(d);
        clearWatchPanelLayout(d);
        syncWatchBackdrop();
      }
    },
    true,
  );

  /* Mobile: dimmer uses pointer-events none so Watch summary stays clickable; close from outside via capture */
  document.addEventListener(
    "click",
    (e) => {
      if (!mobileWatchMq.matches) return;
      if (!gridEl.querySelector("details.watch-details[open]")) return;
      if (e.target.closest(".watch-body") || e.target.closest(".watch-summary")) return;
      gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
        d.open = false;
      });
    },
    true,
  );

  let watchSwipeStart = null;
  if (watchPanelHost) {
    watchPanelHost.addEventListener(
      "click",
      (e) => {
        if (!mobileWatchMq.matches) return;
        const body = e.target.closest(".watch-body");
        if (!body || !watchPanelHost.contains(body)) return;
        if (e.target.closest("a[href], button, input, label, summary")) return;
        const content = body.querySelector(".watch-body__content");
        if (!content) return;
        const r = content.getBoundingClientRect();
        const { clientX: cx, clientY: cy } = e;
        const inContent = cx >= r.left && cx <= r.right && cy >= r.top && cy <= r.bottom;
        const onChrome =
          !inContent ||
          e.target.closest(".prov-label") ||
          e.target.classList.contains("watch-body__content");
        if (!onChrome) return;
        gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
          d.open = false;
        });
        syncWatchBackdrop();
      },
      true,
    );

    watchPanelHost.addEventListener(
      "touchstart",
      (e) => {
        if (!mobileWatchMq.matches || e.touches.length !== 1) return;
        const b = e.target.closest(".watch-body");
        if (!b || !watchPanelHost.contains(b)) return;
        watchSwipeStart = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY,
          scrollTop: b.scrollTop,
          body: b,
        };
      },
      { passive: true },
    );
    watchPanelHost.addEventListener(
      "touchend",
      (e) => {
        if (!watchSwipeStart || e.changedTouches.length !== 1) {
          watchSwipeStart = null;
          return;
        }
        const t = e.changedTouches[0];
        const dx = t.clientX - watchSwipeStart.x;
        const dy = t.clientY - watchSwipeStart.y;
        const dist = Math.hypot(dx, dy);
        const b = watchSwipeStart.body;
        const scrollable = b.scrollHeight > b.clientHeight + 2;
        const scrollDelta = Math.abs(b.scrollTop - watchSwipeStart.scrollTop);
        watchSwipeStart = null;
        if (dist < 52) return;
        if (scrollable && Math.abs(dy) >= Math.abs(dx) && scrollDelta > 10) return;
        gridEl.querySelectorAll("details.watch-details[open]").forEach((d) => {
          d.open = false;
        });
        syncWatchBackdrop();
      },
      { passive: true },
    );
    watchPanelHost.addEventListener("touchcancel", () => {
      watchSwipeStart = null;
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
    updateWatchScrollDismissListeners();
  }
  window.addEventListener("resize", onWatchLayoutMqChange);
  window.addEventListener("resize", () => {
    if (genreMoreAnchor) positionGenreMorePopover(genreMoreAnchor);
    const openWd = gridEl.querySelector("details.watch-details[open]");
    if (openWd && !mobileWatchMq.matches) clampWatchBodyToViewport(openWd);
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

  function setRatingBlockOpen(block, open) {
    const btn = block.querySelector(".rating-stars-toggle");
    const overlay = block.querySelector(".rating-value-overlay");
    if (!btn || !overlay) return;
    block.classList.toggle("rating-block--open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    overlay.setAttribute("aria-hidden", open ? "false" : "true");
    if (!open) btn.blur();
  }

  function closeOpenRatingBlocks() {
    gridEl.querySelectorAll(".rating-block--open").forEach((block) => {
      setRatingBlockOpen(block, false);
    });
  }

  function cardHtmlForMovie(m, i) {
    const ratingHtml = ratingBlockHtml(m);
    const watchHtml = watchBlockHtml(m, `watch-card-${i}`);
    const ratingRowHtml =
      ratingHtml || watchHtml ? `<div class="card-rating-row">${ratingHtml}${watchHtml}</div>` : "";
    const srcKey = String(m.source || "")
      .trim()
      .toLowerCase();
    const srcCard =
      srcKey === "letterboxd"
        ? "card--src-letterboxd"
        : srcKey === "both"
          ? "card--src-both"
          : srcKey === "imdb"
            ? "card--src-imdb"
            : "";
    return `
      <article class="card ${srcCard}">
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
  }

  function finishGridLoading(gen) {
    if (gen !== gridRenderGeneration) return;
    teardownGridLoadObserver();
    const sentinel = document.getElementById("gridLoadSentinel");
    if (sentinel) sentinel.remove();
  }

  function loadMoreGridRows(gen) {
    if (gen !== gridRenderGeneration) return;
    const rows = gridRowsBuffer;
    const start = gridDisplayedCount;
    if (start >= rows.length) {
      finishGridLoading(gen);
      return;
    }
    const end = Math.min(start + GRID_BATCH_SIZE, rows.length);
    const html = rows.slice(start, end).map((m, idx) => cardHtmlForMovie(m, start + idx)).join("");
    const sentinel = document.getElementById("gridLoadSentinel");
    if (!sentinel || gen !== gridRenderGeneration) return;
    sentinel.insertAdjacentHTML("beforebegin", html);
    gridDisplayedCount = end;
    requestAnimationFrame(() => {
      if (gen !== gridRenderGeneration) return;
      syncGenreOverflow();
      requestAnimationFrame(() => {
        if (gen !== gridRenderGeneration) return;
        syncGenreOverflow();
        updateScrollTopBtn();
      });
    });
    if (gridDisplayedCount >= rows.length) {
      finishGridLoading(gen);
    }
  }

  function setupGridLoadObserver(gen) {
    teardownGridLoadObserver();
    if (gen !== gridRenderGeneration) return;
    if (gridDisplayedCount >= gridRowsBuffer.length) return;
    const sentinel = document.getElementById("gridLoadSentinel");
    if (!sentinel) return;
    gridLoadObserver = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        if (gen !== gridRenderGeneration) return;
        loadMoreGridRows(gen);
      },
      { root: null, rootMargin: "0px 0px 400px 0px", threshold: 0 },
    );
    gridLoadObserver.observe(sentinel);
  }

  function runAfterGridPaint(gen, setupObserver) {
    requestAnimationFrame(() => {
      if (gen !== gridRenderGeneration) return;
      syncGenreOverflow();
      requestAnimationFrame(() => {
        if (gen !== gridRenderGeneration) return;
        syncGenreOverflow();
        updateScrollTopBtn();
        if (setupObserver) setupGridLoadObserver(gen);
      });
    });
  }

  let renderDebounceTimer = 0;
  const RENDER_DEBOUNCE_MS = 32;
  function scheduleRender() {
    if (renderDebounceTimer) clearTimeout(renderDebounceTimer);
    renderDebounceTimer = setTimeout(() => {
      renderDebounceTimer = 0;
      requestAnimationFrame(() => {
        render();
      });
    }, RENDER_DEBOUNCE_MS);
  }

  function render() {
    closeGenreMorePopover();
    gridRenderGeneration += 1;
    const gen = gridRenderGeneration;

    const filtered = getPreSortFilteredRows();
    updateSourceCountUi(filtered);
    const rows = [...filtered];
    sortRows(rows);

    if (!rows.length) {
      flushWatchPortalBeforeRender();
      teardownGridLoadObserver();
      gridRowsBuffer = [];
      gridDisplayedCount = 0;
      gridEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      syncUrl();
      updateScrollTopBtn();
      return;
    }
    emptyEl.classList.add("hidden");
    flushWatchPortalBeforeRender();
    teardownGridLoadObserver();
    gridRowsBuffer = rows;
    const firstEnd = Math.min(GRID_BATCH_SIZE, rows.length);
    gridDisplayedCount = firstEnd;
    const firstHtml = rows.slice(0, firstEnd).map((m, i) => cardHtmlForMovie(m, i)).join("");
    const needsMore = firstEnd < rows.length;
    gridEl.innerHTML = needsMore
      ? `${firstHtml}<div class="grid-load-sentinel" id="gridLoadSentinel" aria-hidden="true"></div>`
      : firstHtml;
    syncUrl();
    runAfterGridPaint(gen, needsMore);
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
    const open = !wasOpen;
    setRatingBlockOpen(block, open);
  });

  gridEl.addEventListener("mouseover", (e) => {
    if (!ratingHoverDesktopActive()) return;
    const block = e.target.closest(".rating-block");
    if (!block || !gridEl.contains(block)) return;
    const from = e.relatedTarget;
    if (from && block.contains(from)) return;
    closeOpenRatingBlocks();
    setRatingBlockOpen(block, true);
  });

  gridEl.addEventListener("mouseout", (e) => {
    if (!ratingHoverDesktopActive()) return;
    const block = e.target.closest(".rating-block");
    if (!block || !gridEl.contains(block)) return;
    const rel = e.relatedTarget;
    if (rel && block.contains(rel)) return;
    setRatingBlockOpen(block, false);
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
          setRatingBlockOpen(block, false);
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
    closeOtherFilterSortPopovers("genre");
    const next = !isGenreOpen();
    setGenreOpen(next, { focusFilter: next });
  });

  genreBtn.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      closeOtherFilterSortPopovers("genre");
      const next = !isGenreOpen();
      setGenreOpen(next, { focusFilter: next });
    }
  });

  const genreFilterEl = getGenreFilterInput();
  if (genreFilterEl) {
    genreFilterEl.addEventListener("input", () => {
      syncGenreClearVisibility();
      renderGenreList();
    });
    genreFilterEl.addEventListener("click", (e) => e.stopPropagation());
  }
  const genreClearEl = getGenreClearBtn();
  if (genreClearEl) {
    genreClearEl.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const fi = getGenreFilterInput();
      if (fi) {
        fi.value = "";
        syncGenreClearVisibility();
        renderGenreList();
        fi.focus();
      }
    });
  }

  genrePopup.addEventListener("click", (e) => {
    const opt = e.target.closest(".genre-option");
    if (!opt) return;
    selectedGenre = opt.dataset.genre;
    syncGenreAriaSelected();
    setGenreOpen(false, {});
    updateSortUi();
    scheduleRender();
  });

  if (servicesBtn && servicesPopup) {
    servicesBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeOtherFilterSortPopovers("services");
      const next = !isServicesOpen();
      setServicesOpen(next, {});
    });
    servicesBtn.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        closeOtherFilterSortPopovers("services");
        const next = !isServicesOpen();
        setServicesOpen(next, { focusFirst: next });
      }
    });
    servicesPopup.addEventListener("click", (e) => {
      if (e.target.closest("[data-service-action='done']")) {
        setServicesOpen(false, {});
        return;
      }
      const clr = e.target.closest("[data-service-action='clear']");
      if (!clr) return;
      selectedServiceIds = new Set();
      syncServiceCheckboxUi();
      updateSortUi();
      scheduleRender();
      setServicesOpen(false, {});
    });
    servicesPopup.addEventListener("change", (e) => {
      const inp = e.target;
      if (!(inp instanceof HTMLInputElement) || inp.name !== "svc") return;
      const id = Number(inp.value);
      if (!Number.isFinite(id)) return;
      if (inp.checked) selectedServiceIds.add(id);
      else selectedServiceIds.delete(id);
      updateSortUi();
      scheduleRender();
    });
  }

  if (genreSheetBackdrop) {
    genreSheetBackdrop.addEventListener("click", () => setGenreOpen(false, {}));
  }
  if (servicesSheetBackdrop) {
    servicesSheetBackdrop.addEventListener("click", () => setServicesOpen(false, {}));
  }
  if (sortSheetBackdrop) {
    sortSheetBackdrop.addEventListener("click", () => setSortOpen(false, { focusButtonOnClose: true }));
  }

  if (sortMobileBtn && sortPopup) {
    sortMobileBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeOtherFilterSortPopovers("sort");
      const next = !isSortOpen();
      setSortOpen(next, { focusFirst: next });
    });
    sortMobileBtn.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        closeOtherFilterSortPopovers("sort");
        const next = !isSortOpen();
        setSortOpen(next, { focusFirst: next });
      }
    });
    sortPopup.addEventListener("click", (e) => {
      e.stopPropagation();
      const fieldBtn = e.target.closest("[data-sort-field]");
      if (fieldBtn) {
        const clickedField = fieldBtn.getAttribute("data-sort-field");
        if (clickedField === sortField) toggleMobileSortDirection();
        else setMobileSortField(clickedField);
        updateSortUi();
        scheduleRender();
        return;
      }
      if (e.target.closest("[data-sort-action='done']")) {
        setSortOpen(false, { focusButtonOnClose: true });
      }
    });
  }

  function updateScrollTopBtn() {
    if (!scrollTopBtn) return;
    const doc = document.documentElement;
    const sh = doc.scrollHeight - window.innerHeight;
    const threshold = sh > 200 ? Math.min(420, sh * 0.2) : 400;
    const visible = window.scrollY > threshold;
    scrollTopBtn.classList.toggle("scroll-top-btn--visible", visible);
    scrollTopBtn.tabIndex = visible ? 0 : -1;
  }
  if (scrollTopBtn) {
    window.addEventListener("scroll", updateScrollTopBtn, { passive: true });
    window.addEventListener("resize", updateScrollTopBtn);
    scrollTopBtn.addEventListener("click", () => {
      const instant = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: instant ? "auto" : "smooth" });
      const focusMain = () => {
        if (mainContentEl && typeof mainContentEl.focus === "function") {
          mainContentEl.focus({ preventScroll: true });
        }
      };
      if (instant) {
        focusMain();
      } else {
        window.setTimeout(focusMain, 450);
      }
    });
    updateScrollTopBtn();
  }

  const HINT_KEY = "docsServicesHintDismissed";
  let servicesHintEl = null;
  function removeServicesHint() {
    if (!servicesHintEl) return;
    servicesHintEl.remove();
    servicesHintEl = null;
    try {
      localStorage.setItem(HINT_KEY, "1");
    } catch {
      /* ignore */
    }
  }
  function positionServicesHint() {
    if (!servicesHintEl || !servicesBtn) return;
    const r = servicesBtn.getBoundingClientRect();
    const w = servicesHintEl.offsetWidth;
    const h = servicesHintEl.offsetHeight;
    const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 8));
    const top = Math.max(8, r.top - h - 8);
    servicesHintEl.style.left = `${left}px`;
    servicesHintEl.style.top = `${top}px`;
  }
  function maybeShowServicesHint() {
    try {
      if (localStorage.getItem(HINT_KEY)) return;
    } catch {
      return;
    }
    if (!servicesBtn) return;
    servicesHintEl = document.createElement("div");
    servicesHintEl.className = "services-hint";
    servicesHintEl.setAttribute("role", "tooltip");
    servicesHintEl.textContent = "Select your services";
    document.body.appendChild(servicesHintEl);
    requestAnimationFrame(() => {
      requestAnimationFrame(positionServicesHint);
    });
    function onHintResize() {
      positionServicesHint();
    }
    window.addEventListener("resize", onHintResize);
    let hintDismissed = false;
    function dismissServicesHintUi() {
      if (hintDismissed) return;
      hintDismissed = true;
      window.removeEventListener("resize", onHintResize);
      removeServicesHint();
    }
    servicesBtn.addEventListener("click", dismissServicesHintUi, { once: true });
    setTimeout(() => {
      document.addEventListener(
        "pointerdown",
        (e) => {
          if (servicesBtn.contains(e.target)) return;
          dismissServicesHintUi();
        },
        { once: true, capture: true },
      );
    }, 120);
  }
  requestAnimationFrame(() => requestAnimationFrame(maybeShowServicesHint));

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
    if (
      servicesPopup &&
      servicesBtn &&
      !servicesPopup.contains(e.target) &&
      e.target !== servicesBtn &&
      !servicesBtn.contains(e.target)
    ) {
      if (isServicesOpen()) setServicesOpen(false, {});
    }
    if (
      sortPopup &&
      sortMobileBtn &&
      isSortOpen() &&
      !sortPopup.contains(e.target) &&
      e.target !== sortMobileBtn &&
      !sortMobileBtn.contains(e.target)
    ) {
      setSortOpen(false, {});
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
    if (isSortOpen()) {
      e.preventDefault();
      setSortOpen(false, { focusButtonOnClose: true });
      return;
    }
    if (isServicesOpen()) {
      e.preventDefault();
      setServicesOpen(false, { focusButtonOnClose: true });
      return;
    }
    if (isGenreOpen()) {
      e.preventDefault();
      setGenreOpen(false, { focusButtonOnClose: true });
    }
  });

  function onGenreTruncateMqChange() {
    updateSortUi();
    if (!isPopupSheetMode()) {
      mountPopupForMobileSheet(genrePopup, genrePopupOriginalParent, genrePopupOriginalNext, false, false);
      mountPopupForMobileSheet(
        servicesPopup,
        servicesPopupOriginalParent,
        servicesPopupOriginalNext,
        false,
        false,
      );
      mountSortPopupForMobileSheet(false, false);
      genrePopup.classList.remove("genre-popup--mobile");
      if (servicesPopup) servicesPopup.classList.remove("services-popup--mobile");
      if (sortPopup) sortPopup.classList.remove("sort-popup--mobile");
      if (genreSheetBackdrop) {
        genreSheetBackdrop.classList.add("hidden");
        genreSheetBackdrop.setAttribute("aria-hidden", "true");
      }
      if (servicesSheetBackdrop) {
        servicesSheetBackdrop.classList.add("hidden");
        servicesSheetBackdrop.setAttribute("aria-hidden", "true");
      }
      if (sortSheetBackdrop) {
        sortSheetBackdrop.classList.add("hidden");
        sortSheetBackdrop.setAttribute("aria-hidden", "true");
      }
    }
  }
  if (genreTruncateMq.addEventListener) {
    genreTruncateMq.addEventListener("change", onGenreTruncateMqChange);
  } else {
    genreTruncateMq.addListener(onGenreTruncateMqChange);
  }
  if (popupSheetMq.addEventListener) {
    popupSheetMq.addEventListener("change", onGenreTruncateMqChange);
  } else {
    popupSheetMq.addListener(onGenreTruncateMqChange);
  }
})();
