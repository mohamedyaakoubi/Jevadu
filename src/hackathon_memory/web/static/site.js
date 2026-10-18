// What the page does in the browser (design 12.1, third version). Every page works without this
// file: links and forms then load whole pages. With it, a project opens in a window over the list,
// the windows of the bottom of the page open in place, each (i) explains its term on hover or on a
// tap, the last search stays until it is cleared, and the first page of a visit shows the name of
// the tool for a moment.
(function () {
  "use strict";
  var HOVER = window.matchMedia("(hover: hover) and (pointer: fine)");
  var FAILED = "The comparison with your idea could not be written just now. " +
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
    var other = event.target.value === "other";
    var days = document.querySelector("[data-check-days]");
    if (!days) return;
    days.hidden = !other;
    days.querySelectorAll("input").forEach(function (input) { input.required = other; });
  });

  // ---------------------------------------------------------------- the charts
  // Each canvas carries its numbers; Chart.js draws them as horizontal bars, all the projects
  // and those with a Hedera prize. The same numbers stand in a list for screen readers.
  // Chart.js gives the labels of a horizontal chart at most half of its width; a longer label
  // is cut at the left edge (seen on 18 October 2026), so it breaks into lines here.
  function lines(label) {
    var words = String(label).split(" "), out = [], line = "";
    words.forEach(function (word) {
      if (line && (line + " " + word).length > 22) { out.push(line); line = word; }
      else line = line ? line + " " + word : word;
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
      if (canvas.dataset.drawn) return;
      canvas.dataset.drawn = "1";
      var numbers = JSON.parse(canvas.getAttribute("data-chart"));
      new window.Chart(canvas, {
        type: "bar",
        data: {
          labels: numbers.labels,
          datasets: [
            { label: "Projects", data: numbers.all, backgroundColor: all, borderRadius: 3, barPercentage: 0.9 },
            { label: "With a Hedera prize", data: numbers.won, backgroundColor: won, borderRadius: 3, barPercentage: 0.9 }
          ]
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
          scales: { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { ticks: { autoSkip: false, callback: function (value) { return lines(this.getLabelForValue(value)); } } } }
        }
      });
    });
  }

  // ---------------------------------------------------------------- the (i) and its text
  var home = null; // where the texts live when no window is open
  var openTimer = 0, closeTimer = 0, current = null;
  function place(tip, button) {
    var rect = button.getBoundingClientRect();
    tip.style.left = "0px"; tip.style.top = "0px";
    var width = tip.offsetWidth, height = tip.offsetHeight;
    var left = Math.min(Math.max(8, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 8);
    var below = rect.bottom + 8, above = rect.top - height - 8;
    var top = below + height < window.innerHeight - 8 || above < 8 ? below : above;
    tip.style.left = Math.round(left) + "px";
    tip.style.top = Math.round(Math.max(8, top)) + "px";
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
  // While a submission is checked: what the programs do, in order (design 12.1, S3).
  function checking() {
    return '<div class="project check-progress" role="status"><h2 class="project-title">Checking the submission</h2>' +
      '<ol><li>GitHub: the dates of the code and its README.</li>' +
      '<li>The Hedera ledger: each ID that the README names.</li>' +
      '<li>The collection: the same code or IDs, and the closest past projects.</li></ol>' +
      '<p class="hm-small">This takes up to about half a minute. No model writes anything.</p></div>';
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
  // The comparison: a 503 carries the words of the failure for each result, so it is shown.
  document.addEventListener("htmx:beforeSwap", function (event) {
    // htmx 2 names the target of the swap as `elt` here; the element that asked is in the
    // request's config (htmx 2.0.11, seen in the browser on 18 October 2026).
    var config = event.detail.requestConfig;
    var elt = (config && config.elt) || event.detail.elt;
    var status = event.detail.xhr.status;
    var shown = elt && (elt.id === "compare-loader" || elt.id === "check" || elt.id === "register-form" ||
      elt.hasAttribute("data-check-compare") || elt.hasAttribute("data-check-again") ||
      elt.closest(".compare-ask"));
    if (shown && (status === 503 || status === 400)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  function compareFailed(event) {
    var elt = event.detail.elt;
    if (!elt || elt.id !== "compare-loader") return;
    document.querySelectorAll(".compare.waiting").forEach(function (place) {
      place.classList.remove("waiting");
      place.removeAttribute("aria-busy");
      place.textContent = FAILED;
    });
  }
  document.addEventListener("htmx:sendError", compareFailed);
  document.addEventListener("htmx:responseError", compareFailed);
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
    drawCharts(document); // an outerHTML swap leaves the old element in the event
    if (target.id !== "workspace" && target.id !== "main") return;
    showCount();
    if (bringResults && NARROW.matches) {
      var results = $("results");
      if (results) { results.scrollIntoView({ block: "start" }); results.focus({ preventScroll: true }); }
    }
    bringResults = false;
  });
  document.addEventListener("htmx:historyRestore", function () { drawCharts(document); showCount(); });
  document.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && (elt.id === "ai-button" || elt.hasAttribute("data-asks-gemini")) && !event.detail.successful) {
      var space = $("workspace");
      if (space) space.classList.remove("asking-ai"); // nothing came back: the list stays
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(chosenTheme());
    var themes = document.querySelector("[data-theme-switch]");
    if (themes) themes.hidden = false; // it needs this script, so it is hidden without it
    showCount();
    drawCharts(document);
    remember(window.location.href);
    var dialog = viewer();
    if (dialog && document.querySelector("#viewer-body .project")) {
      showViewer(); // the address names an open project
      steps();
    }
  });
})();
