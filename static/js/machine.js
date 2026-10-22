(function () {
  if (!window.Chart || !window.SUPERVYA_GRAPH_URL) return;

  const charts = {};
  const colors = {
    cpu: "#0b6e4f",
    memoire: "#1b4f72",
    disque: "#c47a12",
  };
  const labelsMap = {
    cpu: "CPU (%)",
    memoire: "Mémoire (%)",
    disque: "Disque (%)",
  };

  function makeChart(canvasId, label, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: label,
            data: [],
            borderColor: color,
            backgroundColor: color + "33",
            tension: 0.25,
            pointRadius: 0,
            borderWidth: 2,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        scales: {
          y: {
            min: 0,
            suggestedMax: 100,
            ticks: {
              callback: function (v) {
                return v + " %";
              },
            },
          },
        },
        plugins: {
          legend: { display: true },
        },
      },
    });
  }

  charts.cpu = makeChart("chart-cpu", labelsMap.cpu, colors.cpu);
  charts.memoire = makeChart("chart-memoire", labelsMap.memoire, colors.memoire);
  charts.disque = makeChart("chart-disque", labelsMap.disque, colors.disque);

  function formatLabel(ms) {
    return new Date(ms).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function load(periode) {
    const url = window.SUPERVYA_GRAPH_URL + "?periode=" + encodeURIComponent(periode);
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        const series = data.series || {};
        Object.keys(charts).forEach(function (key) {
          const chart = charts[key];
          if (!chart) return;
          const points = series[key] || [];
          chart.data.labels = points.map(function (p) {
            return formatLabel(p.t);
          });
          chart.data.datasets[0].data = points.map(function (p) {
            return p.v;
          });
          chart.update();
        });
      })
      .catch(function () {});
  }

  const switcher = document.getElementById("periode-switch");
  if (switcher) {
    switcher.addEventListener("click", function (ev) {
      const btn = ev.target.closest("button[data-periode]");
      if (!btn) return;
      switcher.querySelectorAll("button").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      load(btn.getAttribute("data-periode"));
    });
  }

  load("1h");
  setInterval(function () {
    const active = switcher && switcher.querySelector("button.active");
    load(active ? active.getAttribute("data-periode") : "1h");
  }, 30000);
})();
