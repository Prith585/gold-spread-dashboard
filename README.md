# Gold Spot / Futures Spread Arbitrage Terminal (Institutional Pro Edition)

A professional institutional terminal for monitoring **MCX Gold Futures vs. All India Bullion (IBJA) Spot** arbitrage in India. Engineered for bullion desks, prop traders, jewellers, and quantitative arbitrageurs.

---

## 📡 Live Market Data Infrastructure

1. **MCX (Multi Commodity Exchange of India)**:
   - Direct live market watch parsing (`GetMarketWatch?culture=en`) for all active `FUTCOM` contracts across all forward maturities:
     - `GOLD` (1 Kg standard contract, 1,000g lot, quoted per 10g)
     - `GOLDM` (Gold Mini 100g lot, quoted per 10g)
     - `GOLDTEN` (10g delivery lot, quoted per 10g)
     - `GOLDGUINEA` (8g sovereign lot, normalized to 10g)
     - `GOLDPETAL` (1g micro lot, normalized to 10g)
   - Real-time Last Traded Price (LTP), Open, High, Low, Previous Close, Volume, and Open Interest (OI).

2. **All India Bullion (IBJA - India Bullion and Jewellers Association)**:
   - Benchmark opening (AM) and closing (PM) fixing spot rates from `ibjarates.com`.
   - Supports:
     - **Gold 999** (24 Karat pure fine gold)
     - **Gold 995** (99.5% standard MCX physical delivery fineness)
     - **Gold 916** (22 Karat standard jewellery gold)
   - Custom Spot Price override with 1-click reset to live market.

---

## 🧮 Quantitative Models & Financial Engineering

### 1. Theoretical Fair Value (Cost of Carry Model: $F^*$)
$$\text{Fair Value } F^* = S \times \left[ 1 + (r + s + i) \times \left(\frac{\text{DTE}}{365}\right) \right]$$
Where:
- $S$ = Effective Spot Price (ex-tax or with 3% GST).
- $r$ = Financing rate / cost of capital (default 8.0% p.a.).
- $s$ = Warehousing / vault storage cost (~0.25% p.a.).
- $i$ = Insurance (~0.05% p.a.).
- $\text{DTE}$ = Calendar Days to Expiry.

### 2. Arbitrage Alpha / Mispricing ($\alpha$)
$$\alpha = F_{\text{market}} - F^*$$
- **$\alpha > 0$ (Positive Mispricing)**: Futures contract is trading at an excess premium over theoretical carry $\rightarrow$ **Clean Arbitrage Yield**.
- **$\alpha < 0$ (Discount / Inversion)**: Futures contract is undervalued $\rightarrow$ **Reverse Cash & Carry Opportunity**.

### 3. Breakeven Spread & Margin of Safety
$$\text{Breakeven Spread (₹/10g)} = \text{Spot} \times \left(\frac{r \times \text{DTE}}{365}\right) + \text{Statutory Transaction Charges}$$
$$\text{Safety Margin (₹/10g)} = \text{Actual Gross Spread} - \text{Breakeven Spread}$$
A positive Safety Margin indicates that the trade generates net profit after paying all MCX turnover fees, SEBI turnover fees, stamp duty, brokerage, and carry interest.

### 4. Calendar Spreads (Futures vs. Futures Roll Yield)
For pairwise forward contracts $F_1$ (Near) and $F_2$ (Far):
$$\text{Roll Spread (₹/10g)} = F_2 - F_1$$
$$\text{Annualized Roll Yield \%} = \left(\frac{F_2 - F_1}{F_1}\right) \times \left(\frac{365}{\text{DTE}_2 - \text{DTE}_1}\right)$$
- **Contango Roll**: Buy Near, Sell Far to capture positive roll yield without taking physical delivery or incurring GST.
- **Backwardation Roll**: Inverted spreads where near-month trades at a premium to far-month.

---

## 🏛️ 4-Desk Opportunity Ribbon

The dashboard automatically segments optimal opportunities for different trading desks:
1. **🥇 Best November Cash & Carry Desk**: Identifies the single highest net ROI % trade for the active November prompt month.
2. **💼 Institutional 1kg Bar Desk**: Standard 1,000g contract execution metrics (Total turnover in ₹ Crores, Net ₹ profit per 1kg bar, DTE).
3. **🔄 Calendar Spread Roll Desk**: Top Futures-vs-Futures roll yield without physical gold handling.
4. **🛡️ Maximum Margin of Safety Desk**: The trade with the widest cushion above breakeven cost.

---

## 🚀 Workstation Features

- **Multi-Tab Layout**:
  - **Tab 1: Spot vs Futures Matrix**: Full real-time sortable table with instant live text search, mispricing alpha, safety margin, and net annualized ROI.
  - **Tab 2: Calendar Spreads**: Pairwise roll yield table across all instrument families.
  - **Tab 3: Quantitative Analytics**: Highcharts/Chart.js visualizations of the forward term structure, net yield curve, and mispricing alpha.
  - **Tab 4: Execution Blueprint**: Step-by-step physical delivery, tender margin schedule ($T-5$), and GST input tax credit (ITC) protocol.
- **1-Click Broker Order Ticket**: Generates ready-to-copy 2-legged order tickets for Zerodha Kite, Upstox, Angel One, or MCX terminals.
- **1-Click CSV Export**: Download a full audit-ready CSV spreadsheet of all contracts and calculations.

---

## 💻 How to Run

1. Open PowerShell or Command Prompt:
   ```powershell
   cd c:\Users\user\Documents\gold_spread_dashboard
   python app.py
   ```
   *Or double-click `run_dashboard.bat`.*
2. Open your browser:
   ```
   http://localhost:5055
   ```
