import json
import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Behavioral Sentiment & Win-Rate Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

JSON_PATH = os.path.join("data", "sentiment_data.json")
CSV_PATH = os.path.join("data", "history_backtest.csv")
COUNTER_PATH = os.path.join("data", "visitor_count.txt")

I18N = {
    "zh-TW": {
        "lang_name": "繁體中文",
        "app_title": "📡 行為財務學應用：美股恐慌指標與實證勝率雷達",
        "app_subtitle": "整合 CNN Fear & Greed、CBOE VIX 與 AAII 散戶情緒調查之逆向投資量化實證系統",
        "settings_header": "⚙️ 系統設定 (Settings)",
        "lang_label": "🌐 Language / 語言 / 言語",
        "theme_label": "🎨 背景色系",
        "themes": ["護眼米白", "極簡純白", "深邃暗黑"],
        "font_label": "🔠 全站字體大小 (px)",
        "sidebar_note": "本系統將行為財務學中「投資人情緒與報酬反轉」之實證研究轉化為自動化監控工具。",
        "meta_line": "資料更新：{updated} ｜ 累積瀏覽人次：{visitors:,} ｜ 寄信警報門檻：≥ {threshold}%",
        "tab_dashboard": "📊 即時指標與勝率儀表板",
        "tab_academic": "📚 學術理論基礎與參考文獻",
        "horizon_prompt": "選擇實證回測持有週期：",
        "horizons": {
            "126D": "6 個月 (126 交易日) — 中期波段基準",
            "252D": "1 年 (252 交易日) — 長期均值回歸",
            "63D": "3 個月 (63 交易日) — 季度反彈觀察",
            "21D": "1 個月 (21 交易日) — 短期情緒超賣",
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
            "aaii": {"green": "🟢 散戶投降 (買點亮燈)", "yellow": "🟡 散戶偏空", "red": "🔴 散戶偏多/中性"},
        },
        "section_table": "📈 多週期實證回測勝率與報酬對照表 (2011 年至今)",
        "tbl_cols": ["持有週期", "綜合勝率", "達 90% 警報", "CNN 勝率", "VIX 勝率", "AAII 加權", "S&P 500 平均報酬", "NASDAQ-100 平均報酬", "歷史樣本數"],
        "yes": "✅ 是",
        "days_unit": " 天",
        "section_chart": "📉 近一年 CNN 恐慌指數與 VIX 歷史走勢",
        "no_data": "⚠️ 尚未產生資料檔，請先至 GitHub Actions 手動執行一次 Update Fear & Greed Data。",
        "academic_md": (
            "### 一、研究背景與設計理念\n\n"
            "行為財務學實證研究指出，投資人在極度悲觀時容易產生過度反應，使價格偏離基本面並在後續數月至一年出現均值回歸與正報酬溢酬。"
            "本系統整合隐含波動率（CBOE VIX）、散戶調查情緒（AAII）與複合市場情緒（CNN Fear & Greed）進行實證回測。\n\n"
            "### 二、核心學術參考文獻\n\n"
            "- **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12-17. https://doi.org/10.3905/jpm.2000.319728\n"
            "- **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447-462. https://doi.org/10.1002/fut.1602\n"
            "- **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16-23. https://doi.org/10.2469/faj.v56.n2.2340\n"
            "- **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645-1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x\n"
            "- **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1-32. https://doi.org/10.1093/rfs/hhu072\n\n"
            "### 三、研究限制聲明\n\n"
            "本系統為行為財務學實證模型之教育與研究應用，歷史條件機率不保證未來必然獲利。"
        ),
    },
    "en": {
        "lang_name": "English",
        "app_title": "📡 Behavioral Finance in Action: US Sentiment & Win-Rate Radar",
        "app_subtitle": "An Empirical Contrarian Dashboard Integrating CNN Fear & Greed, CBOE VIX, and AAII Sentiment Survey",
        "settings_header": "⚙️ Settings",
        "lang_label": "🌐 Language / 語言 / 言語",
        "theme_label": "🎨 Color Theme",
        "themes": ["Warm Paper", "Clean White", "Deep Dark"],
        "font_label": "🔠 Base Font Size (px)",
        "sidebar_note": "Translates empirical Behavioral Finance research on investor sentiment and return reversals into an automated monitor.",
        "meta_line": "Updated: {updated} ｜ Visitors: {visitors:,} ｜ Email Alert Threshold: ≥ {threshold}%",
        "tab_dashboard": "📊 Live Sentiment & Win-Rate Dashboard",
        "tab_academic": "📚 Academic Foundations & Literature",
        "horizon_prompt": "Select Forward Holding Horizon:",
        "horizons": {
            "126D": "6 Months (126 Trading Days) — Swing Benchmark",
            "252D": "1 Year (252 Trading Days) — Long-Term Mean Reversion",
            "63D": "3 Months (63 Trading Days) — Quarterly Rebound",
            "21D": "1 Month (21 Trading Days) — Short-Term Oversold",
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
            "aaii": {"green": "🟢 Retail Capitulation (Buy Signal)", "yellow": "🟡 Retail Bearish", "red": "🔴 Neutral / Bullish"},
        },
        "section_table": "📈 Multi-Horizon Empirical Win Rates & Forward Returns (2011–Present)",
        "tbl_cols": ["Holding Horizon", "Composite Win Rate", "≥ 90% Alert", "CNN Win Rate", "VIX Win Rate", "AAII Bonus", "S&P 500 Avg Return", "NASDAQ-100 Avg Return", "Sample Size"],
        "yes": "✅ Yes",
        "days_unit": " days",
        "section_chart": "📉 Trailing 1-Year CNN Fear & Greed vs. VIX Trend",
        "no_data": "⚠️ No dataset found yet. Please run Update Fear & Greed Data in GitHub Actions first.",
        "academic_md": (
            "### 1. Academic Rationale\n\n"
            "Empirical behavioral finance shows that extreme pessimism often triggers overreaction and subsequent mean reversion with positive forward return premia. "
            "This dashboard integrates implied volatility (CBOE VIX), survey-based retail sentiment (AAII), and composite market sentiment (CNN Fear & Greed).\n\n"
            "### 2. Core Academic References\n\n"
            "- **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12-17. https://doi.org/10.3905/jpm.2000.319728\n"
            "- **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447-462. https://doi.org/10.1002/fut.1602\n"
            "- **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16-23. https://doi.org/10.2469/faj.v56.n2.2340\n"
            "- **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645-1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x\n"
            "- **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1-32. https://doi.org/10.1093/rfs/hhu072\n\n"
            "### 3. Disclaimer\n\n"
            "Built for academic research and educational illustration of behavioral finance models. Historical probabilities do not guarantee future returns."
        ),
    },
    "ja": {
        "lang_name": "日本語",
        "app_title": "📡 行動ファイナンス応用：米国株恐怖指数・実証勝率レーダー",
        "app_subtitle": "CNN Fear & Greed・CBOE VIX・AAII 個人投資家センチメントを統合した逆張り実証分析システム",
        "settings_header": "⚙️ システム設定 (Settings)",
        "lang_label": "🌐 Language / 語言 / 言語",
        "theme_label": "🎨 背景テーマ",
        "themes": ["アイボリー", "ピュアホワイト", "ダークモード"],
        "font_label": "🔠 フォントサイズ (px)",
        "sidebar_note": "行動ファイナンスにおける投資家心理とリターン反転の実証研究を自動モニタリングツールとして実装しています。",
        "meta_line": "最終更新：{updated} ｜ 累計訪問者数：{visitors:,} ｜ メール通知閾値：≥ {threshold}%",
        "tab_dashboard": "📊 リアルタイム指標・勝率ダッシュボード",
        "tab_academic": "📚 学術的根拠・参考文献",
        "horizon_prompt": "実証バックテストの保有期間を選択：",
        "horizons": {
            "126D": "6ヶ月 (126営業日) — 中期スイング基準",
            "252D": "1年 (252営業日) — 長期平均回帰",
            "63D": "3ヶ月 (63営業日) — 四半期リバウンド",
            "21D": "1ヶ月 (21営業日) — 短期売られすぎ",
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
            "aaii": {"green": "🟢 個人投資家総悲観 (買い点灯)", "yellow": "🟡 弱気優勢", "red": "🔴 強気・中立"},
        },
        "section_table": "📈 保有期間別・実証勝率および平均リターン比較表 (2011年〜現在)",
        "tbl_cols": ["保有期間", "総合勝率", "90%警報", "CNN勝率", "VIX勝率", "AAII補正", "S&P 500 平均リターン", "NASDAQ-100 平均リターン", "サンプル数"],
        "yes": "✅ 達成",
        "days_unit": " 日",
        "section_chart": "📉 直近1年間の CNN 恐怖指数と VIX 推移",
        "no_data": "⚠️ データファイルが未生成です。先に GitHub Actions から Update Fear & Greed Data を実行してください。",
        "academic_md": (
            "### 1. 研究背景と設計コンセプト\n\n"
            "行動ファイナンスの実証研究では、極度の悲観局面で市場が過剰反応を起こし、その後の数ヶ月から1年にかけて平均回帰と正のリターンプレミアムが生じることが示されています。"
            "本システムはインプライド・ボラティリティ（VIX）、個人投資家サーベイ（AAII）、複合市場センチメント（CNN Fear & Greed）を統合しています。\n\n"
            "### 2. 主要学術参考文献\n\n"
            "- **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12-17. https://doi.org/10.3905/jpm.2000.319728\n"
            "- **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447-462. https://doi.org/10.1002/fut.1602\n"
            "- **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16-23. https://doi.org/10.2469/faj.v56.n2.2340\n"
            "- **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645-1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x\n"
            "- **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1-32. https://doi.org/10.1093/rfs/hhu072\n\n"
            "### 3. 免責事項\n\n"
            "本アプリケーションは行動ファイナンスの実証モデルを学ぶための学術・教育用途であり、将来のリターンを保証するものではありません。"
        ),
    },
}


