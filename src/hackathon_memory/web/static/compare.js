// After the results are shown, ask for the comparison with the idea and put each part in its
// place. The results never wait for it, and when it fails, every place says so in plain words.
(function () {
  "use strict";
  var list = document.querySelector("[data-compare-url]");
  if (!list) return;
  var waiting = function () { return document.querySelectorAll(".compare.waiting"); };
  var failed = function () {
    waiting().forEach(function (place) {
      place.classList.remove("waiting");
      place.textContent = "The comparison with your idea could not be written just now. " +
        "Everything else on this page is complete.";
    });
  };
  fetch(list.getAttribute("data-compare-url"))
    .then(function (answer) { return answer.ok ? answer.text() : Promise.reject(answer.status); })
    .then(function (html) {
      var parts = new DOMParser().parseFromString(html, "text/html");
      parts.querySelectorAll(".compare[data-project]").forEach(function (part) {
        var place = document.querySelector(
          '.compare.waiting[data-project="' + part.getAttribute("data-project") + '"]');
        if (place) place.replaceWith(document.importNode(part, true));
      });
      waiting().forEach(function (place) {
        place.classList.remove("waiting");
        place.textContent = "No comparison was written for this project.";
      });
    })
    .catch(failed);
})();
