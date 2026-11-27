import os
import json
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Behavioral Sentiment & Win-Rate Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

JSON_PATH = os.path.join("data", "sentiment_data.json")
CSV_PATH = os.path.join("data", "history_backtest.csv")
COUNTER_PATH = os.path.join("data", "visitor_count.txt")

# ================= 多國語言字典 (i18n) =================
I18N = {
    "zh-TW": {
        "lang_name": "繁體中文",
        "app_title": "📡 行為財務學應用：美股恐慌指標與實證勝率雷達",
        "app_subtitle": "整合 CNN Fear & Greed、CBOE VIX 與 AAII 散戶情緒調查之逆向投資量化實證系統",
        "settings_header": "⚙️ 系統設定 (Settings)",
        "lang_label": "🌐 顯示語言 / Language",
        "theme_label": "🎨 背景色系",
        "themes": ["護眼米白", "極簡純白", "深邃暗黑"],
        "font_label": "🔠 全站字體大小 (px)",
        "sidebar_note": "本系統將行為財務學（Behavioral Finance）中「投資人情緒與報酬反轉」之實證研究轉化為自動化監控工具。",
        "meta_line": "資料更新：{updated} ｜ 累積瀏覽人次：{visitors:,} ｜ 寄信警報門檻：≥ {threshold}%",
        "tab_dashboard": "📊 即時指標與勝率儀表板",
        "tab_academic": "📚 學術理論基礎與參考文獻",
        "horizon_prompt": "選擇實證回測持有週期（Forward Holding Horizon）：",
        "horizons": {
            "126D": "6 個月 (126 交易日) — 中期波段基準",
            "252D": "1 年 (252 交易日) — 長期均值回歸",
            "63D": "3 個月 (63 交易日) — 季度反彈觀察",
            "21D": "1 個月 (21 交易日) — 短期情緒超賣"
        },
        "alert_triggered": "🚨 已達 90% 以上高勝率寄信門檻！",
        "alert_waiting": "⏳ 恐慌累積中，尚未達 90% 寄信門檻",
        "win_banner_title": "🎯 {horizon} 歷史實證上漲勝率：{status}",
        "green_lights_count": "逆向買點綠燈數：{count} / 3 燈",
        "sample_stats": "歷史相似條件樣本：<b>{samples} 個交易日</b> ｜ S&P 500 平均報酬：<b>{sp:+.2f}%</b> ｜ NASDAQ-100 平均報酬：<b>{ndx:+.2f}%</b>",
        "section_cards": "🚦 三大市場情緒指標即時燈號",
        "card1_title": "1. CNN 恐慌與貪婪指數",
        "card1_sub": "原始評級：{rating}（前日 {prev}）<br>單指標歷史勝率：<b>{win}%</b>",
        "card2_title": "2. CBOE VIX 波動率恐慌指數",
        "card2_sub": "前日收盤：{prev}（門檻 ≥ 30 亮綠燈）<br>單指標歷史勝率：<b>{win}%</b>",
        "card3_title": "3. AAII 散戶看空比例 ({date})",
        "card3_sub": "看多 {bull}% / 中立 {neut}%（多空差 {spread}%）<br>散戶極端看空加權：<b>+{bonus}%</b>",
        "bearish_unit": "看空",
        "lights": {
            "cnn": {"green": "🟢 極度恐慌 (買點亮燈)", "yellow": "🟡 恐慌觀察", "red": "🔴 中性/貪婪"},
            "vix": {"green": "🟢 恐慌噴出 (買點亮燈)", "yellow": "🟡 波動升溫", "red": "🔴 市場平靜"},
            "aaii": {"green": "🟢 散戶投降 (買點亮燈)", "yellow": "🟡 散戶偏空", "red": "🔴 散戶偏多/中性"}
        },
        "section_table": "📈 多週期實證回測勝率與報酬對照表 (2011 年至今)",
        "tbl_cols": ["持有週期", "綜合勝率", "達 90% 警報", "CNN 勝率", "VIX 勝率", "AAII 加權", "S&P 500 平均報酬", "NASDAQ-100 平均報酬", "歷史樣本數"],
        "yes": "✅ 是",
        "days_unit": " 天",
        "section_chart": "📉 近一年 CNN 恐慌指數與 VIX 歷史走勢",
        "no_data": "⚠️ 尚未產生資料檔，請先至 GitHub Actions 手動執行一次 `Update Fear & Greed Data`。",
        "academic_md": """
### 一、研究背景與設計理念（Academic Rationale）

傳統效率市場假說（EMH）認為資產價格已充分反映所有資訊；然而，**行為財務學（Behavioral Finance）**的大量實證研究指出，投資人受到恐懼、從眾行為（Herding）與有限套利（Limits to Arbitrage）影響，會在市場極度悲觀時產生過度反應（Overreaction），導致資產價格偏離基本面，進而在未來數月至一年內出現顯著的**均值回歸（Mean Reversion）與正報酬溢酬**。

本系統將學術界最具代表性的三類情緒代理變數（Sentiment Proxies）進行跨維度整合：
1. **隱含波動率指標（CBOE VIX）**：反映選擇權市場機構法人對未來 30 天下檔風險的避險需求與恐慌定價。
2. **調查型散戶情緒（AAII Sentiment Survey）**：直接衡量個別投資人的多空預期偏差，驗證散戶情緒作為「反向指標（Contrary Indicator）」的預測力。
3. **多因子複合市場情緒（CNN Fear & Greed Index）**：整合動能、股價強度、寬度、Put/Call 比率、垃圾債利差與避險需求等 7 項市場微結構指標。

---

### 二、核心學術參考文獻（Key Academic References）

* **1. VIX「投資人恐慌指標」的理論建構與實證**
  * **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12–17. https://doi.org/10.3905/jpm.2000.319728
  * **學術貢獻**：VIX 編製者 Robert Whaley 正式提出「投資人恐慌指標」概念，闡明當市場遭遇劇烈賣壓時，投資人急於買入賣權避險會推升隱含波動率，使 VIX 成為捕捉市場非理性恐慌高峰的核心指標。

* **2. 恐慌指標作為「逆向交易訊號」的期貨與現貨報酬實證**
  * **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447–462. https://doi.org/10.1002/fut.1602
  * **學術貢獻**：實證檢驗 VIX、Put-Call Ratio 與市場情緒指標的預測能力，證實當恐慌指標處於極端高檔時買進標普指數，其後續風險調整後報酬顯著優於低恐慌時期，且持有期越長（如 3 至 6 個月），反轉效果越穩健。

* **3. AAII 散戶投資人情緒與未來股票報酬的負相關實證**
  * **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16–23. https://doi.org/10.2469/faj.v56.n2.2340
  * **學術貢獻**：分析美國個人投資人協會（AAII）調查數據，發現散戶投資人情緒與未來股市報酬呈現統計上顯著的**負相關**——即散戶極度看空時，往往對應未來數月較高的正向股票報酬。

* **4. 投資人情緒對橫斷面股票報酬與評價偏誤的影響**
  * **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645–1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x
  * **學術貢獻**：建構複合投資人情緒指數，證實情緒波動會系統性造成定價偏誤，且當悲觀情緒到達極端低谷後，高波動與成長型標的（如 NASDAQ-100 成分股）在後續反彈階段展現更強的報酬修復力。

* **5. 市場恐慌指標（FEARS Index）與短期過度反應反轉**
  * **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1–32. https://doi.org/10.1093/rfs/hhu072
  * **學術貢獻**：透過高頻恐慌指標驗證市場層級的「過度反應假說」，指出恐慌情緒推升折現率並壓低當期股價，隨後在恐慌消退時產生可預測的價格回升。

---

### 三、實證回測方法論（Empirical Methodology）
* **樣本期間**：2011 年 1 月 1 日至今之日頻交易資料（涵蓋歐債危機、2015 人民幣匯改、2018 升息縮表、2020 COVID-19 熔斷、2022 暴力升息及近年波動週期）。
* **條件機率勝率計算**：針對任意交易日 $t$，篩選歷史上同時滿足 $CNN_t \\le CNN_{current}$ 且 $VIX_t \\ge VIX_{current}$ 之所有事件日，計算未來 $H \\in \\{21, 63, 126, 252\\}$ 個交易日之遠期報酬率 $R_{t, t+H} = \\frac{P_{t+H}}{P_t} - 1 > 0$ 的經驗勝率，並依 Fisher & Statman (2000) 實證結論納入 AAII 散戶極端看空加權修正。
* **研究限制聲明**：本系統為行為財務學實證模型之教育與研究展示，歷史條件機率不保證未來必然獲利，使用者應搭配資產配置與風險控管。
"""
    },
    "en": {
        "lang_name": "English",
        "app_title": "📡 Behavioral Finance in Action: US Sentiment & Win-Rate Radar",
        "app_subtitle": "An Empirical Contrarian Dashboard Integrating CNN Fear & Greed, CBOE VIX, and AAII Sentiment Survey",
        "settings_header": "⚙️ Settings",
        "lang_label": "🌐 Language / 語言",
        "theme_label": "🎨 Color Theme",
        "themes": ["Warm Paper", "Clean White", "Deep Dark"],
        "font_label": "🔠 Base Font Size (px)",
        "sidebar_note": "This application translates empirical Behavioral Finance findings on investor sentiment and return reversals into an automated quantitative monitor.",
        "meta_line": "Updated: {updated} ｜ Visitors: {visitors:,} ｜ Email Alert Threshold: ≥ {threshold}%",
        "tab_dashboard": "📊 Live Sentiment & Win-Rate Dashboard",
        "tab_academic": "📚 Academic Foundations & Literature",
        "horizon_prompt": "Select Forward Holding Horizon for Empirical Backtest:",
        "horizons": {
            "126D": "6 Months (126 Trading Days) — Swing Benchmark",
            "252D": "1 Year (252 Trading Days) — Long-Term Mean Reversion",
            "63D": "3 Months (63 Trading Days) — Quarterly Rebound",
            "21D": "1 Month (21 Trading Days) — Short-Term Oversold"
        },
        "alert_triggered": "🚨 ≥ 90% High Win-Rate Email Alert Triggered!",
        "alert_waiting": "⏳ Fear Accumulating — Below 90% Alert Threshold",
        "win_banner_title": "🎯 {horizon} Empirical Win Rate: {status}",
        "green_lights_count": "Contrarian Green Lights: {count} / 3",
        "sample_stats": "Historical Analogous Days: <b>{samples} days</b> ｜ S&P 500 Avg Return: <b>{sp:+.2f}%</b> ｜ NASDAQ-100 Avg Return: <b>{ndx:+.2f}%</b>",
        "section_cards": "🚦 Real-Time Sentiment Indicator Signals",
        "card1_title": "1. CNN Fear & Greed Index",
        "card1_sub": "Rating: {rating} (Prev: {prev})<br>Standalone Win Rate: <b>{win}%</b>",
        "card2_title": "2. CBOE VIX Volatility Index",
        "card2_sub": "Prev Close: {prev} (Green Light ≥ 30)<br>Standalone Win Rate: <b>{win}%</b>",
        "card3_title": "3. AAII Retail Bearishness ({date})",
        "card3_sub": "Bullish {bull}% / Neutral {neut}% (Spread: {spread}%)<br>Extreme Bearish Bonus: <b>+{bonus}%</b>",
        "bearish_unit": "Bearish",
        "lights": {
            "cnn": {"green": "🟢 Extreme Fear (Buy Signal)", "yellow": "🟡 Fear Watch", "red": "🔴 Neutral / Greed"},
            "vix": {"green": "🟢 Panic Spike (Buy Signal)", "yellow": "🟡 Elevated Vol", "red": "🔴 Calm Market"},
            "aaii": {"green": "🟢 Retail Capitulation (Buy Signal)", "yellow": "🟡 Retail Bearish", "red": "🔴 Neutral / Bullish"}
        },
        "section_table": "📈 Multi-Horizon Empirical Win Rates & Forward Returns (2011–Present)",
        "tbl_cols": ["Holding Horizon", "Composite Win Rate", "≥ 90% Alert", "CNN Win Rate", "VIX Win Rate", "AAII Bonus", "S&P 500 Avg Return", "NASDAQ-100 Avg Return", "Sample Size"],
        "yes": "✅ Yes",
        "days_unit": " days",
        "section_chart": "📉 Trailing 1-Year CNN Fear & Greed vs. VIX Trend",
        "no_data": "⚠️ No dataset found yet. Please trigger `Update Fear & Greed Data` manually in GitHub Actions first.",
        "academic_md": """
### 1. Academic Rationale & Research Motivation

While the classical Efficient Market Hypothesis (EMH) posits that asset prices fully reflect all available information, empirical **Behavioral Finance** demonstrates that cognitive biases, herding, and limits to arbitrage induce systematic **overreaction** during episodes of acute market fear. When pessimism reaches extreme levels, asset prices temporarily undershoot fundamental values, generating statistically significant **mean reversion and positive forward return premia**.

This tool operationalizes three canonical classes of market sentiment proxies:
1. **Option-Implied Volatility (CBOE VIX):** Captures institutional hedging demand and tail-risk pricing across S&P 500 index options.
2. **Survey-Based Retail Sentiment (AAII Sentiment Survey):** Directly measures individual investors' directional expectations, empirically documented as a reliable contrarian indicator.
3. **Composite Market Microstructure Sentiment (CNN Fear & Greed Index):** Aggregates seven market-based indicators including momentum, stock price breadth, put/call ratios, junk bond demand, and safe-haven flows.

---

### 2. Core Peer-Reviewed Literature

* **1. Conceptualization of the VIX as an Investor Fear Gauge**
  * **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12–17. https://doi.org/10.3905/jpm.2000.319728
  * **Key Finding:** Introduces the VIX as a forward-looking barometer of investor anxiety, showing that surges in index put buying during market sell-offs drive implied volatility spikes that mark capitulation points.

* **2. Contrarian Predictability of Fear Indicators on Equity Index Returns**
  * **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447–462. https://doi.org/10.1002/fut.1602
  * **Key Finding:** Demonstrates that buying S&P futures when fear indicators (including VIX and put-call ratios) reach extreme highs yields superior subsequent returns and risk-adjusted performance, with predictability strengthening over multi-month horizons.

* **3. Negative Relation Between Retail Investor Sentiment and Future Stock Returns**
  * **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16–23. https://doi.org/10.2469/faj.v56.n2.2340
  * **Key Finding:** Examines AAII survey data and documents a statistically significant negative relationship between individual investor sentiment and subsequent S&P 500 returns, validating extreme retail bearishness as a contrarian buy signal.

* **4. Cross-Sectional Effects of Investor Sentiment and Mispricing Reversals**
  * **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645–1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x
  * **Key Finding:** Shows that waves of investor sentiment create systematic mispricing, particularly in high-beta and growth-oriented equities (such as NASDAQ-100 constituents), which exhibit stronger subsequent return rebounds once pessimism subsides.

* **5. Market-Level Fear and Overreaction Reversals**
  * **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1–32. https://doi.org/10.1093/rfs/hhu072
  * **Key Finding:** Provides high-frequency empirical evidence supporting the overreaction hypothesis at the aggregate market level, showing that temporary sentiment-driven price declines reverse predictably over subsequent periods.

---

### 3. Empirical Backtesting Methodology
* **Sample Period:** Daily market observations from January 2011 to present.
* **Conditional Probability Estimation:** For any trading day $t$, the engine filters all historical dates satisfying $CNN_t \\le CNN_{current}$ and $VIX_t \\ge VIX_{current}$, computing the empirical win rate $P(R_{t, t+H} > 0)$ over forward horizons $H \\in \\{21, 63, 126, 252\\}$ trading days, augmented by an AAII bearishness adjustment grounded in Fisher & Statman (2000).
* **Disclaimer:** Designed for academic research and educational illustration of behavioral finance principles. Historical conditional probabilities do not guarantee future performance.
"""
    },
    "ja": {
        "lang_name": "日本語",
        "app_title": "📡 行動ファイナンス応用：米国株恐怖指数・実証勝率レーダー",
        "app_subtitle": "CNN Fear & Greed・CBOE VIX・AAII 個人投資家センチメントを統合した逆張り実証分析システム",
        "settings_header": "⚙️ システム設定 (Settings)",
        "lang_label": "🌐 表示言語 / Language",
        "theme_label": "🎨 背景テーマ",
        "themes": ["アイボリー", "ピュアホワイト", "ダークモード"],
        "font_label": "🔠 フォントサイズ (px)",
        "sidebar_note": "行動ファイナンスにおける「投資家心理とリターン反転」の実証研究を自動モニタリングツールとして実装したアプリケーションです。",
        "meta_line": "最終更新：{updated} ｜ 累計訪問者数：{visitors:,} ｜ メール通知閾値：≥ {threshold}%",
        "tab_dashboard": "📊 リアルタイム指標・勝率ダッシュボード",
        "tab_academic": "📚 学術的根拠・参考文献",
        "horizon_prompt": "実証バックテストの保有期間を選択：",
        "horizons": {
            "126D": "6ヶ月 (126営業日) — 中期スイング基準",
            "252D": "1年 (252営業日) — 長期平均回帰",
            "63D": "3ヶ月 (63営業日) — 四半期リバウンド",
            "21D": "1ヶ月 (21営業日) — 短期売られすぎ"
        },
        "alert_triggered": "🚨 勝率90%以上の高勝率アラート条件を達成しました！",
        "alert_waiting": "⏳ 恐怖心理の蓄積中（90%通知閾値未満）",
        "win_banner_title": "🎯 {horizon} 歴史的実証勝率：{status}",
        "green_lights_count": "逆張り買いシグナル点灯数：{count} / 3 灯",
        "sample_stats": "過去の類似条件サンプル：<b>{samples} 営業日</b> ｜ S&P 500 平均リターン：<b>{sp:+.2f}%</b> ｜ NASDAQ-100 平均リターン：<b>{ndx:+.2f}%</b>",
        "section_cards": "🚦 三大市場センチメント指標シグナル",
        "card1_title": "1. CNN 恐怖と強欲指数",
        "card1_sub": "評価：{rating}（前日 {prev}）<br>単独指標の歴史的勝率：<b>{win}%</b>",
        "card2_title": "2. CBOE VIX 恐怖指数",
        "card2_sub": "前日終値：{prev}（閾値 ≥ 30 で緑点灯）<br>単独指標の歴史的勝率：<b>{win}%</b>",
        "card3_title": "3. AAII 個人投資家弱気比率 ({date})",
        "card3_sub": "強気 {bull}% / 中立 {neut}%（強弱スプレッド {spread}%）<br>極端な弱気補正：<b>+{bonus}%</b>",
        "bearish_unit": "弱気",
        "lights": {
            "cnn": {"green": "🟢 極度の恐怖 (買い点灯)", "yellow": "🟡 恐怖警戒", "red": "🔴 中立・強欲"},
            "vix": {"green": "🟢 パニック急騰 (買い点灯)", "yellow": "🟡 ボラティリティ上昇", "red": "🔴 市場安定"},
            "aaii": {"green": "🟢 個人投資家総悲観 (買い点灯)", "yellow": "🟡 弱気優勢", "red": "🔴 強気・中立"}
        },
        "section_table": "📈 保有期間別・実証勝率および平均リターン比較表 (2011年〜現在)",
        "tbl_cols": ["保有期間", "総合勝率", "90%警報", "CNN勝率", "VIX勝率", "AAII補正", "S&P 500 平均リターン", "NASDAQ-100 平均リターン", "サンプル数"],
        "yes": "✅ 達成",
        "days_unit": " 日",
        "section_chart": "📉 直近1年間の CNN 恐怖指数と VIX 推移",
        "no_data": "⚠️ データファイルが未生成です。先に GitHub Actions から `Update Fear & Greed Data` を手動実行してください。",
        "academic_md": """
### 1. 研究背景と設計コンセプト（Academic Rationale）

伝統的な効率的市場仮説（EMH）に対し、**行動ファイナンス（Behavioral Finance）**の実証研究では、投資家の恐怖心・群集行動（Herding）・裁定の限界により、極度の悲観局面で市場が**過剰反応（Overreaction）**を起こし、その後の数ヶ月から1年にかけて統計的に有意な**平均回帰（Mean Reversion）と正のリターンプレミアム**が生じることが示されています。

本システムでは、学術研究で広く用いられる3つのセンチメント指標を統合しています：
1. **インプライド・ボラティリティ（CBOE VIX）**：オプション市場における機関投資家のヘッジ需要と恐怖心理の価格付けを反映。
2. **個人投資家サーベイ（AAII Sentiment Survey）**：個人投資家の強弱見通しを直接測定し、逆張り指標（Contrary Indicator）としての有効性を検証。
3. **複合市場センチメント（CNN Fear & Greed Index）**：モメンタムやプット・コール・レシオなど7つの市場マイクロストラクチャー指標を統合。

---

### 2. 主要学術参考文献（Key Academic References）

* **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12–17. https://doi.org/10.3905/jpm.2000.319728
  * VIX開発者による原典論文。市場急落時のプット買い急増がVIXを押し上げ、「投資家の恐怖指数」として機能することを解明。
* **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447–462. https://doi.org/10.1002/fut.1602
  * VIX等の恐怖指標が極端な高水準にある際の逆張り買いが、その後のリスク調整後リターンを統計的に向上させることを実証。
* **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16–23. https://doi.org/10.2469/faj.v56.n2.2340
  * AAII調査データを用い、個人投資家センチメントと将来の株式リターンとの間に有意な負の相関（極端な弱気後の上昇）があることを報告。
* **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645–1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x
  * 投資家センチメントの波が価格形成の歪みを生み、悲観の極みからの反転局面ではグロース株（NASDAQ-100等）の反発力が特に強いことを実証。
* **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1–32. https://doi.org/10.1093/rfs/hhu072
  * 市場全体の恐怖指数（FEARS）による一時的な価格下落が、その後の期間で予測可能な反転上昇をもたらす過剰反応仮説を検証。
"""
    }
}


