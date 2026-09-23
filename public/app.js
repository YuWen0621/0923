/**
 * app.js - Taiwan Weather Forecast Vercel Web Demo
 * Replicates Streamlit app features, themes, Leaflet map, and Chart.js chart.
 */

const REGION_COORDINATES = {
  "北部地區": [25.04, 121.56],
  "中部地區": [24.15, 120.67],
  "南部地區": [22.99, 120.21],
  "東北部地區": [24.75, 121.75],
  "東部地區": [23.98, 121.60],
  "東南部地區": [22.76, 121.14],
};

const REGION_SHORT_NAMES = {
  "北部地區": "北部",
  "中部地區": "中部",
  "南部地區": "南部",
  "東北部地區": "東北部",
  "東部地區": "東部",
  "東南部地區": "東南部",
};

const REGION_BOUNDARY_COLORS = {
  "北部地區": "#2563EB",
  "中部地區": "#059669",
  "南部地區": "#D97706",
  "東北部地區": "#7C3AED",
  "東部地區": "#0891B2",
  "東南部地區": "#DB2777",
};

function getTemperatureColor(avgTemp) {
  if (avgTemp < 20.0) return "#2E86AB";
  if (avgTemp < 25.0) return "#48A9A6";
  if (avgTemp < 30.0) return "#F4D35E";
  return "#EE6055";
}

// ── Application State ─────────────────────────────────────────
const state = {
  theme: "light", // 'light' or 'dark'
  weatherData: null,
  geoJsonData: null,
  selectedDate: null,
  selectedRegion: null,
  isPanelOpen: false,
  map: null,
  baseTileLayer: null,
  geoJsonLayer: null,
  markersLayerGroup: null,
  chartInstance: null,
};

// ── DOM Elements ──────────────────────────────────────────────
const el = {
  txtNowTime: document.getElementById("txt-now-time"),
  txtFetchTime: document.getElementById("txt-fetch-time"),
  selectDate: document.getElementById("select-date"),
  selectRegion: document.getElementById("select-region"),
  btnRefresh: document.getElementById("btn-refresh"),
  refreshSpinner: document.getElementById("refresh-spinner"),
  refreshText: document.getElementById("refresh-text"),
  btnInfo: document.getElementById("btn-info"),
  btnTheme: document.getElementById("btn-theme"),
  mapWrapper: document.getElementById("map-wrapper"),
  sidePanel: document.getElementById("side-panel"),
  btnClosePanel: document.getElementById("btn-close-panel"),
  panelRegionTitle: document.getElementById("panel-region-title"),
  cardDateVal: document.getElementById("card-date-val"),
  cardAvgBadge: document.getElementById("card-avg-badge"),
  cardTempRange: document.getElementById("card-temp-range"),
  cardWeatherVal: document.getElementById("card-weather-val"),
  cardPopVal: document.getElementById("card-pop-val"),
  panelWeatherCard: document.getElementById("panel-weather-card"),
  forecastTableBody: document.getElementById("forecast-table-body"),
  infoModal: document.getElementById("info-modal"),
  btnModalClose: document.getElementById("btn-modal-close"),
  modalOverlay: document.getElementById("modal-overlay"),
  toast: document.getElementById("toast"),
};

// ── Toast Notification ────────────────────────────────────────
function showToast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  setTimeout(() => el.toast.classList.remove("show"), 3000);
}

// ── Map Initialization ────────────────────────────────────────
function initMap() {
  state.map = L.map("map", {
    center: [23.65, 120.95],
    zoom: 8,
    minZoom: 7,
    maxZoom: 11,
    maxBounds: [[21.0, 118.0], [26.5, 123.5]],
    maxBoundsViscosity: 1.0,
  });

  state.markersLayerGroup = L.layerGroup().addTo(state.map);
  updateMapTiles();
}

function updateMapTiles() {
  if (state.baseTileLayer) {
    state.map.removeLayer(state.baseTileLayer);
  }

  if (state.theme === "dark") {
    state.baseTileLayer = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        maxZoom: 16,
      }
    );
  } else {
    state.baseTileLayer = L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
        maxZoom: 18,
      }
    );
  }
  state.baseTileLayer.addTo(state.map);
}

