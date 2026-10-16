// The few things the pages do in the browser. Every page works without this file: links and
// forms then load whole pages. With it, a card opens beside the list (or over it on a phone),
// the comparison fills in when it is ready, and the box of the idea counts its characters.
(function () {
  "use strict";
  var NARROW = window.matchMedia("(max-width: 899px)");
  var FAILED = "The comparison with your idea could not be written just now. " +
    "Everything else on this page is complete.";
  var openedHere = false; // a card was opened on this page, so "back" returns to the list

  function counter() {
    var box = document.getElementById("idea");
    var out = document.getElementById("idea-count");
    if (!box || !out) return;
    var limit = Number(out.getAttribute("data-limit")) || box.maxLength;
    var show = function () {
      var used = box.value.length;
      out.textContent = used.toLocaleString("en") + " of " + limit.toLocaleString("en") + " characters";
      out.classList.toggle("near", used > limit * 0.9);
    };
    box.addEventListener("input", show);
    box.addEventListener("keydown", function (event) {
      // Enter searches; Shift and Enter makes a new line, as in a chat box.
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        var form = box.form;
        if (form && form.requestSubmit) form.requestSubmit(); else if (form) form.submit();
      }
    });
    if (box.value) show();
  }

  function others(on) {
    // While the card covers the screen of a phone, the rest of the page is out of reach.
    ["search-band", "filters", "results"].forEach(function (id) {
      var node = document.getElementById(id) || document.querySelector("." + id);
      if (node) node.inert = on;
    });
    document.querySelectorAll(".site-header, .site-footer").forEach(function (node) { node.inert = on; });
    document.body.classList.toggle("panel-open", on);
  }

  function chosen(projectId) {
    document.querySelectorAll(".result[aria-current]").forEach(function (row) {
      row.removeAttribute("aria-current");
    });
    var row = document.getElementById("result-" + projectId);
    if (row) row.setAttribute("aria-current", "true");
  }

  function showPanel() {
    var panel = document.getElementById("panel");
    if (!panel) return;
    var heading = panel.querySelector(".card-head .card-title");
    var id = heading ? heading.id.replace("card-title-", "") : null;
    if (id) chosen(id);
    panel.classList.add("open");
    panel.scrollTop = 0;
    if (NARROW.matches) others(true);
    if (heading) heading.focus({ preventScroll: !NARROW.matches });
  }

  function closePanel() {
    var panel = document.getElementById("panel");
    if (!panel) return;
    var row = document.querySelector(".result[aria-current] .result-link");
    panel.classList.remove("open");
    others(false);
    if (openedHere) {
      openedHere = false;
      history.back();
    } else {
      var url = new URL(window.location.href);
      url.searchParams.delete("open");
      history.replaceState(history.state, "", url.toString());
    }
    if (row) row.focus();
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-close-panel]")) {
      event.preventDefault();
      closePanel();
    }
  });
  document.addEventListener("keydown", function (event) {
    var panel = document.getElementById("panel");
    if (event.key === "Escape" && NARROW.matches && panel && panel.classList.contains("open")) {
      closePanel();
    }
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    if (target && target.id === "panel") {
      openedHere = true;
      showPanel();
    }
  });
  // On a phone the filters start closed, unless one is chosen, so the results come first.
  function foldFilters() {
    var filters = document.getElementById("filters");
    if (filters && NARROW.matches && !filters.querySelector(".chosen-count")) {
      filters.removeAttribute("open");
    }
  }
  var searched = false; // the last request of the form was a search, not a change of filter
  document.addEventListener("submit", function (event) {
    if (event.target && event.target.id === "ask") searched = true;
  });
  document.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail.target;
    if (!target || target.id !== "workspace") return;
    counter();
    if (searched && NARROW.matches) {
      foldFilters();
      var title = document.getElementById("results-title");
      if (title) {
        title.setAttribute("tabindex", "-1");
        title.scrollIntoView({ block: "start" });
        title.focus({ preventScroll: true });
      }
    }
    searched = false;
  });

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
    var elt = event.detail.elt;
    if (elt && elt.id === "compare-loader" && event.detail.xhr.status === 503) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  function compareFailed(event) {
    var elt = event.detail.elt;
    if (!elt || elt.id !== "compare-loader") return;
    document.querySelectorAll(".compare.waiting").forEach(function (place) {
      place.classList.remove("waiting");
      place.textContent = FAILED;
    });
  }
  // When the comparison takes longer than usual, the waiting words say so.
  document.addEventListener("htmx:beforeRequest", function (event) {
    var elt = event.detail.elt;
    if (!elt || elt.id !== "compare-loader") return;
    window.setTimeout(function () {
      document.querySelectorAll(".compare.waiting").forEach(function (place) {
        place.textContent = "Still writing: the model is slower than usual just now. " +
          "It stops after 30 seconds, and the rest of the page is complete.";
      });
    }, 12000);
  });
  document.addEventListener("htmx:sendError", compareFailed);
  document.addEventListener("htmx:responseError", compareFailed);

  NARROW.addEventListener("change", function () {
    var panel = document.getElementById("panel");
    others(Boolean(NARROW.matches && panel && panel.classList.contains("open")));
  });

  document.addEventListener("DOMContentLoaded", function () {
    counter();
    foldFilters();
    var panel = document.getElementById("panel");
    if (panel && panel.classList.contains("open") && NARROW.matches) others(true);
  });
})();
