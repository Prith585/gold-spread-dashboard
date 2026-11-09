/**
 * MCX Gold Futures Spread & Percentage Terminal
 * - Calendar Spread: Next Month Future Close - Current Month Future Close
 * - Cross-Contract Spread: Inter-Commodity Spread (GOLDM, GOLDPETAL, GOLDGUINEA)
 * - Official MCXCCL Accredited Vault Deliverable Stock Position (Inventory)
 */

document.addEventListener('DOMContentLoaded', () => {
    // State
    let appMode = 'calendar';    // 'calendar' (Month-to-Month) or 'cross' (Inter-Commodity)
    let currentSymbol = 'GOLDM'; // 'GOLDM', 'GOLDPETAL', 'GOLDGUINEA', 'GOLD'
    let currentMode = 'rolling';  // 'rolling', 'pair', or 'cross'
    let currentView = 'points';   // 'points', 'percentage', 'dual', 'underlying', 'inventory'
    let selectedPairInfo = null;
    let currentSpreadPayload = null;
    let allDailyRows = [];
    let monthlyPairsList = [];
    let crossMonthlyList = [];

    // Cross-contract state
    let crossSym1 = 'GOLDM';
    let crossSym2 = 'GOLDPETAL';
    let crossFormula = 'leg1_minus_leg2';
    let crossBasis = '10g';       // '10g', '1g', 'raw'

    // Sorting state
    let dailySortOrder = 'asc';   // 'asc' (Oldest to Newest, 01/09/2025 -> Current) or 'desc' (Newest to Oldest)
    let dailySortCol = 'date';    // 'date', 'spread', 'spread_pct', 'inventory_qty'
    let pairsSortOrder = 'asc';   // 'asc' or 'desc'

    // DOM Elements
    const tabModeCalendar = document.getElementById('tabModeCalendar');
    const tabModeCross = document.getElementById('tabModeCross');
    const crossBasisContainer = document.getElementById('crossBasisContainer');
    const selectCrossBasis = document.getElementById('selectCrossBasis');
    const crossPairBar = document.getElementById('crossPairBar');
    const calendarCommodityBar = document.getElementById('calendarCommodityBar');
    const btnCrossPairs = document.querySelectorAll('.btn-cross-pair');
    const labelFormulaTop = document.getElementById('labelFormulaTop');

    const btnCommodities = document.querySelectorAll('.btn-commodity');
    const headerDbStatus = document.getElementById('headerDbStatus');
    const btnSyncMcx = document.getElementById('btnSyncMcx');
    const syncIcon = document.getElementById('syncIcon');
    const chartLoadingOverlay = document.getElementById('chartLoadingOverlay');

    const monthlyPairsBody = document.getElementById('monthlyPairsBody');
    const badgePairsCount = document.getElementById('badgePairsCount');
    const btnViewAllRolling = document.getElementById('btnViewAllRolling');
    const btnSortPairs = document.getElementById('btnSortPairs');
    const pairsSortLabel = document.getElementById('pairsSortLabel');

    const activeChartTitle = document.getElementById('activeChartTitle');
    const activePairBadge = document.getElementById('activePairBadge');

    const chartViewTabs = document.querySelectorAll('#chartViewTabs .chart-tab');
    const timeframeBtns = document.querySelectorAll('.btn-timeframe');
    const btnZoomIn = document.getElementById('btnZoomIn');
    const btnZoomOut = document.getElementById('btnZoomOut');
    const btnResetZoom = document.getElementById('btnResetZoom');

    const sectionDailyTable = document.getElementById('sectionDailyTable');
    const badgeRowCount = document.getElementById('badgeRowCount');
    const selectDailyPair = document.getElementById('selectDailyPair');
    const btnToggleSort = document.getElementById('btnToggleSort');
    const sortOrderLabel = document.getElementById('sortOrderLabel');
    const sortIcon = document.getElementById('sortIcon');
    const bannerPairName = document.getElementById('bannerPairName');
    const bannerDateRange = document.getElementById('bannerDateRange');
    const dailyTableBody = document.getElementById('dailyTableBody');
    const inpTableSearch = document.getElementById('inpTableSearch');
    const btnExportCsv = document.getElementById('btnExportCsv');

    const thLeg1 = document.getElementById('thLeg1');
    const thClose1 = document.getElementById('thClose1');
    const thLeg2 = document.getElementById('thLeg2');
    const thClose2 = document.getElementById('thClose2');

    // Mode Switcher: Calendar vs Cross-Contract
    if (tabModeCalendar && tabModeCross) {
        tabModeCalendar.addEventListener('click', () => {
            if (appMode === 'calendar') return;
            appMode = 'calendar';
            tabModeCalendar.classList.add('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
            tabModeCalendar.classList.remove('bg-slate-950', 'text-slate-300', 'border-slate-800');
            tabModeCross.classList.remove('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
            tabModeCross.classList.add('bg-slate-950', 'text-slate-300', 'border-slate-800');

            calendarCommodityBar.classList.remove('hidden');
            crossPairBar.classList.add('hidden');
            crossBasisContainer.classList.add('hidden');

            if (labelFormulaTop) {
                labelFormulaTop.innerHTML = 'Next Month Close &minus; Current Month Close = Spread (₹)';
            }
            if (thLeg1) thLeg1.textContent = 'Near Month Contract';
            if (thClose1) thClose1.textContent = 'Near Close (₹)';
            if (thLeg2) thLeg2.textContent = 'Next Month Contract';
            if (thClose2) thClose2.textContent = 'Next Close (₹)';

            currentMode = 'rolling';
            selectedPairInfo = null;
            loadMonthlyPairs();
            loadSpreadSeries();
            loadLiveSpreads();
        });

        tabModeCross.addEventListener('click', () => {
            if (appMode === 'cross') return;
            appMode = 'cross';
            tabModeCross.classList.add('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
            tabModeCross.classList.remove('bg-slate-950', 'text-slate-300', 'border-slate-800');
            tabModeCalendar.classList.remove('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
            tabModeCalendar.classList.add('bg-slate-950', 'text-slate-300', 'border-slate-800');

            calendarCommodityBar.classList.add('hidden');
            crossPairBar.classList.remove('hidden');
            crossBasisContainer.classList.remove('hidden');

            updateCrossHeaders();
            currentMode = 'cross';
            selectedPairInfo = null;
            loadCrossMonthlySummary();
            loadSpreadSeries();
            loadLiveSpreads();
        });
    }

    function updateCrossHeaders() {
        const basisLabel = crossBasis === '10g' ? '₹ / 10g' : (crossBasis === '1g' ? '₹ / 1g' : 'Quoted');
        if (labelFormulaTop) {
            labelFormulaTop.innerHTML = `${crossSym1} (${basisLabel}) &minus; ${crossSym2} (${basisLabel}) = Net Spread & %`;
        }
        if (thLeg1) thLeg1.textContent = `${crossSym1} Contract`;
        if (thClose1) thClose1.textContent = `${crossSym1} (${basisLabel})`;
        if (thLeg2) thLeg2.textContent = `${crossSym2} Contract`;
        if (thClose2) thClose2.textContent = `${crossSym2} (${basisLabel})`;
    }

    // Cross Pair Button Switchers
    btnCrossPairs.forEach(btn => {
        btn.addEventListener('click', () => {
            btnCrossPairs.forEach(b => {
                b.classList.remove('active', 'bg-amber-500', 'text-slate-950', 'shadow-sm');
                b.classList.add('bg-slate-950', 'text-slate-300', 'border-slate-800');
            });
            btn.classList.add('active', 'bg-amber-500', 'text-slate-950', 'shadow-sm');
            btn.classList.remove('bg-slate-950', 'text-slate-300', 'border-slate-800');

            crossSym1 = btn.getAttribute('data-sym1');
            crossSym2 = btn.getAttribute('data-sym2');
            crossFormula = btn.getAttribute('data-formula') || 'leg1_minus_leg2';

            updateCrossHeaders();
            selectedPairInfo = null;
            loadCrossMonthlySummary();
            loadSpreadSeries();
            loadLiveSpreads();
        });
    });

    // Cross Basis Dropdown Change
    if (selectCrossBasis) {
        selectCrossBasis.addEventListener('change', () => {
            crossBasis = selectCrossBasis.value;
            updateCrossHeaders();
            loadCrossMonthlySummary();
            loadSpreadSeries();
            loadLiveSpreads();
        });
    }

    // Commodity Switcher (Calendar Mode)
    btnCommodities.forEach(btn => {
        btn.addEventListener('click', () => {
            btnCommodities.forEach(b => {
                b.classList.remove('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
                b.classList.add('bg-slate-950', 'text-slate-300', 'border-slate-800');
            });
            btn.classList.add('active', 'bg-amber-500', 'text-slate-950', 'shadow-md', 'shadow-amber-500/20');
            btn.classList.remove('bg-slate-950', 'text-slate-300', 'border-slate-800');

            currentSymbol = btn.getAttribute('data-symbol');
            currentMode = 'rolling';
            selectedPairInfo = null;
            loadMonthlyPairs();
            loadSpreadSeries();
            loadLiveSpreads();
        });
    });

    // View All Continuous 1-Year Button
    if (btnViewAllRolling) {
        btnViewAllRolling.addEventListener('click', () => {
            currentMode = (appMode === 'cross') ? 'cross' : 'rolling';
            selectedPairInfo = null;
            if (selectDailyPair) selectDailyPair.value = (appMode === 'cross') ? 'all' : 'rolling';
            highlightActivePairRow(-1);
            loadSpreadSeries();
            if (sectionDailyTable) sectionDailyTable.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    // Monthly Pairs Sort Toggle
    if (btnSortPairs) {
        btnSortPairs.addEventListener('click', () => {
            pairsSortOrder = (pairsSortOrder === 'asc') ? 'desc' : 'asc';
            if (pairsSortLabel) {
                pairsSortLabel.innerHTML = pairsSortOrder === 'asc' 
                    ? 'Sort: Oldest &rarr; Newest' 
                    : 'Sort: Newest &rarr; Oldest';
            }
            if (appMode === 'cross') {
                renderCrossMonthlyTable(crossMonthlyList);
            } else {
                renderMonthlyPairsTable(monthlyPairsList);
            }
        });
    }

    // Daily Table Pair Selector Dropdown
    if (selectDailyPair) {
        selectDailyPair.addEventListener('change', () => {
            const val = selectDailyPair.value;
            if (appMode === 'cross') {
                if (val === 'all') {
                    selectedPairInfo = null;
                    highlightActivePairRow(-1);
                    loadSpreadSeries();
                } else {
                    const idx = parseInt(val, 10);
                    const m = crossMonthlyList[idx];
                    if (m) {
                        selectedPairInfo = { label: m.month, start_date: m.start_date, end_date: m.end_date };
                        highlightActivePairRow(idx);
                        applySortAndRenderDailyTable();
                    }
                }
            } else {
                if (val === 'rolling') {
                    currentMode = 'rolling';
                    selectedPairInfo = null;
                    highlightActivePairRow(-1);
                    loadSpreadSeries();
                } else {
                    const idx = parseInt(val, 10);
                    const p = monthlyPairsList[idx];
                    if (p) {
                        currentMode = 'pair';
                        selectedPairInfo = p;
                        highlightActivePairRow(idx);
                        loadSpreadSeries();
                    }
                }
            }
        });
    }

    // Daily Table Sort Toggle (Oldest to Newest <-> Newest to Oldest)
    if (btnToggleSort) {
        btnToggleSort.addEventListener('click', () => {
            dailySortOrder = (dailySortOrder === 'asc') ? 'desc' : 'asc';
            dailySortCol = 'date';
            updateSortToggleUI();
            applySortAndRenderDailyTable();
        });
    }

    function updateSortToggleUI() {
        if (!sortOrderLabel) return;
        if (dailySortOrder === 'asc') {
            sortOrderLabel.innerHTML = 'Sort: Oldest &rarr; Newest';
            sortIcon.className = 'fa-solid fa-arrow-down-short-wide text-amber-400';
        } else {
            sortOrderLabel.innerHTML = 'Sort: Newest &rarr; Oldest';
            sortIcon.className = 'fa-solid fa-arrow-up-wide-short text-amber-400';
        }
    }

    // Clickable table header sorting
    document.querySelectorAll('#sectionDailyTable th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-col');
            if (dailySortCol === col) {
                dailySortOrder = (dailySortOrder === 'asc') ? 'desc' : 'asc';
            } else {
                dailySortCol = col;
                dailySortOrder = (col === 'date') ? 'asc' : 'desc';
            }
            updateSortToggleUI();
            applySortAndRenderDailyTable();
        });
    });

    // Chart View Tab Switching
    chartViewTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            chartViewTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentView = tab.getAttribute('data-view');
            if (currentSpreadPayload) {
                renderPlotlyChart(currentSpreadPayload);
            }
        });
    });

    // Chart Timeframe Quick Filters
    timeframeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            timeframeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyChartTimeframe(btn.getAttribute('data-range'));
        });
    });

    // Zoom Buttons
    if (btnZoomIn) {
        btnZoomIn.addEventListener('click', () => {
            const graphDiv = document.getElementById('mainSpreadChart');
            if (graphDiv && graphDiv.layout && graphDiv.layout.xaxis) {
                const xRange = graphDiv.layout.xaxis.range;
                if (xRange && xRange.length === 2) {
                    const start = new Date(xRange[0]).getTime();
                    const end = new Date(xRange[1]).getTime();
                    const diff = (end - start) * 0.25;
                    Plotly.relayout('mainSpreadChart', {
                        'xaxis.range': [new Date(start + diff).toISOString().slice(0, 10), new Date(end - diff).toISOString().slice(0, 10)]
                    });
                }
            }
        });
    }

    if (btnZoomOut) {
        btnZoomOut.addEventListener('click', () => {
            const graphDiv = document.getElementById('mainSpreadChart');
            if (graphDiv && graphDiv.layout && graphDiv.layout.xaxis) {
                const xRange = graphDiv.layout.xaxis.range;
                if (xRange && xRange.length === 2) {
                    const start = new Date(xRange[0]).getTime();
                    const end = new Date(xRange[1]).getTime();
                    const diff = (end - start) * 0.33;
                    Plotly.relayout('mainSpreadChart', {
                        'xaxis.range': [new Date(start - diff).toISOString().slice(0, 10), new Date(end + diff).toISOString().slice(0, 10)]
                    });
                }
            }
        });
    }

    if (btnResetZoom) {
        btnResetZoom.addEventListener('click', () => {
            Plotly.relayout('mainSpreadChart', {
                'xaxis.autorange': true,
                'yaxis.autorange': true
            });
        });
    }

    // Load Header Status
    async function loadMeta() {
        try {
            const resp = await fetch('/api/contracts');
            const data = await resp.json();
            if (data.success) {
                headerDbStatus.textContent = `${data.total_rows.toLocaleString()} Bhavcopy Rows | MCX Historical DB`;
            }
        } catch (e) {
            headerDbStatus.textContent = 'MCX Historical DB Connected';
        }
    }

    // Load Consecutive Monthly Pairs Table (Calendar Mode)
    async function loadMonthlyPairs() {
        try {
            const resp = await fetch(`/api/monthly_pairs?symbol=${currentSymbol}&formula=leg2_minus_leg1`);
            const data = await resp.json();
            if (!data.success) throw new Error(data.error || 'Failed to load pairs');

            monthlyPairsList = data.pairs || [];
            badgePairsCount.textContent = `${monthlyPairsList.length} Consecutive Pairs`;
            
            populateDailyPairDropdown(monthlyPairsList);
            renderMonthlyPairsTable(monthlyPairsList);

        } catch (err) {
            console.error('Error loading monthly pairs:', err);
            monthlyPairsBody.innerHTML = `<tr><td colspan="11" class="text-center py-6 text-rose-400">Error loading pairs: ${err.message}</td></tr>`;
        }
    }

    // Populate Daily Data Pair Dropdown (Calendar Mode)
    function populateDailyPairDropdown(pairs) {
        if (!selectDailyPair) return;
        let opts = `<option value="rolling">Full 1-Year Continuous (All 14 Pairs Combined: 01/09/2025 to Current)</option>`;
        pairs.forEach((p, idx) => {
            opts += `<option value="${idx}">${idx + 1}. ${p.label} (${p.near_expiry} - ${p.next_expiry}) [${p.trading_days} Days]</option>`;
        });
        selectDailyPair.innerHTML = opts;
    }

    // Render Monthly Pairs Table (Calendar Mode)
    function renderMonthlyPairsTable(pairs) {
        if (!pairs.length) {
            monthlyPairsBody.innerHTML = `<tr><td colspan="11" class="text-center py-8 text-slate-500 font-sans">No monthly pairs found for ${currentSymbol}.</td></tr>`;
            return;
        }

        const displayList = [...pairs];
        if (pairsSortOrder === 'desc') {
            displayList.reverse();
        }

        let html = '';
        displayList.forEach((p) => {
            const originalIndex = pairs.findIndex(x => x.label === p.label);
            const isLive = Boolean(p.is_live && p.live_spread !== undefined);
            const currentSpread = isLive ? p.live_spread : p.spread;
            const currentPct = isLive ? p.live_spread_pct : p.spread_pct;
            const currentNearClose = isLive ? p.live_near_ltp : p.near_close;
            const currentNextClose = isLive ? p.live_next_ltp : p.next_close;

            const spreadSign = currentSpread >= 0 ? '+' : '';
            const pctSign = currentPct >= 0 ? '+' : '';
            const avgSpreadSign = p.avg_spread >= 0 ? '+' : '';
            const avgPctSign = p.avg_spread_pct >= 0 ? '+' : '';

            const isPositive = currentSpread >= 0;
            const spreadColor = isPositive ? 'text-emerald-400' : 'text-rose-400';
            const avgColor = p.avg_spread >= 0 ? 'text-emerald-400' : 'text-rose-400';

            const liveBadge = isLive 
                ? `<span class="ml-1.5 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold inline-flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>LIVE</span>` 
                : '';
            const nearLtpSub = isLive ? `<span class="block text-[9px] text-emerald-400 font-sans">Live LTP</span>` : '';
            const nextLtpSub = isLive ? `<span class="block text-[9px] text-emerald-400 font-sans">Live LTP</span>` : '';

            const isActive = selectedPairInfo && selectedPairInfo.label === p.label;
            const rowClass = isActive 
                ? 'bg-amber-500/20 ring-1 ring-amber-500/50 hover:bg-amber-500/25' 
                : (isLive ? 'bg-emerald-950/20 hover:bg-emerald-950/30' : 'hover:bg-slate-800/40');

            html += `
                <tr id="pairRow-${originalIndex}" class="${rowClass} cursor-pointer transition pair-row" onclick="window.viewPairFromTable(event, ${originalIndex})">
                    <td class="py-2.5 px-3 font-semibold text-slate-100 flex items-center gap-1.5">
                        <i class="fa-regular fa-calendar text-amber-400 text-xs"></i>
                        <span>${p.label}</span>
                        ${liveBadge}
                    </td>
                    <td class="py-2.5 px-3 text-sky-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/20">${p.near_expiry}</span>
                    </td>
                    <td class="py-2.5 px-3 text-right text-slate-200">
                        <span>₹${currentNearClose.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
                        ${nearLtpSub}
                    </td>
                    <td class="py-2.5 px-3 text-fuchsia-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/20">${p.next_expiry}</span>
                    </td>
                    <td class="py-2.5 px-3 text-right text-slate-200">
                        <span>₹${currentNextClose.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
                        ${nextLtpSub}
                    </td>
                    <td class="py-2.5 px-3 text-right font-bold ${spreadColor}">${spreadSign}₹${currentSpread.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td class="py-2.5 px-3 text-right font-bold ${spreadColor}">${pctSign}${currentPct.toFixed(2)}%</td>
                    <td class="py-2.5 px-3 text-right ${avgColor}">${avgSpreadSign}₹${p.avg_spread.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td class="py-2.5 px-3 text-right ${avgColor}">${avgPctSign}${p.avg_spread_pct.toFixed(2)}%</td>
                    <td class="py-2.5 px-3 text-center text-slate-300 font-semibold">${p.trading_days}d</td>
                    <td class="py-2.5 px-3 text-center" onclick="event.stopPropagation()">
                        <button onclick="window.viewPairFromTable(event, ${originalIndex})" title="View daily spread data and chart for ${p.label}" class="btn-select-pair px-3 py-1 bg-amber-500/15 hover:bg-amber-500 text-amber-300 hover:text-slate-950 border border-amber-500/30 rounded text-[11px] font-bold transition flex items-center gap-1.5 mx-auto shadow-sm">
                            <i class="fa-solid fa-chart-line text-[10px]"></i> View
                        </button>
                    </td>
                </tr>
            `;
        });

        monthlyPairsBody.innerHTML = html;
    }

    // Load Cross Monthly Summary (Cross Mode)
    async function loadCrossMonthlySummary() {
        try {
            const resp = await fetch(`/api/cross_commodity_monthly?leg1_symbol=${crossSym1}&leg2_symbol=${crossSym2}&basis=${crossBasis}&formula=${crossFormula}`);
            const data = await resp.json();
            if (!data.success) throw new Error(data.error || 'Failed to load cross summary');

            crossMonthlyList = data.months || [];
            badgePairsCount.textContent = `${crossMonthlyList.length} Monthly Cycles`;

            populateCrossPairDropdown(crossMonthlyList);
            renderCrossMonthlyTable(crossMonthlyList);

        } catch (err) {
            console.error('Error loading cross monthly summary:', err);
            monthlyPairsBody.innerHTML = `<tr><td colspan="11" class="text-center py-6 text-rose-400">Error loading cross pairs: ${err.message}</td></tr>`;
        }
    }

    // Populate Dropdown (Cross Mode)
    function populateCrossPairDropdown(months) {
        if (!selectDailyPair) return;
        const basisLabel = crossBasis === '10g' ? '₹ / 10g' : (crossBasis === '1g' ? '₹ / 1g' : 'Quoted');
        let opts = `<option value="all">Full 1-Year Continuous (${crossSym1} vs ${crossSym2}: 01/09/2025 to Current)</option>`;
        months.forEach((m, idx) => {
            opts += `<option value="${idx}">${idx + 1}. ${m.month} (${m.leg1_expiry} vs ${m.leg2_expiry}) [${m.trading_days} Days]</option>`;
        });
        selectDailyPair.innerHTML = opts;
    }

    // Render Cross Monthly Table (Cross Mode)
    function renderCrossMonthlyTable(months) {
        if (!months.length) {
            monthlyPairsBody.innerHTML = `<tr><td colspan="11" class="text-center py-8 text-slate-500 font-sans">No cross data found for ${crossSym1} vs ${crossSym2}.</td></tr>`;
            return;
        }

        const displayList = [...months];
        if (pairsSortOrder === 'desc') {
            displayList.reverse();
        }

        let html = '';
        displayList.forEach((m) => {
            const originalIndex = months.findIndex(x => x.month === m.month);
            const isLive = Boolean(m.is_live && m.live_spread !== undefined);
            const currentSpread = isLive ? m.live_spread : m.latest_spread;
            const currentPct = isLive ? m.live_spread_pct : m.latest_spread_pct;
            const currentP1 = isLive ? m.live_p1 : m.norm_p1;
            const currentP2 = isLive ? m.live_p2 : m.norm_p2;

            const spreadSign = currentSpread >= 0 ? '+' : '';
            const pctSign = currentPct >= 0 ? '+' : '';
            const avgSpreadSign = m.avg_spread >= 0 ? '+' : '';
            const avgPctSign = m.avg_spread_pct >= 0 ? '+' : '';

            const isPositive = currentSpread >= 0;
            const spreadColor = isPositive ? 'text-emerald-400' : 'text-rose-400';
            const avgColor = m.avg_spread >= 0 ? 'text-emerald-400' : 'text-rose-400';

            const liveBadge = isLive 
                ? `<span class="ml-1.5 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold inline-flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>LIVE</span>` 
                : '';
            const p1Sub = isLive ? `<span class="block text-[9px] text-emerald-400 font-sans">Live LTP</span>` : '';
            const p2Sub = isLive ? `<span class="block text-[9px] text-emerald-400 font-sans">Live LTP</span>` : '';

            const isActive = selectedPairInfo && selectedPairInfo.label === m.month;
            const rowClass = isActive 
                ? 'bg-amber-500/20 ring-1 ring-amber-500/50 hover:bg-amber-500/25' 
                : (isLive ? 'bg-emerald-950/20 hover:bg-emerald-950/30' : 'hover:bg-slate-800/40');

            html += `
                <tr id="pairRow-${originalIndex}" class="${rowClass} cursor-pointer transition pair-row" onclick="window.viewPairFromTable(event, ${originalIndex})">
                    <td class="py-2.5 px-3 font-semibold text-slate-100 flex items-center gap-1.5">
                        <i class="fa-solid fa-shuffle text-amber-400 text-xs"></i>
                        <span>${m.month}</span>
                        ${liveBadge}
                    </td>
                    <td class="py-2.5 px-3 text-sky-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/20">${m.leg1_expiry}</span>
                    </td>
                    <td class="py-2.5 px-3 text-right text-slate-200">
                        <span>₹${currentP1.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
                        ${p1Sub}
                    </td>
                    <td class="py-2.5 px-3 text-fuchsia-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/20">${m.leg2_expiry}</span>
                    </td>
                    <td class="py-2.5 px-3 text-right text-slate-200">
                        <span>₹${currentP2.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
                        ${p2Sub}
                    </td>
                    <td class="py-2.5 px-3 text-right font-bold ${spreadColor}">${spreadSign}₹${currentSpread.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td class="py-2.5 px-3 text-right font-bold ${spreadColor}">${pctSign}${currentPct.toFixed(2)}%</td>
                    <td class="py-2.5 px-3 text-right ${avgColor}">${avgSpreadSign}₹${m.avg_spread.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td class="py-2.5 px-3 text-right ${avgColor}">${avgPctSign}${m.avg_spread_pct.toFixed(2)}%</td>
                    <td class="py-2.5 px-3 text-center text-slate-300 font-semibold">${m.trading_days}d</td>
                    <td class="py-2.5 px-3 text-center" onclick="event.stopPropagation()">
                        <button onclick="window.viewPairFromTable(event, ${originalIndex})" title="View daily data and chart for ${m.month}" class="btn-select-pair px-3 py-1 bg-amber-500/15 hover:bg-amber-500 text-amber-300 hover:text-slate-950 border border-amber-500/30 rounded text-[11px] font-bold transition flex items-center gap-1.5 mx-auto shadow-sm">
                            <i class="fa-solid fa-chart-line text-[10px]"></i> View
                        </button>
                    </td>
                </tr>
            `;
        });

        monthlyPairsBody.innerHTML = html;
    }

    // Global View Action Handler attached to window
    window.viewPairFromTable = function(event, idx) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        if (appMode === 'cross') {
            const m = crossMonthlyList[idx];
            if (!m) return;
            selectedPairInfo = { label: m.month, start_date: m.start_date, end_date: m.end_date };
            highlightActivePairRow(idx);
            if (selectDailyPair) selectDailyPair.value = idx.toString();
            applySortAndRenderDailyTable();
        } else {
            const p = monthlyPairsList[idx];
            if (!p) return;
            currentMode = 'pair';
            selectedPairInfo = p;
            highlightActivePairRow(idx);
            if (selectDailyPair) selectDailyPair.value = idx.toString();
            loadSpreadSeries();
        }

        setTimeout(() => {
            if (sectionDailyTable) {
                sectionDailyTable.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }, 100);
    };

    function highlightActivePairRow(activeIdx) {
        document.querySelectorAll('.pair-row').forEach(r => {
            r.classList.remove('bg-amber-500/20', 'ring-1', 'ring-amber-500/50');
            r.classList.add('hover:bg-slate-800/40');
        });
        if (activeIdx >= 0) {
            const activeRow = document.getElementById(`pairRow-${activeIdx}`);
            if (activeRow) {
                activeRow.classList.add('bg-amber-500/20', 'ring-1', 'ring-amber-500/50');
                activeRow.classList.remove('hover:bg-slate-800/40');
            }
        }
    }

    // Load Spread Time Series (for Chart & Daily Table)
    async function loadSpreadSeries() {
        chartLoadingOverlay.classList.remove('hidden');

        let payload = {};

        if (appMode === 'cross') {
            payload = {
                mode: 'cross',
                leg1_symbol: crossSym1,
                leg2_symbol: crossSym2,
                basis: crossBasis,
                formula: crossFormula
            };

            const basisLabel = crossBasis === '10g' ? '₹ / 10g' : (crossBasis === '1g' ? '₹ / 1g' : 'Quoted');
            activeChartTitle.textContent = `${crossSym1} vs ${crossSym2} Cross Spread (${basisLabel})`;
            activePairBadge.textContent = `${crossSym1} &minus; ${crossSym2}`;

            if (bannerPairName) {
                bannerPairName.textContent = `${crossSym1} vs ${crossSym2} Inter-Commodity Spread (${basisLabel})`;
            }
        } else {
            payload = {
                symbol: currentSymbol,
                formula: 'leg2_minus_leg1'
            };

            if (currentMode === 'pair' && selectedPairInfo) {
                payload.mode = 'pair';
                payload.leg1_symbol = currentSymbol;
                payload.leg1_expiry = selectedPairInfo.near_expiry;
                payload.leg2_symbol = currentSymbol;
                payload.leg2_expiry = selectedPairInfo.next_expiry;

                activeChartTitle.textContent = `${currentSymbol} ${selectedPairInfo.label} Daily Spread`;
                activePairBadge.textContent = `${selectedPairInfo.next_expiry} &minus; ${selectedPairInfo.near_expiry}`;
                
                if (bannerPairName) {
                    bannerPairName.textContent = `${currentSymbol} ${selectedPairInfo.label} (${selectedPairInfo.near_expiry} - ${selectedPairInfo.next_expiry})`;
                }
            } else {
                payload.mode = 'rolling';
                payload.roll_days = 5;

                activeChartTitle.textContent = `${currentSymbol} Continuous 1-Year Spread (All 14 Pairs)`;
                activePairBadge.textContent = 'Next Month Future &minus; Current Month Future';

                if (bannerPairName) {
                    bannerPairName.textContent = `Full 1-Year Continuous Spread (All 14 Pairs Combined)`;
                }
            }
        }

        try {
            const resp = await fetch('/api/spread_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.error || 'Failed to fetch spread');

            currentSpreadPayload = data;
            allDailyRows = data.table_rows || [];

            if (bannerDateRange && data.dates && data.dates.length) {
                const firstD = data.dates[0];
                const lastD = data.dates[data.dates.length - 1];
                bannerDateRange.textContent = `(${firstD} to ${lastD} &bull; ${data.dates.length} Trading Days)`;
            }

            renderPlotlyChart(data);
            applySortAndRenderDailyTable();

        } catch (err) {
            alert('Error loading spread series: ' + err.message);
            console.error(err);
        } finally {
            chartLoadingOverlay.classList.add('hidden');
        }
    }

    // Render Clean Presentable Plotly Chart (No EMA, No Bollinger bands)
    function renderPlotlyChart(data) {
        const dates = data.dates;
        const traces = [];

        const layout = {
            plot_bgcolor: '#090d16',
            paper_bgcolor: '#0f172a',
            font: { color: '#94a3b8', family: 'ui-sans-serif, system-ui, -apple-system, sans-serif', size: 12 },
            margin: { t: 40, r: 40, b: 50, l: 65 },
            xaxis: {
                gridcolor: '#1e293b',
                zerolinecolor: '#334155',
                showline: true,
                linecolor: '#334155',
                tickformat: '%d %b %Y',
                rangeslider: {
                    visible: true,
                    thickness: 0.08,
                    bgcolor: '#090d16',
                    bordercolor: '#1e293b'
                }
            },
            yaxis: {
                gridcolor: '#1e293b',
                zerolinecolor: '#475569',
                zerolinewidth: 1.5,
                showline: true,
                linecolor: '#334155',
                side: 'right',
                title: { text: '', font: { size: 12, color: '#f59e0b' } }
            },
            legend: {
                orientation: 'h',
                yanchor: 'bottom',
                y: 1.03,
                xanchor: 'right',
                x: 1,
                font: { size: 12 }
            },
            hovermode: 'x unified'
        };

        const hoverText = dates.map((d, i) => {
            const exp1 = data.leg1_expiry[i];
            const c1 = data.close_leg1[i];
            const exp2 = data.leg2_expiry[i];
            const c2 = data.close_leg2[i];
            const sp = data.spread[i];
            const pct = data.spread_pct[i];
            const inv = (data.inventory_display && data.inventory_display[i]) ? data.inventory_display[i] : '—';
            const sign = sp >= 0 ? '+' : '';
            const pctSign = pct >= 0 ? '+' : '';
            const l1Label = (appMode === 'cross') ? crossSym1 : 'Current';
            const l2Label = (appMode === 'cross') ? crossSym2 : 'Next';
            return `<b>Date: ${d}</b><br>` +
                   `${l1Label} (${exp1}): ₹${c1?.toLocaleString('en-IN')}<br>` +
                   `${l2Label} (${exp2}): ₹${c2?.toLocaleString('en-IN')}<br>` +
                   `<b>Spread: ${sign}₹${sp?.toLocaleString('en-IN')} (${pctSign}${pct}%)</b><br>` +
                   `<b>MCX Vault Stock: ${inv}</b>`;
        });

        if (currentView === 'points') {
            layout.yaxis.title.text = 'Spread Points (₹)';
            layout.title = { text: `${activeChartTitle.textContent} (Points / ₹)`, font: { color: '#f8fafc', size: 14 } };

            traces.push({
                x: dates,
                y: data.spread,
                text: hoverText,
                hoverinfo: 'text',
                name: 'Spread Points (₹)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#f59e0b', width: 2.5 }
            });

        } else if (currentView === 'percentage') {
            layout.yaxis.title.text = 'Spread Percentage (%)';
            layout.yaxis.ticksuffix = '%';
            layout.title = { text: `${activeChartTitle.textContent} (%)`, font: { color: '#f8fafc', size: 14 } };

            traces.push({
                x: dates,
                y: data.spread_pct,
                text: hoverText,
                hoverinfo: 'text',
                name: 'Spread (%)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#10b981', width: 2.5 }
            });

        } else if (currentView === 'dual') {
            layout.title = { text: `${activeChartTitle.textContent} - Points & Percentage`, font: { color: '#f8fafc', size: 14 } };
            layout.yaxis.title.text = 'Spread (Points ₹)';
            layout.yaxis.side = 'left';
            layout.yaxis2 = {
                title: 'Spread Percentage (%)',
                ticksuffix: '%',
                overlaying: 'y',
                side: 'right',
                gridcolor: 'transparent',
                showline: true,
                linecolor: '#334155',
                font: { color: '#10b981' }
            };

            traces.push({
                x: dates,
                y: data.spread,
                name: 'Spread (Points ₹)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#f59e0b', width: 2 }
            });

            traces.push({
                x: dates,
                y: data.spread_pct,
                yaxis: 'y2',
                name: 'Spread (%)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#10b981', width: 2 }
            });

        } else if (currentView === 'underlying') {
            const l1 = (appMode === 'cross') ? `${crossSym1} Close (₹)` : 'Current Month Close (₹)';
            const l2 = (appMode === 'cross') ? `${crossSym2} Close (₹)` : 'Next Month Close (₹)';
            layout.yaxis.title.text = 'Contract Closing Price (₹)';
            layout.title = { text: `${l1} vs ${l2}`, font: { color: '#f8fafc', size: 14 } };

            traces.push({
                x: dates,
                y: data.close_leg1,
                name: l1,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#38bdf8', width: 2 }
            });

            traces.push({
                x: dates,
                y: data.close_leg2,
                name: l2,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#e879f9', width: 2 }
            });
        } else if (currentView === 'inventory') {
            layout.title = { text: `${activeChartTitle.textContent} - Spread vs MCX Stock Position (Vault Inventory)`, font: { color: '#f8fafc', size: 14 } };
            layout.yaxis.title.text = 'Spread (Points ₹)';
            layout.yaxis.side = 'left';
            layout.yaxis2 = {
                title: `MCX Stock Position (${data.inventory_unit || 'KG'})`,
                overlaying: 'y',
                side: 'right',
                gridcolor: 'transparent',
                showline: true,
                linecolor: '#334155',
                font: { color: '#38bdf8' }
            };

            traces.push({
                x: dates,
                y: data.spread,
                text: hoverText,
                hoverinfo: 'text',
                name: 'Spread (Points ₹)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#f59e0b', width: 2.5 }
            });

            traces.push({
                x: dates,
                y: data.inventory_qty,
                yaxis: 'y2',
                text: dates.map((d, i) => `<b>Date: ${d}</b><br>MCX Vault Stock: <b>${(data.inventory_display && data.inventory_display[i]) || '—'}</b>`),
                hoverinfo: 'text',
                name: `MCX Stock Position (${data.inventory_unit || 'KG'})`,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#38bdf8', width: 2, dash: 'dot' },
                fill: 'tozeroy',
                fillcolor: 'rgba(56, 189, 248, 0.08)'
            });
        }

        const config = {
            responsive: true,
            scrollZoom: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToAdd: ['zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d']
        };

        Plotly.newPlot('mainSpreadChart', traces, layout, config);
    }

    // Apply Timeframe Filter on Chart
    function applyChartTimeframe(rangeType) {
        if (!currentSpreadPayload || !currentSpreadPayload.dates.length) return;
        const dates = currentSpreadPayload.dates;
        const lastDate = new Date(dates[dates.length - 1]);
        let startDate = new Date(dates[0]);

        if (rangeType === '1m') {
            startDate = new Date(lastDate);
            startDate.setMonth(startDate.getMonth() - 1);
        } else if (rangeType === '3m') {
            startDate = new Date(lastDate);
            startDate.setMonth(startDate.getMonth() - 3);
        } else if (rangeType === '6m') {
            startDate = new Date(lastDate);
            startDate.setMonth(startDate.getMonth() - 6);
        } else if (rangeType === '1y') {
            startDate = new Date(lastDate);
            startDate.setFullYear(startDate.getFullYear() - 1);
        }

        Plotly.relayout('mainSpreadChart', {
            'xaxis.range': [startDate.toISOString().slice(0, 10), lastDate.toISOString().slice(0, 10)],
            'xaxis.autorange': rangeType === 'all'
        });
    }

    // Apply Sorting and Render Daily Numbers Table
    function applySortAndRenderDailyTable() {
        if (!allDailyRows || !allDailyRows.length) {
            renderDailyTable([]);
            return;
        }

        let filtered = allDailyRows;

        // Filter by selected pair / month if active
        if (selectedPairInfo) {
            if (selectedPairInfo.start_date && selectedPairInfo.end_date) {
                filtered = filtered.filter(r => r.date >= selectedPairInfo.start_date && r.date <= selectedPairInfo.end_date);
            } else if (selectedPairInfo.label) {
                filtered = filtered.filter(r => (r.pair_label && r.pair_label.includes(selectedPairInfo.label)) || (r.date && r.date.includes(selectedPairInfo.label)));
            }
        }

        const query = inpTableSearch.value.trim().toLowerCase();
        if (query) {
            filtered = filtered.filter(r =>
                r.date.toLowerCase().includes(query) ||
                (r.pair_label && r.pair_label.toLowerCase().includes(query)) ||
                (r.leg1_expiry && r.leg1_expiry.toLowerCase().includes(query)) ||
                (r.leg2_expiry && r.leg2_expiry.toLowerCase().includes(query))
            );
        }

        // Sort rows
        const sorted = [...filtered].sort((a, b) => {
            if (dailySortCol === 'date') {
                return (dailySortOrder === 'asc') 
                    ? a.date.localeCompare(b.date) 
                    : b.date.localeCompare(a.date);
            } else if (dailySortCol === 'spread') {
                return (dailySortOrder === 'asc') ? (a.spread - b.spread) : (b.spread - a.spread);
            } else if (dailySortCol === 'spread_pct') {
                return (dailySortOrder === 'asc') ? (a.spread_pct - b.spread_pct) : (b.spread_pct - a.spread_pct);
            } else if (dailySortCol === 'inventory_qty') {
                const aInv = (a.inventory_qty !== undefined && a.inventory_qty !== null) ? a.inventory_qty : -1;
                const bInv = (b.inventory_qty !== undefined && b.inventory_qty !== null) ? b.inventory_qty : -1;
                return (dailySortOrder === 'asc') ? (aInv - bInv) : (bInv - aInv);
            }
            return 0;
        });

        renderDailyTable(sorted);
    }

    // Render Daily Numbers Table
    function renderDailyTable(rows) {
        badgeRowCount.textContent = `${rows.length} Days`;
        if (!rows.length) {
            dailyTableBody.innerHTML = `<tr><td colspan="10" class="text-center py-8 text-slate-500 font-sans">No daily closing data available for the current filter.</td></tr>`;
            return;
        }

        let html = '';
        rows.forEach(r => {
            const spreadSign = r.spread >= 0 ? '+' : '';
            const pctSign = r.spread_pct >= 0 ? '+' : '';
            const changeSign = r.spread_change >= 0 ? '+' : '';

            const isPos = r.spread >= 0;
            const spreadColor = isPos ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold';
            const changeColor = r.spread_change >= 0 ? 'text-emerald-400' : 'text-rose-400';
            const invHtml = r.inventory 
                ? `<span class="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 font-semibold text-[11px] whitespace-nowrap">${r.inventory}</span>` 
                : `<span class="text-slate-600 text-xs">—</span>`;

            const isLive = Boolean(r.is_live);
            const rowHighlight = isLive 
                ? 'bg-emerald-950/30 hover:bg-emerald-950/40 border-l-2 border-emerald-400 font-semibold' 
                : 'hover:bg-slate-800/40';
            const dateDisplay = isLive 
                ? `<span class="inline-flex items-center gap-1.5 text-emerald-300 font-bold"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>${r.date}</span>` 
                : r.date;
            const c1Display = isLive 
                ? `<span>₹${r.close_leg1.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span><span class="text-[9px] text-emerald-400 block font-sans">Live LTP</span>`
                : `₹${r.close_leg1.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`;
            const c2Display = isLive 
                ? `<span>₹${r.close_leg2.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span><span class="text-[9px] text-emerald-400 block font-sans">Live LTP</span>`
                : `₹${r.close_leg2.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`;

            html += `
                <tr class="${rowHighlight}">
                    <td class="py-2 px-3 text-slate-200 font-semibold">${dateDisplay}</td>
                    <td class="py-2 px-3">
                        <span class="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-amber-300 font-mono text-[11px] whitespace-nowrap font-medium">${r.pair_label || '—'}</span>
                    </td>
                    <td class="py-2 px-3 text-sky-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/20">${r.leg1_expiry}</span>
                    </td>
                    <td class="py-2 px-3 text-right text-slate-200">${c1Display}</td>
                    <td class="py-2 px-3 text-fuchsia-400 font-medium">
                        <span class="px-1.5 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/20">${r.leg2_expiry}</span>
                    </td>
                    <td class="py-2 px-3 text-right text-slate-200">${c2Display}</td>
                    <td class="py-2 px-3 text-right ${spreadColor}">${spreadSign}₹${r.spread.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td class="py-2 px-3 text-right ${spreadColor}">${pctSign}${r.spread_pct.toFixed(2)}%</td>
                    <td class="py-2 px-3 text-right">${invHtml}</td>
                    <td class="py-2 px-3 text-right ${changeColor}">${changeSign}₹${r.spread_change.toFixed(1)}</td>
                </tr>
            `;
        });

        dailyTableBody.innerHTML = html;
    }

    // Filter Daily Table
    if (inpTableSearch) {
        inpTableSearch.addEventListener('input', () => {
            applySortAndRenderDailyTable();
        });
    }

    // Export CSV
    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', () => {
            if (!allDailyRows.length) {
                alert('No data to export.');
                return;
            }

            fetch('/api/export_spread_csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rows: allDailyRows })
            })
            .then(res => res.blob())
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const prefix = (appMode === 'cross') ? `${crossSym1}_vs_${crossSym2}` : currentSymbol.toLowerCase();
                const scopeName = selectedPairInfo ? selectedPairInfo.label.replace(/\s+/g, '_') : '1_year_continuous';
                a.download = `mcx_${prefix}_${scopeName}_daily_spread_${Date.now()}.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            })
            .catch(err => alert('Export failed: ' + err.message));
        });
    }

    // Sync MCX Data
    if (btnSyncMcx) {
        btnSyncMcx.addEventListener('click', async () => {
            if (!confirm('Fetch latest MCX Bhavcopy data now? This will refresh all active contracts.')) return;
            if (syncIcon) syncIcon.classList.add('spin-active');
            btnSyncMcx.disabled = true;

            try {
                const resp = await fetch('/api/sync_data', { method: 'POST' });
                const data = await resp.json();
                if (data.success) {
                    pollSyncStatus();
                } else {
                    alert(data.message);
                    if (syncIcon) syncIcon.classList.remove('spin-active');
                    btnSyncMcx.disabled = false;
                }
            } catch (err) {
                alert('Sync failed: ' + err.message);
                if (syncIcon) syncIcon.classList.remove('spin-active');
                btnSyncMcx.disabled = false;
            }
        });
    }

    function pollSyncStatus() {
        const interval = setInterval(async () => {
            try {
                const res = await fetch('/api/sync_status');
                const st = await res.json();
                if (!st.is_syncing) {
                    clearInterval(interval);
                    syncIcon.classList.remove('spin-active');
                    btnSyncMcx.disabled = false;
                    alert('MCX Data Sync Completed!');
                    loadMeta();
                    if (appMode === 'cross') {
                        loadCrossMonthlySummary();
                    } else {
                        loadMonthlyPairs();
                    }
                    loadSpreadSeries();
                } else {
                    headerDbStatus.textContent = st.progress || 'Syncing MCX Data...';
                }
            } catch (e) {
                clearInterval(interval);
                syncIcon.classList.remove('spin-active');
                btnSyncMcx.disabled = false;
            }
        }, 2000);
    }

    // Auto-Update Controls
    const labelAutoUpdateStatus = document.getElementById('labelAutoUpdateStatus');
    const btnCheckUpdateNow = document.getElementById('btnCheckUpdateNow');
    const iconCheckUpdate = document.getElementById('iconCheckUpdate');
    const toastNotification = document.getElementById('toastNotification');
    const toastTitle = document.getElementById('toastTitle');
    const toastMessage = document.getElementById('toastMessage');

    let lastKnownDbDate = null;

    function showToast(title, msg) {
        if (!toastNotification) return;
        if (toastTitle) toastTitle.textContent = title;
        if (toastMessage) toastMessage.textContent = msg;
        toastNotification.classList.remove('hidden');
        setTimeout(() => {
            toastNotification.classList.add('hidden');
        }, 5000);
    }

    async function checkAutoUpdateStatus() {
        try {
            const resp = await fetch('/api/auto_update_status');
            const data = await resp.json();
            if (!data.success) return;

            if (data.is_updating) {
                if (labelAutoUpdateStatus) labelAutoUpdateStatus.innerHTML = '<span class="text-amber-400">Updating Closing Data...</span>';
                if (iconCheckUpdate) iconCheckUpdate.classList.add('fa-spin');
                if (btnCheckUpdateNow) btnCheckUpdateNow.disabled = true;
            } else {
                if (iconCheckUpdate) iconCheckUpdate.classList.remove('fa-spin');
                if (btnCheckUpdateNow) btnCheckUpdateNow.disabled = false;
                const dbDate = data.latest_db_date || 'Current';
                if (labelAutoUpdateStatus) {
                    labelAutoUpdateStatus.innerHTML = `Auto-Update: ON <span class="text-emerald-400 font-mono text-[11px]">(${dbDate})</span>`;
                }

                // If DB date updated, trigger seamless reload
                if (lastKnownDbDate && data.latest_db_date && data.latest_db_date !== lastKnownDbDate) {
                    showToast('MCX Daily Spread Updated!', `New closing data loaded for ${data.latest_db_date}`);
                    loadMeta();
                    if (appMode === 'cross') {
                        loadCrossMonthlySummary();
                    } else {
                        loadMonthlyPairs();
                    }
                    loadSpreadSeries();
                }
                lastKnownDbDate = data.latest_db_date;
            }
        } catch (err) {
            console.error('Error checking auto-update status:', err);
        }
    }

    if (btnCheckUpdateNow) {
        btnCheckUpdateNow.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (iconCheckUpdate) iconCheckUpdate.classList.add('fa-spin');
            if (btnCheckUpdateNow) btnCheckUpdateNow.disabled = true;
            try {
                const resp = await fetch('/api/trigger_auto_update', { method: 'POST' });
                const res = await resp.json();
                showToast('Checking MCX Closing Data', res.message || 'Check started...');
                setTimeout(checkAutoUpdateStatus, 1500);
            } catch (err) {
                alert('Update check failed: ' + err.message);
                if (iconCheckUpdate) iconCheckUpdate.classList.remove('fa-spin');
                if (btnCheckUpdateNow) btnCheckUpdateNow.disabled = false;
            }
        });
    }

    // Poll every 30 seconds
    setInterval(checkAutoUpdateStatus, 30000);

    // Telegram Modal & Alert Controls
    const btnOpenTelegramModal = document.getElementById('btnOpenTelegramModal');
    const telegramModal = document.getElementById('telegramModal');
    const btnCloseTelegramModal = document.getElementById('btnCloseTelegramModal');
    const btnCancelTelegram = document.getElementById('btnCancelTelegram');
    const btnSaveTelegramSettings = document.getElementById('btnSaveTelegramSettings');
    const btnSendTestTg = document.getElementById('btnSendTestTg');
    const btnTriggerScanNow = document.getElementById('btnTriggerScanNow');
    const inpTgEnabled = document.getElementById('inpTgEnabled');
    const inpTgBotToken = document.getElementById('inpTgBotToken');
    const inpTgChatId = document.getElementById('inpTgChatId');
    const inpTgThreshold = document.getElementById('inpTgThreshold');
    const lblLastAlertSent = document.getElementById('lblLastAlertSent');
    const tgStatusFeedback = document.getElementById('tgStatusFeedback');
    const tgActiveIndicator = document.getElementById('tgActiveIndicator');

    function setTgFeedback(text, isError = false) {
        if (!tgStatusFeedback) return;
        tgStatusFeedback.textContent = text;
        tgStatusFeedback.className = isError 
            ? 'p-2.5 rounded-lg text-xs font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30' 
            : 'p-2.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
        tgStatusFeedback.classList.remove('hidden');
    }

    async function loadTelegramSettings() {
        try {
            const resp = await fetch('/api/telegram_settings');
            const data = await resp.json();
            if (!data.success) return;

            if (inpTgBotToken) inpTgBotToken.value = data.bot_token || '';
            if (inpTgChatId) inpTgChatId.value = data.chat_id || '';
            if (inpTgThreshold) inpTgThreshold.value = data.threshold_pct || 1.8;
            if (inpTgEnabled) inpTgEnabled.checked = data.is_enabled;
            if (lblLastAlertSent) lblLastAlertSent.textContent = data.last_alert_sent || '—';

            if (tgActiveIndicator) {
                if (data.is_enabled && data.bot_token && data.chat_id) {
                    tgActiveIndicator.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400';
                } else {
                    tgActiveIndicator.className = 'w-1.5 h-1.5 rounded-full bg-slate-500';
                }
            }
        } catch (err) {
            console.error('Error loading telegram settings:', err);
        }
    }

    if (btnOpenTelegramModal && telegramModal) {
        btnOpenTelegramModal.addEventListener('click', () => {
            telegramModal.classList.remove('hidden');
            if (tgStatusFeedback) tgStatusFeedback.classList.add('hidden');
            loadTelegramSettings();
        });

        const closeModal = () => telegramModal.classList.add('hidden');
        if (btnCloseTelegramModal) btnCloseTelegramModal.addEventListener('click', closeModal);
        if (btnCancelTelegram) btnCancelTelegram.addEventListener('click', closeModal);
        telegramModal.addEventListener('click', (e) => {
            if (e.target === telegramModal) closeModal();
        });
    }

    if (btnSaveTelegramSettings) {
        btnSaveTelegramSettings.addEventListener('click', async () => {
            const botToken = inpTgBotToken.value.trim();
            const chatId = inpTgChatId.value.trim();
            const threshold = parseFloat(inpTgThreshold.value) || 1.8;
            const isEnabled = inpTgEnabled.checked;

            try {
                const resp = await fetch('/api/telegram_settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bot_token: botToken,
                        chat_id: chatId,
                        threshold_pct: threshold,
                        is_enabled: isEnabled
                    })
                });
                const res = await resp.json();
                if (res.success) {
                    setTgFeedback('Settings saved successfully! Alerts will trigger when any spread exceeds ' + threshold + '%.');
                    loadTelegramSettings();
                    setTimeout(() => {
                        if (telegramModal) telegramModal.classList.add('hidden');
                    }, 1500);
                } else {
                    setTgFeedback(res.error || 'Failed to save settings', true);
                }
            } catch (err) {
                setTgFeedback('Error saving settings: ' + err.message, true);
            }
        });
    }

    if (btnSendTestTg) {
        btnSendTestTg.addEventListener('click', async () => {
            const botToken = inpTgBotToken.value.trim();
            const chatId = inpTgChatId.value.trim();

            if (!botToken || !chatId) {
                setTgFeedback('Please enter both Bot Token and Chat ID to send a test message.', true);
                return;
            }

            setTgFeedback('Sending test message to Telegram...');
            try {
                const resp = await fetch('/api/telegram_test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_token: botToken, chat_id: chatId })
                });
                const res = await resp.json();
                if (res.success) {
                    setTgFeedback('✅ Test message delivered successfully! Check your Telegram app.');
                } else {
                    setTgFeedback('❌ ' + res.message, true);
                }
            } catch (err) {
                setTgFeedback('Failed to send test: ' + err.message, true);
            }
        });
    }

    if (btnTriggerScanNow) {
        btnTriggerScanNow.addEventListener('click', async () => {
            setTgFeedback('Scanning for spreads exceeding threshold...');
            try {
                const resp = await fetch('/api/telegram_check_alerts', { method: 'POST' });
                const res = await resp.json();
                if (res.success) {
                    setTgFeedback(`✅ ${res.message}`);
                    loadTelegramSettings();
                } else {
                    setTgFeedback(`⚠️ ${res.message}`, true);
                }
            } catch (err) {
                setTgFeedback('Scan error: ' + err.message, true);
            }
        });
    }

    // ==========================================
    // Real-Time Live MCX Intraday Spreads Engine
    // ==========================================
    const liveCardsContainer = document.getElementById('liveCardsContainer');
    const liveMatrixContainer = document.getElementById('liveMatrixContainer');
    const badgeMarketStatus = document.getElementById('badgeMarketStatus');
    const lblLiveTime = document.getElementById('lblLiveTime');
    const chkAutoLive = document.getElementById('chkAutoLive');
    const btnRefreshLiveNow = document.getElementById('btnRefreshLiveNow');
    const iconRefreshLive = document.getElementById('iconRefreshLive');
    const livePingAnimate = document.getElementById('livePingAnimate');
    const liveDot = document.getElementById('liveDot');

    // Live Toolbar Controls
    const btnLiveViewMatrix = document.getElementById('btnLiveViewMatrix');
    const btnLiveViewCards = document.getElementById('btnLiveViewCards');
    const btnLiveFilterFront2 = document.getElementById('btnLiveFilterFront2');
    const btnLiveFilterAll = document.getElementById('btnLiveFilterAll');
    const btnLiveModeCross = document.getElementById('btnLiveModeCross');
    const btnLiveModeCalendar = document.getElementById('btnLiveModeCalendar');
    const selectLiveBasis = document.getElementById('selectLiveBasis');
    const liveMonthTabs = document.getElementById('liveMonthTabs');
    const liveMonthTabsContainer = document.getElementById('liveMonthTabsContainer');
    const liveBasisWrapper = document.getElementById('liveBasisWrapper');

    let liveIntervalId = null;
    let isFetchingLive = false;
    let cachedLiveData = null;

    // Live Display Preferences
    let liveViewMode = 'matrix';       // 'matrix' (Photo 3) or 'cards' (Photo 1)
    let liveFilterDepth = 'front2';    // 'front2' (Latest 2 Spreads) or 'all' (All Spreads)
    let liveSpreadType = 'cross';      // 'cross' (Cross-Instrument) or 'calendar' (Calendar Spreads)
    let liveActiveMonth = 'consolidated'; // 'consolidated' or month code like '2026-11'
    let liveBasis = '10g';

    const fmtLive = (v, dec = 1) => {
        if (v === null || v === undefined || isNaN(v)) return '—';
        return Number(v).toLocaleString('en-IN', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    };
    const fmtLiveInt = (v) => {
        if (v === null || v === undefined || isNaN(v)) return '0';
        return Number(v).toLocaleString('en-IN');
    };

    // Live Toolbar Event Handlers
    function updateLiveToolbarUI() {
        if (btnLiveViewMatrix && btnLiveViewCards) {
            if (liveViewMode === 'matrix') {
                btnLiveViewMatrix.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-amber-500 text-slate-950 shadow-sm';
                btnLiveViewCards.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
            } else {
                btnLiveViewCards.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-amber-500 text-slate-950 shadow-sm';
                btnLiveViewMatrix.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
            }
        }

        if (btnLiveFilterFront2 && btnLiveFilterAll) {
            if (liveFilterDepth === 'front2') {
                btnLiveFilterFront2.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                btnLiveFilterAll.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
            } else {
                btnLiveFilterAll.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                btnLiveFilterFront2.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
            }
        }

        if (btnLiveModeCross && btnLiveModeCalendar) {
            if (liveSpreadType === 'cross') {
                btnLiveModeCross.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-sky-500/20 text-sky-300 border border-sky-500/40';
                btnLiveModeCalendar.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
                if (liveMonthTabsContainer) liveMonthTabsContainer.classList.remove('hidden');
                if (liveBasisWrapper) liveBasisWrapper.classList.remove('hidden');
            } else {
                btnLiveModeCalendar.className = 'px-3 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-sky-500/20 text-sky-300 border border-sky-500/40';
                btnLiveModeCross.className = 'px-3 py-1 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5';
                if (liveMonthTabsContainer) liveMonthTabsContainer.classList.add('hidden');
                if (liveBasisWrapper) liveBasisWrapper.classList.add('hidden');
            }
        }
    }

    if (btnLiveViewMatrix) {
        btnLiveViewMatrix.addEventListener('click', () => {
            liveViewMode = 'matrix';
            updateLiveToolbarUI();
            renderLiveDisplay();
        });
    }

    if (btnLiveViewCards) {
        btnLiveViewCards.addEventListener('click', () => {
            liveViewMode = 'cards';
            updateLiveToolbarUI();
            renderLiveDisplay();
        });
    }

    if (btnLiveFilterFront2) {
        btnLiveFilterFront2.addEventListener('click', () => {
            liveFilterDepth = 'front2';
            updateLiveToolbarUI();
            renderLiveDisplay();
        });
    }

    if (btnLiveFilterAll) {
        btnLiveFilterAll.addEventListener('click', () => {
            liveFilterDepth = 'all';
            updateLiveToolbarUI();
            renderLiveDisplay();
        });
    }

    if (btnLiveModeCross) {
        btnLiveModeCross.addEventListener('click', () => {
            liveSpreadType = 'cross';
            updateLiveToolbarUI();
            loadLiveSpreads();
        });
    }

    if (btnLiveModeCalendar) {
        btnLiveModeCalendar.addEventListener('click', () => {
            liveSpreadType = 'calendar';
            updateLiveToolbarUI();
            loadLiveSpreads();
        });
    }

    if (selectLiveBasis) {
        selectLiveBasis.addEventListener('change', () => {
            liveBasis = selectLiveBasis.value;
            loadLiveSpreads();
        });
    }

    async function loadLiveSpreads() {
        if (isFetchingLive) return;
        isFetchingLive = true;

        if (iconRefreshLive) iconRefreshLive.classList.add('animate-spin');

        const sym = currentSymbol || 'GOLDM';
        const url = `/api/live_spreads?mode=${liveSpreadType}&symbol=${sym}&formula=leg2_minus_leg1&leg1_symbol=${crossSym1}&leg2_symbol=${crossSym2}&basis=${liveBasis}`;

        try {
            const resp = await fetch(url);
            const data = await resp.json();

            if (!data.success) {
                console.warn('Live spreads fetch notice:', data.error);
                return;
            }

            cachedLiveData = data;

            // Update Market Status Indicator
            if (badgeMarketStatus) {
                if (data.is_market_open) {
                    badgeMarketStatus.textContent = 'MARKET OPEN';
                    badgeMarketStatus.className = 'text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider';
                    if (livePingAnimate) livePingAnimate.className = 'animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75';
                    if (liveDot) liveDot.className = 'relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500';
                } else {
                    badgeMarketStatus.textContent = 'MARKET CLOSED';
                    badgeMarketStatus.className = 'text-[10px] bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider';
                    if (livePingAnimate) livePingAnimate.className = 'hidden';
                    if (liveDot) liveDot.className = 'relative inline-flex rounded-full h-3.5 w-3.5 bg-slate-500';
                }
            }

            if (lblLiveTime) {
                lblLiveTime.textContent = `${data.timestamp} (${data.quotes_count} quotes)`;
            }

            renderLiveDisplay();

        } catch (err) {
            console.error('Error fetching live spreads:', err);
        } finally {
            isFetchingLive = false;
            if (iconRefreshLive) iconRefreshLive.classList.remove('animate-spin');
        }
    }

    function renderLiveDisplay() {
        if (!cachedLiveData) return;

        updateLiveToolbarUI();

        if (liveViewMode === 'matrix') {
            if (liveMatrixContainer) liveMatrixContainer.classList.remove('hidden');
            if (liveCardsContainer) liveCardsContainer.classList.add('hidden');
            renderLiveMatrix(cachedLiveData);
        } else {
            if (liveMatrixContainer) liveMatrixContainer.classList.add('hidden');
            if (liveCardsContainer) liveCardsContainer.classList.remove('hidden');
            renderLiveCards(cachedLiveData);
        }
    }

    // ==========================================
    // View 1: Consolidated Matrix (Photo 3 Style)
    // ==========================================
    function renderLiveMatrix(data) {
        if (!liveMatrixContainer) return;

        if (liveSpreadType === 'cross') {
            const matrix = data.cross_matrix;
            if (!matrix || !matrix.rows || !matrix.rows.length) {
                liveMatrixContainer.innerHTML = `
                    <div class="py-4 text-center text-slate-500 text-xs">
                        No cross-instrument live quotes available.
                    </div>
                `;
                return;
            }

            // Populate Month Tabs (Photo 3: Select Month View: NOV | DEC | JAN | Consolidated)
            renderMonthTabsUI(matrix.months);

            // Filter columns based on month selection or front2 filter
            let activeCols = matrix.months;
            if (liveActiveMonth !== 'consolidated') {
                activeCols = matrix.months.filter(m => m.code === liveActiveMonth);
            } else if (liveFilterDepth === 'front2') {
                activeCols = matrix.months.slice(0, 3); // Front 3 active months (NOV, DEC, JAN)
            }

            const basisLabel = matrix.basis === '10g' ? '₹ / 10g Standard' : (matrix.basis === '1g' ? '₹ / 1g' : 'Nominal');

            let thCols = '';
            activeCols.forEach(m => {
                thCols += `
                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 border-l border-slate-800 uppercase tracking-wider bg-slate-950/70">${m.short_label} POINTS (₹)</th>
                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 uppercase tracking-wider bg-slate-950/70">${m.short_label} SPREAD %</th>
                `;
            });

            let trRows = '';
            matrix.rows.forEach(r => {
                let tdCols = '';
                activeCols.forEach(m => {
                    const cell = r.months[m.code];
                    if (cell && cell.available) {
                        const isPos = cell.spread >= 0;
                        const sign = isPos ? '+' : '';
                        const colorClass = isPos ? 'text-emerald-400' : 'text-rose-400';
                        const pctSign = cell.spread_pct >= 0 ? '+' : '';
                        tdCols += `
                            <td class="py-2.5 px-3 text-right font-mono font-bold ${colorClass} border-l border-slate-800/80 bg-slate-950/30">
                                ${sign}₹${fmtLive(cell.spread, 2)}
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold ${colorClass} bg-slate-950/30">
                                ${pctSign}${cell.spread_pct.toFixed(2)}%
                            </td>
                        `;
                    } else {
                        tdCols += `
                            <td class="py-2.5 px-3 text-right font-mono text-slate-600 border-l border-slate-800/80 bg-slate-950/20">+0.00</td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-600 bg-slate-950/20">+0.00%</td>
                        `;
                    }
                });

                trRows += `
                    <tr class="border-b border-slate-800/60 hover:bg-amber-500/5 transition">
                        <td class="py-2.5 px-3 font-semibold text-slate-200 flex items-center gap-2">
                            <i class="fa-solid fa-arrows-left-right text-amber-400/80 text-[10px]"></i>
                            <span>${r.pair_label}</span>
                        </td>
                        ${tdCols}
                    </tr>
                `;
            });

            liveMatrixContainer.innerHTML = `
                <div class="rounded-xl border border-slate-800 overflow-hidden bg-slate-950/60 shadow-lg">
                    <div class="p-3 border-b border-slate-800/80 bg-slate-900/60 flex flex-wrap items-center justify-between gap-2">
                        <div class="flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                            <h3 class="font-bold text-xs uppercase text-slate-100 tracking-wide flex items-center gap-1.5">
                                <i class="fa-solid fa-layer-group text-amber-400"></i>
                                PART 3: CROSS-INSTRUMENT SPREAD ANALYSIS (POINTS & PERCENTAGE)
                            </h3>
                            <span class="text-[11px] text-slate-400 font-normal">
                                Spread in points (Net ₹ Value) and percentage (%) between Gold Petal, Gold Guinea, and Gold M.
                            </span>
                        </div>
                        <span class="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                            Basis: ${basisLabel}
                        </span>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead>
                                <tr class="border-b border-slate-800 text-[11px]">
                                    <th class="py-2.5 px-3 font-bold text-slate-300 uppercase tracking-wider bg-slate-950/80 min-w-[200px]">COMPARISON PAIR</th>
                                    ${thCols}
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/50">
                                ${trRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        } else {
            // Calendar Spreads Consolidated Matrix (All 4 Commodities across front 2 cycles)
            const allCal = data.all_calendar;
            if (!allCal || !allCal.grouped) {
                liveMatrixContainer.innerHTML = `
                    <div class="py-4 text-center text-slate-500 text-xs">
                        No calendar live quotes available.
                    </div>
                `;
                return;
            }

            let trRows = '';
            allCal.symbols.forEach(sym => {
                const spreads = allCal.grouped[sym] || [];
                const s1 = spreads[0];
                const s2 = spreads[1];

                const renderCell = (s) => {
                    if (!s) return `<td class="py-2.5 px-3 text-right font-mono text-slate-600">—</td><td class="py-2.5 px-3 text-right font-mono text-slate-600">—</td>`;
                    const isPos = s.spread >= 0;
                    const sign = isPos ? '+' : '';
                    const pctSign = s.spread_pct >= 0 ? '+' : '';
                    const colorClass = isPos ? 'text-emerald-400' : 'text-rose-400';
                    return `
                        <td class="py-2.5 px-3 text-right font-mono font-bold ${colorClass} border-l border-slate-800/80 bg-slate-950/30">
                            ${sign}₹${fmtLive(s.spread, 1)} <span class="text-[10px] text-slate-500 block font-normal">${s.near_expiry} &rarr; ${s.next_expiry}</span>
                        </td>
                        <td class="py-2.5 px-3 text-right font-mono font-bold ${colorClass} bg-slate-950/30">
                            ${pctSign}${s.spread_pct.toFixed(2)}%
                        </td>
                    `;
                };

                trRows += `
                    <tr class="border-b border-slate-800/60 hover:bg-amber-500/5 transition">
                        <td class="py-2.5 px-3 font-bold text-amber-400 flex items-center gap-2">
                            <i class="fa-regular fa-calendar text-slate-400 text-[11px]"></i>
                            <span>${sym}</span>
                        </td>
                        ${renderCell(s1)}
                        ${renderCell(s2)}
                    </tr>
                `;
            });

            liveMatrixContainer.innerHTML = `
                <div class="rounded-xl border border-slate-800 overflow-hidden bg-slate-950/60 shadow-lg">
                    <div class="p-3 border-b border-slate-800/80 bg-slate-900/60 flex items-center justify-between">
                        <h3 class="font-bold text-xs uppercase text-slate-100 tracking-wide flex items-center gap-1.5">
                            <i class="fa-solid fa-calendar-days text-amber-400"></i>
                            CONSOLIDATED CALENDAR SPREAD ANALYSIS (LATEST 2 SPREADS OF EVERY INSTRUMENT)
                        </h3>
                        <span class="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                            Front 2 Active Consecutive Cycles
                        </span>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead>
                                <tr class="border-b border-slate-800 text-[11px]">
                                    <th class="py-2.5 px-3 font-bold text-slate-300 uppercase tracking-wider bg-slate-950/80 min-w-[150px]">INSTRUMENT</th>
                                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 border-l border-slate-800 uppercase tracking-wider bg-slate-950/70">CYCLE 1 SPREAD (₹)</th>
                                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 uppercase tracking-wider bg-slate-950/70">CYCLE 1 SPREAD %</th>
                                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 border-l border-slate-800 uppercase tracking-wider bg-slate-950/70">CYCLE 2 (NEXT-FAR) SPREAD (₹)</th>
                                    <th class="py-2.5 px-3 text-right font-bold text-slate-300 uppercase tracking-wider bg-slate-950/70">CYCLE 2 SPREAD %</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/50">
                                ${trRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }
    }

    function renderMonthTabsUI(months) {
        if (!liveMonthTabs) return;

        let html = `
            <button type="button" class="live-month-tab ${liveActiveMonth === 'consolidated' ? 'active font-bold bg-amber-500 text-slate-950' : 'font-semibold text-slate-400 hover:text-slate-200'} px-2.5 py-0.5 rounded text-xs transition" data-month="consolidated">
                Consolidated
            </button>
        `;

        months.forEach(m => {
            const isActive = liveActiveMonth === m.code;
            const cls = isActive ? 'active font-bold bg-amber-500 text-slate-950' : 'font-semibold text-slate-400 hover:text-slate-200';
            html += `
                <button type="button" class="live-month-tab ${cls} px-2.5 py-0.5 rounded text-xs transition" data-month="${m.code}">
                    ${m.short_label}
                </button>
            `;
        });

        liveMonthTabs.innerHTML = html;

        liveMonthTabs.querySelectorAll('.live-month-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                liveActiveMonth = btn.getAttribute('data-month');
                renderLiveDisplay();
            });
        });
    }

    // ==========================================
    // View 2: Live Spreads Cards Grid (Photo 1)
    // ==========================================
    function renderLiveCards(data) {
        if (!liveCardsContainer) return;

        let spreads = data.spreads || [];

        // Apply "Latest 2 Spreads" filter if enabled
        if (liveFilterDepth === 'front2') {
            if (liveSpreadType === 'calendar' && data.all_calendar && data.all_calendar.spreads) {
                // Show latest 2 spreads for EVERY commodity
                spreads = data.all_calendar.spreads;
            } else {
                spreads = spreads.slice(0, 2);
            }
        }

        if (!spreads || !spreads.length) {
            liveCardsContainer.innerHTML = `
                <div class="col-span-full py-3 text-center text-slate-500 text-xs">
                    No active trading spreads currently available.
                </div>
            `;
            return;
        }

        let html = '';
        spreads.forEach(c => {
            const isPos = c.spread >= 0;
            const spreadSign = isPos ? '+' : '';
            const pctSign = c.spread_pct >= 0 ? '+' : '';
            const spreadColor = isPos ? 'text-emerald-400' : 'text-rose-400';
            const bgBox = isPos ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20';

            const activePill = c.is_live 
                ? `<span class="inline-flex items-center gap-1 text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-bold"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>LIVE TRADING</span>` 
                : `<span class="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">UNTRADED TODAY</span>`;

            if (c.leg1_symbol && c.leg2_symbol) {
                // Cross commodity card
                const basisLabel = c.basis === '10g' ? '₹ / 10g' : (c.basis === '1g' ? '₹ / 1g' : 'Quoted');
                html += `
                    <div class="bg-slate-950/90 border border-slate-800 hover:border-amber-500/40 rounded-xl p-3 shadow-md transition flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2">
                                <div class="font-bold text-xs text-slate-100 flex items-center gap-1.5">
                                    <i class="fa-solid fa-shuffle text-amber-400 text-xs"></i>
                                    <span>${c.month} (${c.leg1_symbol} vs ${c.leg2_symbol})</span>
                                </div>
                                ${activePill}
                            </div>

                            <div class="grid grid-cols-2 gap-2 text-xs mb-2.5">
                                <div class="bg-slate-900 p-2 rounded-lg border border-slate-800/80">
                                    <div class="text-[10px] text-sky-400 font-semibold flex items-center justify-between">
                                        <span>${c.leg1_symbol}</span>
                                        <span class="font-mono text-slate-400">${c.leg1_expiry}</span>
                                    </div>
                                    <div class="text-sm font-bold font-mono text-slate-100 mt-0.5">₹${fmtLive(c.leg1_norm)}</div>
                                    <div class="text-[9px] text-slate-500 mt-0.5">LTP: ₹${fmtLive(c.leg1_ltp)}</div>
                                </div>
                                <div class="bg-slate-900 p-2 rounded-lg border border-slate-800/80">
                                    <div class="text-[10px] text-fuchsia-400 font-semibold flex items-center justify-between">
                                        <span>${c.leg2_symbol}</span>
                                        <span class="font-mono text-slate-400">${c.leg2_expiry}</span>
                                    </div>
                                    <div class="text-sm font-bold font-mono text-slate-100 mt-0.5">₹${fmtLive(c.leg2_norm)}</div>
                                    <div class="text-[9px] text-slate-500 mt-0.5">LTP: ₹${fmtLive(c.leg2_ltp)}</div>
                                </div>
                            </div>
                        </div>

                        <div class="flex items-center justify-between p-2.5 rounded-lg border ${bgBox}">
                            <div>
                                <div class="text-[10px] uppercase font-bold text-slate-400">Live Spread (${basisLabel})</div>
                                <div class="text-base font-extrabold font-mono ${spreadColor}">${spreadSign}₹${fmtLive(c.spread)}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-[10px] uppercase font-bold text-slate-400">Live Spread %</div>
                                <div class="text-base font-extrabold font-mono ${spreadColor}">${pctSign}${c.spread_pct.toFixed(2)}%</div>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                // Calendar spread card
                html += `
                    <div class="bg-slate-950/90 border border-slate-800 hover:border-amber-500/40 rounded-xl p-3 shadow-md transition flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2">
                                <div class="font-bold text-xs text-slate-100 flex items-center gap-1.5">
                                    <i class="fa-regular fa-calendar text-amber-400 text-xs"></i>
                                    <span>${c.label}</span>
                                    <span class="text-[10px] text-amber-400 font-mono font-semibold">(${c.symbol})</span>
                                </div>
                                ${activePill}
                            </div>

                            <div class="grid grid-cols-2 gap-2 text-xs mb-2.5">
                                <div class="bg-slate-900 p-2 rounded-lg border border-slate-800/80">
                                    <div class="text-[10px] text-sky-400 font-semibold flex items-center justify-between">
                                        <span>Near Month</span>
                                        <span class="font-mono text-slate-400">${c.near_expiry}</span>
                                    </div>
                                    <div class="text-sm font-bold font-mono text-slate-100 mt-0.5">₹${fmtLive(c.near_effective)}</div>
                                    <div class="text-[9px] text-slate-500 mt-0.5">Vol: ${fmtLiveInt(c.near_volume)}</div>
                                </div>
                                <div class="bg-slate-900 p-2 rounded-lg border border-slate-800/80">
                                    <div class="text-[10px] text-fuchsia-400 font-semibold flex items-center justify-between">
                                        <span>Next Month</span>
                                        <span class="font-mono text-slate-400">${c.next_expiry}</span>
                                    </div>
                                    <div class="text-sm font-bold font-mono text-slate-100 mt-0.5">₹${fmtLive(c.next_effective)}</div>
                                    <div class="text-[9px] text-slate-500 mt-0.5">Vol: ${fmtLiveInt(c.next_volume)}</div>
                                </div>
                            </div>
                        </div>

                        <div class="flex items-center justify-between p-2.5 rounded-lg border ${bgBox}">
                            <div>
                                <div class="text-[10px] uppercase font-bold text-slate-400">Live Spread Points</div>
                                <div class="text-base font-extrabold font-mono ${spreadColor}">${spreadSign}₹${fmtLive(c.spread)}</div>
                            </div>
                            <div class="text-right">
                                <div class="text-[10px] uppercase font-bold text-slate-400">Live Spread %</div>
                                <div class="text-base font-extrabold font-mono ${spreadColor}">${pctSign}${c.spread_pct.toFixed(2)}%</div>
                            </div>
                        </div>
                    </div>
                `;
            }
        });

        liveCardsContainer.innerHTML = html;
    }

    if (btnRefreshLiveNow) {
        btnRefreshLiveNow.addEventListener('click', () => {
            loadLiveSpreads();
        });
    }

    if (chkAutoLive) {
        chkAutoLive.addEventListener('change', () => {
            if (chkAutoLive.checked) {
                startLivePolling();
            } else {
                stopLivePolling();
            }
        });
    }

    function startLivePolling() {
        stopLivePolling();
        liveIntervalId = setInterval(() => {
            if (chkAutoLive && chkAutoLive.checked) {
                loadLiveSpreads();
            }
        }, 15000);
    }

    function stopLivePolling() {
        if (liveIntervalId) {
            clearInterval(liveIntervalId);
            liveIntervalId = null;
        }
    }

    // Initialize
    try {
        updateSortToggleUI();
        loadMeta();
        checkAutoUpdateStatus();
        loadTelegramSettings();
        loadMonthlyPairs();
        loadSpreadSeries();
    } catch (e) {
        console.error('Initialization error:', e);
    }

    try {
        loadLiveSpreads();
        startLivePolling();
    } catch (e) {
        console.error('Live feed initialization error:', e);
    }
});