// ── GeoJSON Loading & Rendering ───────────────────────────────
async function loadGeoJson() {
  try {
    const res = await fetch("taiwan_regions.geojson");
    if (!res.ok) throw new Error("GeoJSON not found");
    state.geoJsonData = await res.json();
    renderGeoJson();
  } catch (err) {
    console.error("Failed to load GeoJSON:", err);
  }
}

function renderGeoJson() {
  if (!state.geoJsonData || !state.map) return;
  if (state.geoJsonLayer) {
    state.map.removeLayer(state.geoJsonLayer);
  }

  state.geoJsonLayer = L.geoJSON(state.geoJsonData, {
    style: (feature) => {
      const regionName = feature.properties?.region;
      const borderColor = REGION_BOUNDARY_COLORS[regionName] || "#2563EB";
      const isActive = state.isPanelOpen && regionName === state.selectedRegion;
      return {
        color: borderColor,
        fillColor: borderColor,
        weight: isActive ? 3.5 : 2.2,
        fillOpacity: isActive ? 0.32 : 0.15,
      };
    },
    onEachFeature: (feature, layer) => {
      const region = feature.properties?.region || "";
      const county = feature.properties?.county || "";
      layer.bindTooltip(`<b>氣象分區：</b>${region}<br><b>縣市：</b>${county}`, {
        sticky: true,
      });

      layer.on({
        mouseover: (e) => {
          const l = e.target;
          l.setStyle({
            weight: 3.8,
            fillOpacity: 0.45,
          });
        },
        mouseout: (e) => {
          state.geoJsonLayer.resetStyle(e.target);
        },
        click: () => {
          if (region) {
            selectRegion(region);
          }
        },
      });
    },
  }).addTo(state.map);
}

// ── Weather Markers Rendering ─────────────────────────────────
function renderWeatherMarkers() {
  if (!state.weatherData || !state.selectedDate) return;
  state.markersLayerGroup.clearLayers();

  const isDark = state.theme === "dark";
  const labelColor = isDark ? "#f8fafc" : "#1a252f";
  const shadowColor = isDark
    ? "1px 1px 3px black, -1px -1px 3px black, 1px -1px 3px black, -1px 1px 3px black"
    : "1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white";

  Object.entries(REGION_COORDINATES).forEach(([regionName, coords]) => {
    const list = state.weatherData.regions[regionName];
    if (!list) return;

    const dayInfo = list.find((item) => item.date === state.selectedDate);
    if (!dayInfo) return;

    const avgTemp = dayInfo.avg;
    const colorHex = getTemperatureColor(avgTemp);
    const shortName = REGION_SHORT_NAMES[regionName] || regionName;
    const popDisplay = dayInfo.pop !== null && dayInfo.pop !== undefined ? `${dayInfo.pop}%` : "--";

    // CircleMarker
    const circle = L.circleMarker(coords, {
      radius: 14,
      color: "#ffffff",
      weight: 2.5,
      fillColor: colorHex,
      fillOpacity: 0.9,
    });

    circle.bindTooltip(`<b>${regionName}</b>: ${avgTemp.toFixed(1)}°C ｜ ${dayInfo.weather}`, {
      direction: "top",
    });

    const popupHtml = `
      <div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; min-width: 150px; padding: 4px;">
        <h4 style="margin: 0 0 6px 0; color: #2c3e50; border-bottom: 2px solid ${colorHex}; padding-bottom: 3px;">
          ${regionName}
        </h4>
        <b>預報日期：</b>${state.selectedDate}<br>
        <b>最低氣溫：</b>${dayInfo.mint.toFixed(1)}°C<br>
        <b>最高氣溫：</b>${dayInfo.maxt.toFixed(1)}°C<br>
        <b>平均溫度：</b><span style="font-weight: bold; color: ${colorHex};">${avgTemp.toFixed(1)}°C</span><br>
        <b>天氣現象：</b>${dayInfo.weather}<br>
        <b>降雨機率：</b>${popDisplay}
      </div>
    `;
    circle.bindPopup(popupHtml, { maxWidth: 250 });

    circle.on("click", () => {
      selectRegion(regionName);
    });

    circle.addTo(state.markersLayerGroup);

    // DivIcon Label next to circle
    const labelIcon = L.divIcon({
      className: "region-map-label",
      html: `<div style="color: ${labelColor}; text-shadow: ${shadowColor};">${shortName}</div>`,
      iconSize: [60, 20],
      iconAnchor: [-10, 10],
    });

    const marker = L.marker([coords[0] - 0.03, coords[1] + 0.15], { icon: labelIcon });
    marker.on("click", () => selectRegion(regionName));
    marker.addTo(state.markersLayerGroup);
  });
}

