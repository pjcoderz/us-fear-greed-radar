# us-fear-greed-radar

**Behavioral Finance in Action: US Market Sentiment & Empirical Win-Rate Radar**  
**行為財務學應用：美股恐慌指標與實證勝率雷達**

`us-fear-greed-radar` is an automated quantitative monitoring and empirical backtesting dashboard built on a decoupled `crawler.py` + `app.py` + GitHub Actions architecture. It tracks three canonical market sentiment indicators—**CNN Fear & Greed Index**, **CBOE VIX**, and **AAII Sentiment Survey**—computes historical conditional win rates and forward benchmark returns (**S&P 500** and **NASDAQ-100**) across multiple holding horizons, sends automated email alerts when win rates reach **≥ 90%**, and provides an interactive multilingual interface (**Traditional Chinese / English / Japanese**) alongside an academic literature and methodology tab.

---

## Key Features

1. **Automated Multi-Source Data Pipeline (`crawler.py`)**
   - Fetches real-time and historical **CNN Fear & Greed** scores, **CBOE VIX**, **S&P 500 (`^GSPC`)**, **NASDAQ-100 (`^NDX`)**, and weekly **AAII Sentiment Survey** figures.
   - Includes retry logic, SSL tolerance, and anti-wipe fallback protection so temporary source hiccups do not overwrite valid historical records.
2. **Empirical Conditional Win-Rate Engine**
   - Evaluates historical analogous market states from 2011 to present across **21D (1M)**, **63D (3M)**, **126D (6M)**, and **252D (1Y)** trading-day horizons.
   - Triggers an automated Gmail SMTP alert when the target horizon win rate meets or exceeds the **90.0%** threshold.
3. **Multilingual Streamlit Dashboard (`app.py`)**
   - Switch dynamically in **Settings** between **繁體中文**, **English**, and **日本語**.
   - Supports theme customization, base font size adjustment, RWD cards and summary tables, 1-year trend visualization, and a visitor counter starting from 1,000.
4. **Academic Foundations & Literature Tab**
   - Documents the behavioral finance rationale, empirical backtesting methodology, and key peer-reviewed references for researchers and learners.

---

## Academic References

- **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12–17. https://doi.org/10.3905/jpm.2000.319728
- **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447–462. https://doi.org/10.1002/fut.1602
- **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16–23. https://doi.org/10.2469/faj.v56.n2.2340
- **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645–1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x
- **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1–32. https://doi.org/10.1093/rfs/hhu072

---

## Deployment on GitHub & Streamlit Cloud

1. Create a new repository named **`us-fear-greed-radar`** and add `crawler.py`, `app.py`, `requirements.txt`, `README.md`, and `.github/workflows/update_data.yml`.
2. In **Settings → Secrets and variables → Actions**, add:
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD`
   - `RECEIVER_EMAIL`
3. Run **Actions → Update Fear & Greed Data → Run workflow** once to generate `data/sentiment_data.json` and `data/history_backtest.csv`.
4. Deploy `app.py` on **Streamlit Cloud** pointing to `us-fear-greed-radar`.

*Disclaimer: This tool is designed for academic research and educational illustration of behavioral finance models. Historical conditional win rates do not guarantee future investment outcomes.*
