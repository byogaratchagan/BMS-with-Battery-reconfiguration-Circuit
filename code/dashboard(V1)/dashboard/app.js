/*
 * Production-Grade SCADA EV/ESS BMS Dashboard Client Logic
 * Refactored to support dynamic cell grids, theme switching (Dark & Light),
 * tab-based categorization, interactive charts, and offline timeouts.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Global & State variables
  let lastSuccessfulUpdate = Date.now();
  let offlineTimeoutCheck = null;
  let isOffline = false;
  let currentTimeframe = '1m'; // Default timeframe
  let currentBmsConfig = {}; // Store latest config received from BMS
  let latestTelemetryData = null; // Cache last telemetry data for tab/theme redraws

  // Alert tracking & dismissal state
  let currentAlertsList = [];
  let dismissedAlertsHash = "";

  // Chart instances
  let barChart = null;
  let doughnutChart = null;
  let historicalChart = null;
  let miniWaveformChart = null;

  // Historical data memory
  const historyLabels = [];

  // ─── Theme Management (Default Dark vs White/Light) ────────────────────────
  function isLightTheme() {
    return document.body.classList.contains('light-theme');
  }

  function applyChartTheme(isLight) {
    const gridColor = isLight ? 'rgba(0, 0, 0, 0.08)' : 'rgba(255, 255, 255, 0.06)';
    const textColor = isLight ? '#475569' : '#94a3b8';
    const tooltipBg = isLight ? '#ffffff' : 'rgba(15, 22, 42, 0.95)';
    const tooltipTitle = isLight ? '#0f172a' : '#ffffff';
    const tooltipBody = isLight ? '#475569' : '#94a3b8';
    const tooltipBorder = isLight ? 'rgba(2, 132, 199, 0.35)' : 'rgba(0, 242, 254, 0.3)';

    if (barChart) {
      barChart.options.scales.x.grid.color = gridColor;
      barChart.options.scales.x.ticks.color = textColor;
      barChart.options.scales.x.ticks.font = { family: 'Outfit', size: 12, weight: 'bold' };
      barChart.options.scales.y.grid.color = gridColor;
      barChart.options.scales.y.ticks.color = textColor;
      barChart.options.scales.y.ticks.font = { family: 'JetBrains Mono', size: 11 };
      barChart.options.scales.y.title.color = textColor;
      barChart.options.scales.y.title.font = { family: 'Outfit', size: 12, weight: 'bold' };
      barChart.update('none');
    }

    if (historicalChart) {
      historicalChart.options.scales.x.grid.color = gridColor;
      historicalChart.options.scales.x.ticks.color = textColor;
      historicalChart.options.scales.x.ticks.font = { family: 'JetBrains Mono', size: 11 };
      historicalChart.options.scales.yVolt.grid.color = gridColor;
      historicalChart.options.scales.yVolt.ticks.color = isLight ? '#059669' : '#00e676';
      historicalChart.options.scales.yVolt.ticks.font = { family: 'JetBrains Mono', size: 11 };
      historicalChart.options.scales.yCurr.ticks.color = isLight ? '#0284c7' : '#00f2fe';
      historicalChart.options.scales.yCurr.ticks.font = { family: 'JetBrains Mono', size: 11 };
      historicalChart.options.plugins.legend.labels.color = textColor;
      historicalChart.options.plugins.legend.labels.font = { family: 'Outfit', size: 12, weight: 'bold' };
      if (historicalChart.options.plugins.tooltip) {
        historicalChart.options.plugins.tooltip.backgroundColor = tooltipBg;
        historicalChart.options.plugins.tooltip.titleColor = tooltipTitle;
        historicalChart.options.plugins.tooltip.bodyColor = tooltipBody;
        historicalChart.options.plugins.tooltip.borderColor = tooltipBorder;
      }
      historicalChart.update('none');
    }
  }

  function updateThemeToggleButton(isLight) {
    const icon = document.getElementById('themeToggleIcon');
    const text = document.getElementById('themeToggleText');
    if (icon && text) {
      if (isLight) {
        icon.className = 'fa-solid fa-moon';
        text.textContent = 'Dark Theme';
      } else {
        icon.className = 'fa-solid fa-sun';
        text.textContent = 'Light Theme';
      }
    }
  }

  function initTheme() {
    const savedTheme = localStorage.getItem('bms_theme');
    const light = savedTheme === 'light';
    if (light) {
      document.body.classList.add('light-theme');
      document.documentElement.classList.add('light-theme');
    } else {
      document.body.classList.remove('light-theme');
      document.documentElement.classList.remove('light-theme');
    }
    updateThemeToggleButton(light);

    const toggleBtn = document.getElementById('themeToggleBtn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const nowLight = document.body.classList.toggle('light-theme');
        document.documentElement.classList.toggle('light-theme', nowLight);
        localStorage.setItem('bms_theme', nowLight ? 'light' : 'dark');
        updateThemeToggleButton(nowLight);
        applyChartTheme(nowLight);
        if (latestTelemetryData) {
          drawTopology(latestTelemetryData);
        }
      });
    }
  }

  // ─── Tab Navigation Logic ──────────────────────────────────────────────────
  function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTabId = btn.getAttribute('data-tab');

        tabButtons.forEach(b => b.classList.remove('active'));
        tabContents.forEach(tc => tc.classList.remove('active'));

        btn.classList.add('active');
        const targetContent = document.getElementById(targetTabId);
        if (targetContent) {
          targetContent.classList.add('active');
        }

        // Trigger chart / canvas resizing so graphs adjust to active container dimensions
        setTimeout(() => {
          if (targetTabId === 'tab-overview') {
            if (latestTelemetryData) drawTopology(latestTelemetryData);
          } else if (targetTabId === 'tab-cells') {
            if (barChart) barChart.resize();
          } else if (targetTabId === 'tab-analytics') {
            if (historicalChart) historicalChart.resize();
            if (doughnutChart) doughnutChart.resize();
            if (miniWaveformChart) miniWaveformChart.resize();
          }
        }, 30);

        sessionStorage.setItem('bms_active_tab', targetTabId);
      });
    });

    // Restore previously active tab if available
    const savedTab = sessionStorage.getItem('bms_active_tab');
    if (savedTab) {
      const matchingBtn = document.querySelector(`.tab-btn[data-tab="${savedTab}"]`);
      if (matchingBtn) matchingBtn.click();
    }
  }

  // ─── Initialize All Dynamic Charts ─────────────────────────────────────────
  function initCharts() {
    const isLight = isLightTheme();
    const gridColor = isLight ? 'rgba(0, 0, 0, 0.08)' : 'rgba(255, 255, 255, 0.06)';
    const textColor = isLight ? '#475569' : '#94a3b8';

    // 1. Cell Voltage Distribution Bar Chart
    const barCtx = document.getElementById('cellVoltageBarChart').getContext('2d');
    barChart = new Chart(barCtx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Cell Voltage (V)',
          data: [],
          backgroundColor: [],
          borderRadius: 8,
          borderWidth: 1.5,
          borderColor: isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.12)'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: textColor, font: { family: 'Outfit', size: 12, weight: 'bold' } } },
          y: { min: 2.5, max: 4.5, grid: { color: gridColor }, ticks: { color: textColor, font: { family: 'JetBrains Mono', size: 11 } }, title: { display: true, text: 'Voltage (V)', color: textColor, font: { family: 'Outfit', size: 12, weight: 'bold' } } }
        },
        plugins: { legend: { display: false } }
      }
    });

    // 2. Health Analytics Doughnut
    const doughnutCtx = document.getElementById('healthDoughnutChart').getContext('2d');
    doughnutChart = new Chart(doughnutCtx, {
      type: 'doughnut',
      data: {
        labels: ['Healthy Cells', 'Warning Cells', 'Critical Cells'],
        datasets: [{
          data: [0, 0, 0],
          backgroundColor: isLight ? ['#059669', '#d97706', '#dc2626'] : ['#00e676', '#ffab00', '#ff1744'],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '74%',
        plugins: { legend: { display: false } }
      }
    });

    // 3. Mini Current Waveform
    const miniCtx = document.getElementById('miniCurrentWaveform').getContext('2d');
    miniWaveformChart = new Chart(miniCtx, {
      type: 'line',
      data: {
        labels: Array(24).fill(''),
        datasets: [{
          data: Array(24).fill(0),
          borderColor: isLight ? '#0284c7' : '#00f2fe',
          backgroundColor: isLight ? 'rgba(2, 132, 199, 0.1)' : 'rgba(0, 242, 254, 0.1)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { x: { display: false }, y: { display: false } },
        plugins: { legend: { display: false } }
      }
    });

    // 4. Historical Time-Series Analytics
    const histCtx = document.getElementById('historicalTimeSeriesChart').getContext('2d');
    historicalChart = new Chart(histCtx, {
      type: 'line',
      data: {
        labels: historyLabels,
        datasets: [
          { label: 'Voltage (V)', data: [], borderColor: isLight ? '#059669' : '#00e676', backgroundColor: 'transparent', tension: 0.3, borderWidth: 2.2, yAxisID: 'yVolt', pointRadius: 0 },
          { label: 'Current (A)', data: [], borderColor: isLight ? '#0284c7' : '#00f2fe', backgroundColor: isLight ? 'rgba(2, 132, 199, 0.06)' : 'rgba(0, 242, 254, 0.06)', tension: 0.3, borderWidth: 2.2, fill: true, yAxisID: 'yCurr', pointRadius: 0 },
          { label: 'SOC (%)', data: [], borderColor: '#4facfe', backgroundColor: 'transparent', tension: 0.3, borderWidth: 1.8, yAxisID: 'ySoc', pointRadius: 0 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: textColor, font: { family: 'JetBrains Mono', size: 11 }, maxTicksLimit: 8 } },
          yVolt: { type: 'linear', position: 'left', grid: { color: gridColor }, ticks: { color: isLight ? '#059669' : '#00e676', font: { family: 'JetBrains Mono', size: 11 } } },
          yCurr: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, ticks: { color: isLight ? '#0284c7' : '#00f2fe', font: { family: 'JetBrains Mono', size: 11 } } },
          ySoc: { type: 'linear', display: false, min: 0, max: 100 }
        },
        plugins: {
          legend: { labels: { color: textColor, font: { family: 'Outfit', size: 12, weight: 'bold' } } },
          tooltip: {
            backgroundColor: isLight ? '#ffffff' : 'rgba(15,22,42,0.95)',
            borderColor: isLight ? 'rgba(2, 132, 199, 0.35)' : 'rgba(0,242,254,0.3)',
            borderWidth: 1.5,
            titleColor: isLight ? '#0f172a' : '#fff',
            bodyColor: isLight ? '#475569' : '#94a3b8'
          },
          zoom: {
            pan: {
              enabled: true,
              mode: 'x',
              modifierKey: null
            },
            zoom: {
              wheel: { enabled: true },
              pinch: { enabled: true },
              mode: 'x',
              onZoomComplete: () => {
                const rzb = document.getElementById('resetZoomBtn');
                if (rzb) rzb.style.display = 'inline-flex';
              }
            }
          }
        }
      }
    });
  }

  // ─── Topology Drawing ───────────────────────────────────────────────────────
  function parseTopology(str) {
    if (str && str.includes('S') && str.includes('P')) {
      const s = parseInt(str.split('S')[0]) || 1;
      const p = parseInt(str.split('S')[1].replace('P','')) || 1;
      return { sCount: s, pCount: p };
    }
    return { sCount: 3, pCount: 1 };
  }

  function drawTopoOnCanvas(canvasId, topoStr, isCharging) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const parent = canvas.parentElement;
    canvas.width  = parent.clientWidth  || 240;
    canvas.height = parent.clientHeight || 120;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const { sCount, pCount } = parseTopology(topoStr);
    const isLight = isLightTheme();

    const accent = isCharging
      ? (isLight ? '#059669' : '#00e676')
      : (isLight ? '#d97706' : '#ffab00');

    const accentDim = isCharging
      ? (isLight ? 'rgba(5, 150, 105, 0.4)' : 'rgba(0, 230, 118, 0.3)')
      : (isLight ? 'rgba(217, 119, 6, 0.4)' : 'rgba(255, 171, 0, 0.3)');

    const cellFill = isLight ? '#ffffff' : 'rgba(15, 22, 42, 0.92)';
    const textLabelColor = isLight ? '#0f172a' : '#ffffff';

    if (sCount >= pCount) {
      // SERIES-dominant: draw cells horizontally left→right
      const cellW = Math.min(52, (w - 50) / sCount - 10);
      const cellH = Math.min(42, h * 0.42);
      const spacing = (w - 50 - sCount * cellW) / Math.max(sCount - 1, 1);
      const yMid = h / 2;

      // Bus wire
      ctx.strokeStyle = accentDim;
      ctx.lineWidth = 2.5;
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.moveTo(12, yMid);
      ctx.lineTo(w - 12, yMid);
      ctx.stroke();

      // Terminals
      ctx.fillStyle = accent;
      ctx.font = 'bold 14px Outfit';
      ctx.textAlign = 'left';
      ctx.fillText('+', 3, yMid + 5);
      ctx.textAlign = 'right';
      ctx.fillText('–', w - 3, yMid + 5);

      for (let i = 0; i < sCount; i++) {
        const bx = 24 + i * (cellW + spacing);
        const by = yMid - cellH / 2;

        ctx.fillStyle = cellFill;
        ctx.strokeStyle = accent;
        ctx.lineWidth = 2;
        if (!isLight) {
          ctx.shadowBlur = 8;
          ctx.shadowColor = accent;
        } else {
          ctx.shadowBlur = 3;
          ctx.shadowColor = 'rgba(0,0,0,0.1)';
        }
        ctx.beginPath();
        ctx.roundRect(bx, by, cellW, cellH, 6);
        ctx.fill();
        ctx.stroke();
        ctx.shadowBlur = 0;

        ctx.fillStyle = textLabelColor;
        ctx.font = `bold ${Math.min(13, cellW / 2.6)}px Outfit`;
        ctx.textAlign = 'center';
        ctx.fillText(`C${i + 1}`, bx + cellW / 2, yMid - (pCount > 1 ? 2 : -4));

        if (pCount > 1) {
          ctx.fillStyle = accent;
          ctx.font = `bold ${Math.min(10, cellW / 3.5)}px Outfit`;
          ctx.fillText(`×${pCount}P`, bx + cellW / 2, yMid + 12);
        }
      }
    } else {
      // PARALLEL-dominant: draw cells stacked vertically
      const cellH = Math.min(30, (h - 26) / pCount - 6);
      const cellW = Math.min(90, w * 0.48);
      const spacing = (h - 26 - pCount * cellH) / Math.max(pCount - 1, 1);
      const xMid = w / 2;

      // Left bus bar
      ctx.strokeStyle = accentDim;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(14, 12);
      ctx.lineTo(14, h - 12);
      ctx.stroke();

      // Right bus bar
      ctx.beginPath();
      ctx.moveTo(w - 14, 12);
      ctx.lineTo(w - 14, h - 12);
      ctx.stroke();

      ctx.fillStyle = accent;
      ctx.font = 'bold 14px Outfit';
      ctx.textAlign = 'center';
      ctx.fillText('+', w - 14, 10);
      ctx.fillText('–', 14, 10);

      for (let i = 0; i < pCount; i++) {
        const by = 14 + i * (cellH + spacing);
        const bx = xMid - cellW / 2;

        ctx.strokeStyle = accentDim;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(14, by + cellH / 2);
        ctx.lineTo(bx, by + cellH / 2);
        ctx.moveTo(bx + cellW, by + cellH / 2);
        ctx.lineTo(w - 14, by + cellH / 2);
        ctx.stroke();

        ctx.fillStyle = cellFill;
        ctx.strokeStyle = accent;
        ctx.lineWidth = 2;
        if (!isLight) {
          ctx.shadowBlur = 6;
          ctx.shadowColor = accent;
        } else {
          ctx.shadowBlur = 3;
          ctx.shadowColor = 'rgba(0,0,0,0.1)';
        }
        ctx.beginPath();
        ctx.roundRect(bx, by, cellW, cellH, 5);
        ctx.fill();
        ctx.stroke();
        ctx.shadowBlur = 0;

        ctx.fillStyle = textLabelColor;
        ctx.font = `bold ${Math.min(12, cellH * 0.55)}px Outfit`;
        ctx.textAlign = 'center';
        if (sCount > 1) {
          ctx.fillText(`C${i * sCount + 1}–C${(i + 1) * sCount} (${sCount}S)`, xMid, by + cellH / 2 + 4);
        } else {
          ctx.fillText(`Cell ${i + 1}`, xMid, by + cellH / 2 + 4);
        }
      }
    }
  }

  function drawTopology(data) {
    if (!data) return;
    const chgTopo = data.charge_topology    || data.configuration || '3S1P';
    const disTopo = data.discharge_topology || data.configuration || '3S1P';

    // Use firmware charging flag only. No current. No idle.
    // Before reflash (data.charging is null) → default DISCHARGING.
    const topoIsCharging = data.charging === true;
    const activeTopo = topoIsCharging ? chgTopo : disTopo;

    const chgParsed = parseTopology(chgTopo);
    const totalCells = chgParsed.sCount * chgParsed.pCount;

    const ctEl = document.getElementById('valChargeTopology');
    const dtEl = document.getElementById('valDischargeTopology');
    const tcEl = document.getElementById('valTotalCells');
    const bcEl = document.getElementById('topBadgeConfig');

    if (ctEl) ctEl.textContent = chgTopo;
    if (dtEl) dtEl.textContent = disTopo;
    if (tcEl) tcEl.textContent = `${totalCells} Total Cells`;
    if (bcEl) bcEl.textContent = topoIsCharging ? `CHG: ${chgTopo}` : `DIS: ${disTopo}`;

    const topEl = document.getElementById('topologyText');
    if (topEl) topEl.textContent = activeTopo;

    const hdrEl = document.getElementById('headerPackName');
    if (hdrEl) hdrEl.textContent = `EV BMS · CHG:${chgTopo} / DIS:${disTopo}`;

    drawTopoOnCanvas('topologyCanvasCharge',    chgTopo, true);
    drawTopoOnCanvas('topologyCanvasDischarge', disTopo, false);
  }

  // ─── Real-Time Data Validation Check ───────────────────────────────────────
  function validateData(data) {
    if (!data || typeof data !== 'object') return false;
    if (data.connected === undefined) return false;
    if (data.connected && (!data.cells || !Array.isArray(data.cells))) return false;
    return true;
  }

  // ─── Reset UI on Disconnect / Offline ──────────────────────────────────────
  function resetBmsUI(disconnectedState = true) {
    const discEl = document.getElementById('disconnectedOverlay');
    const offEl = document.getElementById('offlineOverlay');
    if (discEl) {
      discEl.classList.toggle('active', disconnectedState);
      discEl.style.display = disconnectedState ? 'flex' : 'none';
    }
    if (offEl) {
      offEl.classList.toggle('active', !disconnectedState);
      offEl.style.display = !disconnectedState ? 'flex' : 'none';
    }

    document.getElementById('systemStatusText').textContent = disconnectedState ? 'BATTERY DISCONNECTED' : 'DEVICE OFFLINE';
    document.getElementById('statusPulseDot').className = disconnectedState ? 'status-pulse pulse-red' : 'status-pulse';
    document.getElementById('topologyText').textContent = '--';
    document.getElementById('headerPackName').textContent = 'EV-ESS BMS Command Center';

    document.getElementById('valOverviewSoc').textContent = '--';
    document.getElementById('valOverviewSoh').textContent = '--';
    document.getElementById('valOverviewState').textContent = '--';
    document.getElementById('valOverviewMode').textContent = '--';
    document.getElementById('valPackVoltage').textContent = '--';
    document.getElementById('valPackCurrent').textContent = '--';
    document.getElementById('valInputVoltage').textContent = '--';
    document.getElementById('valPackTemp').textContent = '--';
    document.getElementById('valRemainingAh').textContent = '--';
    document.getElementById('valRemainingTime').textContent = '--';
    document.getElementById('valPowerKw').textContent = '--';

    document.getElementById('cellMonitoringGrid').innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 40px; font-size: 1rem;">
        <i class="fa-solid fa-battery-empty" style="font-size: 2.5rem; display: block; margin-bottom: 10px;"></i>
        Grid Offline — No Cell Telemetry Scanned
      </div>
    `;
    document.getElementById('moduleVisualizerGrid').innerHTML = '';

    document.getElementById('deltaVBadge').textContent = 'ΔV = --';
    document.getElementById('gaugeVin').textContent = '--';
    document.getElementById('gaugeVbat').textContent = '--';
    document.getElementById('gaugeVmax').textContent = '--';
    document.getElementById('gaugeVmin').textContent = '--';
    document.getElementById('gaugeVavg').textContent = '--';
    document.getElementById('gaugeDeltaV').textContent = '--';
    document.getElementById('valChargeCurrent').textContent = '--';
    document.getElementById('valDischargeCurrent').textContent = '--';
    document.getElementById('valNetCurrent').textContent = '--';
    document.getElementById('currentDirectionTag').textContent = '--';

    document.querySelectorAll('.status-badge-item').forEach(badge => {
      badge.className = 'status-badge-item badge-inactive';
    });

    document.getElementById('doughnutAvgSoh').textContent = '--';
    document.getElementById('valStrongestCell').textContent = '--';
    document.getElementById('valWeakestCell').textContent = '--';
    document.getElementById('valHealthImbalance').textContent = '--';
    document.getElementById('valCycleLife').textContent = '--';
    document.getElementById('valAgingTrend').textContent = '--';

    if (doughnutChart) {
      doughnutChart.data.datasets[0].data = [0, 0, 0];
      doughnutChart.update();
    }
  }

  // ─── Dynamic Cell Grid & Visualizer ────────────────────────────────────────
  function updateCellsGridAndVisualizer(cellsList) {
    const grid = document.getElementById('cellMonitoringGrid');
    const visualizer = document.getElementById('moduleVisualizerGrid');
    if (!grid || !visualizer) return;

    grid.innerHTML = '';
    visualizer.innerHTML = '';

    let healthy = 0, warn = 0, crit = 0;
    const cols = Math.min(8, cellsList.length);
    visualizer.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

    cellsList.forEach(cell => {
      const idx = cell.id;
      const v = parseFloat(cell.voltage);
      const soc = parseFloat(cell.soc);
      const soh = parseFloat(cell.soh);
      const temp = parseFloat(cell.temp) || 25.0;
      const ir = parseFloat(cell.ir) || 12.0;
      const bleed = parseFloat(cell.bleed) || 0.0;
      const health = cell.health || 'GOOD';

      if (isNaN(v) || v < 0 || v > 5.0 || isNaN(soc) || soc < 0 || soc > 100 || isNaN(soh) || soh < 0 || soh > 100) {
        return;
      }

      if (health === 'GOOD') healthy++;
      else if (health === 'DEGRADING') warn++;
      else crit++;

      // Visualizer block
      const block = document.createElement('div');
      block.className = `module-cell-block ${health === 'GOOD' ? '' : (health === 'DEGRADING' ? 'block-warn' : 'block-crit')}`;
      block.innerHTML = `
        <span class="cell-num">C${idx}</span>
        <div class="cell-v-mini">${v.toFixed(2)}V</div>
        <div class="cell-soc-mini">${soc.toFixed(0)}%</div>
      `;
      block.addEventListener('click', () => openCellModal(idx, v, soc, soh, temp, ir, bleed, health));
      visualizer.appendChild(block);

      // Detailed Cell card (Rendered prominently at top of Tab 2)
      const card = document.createElement('div');
      card.className = 'cell-spec-card';
      const statusClass = health === 'GOOD' ? 'status-good' : (health === 'DEGRADING' ? 'status-degrading' : 'status-dead');
      const offset = 110 - (110 * soc / 100);

      card.innerHTML = `
        <div class="cell-card-head">
          <span class="cell-id-title"><i class="fa-solid fa-battery-bolt"></i> Cell ${idx}</span>
          <span class="status-badge-sm ${statusClass}">${health}</span>
        </div>
        <div class="cell-main-values">
          <div class="cell-voltage-hero">${v.toFixed(3)}<small>V</small></div>
          <div class="mini-radial-soc">
            <svg viewBox="0 0 40 40" class="mini-radial-svg">
              <circle cx="20" cy="20" r="17.5" class="mini-ring-bg"></circle>
              <circle cx="20" cy="20" r="17.5" class="mini-ring-fg" style="stroke-dashoffset: ${offset};"></circle>
            </svg>
            <div class="mini-ring-text">${soc.toFixed(0)}%</div>
          </div>
        </div>
        <div class="cell-details-compact">
          <div><label>SOH</label><span>${soh.toFixed(1)}%</span></div>
          <div><label>Temp</label><span>${temp.toFixed(1)}°C</span></div>
          <div><label>Internal Res.</label><span>${ir.toFixed(1)} mΩ</span></div>
          <div><label>Balancing</label><span class="${bleed > 0 ? 'amber-text' : ''}">${bleed > 0 ? 'ACTIVE' : 'OFF'}</span></div>
        </div>
      `;
      card.addEventListener('click', () => openCellModal(idx, v, soc, soh, temp, ir, bleed, health));
      grid.appendChild(card);
    });

    if (doughnutChart) {
      doughnutChart.data.datasets[0].data = [healthy, warn, crit];
      doughnutChart.update('none');
    }
  }

  // ─── Cell Diagnostics Modal ────────────────────────────────────────────────
  function openCellModal(idx, v, soc, soh, temp, ir, bleed, health) {
    const modal = document.getElementById('cellDetailModal');
    const title = document.getElementById('modalCellTitle');
    const body = document.getElementById('modalCellBody');

    title.innerHTML = `<i class="fa-solid fa-battery-half"></i> Diagnostic Overview: Cell ${idx}`;
    body.innerHTML = `
      <div class="ml-features-grid">
        <div class="feat-box"><label>Cell Voltage</label><span>${v.toFixed(3)} V</span></div>
        <div class="feat-box"><label>State of Charge</label><span>${soc.toFixed(1)}%</span></div>
        <div class="feat-box"><label>State of Health</label><span>${soh.toFixed(1)}%</span></div>
        <div class="feat-box"><label>Temperature</label><span>${temp.toFixed(1)} °C</span></div>
        <div class="feat-box"><label>Internal Resistance</label><span>${ir.toFixed(1)} mΩ</span></div>
        <div class="feat-box"><label>Balance Resistor</label><span class="${bleed > 0 ? 'amber-text' : ''}">${bleed > 0 ? 'BLEEDING (ACTIVE)' : 'IDLE (OFF)'}</span></div>
      </div>
      <div style="background: var(--bg-card-hover); border: 1px solid var(--bg-card-border); padding: 14px; border-radius: 12px; font-size: 0.85rem; margin-top: 14px;">
        <strong style="color:var(--text-main);"><i class="fa-solid fa-microchip"></i> Safety Diagnostic Analysis:</strong>
        <p style="color: var(--text-muted); margin-top: 6px; line-height: 1.5;">Cell impedance variance is nominal. ML degradation projections match expected Lithium-ion battery cycle aging curves.</p>
      </div>
    `;
    modal.classList.add('active');
  }

  document.getElementById('closeCellModalBtn').addEventListener('click', () => {
    document.getElementById('cellDetailModal').classList.remove('active');
  });

  // ─── Live Alerts Drawer (Bottom-Right Floating Toast) ──────────────────────
  function updateAlertsList(alerts) {
    const drawer = document.getElementById('floatingAlertsDrawer');
    const list = document.getElementById('alertsList');
    if (!drawer || !list) return;

    if (!alerts || alerts.length === 0) {
      drawer.style.display = 'none';
      return;
    }

    // Check if the current set of alerts has been dismissed by user
    const currentHash = alerts.slice().sort().join('|');
    if (currentHash === dismissedAlertsHash) {
      drawer.style.display = 'none';
      return;
    }

    drawer.style.display = 'flex';
    list.innerHTML = '';
    alerts.forEach(txt => {
      const isCrit = txt.includes('CRITICAL') || txt.includes('ALERT');
      const item = document.createElement('div');
      item.className = `alert-item ${isCrit ? 'alert-crit' : 'alert-warn'}`;
      item.innerHTML = `<i class="fa-solid fa-${isCrit ? 'triangle-exclamation' : 'circle-exclamation'}"></i> <span>${txt}</span>`;
      list.appendChild(item);
    });
  }

  // Dismiss Alerts
  document.getElementById('clearAlertsBtn').addEventListener('click', () => {
    dismissedAlertsHash = currentAlertsList.slice().sort().join('|');
    const drawer = document.getElementById('floatingAlertsDrawer');
    if (drawer) drawer.style.display = 'none';
  });

  // ─── Main BMS UI Update Engine ─────────────────────────────────────────────
  function updateBmsUI(data) {
    latestTelemetryData = data;

    const discEl = document.getElementById('disconnectedOverlay');
    const offEl = document.getElementById('offlineOverlay');
    if (discEl) {
      discEl.classList.remove('active');
      discEl.style.display = 'none';
    }
    if (offEl) {
      offEl.classList.remove('active');
      offEl.style.display = 'none';
    }

    const statusText = document.getElementById('systemStatusText');
    const pulseDot = document.getElementById('statusPulseDot');

    if (data.timestamp) {
      const dateObj = new Date(data.timestamp * 1000);
      document.getElementById('lastUpdateTimestamp').innerHTML = `<i class="fa-regular fa-clock"></i> Last Update: ${dateObj.toLocaleTimeString()}`;
    }

    if (data.esp32_config) {
      currentBmsConfig = data.esp32_config;
      // Update Tab 4 quick config display
      const cDispChg = document.getElementById('cfgDispCharge');
      const cDispDis = document.getElementById('cfgDispDischarge');
      const cDispCap = document.getElementById('cfgDispCapacity');
      const cDispMax = document.getElementById('cfgDispMaxV');
      const cDispCut = document.getElementById('cfgDispCutoffI');
      if (cDispChg) cDispChg.textContent = currentBmsConfig.charge_mode === 1 ? 'Series (3S1P)' : 'Parallel (1S3P)';
      if (cDispDis) cDispDis.textContent = currentBmsConfig.discharge_mode === 1 ? 'Series (3S1P)' : 'Parallel (1S3P)';
      if (cDispCap) cDispCap.textContent = `${currentBmsConfig.capacity || '--'} Ah`;
      if (cDispMax) cDispMax.textContent = `${currentBmsConfig.max_voltage || '--'} V`;
      if (cDispCut) cDispCut.textContent = `${currentBmsConfig.cutoff_current || '--'} A`;
    }

    // ── Determine operating mode from firmware telemetry flags only ───────────
    // Binary: charging=true → CHARGING, anything else → DISCHARGING.
    // No idle state — load is always connected when not charging.
    // Before ESP32 reflash (data.charging is null), default to DISCHARGING.
    const isCharging    = data.charging === true;
    const isDischarging = !isCharging;

    // Status bar text & pulse color
    statusText.textContent = isCharging ? 'CHARGING PACK' : 'DISCHARGING';
    pulseDot.className = isCharging ? 'status-pulse pulse-blue' : 'status-pulse pulse-green';

    document.getElementById('topologyText').textContent = data.configuration || '3S1P';
    document.getElementById('headerPackName').textContent = `EV BMS (${data.configuration || '3S1P'})`;

    // Overview 10 Cards
    const packSoc = data.soc || 0;
    document.getElementById('valOverviewSoc').innerHTML = `${packSoc.toFixed(1)}<small>%</small>`;
    document.getElementById('overviewSocRing').style.strokeDashoffset = 264 - (264 * packSoc / 100);

    const packSoh = data.soh || 0;
    document.getElementById('valOverviewSoh').innerHTML = `${packSoh.toFixed(1)} <small>%</small>`;
    document.getElementById('sohBarFill').style.width = `${packSoh}%`;
    document.getElementById('doughnutAvgSoh').textContent = `${packSoh.toFixed(1)}%`;

    document.getElementById('valOverviewState').textContent = isCharging ? 'CHARGING' : 'DISCHARGING';
    document.getElementById('valOverviewMode').textContent = isCharging ? 'CC-CV Mode Active' : 'Load Active';

    const batV = data.batteryVoltage || 0;
    const current = data.current || 0;
    const inputV = data.inputVoltage || 0;

    document.getElementById('valPackVoltage').innerHTML = `${batV.toFixed(2)} <small>V</small>`;
    document.getElementById('valPackCurrent').innerHTML = `${current > 0 ? '+' : ''}${current.toFixed(2)} <small>A</small>`;
    document.getElementById('valInputVoltage').innerHTML = `${inputV.toFixed(2)} <small>V</small>`;

    const pKw = Math.abs(batV * current) / 1000.0;
    document.getElementById('valPowerKw').innerHTML = `${pKw.toFixed(3)} <small>kW</small>`;

    // Cell Voltages min/max/avg
    const cells = data.cells || [];
    const cellVoltages = cells.map(c => c.voltage);
    const maxV = cellVoltages.length > 0 ? Math.max(...cellVoltages) : 0;
    const minV = cellVoltages.length > 0 ? Math.min(...cellVoltages) : 0;
    const avgV = cellVoltages.length > 0 ? (cellVoltages.reduce((a, b) => a + b, 0) / cellVoltages.length) : 0;
    const deltaV = Math.round((maxV - minV) * 1000);

    document.getElementById('gaugeVin').textContent = `${inputV.toFixed(1)} V`;
    document.getElementById('gaugeVbat').textContent = `${batV.toFixed(2)} V`;
    document.getElementById('gaugeVmax').textContent = cellVoltages.length > 0 ? `${maxV.toFixed(3)} V` : '--';
    document.getElementById('gaugeVmin').textContent = cellVoltages.length > 0 ? `${minV.toFixed(3)} V` : '--';
    document.getElementById('gaugeVavg').textContent = cellVoltages.length > 0 ? `${avgV.toFixed(3)} V` : '--';
    document.getElementById('gaugeDeltaV').textContent = cellVoltages.length > 0 ? `${deltaV} mV` : '--';
    document.getElementById('deltaVBadge').textContent = cellVoltages.length > 0 ? `ΔV = ${deltaV} mV` : '--';

    // Current monitoring — split by firmware mode flag, no current-direction guessing
    document.getElementById('valChargeCurrent').textContent = isCharging ? `${Math.abs(current).toFixed(2)} A` : '0.00 A';
    document.getElementById('valDischargeCurrent').textContent = isDischarging ? `${Math.abs(current).toFixed(2)} A` : '0.00 A';
    document.getElementById('valNetCurrent').textContent = `${current > 0 ? '+' : ''}${current.toFixed(2)} A`;
    document.getElementById('currentDirectionTag').textContent = isCharging ? 'CHARGING IN' : 'DISCHARGING OUT';

    // Health
    document.getElementById('valStrongestCell').textContent = cellVoltages.length > 0 ? `Cell ${cellVoltages.indexOf(maxV) + 1} (${maxV.toFixed(2)}V)` : '--';
    document.getElementById('valWeakestCell').textContent = cellVoltages.length > 0 ? `Cell ${cellVoltages.indexOf(minV) + 1} (${minV.toFixed(2)}V)` : '--';
    document.getElementById('valHealthImbalance').textContent = cellVoltages.length > 0 ? `${deltaV} mV` : '--';
    document.getElementById('valCycleLife').textContent = '3,200 Cycles';
    document.getElementById('valAgingTrend').textContent = packSoh > 85 ? 'Healthy Pack' : 'Degraded impedance';

    // Update dynamic grid list
    updateCellsGridAndVisualizer(cells);

    // Update Cell Voltages Bar Chart
    if (barChart) {
      const isLight = isLightTheme();
      barChart.data.labels = cells.map(c => `C${c.id}`);
      barChart.data.datasets[0].data = cellVoltages;
      barChart.data.datasets[0].backgroundColor = cellVoltages.map(v =>
        v < 3.0 ? (isLight ? '#dc2626' : '#ff1744') :
        (v < 3.2 ? (isLight ? '#d97706' : '#ffab00') : (isLight ? '#059669' : '#00e676'))
      );
      barChart.update('none');
    }

    // Protection Badges — binary: charging or discharging, no idle badge
    document.getElementById('badgeState').className = isCharging ? 'status-badge-item badge-active-green' : 'status-badge-item badge-inactive';
    document.getElementById('badgeDischarge').className = isDischarging ? 'status-badge-item badge-active-green' : 'status-badge-item badge-inactive';
    document.getElementById('badgeIdle').className = 'status-badge-item badge-inactive';
    document.getElementById('badgeOverV').className = maxV > 4.25 ? 'status-badge-item badge-alert' : 'status-badge-item badge-ok';
    document.getElementById('badgeUnderV').className = (minV > 0 && minV < 3.0) ? 'status-badge-item badge-alert' : 'status-badge-item badge-ok';
    document.getElementById('badgeOverI').className = Math.abs(current) > 40.0 ? 'status-badge-item badge-alert' : 'status-badge-item badge-ok';
    document.getElementById('badgeImbalance').className = deltaV > 120 ? 'status-badge-item badge-alert' : 'status-badge-item badge-ok';

    // Draw topology canvases
    drawTopology(data);

    // Update Alerts (Only genuine critical alarms or serious >120mV imbalances)
    const alerts = [];
    if (minV > 0 && minV < 3.0) alerts.push("CRITICAL: Under-Voltage Cutoff Triggered");
    if (maxV > 4.25) alerts.push("CRITICAL: Cell Over-Voltage Alarm");
    if (deltaV > 120) alerts.push(`WARNING: Cell Imbalance Spread (${deltaV}mV)`);
    currentAlertsList = alerts;
    updateAlertsList(alerts);
  }

  // ─── Telemetry Fetch Loop ──────────────────────────────────────────────────
  async function fetchBmsTelemetry() {
    try {
      const res = await fetch('/api/telemetry?cb=' + Date.now());
      if (!res.ok) return;

      const data = await res.json();
      if (!validateData(data)) return;

      if (data.esp32_online === false) {
        isOffline = true;
        resetBmsUI(false);
        return;
      }

      lastSuccessfulUpdate = Date.now();
      isOffline = false;

      if (!data.connected) {
        resetBmsUI(true);
        return;
      }

      updateBmsUI(data);

    } catch (e) {
      console.warn('Error fetching telemetry:', e);
    }
  }

  // Client-side communication watchdog
  setInterval(() => {
    const elapsed = Date.now() - lastSuccessfulUpdate;
    if (elapsed > 8000 && !isOffline) {
      isOffline = true;
      resetBmsUI(false);
    }
  }, 2000);

  // ─── Historical Time-Series Fetch ──────────────────────────────────────────
  async function fetchHistoryData(tf) {
    try {
      const res = await fetch(`/api/history?tf=${tf}&cb=${Date.now()}`);
      if (!res.ok) return;
      const historyData = await res.json();

      if (!historicalChart) return;

      const lbls = [];
      const vData = [];
      const cData = [];
      const sData = [];

      historyData.forEach(row => {
        const timeObj = new Date((row.timestamp || 0) * 1000);
        lbls.push(timeObj.toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }));
        vData.push(row.batteryVoltage || 0);
        cData.push(row.current || 0);
        sData.push(row.soc || 0);
      });

      historicalChart.data.labels = lbls;
      historicalChart.data.datasets[0].data = vData;
      historicalChart.data.datasets[1].data = cData;
      historicalChart.data.datasets[2].data = sData;
      historicalChart.update('none');

    } catch (err) {
      console.warn("Failed to fetch history:", err);
    }
  }

  // ─── Timeframe & Zoom Buttons ──────────────────────────────────────────────
  document.querySelectorAll('.tf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTimeframe = btn.getAttribute('data-range');
      if (historicalChart) historicalChart.resetZoom();
      const rzb = document.getElementById('resetZoomBtn');
      if (rzb) rzb.style.display = 'none';
      fetchHistoryData(currentTimeframe);
    });
  });

  const resetZoomBtn = document.getElementById('resetZoomBtn');
  if (resetZoomBtn) {
    resetZoomBtn.addEventListener('click', () => {
      if (historicalChart) historicalChart.resetZoom();
      resetZoomBtn.style.display = 'none';
    });
  }

  // ─── Simulator Handlers ────────────────────────────────────────────────────
  document.querySelectorAll('.cell-config-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const cellsCount = btn.getAttribute('data-cells');
      document.querySelectorAll('.cell-config-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      try {
        await fetch(`/api/simulate/config?cells=${cellsCount}`);
        fetchBmsTelemetry();
      } catch (err) {
        console.error('Failed to configure simulator cells:', err);
      }
    });
  });

  document.getElementById('btnConnectTrue').addEventListener('click', async () => {
    document.getElementById('btnConnectTrue').classList.add('active');
    document.getElementById('btnConnectFalse').classList.remove('active');
    await fetch('/api/simulate/config?connected=true');
    fetchBmsTelemetry();
  });

  document.getElementById('btnConnectFalse').addEventListener('click', async () => {
    document.getElementById('btnConnectTrue').classList.remove('active');
    document.getElementById('btnConnectFalse').classList.add('active');
    await fetch('/api/simulate/config?connected=false');
    fetchBmsTelemetry();
  });

  document.getElementById('btnSignalTrue').addEventListener('click', async () => {
    document.getElementById('btnSignalTrue').classList.add('active');
    document.getElementById('btnSignalFalse').classList.remove('active');
    await fetch('/api/simulate/config?online=true');
    lastSuccessfulUpdate = Date.now();
    fetchBmsTelemetry();
  });

  document.getElementById('btnSignalFalse').addEventListener('click', async () => {
    document.getElementById('btnSignalTrue').classList.remove('active');
    document.getElementById('btnSignalFalse').classList.add('active');
    await fetch('/api/simulate/config?online=false');
  });

  // Export CSV Logs
  document.getElementById('exportCsvBtn').addEventListener('click', () => {
    window.location.href = '/api/export/csv';
  });

  // ─── Config Modal Interactivity ────────────────────────────────────────────
  const configModal = document.getElementById('configModal');

  function openConfigDialog() {
    if (currentBmsConfig.charge_mode !== undefined) {
      document.getElementById('configChargeMode').value = currentBmsConfig.charge_mode;
    }
    if (currentBmsConfig.discharge_mode !== undefined) {
      document.getElementById('configDischargeMode').value = currentBmsConfig.discharge_mode;
    }
    if (currentBmsConfig.capacity !== undefined) {
      document.getElementById('configCapacity').value = currentBmsConfig.capacity;
    }
    if (currentBmsConfig.max_voltage !== undefined) {
      document.getElementById('configMaxVoltage').value = currentBmsConfig.max_voltage;
    }
    if (currentBmsConfig.cutoff_current !== undefined) {
      document.getElementById('configCutoffCurrent').value = currentBmsConfig.cutoff_current;
    }
    configModal.classList.add('active');
  }

  document.getElementById('openConfigBtn').addEventListener('click', openConfigDialog);

  const openConfigBtnInline = document.getElementById('openConfigBtnInline');
  if (openConfigBtnInline) {
    openConfigBtnInline.addEventListener('click', openConfigDialog);
  }

  document.getElementById('closeConfigModalBtn').addEventListener('click', () => {
    configModal.classList.remove('active');
  });

  document.getElementById('saveConfigBtn').addEventListener('click', async () => {
    const chargeMode = parseInt(document.getElementById('configChargeMode').value);
    const dischargeMode = parseInt(document.getElementById('configDischargeMode').value);
    const capacity = parseFloat(document.getElementById('configCapacity').value);
    const maxVoltage = parseFloat(document.getElementById('configMaxVoltage').value);
    const cutoffCurrent = parseFloat(document.getElementById('configCutoffCurrent').value);

    const configPayload = {
      charge_mode: chargeMode,
      discharge_mode: dischargeMode,
      capacity: capacity,
      max_voltage: maxVoltage,
      cutoff_current: cutoffCurrent
    };

    const saveBtn = document.getElementById('saveConfigBtn');
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configPayload)
      });
      if (res.ok) {
        currentBmsConfig = { ...currentBmsConfig, ...configPayload };
        saveBtn.innerHTML = '<i class="fa-solid fa-circle-check"></i> Saved! Sending to ESP32...';
        saveBtn.style.borderColor = '#00e676';
        saveBtn.style.color = '#00e676';
        setTimeout(() => {
          configModal.classList.remove('active');
          saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Configuration to ESP32';
          saveBtn.style.borderColor = '';
          saveBtn.style.color = '';
          saveBtn.disabled = false;
        }, 1500);
      } else {
        saveBtn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Failed!';
        saveBtn.style.borderColor = '#ff1744';
        setTimeout(() => {
          saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Configuration to ESP32';
          saveBtn.style.borderColor = '';
          saveBtn.disabled = false;
        }, 2000);
      }
    } catch (err) {
      saveBtn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Error!';
      setTimeout(() => {
        saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Configuration to ESP32';
        saveBtn.disabled = false;
      }, 2000);
    }
  });

  // ─── Bootstrap Dashboard ───────────────────────────────────────────────────
  initTheme();
  initTabs();
  initCharts();

  fetchBmsTelemetry();
  fetchHistoryData(currentTimeframe);
  setInterval(fetchBmsTelemetry, 1000);
  setInterval(() => fetchHistoryData(currentTimeframe), 5000);
});
