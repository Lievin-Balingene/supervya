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

  function fmtPct(v) {
    return v === null || v === undefined ? "—" : Math.round(v) + "%";
  }

  function renderMachines(machines) {
    if (!machines.length) {
      machinesList.innerHTML =
        '<div class="empty-state">' +
        "<p>Aucune machine activée pour le moment.</p>" +
        '<a class="btn" href="/licences/">Activer une licence</a></div>';
      return;
    }
    machinesList.innerHTML = machines
      .map(function (m) {
        return (
          '<a class="machine-card" href="/machines/' +
          m.id +
          '/" data-id="' +
          m.id +
          '">' +
          '<div class="machine-card-top">' +
          '<div class="name">' +
          m.identifiant +
          "</div>" +
          '<div class="badge ' +
          m.couleur +
          '"><span class="dot ' +
          m.couleur +
          '"></span><span class="statut">' +
          m.statut_label +
          "</span></div></div>" +
          '<div class="meta">' +
          m.systeme +
          " · IP " +
          (m.adresse_ip || "—") +
          "</div>" +
          '<div class="meta mono">' +
          m.cle +
          "</div>" +
          '<div class="mini-metrics">' +
          "<span>CPU " +
          fmtPct(m.cpu_pct) +
          "</span>" +
          "<span>RAM " +
          fmtPct(m.memoire_pct) +
          "</span>" +
          "<span>Disque " +
          fmtPct(m.disque_pct) +
          "</span></div>" +
          '<div class="meta alertes-count">' +
          m.alertes_actives +
          " alerte(s) active(s)</div></a>"
        );
      })
      .join("");
  }

  function renderAlertes(alertes) {
    if (!alertes.length) {
      alertesBody.innerHTML =
        '<tr><td colspan="4" class="empty">Aucune alerte active — tout est nominal.</td></tr>';
      return;
    }
    alertesBody.innerHTML = alertes
      .map(function (a) {
        return (
          "<tr><td>" +
          a.machine +
          "</td><td>" +
          a.titre +
          "</td><td>" +
          a.severite_label +
          "</td><td>" +
          fmtDate(a.date_debut) +
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
      .catch(function () {});
  }

  setInterval(refresh, 30000);
})();
