// Vue Planning : positionnement des missions dans la grille hebdomadaire
// (desktop). La vue agenda (mobile) est entièrement rendue côté serveur,
// donc fonctionne même si ce script échoue à charger.
(function () {
  var HOUR_HEIGHT = 48; // px par heure, doit rester en phase avec le CSS

  function toMinutes(hhmm) {
    var parts = hhmm.split(":");
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtTime(hhmm) {
    return hhmm.replace(":", "h");
  }

  // L'amplitude est rendue à part de la plage horaire : dans un bloc étroit,
  // les deux collées formaient un pavé illisible.
  function timeLabel(ev) {
    if (ev.continued_from_previous_day) {
      // 2e jour d'une mission de nuit : elle a commencé la veille.
      return "veille " + fmtTime(ev.start_time) + " → " + fmtTime(ev.end_time);
    }
    if (ev.continues_next_day) {
      return fmtTime(ev.start_time) + " → " + fmtTime(ev.end_time) + " (+1j)";
    }
    return fmtTime(ev.start_time) + "–" + fmtTime(ev.end_time);
  }

  // Empile les missions qui se chevauchent en colonnes côte à côte (façon
  // Google Calendar) : composantes connexes par intervalle, puis
  // coloration gloutonne des colonnes à l'intérieur de chaque composante.
  function layoutDay(dayEvents) {
    // span_start_min / span_end_min = la portion de la mission qui tombe
    // dans CE jour-là (le serveur a déjà découpé les missions de nuit).
    dayEvents.forEach(function (ev) {
      ev._start = ev.span_start_min;
      ev._end = Math.max(ev.span_end_min, ev._start + 15);
    });
    dayEvents.sort(function (a, b) { return a._start - b._start; });

    var clusters = [];
    dayEvents.forEach(function (ev) {
      var cluster = clusters[clusters.length - 1];
      if (cluster && ev._start < cluster.end) {
        cluster.events.push(ev);
        cluster.end = Math.max(cluster.end, ev._end);
      } else {
        clusters.push({ events: [ev], end: ev._end });
      }
    });

    clusters.forEach(function (cluster) {
      var colEnds = [];
      cluster.events.forEach(function (ev) {
        var col = 0;
        while (col < colEnds.length && colEnds[col] > ev._start) col++;
        colEnds[col] = ev._end;
        ev._col = col;
      });
      cluster.events.forEach(function (ev) { ev._cols = colEnds.length; });
    });
  }

  function renderGrid() {
    var dataEl = document.getElementById("planning-events");
    var gridEl = document.getElementById("planning-grid");
    if (!dataEl || !gridEl) return;

    var events;
    try {
      events = JSON.parse(dataEl.textContent || "[]");
    } catch (e) {
      return;
    }

    var timed = {}, allDay = [];
    events.forEach(function (ev) {
      if (ev.all_day) { allDay.push(ev); return; }
      (timed[ev.date] = timed[ev.date] || []).push(ev);
    });
    Object.keys(timed).forEach(function (d) { layoutDay(timed[d]); });

    document.querySelectorAll(".planning-grid__daycol").forEach(function (col) {
      var date = col.getAttribute("data-date");
      (timed[date] || []).forEach(function (ev) {
        var a = document.createElement("a");
        a.href = ev.url;
        a.className = "planning-event"
          + (ev.continues_next_day ? " planning-event--continues" : "")
          + (ev.continued_from_previous_day ? " planning-event--continued" : "");
        a.title = ev.title + " — " + ev.driver_label + (ev.vehicle ? " — " + ev.vehicle : "");
        var top = (ev._start / 60) * HOUR_HEIGHT;
        var height = Math.max(18, ((ev._end - ev._start) / 60) * HOUR_HEIGHT);
        var widthPct = 100 / ev._cols;
        a.style.top = top + "px";
        a.style.height = height + "px";
        a.style.left = (ev._col * widthPct) + "%";
        a.style.width = "calc(" + widthPct + "% - 3px)";
        a.style.background = ev.color;
        a.innerHTML =
          '<div class="planning-event__time">' + escapeHtml(timeLabel(ev)) + "</div>" +
          (ev.amplitude
            ? '<div class="planning-event__amplitude">(' + escapeHtml(ev.amplitude) + ")</div>"
            : "") +
          '<div class="planning-event__title">' + escapeHtml(ev.title) + "</div>" +
          '<div class="planning-event__meta">' + escapeHtml(ev.driver_label) + "</div>" +
          (ev.vehicle ? '<div class="planning-event__vehicle">' + escapeHtml(ev.vehicle) + "</div>" : "");
        col.appendChild(a);
      });
    });

    var anyAllDay = false;
    allDay.forEach(function (ev) {
      var slot = document.querySelector('.planning-grid__allday-slot[data-date="' + ev.date + '"]');
      if (!slot) return;
      anyAllDay = true;
      var a = document.createElement("a");
      a.href = ev.url;
      a.className = "planning-allday-chip";
      a.style.background = ev.color;
      a.textContent = ev.title;
      a.title = ev.title + " — " + ev.driver_label;
      slot.appendChild(a);
    });
    if (!anyAllDay) {
      var row = document.getElementById("planning-grid-allday");
      if (row) row.style.display = "none";
    }

    // Ligne "maintenant" sur la colonne du jour courant.
    var today = gridEl.getAttribute("data-today");
    var todayCol = document.querySelector('.planning-grid__daycol[data-date="' + today + '"]');
    if (todayCol) {
      var now = new Date();
      var line = document.createElement("div");
      line.className = "planning-now-line";
      line.style.top = ((now.getHours() * 60 + now.getMinutes()) / 60 * HOUR_HEIGHT) + "px";
      todayCol.appendChild(line);
    }

    // La grille n'a plus d'ascenseur propre (c'est la page qui défile) :
    // rien à repositionner au chargement, et surtout pas la page elle-même,
    // qui escamoterait l'en-tête et les filtres.
  }

  function copyText(text, button) {
    var done = function () {
      var old = button.textContent;
      button.textContent = "Copié ✓";
      setTimeout(function () { button.textContent = old; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { /* rien */ }
    document.body.removeChild(ta);
  }

  function initSharePanel() {
    var select = document.getElementById("share-driver-select");
    var input = document.getElementById("share-link-input");
    var webcal = document.getElementById("share-webcal-link");
    var copyBtn = document.getElementById("share-copy-btn");
    if (!select || !input) return;
    var row = input.closest("[data-feed-base]");
    var base = row ? row.getAttribute("data-feed-base") : input.value;

    select.addEventListener("change", function () {
      var url = base + (select.value ? "&driver_id=" + encodeURIComponent(select.value) : "");
      input.value = url;
      if (webcal) webcal.href = url.replace(/^https?:\/\//, "webcal://");
    });

    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        input.select();
        copyText(input.value, copyBtn);
      });
    }
  }

  renderGrid();
  initSharePanel();
})();