def update_visitor_counter():
    os.makedirs("data", exist_ok=True)
    if "counted" not in st.session_state:
        count = 1000
        if os.path.exists(COUNTER_PATH):
            try:
                with open(COUNTER_PATH, "r", encoding="utf-8") as f:
                    count = int(f.read().strip())
            except Exception:
                count = 1000
        count += 1
        with open(COUNTER_PATH, "w", encoding="utf-8") as f:
            f.write(str(count))
        st.session_state["counted"] = True
        st.session_state["visitor_count"] = count
    return st.session_state.get("visitor_count", 1001)


with st.sidebar:
    lang_keys = ["zh-TW", "en", "ja"]
    selected_lang = st.selectbox(
        "🌐 Language / 語言 / 言語",
        options=lang_keys,
        format_func=lambda k: I18N[k]["lang_name"],
        index=0,
    )
    t = I18N[selected_lang]

    st.header(t["settings_header"])
    theme_idx = st.selectbox(
        t["theme_label"],
        options=[0, 1, 2],
        format_func=lambda i: t["themes"][i],
        index=0,
    )
    font_size = st.slider(t["font_label"], min_value=14, max_value=22, value=16, step=1)
    st.divider()
    st.caption(t["sidebar_note"])

THEME_PALETTES = [
    {"bg": "#FAF8F5", "card": "#FFFFFF", "text": "#1F2937", "border": "#E5E7EB"},
    {"bg": "#FFFFFF", "card": "#F9FAFB", "text": "#111827", "border": "#E5E7EB"},
    {"bg": "#0F172A", "card": "#1E293B", "text": "#F8FAFC", "border": "#334155"},
]
style = THEME_PALETTES[theme_idx]

