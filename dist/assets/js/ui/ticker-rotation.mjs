/**
 * Splits the market strip into balanced rows when its items do not fit on
 * one line: 6 items in room for 4 become 2 rows of 3, not 4 + 2.
 */
export function tickerLayout(count, width, minWidth) {
  if (!(count > 0)) return { perRow: 0, rows: 0 };
  if (!(width > 0 && minWidth > 0)) return { perRow: count, rows: 1 };
  const fit = Math.max(1, Math.floor(width / minWidth));
  if (fit >= count) return { perRow: count, rows: 1 };
  const rows = Math.ceil(count / fit);
  return { perRow: Math.ceil(count / rows), rows };
}

/**
 * Rotates the strip upwards one row at a time when it overflows. The app
 * re-renders the whole shell on every state change, so the visible row lives
 * here and is reapplied without animation after each render. Rotation pauses
 * while the strip is hovered or focused, while the tab is hidden and for
 * users who prefer reduced motion; the DOM content never changes, so assistive
 * technology reads every reference without announcements.
 */
export function createTickerRotation({ interval = 5000 } = {}) {
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let strip = null;
  let track = null;
  let observer = null;
  let layout = { perRow: 0, rows: 0 };
  let row = 0;
  let timer = null;

  const items = () => [...track.querySelectorAll(".ticker-item:not(.ticker-clone)")];

  function show(index, animate) {
    track.classList.toggle("is-snapping", !animate);
    track.style.setProperty("--ticker-row", String(index));
    if (!animate) void track.offsetHeight;
    track.classList.remove("is-snapping");
  }

  function measure() {
    if (!strip?.isConnected) return;
    const real = items();
    const minWidth = parseFloat(getComputedStyle(strip).getPropertyValue("--ticker-min-width")) || 156;
    const next = reducedMotion.matches
      ? { perRow: real.length, rows: 1 }
      : tickerLayout(real.length, strip.clientWidth, minWidth);
    track.querySelectorAll(".ticker-clone").forEach((clone) => clone.remove());
    // A copy of the first row after the last one keeps the wrap moving upwards.
    if (next.rows > 1)
      for (const item of real.slice(0, next.perRow)) {
        const clone = item.cloneNode(true);
        clone.classList.add("ticker-clone");
        clone.setAttribute("aria-hidden", "true");
        clone.setAttribute("tabindex", "-1");
        clone.inert = true;
        track.append(clone);
      }
    if (next.perRow !== layout.perRow || row >= next.rows) row = 0;
    layout = next;
    track.style.setProperty("--ticker-per-row", String(Math.max(1, next.perRow)));
    show(row, false);
  }

  function advance() {
    if (!strip?.isConnected || layout.rows < 2 || document.hidden ||
        reducedMotion.matches || strip.matches(":hover, :focus-within")) return;
    row += 1;
    show(row, true);
    if (row === layout.rows) {
      row = 0;
      const current = track;
      const settle = (event) => {
        if (event.target !== current) return;
        current.removeEventListener("transitionend", settle);
        if (current === track && row === 0) show(0, false);
      };
      current.addEventListener("transitionend", settle);
    }
  }

  // Focusing a hidden item makes the browser scroll the clipped strip; the
  // transform alone decides which row is visible.
  function unscroll() {
    if (strip.scrollTop) strip.scrollTop = 0;
  }

  function reveal(event) {
    const item = event.target.closest(".ticker-item:not(.ticker-clone)");
    if (!item || layout.rows < 2) return;
    const target = Math.floor(items().indexOf(item) / layout.perRow);
    if (target >= 0 && target !== row) {
      row = target;
      show(row, false);
    }
    unscroll();
  }

  return {
    attach(root) {
      observer?.disconnect();
      strip = root.querySelector(".ticker-strip");
      track = strip?.querySelector(".ticker-track");
      if (!strip || !track) return;
      strip.addEventListener("focusin", reveal);
      strip.addEventListener("scroll", unscroll);
      observer = new ResizeObserver(measure);
      observer.observe(strip);
      measure();
      if (!timer) {
        timer = setInterval(advance, interval);
        reducedMotion.addEventListener("change", measure);
      }
    },
  };
}
