// What the page does in the browser (design 12.1, third version). Every page works without this
// file: links and forms then load whole pages. With it, a project opens in a window over the list,
// the windows of the bottom of the page open in place, each (i) explains its term on hover or on a
// tap, the last search stays until it is cleared, and the first page of a visit shows the name of
// the tool for a moment.
(function () {
  "use strict";
  var HOVER = window.matchMedia("(hover: hover) and (pointer: fine)");
  var FAILED = "The comparison with your idea could not be generated just now. " +
    "Everything else on this page is complete.";

  function $(id) { return document.getElementById(id); }
  function store(kind) { try { return window[kind]; } catch (error) { return null; } }

  // ---------------------------------------------------------------- the first screen of a visit
  function endSplash() {
    var root = document.documentElement;
    if (!root.classList.contains("hm-splash")) return;
    root.classList.remove("hm-splash");
    var session = store("sessionStorage");
    if (session) session.setItem("hm-seen", "1");
  }
  if (document.documentElement.classList.contains("hm-splash")) {
    window.setTimeout(endSplash, 1450);
    ["keydown", "pointerdown", "wheel", "touchstart"].forEach(function (name) {
      window.addEventListener(name, endSplash, { once: true, passive: true });
    });
  }

  // ---------------------------------------------------------------- the switch of the theme
  // The choice is kept in this browser; "auto" follows the computer, also when the computer
  // changes. The script in the head of the page applies it before the page is drawn.
  var DARK = window.matchMedia("(prefers-color-scheme: dark)");
  function chosenTheme() {
    var local = store("localStorage");
    var chosen = local && local.getItem("hm-theme");
    return chosen === "light" || chosen === "dark" ? chosen : "auto";
  }
  function applyTheme(choice) {
    var root = document.documentElement;
    var theme = (choice === "auto" ? DARK.matches : choice === "dark") ? "dark" : "light";
    document.querySelectorAll("input[name=hm-theme]").forEach(function (input) {
      input.checked = input.value === choice;
    });
    if (root.getAttribute("data-bs-theme") === theme) return;
    root.setAttribute("data-bs-theme", theme);
    if (!window.Chart) return;
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var chart = window.Chart.getChart(canvas); // Chart.js 4.5.1: the chart drawn on this canvas
      if (chart) chart.destroy();
      delete canvas.dataset.drawn;
    });
    drawCharts(document); // the colours of the charts come from the theme
  }
  document.addEventListener("change", function (event) {
    if (!event.target.matches("input[name=hm-theme]")) return;
    var choice = event.target.value;
    try {
      if (choice === "auto") window.localStorage.removeItem("hm-theme");
      else window.localStorage.setItem("hm-theme", choice);
    } catch (error) { /* the browser keeps nothing: the choice holds for this page only */ }
    applyTheme(choice);
  });
  DARK.addEventListener("change", function () { if (chosenTheme() === "auto") applyTheme("auto"); });

  // ---------------------------------------------------------------- the last search is kept
  function remember(address) {
    var local = store("localStorage");
    if (!local) return;
    var url = new URL(address, window.location.origin);
    if (url.pathname !== "/") return;
    url.searchParams.delete("open");
    var query = url.searchParams.toString();
    if (query) local.setItem("hm-last", query); else local.removeItem("hm-last");
  }
  document.addEventListener("htmx:pushedIntoHistory", function (event) { remember(event.detail.path); });
  document.addEventListener("htmx:replacedInHistory", function (event) { remember(event.detail.path); });

  // ---------------------------------------------------------------- the box of the idea
  function box() { return $("idea"); }
  function showCount() {
    var idea = box(), out = $("idea-count");
    if (!idea || !out) return;
    var limit = Number(out.getAttribute("data-limit")) || idea.maxLength;
    var used = idea.value.length;
    out.textContent = used.toLocaleString("en") + " of " + limit.toLocaleString("en") + " characters";
    out.classList.toggle("near", used > limit * 0.9);
    var empty = !idea.value.trim();
    var ai = $("ai-button");
    if (ai) ai.disabled = empty;
    var examples = document.querySelector(".try");
    if (examples) examples.hidden = !empty;
  }
  document.addEventListener("input", function (event) {
    if (event.target === box()) showCount();
  });
  document.addEventListener("keydown", function (event) {
    var idea = box();
    // Enter shows the quick results at once; Shift and Enter makes a new line.
    if (event.target === idea && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (idea.form && idea.form.requestSubmit) idea.form.requestSubmit();
    }
  });
  // "Clear the search": htmx loads the empty page; the browser forgets the last search first.
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-clear-search]")) return;
    var local = store("localStorage");
    if (local) local.removeItem("hm-last");
  }, true);

  // "Check your GitHub link here", under the results: the box of the check takes the cursor.
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-focus-check]")) return;
    var box = $("check-repo");
    if (!box) return;
    event.preventDefault();
    box.scrollIntoView({ block: "center" });
    box.focus({ preventScroll: true });
  });

  // ---------------------------------------------------------------- the check of a submission
  document.addEventListener("change", function (event) {
    if (event.target.id !== "check-event") return;
    var search = $("check-event-search");
    if (search && search.value) { // a choice ends the search: the whole list comes back
      search.value = "";
      searchHackathons(search);
    }
    var other = event.target.value === "other";
    var days = document.querySelector("[data-check-days]");
    if (!days) return;
    days.hidden = !other;
    days.querySelectorAll("input").forEach(function (input) { input.required = other; });
  });

  // The box above the list of hackathons (design 12.1, S3): it keeps the hackathons whose name
  // holds its words and opens the list to show them; Enter picks the first, Escape empties the
  // box, and the down arrow goes into the list. "None" and "Other hackathon" always stay
  // (1 November 2026).
  function searchHackathons(box) {
    var list = $("check-event");
    if (!list) return [];
    var words = box.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var kept = [];
    list.querySelectorAll("option").forEach(function (option) {
      if (option.value === "" || option.value === "other") return;
      var name = option.textContent.toLowerCase();
      var keep = words.every(function (word) { return name.indexOf(word) !== -1; });
      option.hidden = !keep;
      if (keep) kept.push(option);
    });
    var years = 0; // each year's heading takes a line of the list too
    list.querySelectorAll("optgroup").forEach(function (group) {
      group.hidden = !group.querySelector("option:not([hidden])");
      if (!group.hidden) years += 1;
    });
    if (words.length) list.size = Math.max(2, Math.min(10, kept.length + years + 2));
    else list.removeAttribute("size");
    return kept;
  }
  document.addEventListener("input", function (event) {
    if (event.target.id === "check-event-search") searchHackathons(event.target);
  });
  document.addEventListener("keydown", function (event) {
    if (event.target.id !== "check-event-search") return;
    var list = $("check-event");
    if (event.key === "Enter") {
      event.preventDefault(); // the box picks a hackathon; it does not send the check
      var first = searchHackathons(event.target)[0];
      if (first && list) {
        list.value = first.value;
        list.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } else if (event.key === "Escape" && event.target.value) {
      event.preventDefault();
      event.target.value = "";
      searchHackathons(event.target);
    } else if (event.key === "ArrowDown" && list && list.size > 1) {
      event.preventDefault();
      list.focus();
    }
  });

  // ---------------------------------------------------------------- the charts
  // Each canvas carries its numbers; Chart.js draws them as horizontal bars, all the projects
  // and those with a Hedera prize. The same numbers stand in a list for screen readers.
  // Chart.js gives the labels of a horizontal chart at most half of its width; a longer label
  // is cut at the left edge (seen on 18 October 2026), so it breaks into lines here.
  // A label in lines of 22 characters at most. It breaks at spaces, and a long name with none,
  // such as a package name, after a "/" or a "-".
  function lines(label) {
    var words = [], out = [], line = "";
    String(label).split(" ").forEach(function (word) {
      if (word.length <= 22) words.push(word);
      else words.push.apply(words, word.match(/[^\/-]+[\/-]?|[\/-]/g));
    });
    words.forEach(function (word) {
      var joined = line + (line && !/[\/-]$/.test(line) ? " " : "") + word;
      if (line && joined.length > 22) { out.push(line); line = word; }
      else line = joined;
    });
    if (line) out.push(line);
    return out.length > 1 ? out : out[0];
  }
  function drawCharts(root) {
    if (!window.Chart) return;
    var style = window.getComputedStyle(document.body);
    var theme = window.getComputedStyle(document.documentElement);
    var all = theme.getPropertyValue("--hm-chart-all").trim() || "#007654";
    var won = theme.getPropertyValue("--hm-chart-won").trim() || "#a15c00";
    window.Chart.defaults.color = style.color;
    window.Chart.defaults.font.family = style.fontFamily;
    (root || document).querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      // A chart on a hidden tab has no size yet: it is drawn when its tab is shown.
      if (canvas.dataset.drawn || canvas.closest("[hidden]")) return;
      canvas.dataset.drawn = "1";
      var numbers = JSON.parse(canvas.getAttribute("data-chart"));
      var colours = { all: all, won: won };
      // A comparison gives its own series of shares; the other charts give two counts.
      var series = numbers.series || [
        { label: "Projects", data: numbers.all, color: "all" },
        { label: "With a Hedera prize", data: numbers.won, color: "won" }
      ];
      var unit = numbers.unit || "";
      new window.Chart(canvas, {
        type: "bar",
        data: {
          labels: numbers.labels,
          datasets: series.map(function (one) {
            // a chart of few rows is 140 pixels high (_parts.html): its bars stay bars
            return { label: one.label, data: one.data, backgroundColor: colours[one.color] || all, borderRadius: 3, barPercentage: 0.9, maxBarThickness: 20 };
          })
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
            tooltip: { callbacks: { label: function (item) { return item.dataset.label + ": " + item.formattedValue + unit; } } }
          },
          scales: {
            x: unit ? { beginAtZero: true, max: 100, ticks: { callback: function (value) { return value + unit; } } }
                    : { beginAtZero: true, ticks: { precision: 0 } },
            y: { ticks: { autoSkip: false, callback: function (value) { return lines(this.getLabelForValue(value)); } } }
          }
        }
      });
    });
  }

  // ---------------------------------------------------------------- the tabs of the insights
  // Without this file the four parts show one under the other. With it, one part shows at a
  // time, the arrow keys move between the tabs, and the tab chosen stays for the visit.
  function showTab(tabs, key, focus) {
    var shown = null;
    tabs.querySelectorAll("[role=tab]").forEach(function (tab) {
      var on = tab.getAttribute("data-tab") === key;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.classList.toggle("active", on);
      tab.tabIndex = on ? 0 : -1;
      if (on && focus) tab.focus();
      var panel = $(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
      if (on) shown = panel;
    });
    if (shown) drawCharts(shown);
    var session = store("sessionStorage");
    if (session) session.setItem("hm-tab", key);
  }
  function setUpTabs(root) {
    (root || document).querySelectorAll("[data-tabs]").forEach(function (tabs) {
      if (tabs.dataset.ready) return;
      tabs.dataset.ready = "1";
      var list = tabs.querySelector("[role=tablist]");
      if (list) list.hidden = false;
      var keys = Array.prototype.map.call(tabs.querySelectorAll("[role=tab]"), function (tab) {
        return tab.getAttribute("data-tab");
      });
      var session = store("sessionStorage");
      var kept = session && session.getItem("hm-tab");
      showTab(tabs, keys.indexOf(kept) >= 0 ? kept : keys[0], false);
    });
  }
  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-tabs] [role=tab]");
    if (tab) showTab(tab.closest("[data-tabs]"), tab.getAttribute("data-tab"), false);
  });
  document.addEventListener("keydown", function (event) {
    var tab = event.target.closest && event.target.closest("[data-tabs] [role=tab]");
    if (!tab) return;
    var all = Array.prototype.slice.call(tab.closest("[role=tablist]").querySelectorAll("[role=tab]"));
    var at = all.indexOf(tab), next = null;
    if (event.key === "ArrowRight") next = all[(at + 1) % all.length];
    else if (event.key === "ArrowLeft") next = all[(at + all.length - 1) % all.length];
    else if (event.key === "Home") next = all[0];
    else if (event.key === "End") next = all[all.length - 1];
    if (!next) return;
    event.preventDefault();
    showTab(tab.closest("[data-tabs]"), next.getAttribute("data-tab"), true);
  });

  // ---------------------------------------------------------------- the (i) and its text
  var home = null; // where the texts live when no window is open
  var openTimer = 0, closeTimer = 0, current = null;
  function place(tip, button) {
    var rect = button.getBoundingClientRect();
    tip.style.left = "0px"; tip.style.top = "0px";
    var width = tip.offsetWidth, height = tip.offsetHeight;
    var left = Math.min(Math.max(8, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 8);
    var below = rect.bottom + 8, above = rect.top - height - 8;
    // Below when it fits, else above when it fits. A text taller than both stands whole on the
    // screen, over its (i) if need be, and scrolls inside itself: it is never taller than the
    // screen (style.css). Before, it ran off the bottom (24 October 2026).
    var top = below + height <= window.innerHeight - 8 ? below : above >= 8 ? above :
      Math.max(8, window.innerHeight - height - 8);
    tip.style.left = Math.round(left) + "px";
    tip.style.top = Math.round(top) + "px";
  }
  function showTip(button) {
    var tip = $(button.getAttribute("data-tip"));
    if (!tip || !tip.showPopover) return;
    home = home || document.querySelector(".tips");
    var host = button.closest("dialog[open]") || home;
    if (tip.parentElement !== host) {
      if (tip.matches(":popover-open")) tip.hidePopover();
      host.appendChild(tip);
    }
    current = { tip: tip, button: button };
    if (!tip.matches(":popover-open")) tip.showPopover();
    place(tip, button);
  }
  function hideTip() {
    if (current && current.tip.matches(":popover-open")) current.tip.hidePopover();
    current = null;
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".info");
    if (!button) return;
    event.preventDefault();
    window.clearTimeout(openTimer);
    if (current && current.button === button && current.tip.matches(":popover-open")) hideTip();
    else showTip(button);
  });
  document.addEventListener("pointerover", function (event) {
    if (!HOVER.matches) return;
    var button = event.target.closest(".info");
    if (button) {
      window.clearTimeout(closeTimer);
      window.clearTimeout(openTimer);
      openTimer = window.setTimeout(function () { showTip(button); }, 160);
    } else if (event.target.closest(".tip")) {
      window.clearTimeout(closeTimer);
    }
  });
  document.addEventListener("pointerout", function (event) {
    if (!HOVER.matches) return;
    var from = event.target.closest(".info, .tip");
    if (!from) return;
    var to = event.relatedTarget && event.relatedTarget.closest
      ? event.relatedTarget.closest(".info, .tip") : null;
    if (to) return; // from the (i) to its text, or back: it stays, so it can be read (WCAG 1.4.13)
    window.clearTimeout(openTimer);
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(hideTip, 260);
  });
  window.addEventListener("resize", hideTip);

  // ---------------------------------------------------------------- where the page says a word
  // A word of the page in the ledger story is a button (design 7.5): it marks each place where the
  // page's texts on the card say it, and brings the next one into view at each press, as a search
  // of the page would.
  // ------------------------------------------------------------- the days of the ledger
  // A square of the strip of days (design 7.5) names its day and its number in the line under
  // the strip, when the pointer rests on it or when it has the focus of the keyboard.
  function stripNote(event) {
    var square = event.target.closest && event.target.closest("[data-strip] a[data-note]");
    if (!square) return;
    var note = square.closest("[data-strip]").querySelector(".hm-strip-note");
    if (note) note.textContent = square.getAttribute("data-note");
  }
  document.addEventListener("mouseover", stripNote);
  document.addEventListener("focusin", stripNote);

  // The days widen (design 12.1, S2, 28 October 2026): Ctrl and the mouse wheel over the strip
  // (a pinch of a touchpad comes as the same) widen or narrow them around the pointer, and the
  // buttons + and - around the middle of what is in view. Only the places and the widths of the
  // shapes stretch, with the width of the drawing, so its words keep their size; the days scroll
  // sideways. Wide enough, a short date stands under every few days.
  var WHEEL_NOTCH = 50; // a step of the wheel this big or more is a notch of a mouse wheel
  var NOTCH_STEP = 1.5; // how much one notch widens the days
  var TICK_ROOM = 56; // pixels between two dates under the days
  var TICK_HALF = 22; // pixels from the middle of a date to its end
  var TICK_STEPS = [1, 2, 7, 14, 28]; // every day, every second day, every week...

  // The dates under the days, for what is in view: none at the first width, else every few days,
  // whole, and clear of "the event". A time cut out of the strip has no date (28 October 2026).
  function stripTicks(scroller) {
    var svg = scroller.querySelector(".hm-strip-svg");
    var group = svg && svg.querySelector(".hm-strip-ticks");
    if (!group) return;
    var zoom = Number(svg.getAttribute("data-zoom") || 1);
    var width = Number(svg.getAttribute("data-width"));
    var unit = scroller.clientWidth / width; // pixels of one unit of the drawing
    var day = Number(svg.getAttribute("data-step")) * zoom * unit; // pixels of one day
    var every = TICK_STEPS[TICK_STEPS.length - 1];
    for (var n = 0; n < TICK_STEPS.length; n++) {
      if (TICK_STEPS[n] * day >= TICK_ROOM) { every = TICK_STEPS[n]; break; }
    }
    var wide = zoom > 1;
    group.setAttribute("display", wide ? "inline" : "none");
    svg.querySelectorAll(".hm-strip-end").forEach(function (end) {
      end.setAttribute("display", wide ? "none" : "inline");
    });
    if (!wide) return;
    var label = svg.querySelector(".hm-strip-event-mark");
    var box = label ? label.getBBox() : null;
    var half = TICK_HALF / unit; // drawing units
    var from = scroller.scrollLeft / unit + half;
    var to = (scroller.scrollLeft + scroller.clientWidth) / unit - half;
    group.querySelectorAll("text").forEach(function (tick, number) {
      var x = Number(tick.getAttribute("data-x")) * zoom;
      var clear = !box || Math.abs(x - (box.x + box.width / 2)) > box.width / 2 + 2 * half;
      var whole = x >= from && x <= to;
      tick.setAttribute("display", number % every === 0 && clear && whole ? "inline" : "none");
    });
  }

  var ticking = null;
  document.addEventListener("scroll", function (event) { // scroll does not bubble: caught early
    var scroller = event.target;
    if (!scroller.classList || !scroller.classList.contains("hm-strip-scroll") || ticking) return;
    ticking = window.requestAnimationFrame(function () { ticking = null; stripTicks(scroller); });
  }, true);

  function widenStrip(figure, factor, at) {
    var scroller = figure && figure.querySelector(".hm-strip-scroll");
    var svg = scroller && scroller.querySelector(".hm-strip-svg");
    if (!svg) return false;
    var before = Number(svg.getAttribute("data-zoom") || 1);
    var most = Number(svg.getAttribute("data-most")) || 1;
    var zoom = Math.min(most, Math.max(1, before * factor));
    if (Math.abs(zoom - before) < 0.001) return false;
    if (at === undefined) at = scroller.clientWidth / 2;
    var share = (scroller.scrollLeft + at) / scroller.scrollWidth; // the place under `at` stays
    var width = Number(svg.getAttribute("data-width"));
    svg.setAttribute("data-zoom", String(zoom));
    svg.setAttribute("viewBox", "0 0 " + width * zoom + " " + svg.getAttribute("data-height"));
    svg.style.width = zoom * 100 + "%";
    svg.querySelectorAll("[data-x]").forEach(function (shape) {
      shape.setAttribute("x", Number(shape.getAttribute("data-x")) * zoom);
      var wide = shape.getAttribute("data-w");
      if (wide === null) return;
      var day = shape.classList.contains("hm-strip-day"); // a day keeps its gap of one unit
      shape.setAttribute("width", day ? Math.max((Number(wide) + 1) * zoom - 1, 1.5)
        : Number(wide) * zoom);
    });
    svg.querySelectorAll(".hm-strip-base").forEach(function (line) {
      line.setAttribute("x2", width * zoom);
    });
    scroller.scrollLeft = share * scroller.scrollWidth - at;
    stripTicks(scroller);
    figure.querySelector('[data-zoom="out"]').disabled = zoom <= 1;
    figure.querySelector('[data-zoom="in"]').disabled = zoom >= most;
    return true;
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-strip] .hm-strip-zoom");
    if (button) widenStrip(button.closest("[data-strip]"),
                           button.getAttribute("data-zoom") === "in" ? 2 : 0.5);
  });
  document.addEventListener("wheel", function (event) {
    if (!event.ctrlKey) return;
    var frame = event.target.closest && event.target.closest("[data-strip] .hm-strip-frame");
    if (!frame) return;
    event.preventDefault(); // over the strip, the wheel with Ctrl widens its days, not the page
    var scroller = frame.querySelector(".hm-strip-scroll");
    var delta = event.deltaY * (event.deltaMode === 1 ? 33 : (event.deltaMode === 2 ? 400 : 1));
    // A notch of a mouse wheel moves by about 100; a pinch of a touchpad sends many small steps,
    // and the days follow the fingers: Chrome sends a pinch of a scale s as -100 ln(s) in all.
    var factor = Math.abs(delta) >= WHEEL_NOTCH ? (delta < 0 ? NOTCH_STEP : 1 / NOTCH_STEP)
      : Math.exp(-delta / 100);
    var box = scroller.getBoundingClientRect();
    var at = Math.min(Math.max(event.clientX - box.left, 0), scroller.clientWidth);
    widenStrip(frame.closest("[data-strip]"), factor, at);
  }, { passive: false });

  var LESS_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-said-word]");
    var shown = button ? null : event.target.closest("mark.hm-said.is-shown");
    if (shown) { // a marked place in the text: the word that marked it goes on to the next place
      var home = shown.closest(".project");
      button = home ? home.querySelector("[data-said-word][data-at]") : null;
    }
    var card = button ? button.closest(".project") : null;
    if (!card) return;
    var word = button.getAttribute("data-said-word");
    var marks = Array.prototype.filter.call(card.querySelectorAll("mark.hm-said"), function (mark) {
      return mark.getAttribute("data-word") === word;
    });
    card.querySelectorAll("mark.hm-said.is-shown").forEach(function (mark) {
      mark.classList.remove("is-shown", "is-current");
      mark.removeAttribute("title");
    });
    card.querySelectorAll("[data-said-word][data-at]").forEach(function (other) {
      if (other !== button) other.removeAttribute("data-at");
    });
    if (!marks.length) return;
    var at = button.getAttribute("data-at");
    var next = at === null ? 0 : (Number(at) + 1) % marks.length;
    button.setAttribute("data-at", String(next));
    marks.forEach(function (mark) {
      mark.classList.add("is-shown");
      if (marks.length > 1) mark.title = "Next place";
    });
    marks[next].classList.add("is-current");
    var box = marks[next].closest("details"); // the lines of a README, shown when asked for
    if (box) box.open = true;
    marks[next].scrollIntoView({ block: "center", behavior: LESS_MOTION.matches ? "auto" : "smooth" });
    var status = card.querySelector(".hm-said-status");
    var story = button.closest("[data-said-in]");
    var where = story ? story.getAttribute("data-said-in") : "on the page";
    if (status) {
      status.textContent = "“" + marks[next].textContent + "” " + where + ": place " +
        (next + 1) + " of " + marks.length + "." +
        (marks.length > 1 ? " Press the word again, or a marked place, for the next one." : "");
    }
  });

  // ---------------------------------------------------------------- the graph of a list
  // A dot of the graph (design 8.6, S7) shows its project while the pointer rests on it, with the
  // line to its closest project, and opens its card on a click, through the link of the same
  // project in the lists under the graph. The click keeps the line and both dots lit after the card
  // is closed, until a click on an empty place. The name of a group opens the card of the project
  // it is named after. The words of a project are put in as text only.
  function graphDot(node) { return node && node.closest ? node.closest(".hm-dot") : null; }
  function graphName(node) { return node && node.closest ? node.closest("[data-graph-centre]") : null; }
  function graphOf(node) { return node.closest("[data-graph]"); }
  function dotOf(graph, id) { return graph.querySelector('.hm-dot[data-graph-id="' + id + '"]'); }
  function listLink(id) { return document.querySelector('[data-graph-link="' + id + '"]'); }
  function darkGraph(graph) { // what the pointer showed goes; the kept dot stays (keepDot)
    graph.querySelectorAll(".is-lit").forEach(function (one) { one.classList.remove("is-lit"); });
    var hover = graph.querySelector(".hm-graph-hover");
    if (hover) hover.setAttribute("visibility", "hidden");
    var tip = graph.querySelector(".hm-graph-tip");
    if (tip) tip.hidden = true;
  }
  function strongLines(graph, dot) {
    return graph.querySelectorAll('.hm-graph-lines line[data-ends~="' + dot.getAttribute("data-graph-id") + '"]');
  }
  // `line` joins the dot to its closest project; returns that project's dot, or null.
  function joinNearest(graph, dot, line) {
    var near = dot.getAttribute("data-near"), other = near ? dotOf(graph, near) : null;
    if (!other || !line) return null;
    var from = dot.querySelector(".hm-mark"), to = other.querySelector(".hm-mark");
    line.setAttribute("x1", from.getAttribute("cx"));
    line.setAttribute("y1", from.getAttribute("cy"));
    line.setAttribute("x2", to.getAttribute("cx"));
    line.setAttribute("y2", to.getAttribute("cy"));
    line.setAttribute("visibility", "visible");
    return other;
  }
  function lightGraph(graph, dot) {
    dot.classList.add("is-lit");
    strongLines(graph, dot).forEach(function (line) { line.classList.add("is-lit"); });
    var other = joinNearest(graph, dot, graph.querySelector(".hm-graph-hover"));
    if (other) other.classList.add("is-lit");
  }
  // The dot that a click kept has a line of its own: it stays lit, with its closest project,
  // while the pointer shows other dots, until a click on an empty place (24 October 2026: the
  // pointer took it away, and the dot had to be found again).
  function keepDot(graph, dot) {
    graph.querySelectorAll(".is-kept, .is-kept-near").forEach(function (one) {
      one.classList.remove("is-kept", "is-kept-near");
    });
    var kept = graph.querySelector(".hm-graph-kept");
    if (kept) kept.setAttribute("visibility", "hidden");
    if (!dot) { graph.removeAttribute("data-kept"); return; }
    graph.setAttribute("data-kept", dot.getAttribute("data-graph-id"));
    graph.hmKeptAt = clickOrder(graph);
    dot.classList.add("is-kept");
    strongLines(graph, dot).forEach(function (line) { line.classList.add("is-kept"); });
    var other = joinNearest(graph, dot, kept);
    if (other) other.classList.add("is-kept-near");
  }
  // A right click keeps a dot lit with its closest project and their line, for as many dots as
  // one likes, kept in the order of the clicks; a right click on it again lets it go (30 October
  // 2026). Each click on an empty place lets go of the latest pair, kept by a click or by a right
  // click, one at each click (30 October 2026, evening: it let them all go at once).
  function clickOrder(graph) {
    graph.hmClicks = (graph.hmClicks || 0) + 1;
    return graph.hmClicks;
  }
  function pinnedOf(graph) {
    return (graph.getAttribute("data-pinned") || "").split(" ").filter(Boolean);
  }
  function drawPins(graph) {
    graph.querySelectorAll(".is-pinned, .is-pinned-near").forEach(function (one) {
      one.classList.remove("is-pinned", "is-pinned-near");
    });
    var lines = graph.querySelector(".hm-graph-pins");
    if (lines) lines.replaceChildren();
    pinnedOf(graph).forEach(function (id) {
      var dot = dotOf(graph, id);
      if (!dot) return;
      dot.classList.add("is-pinned");
      strongLines(graph, dot).forEach(function (line) { line.classList.add("is-pinned"); });
      var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      if (lines) lines.appendChild(line);
      var other = joinNearest(graph, dot, line);
      if (other) other.classList.add("is-pinned-near");
    });
  }
  function pin(graph, ids) {
    if (ids.length) graph.setAttribute("data-pinned", ids.join(" "));
    else graph.removeAttribute("data-pinned");
    drawPins(graph);
  }
  document.addEventListener("contextmenu", function (event) {
    var dot = graphDot(event.target);
    if (!dot) return;
    event.preventDefault(); // the menu of the browser has nothing to do on a dot
    var graph = graphOf(dot), id = dot.getAttribute("data-graph-id"), ids = pinnedOf(graph);
    if (ids.indexOf(id) >= 0) {
      pin(graph, ids.filter(function (one) { return one !== id; }));
      return;
    }
    graph.hmPinnedAt = graph.hmPinnedAt || {};
    graph.hmPinnedAt[id] = clickOrder(graph);
    pin(graph, ids.concat([id]));
  });
  function letGoOfTheLatest(graph) {
    var ids = pinnedOf(graph), last = ids[ids.length - 1];
    var pinnedAt = last ? (graph.hmPinnedAt || {})[last] || 0 : -1;
    var keptAt = graph.getAttribute("data-kept") ? graph.hmKeptAt || 0 : -1;
    if (keptAt < 0 && pinnedAt < 0) return;
    if (keptAt >= pinnedAt) keepDot(graph, null);
    else pin(graph, ids.slice(0, -1));
  }
  function showGraphTip(graph, dot) {
    var tip = graph.querySelector(".hm-graph-tip");
    if (!tip) return;
    tip.textContent = "";
    function line(text, kind, label) { // a label stands out from its value
      if (!text) return;
      var one = document.createElement("p");
      if (kind) one.className = kind;
      if (label) {
        var title = document.createElement("span");
        title.className = "hm-tip-label";
        title.textContent = label + " ";
        one.appendChild(title);
      }
      one.appendChild(document.createTextNode(text));
      tip.appendChild(one);
    }
    var rank = dot.getAttribute("data-rank"), near = dot.getAttribute("data-near");
    var other = near ? dotOf(graph, near) : null;
    line(dot.getAttribute("data-name"), "hm-tip-name");
    line((rank ? "Number " + rank + " in the list · " : "") + dot.getAttribute("data-event"), "hm-tip-small");
    line(dot.getAttribute("data-line"));
    line(dot.getAttribute("data-proof"), "hm-tip-small", "Proof:");
    line(dot.getAttribute("data-prize"), "hm-tip-small", "Won:");
    line(dot.getAttribute("data-group"), "hm-tip-small", "Group:");
    if (other) { // a project at the edge of its group can be closest to one of another group
      var apart = other.getAttribute("data-group") !== dot.getAttribute("data-group");
      line(other.getAttribute("data-name") + (apart ? ", in the group " + other.getAttribute("data-group") : ""),
        "hm-tip-small", "Closest in meaning:");
    }
    tip.hidden = false;
    var box = graph.getBoundingClientRect(), mark = dot.querySelector(".hm-mark").getBoundingClientRect();
    var x = mark.left + mark.width / 2 - box.left, y = mark.top + mark.height / 2 - box.top;
    var width = tip.offsetWidth, height = tip.offsetHeight;
    var left = x + width + 16 < box.width ? x + 14 : x - width - 14;
    var top = y + height + 16 < box.height ? y + 14 : y - height - 14;
    tip.style.left = Math.round(Math.max(4, left)) + "px";
    tip.style.top = Math.round(Math.max(4, top)) + "px";
  }
  document.addEventListener("pointerover", function (event) {
    if (dragging && dragging.moved) return;
    var dot = graphDot(event.target);
    var link = dot ? null : event.target.closest && event.target.closest("[data-graph-link]");
    if (link) dot = document.querySelector('.hm-dot[data-graph-id="' + link.getAttribute("data-graph-link") + '"]');
    if (!dot) return;
    var graph = graphOf(dot);
    darkGraph(graph);
    lightGraph(graph, dot);
    if (!link && HOVER.matches) showGraphTip(graph, dot);
  });
  document.addEventListener("pointerout", function (event) {
    var from = graphDot(event.target) || (event.target.closest && event.target.closest("[data-graph-link]"));
    if (!from || (event.relatedTarget && from.contains(event.relatedTarget))) return;
    document.querySelectorAll("[data-graph]").forEach(darkGraph);
  });
  document.addEventListener("focusin", function (event) { // a project of the lists, by keyboard
    var link = event.target.closest && event.target.closest("[data-graph-link]");
    var dot = link && document.querySelector('.hm-dot[data-graph-id="' + link.getAttribute("data-graph-link") + '"]');
    if (!dot) return;
    darkGraph(graphOf(dot));
    lightGraph(graphOf(dot), dot);
  });
  document.addEventListener("focusout", function (event) {
    if (event.target.closest && event.target.closest("[data-graph-link]")) {
      document.querySelectorAll("[data-graph]").forEach(darkGraph);
    }
  });
  document.addEventListener("click", function (event) {
    var dot = graphDot(event.target), name = dot ? null : graphName(event.target);
    var id = dot ? dot.getAttribute("data-graph-id") : name ? name.getAttribute("data-graph-centre") : null;
    if (!id || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    var link = listLink(id);
    if (!link || !window.htmx) return; // the address of the dot then loads the whole page
    event.preventDefault();
    var graph = graphOf(dot || name);
    keepDot(graph, dot || dotOf(graph, id));
    // The picture is hidden from screen readers: the focus does not stay in it, so the window of
    // the card gives it back to the page, not to the dot.
    if (document.activeElement && graph.contains(document.activeElement)) document.activeElement.blur();
    window.htmx.trigger(link, "click");
  });
  document.addEventListener("click", function (event) { // a project of the lists keeps its dot too
    var link = event.target.closest && event.target.closest("[data-graph-link]");
    var dot = link && document.querySelector('.hm-dot[data-graph-id="' + link.getAttribute("data-graph-link") + '"]');
    if (dot && event.isTrusted) keepDot(graphOf(dot), dot);
  });
  document.addEventListener("click", function (event) { // an empty place lets go of the latest
    var svg = event.target.closest && event.target.closest(".hm-graph-svg");
    if (!svg) return;
    if (svg.hmDragged) { svg.hmDragged = false; return; } // the click that ends a drag
    if (!graphDot(event.target) && !graphName(event.target)) letGoOfTheLatest(graphOf(svg));
  });

  // Ctrl and the wheel, or the pinch of a touchpad, which the browser sends the same way, zoom the
  // graph around the pointer, up to 8 times; a drag, or two fingers on a touchpad, move the zoomed
  // graph, and three buttons zoom in, out and back. The dots, the lines and the names keep their
  // size on the screen (style.css divides them by --hm-zoom), so dots that touch come apart
  // (design 8.6).
  var ZOOM_MOST = 8, dragging = null;
  function zoomOf(svg) {
    if (!svg.hmZoom) {
      var box = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
      svg.hmZoom = { base: box, x: box[0], y: box[1], k: 1 };
    }
    return svg.hmZoom;
  }
  function drawZoom(svg) {
    var zoom = zoomOf(svg), base = zoom.base;
    var width = base[2] / zoom.k, height = base[3] / zoom.k;
    zoom.x = Math.min(Math.max(zoom.x, base[0]), base[0] + base[2] - width);
    zoom.y = Math.min(Math.max(zoom.y, base[1]), base[1] + base[3] - height);
    svg.setAttribute("viewBox", [zoom.x, zoom.y, width, height].join(" "));
    svg.style.setProperty("--hm-zoom", String(zoom.k));
    svg.classList.toggle("is-zoomed", zoom.k > 1);
    svg.querySelectorAll("circle[data-r]").forEach(function (circle) {
      circle.setAttribute("r", String(Number(circle.getAttribute("data-r")) / zoom.k));
    });
    // A crown keeps its size, and its place just above its dot (31 October 2026).
    svg.querySelectorAll("[data-crown]").forEach(function (crown) {
      var x = Number(crown.getAttribute("data-cx")), y = Number(crown.getAttribute("data-cy"));
      var r = Number(crown.getAttribute("data-cr"));
      crown.setAttribute("transform", "translate(" + x + " " + (y - (r + 4) / zoom.k) +
        ") scale(" + (1 / zoom.k) + ")");
    });
    var graph = graphOf(svg), tip = graph.querySelector(".hm-graph-tip");
    if (tip) tip.hidden = true;
    graph.querySelectorAll("[data-zoom]").forEach(function (button) {
      var way = button.getAttribute("data-zoom");
      button.disabled = way === "in" ? zoom.k >= ZOOM_MOST : zoom.k <= 1;
    });
  }
  function zoomAt(svg, clientX, clientY, factor) {
    var zoom = zoomOf(svg), base = zoom.base;
    var k = Math.min(ZOOM_MOST, Math.max(1, zoom.k * factor));
    var matrix = svg.getScreenCTM();
    if (k === zoom.k || !matrix) return;
    // The point under the pointer stays under it.
    var point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    var fx = (point.x - zoom.x) / (base[2] / zoom.k), fy = (point.y - zoom.y) / (base[3] / zoom.k);
    zoom.k = k;
    zoom.x = point.x - fx * base[2] / k;
    zoom.y = point.y - fy * base[3] / k;
    drawZoom(svg);
  }
  document.addEventListener("wheel", function (event) {
    var svg = event.target.closest && event.target.closest(".hm-graph-svg");
    if (!svg) return;
    var unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1;
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault(); // the graph zooms, not the page
      zoomAt(svg, event.clientX, event.clientY, Math.exp(-event.deltaY * unit * 0.0025));
      return;
    }
    // Two fingers on a touchpad send the wheel: they move a zoomed graph (24 October 2026: they
    // scrolled the page). At the edge of the graph nothing moves, and the page scrolls again.
    var zoom = zoomOf(svg), matrix = svg.getScreenCTM();
    if (zoom.k <= 1 || !matrix) return;
    var before = [zoom.x, zoom.y];
    zoom.x += event.deltaX * unit / matrix.a;
    zoom.y += event.deltaY * unit / matrix.d;
    drawZoom(svg); // keeps the view inside the graph
    if (zoom.x !== before[0] || zoom.y !== before[1]) event.preventDefault();
  }, { passive: false });
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-zoom]");
    var graph = button && graphOf(button), svg = graph && graph.querySelector(".hm-graph-svg");
    if (!svg) return;
    var way = button.getAttribute("data-zoom");
    if (way === "reset") { zoomOf(svg).k = 1; drawZoom(svg); return; }
    var rect = svg.getBoundingClientRect();
    zoomAt(svg, rect.left + rect.width / 2, rect.top + rect.height / 2, way === "in" ? 1.6 : 1 / 1.6);
  });
  document.addEventListener("pointerdown", function (event) {
    var svg = event.target.closest && event.target.closest(".hm-graph-svg");
    if (!svg || event.button !== 0 || graphDot(event.target) || graphName(event.target)) return;
    var zoom = zoomOf(svg);
    dragging = { svg: svg, id: event.pointerId, x: event.clientX, y: event.clientY,
      from: [zoom.x, zoom.y], moved: false };
  });
  document.addEventListener("pointermove", function (event) {
    if (!dragging || event.pointerId !== dragging.id) return;
    var svg = dragging.svg, zoom = zoomOf(svg), matrix = svg.getScreenCTM();
    var dx = event.clientX - dragging.x, dy = event.clientY - dragging.y;
    if (zoom.k <= 1 || !matrix || (!dragging.moved && Math.abs(dx) + Math.abs(dy) < 4)) return;
    if (!dragging.moved) {
      dragging.moved = true;
      svg.setPointerCapture(event.pointerId);
      svg.classList.add("is-dragged");
      darkGraph(graphOf(svg));
    }
    zoom.x = dragging.from[0] - dx / matrix.a; // from the pixels of the screen to the graph's units
    zoom.y = dragging.from[1] - dy / matrix.d;
    drawZoom(svg);
  });
  function endDrag(event) {
    if (!dragging || event.pointerId !== dragging.id) return;
    var ended = dragging;
    dragging = null;
    ended.svg.classList.remove("is-dragged");
    if (ended.moved) ended.svg.hmDragged = true;
  }
  document.addEventListener("pointerup", endDrag);
  document.addEventListener("pointercancel", endDrag);
  function setUpGraphs(root) { // the buttons need this script, so they are hidden without it
    (root || document).querySelectorAll(".hm-graph-tools[hidden]").forEach(function (tools) {
      tools.hidden = false;
    });
  }

  // ---------------------------------------------------------------- long lists
  // A long list shows its first 10 lines, with "Show 10 more" and "Show all" under it, and "Show
  // fewer" once it is whole (design 12.1, S5 and S7). Without this file every line shows.
  var STEP = 10;
  function setUpMore(root) {
    (root || document).querySelectorAll("[data-more-for]").forEach(function (place) {
      var list = $(place.getAttribute("data-more-for"));
      if (place.dataset.ready || !list || list.children.length <= STEP) return;
      place.dataset.ready = "1";
      var lines = Array.prototype.slice.call(list.children);
      var said = document.createElement("span");
      said.className = "visually-hidden";
      said.setAttribute("aria-live", "polite");
      function button(then) {
        var one = document.createElement("button");
        one.type = "button";
        one.className = "btn btn-sm";
        one.addEventListener("click", then);
        place.appendChild(one);
        return one;
      }
      var shown = STEP;
      var more = button(function () { show(shown + STEP, true); });
      var all = button(function () { show(lines.length, true); });
      var fewer = button(function () {
        show(STEP, true);
        list.scrollIntoView({ block: "nearest" });
        more.focus({ preventScroll: true });
      });
      place.appendChild(said);
      function show(count, announce) {
        var first = shown;
        shown = Math.min(count, lines.length);
        lines.forEach(function (line, at) { line.hidden = at >= shown; });
        var left = lines.length - shown;
        more.hidden = left <= 0;
        all.hidden = left <= STEP;
        fewer.hidden = left > 0;
        more.textContent = left > STEP ? "Show " + STEP + " more" : "Show the last " + left;
        all.textContent = "Show all " + lines.length;
        fewer.textContent = "Show fewer";
        if (announce) said.textContent = shown + " of " + lines.length + " shown.";
        if (announce && left <= 0 && shown > first) fewer.focus({ preventScroll: true });
      }
      show(STEP, false);
      place.hidden = false;
    });
  }

  // ---------------------------------------------------------------- how a mark was judged
  // A mark of the proof or the activity leads to how it was judged (design 12.1, S1 to S3): inside
  // a card or a check it brings that part into view; on a card of the list it opens the project's
  // card first, and brings the part into view once the card is there. The window moves as little
  // as it can: a part that fits is shown whole, a taller one from its top (24 October 2026: it
  // went to the top every time, far down the check).
  var pointedAt = null; // the part to bring into view when the window of a project opens
  function bringIntoView(id) {
    var part = $(id);
    if (!part) return false;
    part.scrollIntoView({ block: "nearest", behavior: LESS_MOTION.matches ? "auto" : "smooth" });
    if (part.hasAttribute("tabindex")) part.focus({ preventScroll: true });
    part.classList.remove("is-pointed");
    void part.offsetWidth; // start the moment of light again
    part.classList.add("is-pointed");
    window.setTimeout(function () { part.classList.remove("is-pointed"); }, 2000); // style.css
    return true;
  }
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-scroll-to]");
    if (!link || link.hasAttribute("hx-get")) return; // a card of the list opens first, below
    if (bringIntoView(link.getAttribute("data-scroll-to"))) event.preventDefault();
  });
  document.addEventListener("htmx:beforeRequest", function (event) {
    var target = event.detail.target;
    if (!target || target.id !== "viewer-body") return;
    var link = event.detail.elt && event.detail.elt.closest && event.detail.elt.closest("[data-scroll-to]");
    pointedAt = link ? link.getAttribute("data-scroll-to") : null;
  });
  document.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail.target;
    if (!target || target.id !== "viewer-body" || !pointedAt) return;
    var id = pointedAt;
    pointedAt = null;
    bringIntoView(id);
  });

  // ---------------------------------------------------------------- the window of a project
  var viewer = function () { return $("viewer"); };
  var pushed = false; // the window added an entry to the history, so "back" closes it
  var checkSaved = null; // the result of a check, while one of its projects is open over it
  function openParam(id) {
    var url = new URL(window.location.href);
    if (id) url.searchParams.set("open", id); else url.searchParams.delete("open");
    return url.toString();
  }
  function skeleton() {
    return '<div class="project" aria-hidden="true"><span class="bone short"></span>' +
      '<span class="bone title"></span><span class="bone"></span><span class="bone"></span>' +
      '<span class="bone short"></span></div>';
  }
  // While a submission is checked: the moment before the server shows its steps (design 12.1,
  // S3, and the steps in _check_steps.html).
  function checking() {
    return '<div class="project check-progress" role="status"><h2 class="project-title">Checking the submission</h2>' +
      '<p class="hm-small">Starting the check.</p></div>';
  }
  function showViewer() {
    var dialog = viewer();
    if (!dialog) return;
    if (dialog.open && !dialog.matches(":modal")) dialog.close();
    if (!dialog.open) dialog.showModal();
  }
  function steps() {
    var article = document.querySelector("#viewer-body .project[data-project]");
    var id = article ? article.getAttribute("data-project") : null;
    var row = id ? $("result-" + id) : null;
    document.querySelectorAll(".result[aria-current]").forEach(function (one) { one.removeAttribute("aria-current"); });
    if (row) row.setAttribute("aria-current", "true");
    var before = row && row.previousElementSibling, after = row && row.nextElementSibling;
    document.querySelectorAll("[data-viewer-step]").forEach(function (button) {
      var forward = button.getAttribute("data-viewer-step") === "1";
      button.disabled = !(forward ? after : before);
      button.hidden = !article; // a check of a submission has no list to step through
    });
  }
  function closeViewer() {
    var dialog = viewer();
    if (!dialog || !dialog.open) return;
    if (pushed) { history.back(); return; } // the history's own "back" closes it, below
    dialog.close();
  }
  // "Back to the check": the result of the check comes back as it was, with no new request.
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-back-to-check]") || checkSaved === null) return;
    var body = $("viewer-body");
    body.innerHTML = checkSaved;
    checkSaved = null;
    if (window.htmx) window.htmx.process(body);
    steps();
    var title = $("viewer-title");
    if (title) title.focus({ preventScroll: true });
  });
  function closed() {
    checkSaved = null;
    var row = document.querySelector(".result[aria-current] .result-link");
    if (!pushed && new URL(window.location.href).searchParams.has("open")) {
      history.replaceState(history.state, "", openParam(null));
    }
    pushed = false;
    if (row) row.focus({ preventScroll: true });
  }
  document.addEventListener("htmx:beforeRequest", function (event) {
    var target = event.detail.target;
    if (target && target.id === "viewer-body") {
      var link = event.detail.elt.closest("[data-open-viewer]");
      var fromCheck = !!(link && link.hasAttribute("data-from-check"));
      checkSaved = fromCheck ? target.innerHTML : null; // a project of a check keeps the check
      var asking = event.detail.elt;
      var aCheck = asking.id === "check" || asking.hasAttribute("data-check-again");
      target.innerHTML = aCheck ? checking() : skeleton();
      showViewer();
      if (link && !fromCheck) {
        var id = link.getAttribute("data-open-viewer");
        if (!pushed) { history.pushState({ hmViewer: id }, "", openParam(id)); pushed = true; }
        else history.replaceState({ hmViewer: id }, "", openParam(id));
      }
    }
    var elt = event.detail.elt;
    if (elt && (elt.id === "ai-button" || elt.hasAttribute("data-asks-gemini"))) {
      var space = $("workspace");
      if (space) space.classList.add("asking-ai");
    }
    if (elt && elt.hasAttribute("data-check-compare")) {
      document.querySelectorAll("[id^='check-compare-'].compare").forEach(function (place) {
        place.classList.add("waiting");
        place.setAttribute("aria-busy", "true");
        place.textContent = "Gemini is comparing this project with the README.";
      });
    }
    if (elt && elt.id === "compare-loader") {
      window.setTimeout(function () {
        document.querySelectorAll(".compare.waiting").forEach(function (place) {
          place.textContent = "Still writing: Gemini is slower than usual just now. It stops " +
            "after 30 seconds, and the rest of the page is complete.";
        });
      }, 12000);
    }
  });
  // A comparison asked in a project's window shows on the project's card in the list too, at
  // once (30 October 2026: the card kept no trace of it until the list was asked again).
  function comparedOnCards() {
    document.querySelectorAll(".compare-place[id^='one-compare-']").forEach(function (place) {
      var text = place.querySelector(".hm-compare-text");
      var pid = place.id.slice("one-compare-".length);
      var card = document.querySelector("#result-" + pid + " .hm-card");
      if (!text || !card) return;
      var slot = $("compare-" + pid);
      if (!slot) {
        slot = document.createElement("div");
        slot.id = "compare-" + pid;
        slot.className = "hm-compare compare";
        card.appendChild(slot);
      }
      slot.classList.remove("waiting");
      slot.removeAttribute("aria-busy");
      slot.innerHTML = text.outerHTML;
    });
  }
  // After the settle, not the swap: htmx keeps the old attributes of an element with the same id
  // until it settles, so at the swap the place still has the class of the button's box.
  document.addEventListener("htmx:afterSettle", comparedOnCards);
  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    if (target && target.id === "viewer-body") {
      var title = $("viewer-title");
      if (title) title.focus({ preventScroll: true });
      target.scrollTop = 0;
      steps();
      if (checkSaved !== null && target.querySelector(".project[data-project]")) {
        var back = document.createElement("p");
        back.className = "viewer-back";
        back.innerHTML = '<button type="button" class="btn btn-sm hm-back" data-back-to-check>&lsaquo; Back to the check</button>';
        target.insertBefore(back, target.firstChild);
        document.querySelectorAll("[data-viewer-step]").forEach(function (button) { button.hidden = true; });
      }
    }
    if (target && target.id === "register-box") {
      var heading = $("register-title");
      if (heading) heading.focus({ preventScroll: false });
    }
    if (target && target.id === "sheet-body") {
      var heading = $("sheet-title");
      if (heading) heading.focus({ preventScroll: true });
    }
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-viewer]")) { event.preventDefault(); closeViewer(); return; }
    var step = event.target.closest("[data-viewer-step]");
    if (!step) return;
    var article = document.querySelector("#viewer-body .project[data-project]");
    var row = article ? $("result-" + article.getAttribute("data-project")) : null;
    var next = row && (step.getAttribute("data-viewer-step") === "1" ? row.nextElementSibling : row.previousElementSibling);
    var link = next && next.querySelector("[data-open-viewer]");
    if (link && window.htmx) window.htmx.trigger(link, "click");
  });
  document.addEventListener("cancel", function (event) {
    if (event.target === viewer()) { event.preventDefault(); closeViewer(); }
  }, true);
  document.addEventListener("close", function (event) {
    if (event.target === viewer()) closed();
  }, true);
  document.addEventListener("click", function (event) {
    var dialog = event.target;
    if (dialog === viewer()) closeViewer(); // a click on the dim page behind the window
    else if (dialog === $("sheet")) dialog.close();
  });
  // "Back" while a project is open closes its window, and asks the server nothing: the list
  // under it is still the page. This runs before htmx's own handler, which it then stops.
  window.addEventListener("popstate", function (event) {
    var dialog = viewer();
    var state = event.state || {};
    if (dialog && dialog.open && !state.hmViewer) {
      pushed = false;
      dialog.close();
      event.stopImmediatePropagation();
    }
  }, true);

  // ---------------------------------------------------------------- the windows of the footer
  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-sheet]");
    if (!link || !window.htmx) return;
    event.preventDefault();
    var sheet = $("sheet");
    if (!sheet) return;
    $("sheet-body").innerHTML = skeleton();
    if (!sheet.open) sheet.showModal();
    window.htmx.ajax("GET", "/about/" + link.getAttribute("data-sheet"), { target: "#sheet-body", swap: "innerHTML" });
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-sheet]")) { var sheet = $("sheet"); if (sheet) sheet.close(); }
  });

  // ---------------------------------------------------------------- the requests of the page
  // An empty filter means "all": it is left out of the address, which stays short to share.
  document.addEventListener("htmx:configRequest", function (event) {
    var values = event.detail.parameters;
    if (!values) return;
    var empty = [];
    if (typeof values.forEach === "function" && typeof values.delete === "function") {
      values.forEach(function (value, key) { if (value === "") empty.push(key); });
      empty.forEach(function (key) { values.delete(key); });
    } else {
      Object.keys(values).forEach(function (key) { if (values[key] === "") delete values[key]; });
    }
  });
  // An answer of 400, 404 or 503 says in plain words what happened, and so does an answer of 500
  // in the window of a project or a check: it takes the place of the waiting state. A 503 of the
  // comparison carries the words of the failure for each result. Answers of 429 and 403 come from
  // the public copy only, when a visitor's allowance is used, or before Cloudflare found them to
  // be a person, and say so wherever it was asked.
  // Vercel's firewall may answer a request of the page with its own check that the visitor uses a
  // browser: an answer of 429 with the header X-Vercel-Mitigated: challenge (seen on 30 October
  // 2026). That page cannot work inside a part of this one, so the whole page is asked again,
  // where the browser passes the check by itself; once a minute at most, so it never loops.
  function checkpoint() {
    var session = store("sessionStorage");
    try {
      var last = Number(session && session.getItem("hm-checkpoint")) || 0;
      if (Date.now() - last < 60000) return;
      if (session) session.setItem("hm-checkpoint", String(Date.now()));
    } catch (error) { /* nothing is kept: the page is asked again all the same */ }
    window.location.reload();
  }
  document.addEventListener("htmx:beforeSwap", function (event) {
    if (event.detail.xhr.getResponseHeader("x-vercel-mitigated") === "challenge") {
      event.detail.shouldSwap = false;
      checkpoint();
      return;
    }
    // htmx 2 names the target of the swap as `elt` here; the element that asked is in the
    // request's config (htmx 2.0.11, seen in the browser on 18 October 2026).
    var config = event.detail.requestConfig;
    var elt = (config && config.elt) || event.detail.elt;
    var target = event.detail.target;
    var status = event.detail.xhr.status;
    var shown = elt && (elt.id === "compare-loader" || elt.id === "check" || elt.id === "register-form" ||
      elt.hasAttribute("data-check-compare") || elt.hasAttribute("data-check-again") ||
      elt.closest(".compare-ask"));
    var inWindow = target && target.id === "viewer-body";
    var inPlace = inWindow || (target && target.id === "workspace");
    if ((shown && (status === 503 || status === 400)) ||
        (inPlace && (status === 400 || status === 404 || status === 503)) ||
        (inWindow && status === 500) || status === 429 || status === 403) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  // A request with no answer, or with an answer that cannot be shown, leaves no waiting state on
  // the screen: the place says what happened and what to do (design 12.3). In htmx 2.0.11 these
  // events come from the element that asked, with the target of the swap in the detail.
  var NO_ANSWER = "The server did not answer. Check that it is running and that you are " +
    "connected, then try again.";
  var WENT_WRONG = "Something went wrong on the server, so this cannot be shown. Try again in a minute.";
  // The longest wait of a request is about a minute (a check that reads the code of a repository
  // for the first time, at most 30 seconds of it for the code), so the page stops waiting after 90
  // seconds: "timeout" in the htmx-config of the page's head.
  var TOO_SLOW = "The server did not answer within 90 seconds, so the page stopped waiting. " +
    "Try again in a minute.";
  var CHECK_FAILED = "The comparison with the README could not be generated just now. " +
    "Everything else on this page is complete.";
  function requestFailed(event) {
    var elt = event.detail.elt, target = event.detail.target;
    var words = event.type === "htmx:responseError" ? WENT_WRONG :
      event.type === "htmx:timeout" ? TOO_SLOW : NO_ANSWER;
    if (!elt) return;
    if (elt.id === "compare-loader" || elt.hasAttribute("data-check-compare")) {
      var failed = elt.id === "compare-loader" ? FAILED : CHECK_FAILED;
      document.querySelectorAll(".compare.waiting").forEach(function (place) {
        place.classList.remove("waiting");
        place.removeAttribute("aria-busy");
        place.textContent = failed;
      });
      return;
    }
    if (target && target.id === "check-steps") target = $("viewer-body"); // a check that runs
    if (!target || !document.body.contains(target)) return;
    if (target.id === "viewer-body" || target.id === "sheet-body") {
      var name = target.id === "viewer-body" ? "viewer-title" : "sheet-title";
      target.innerHTML = '<div class="project"><h2 id="' + name + '" class="project-title" ' +
        'tabindex="-1">This cannot be shown</h2><div class="alert alert-danger" role="alert"></div></div>';
      target.querySelector(".alert").textContent = words;
      if (target.id === "viewer-body") {
        steps();
        if (checkSaved !== null) { // the check that was open stays one click away
          var back = document.createElement("p");
          back.className = "viewer-back";
          back.innerHTML = '<button type="button" class="btn btn-sm hm-back" data-back-to-check>&lsaquo; Back to the check</button>';
          target.insertBefore(back, target.firstChild);
        }
      }
      $(name).focus({ preventScroll: true });
      return;
    }
    var line = document.createElement("div"); // the list and the forms keep what they showed
    line.className = "alert alert-danger hm-failed";
    line.setAttribute("role", "alert");
    line.textContent = words + " What is shown below has not changed.";
    target.insertBefore(line, target.firstChild);
  }
  document.addEventListener("htmx:sendError", requestFailed);
  document.addEventListener("htmx:timeout", requestFailed);
  document.addEventListener("htmx:responseError", requestFailed);
  document.addEventListener("htmx:beforeRequest", function () {
    document.querySelectorAll(".hm-failed").forEach(function (line) { line.remove(); });
  });
  // A clicked link or button keeps the focus, and the browser's scroll anchoring follows the
  // focused element: while htmx put the new part above the old one, the page went down with the
  // old link, to the bottom ("Clear" and the examples, 23 October 2026). So the focus leaves a
  // link or a button of the part that is replaced; a box that is being typed in keeps it.
  document.addEventListener("htmx:beforeSwap", function (event) {
    var active = document.activeElement, target = event.detail.target;
    if (active && target && target.contains(active) && active.matches("a, button")) active.blur();
  });
  // On a phone, after the button or Enter, the results come into view (not while typing).
  var NARROW = window.matchMedia("(max-width: 760px)");
  var bringResults = false;
  document.addEventListener("htmx:beforeRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && (elt.id === "ai-button" || elt.id === "ask")) bringResults = true;
    else if (elt && elt.id === "idea") bringResults = false;
  });
  document.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail.target;
    if (!target) return;
    setUpTabs(document);
    setUpGraphs(document);
    setUpMore(document);
    drawCharts(document); // an outerHTML swap leaves the old element in the event
    if (target.id !== "workspace" && target.id !== "main") return;
    showCount();
    if (bringResults && NARROW.matches) {
      var results = $("results");
      if (results) { results.scrollIntoView({ block: "start" }); results.focus({ preventScroll: true }); }
    }
    bringResults = false;
  });
  document.addEventListener("htmx:historyRestore", function () {
    setUpTabs(document);
    setUpGraphs(document);
    setUpMore(document);
    drawCharts(document);
    showCount();
  });
  document.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && (elt.id === "ai-button" || elt.hasAttribute("data-asks-gemini")) && !event.detail.successful) {
      var space = $("workspace");
      if (space) space.classList.remove("asking-ai"); // nothing came back: the list stays
    }
  });

  // ------------------------------------------------- Cloudflare's Turnstile on the public copy
  // Before the public copy uses Gemini, GitHub or Hedera for a visitor, Cloudflare's Turnstile
  // says whether they are a person (web/turnstile.py). Its widget shows itself only when it needs
  // a click; its token goes to the server at once, which spends it and keeps the pass for a day.
  // A token is spent once: after a refusal the widget makes a new one, PERSON_TRIES in all.
  var PERSON_ASKS = "Before it uses Gemini, GitHub or Hedera for you, this public copy asks " +
    "Cloudflare whether you are a person. Tick the box below once.";
  var PERSON_FAILED = "Cloudflare could not confirm that you are a person, so this public copy " +
    "does not use Gemini, GitHub or Hedera for you. The search works without it. Reload the " +
    "page to try again.";
  var PERSON_BLOCKED = "Cloudflare's check could not load; an extension of the browser may " +
    "block it. Until it runs, this public copy does not use Gemini, GitHub or Hedera for you. " +
    "The search works without it.";
  var PERSON_UNSUPPORTED = "This browser cannot run Cloudflare's check, so this public copy " +
    "does not use Gemini, GitHub or Hedera for you. The search works without it.";
  var PERSON_TRIES = 3;
  var PERSON_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js" +
    "?render=explicit&onload=jevaduPerson";

  function checkPerson() {
    var box = $("person-check");
    if (!box) return;
    var widget = null;
    var tries = 0;
    function say(words, closable) {
      box.querySelector(".hm-person-words").textContent = words;
      box.querySelector(".hm-person-close").hidden = !closable;
      box.hidden = false;
      box.classList.add("shown");
    }
    function sent(token) {
      tries += 1;
      fetch("/person-check", { method: "POST", body: new URLSearchParams({ token: token }) })
        .then(function (answer) {
          if (answer.status !== 204) throw new Error("refused: " + answer.status);
          window.turnstile.remove(widget);
          box.remove();
        })
        .catch(function () {
          if (tries >= PERSON_TRIES) { say(PERSON_FAILED, true); return; }
          window.turnstile.reset(widget); // a spent token is never sent again: a new one comes
        });
    }
    window.jevaduPerson = function () {
      try {
        widget = window.turnstile.render(box.querySelector(".hm-person-widget"), {
          sitekey: box.getAttribute("data-sitekey"),
          action: "visitor",
          appearance: "interaction-only",
          theme: document.documentElement.getAttribute("data-bs-theme") === "dark" ? "dark" : "light",
          callback: sent,
          "before-interactive-callback": function () {
            // The windows are modal: the box behind an open one could not be clicked.
            closeViewer();
            var sheet = $("sheet");
            if (sheet && sheet.open) sheet.close();
            say(PERSON_ASKS, false);
          },
          "error-callback": function () { say(PERSON_FAILED, true); },
          "unsupported-callback": function () { say(PERSON_UNSUPPORTED, true); }
        });
      } catch (error) {
        say(PERSON_FAILED, true);
      }
    };
    box.querySelector(".hm-person-close").addEventListener("click", function () {
      box.hidden = true;
    });
    var script = document.createElement("script");
    script.src = PERSON_SCRIPT;
    script.async = true;
    script.onerror = function () { say(PERSON_BLOCKED, true); };
    document.head.appendChild(script);
  }

  // ------------------------------------------------------------- the tour (design 12.1, S8)
  // Offered once on a first visit of the search page, when its first screen is gone, and never
  // started by itself; the choice is kept in this browser. Driver.js (vendor, 1.10.1) is loaded
  // only when the tour starts. A step whose part is not on the page is left out. "Take the tour"
  // at the bottom of a page starts it again: at once here, elsewhere through /?tour=1.
  var TOUR_KEPT = "hm-tour";
  function tourChoice(how) {
    var local = store("localStorage");
    try {
      if (how && local) local.setItem(TOUR_KEPT, how);
      return local ? local.getItem(TOUR_KEPT) : null;
    } catch (error) { return null; }
  }
  function withDriver(then) {
    if (window.driver && window.driver.js) { then(); return; }
    var style = document.createElement("link");
    style.rel = "stylesheet";
    style.href = "/static/vendor/driver.css";
    document.head.appendChild(style);
    var script = document.createElement("script");
    script.src = "/static/vendor/driver.js.iife.js";
    script.onload = then;
    document.head.appendChild(script);
  }
  function tourSteps() {
    var holder = $("tour-steps");
    if (!holder) return [];
    var steps = [];
    holder.content.querySelectorAll("[data-step]").forEach(function (part) {
      var where = part.getAttribute("data-element");
      var element = where ? document.querySelector(where) : null;
      if (where && !element) return;
      steps.push({ element: element || undefined, popover: {
        title: part.querySelector("h3").textContent, description: part.querySelector("p").textContent,
        side: part.getAttribute("data-side") || undefined, align: "start" } });
    });
    return steps;
  }
  function startTour() {
    var offer = $("tour-offer");
    if (offer) offer.hidden = true;
    var steps = tourSteps();
    if (!steps.length) return;
    // Taken is seen, however it ends: Driver.js calls onDestroyed only once a step is in place,
    // not when the tour is skipped while its first step still moves in (driver.js 1.10.1, y()).
    tourChoice("seen");
    // A dark page dims less under the same shade, so the shade is deeper there (30 October 2026:
    // in the dark theme the lit part hardly stood out); the ring of style.css marks it in both.
    var dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    withDriver(function () {
      var tour = window.driver.js.driver({
        steps: steps, showProgress: true, progressText: "{{current}} of {{total}}",
        nextBtnText: "Next", prevBtnText: "Back", doneBtnText: "Done", popoverClass: "hm-tour",
        overlayOpacity: dark ? 0.72 : 0.45, stagePadding: 6, stageRadius: 6,
        disableActiveInteraction: true,
        animate: !LESS_MOTION.matches, smoothScroll: !LESS_MOTION.matches,
        onPopoverRender: function (popover) {
          var skip = document.createElement("button");
          skip.type = "button";
          skip.className = "hm-tour-skip";
          skip.textContent = "Skip the tour";
          skip.addEventListener("click", function () { tour.destroy(); });
          popover.footer.insertBefore(skip, popover.footer.firstChild);
        }
      });
      // Any click but on the note ends the tour, on its lit part too: while the tour runs, the
      // page does not react, so no click starts a search, Gemini or a window by mistake (30
      // October 2026: a click on the lit part went through to the page, and the tour went on).
      function outside(event) {
        if (!tour.isActive()) { document.removeEventListener("click", outside, true); return; }
        if (event.target.closest && event.target.closest(".driver-popover")) return;
        document.removeEventListener("click", outside, true);
        tour.destroy();
      }
      tour.drive();
      setTimeout(function () { document.addEventListener("click", outside, true); }, 0);
    });
  }
  function offerTour() {
    var offer = $("tour-offer");
    if (!offer) return;
    var address = new URL(window.location.href);
    if (address.searchParams.get("tour") === "1") {
      address.searchParams.delete("tour"); // a reload does not start it again
      history.replaceState(history.state, "", address.pathname + address.search + address.hash);
      startTour();
      return;
    }
    if (tourChoice() || address.searchParams.get("idea")) return;
    var root = document.documentElement;
    var wait = window.setInterval(function () { // after the name of the tool, not over it
      if (root.classList.contains("hm-splash")) return;
      window.clearInterval(wait);
      offer.hidden = false;
    }, 200);
  }
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-tour-start]")) { startTour(); return; }
    if (event.target.closest("[data-tour-decline]")) {
      tourChoice("declined");
      var offer = $("tour-offer");
      if (offer) offer.hidden = true;
      return;
    }
    if (event.target.closest("[data-tour-again]") && $("tour-steps")) {
      event.preventDefault();
      startTour();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    checkPerson();
    offerTour();
    applyTheme(chosenTheme());
    var themes = document.querySelector("[data-theme-switch]");
    if (themes) themes.hidden = false; // it needs this script, so it is hidden without it
    showCount();
    setUpTabs(document);
    setUpGraphs(document);
    setUpMore(document);
    drawCharts(document);
    remember(window.location.href);
    var dialog = viewer();
    if (dialog && document.querySelector("#viewer-body .project")) {
      showViewer(); // the address names an open project
      steps();
    }
  });

  // The values of a filter (design 8.2): the list stays open while its boxes are ticked, though
  // each tick sends the search and the row of filters comes back new; Escape or a click outside
  // closes it (1 November 2026).
  var openFilter = null;
  var tickedValue = null;
  document.addEventListener("htmx:beforeSwap", function () {
    var menu = document.querySelector(".hm-filter-menu[open]");
    openFilter = menu ? menu.getAttribute("data-filter") : null;
    var active = document.activeElement;
    tickedValue = menu && active && menu.contains(active) ? active.value : null;
  });
  document.addEventListener("htmx:afterSettle", function () {
    if (!openFilter) return;
    var menu = document.querySelector('.hm-filter-menu[data-filter="' + openFilter + '"]');
    openFilter = null;
    if (!menu) return;
    menu.open = true;
    var boxes = menu.querySelectorAll("input");
    for (var i = 0; i < boxes.length; i += 1) {
      if (boxes[i].value === tickedValue) {
        boxes[i].focus();
        break;
      }
    }
  });
  document.addEventListener("click", function (event) {
    var menus = document.querySelectorAll(".hm-filter-menu[open]");
    for (var i = 0; i < menus.length; i += 1) {
      if (!menus[i].contains(event.target)) menus[i].open = false;
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var menu = document.querySelector(".hm-filter-menu[open]");
    if (!menu) return;
    menu.open = false;
    menu.querySelector("summary").focus();
  });
})();
