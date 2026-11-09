# MCX Gold Futures Spread & Percentage Terminal

Clean, interactive institutional dashboard for tracking **Active Future &minus; Next Month Future Spread** and **Spread Percentage (%)** using daily closing prices from MCX India over the past 1+ year to the current date.

---

## What the Terminal Provides

1. **Spread in Points (₹) & Percentage (%)**:
   - Calculates daily spread:
     $$\text{Spread (Points / ₹)} = \text{Active Future Close} - \text{Next Month Future Close}$$
   - Calculates spread percentage:
     $$\text{Spread (\%)} = \frac{\text{Spread}}{\text{Active Future Close}} \times 100\%$$
   - Displays both in **Summary KPI Cards**, **Data Table (in numbers)**, and **Interactive Graph Charts**.

2. **Official Daily Closing Price**:
   - Uses exchange-certified Bhavcopy `Close` price for both futures legs.

3. **Two Flexible Modes**:
   - **Continuous 1-Year Active vs Next Month**: Follows the front-month contract and rolls to the next active contract across 300+ trading days from the past year to the current date.
   - **Specific Month Pair (e.g. March Future &minus; April Future)**: Select any exact contract pair to view all overlapping trading days.

4. **Clean & Presentable Graph Chart**:
   - **No clutter**: No EMA, no Bollinger bands, no indicator lines.
   - Four clean views:
     - **Spread Points (₹)**: High-resolution daily closing spread line.
     - **Spread Percentage (%)**: Exact daily spread as percentage of active future.
     - **Dual View (Points & %)**: Synchronized dual-axis view.
     - **Active vs Next Month Closing Prices**: Underlying futures price comparison.
   - **Full Zoom Controls**:
     - Mouse wheel / touch zoom in & zoom out (`scrollZoom`).
     - Zoom In (`+`) & Zoom Out (`-`) buttons.
     - Box zoom & Pan tools.
     - Reset view button.
     - Quick timeframe buttons: `[ 1M ] [ 3M ] [ 6M ] [ 1Y ] [ All ]`.
     - Interactive Timeline Range Slider at the bottom of the chart.

5. **Data in Numbers (Table View)**:
   - Date, Active Contract Month, Active Close, Next Month Contract, Next Close, Spread (₹), Spread (%), Annualized %, and Daily Change (₹).
   - Real-time search filter by date or month.
   - One-click **"Export CSV"** button for Excel.

---

## Live Dashboard

The application is running at:
**[http://127.0.0.1:5000](http://127.0.0.1:5000)**

To run manually:
```bash
python app.py
```
Or double-click `run_dashboard.bat`.