// ── Region Selection & Side Panel ─────────────────────────────
function selectRegion(regionName) {
  if (!regionName || !state.weatherData) {
    closePanel();
    return;
  }

  state.selectedRegion = regionName;
  state.isPanelOpen = true;
  el.selectRegion.value = regionName;

  el.mapWrapper.classList.remove("full-width");
  el.mapWrapper.classList.add("with-panel");
  el.sidePanel.classList.remove("hidden");

  setTimeout(() => state.map.invalidateSize(), 200);

  renderGeoJson();
  updateSidePanelContent();
}

function closePanel() {
  state.isPanelOpen = false;
  state.selectedRegion = null;
  el.selectRegion.value = "";

  el.sidePanel.classList.add("hidden");
  el.mapWrapper.classList.remove("with-panel");
  el.mapWrapper.classList.add("full-width");

  setTimeout(() => state.map.invalidateSize(), 200);
  renderGeoJson();
}

function updateSidePanelContent() {
  const regionName = state.selectedRegion;
  if (!regionName || !state.weatherData) return;

  const list = state.weatherData.regions[regionName];
  if (!list || list.length === 0) return;

  const currentDay = list.find((item) => item.date === state.selectedDate) || list[0];
  const colorHex = getTemperatureColor(currentDay.avg);
  const popStr = currentDay.pop !== null && currentDay.pop !== undefined ? `${currentDay.pop}%` : "--";

  el.panelRegionTitle.textContent = `📍 ${regionName}`;
  el.cardDateVal.textContent = state.selectedDate;
  el.cardAvgBadge.textContent = `平均 ${currentDay.avg.toFixed(1)}°C`;
  el.cardAvgBadge.style.backgroundColor = colorHex;
  el.panelWeatherCard.style.borderLeftColor = colorHex;

  el.cardTempRange.textContent = `${currentDay.mint.toFixed(1)}°C ~ ${currentDay.maxt.toFixed(1)}°C`;
  el.cardWeatherVal.textContent = currentDay.weather;
  el.cardPopVal.textContent = popStr;

  // Render Chart
  renderChart(list);

  // Render Table
  el.forecastTableBody.innerHTML = list
    .map((row) => {
      const p = row.pop !== null && row.pop !== undefined ? `${row.pop}%` : "--";
      return `
        <tr>
          <td>${row.date}</td>
          <td>${row.mint.toFixed(1)}°C</td>
          <td>${row.maxt.toFixed(1)}°C</td>
          <td>${row.weather}</td>
          <td>${p}</td>
        </tr>
      `;
    })
    .join("");
}

