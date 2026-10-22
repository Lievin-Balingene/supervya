(function () {
  const machinesList = document.getElementById("machines-list");
  const alertesBody = document.querySelector("#alertes-table tbody");
  if (!machinesList || !alertesBody) return;

  function fmtDate(iso) {
    try {
      return new Date(iso).toLocaleString("fr-FR");
    } catch (e) {
      return iso;
    }
  }

  function renderMachines(machines) {
    if (!machines.length) {
      machinesList.innerHTML = '<p class="empty">Aucune machine activée pour le moment.</p>';
      return;
    }
    machinesList.innerHTML = machines
      .map(function (m) {
        return (
          '<a class="machine-card" href="/machines/' + m.id + '/" data-id="' + m.id + '">' +
          '<div class="name">' + m.identifiant + "</div>" +
          '<div class="meta">' + m.systeme + " · " + m.cle + "</div>" +
          '<div class="badge ' + m.couleur + '">' +
          '<span class="dot ' + m.couleur + '"></span>' +
          '<span class="statut">' + m.statut_label + "</span></div>" +
          '<div class="meta alertes-count">' + m.alertes_actives + " alerte(s) active(s)</div>" +
          "</a>"
        );
      })
      .join("");
  }

  function renderAlertes(alertes) {
    if (!alertes.length) {
      alertesBody.innerHTML = '<tr><td colspan="4" class="empty">Aucune alerte active.</td></tr>';
      return;
    }
    alertesBody.innerHTML = alertes
      .map(function (a) {
        return (
          "<tr><td>" + a.machine + "</td><td>" + a.titre +
          "</td><td>" + a.severite_label + "</td><td>" + fmtDate(a.date_debut) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function refresh() {
    fetch("/api/etat/", { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("etat");
        return r.json();
      })
      .then(function (data) {
        renderMachines(data.machines || []);
        renderAlertes(data.alertes || []);
      })
      .catch(function () {
        /* silencieux : prochaine tentative dans 30 s */
      });
  }

  setInterval(refresh, 30000);
})();