def update_visitor_counter():
    """訪客計數器（從 1,000 起跳）"""
    os.makedirs("data", exist_ok=True)
    if "counted" not in st.session_state:
        count = 1000
        if os.path.exists(COUNTER_PATH):
            try:
                with open(COUNTER_PATH, "r") as f:
                    count = int(f.read().strip())
            except Exception:
                count = 1000
        count += 1
        with open(COUNTER_PATH, "w") as f:
            f.write(str(count))
        st.session_state["counted"] = True
        st.session_state["visitor_count"] = count
    return st.session_state.get("visitor_count", 1001)


# ================= 側邊欄：多語系與外觀設定 =================
with st.sidebar:
    lang_options = {"zh-TW": "繁體中文", "en": "English", "ja": "日本語"}
    selected_lang = st.selectbox(
        "🌐 Language / 語言 / 言語",
        options=list(lang_options.keys()),
        format_func=lambda k: lang_options[k],
        index=0
    )
    t = I18N[selected_lang]

    st.header(t["settings_header"])
    theme_idx = st.selectbox(
        t["theme_label"],
        options=[0, 1, 2],
        format_func=lambda i: t["themes"][i],
        index=0
    )
    font_size = st.slider(t["font_label"], min_value=14, max_value=22, value=16, step=1)
    st.divider()
    st.caption(t["sidebar_note"])