// ── Chart.js 7-Day Temperature Line Chart ─────────────────────
function renderChart(forecastList) {
  const ctx = document.getElementById("forecastChart").getContext("2d");
  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const isDark = state.theme === "dark";
  const maxLineColor = isDark ? "#f87171" : "#E74C3C";
  const minLineColor = isDark ? "#38bdf8" : "#3498DB";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.08)";
  const textColor = isDark ? "#cbd5e1" : "#64748b";

  const labels = forecastList.map((item) =>
    item.date.length >= 10 ? item.date.slice(5).replace("-", "/") : item.date
  );
  const maxTemps = forecastList.map((item) => item.maxt);
  const minTemps = forecastList.map((item) => item.mint);

  const minVal = Math.min(...minTemps);
  const maxVal = Math.max(...maxTemps);

  state.chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "MaxT",
          data: maxTemps,
          borderColor: maxLineColor,
          backgroundColor: maxLineColor,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          tension: 0.2,
        },
        {
          label: "MinT",
          data: minTemps,
          borderColor: minLineColor,
          backgroundColor: minLineColor,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: {
            boxWidth: 12,
            color: textColor,
            font: { size: 11 },
          },
        },
        tooltip: {
          callbacks: {
            label: (context) => `${context.dataset.label}: ${context.parsed.y.toFixed(1)}°C`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 } },
        },
        y: {
          title: {
            display: true,
            text: "Temperature (°C)",
            color: textColor,
            font: { size: 10, weight: "bold" },
          },
          suggestedMin: Math.max(0, Math.floor(minVal - 2)),
          suggestedMax: Math.ceil(maxVal + 2),
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 } },
        },
      },
    },
  });
}

// ── Weather Data Fetching ─────────────────────────────────────
async function fetchWeather(force = false) {
  el.refreshSpinner.classList.remove("hidden");
  el.btnRefresh.disabled = true;

  try {
    const url = force ? "/api/weather?force=1" : "/api/weather";
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`API error ${res.status}`);
    }
    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || "無法取得預報資料");
    }

    state.weatherData = data;

    // Header Time Info
    el.txtNowTime.textContent = data.meta.now_display || "--";
    el.txtFetchTime.textContent = data.meta.last_fetch_display || "--";

    // Date Dropdown
    const dates = data.dates || [];
    el.selectDate.innerHTML = dates
      .map((d) => `<option value="${d}">${d}</option>`)
      .join("");

    if (!state.selectedDate || !dates.includes(state.selectedDate)) {
      state.selectedDate = dates[0] || null;
    }
    el.selectDate.value = state.selectedDate;

    renderWeatherMarkers();

    if (state.isPanelOpen && state.selectedRegion) {
      updateSidePanelContent();
    }

    if (force) {
      showToast("✅ 已成功獲取中央氣象署最新預報！");
    }
  } catch (err) {
    console.error("Fetch weather failed:", err);
    showToast(`⚠️ 獲取預報失敗：${err.message}`);
  } finally {
    el.refreshSpinner.classList.add("hidden");
    el.btnRefresh.disabled = false;
  }
}

// ── Theme Management ──────────────────────────────────────────
function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  document.body.className = `theme-${state.theme}`;
  el.btnTheme.textContent = state.theme === "dark" ? "☀️ 淺色" : "🌙 深色";

  updateMapTiles();
  renderWeatherMarkers();

  if (state.isPanelOpen && state.selectedRegion && state.weatherData) {
    const list = state.weatherData.regions[state.selectedRegion];
    if (list) renderChart(list);
  }
}

// ── Event Listeners ───────────────────────────────────────────
function setupEvents() {
  // Date selector change
  el.selectDate.addEventListener("change", (e) => {
    state.selectedDate = e.target.value;
    renderWeatherMarkers();
    if (state.isPanelOpen) {
      updateSidePanelContent();
    }
  });

  // Region dropdown change
  el.selectRegion.addEventListener("change", (e) => {
    const r = e.target.value;
    if (r) {
      selectRegion(r);
    } else {
      closePanel();
    }
  });

  // Manual refresh button
  el.btnRefresh.addEventListener("click", () => {
    fetchWeather(true);
  });

  // Theme toggle
  el.btnTheme.addEventListener("click", toggleTheme);

  // Close panel button
  el.btnClosePanel.addEventListener("click", closePanel);

  // Info modal open/close
  el.btnInfo.addEventListener("click", () => {
    el.infoModal.classList.remove("hidden");
  });
  el.btnModalClose.addEventListener("click", () => {
    el.infoModal.classList.add("hidden");
  });
  el.modalOverlay.addEventListener("click", () => {
    el.infoModal.classList.add("hidden");
  });
}

// ── App Startup ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  setupEvents();
  await loadGeoJson();
  await fetchWeather(false);
});