css_block = (
    "<style>"
    ".stApp { background-color: " + style["bg"] + "; color: " + style["text"] + "; font-size: " + str(font_size) + "px; }"
    ".radar-card { background-color: " + style["card"] + "; border: 1px solid " + style["border"] + "; border-radius: 14px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }"
    ".metric-big { font-size: " + str(font_size + 14) + "px; font-weight: 800; margin: 6px 0; }"
    ".badge-green { background-color: #DCFCE7; color: #166534; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    ".badge-yellow { background-color: #FEF9C3; color: #854D0E; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    ".badge-red { background-color: #FEE2E2; color: #991B1B; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    "</style>"
)
st.markdown(css_block, unsafe_allow_html=True)

visitors = update_visitor_counter()
st.title(t["app_title"])
st.markdown("**" + t["app_subtitle"] + "**")

if not os.path.exists(JSON_PATH):
    st.warning(t["no_data"])
    _, tab_acad_only = st.tabs([t["tab_dashboard"], t["tab_academic"]])
    with tab_acad_only:
        st.markdown(t["academic_md"])
    st.stop()

with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

st.caption(
    t["meta_line"].format(
        updated=data.get("updated_at", ""),
        visitors=visitors,
        threshold=data.get("alert_threshold", 90.0),
    )
)

tab_dash, tab_acad = st.tabs([t["tab_dashboard"], t["tab_academic"]])

with tab_dash:
    cnn = data["cnn"]
    vix = data["vix"]
    aaii = data["aaii"]
    lights = data["lights"]
    win_rates = data["win_rates"]

    h_keys = ["126D", "252D", "63D", "21D"]
    h_code = st.radio(
        t["horizon_prompt"],
        options=h_keys,
        format_func=lambda k: t["horizons"][k],
        horizontal=True,
    )
    current_stat = win_rates[h_code]
    win_val = current_stat["final_win_rate"]
    status_str = t["alert_triggered"] if win_val >= 90 else t["alert_waiting"]
    banner_color = "#16A34A" if win_val >= 90 else "#F59E0B"
    win_color = "#16A34A" if win_val >= 90 else "#D97706"
    horizon_short = t["horizons"][h_code].split("—")[0].strip()

    banner_html = (
        "<div class='radar-card' style='border-left: 6px solid " + banner_color + ";'>"
        "<div style='font-weight: 700; opacity: 0.9;'>"
        + t["win_banner_title"].format(horizon=horizon_short, status=status_str)
        + "</div>"
        "<div class='metric-big' style='color: " + win_color + ";'>"
        + str(win_val)
        + "% <span style='font-size: " + str(font_size) + "px; font-weight: 500;'>（"
        + t["green_lights_count"].format(count=lights["green_count"])
        + "）</span></div>"
        "<div>"
        + t["sample_stats"].format(
            samples=current_stat["sample_size"],
            sp=current_stat["sp_avg_ret"],
            ndx=current_stat["ndx_avg_ret"],
        )
        + "</div></div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    st.subheader(t["section_cards"])
    col1, col2, col3 = st.columns(3)

    with col1:
        lvl1 = lights["cnn_level"]
        c1_html = (
            "<div class='radar-card'>"
            "<div style='font-weight:700;'>" + t["card1_title"] + "</div>"
            "<div class='metric-big'>" + str(cnn["score"]) + " <span style='font-size:" + str(font_size - 2) + "px;'>/ 100</span></div>"
            "<span class='badge-" + lvl1 + "'>" + t["lights"]["cnn"][lvl1] + "</span>"
            "<p style='margin-top:10px; opacity:0.85;'>"
            + t["card1_sub"].format(rating=str(cnn["rating"]).title(), prev=cnn["prev_close"], win=current_stat["win_cnn"])
            + "</p></div>"
        )
        st.markdown(c1_html, unsafe_allow_html=True)

    with col2:
        lvl2 = lights["vix_level"]
        c2_html = (
            "<div class='radar-card'>"
            "<div style='font-weight:700;'>" + t["card2_title"] + "</div>"
            "<div class='metric-big'>" + str(vix["vix"]) + "</div>"
            "<span class='badge-" + lvl2 + "'>" + t["lights"]["vix"][lvl2] + "</span>"
            "<p style='margin-top:10px; opacity:0.85;'>"
            + t["card2_sub"].format(prev=vix["vix_prev"], win=current_stat["win_vix"])
            + "</p></div>"
        )
        st.markdown(c2_html, unsafe_allow_html=True)

    with col3:
        lvl3 = lights["aaii_level"]
        c3_html = (
            "<div class='radar-card'>"
            "<div style='font-weight:700;'>" + t["card3_title"].format(date=aaii["date"]) + "</div>"
            "<div class='metric-big'>" + str(aaii["bearish"]) + "% <span style='font-size:" + str(font_size - 2) + "px;'>" + t["bearish_unit"] + "</span></div>"
            "<span class='badge-" + lvl3 + "'>" + t["lights"]["aaii"][lvl3] + "</span>"
            "<p style='margin-top:10px; opacity:0.85;'>"
            + t["card3_sub"].format(
                bull=aaii["bullish"],
                neut=aaii["neutral"],
                spread=aaii["spread"],
                bonus=current_stat["aaii_bonus"],
            )
            + "</p></div>"
        )
        st.markdown(c3_html, unsafe_allow_html=True)

    st.subheader(t["section_table"])
    cols = t["tbl_cols"]
    rows = []
    for code in ["21D", "63D", "126D", "252D"]:
        item = win_rates[code]
        rows.append({
            cols[0]: t["horizons"][code].split("—")[0].strip(),
            cols[1]: str(item["final_win_rate"]) + "%",
            cols[2]: t["yes"] if item["final_win_rate"] >= 90 else "—",
            cols[3]: str(item["win_cnn"]) + "%",
            cols[4]: str(item["win_vix"]) + "%",
            cols[5]: "+" + str(item["aaii_bonus"]) + "%",
            cols[6]: f"{item['sp_avg_ret']:+.2f}%",
            cols[7]: f"{item['ndx_avg_ret']:+.2f}%",
            cols[8]: str(item["sample_size"]) + t["days_unit"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if os.path.exists(CSV_PATH):
        st.subheader(t["section_chart"])
        df_hist = pd.read_csv(CSV_PATH).set_index("Date")
        chart_cols = [c for c in ["CNN_FG", "VIX"] if c in df_hist.columns]
        if chart_cols:
            st.line_chart(df_hist[chart_cols])

with tab_acad:
    st.markdown(t["academic_md"])