THEME_PALETTES = [
    {"bg": "#FAF8F5", "card": "#FFFFFF", "text": "#1F2937", "border": "#E5E7EB"},  # Warm Paper
    {"bg": "#FFFFFF", "card": "#F9FAFB", "text": "#111827", "border": "#E5E7EB"},  # Clean White
    {"bg": "#0F172A", "card": "#1E293B", "text": "#F8FAFC", "border": "#334155"},  # Deep Dark
]
style = THEME_PALETTES[theme_idx]

st.markdown(f"""
<style>
    .stApp {{
        background-color: {style['bg']};
        color: {style['text']};
        font-size: {font_size}px;
    }}
    .radar-card {{
        background-color: {style['card']};
        border: 1px solid {style['border']};
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .metric-big {{
        font-size: {font_size + 14}px;
        font-weight: 800;
        margin: 6px 0;
    }}
    .badge-green {{
        background-color: #DCFCE7; color: #166534;
        padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: {font_size - 2}px;
    }}
    .badge-yellow {{
        background-color: #FEF9C3; color: #854D0E;
        padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: {font_size - 2}px;
    }}
    .badge-red {{
        background-color: #FEE2E2; color: #991B1B;
        padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: {font_size - 2}px;
    }}
</style>
""", unsafe_allow_html=True)

