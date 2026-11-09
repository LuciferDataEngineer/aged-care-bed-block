/* Stakeholder pages. Numbers come from data/marts.json and data/acpr.geojson. */
(function () {
  const nf = new Intl.NumberFormat("en-AU");
  const nf1 = new Intl.NumberFormat("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const charts = {};
  const made = {};
  let MARTS = null;
  let GEO = null;
  let stateFilter = "ALL";

  const STATE_ORDER = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"];
  const STATE_NAME = {
    NSW: "New South Wales", VIC: "Victoria", QLD: "Queensland", WA: "Western Australia",
    SA: "South Australia", TAS: "Tasmania", ACT: "Australian Capital Territory",
    NT: "Northern Territory", AUS: "Australia",
  };

  function n(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) return "–";
    return digits ? nf1.format(value) : nf.format(Math.round(value));
  }

  function latestNational() {
    return MARTS.national_series.find((row) => row.year === 2025);
  }

  function ausOutlook() {
    return MARTS.outlook.find((row) => row.state_code === "AUS");
  }

  function colourRatio(ratio) {
    if (ratio === null || ratio === undefined) return "#334155";
    if (ratio <= 0) return "#334155";
    if (ratio < 60) return "#ff5d73";
    if (ratio < 70) return "#ff8a5b";
    if (ratio < 78) return "#ffb020";
    return "#3dce8a";
  }

  function chartDefaults() {
    Chart.defaults.color = "#d5e2ef";
    Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
    Chart.defaults.font.family = '"Segoe UI", "Helvetica Neue", Arial, sans-serif';
    Chart.defaults.plugins.legend.labels.boxWidth = 14;
  }

  function baseOptions(extra) {
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: false, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    }, extra || {});
  }

  function remember(page, chart) {
    charts[page] = charts[page] || [];
    charts[page].push(chart);
    return chart;
  }

  function table(headers, rows) {
    const head = "<tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr>";
    const body = rows.map((row) => "<tr>" + row.map((cell) => `<td>${cell}</td>`).join("") + "</tr>").join("");
    return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  const STATUS_PILL = { red: "Behind", amber: "Watch", green: "On track" };
  const SHORT_TAKE = [
    "Behind the benchmark of 78 per 1,000.",
    "Places still short of that benchmark today.",
    "Counted rise last year, against about 10,600 needed.",
    "Each year to 2031 just to hold today's ratio.",
    "The region with the largest place gap.",
  ];

  function fillBanner() {
    const latest = latestNational();
    const earlier = MARTS.national_series.find((row) => row.year === 2015);
    const outlook = ausOutlook();
    document.getElementById("banner").textContent =
      `Australia is ${n(latest.shortfall_vs_78)} aged care places short, and added just ${n(latest.net_operational_places)} last year against ~10,600 needed.`;
    document.getElementById("banner-sub").textContent =
      `That is ${n(latest.per_1000_70, 1)} places per 1,000 people aged 70+, down from ${n(earlier.per_1000_70, 1)} in 2015. ` +
      `Reaching 78 by 2031 would take about ${n(outlook.annual_extra_to_reach_78)} extra places a year.`;
  }

  function fillKpis() {
    const host = document.getElementById("kpis");
    host.innerHTML = MARTS.kpis.map((kpi, index) => `
      <article class="kpi ${kpi.status}">
        <div class="kpi-top">
          <p class="label">${kpi.label}</p>
          <span class="pill">${STATUS_PILL[kpi.status] || "Watch"}</span>
        </div>
        <p class="value">${kpi.value}</p>
        <p class="unit">${kpi.unit}</p>
        <p class="take">${SHORT_TAKE[index] || kpi.takeaway}</p>
      </article>`).join("");
    document.getElementById("kpi-notes-body").innerHTML = table(
      ["Card", "Value", "Status", "Detail"],
      MARTS.kpis.map((kpi) => [
        kpi.label,
        kpi.value,
        STATUS_PILL[kpi.status] || "Watch",
        kpi.takeaway,
      ])
    );
  }

  function renderOverview() {
    const series = MARTS.national_series;
    const latest = latestNational();
    const first = series.find((row) => row.year === 2015);
    document.getElementById("overview-hero-sub").textContent =
      `From ${n(first.per_1000_70, 1)} in 2015 to ${n(latest.per_1000_70, 1)} in 2025. ` +
      `The Department’s own published ratio moved from ${n(first.published_ratio_per_1000_70, 1)} to ${n(latest.published_ratio_per_1000_70, 1)}.`;
    remember("overview", new Chart(document.getElementById("chart-ratio"), {
      type: "line",
      data: {
        labels: series.map((row) => row.year),
        datasets: [
          {
            label: "ABS population",
            data: series.map((row) => row.per_1000_70),
            borderColor: "#5ec8ff",
            backgroundColor: "rgba(94,200,255,0.15)",
            tension: 0.25,
            pointRadius: 4,
            fill: false,
          },
          {
            label: "Department published ratio",
            data: series.map((row) => row.published_ratio_per_1000_70),
            borderColor: "#c4b5fd",
            borderDash: [4, 4],
            pointRadius: 3,
            tension: 0.25,
          },
          {
            label: "Benchmark 78",
            data: series.map(() => 78),
            borderColor: "#ffb020",
            borderDash: [2, 3],
            pointRadius: 0,
          },
        ],
      },
      options: baseOptions({
        scales: {
          y: { title: { display: true, text: "Places per 1,000 people aged 70+" }, min: 60, max: 90 },
          x: { grid: { display: false } },
        },
      }),
    }));

    remember("overview", new Chart(document.getElementById("chart-net"), {
      type: "bar",
      data: {
        labels: series.filter((row) => row.net_operational_places !== null).map((row) => String(row.year)),
        datasets: [{
          label: "Net operational places",
          data: series.filter((row) => row.net_operational_places !== null).map((row) => row.net_operational_places),
          backgroundColor: series.filter((row) => row.net_operational_places !== null).map((row) => row.net_operational_places < 1500 ? "#ff5d73" : "#5ec8ff"),
        }],
      },
      options: baseOptions({
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, title: { display: true, text: "Places" } }, x: { grid: { display: false } } },
      }),
    }));

    const states = STATE_ORDER.map((code) => MARTS.states_latest.find((row) => row.state_code === code));
    remember("overview", new Chart(document.getElementById("chart-states"), {
      type: "bar",
      data: {
        labels: states.map((row) => row.state_code),
        datasets: [
          {
            type: "bar",
            label: "Places per 1,000 aged 70+",
            data: states.map((row) => row.per_1000_70),
            backgroundColor: states.map((row) => colourRatio(row.per_1000_70)),
          },
          {
            type: "line",
            label: "Benchmark 78",
            data: states.map(() => 78),
            borderColor: "#ffb020",
            pointRadius: 0,
            borderDash: [4, 3],
          },
        ],
      },
      options: baseOptions({
        scales: { y: { min: 0, max: 90, title: { display: true, text: "Places per 1,000" } }, x: { grid: { display: false } } },
      }),
    }));

    document.getElementById("overview-means").innerHTML =
      `<h2>What this means</h2>
       <p>In 2015 the country still had more than 78 operational residential places for every 1,000 people aged 70+.
       By 30 June 2025 that had fallen to ${n(latest.per_1000_70, 1)}, a gap of about ${n(latest.shortfall_vs_78)} places.
       Last year the stock of operational places grew by only ${n(latest.net_operational_places)}.
       Standing still at today’s ratio, while the older population keeps growing, takes several thousand new places a year. Last year’s increase does not do that.</p>`;

    document.getElementById("overview-table").innerHTML = table(
      ["Year", "Operational places", "People 70+", "People 80+", "Per 1,000 aged 70+", "Per 1,000 aged 80+", "Department ratio", "Net places", "Gap to 78"],
      series.map((row) => [
        row.year,
        n(row.operational_residential_places),
        n(row.pop_70_plus),
        n(row.pop_80_plus),
        n(row.per_1000_70, 1),
        n(row.per_1000_80, 1),
        n(row.published_ratio_per_1000_70, 1),
        row.net_operational_places === null ? "–" : n(row.net_operational_places),
        n(row.shortfall_vs_78),
      ])
    );
  }

  function renderRegions() {
    const pills = document.getElementById("state-pills");
    const options = ["ALL"].concat(STATE_ORDER);
    pills.innerHTML = options.map((code) =>
      `<button type="button" data-state="${code}" class="${code === stateFilter ? "is-on" : ""}">${code === "ALL" ? "All states" : code}</button>`
    ).join("");
    pills.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        stateFilter = button.dataset.state;
        pills.querySelectorAll("button").forEach((item) => item.classList.toggle("is-on", item === button));
        drawMap();
        drawRegionBars();
      });
    });
    document.getElementById("legend").innerHTML = [
      ["#ff5d73", "Under 60"],
      ["#ff8a5b", "60 to under 70"],
      ["#ffb020", "70 to under 78"],
      ["#3dce8a", "78 or more"],
      ["#334155", "Not in this filter"],
    ].map(([colour, label]) => `<span><i class="swatch" style="background:${colour}"></i>${label}</span>`).join("");
    drawMap();
    drawRegionBars();
    const worst = MARTS.acpr[0];
    const darwin = MARTS.acpr.find((row) => row.acpr_name === "Darwin");
    document.getElementById("region-means").innerHTML =
      `<h2>What this means</h2>
       <p>${worst.acpr_name} in ${STATE_NAME[worst.state_code]} is missing the most places against the benchmark: about ${n(worst.shortfall_vs_78)}.
       The lowest ratio among regions that have places is ${darwin ? darwin.acpr_name : "Darwin"} at ${darwin ? n(darwin.published_ratio_per_1000_70, 1) : "–"} per 1,000.
       Wide Bay in Queensland is both thin and large: a ratio near 50 and one of the bigger place gaps.
       Indian Ocean Territories has no residential places in the stocktake and is not drawn.</p>`;
    const rows = MARTS.acpr.slice().sort((a, b) => a.state_code.localeCompare(b.state_code) || a.acpr_name.localeCompare(b.acpr_name));
    document.getElementById("region-table").innerHTML = table(
      ["State", "Region", "Operational places", "Published ratio per 1,000 aged 70+", "Gap to 78 (places)", "Estimated per 1,000 aged 80+"],
      rows.map((row) => [
        row.state_code,
        row.acpr_name,
        n(row.operational_residential_places),
        n(row.published_ratio_per_1000_70, 1),
        n(row.shortfall_vs_78),
        n(row.per_1000_80_estimated, 1),
      ])
    );
  }

  function regionRows() {
    const rows = MARTS.acpr.filter((row) => row.operational_residential_places > 0);
    if (stateFilter === "ALL") return rows;
    return rows.filter((row) => row.state_code === stateFilter);
  }

  function drawRegionBars() {
    const top = regionRows().slice().sort((a, b) => b.shortfall_vs_78 - a.shortfall_vs_78).slice(0, 10);
    document.getElementById("region-bar-title").textContent =
      stateFilter === "ALL" ? "Ten largest place gaps" : `Largest place gaps in ${stateFilter}`;
    const existing = charts.regionBar;
    const data = {
      labels: top.map((row) => row.acpr_name),
      datasets: [{
        label: "Places short of 78 per 1,000",
        data: top.map((row) => Math.max(0, row.shortfall_vs_78)),
        backgroundColor: "#ff8a5b",
      }],
    };
    if (existing) {
      existing.data = data;
      existing.update();
      return;
    }
    charts.regionBar = new Chart(document.getElementById("chart-regions"), {
      type: "bar",
      data,
      options: baseOptions({
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, title: { display: true, text: "Places" } }, y: { grid: { display: false } } },
      }),
    });
  }

  function pathFromGeometry(geometry) {
    const minLon = 112.6, maxLon = 154.0, minLat = -44.0, maxLat = -10.2;
    function xy(lon, lat) {
      const x = (lon - minLon) / (maxLon - minLon) * 1000;
      const y = (maxLat - lat) / (maxLat - minLat) * 780 + 20;
      return [x, y];
    }
    function ring(coords) {
      return coords.map((pair, index) => {
        const [x, y] = xy(pair[0], pair[1]);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      }).join(" ") + " Z";
    }
    if (!geometry) return "";
    if (geometry.type === "Polygon") return geometry.coordinates.map(ring).join(" ");
    if (geometry.type === "MultiPolygon") return geometry.coordinates.map((poly) => poly.map(ring).join(" ")).join(" ");
    return "";
  }

  function drawMap() {
    const svg = document.getElementById("map");
    const byKey = {};
    MARTS.acpr.forEach((row) => { byKey[row.join_key] = row; });
    const tip = document.getElementById("tip");
    svg.innerHTML = "";
    GEO.features.forEach((feature) => {
      const props = feature.properties;
      const row = byKey[props.join_key];
      const dim = stateFilter !== "ALL" && props.state_code !== stateFilter;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", pathFromGeometry(feature.geometry));
      path.setAttribute("fill", dim ? "#243140" : colourRatio(row ? row.published_ratio_per_1000_70 : null));
      path.setAttribute("stroke", "#0c1117");
      path.setAttribute("stroke-width", "0.6");
      path.addEventListener("mousemove", (event) => {
        const ratio = row ? n(row.published_ratio_per_1000_70, 1) : "–";
        const places = row ? n(row.operational_residential_places) : "–";
        const gap = row ? n(row.shortfall_vs_78) : "–";
        tip.hidden = false;
        tip.innerHTML = `<strong>${props.acpr_name}</strong> · ${props.state_code}<br>${places} operational places<br>${ratio} per 1,000 aged 70+<br>${gap} places versus 78`;
        tip.style.left = Math.min(event.clientX + 14, window.innerWidth - 280) + "px";
        tip.style.top = (event.clientY + 14) + "px";
      });
      path.addEventListener("mouseleave", () => { tip.hidden = true; });
      svg.appendChild(path);
    });
  }

  function renderHospitals() {
    const quote = MARTS.reported.sa_hospital_patients_waiting;
    document.getElementById("hospital-quote").innerHTML =
      `${quote.statement}<span>ABC Radio National Breakfast, 10 November 2026, 7:30 am AEDT, and ABC News, 9 November 2026. Four years earlier the reported figure was about 60.</span>`;
    const sa = MARTS.state_series.filter((row) => row.state_code === "SA").sort((a, b) => a.year - b.year);
    const national = MARTS.national_series;
    remember("hospitals", new Chart(document.getElementById("chart-sa"), {
      type: "line",
      data: {
        labels: sa.map((row) => row.year),
        datasets: [
          { label: "South Australia", data: sa.map((row) => row.per_1000_70), borderColor: "#ff8a5b", tension: 0.25, pointRadius: 4 },
          { label: "Australia", data: national.map((row) => row.per_1000_70), borderColor: "#5ec8ff", tension: 0.25, pointRadius: 3 },
          { label: "Benchmark 78", data: sa.map(() => 78), borderColor: "#ffb020", borderDash: [4, 3], pointRadius: 0 },
        ],
      },
      options: baseOptions({
        scales: { y: { min: 50, max: 100, title: { display: true, text: "Places per 1,000 aged 70+" } }, x: { grid: { display: false } } },
      }),
    }));
    const states = STATE_ORDER.map((code) => MARTS.states_latest.find((row) => row.state_code === code));
    remember("hospitals", new Chart(document.getElementById("chart-hospital-states"), {
      type: "bar",
      data: {
        labels: states.map((row) => row.state_code),
        datasets: [{
          label: "Places per 1,000 aged 70+",
          data: states.map((row) => row.per_1000_70),
          backgroundColor: states.map((row) => row.state_code === "SA" ? "#ff8a5b" : "#5ec8ff"),
        }],
      },
      options: baseOptions({
        plugins: { legend: { display: false } },
        scales: { y: { min: 0, max: 90 }, x: { grid: { display: false } } },
      }),
    }));
    const saNow = sa.find((row) => row.year === 2025);
    const saThen = sa.find((row) => row.year === 2015);
    document.getElementById("hospital-means").innerHTML =
      `<h2>What this means</h2>
       <p>South Australia’s operational places rose from ${n(saThen.operational_residential_places)} in 2015 to ${n(saNow.operational_residential_places)} in 2025.
       The ratio fell from ${n(saThen.per_1000_70, 1)} to ${n(saNow.per_1000_70, 1)} per 1,000 people aged 70+.
       Last year the state added ${n(saNow.net_operational_places)} operational places.
       Over the same decade the state reports the number of older patients waiting in hospital for a residential place rose from about 60 to more than 500.
       This page does not calculate that queue. The place ratio and the reported queue point the same way: supply has not kept up with the older population.</p>`;
    document.getElementById("hospital-table").innerHTML = table(
      ["Year", "Operational places", "People aged 70+", "Per 1,000 aged 70+", "Net places"],
      sa.map((row) => [row.year, n(row.operational_residential_places), n(row.pop_70_plus), n(row.per_1000_70, 1), row.net_operational_places === null ? "–" : n(row.net_operational_places)])
    );
  }

  function renderOutlook() {
    const states = STATE_ORDER.map((code) => MARTS.outlook.find((row) => row.state_code === code));
    const aus = ausOutlook();
    document.getElementById("outlook-title").textContent =
      `About ${n(aus.annual_extra_to_hold_ratio)} extra places a year would hold today’s national ratio to 2031`;
    remember("outlook", new Chart(document.getElementById("chart-outlook"), {
      type: "bar",
      data: {
        labels: states.map((row) => row.state_code),
        datasets: [
          { label: "Each year to hold today’s ratio", data: states.map((row) => row.annual_extra_to_hold_ratio), backgroundColor: "#5ec8ff" },
          { label: "Each year to reach 78 by 2031", data: states.map((row) => row.annual_extra_to_reach_78), backgroundColor: "#ff8a5b" },
        ],
      },
      options: baseOptions({
        scales: { y: { beginAtZero: true, title: { display: true, text: "Extra places a year" } }, x: { grid: { display: false } } },
      }),
    }));
    const pop = MARTS.projection_series.filter((row) => row.state_code === "AUS").sort((a, b) => a.year - b.year);
    const erp = MARTS.national_series.map((row) => ({ year: row.year, pop: row.pop_70_plus }));
    remember("outlook", new Chart(document.getElementById("chart-pop"), {
      type: "line",
      data: {
        labels: erp.map((row) => row.year).concat(pop.filter((row) => row.year > 2025).map((row) => row.year)),
        datasets: [
          {
            label: "Estimated resident population, 70+",
            data: erp.map((row) => row.pop).concat(pop.filter((row) => row.year > 2025).map(() => null)),
            borderColor: "#5ec8ff",
            spanGaps: false,
            pointRadius: 3,
          },
          {
            label: "Medium projection path, anchored on the 2025 estimate",
            data: erp.map((row) => (row.year === 2025 ? row.pop : null)).concat(
              pop.filter((row) => row.year > 2025).map((row) => {
                const base = pop.find((item) => item.year === 2025);
                const erp2025 = latestNational().pop_70_plus;
                return erp2025 * (row.pop_70_plus / base.pop_70_plus);
              })
            ),
            borderColor: "#2ee6c7",
            borderDash: [5, 4],
            spanGaps: true,
            pointRadius: 3,
          },
        ],
      },
      options: baseOptions({
        scales: { y: { title: { display: true, text: "People aged 70+" } }, x: { grid: { display: false } } },
      }),
    }));
    document.getElementById("outlook-means").innerHTML =
      `<h2>What this means</h2>
       <p>If no current place closes, Australia needs about ${n(aus.extra_places_to_hold_ratio)} more operational residential places by 30 June 2031 just to keep ${n(latestNational().per_1000_70, 1)} per 1,000.
       Getting back to 78 by then needs about ${n(aus.extra_places_to_reach_78)}.
       That is ${n(aus.annual_extra_to_reach_78)} a year, against ${n(latestNational().net_operational_places)} added last year.
       These are not forecasts of what governments will build. They are the arithmetic of the ABS medium projection and today’s stock. Regions are assumed to keep their 2025 share of their state’s older population.</p>`;
    const outlookRows = ["AUS"].concat(STATE_ORDER).map((code) => MARTS.outlook.find((row) => row.state_code === code));
    document.getElementById("outlook-table").innerHTML = table(
      ["State", "Places in 2025", "People 70+ in 2025", "People 70+ in 2031", "Extra places to hold the ratio", "Per year", "Extra places to reach 78", "Per year"],
      outlookRows.map((row) => [
        STATE_NAME[row.state_code],
        n(row.places_base),
        n(row.erp_70_base),
        n(row.pop_70_horizon),
        n(row.extra_places_to_hold_ratio),
        n(row.annual_extra_to_hold_ratio),
        n(row.extra_places_to_reach_78),
        n(row.annual_extra_to_reach_78),
      ])
    );
  }

  function renderAction() {
    const latest = latestNational();
    const aus = ausOutlook();
    const rows = [
      ["Added last year", latest.net_operational_places, "Counted from the stocktake"],
      ["Hold today’s ratio", aus.annual_extra_to_hold_ratio, "Counted, ABS medium projection, per year to 2031"],
      ["States’ reported need", MARTS.reported.national_places_needed_per_year.value, "Quoted by ABC News, 9 November 2026"],
      ["Federal claim", MARTS.reported.federal_construction_claim.value, "Quoted by ABC News, 9 November 2026"],
      ["Reach 78 by 2031", aus.annual_extra_to_reach_78, "Counted, ABS medium projection, per year"],
    ];
    remember("action", new Chart(document.getElementById("chart-pace"), {
      type: "bar",
      data: {
        labels: rows.map((row) => row[0]),
        datasets: [{
          label: "Residential places a year",
          data: rows.map((row) => row[1]),
          backgroundColor: ["#ff5d73", "#5ec8ff", "#c4b5fd", "#2ee6c7", "#ff8a5b"],
        }],
      },
      options: baseOptions({
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, title: { display: true, text: "Places a year" } }, y: { grid: { display: false } } },
      }),
    }));
    document.getElementById("action-steps").innerHTML = `
      <article class="step"><h3>1. Count the pace, not the announcement</h3><p>Last year’s counted increase was ${n(latest.net_operational_places)} operational places. The reported “about 800” matches that count. It is far below both the states’ 10,600 and the roughly ${n(aus.annual_extra_to_hold_ratio)} a year needed to hold today’s ratio.</p></article>
      <article class="step"><h3>2. Look at beds and at ratios</h3><p>New South Wales is missing the most places. The Northern Territory, the ACT, Tasmania and Western Australia have the thinnest ratios. A national average hides both.</p></article>
      <article class="step"><h3>3. Treat 78 as a yardstick</h3><p>78 residential places per 1,000 people aged 70+ is the old planning benchmark, not a measure of who needs a bed this week. Holding today’s lower ratio is the minimum that stops the gap getting wider.</p></article>
      <article class="step"><h3>4. Do not read a place as a free bed</h3><p>These figures are operational places. A region can be on the map with places and still have no bed free. The South Australian hospital number is a reported queue, not something this count produces.</p></article>`;
    document.getElementById("action-means").innerHTML =
      `<h2>What this means</h2>
       <p>The 10,600 places a year that states have asked for would, on the ABS medium projection, be enough to hold today’s national ratio of ${n(latest.per_1000_70, 1)} and to close a little of the gap. It would not get the country back to 78 by 2031. That would take about ${n(aus.annual_extra_to_reach_78)} extra places a year if none of today’s places close. The federal claim of about 5,000 beds a year, if it became operational places, would slow the slide and would not stop it.</p>`;
    document.getElementById("action-table").innerHTML = table(
      ["Comparison", "Places a year", "What it is"],
      rows.map((row) => [row[0], n(row[1]), row[2]])
    );
  }

  const renderers = {
    overview: renderOverview,
    regions: renderRegions,
    hospitals: renderHospitals,
    outlook: renderOutlook,
    action: renderAction,
  };

  function show(page) {
    document.querySelectorAll("[data-page]").forEach((section) => {
      section.hidden = section.dataset.page !== page;
    });
    document.querySelectorAll("[data-tab]").forEach((button) => {
      const on = button.dataset.tab === page;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (!made[page]) {
      made[page] = true;
      renderers[page]();
    }
    (charts[page] || []).forEach((chart) => chart.resize());
    if (page === "regions" && charts.regionBar) charts.regionBar.resize();
    requestAnimationFrame(() => {
      (charts[page] || []).forEach((chart) => chart.resize());
      if (page === "regions" && charts.regionBar) charts.regionBar.resize();
    });
  }

  async function start() {
    chartDefaults();
    const [marts, geo] = await Promise.all([
      fetch("data/marts.json").then((response) => response.json()),
      fetch("data/acpr.geojson").then((response) => response.json()),
    ]);
    MARTS = marts;
    GEO = geo;
    fillBanner();
    fillKpis();
    document.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => show(button.dataset.tab));
    });
    show("overview");
  }

  start().catch((error) => {
    document.getElementById("banner").textContent = "The figures could not be loaded.";
    console.error(error);
  });
})();