# ================= 主畫面標題與分頁 =================
visitors = update_visitor_counter()
st.title(t["app_title"])
st.markdown(f"**{t['app_subtitle']}**")

if not os.path.exists(JSON_PATH):
    st.warning(t["no_data"])
    tab1, tab2 = st.tabs([t["tab_dashboard"], t["tab_academic"]])
    with tab2:
        st.markdown(t["academic_md"])
    st.stop()

with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

st.caption(t["meta_line"].format(
    updated=data["updated_at"],
    visitors=visitors,
    threshold=data["alert_threshold"]
))

tab_dash, tab_acad = st.tabs([t["tab_dashboard"], t["tab_academic"]])

with tab_dash:
    cnn = data["cnn"]
    vix = data["vix"]
    aaii = data["aaii"]
    lights = data["lights"]
    win_rates = data["win_rates"]

    h_keys = list(t["horizons"].keys())
    h_code = st.radio(
        t["horizon_prompt"],
        options=h_keys,
        format_func=lambda k: t["horizons"][k],
        horizontal=True
    )
    current_stat = win_rates[h_code]
    win_val = current_stat["final_win_rate"]
    status_str = t["alert_triggered"] if win_val >= 90 else t["alert_waiting"]

    # 頂部實證勝率總覽卡片
    st.markdown(f"""
    <div class="radar-card" style="border-left: 6px solid {'#16A34A' if win_val >= 90 else '#F59E0B'};">
        <div style="font-weight: 700; opacity: 0.9;">{t['win_banner_title'].format(horizon=t['horizons'][h_code].split('—')[0].strip(), status=status_str)}</div>
        <div class="metric-big" style="color: {'#16A34A' if win_val >= 90 else '#D97706'};">
            {win_val}% <span style="font-size: {font_size}px; font-weight: 500;">（{t['green_lights_count'].format(count=lights['green_count'])}）</span>
        </div>
        <div>{t['sample_stats'].format(samples=current_stat['sample_size'], sp=current_stat['sp_avg_ret'], ndx=current_stat['ndx_avg_ret'])}</div>
    </div>
    """, unsafe_allow_html=True)

    # 三大指標 RWD 卡片
    st.subheader(t["section_cards"])
    col1, col2, col3 = st.columns(3)

    with col1:
        lvl = lights["cnn_level"]
        st.markdown(f"""
        <div class="radar-card">
            <div style="font-weight:700;">{t['card1_title']}</div>
            <div class="metric-big">{cnn['score']} <span style="font-size:{font_size-2}px;">/ 100</span></div>
            <span class="badge-{lvl}">{t['lights']['cnn'][lvl]}</span>
            <p style="margin-top:10px; opacity:0.85;">{t['card1_sub'].format(rating=cnn['rating'].title(), prev=cnn['prev_close'], win=current_stat['win_cnn'])}</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        lvl = lights["vix_level"]
        st.markdown(f"""
        <div class="radar-card">
            <div style="font-weight:700;">{t['card2_title']}</div>
            <div class="metric-big">{vix['vix']}</div>
            <span class="badge-{lvl}">{t['lights']['vix'][lvl]}</span>
            <p style="margin-top:10px; opacity:0.85;">{t['card2_sub'].format(prev=vix['vix_prev'], win=current_stat['win_vix'])}</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        lvl = lights["aaii_level"]
        st.markdown(f"""
        <div class="radar-card">
            <div style="font-weight:700;">{t['card3_title'].format(date=aaii['date'])}</div>
            <div class="metric-big">{aaii['bearish']}% <span style="font-size:{font_size-2}px;">{t['bearish_unit']}</span></div>
            <span class="badge-{lvl}">{t['lights']['aaii'][lvl]}</span>
            <p style="margin-top:10px; opacity:0.85;">{t['card3_sub'].format(bull=aaii['bullish'], neut=aaii['neutral'], spread=aaii['spread'], bonus=current_stat['aaii_bonus'])}</p>
        </div>
        """, unsafe_allow_html=True)

    # 多週期實證比較表
    st.subheader(t["section_table"])
    cols = t["tbl_cols"]
    rows = []
    for code in ["21D", "63D", "126D", "252D"]:
        item = win_rates[code]
        rows.append({
            cols[0]: t["horizons"][code].split("—")[0].strip(),
            cols[1]: f"{item['final_win_rate']}%",
            cols[2]: t["yes"] if item["final_win_rate"] >= 90 else "—",
            cols[3]: f"{item['win_cnn']}%",
            cols[4]: f"{item['win_vix']}%",
            cols[5]: f"+{item['aaii_bonus']}%",
            cols[6]: f"{item['sp_avg_ret']:+.2f}%",
            cols[7]: f"{item['ndx_avg_ret']:+.2f}%",
            cols[8]: f"{item['sample_size']}{t['days_unit']}"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 近一年趨勢圖
    if os.path.exists(CSV_PATH):
        st.subheader(t["section_chart"])
        df_hist = pd.read_csv(CSV_PATH).set_index("Date")
        st.line_chart(df_hist[["CNN_FG", "VIX"]])

with tab_acad:
    st.markdown(t["academic_md"])
