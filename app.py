import io
import json
import os
import random
import urllib.parse
import altair as alt
import pandas as pd
import qrcode
import requests as req_lib
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Behavioral Sentiment & Win-Rate Radar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

JSON_PATH = os.path.join("data", "sentiment_data.json")
CSV_PATH = os.path.join("data", "history_backtest.csv")
COUNTER_PATH = os.path.join("data", "visitor_count.txt")
AUDIO_PATH = os.path.join("data", "daily_brief.mp3")

GITHUB_REPO_URL = "https://github.com/pjcoderz/us-fear-greed-radar"
APP_BRIEF_URL = "https://us-fear-greed-radar.streamlit.app/?view=brief"

# 請將下方 8 行替換為執行 Google Apps Script 後「執行紀錄」印出的實際內容
GOOGLE_FORM_ACTION_URL = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/formResponse"
ENTRY_UPDATED_AT = "entry.000001"
ENTRY_LANG = "entry.000002"
ENTRY_CNN = "entry.000003"
ENTRY_VIX = "entry.000004"
ENTRY_AAII = "entry.000005"
ENTRY_EMOTION = "entry.000006"
ENTRY_ACTION = "entry.000007"

CUTE_ANIMALS = [
    ("🦫", "水豚", "Capybara", "カピバラ"),
    ("🦊", "小狐狸", "Little Fox", "キツネ"),
    ("🦉", "貓頭鷹", "Owl", "フクロウ"),
    ("🦔", "小刺蝟", "Hedgehog", "ハリネズミ"),
    ("🐢", "小海龜", "Sea Turtle", "ウミガメ"),
    ("🐧", "小企鵝", "Penguin", "ペンギン"),
]

I18N = {
    "zh-TW": {
        "lang_name": "繁體中文",
        "app_title": "📡 行為財務學應用：美股恐慌指標與實證勝率雷達",
        "app_subtitle": "整合 CNN Fear & Greed、CBOE VIX 與 AAII 散戶情緒調查之逆向投資量化實證系統",
        "settings_header": "⚙️ 系統設定 (Settings)",
        "theme_label": "🎨 背景色系",
        "themes": ["護眼米白", "極簡純白", "深邃暗黑"],
        "font_label": "🔠 全站字體大小 (px)",
        "sidebar_note": "本系統將行為財務學中「投資人情緒與報酬反轉」之實證研究轉化為自動化監控工具。",
        "contact_header": "📬 專案與學術說明",
        "github_btn": "💻 GitHub 專案原始碼",
        "contact_desc": "本系統僅供行為財務學與投資情緒研究探討（開發者：pjcoderz）。",
        "meta_line": "資料更新：{updated} ｜ 累積瀏覽人次：{visitors:,} ｜ 寄信警報門檻：≥ {threshold}%",
        "tab_dashboard": "📊 即時指標與勝率儀表板",
        "tab_brief": "⚡ 點這裡直接看結論",
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
        "card1_ext": "極端值：最低 {min_v:.1f} / 最高 {max_v:.1f}（目前恐慌百分位 {pct:.0f}%）",
        "card2_title": "2. CBOE VIX 波動率恐慌指數",
        "card2_sub": "前日收盤：{prev}（門檻 ≥ 30 亮綠燈）<br>單指標歷史勝率：<b>{win}%</b>",
        "card2_ext": "極端值：最低 {min_v:.2f} / 最高 {max_v:.2f}（目前恐慌百分位 {pct:.0f}%）",
        "card3_title": "3. AAII 散戶看空比例 ({date})",
        "card3_sub": "看多 {bull}% / 中立 {neut}%（多空差 {spread}%）<br>散戶極端看空加權：<b>+{bonus}%</b>",
        "card3_ext": "極端值：最低 {min_v:.1f}% / 最高 {max_v:.1f}（目前看空百分位 {pct:.0f}%）",
        "bearish_unit": "看空",
        "lights": {
            "cnn": {"green": "🟢 極度恐慌 (買點亮燈)", "yellow": "🟡 恐慌觀察", "red": "🔴 中性/貪婪"},
            "vix": {"green": "🟢 恐慌噴出 (買點亮燈)", "yellow": "🟡 波動升溫", "red": "🔴 市場平靜"},
            "aaii": {"green": "🟢 散戶投降 (買點亮燈)", "yellow": "🟡 散戶偏空", "red": "🔴 散戶偏多/中性"},
        },
        "section_table": "📈 多週期實證回測勝率與報酬對照表",
        "tbl_cols": ["持有週期", "綜合勝率", "達 90% 警報", "CNN 勝率", "VIX 勝率", "AAII 加權", "S&P 500 平均報酬", "NASDAQ-100 平均報酬", "歷史樣本數"],
        "yes": "✅ 是",
        "days_unit": " 天",
        "chart_header": "📈 歷史恐慌趨勢與門檻雷達圖",
        "chart_modes": ["日線：CNN 恐慌度 & VIX（每日）", "週線：CNN 恐慌度 & VIX & AAII 看空（每週三指標同框）"],
        "range_opts": ["3M", "6M", "1Y", "3Y", "5Y", "2011+", "ALL"],
        "range_labels": {
            "3M": "近 3 個月",
            "6M": "近 6 個月",
            "1Y": "近 1 年",
            "3Y": "近 3 年",
            "5Y": "近 5 年",
            "2011+": "2011 年至今",
            "ALL": "全部歷史",
        },
        "chart_caption": (
            "同向門檻解讀：三條線皆為「越高＝越恐慌」，紅色虛線（100%）為逆向買點綠燈門檻"
            "（CNN_Fear ≥ 75 即原 CNN ≤ 25；VIX ≥ 30；AAII_Bearish ≥ 50%）。指標尚未發展或缺漏期間直接留白；"
            "滑鼠移過或手指點選任一日期，十字準星 Tooltip 會同步顯示該日「S&P 500 距前高回檔比例」。"
        ),
        "bench_expander": "📉 點開平行大盤價格走勢對照（S&P 500 / NASDAQ-100，與上方時間區間同步）",
        "bench_opts": ["S&P 500 (^GSPC)", "NASDAQ-100 (^NDX)"],
        "bench_caption": "純背景基準參考圖層（不參與情緒燈號運算），可垂直對照上方情緒未亮燈時的緩跌與三燈齊亮時的位置。",
        "bench_pending": "⏳ 平行指數收盤序列將於下一次 GitHub Actions 更新後顯示。",
        # 分頁二：等燈燈懶人包與分享圖卡
        "brief_title": "🚦 等燈燈｜美股逆向情緒雷達快報",
        "brief_audio_title": "🔊 聽 1 分鐘「登、登、登」語音結論",
        "brief_audio_pending": "⏳ 語音檔將於下一次 GitHub Actions 更新時自動產生，下方先為您呈現今日 1 分鐘語音播報內容：",
        "brief_download_btn": "⬇️ 一鍵下載戰情圖卡 (PNG 存檔檢驗)",
        "brief_copy_title": "📄 完整可編輯分享文案",
        "no_data": "⚠️ 尚未產生資料檔，請先至 GitHub Actions 手動執行一次 Update Fear & Greed Data。",
        "academic_md": (
            "### 一、研究背景與設計理念\n\n"
            "行為財務學實證研究指出，投資人在極度悲觀時容易產生過度反應，使價格偏離基本面並在後續數月至一年出現均值回歸與正報酬溢酬。"
            "本系統整合隱含波動率（CBOE VIX）、散戶調查情緒（AAII）與複合市場情緒（CNN Fear & Greed）進行實證回測。\n\n"
            "### 二、核心學術參考文獻\n\n"
            "- **Whaley, R. E. (2000).** The Investor Fear Gauge. *The Journal of Portfolio Management*, 26(3), 12-17. https://doi.org/10.3905/jpm.2000.319728\n"
            "- **Simon, D. P., & Wiggins, R. A. (2001).** S&P futures returns and contrary sentiment indicators. *Journal of Futures Markets*, 21(5), 447-462. https://doi.org/10.1002/fut.1602\n"
            "- **Fisher, K. L., & Statman, M. (2000).** Investor sentiment and stock returns. *Financial Analysts Journal*, 56(2), 16-23. https://doi.org/10.2469/faj.v56.n2.2340\n"
            "- **Baker, M., & Wurgler, J. (2006).** Investor sentiment and the cross-section of stock returns. *The Journal of Finance*, 61(4), 1645-1680. https://doi.org/10.1111/j.1540-6261.2006.00885.x\n"
            "- **Da, Z., Engelberg, J., & Gao, P. (2015).** The sum of all FEARS: Investor sentiment and asset prices. *The Review of Financial Studies*, 28(1), 1-32. https://doi.org/10.1093/rfs/hhu072\n\n"
            "### 三、研究限制聲明\n\n"
            "本系統為行為財務學實證模型之教育與研究應用，歷史條件機率不保證未來必然獲利，非投資建議。"
        ),
    },
    "en": {
        "lang_name": "English",
        "app_title": "📡 Behavioral Finance in Action: US Sentiment & Win-Rate Radar",
        "app_subtitle": "An Empirical Contrarian Dashboard Integrating CNN Fear & Greed, CBOE VIX, and AAII Sentiment Survey",
        "settings_header": "⚙️ Settings",
        "theme_label": "🎨 Color Theme",
        "themes": ["Warm Paper", "Clean White", "Deep Dark"],
        "font_label": "🔠 Base Font Size (px)",
        "sidebar_note": "Translates empirical Behavioral Finance research on investor sentiment and return reversals into an automated monitor.",
        "contact_header": "📬 Project & Academic Info",
        "github_btn": "💻 GitHub Repository",
        "contact_desc": "Academic and educational dashboard on behavioral sentiment and return reversals (Author: pjcoderz).",
        "meta_line": "Updated: {updated} ｜ Visitors: {visitors:,} ｜ Email Alert Threshold: ≥ {threshold}%",
        "tab_dashboard": "📊 Live Sentiment & Win-Rate Dashboard",
        "tab_brief": "⚡ Quick Takeaway & Card",
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
        "card1_ext": "Range: Min {min_v:.1f} / Max {max_v:.1f} (Fear Pct: {pct:.0f}th)",
        "card2_title": "2. CBOE VIX Volatility Index",
        "card2_sub": "Prev Close: {prev} (Green Light ≥ 30)<br>Standalone Win Rate: <b>{win}%</b>",
        "card2_ext": "Range: Min {min_v:.2f} / Max {max_v:.2f} (Fear Pct: {pct:.0f}th)",
        "card3_title": "3. AAII Retail Bearishness ({date})",
        "card3_sub": "Bullish {bull}% / Neutral {neut}% (Spread: {spread}%)<br>Extreme Bearish Bonus: <b>+{bonus}%</b>",
        "card3_ext": "Range: Min {min_v:.1f}% / Max {max_v:.1f}% (Bearish Pct: {pct:.0f}th)",
        "bearish_unit": "Bearish",
        "lights": {
            "cnn": {"green": "🟢 Extreme Fear (Buy Signal)", "yellow": "🟡 Fear Watch", "red": "🔴 Neutral / Greed"},
            "vix": {"green": "🟢 Panic Spike (Buy Signal)", "yellow": "🟡 Elevated Vol", "red": "🔴 Calm Market"},
            "aaii": {"green": "🟢 Retail Capitulation (Buy Signal)", "yellow": "🟡 Retail Bearish", "red": "🔴 Neutral / Bullish"},
        },
        "section_table": "📈 Multi-Horizon Empirical Win Rates & Forward Returns",
        "tbl_cols": ["Holding Horizon", "Composite Win Rate", "≥ 90% Alert", "CNN Win Rate", "VIX Win Rate", "AAII Bonus", "S&P 500 Avg Return", "NASDAQ-100 Avg Return", "Sample Size"],
        "yes": "✅ Yes",
        "days_unit": " days",
        "chart_header": "📈 Historical Fear Trend & Threshold Radar",
        "chart_modes": ["Daily: CNN Fear & VIX", "Weekly: CNN Fear & VIX & AAII Bearish (3-Series Weekly)"],
        "range_opts": ["3M", "6M", "1Y", "3Y", "5Y", "2011+", "ALL"],
        "range_labels": {
            "3M": "3M",
            "6M": "6M",
            "1Y": "1Y",
            "3Y": "3Y",
            "5Y": "5Y",
            "2011+": "2011+",
            "ALL": "All History",
        },
        "chart_caption": (
            "Aligned Threshold Guide: HIGHER = MORE FEAR, with 100% marking each contrarian green-light threshold"
            " (CNN_Fear ≥ 75 = raw CNN ≤ 25; VIX ≥ 30; AAII_Bearish ≥ 50%). Hover or tap any date to view crosshair values "
            "including S&P 500 drawdown from its all-time high."
        ),
        "bench_expander": "📉 Expand Parallel Index Price Chart (S&P 500 / NASDAQ-100, synced with range above)",
        "bench_opts": ["S&P 500 (^GSPC)", "NASDAQ-100 (^NDX)"],
        "bench_caption": "Pure background price reference layer (excluded from sentiment signal logic) for post-survey visual comparison.",
        "bench_pending": "⏳ Parallel index price series will appear after the next GitHub Actions run.",
        "brief_title": "🚦 Deng-Deng-Deng | US Contrarian Sentiment Brief",
        "brief_audio_title": "🔊 Play 1-Min Audio Brief",
        "brief_audio_pending": "⏳ Audio MP3 will be generated on the next GitHub Actions run. Here is today's 1-minute brief:",
        "brief_download_btn": "⬇️ Download Radar Card (PNG)",
        "brief_copy_title": "📄 Editable Share Caption",
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
            "Built for academic research and educational illustration of behavioral finance models, not financial advice."
        ),
    },
    "ja": {
        "lang_name": "日本語",
        "app_title": "📡 行動ファイナンス応用：米国株恐怖指数・実証勝率レーダー",
        "app_subtitle": "CNN Fear & Greed・CBOE VIX・AAII 個人投資家センチメントを統合した逆張り実証分析システム",
        "settings_header": "⚙️ システム設定 (Settings)",
        "theme_label": "🎨 背景テーマ",
        "themes": ["アイボリー", "ピュアホワイト", "ダークモード"],
        "font_label": "🔠 フォントサイズ (px)",
        "sidebar_note": "行動ファイナンスにおける投資家心理とリターン反転の実証研究を自動モニタリングツールとして実装しています。",
        "contact_header": "📬 プロジェクト・学術情報",
        "github_btn": "💻 GitHub リポジトリ",
        "contact_desc": "行動ファイナンスと投資心理の学術・教育向けダッシュボードです（開発者：pjcoderz）。",
        "meta_line": "最終更新：{updated} ｜ 累計訪問者数：{visitors:,} ｜ メール通知閾値：≥ {threshold}%",
        "tab_dashboard": "📊 リアルタイム指標・勝率ダッシュボード",
        "tab_brief": "⚡ 結論だけすぐ見る",
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
        "card1_ext": "極値：最小 {min_v:.1f} / 最大 {max_v:.1f}（現在恐怖パーセンタイル {pct:.0f}%）",
        "card2_title": "2. CBOE VIX 恐怖指数",
        "card2_sub": "前日終値：{prev}（閾値 ≥ 30 で緑点灯）<br>単独指標の歴史的勝率：<b>{win}%</b>",
        "card2_ext": "極値：最小 {min_v:.2f} / 最大 {max_v:.2f}（現在恐怖パーセンタイル {pct:.0f}%）",
        "card3_title": "3. AAII 個人投資家弱気比率 ({date})",
        "card3_sub": "強気 {bull}% / 中立 {neut}%（強弱スプレッド {spread}%）<br>極端な弱気補正：<b>+{bonus}%</b>",
        "card3_ext": "極値：最小 {min_v:.1f}% / 最大 {max_v:.1f}%（現在弱気パーセンタイル {pct:.0f}%）",
        "bearish_unit": "弱気",
        "lights": {
            "cnn": {"green": "🟢 極度の恐怖 (買い点灯)", "yellow": "🟡 恐怖警戒", "red": "🔴 中立・強欲"},
            "vix": {"green": "🟢 パニック急騰 (買い点灯)", "yellow": "🟡 ボラティリティ上昇", "red": "🔴 市場安定"},
            "aaii": {"green": "🟢 個人投資家総悲観 (買い点灯)", "yellow": "🟡 弱気優勢", "red": "🔴 強気・中立"},
        },
        "section_table": "📈 保有期間別・実証勝率および平均リターン比較表",
        "tbl_cols": ["保有期間", "総合勝率", "90%警報", "CNN勝率", "VIX勝率", "AAII補正", "S&P 500 平均リターン", "NASDAQ-100 平均リターン", "サンプル数"],
        "yes": "✅ 達成",
        "days_unit": " 日",
        "chart_header": "📈 過去の恐怖トレンド・閾値レーダー",
        "chart_modes": ["日足：CNN恐怖度 & VIX", "週足：CNN恐怖度 & VIX & AAII弱気（週次3指標同框）"],
        "range_opts": ["3M", "6M", "1Y", "3Y", "5Y", "2011+", "ALL"],
        "range_labels": {
            "3M": "3ヶ月",
            "6M": "6ヶ月",
            "1Y": "1年",
            "3Y": "3年",
            "5Y": "5年",
            "2011+": "2011年〜",
            "ALL": "全期間",
        },
        "chart_caption": (
            "同向閾値の見方：全指標を「高いほど恐怖」に統一し、100%ラインを逆張り買い点灯基準としました。"
            "ホバーまたはタップで十字線とともに「S&P 500 高値からの下落率」も確認できます。"
        ),
        "bench_expander": "📉 平行株価チャートを開く（S&P 500 / NASDAQ-100・上の表示期間と連動）",
        "bench_opts": ["S&P 500 (^GSPC)", "NASDAQ-100 (^NDX)"],
        "bench_caption": "センチメント判定には含めない純粋な背景参照チャートです。",
        "bench_pending": "⏳ 次回の GitHub Actions 実行後に平行株価データが表示されます。",
        "brief_title": "🚦 等燈燈｜米国株逆張りセンチメント速報",
        "brief_audio_title": "🔊 1分で結論を聴く（音声ブリーフ）",
        "brief_audio_pending": "⏳ 次回の GitHub Actions 実行後に音声 MP3 が生成されます。",
        "brief_download_btn": "⬇️ 戦情カード (PNG) をダウンロード",
        "brief_copy_title": "📄 SNS投稿用テキスト",
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
            "本アプリケーションは行動ファイナンスの実証モデルを学ぶための学術・教育用途であり、投資助言ではありません。"
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


def compute_extremes_summary(df_hist, cnn_val, vix_val, aaii_val):
    summary = {
        "cnn": {"min_v": float(cnn_val), "max_v": float(cnn_val), "pct": 50.0},
        "vix": {"min_v": float(vix_val), "max_v": float(vix_val), "pct": 50.0},
        "aaii": {"min_v": float(aaii_val), "max_v": float(aaii_val), "pct": 50.0},
    }
    if df_hist is None or df_hist.empty:
        return summary

    if "CNN_FG" in df_hist.columns:
        s_cnn = pd.to_numeric(df_hist["CNN_FG"], errors="coerce").dropna()
        if not s_cnn.empty:
            summary["cnn"]["min_v"] = float(s_cnn.min())
            summary["cnn"]["max_v"] = float(s_cnn.max())
            summary["cnn"]["pct"] = float((s_cnn <= float(cnn_val)).mean() * 100.0)

    if "VIX" in df_hist.columns:
        s_vix = pd.to_numeric(df_hist["VIX"], errors="coerce").dropna()
        if not s_vix.empty:
            summary["vix"]["min_v"] = float(s_vix.min())
            summary["vix"]["max_v"] = float(s_vix.max())
            summary["vix"]["pct"] = float((s_vix <= float(vix_val)).mean() * 100.0)

    if "AAII_Bearish" in df_hist.columns:
        s_aaii = pd.to_numeric(df_hist["AAII_Bearish"], errors="coerce").dropna()
        if not s_aaii.empty:
            summary["aaii"]["min_v"] = float(s_aaii.min())
            summary["aaii"]["max_v"] = float(s_aaii.max())
            summary["aaii"]["pct"] = float((s_aaii <= float(aaii_val)).mean() * 100.0)

    return summary


def load_cjk_font(size):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Bold.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msjhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_dengdengdeng_poster_png(data):
    """生成 3:4 (1080x1440) 米白黑框＋亮黃螢光筆記風爆款圖卡（固定鎖定 6 個月 126D）"""
    w, h = 1080, 1440
    cream_bg = "#FAF6EE"
    card_bg = "#FFFDF9"
    ink = "#111111"
    neon_yellow = "#F7FF00"
    green_pill = "#4ADE80"
    yellow_pill = "#FACC15"
    red_pill = "#F87171"

    img = Image.new("RGB", (w, h), color=cream_bg)
    draw = ImageDraw.Draw(img)

    f_pill = load_cjk_font(28)
    f_h1 = load_cjk_font(66)
    f_mega = load_cjk_font(124)
    f_sub_bold = load_cjk_font(34)
    f_status = load_cjk_font(32)
    f_card_lbl = load_cjk_font(30)
    f_card_val = load_cjk_font(62)
    f_card_tag = load_cjk_font(28)
    f_slogan = load_cjk_font(36)
    f_footer_title = load_cjk_font(32)
    f_footer_sub = load_cjk_font(23)

    cnn = data["cnn"]
    vix = data["vix"]
    aaii = data["aaii"]
    lights = data["lights"]
    stat_126 = data["win_rates"]["126D"]
    win_pct = f"{stat_126['final_win_rate']:.1f}%"
    g_cnt = lights["green_count"]
    sp_dd = data.get("sp500", {}).get("drawdown_pct", 0.0)
    date_only = str(data.get("updated_at", "")).split(" ")[0]

    # 1. 頂部膠囊標籤（含明確日期）
    top_text = f"等燈燈｜美股逆向情緒雷達 · 日期 {date_only}"
    tb = draw.textbbox((0, 0), top_text, font=f_pill)
    tw = tb[2] - tb[0]
    pill_w = tw + 68
    pill_x0 = (w - pill_w) // 2
    draw.rounded_rectangle([pill_x0, 44, pill_x0 + pill_w, 104], radius=30, fill=card_bg, outline=ink, width=4)
    draw.text((pill_x0 + 34, 56), top_text, font=f_pill, fill=ink)

    # 2. 主標題兩行（第一行：【美股恐慌掃描】，第二行另起：6 個月歷史勝率 XX.X%）
    line1 = "【美股恐慌掃描】"
    line2 = f"6 個月歷史勝率 {win_pct}"

    b1 = draw.textbbox((0, 0), line1, font=f_h1)
    w1 = b1[2] - b1[0]
    x1 = (w - w1) // 2
    draw.rectangle([x1 - 16, 152, x1 + w1 + 16, 214], fill=neon_yellow)
    draw.text((x1, 134), line1, font=f_h1, fill=ink)

    b2 = draw.textbbox((0, 0), line2, font=f_h1)
    w2 = b2[2] - b2[0]
    x2 = (w - w2) // 2
    draw.rectangle([x2 - 16, 248, x2 + w2 + 16, 310], fill=neon_yellow)
    draw.text((x2, 230), line2, font=f_h1, fill=ink)

    # 3. 中央巨無霸核心數字便當盒（帶粗黑立體陰影）
    mx0, my0, mx1, my1 = 64, 355, w - 64, 675
    draw.rounded_rectangle([mx0 + 10, my0 + 10, mx1 + 10, my1 + 10], radius=28, fill=ink)
    draw.rounded_rectangle([mx0, my0, mx1, my1], radius=28, fill=card_bg, outline=ink, width=5)

    draw.text((112, 388), win_pct, font=f_mega, fill=ink)
    draw.text((185, 558), "6 個月歷史勝率", font=f_sub_bold, fill=ink)

    status_map = {
        0: ("情緒冷靜：0 / 3 綠燈", "#E5E7EB"),
        1: ("警戒累積：1 / 3 綠燈", neon_yellow),
        2: ("雙燈警戒：2 / 3 綠燈", yellow_pill),
        3: ("三燈齊亮：3 / 3 綠燈", green_pill),
    }
    st_text, st_bg = status_map.get(g_cnt, ("警戒累積：1 / 3 綠燈", neon_yellow))
    sb = draw.textbbox((0, 0), st_text, font=f_status)
    sw = sb[2] - sb[0] + 64
    sx0 = mx1 - 44 - sw
    draw.rounded_rectangle([sx0, 415, mx1 - 44, 488], radius=36, fill=st_bg, outline=ink, width=4)
    draw.ellipse([sx0 + 22, 439, sx0 + 46, 463], fill=green_pill if g_cnt > 0 else "#9CA3AF", outline=ink, width=3)
    draw.text((sx0 + 56, 431), st_text, font=f_status, fill=ink)

    dd_str = f"S&P 500 距前高 {sp_dd:+.1f}%"
    db = draw.textbbox((0, 0), dd_str, font=f_sub_bold)
    draw.text((mx1 - 48 - (db[2] - db[0]), 535), dd_str, font=f_sub_bold, fill=ink)

    # 4. 中下三格粗黑框便當盒（CNN / VIX / AAII）
    cnn_tag = "極度恐慌" if lights["cnn_level"] == "green" else ("恐慌觀察" if lights["cnn_level"] == "yellow" else "中性貪婪")
    vix_tag = "恐慌噴出" if lights["vix_level"] == "green" else ("波動升溫" if lights["vix_level"] == "yellow" else "市場平靜")
    aaii_tag = "散戶投降" if lights["aaii_level"] == "green" else ("散戶偏空" if lights["aaii_level"] == "yellow" else "偏多中性")

    level_bg = {"green": green_pill, "yellow": neon_yellow, "red": red_pill}
    cards = [
        ("CNN 恐慌貪婪", f"{cnn['score']:.1f}", cnn_tag, level_bg[lights["cnn_level"]]),
        ("CBOE VIX", f"{vix['vix']:.1f}", vix_tag, level_bg[lights["vix_level"]]),
        ("AAII 散戶看空", f"{aaii['bearish']:.1f}%", aaii_tag, level_bg[lights["aaii_level"]]),
    ]

    gap = 24
    cw = (w - 128 - gap * 2) // 3
    cy0, cy1 = 710, 1055
    for idx, (c_title, c_val, c_tag, c_pill_bg) in enumerate(cards):
        cx0 = 64 + idx * (cw + gap)
        cx1 = cx0 + cw
        draw.rounded_rectangle([cx0 + 8, cy0 + 8, cx1 + 8, cy1 + 8], radius=24, fill=ink)
        draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=24, fill=card_bg, outline=ink, width=5)

        b_lbl = draw.textbbox((0, 0), c_title, font=f_card_lbl)
        draw.text((cx0 + (cw - (b_lbl[2] - b_lbl[0])) // 2, cy0 + 34), c_title, font=f_card_lbl, fill=ink)

        b_val = draw.textbbox((0, 0), c_val, font=f_card_val)
        draw.text((cx0 + (cw - (b_val[2] - b_val[0])) // 2, cy0 + 132), c_val, font=f_card_val, fill=ink)

        b_tag = draw.textbbox((0, 0), c_tag, font=f_card_tag)
        pw = (b_tag[2] - b_tag[0]) + 46
        px0 = cx0 + (cw - pw) // 2
        draw.rounded_rectangle([px0, cy0 + 250, px0 + pw, cy0 + 306], radius=28, fill=c_pill_bg, outline=ink, width=4)
        draw.text((px0 + 23, cy0 + 260), c_tag, font=f_card_tag, fill=ink)

    # 5. 底部亮黃色金句橫幅
    sy0, sy1 = 1095, 1192
    draw.rounded_rectangle([64 + 8, sy0 + 8, w - 64 + 8, sy1 + 8], radius=20, fill=ink)
    draw.rounded_rectangle([64, sy0, w - 64, sy1], radius=20, fill=neon_yellow, outline=ink, width=5)
    slogan = "新聞在賣驚嚇，數據在算機率——別猜底，等燈燈。"
    bs = draw.textbbox((0, 0), slogan, font=f_slogan)
    draw.text(((w - (bs[2] - bs[0])) // 2, sy0 + 24), slogan, font=f_slogan, fill=ink)

    # 6. 最底部滿版橫列：左側 QR Code ＋ 右側乾淨網址與免責聲明橫跨全幅
    fy0, fy1 = 1222, 1396
    draw.rounded_rectangle([64, fy0, w - 64, fy1], radius=20, fill=card_bg, outline=ink, width=4)

    qr = qrcode.QRCode(box_size=5, border=1)
    qr.add_data(APP_BRIEF_URL)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#111111", back_color="#FFFDF9").convert("RGB")
    qr_size = 138
    qr_img = qr_img.resize((qr_size, qr_size))
    img.paste(qr_img, (88, fy0 + (fy1 - fy0 - qr_size) // 2))

    tx_x = 88 + qr_size + 32
    draw.text((tx_x, fy0 + 24), "掃描 QR Code 或輸入網址開啟「等燈燈」快報：", font=f_footer_title, fill=ink)
    draw.text((tx_x, fy0 + 76), APP_BRIEF_URL, font=f_footer_sub, fill=ink)
    draw.text((tx_x, fy0 + 120), "僅供行為財務學與投資情緒研究參考，非投資建議。", font=f_footer_sub, fill="#4B5563")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def build_brief_share_text(data):
    cnn = data["cnn"]
    vix = data["vix"]
    aaii = data["aaii"]
    g_cnt = data["lights"]["green_count"]
    stat_126 = data["win_rates"]["126D"]
    sp_dd = data.get("sp500", {}).get("drawdown_pct", 0.0)
    date_only = str(data.get("updated_at", "")).split(" ")[0]

    return (
        f"🚦 等燈燈｜美股逆向情緒雷達（{date_only}）\n"
        f"今天亮了 {g_cnt} / 3 盞綠燈｜6 個月歷史勝率：{stat_126['final_win_rate']:.1f}%（S&P 500 距前高 {sp_dd:+.1f}%）\n"
        f"• CNN 恐慌貪婪：{cnn['score']:.1f}\n"
        f"• CBOE VIX：{vix['vix']:.1f}\n"
        f"• AAII 散戶看空：{aaii['bearish']:.1f}%\n"
        f"新聞在賣驚嚇，數據在算機率——別猜底，等燈燈。\n"
        f"👉 聽 1 分鐘語音＆下載戰情圖卡：{APP_BRIEF_URL}\n"
        f"#等燈燈 #美股 #行為財務學 #VIX #逆向投資（非投資建議）"
    )


def build_aligned_fear_chart(df_source, include_aaii=False):
    if df_source is None or df_source.empty:
        return None

    has_dd = "SP500_DD" in df_source.columns
    has_sp = "SP500" in df_source.columns

    records = []
    for idx, row in df_source.iterrows():
        dt_str = idx.strftime("%Y-%m-%d")

        if has_dd and pd.notna(row.get("SP500_DD")):
            dd_val = float(row["SP500_DD"])
            if has_sp and pd.notna(row.get("SP500")):
                sp_dd_text = f"{dd_val:+.2f}% (SP500: {float(row['SP500']):,.0f})"
            else:
                sp_dd_text = f"{dd_val:+.2f}%"
        else:
            sp_dd_text = "N/A"

        if "CNN_FG" in df_source.columns and pd.notna(row.get("CNN_FG")):
            raw_cnn = float(row["CNN_FG"])
            cnn_fear = 100.0 - raw_cnn
            records.append({
                "Date": dt_str,
                "Indicator": "CNN_Fear (100 - CNN)",
                "ThresholdPct": round((cnn_fear / 75.0) * 100.0, 1),
                "RawText": f"{raw_cnn:.1f} (Fear {cnn_fear:.1f} / 100)",
                "SP500_DD_Text": sp_dd_text,
            })
        else:
            records.append({
                "Date": dt_str,
                "Indicator": "CNN_Fear (100 - CNN)",
                "ThresholdPct": None,
                "RawText": "N/A",
                "SP500_DD_Text": sp_dd_text,
            })

        if "VIX" in df_source.columns and pd.notna(row.get("VIX")):
            raw_vix = float(row["VIX"])
            records.append({
                "Date": dt_str,
                "Indicator": "VIX",
                "ThresholdPct": round((raw_vix / 30.0) * 100.0, 1),
                "RawText": f"{raw_vix:.2f}",
                "SP500_DD_Text": sp_dd_text,
            })
        else:
            records.append({
                "Date": dt_str,
                "Indicator": "VIX",
                "ThresholdPct": None,
                "RawText": "N/A",
                "SP500_DD_Text": sp_dd_text,
            })

        if include_aaii:
            if "AAII_Bearish" in df_source.columns and pd.notna(row.get("AAII_Bearish")):
                raw_aaii = float(row["AAII_Bearish"])
                records.append({
                    "Date": dt_str,
                    "Indicator": "AAII_Bearish",
                    "ThresholdPct": round((raw_aaii / 50.0) * 100.0, 1),
                    "RawText": f"{raw_aaii:.1f}%",
                    "SP500_DD_Text": sp_dd_text,
                })
            else:
                records.append({
                    "Date": dt_str,
                    "Indicator": "AAII_Bearish",
                    "ThresholdPct": None,
                    "RawText": "N/A",
                    "SP500_DD_Text": sp_dd_text,
                })

    df_long = pd.DataFrame(records)
    if df_long["ThresholdPct"].dropna().empty:
        return None

    domain_list = ["CNN_Fear (100 - CNN)", "VIX"] + (["AAII_Bearish"] if include_aaii else [])
    range_list = ["#2563EB", "#D97706"] + (["#059669"] if include_aaii else [])

    nearest = alt.selection_point(
        nearest=True,
        on="pointerover",
        fields=["Date"],
        empty=False,
    )

    lines = (
        alt.Chart(df_long)
        .mark_line(strokeWidth=2.2)
        .encode(
            x=alt.X("Date:N", title=None, axis=alt.Axis(labelAngle=-35, tickCount=10)),
            y=alt.Y(
                "ThresholdPct:Q",
                title="Threshold Level (100% = Green Light)",
                scale=alt.Scale(domain=[0, 180], clamp=True),
            ),
            color=alt.Color(
                "Indicator:N",
                scale=alt.Scale(domain=domain_list, range=range_list),
                legend=alt.Legend(title=None, orient="top"),
            ),
        )
    )

    hover_layer = (
        alt.Chart(df_long)
        .mark_point(opacity=0, size=60)
        .encode(
            x=alt.X("Date:N"),
            y=alt.Y("ThresholdPct:Q"),
            tooltip=[
                alt.Tooltip("Date:N", title="Date"),
                alt.Tooltip("Indicator:N", title="Indicator"),
                alt.Tooltip("ThresholdPct:Q", title="Threshold %"),
                alt.Tooltip("RawText:N", title="Raw Value"),
                alt.Tooltip("SP500_DD_Text:N", title="S&P 500 vs ATH"),
            ],
        )
        .add_params(nearest)
    )

    crosshair_rule = (
        alt.Chart(df_long)
        .mark_rule(color="#64748B", strokeDash=[3, 3], strokeWidth=1.2)
        .encode(x=alt.X("Date:N"))
        .transform_filter(nearest)
    )

    active_points = (
        alt.Chart(df_long)
        .mark_circle(size=75)
        .encode(
            x=alt.X("Date:N"),
            y=alt.Y("ThresholdPct:Q"),
            color=alt.Color("Indicator:N", scale=alt.Scale(domain=domain_list, range=range_list)),
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
        )
    )

    threshold_df = pd.DataFrame({"y": [100.0]})
    rule = (
        alt.Chart(threshold_df)
        .mark_rule(color="#DC2626", strokeDash=[5, 4], strokeWidth=2)
        .encode(y="y:Q")
    )

    return (lines + rule + crosshair_rule + active_points + hover_layer).properties(height=360)


def build_parallel_index_chart(df_source, col_name, label_name, line_color="#475569"):
    if df_source is None or df_source.empty or col_name not in df_source.columns:
        return None

    s = pd.to_numeric(df_source[col_name], errors="coerce")
    if s.dropna().empty:
        return None

    dd_s = ((s / s.cummax()) - 1.0) * 100.0
    rows = []
    for idx in df_source.index:
        dt_str = idx.strftime("%Y-%m-%d")
        val = s.loc[idx]
        dd_val = dd_s.loc[idx]
        rows.append({
            "Date": dt_str,
            "Price": round(float(val), 2) if pd.notna(val) else None,
            "DDText": f"{float(dd_val):+.2f}%" if pd.notna(dd_val) else "N/A",
        })

    df_idx = pd.DataFrame(rows)
    nearest = alt.selection_point(
        nearest=True,
        on="pointerover",
        fields=["Date"],
        empty=False,
    )

    line = (
        alt.Chart(df_idx)
        .mark_line(strokeWidth=2.0, color=line_color)
        .encode(
            x=alt.X("Date:N", title=None, axis=alt.Axis(labelAngle=-35, tickCount=10)),
            y=alt.Y("Price:Q", title=label_name, scale=alt.Scale(zero=False)),
        )
    )

    hover = (
        alt.Chart(df_idx)
        .mark_point(opacity=0, size=60)
        .encode(
            x=alt.X("Date:N"),
            y=alt.Y("Price:Q"),
            tooltip=[
                alt.Tooltip("Date:N", title="Date"),
                alt.Tooltip("Price:Q", title=label_name, format=",.2f"),
                alt.Tooltip("DDText:N", title="Drawdown vs Peak"),
            ],
        )
        .add_params(nearest)
    )

    rule = (
        alt.Chart(df_idx)
        .mark_rule(color="#64748B", strokeDash=[3, 3], strokeWidth=1.2)
        .encode(x=alt.X("Date:N"))
        .transform_filter(nearest)
    )

    dot = (
        alt.Chart(df_idx)
        .mark_circle(size=70, color=line_color)
        .encode(
            x=alt.X("Date:N"),
            y=alt.Y("Price:Q"),
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
        )
    )

    return (line + rule + dot + hover).properties(height=250)


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
    st.subheader(t["contact_header"])
    st.caption(t["contact_desc"])
    st.link_button(t["github_btn"], GITHUB_REPO_URL, use_container_width=True)

    st.divider()
    st.caption(t["sidebar_note"])

THEME_PALETTES = [
    {
        "bg": "#FAF8F5",
        "card": "#FFFFFF",
        "text": "#1F2937",
        "border": "#E5E7EB",
        "lab_bg": "#E0E7FF",
        "lab_text": "#1E1B4B",
        "lab_border": "#4338CA",
        "lab_badge_bg": "#4338CA",
        "lab_badge_fg": "#FFFFFF",
        "time_highlight": "#3730A3",
        "info_bg": "#F8FAFC",
    },
    {
        "bg": "#FFFFFF",
        "card": "#F9FAFB",
        "text": "#111827",
        "border": "#E5E7EB",
        "lab_bg": "#E0F2FE",
        "lab_text": "#0C4A6E",
        "lab_border": "#0369A1",
        "lab_badge_bg": "#0369A1",
        "lab_badge_fg": "#FFFFFF",
        "time_highlight": "#075985",
        "info_bg": "#F8FAFC",
    },
    {
        "bg": "#0F172A",
        "card": "#1E293B",
        "text": "#F8FAFC",
        "border": "#334155",
        "lab_bg": "#1E1B4B",
        "lab_text": "#EEF2FF",
        "lab_border": "#818CF8",
        "lab_badge_bg": "#6366F1",
        "lab_badge_fg": "#FFFFFF",
        "time_highlight": "#A5B4FC",
        "info_bg": "#172554",
    },
]
style = THEME_PALETTES[theme_idx]

css_block = (
    "<style>"
    ".stApp { background-color: " + style["bg"] + "; color: " + style["text"] + "; font-size: " + str(font_size) + "px; }"
    ".radar-card { background-color: " + style["card"] + "; border: 1px solid " + style["border"] + "; border-radius: 14px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }"
    ".metric-big { font-size: " + str(font_size + 14) + "px; font-weight: 800; margin: 6px 0; }"
    ".ext-foot { margin-top: 8px; padding-top: 8px; border-top: 1px dashed " + style["border"] + "; font-size: " + str(max(12, font_size - 3)) + "px; opacity: 0.8; }"
    ".badge-green { background-color: #DCFCE7; color: #166534 !important; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    ".badge-yellow { background-color: #FEF9C3; color: #854D0E !important; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    ".badge-red { background-color: #FEE2E2; color: #991B1B !important; padding: 4px 10px; border-radius: 999px; font-weight: 700; font-size: " + str(font_size - 2) + "px; }"
    ".lab-badge-wrap { text-align: center; margin-bottom: 8px; }"
    ".st-key-survey_lab_box .lab-badge { display: inline-block; background-color: " + style["lab_badge_bg"] + "; color: " + style["lab_badge_fg"] + " !important; padding: 6px 16px; border-radius: 999px; font-weight: 800; font-size: " + str(font_size + 1) + "px; letter-spacing: 0.4px; }"
    ".st-key-survey_lab_box .lab-hero-center { text-align: center; font-size: " + str(font_size + 2) + "px; font-weight: 800; color: " + style["lab_text"] + " !important; margin: 6px 0 8px 0; }"
    ".st-key-survey_lab_box .sec-big { font-size: " + str(font_size + 3) + "px; font-weight: 800; color: " + style["time_highlight"] + " !important; }"
    ".st-key-survey_lab_box {"
    "  background-color: " + style["lab_bg"] + " !important;"
    "  color: " + style["lab_text"] + " !important;"
    "  border: 2.5px solid " + style["lab_border"] + " !important;"
    "  border-top: 8px solid " + style["lab_border"] + " !important;"
    "  border-radius: 18px !important;"
    "  padding: 20px 18px !important;"
    "  margin: 22px 0 26px 0 !important;"
    "  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.09) !important;"
    "}"
    ".st-key-survey_lab_box p, .st-key-survey_lab_box label, .st-key-survey_lab_box h2, .st-key-survey_lab_box h3 {"
    "  color: " + style["lab_text"] + " !important;"
    "}"
    ".st-key-survey_lab_box button[kind='primary']:not(:disabled) p {"
    "  color: #FFFFFF !important;"
    "}"
    ".st-key-survey_lab_box [data-testid='stAlert'] {"
    "  background-color: " + style["info_bg"] + " !important;"
    "  border: 1px solid " + style["lab_border"] + " !important;"
    "}"
    "</style>"
)
st.markdown(css_block, unsafe_allow_html=True)

visitors = update_visitor_counter()
st.title(t["app_title"])
st.markdown("**" + t["app_subtitle"] + "**")

if not os.path.exists(JSON_PATH):
    st.warning(t["no_data"])
    _, _, tab_acad_only = st.tabs([t["tab_dashboard"], t["tab_brief"], t["tab_academic"]])
    with tab_acad_only:
        st.markdown(t["academic_md"])
    st.stop()

with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

df_hist = None
if os.path.exists(CSV_PATH):
    df_tmp = pd.read_csv(CSV_PATH)
    df_tmp["dt"] = pd.to_datetime(df_tmp["Date"], errors="coerce")
    df_hist = df_tmp.dropna(subset=["dt"]).set_index("dt").sort_index()

st.caption(
    t["meta_line"].format(
        updated=data.get("updated_at", ""),
        visitors=visitors,
        threshold=data.get("alert_threshold", 90.0),
    )
)

query_view = str(st.query_params.get("view", "")).lower()
tab_order = (
    [t["tab_brief"], t["tab_dashboard"], t["tab_academic"]]
    if query_view == "brief"
    else [t["tab_dashboard"], t["tab_brief"], t["tab_academic"]]
)
tabs_objs = st.tabs(tab_order)
tab_map = dict(zip(tab_order, tabs_objs))
tab_dash = tab_map[t["tab_dashboard"]]
tab_brief = tab_map[t["tab_brief"]]
tab_acad = tab_map[t["tab_academic"]]

cnn = data["cnn"]
vix = data["vix"]
aaii = data["aaii"]
lights = data["lights"]
win_rates = data["win_rates"]
ext_stats = compute_extremes_summary(df_hist, cnn["score"], vix["vix"], aaii["bearish"])

# ================= 分頁一：維持原樣不改 =================
with tab_dash:
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
            + "</p>"
            "<div class='ext-foot'>"
            + t["card1_ext"].format(
                min_v=ext_stats["cnn"]["min_v"],
                max_v=ext_stats["cnn"]["max_v"],
                pct=ext_stats["cnn"]["pct"],
            )
            + "</div></div>"
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
            + "</p>"
            "<div class='ext-foot'>"
            + t["card2_ext"].format(
                min_v=ext_stats["vix"]["min_v"],
                max_v=ext_stats["vix"]["max_v"],
                pct=ext_stats["vix"]["pct"],
            )
            + "</div></div>"
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
            + "</p>"
            "<div class='ext-foot'>"
            + t["card3_ext"].format(
                min_v=ext_stats["aaii"]["min_v"],
                max_v=ext_stats["aaii"]["max_v"],
                pct=ext_stats["aaii"]["pct"],
            )
            + "</div></div>"
        )
        st.markdown(c3_html, unsafe_allow_html=True)

    # ================= 官方 .st-key-survey_lab_box 整塊色塊投票容器 =================
    survey_texts = {
        "zh-TW": {
            "badge": "🧪 行為實驗互動區 · 只要 10 秒",
            "title": "🗳️ 順手幫個忙：記錄您此刻的市場直覺（5 點量表）",
            "center_10s": "⏱️ 只要 <span class='sec-big'>10 秒</span>，順手留下一筆匿名研究紀錄！",
            "prompt_lead": "看完今日指標了嗎？如果這些數據對您有幫助，歡迎花 <span class='sec-big'>10 秒</span> 幫個忙填一下。",
            "invite": "💡 **您的真實反應對學術研究非常寶貴**——我們正在收集投資人看到恐慌指標與勝率後的第一直覺，完全自由參與、無需登入。",
            "pre_ethics": (
                "**研究倫理聲明（送出前請閱覽）**：本匿名調查探討檢視美股恐慌指標與歷史勝率後之「反身性」行為反應。"
                "不收集姓名、Email 或 IP，僅記錄時間戳記、當下指標數值與量表分數；採盲測設計不公開即時票數以防從眾偏誤，僅供學術探討，非投資建議。"
            ),
            "expander_label": "📜 檢視完整知情同意細節",
            "ethics_detail": (
                "1. **研究目的**：分別測量投資人檢視指標與歷史勝率後之「主觀情緒（1–5分）」與「操作傾向（1–5分）」。\n"
                "2. **自願與匿名**：參與完全自願，可隨時中止；資料僅儲存於研究者專屬 Google 試算表作彙整分析。\n"
                "3. **盲測防反身性**：填答後不顯示他人投票統計，避免資訊瀑布與從眾效應干擾研究效度。"
            ),
            "q1_label": "【題目一：主觀情緒感受】看到目前數據後，您此刻對美股的情緒偏向？",
            "q1_opts": {
                1: "1 分 — 極度恐慌 / 非常悲觀",
                2: "2 分 — 略感恐慌 / 偏悲觀",
                3: "3 分 — 中性平靜 / 看看聽聽（維持原狀）",
                4: "4 分 — 略感樂觀 / 偏貪婪",
                5: "5 分 — 極度樂觀 / 非常貪婪",
            },
            "q2_label": "【題目二：實際操作傾向】看到目前數據後，您接下來的資金操作傾向？",
            "q2_opts": {
                1: "1 分 — 傾向大幅減碼 / 賣出避險",
                2: "2 分 — 傾向小幅減碼 / 保守防禦",
                3: "3 分 — 按兵不動 / 觀望或堅持原本定見",
                4: "4 分 — 傾向分批試單 / 小幅逆向買進",
                5: "5 分 — 傾向積極加碼 / 大幅逆向買進",
            },
            "consent_chk": "我已閱讀上述研究倫理聲明，並同意以完全匿名方式參與本研究",
            "unlock_hint": "⏳ 請先點選上方兩題選項，並勾選研究倫理同意聲明，即可解鎖送出按鈕。",
            "submit": "✨ 匿名送出兩題量表",
            "thank_line": "我們謝謝你 😊",
            "thank_sub": "您的匿名作答已記錄（採盲測設計，不公開即時統計；僅供學術探討，非投資建議）。",
        },
        "en": {
            "badge": "🧪 BEHAVIORAL LAB · ONLY 10 SECONDS",
            "title": "🗳️ Quick Favor: Record Your Market Intuition (5-Point Scale)",
            "center_10s": "⏱️ Takes just <span class='sec-big'>10 seconds</span> to help our research!",
            "prompt_lead": "Found today's indicators helpful? Spend <span class='sec-big'>10 seconds</span> contributing an anonymous data point!",
            "invite": "💡 **Your genuine reaction is invaluable for academic research.** We study investors' immediate intuition after viewing sentiment and win-rate data—voluntary and no login required.",
            "pre_ethics": (
                "**Research Ethics Notice (Please Read Before Submitting)**: This anonymous survey examines investor reflexivity after viewing sentiment indicators and win rates. "
                "No names, emails, or IPs are collected—only timestamps, current indicator values, and scale ratings. Aggregate results remain blinded to prevent herding; for academic research only, not financial advice."
            ),
            "expander_label": "📜 View Full Informed Consent Details",
            "ethics_detail": (
                "1. **Purpose**: Separately measures subjective emotion (1–5) and action tendency (1–5) after viewing sentiment and win-rate data.\n"
                "2. **Voluntary & Anonymous**: Participation is voluntary; responses are stored in the researcher's private Google Sheet for aggregate analysis.\n"
                "3. **Blinded Design**: Live tallies are hidden to prevent herding and information cascades."
            ),
            "q1_label": "[Q1: Subjective Emotion] After viewing the data, how do you feel about US equities?",
            "q1_opts": {
                1: "1 — Extreme Fear / Very Bearish",
                2: "2 — Mild Fear / Slightly Bearish",
                3: "3 — Neutral / Wait-and-See (Unchanged)",
                4: "4 — Mild Greed / Slightly Bullish",
                5: "5 — Extreme Greed / Very Bullish",
            },
            "q2_label": "[Q2: Action Tendency] After viewing the data, what is your intended portfolio action?",
            "q2_opts": {
                1: "1 — Strongly Reduce / Sell to Hedge",
                2: "2 — Slightly Trim / Stay Defensive",
                3: "3 — Hold Steady / Observe or Stick to Prior Plan",
                4: "4 — Scale In / Contrarian Buy Gradually",
                5: "5 — Strongly Add / Aggressive Contrarian Buy",
            },
            "consent_chk": "I have read the research ethics notice above and consent to participate anonymously",
            "unlock_hint": "⏳ Please answer both questions above and check the research ethics consent box to unlock submission.",
            "submit": "✨ Submit Anonymous Ratings",
            "thank_line": "Thank you 😊",
            "thank_sub": "Your anonymous response has been recorded (blinded design, no live tallies; academic research only, not financial advice).",
        },
        "ja": {
            "badge": "🧪 行動実験エリア · たった 10 秒",
            "title": "🗳️ 研究へのご協力：現在の直感をお聞かせください（5段階尺度）",
            "center_10s": "⏱️ たった <span class='sec-big'>10 秒</span> で研究にご協力いただけます！",
            "prompt_lead": "本日の指標はお役に立ちましたか？<span class='sec-big'>10 秒</span> だけお時間をいただき、匿名データの記録にご協力ください！",
            "invite": "💡 **あなたの素直な反応が学術研究の貴重なデータになります。** 恐怖指数と実証勝率を見た直後の心理を調査しています（任意参加・ログイン不要）。",
            "pre_ethics": (
                "**研究倫理声明（送信前にお読みください）**：本匿名調査は恐怖指数と実証勝率を閲覧した後の投資家の再帰性（リフレクシビティ）を検証します。"
                "氏名・メール・IPアドレスは収集せず、タイムスタンプ・指標値・尺度スコアのみを記録します。群集バイアス防止のため集計結果は非公開とし、学術目的のみで投資助言ではありません。"
            ),
            "expander_label": "📜 インフォームドコンセントの詳細を見る",
            "ethics_detail": (
                "1. **研究目的**：指標と勝率を閲覧した後の「主観的感情（1〜5点）」と「行動傾向（1〜5点）」を分離測定します。\n"
                "2. **任意参加・匿名性**：参加は任意であり、データは研究者専用のGoogleスプレッドシートに集計分析用として保存されます。\n"
                "3. **ブラインド設計**：群集行動や情報カスケードを防ぐため、リアルタイム集計は非公開です。"
            ),
            "q1_label": "【質問1：主観的感情】現在のデータを見た後の米国株に対する心理状態は？",
            "q1_opts": {
                1: "1点 — 極度の恐怖 / 非常に弱気",
                2: "2点 — やや恐怖 / 弱気寄り",
                3: "3点 — 中立・様子見（変化なし）",
                4: "4点 — やや強欲 / 強気寄り",
                5: "5点 — 極度の強欲 / 非常に強気",
            },
            "q2_label": "【質問2：実際の行動傾向】現在のデータを見た後の資金配分・売買の意向は？",
            "q2_opts": {
                1: "1点 — 大幅にポジション縮小 / ヘッジ売り",
                2: "2点 — やや縮小 / 守備的に調整",
                3: "3点 — 静観・様子見（当初の方針を維持）",
                4: "4点 — 少しずつ逆張り買い / 打診買い",
                5: "5点 — 積極的に逆張り買い / 大幅買い増し",
            },
            "consent_chk": "上記の研究倫理声明を読み、完全匿名での研究参加に同意します",
            "unlock_hint": "⏳ 上記2つの質問に回答し、研究倫理声明にチェックを入れると送信ボタンが有効になります。",
            "submit": "✨ 匿名で5段階評価を送信",
            "thank_line": "ありがとうございます 😊",
            "thank_sub": "匿名回答を記録しました（ブラインド設計のため集計非公開・学術研究目的であり投資助言ではありません）。",
        },
    }[selected_lang]

    if "voted_in_session" not in st.session_state:
        st.session_state["voted_in_session"] = False
    if "thank_animal" not in st.session_state:
        st.session_state["thank_animal"] = random.choice(CUTE_ANIMALS)

    with st.container(key="survey_lab_box", border=True):
        st.markdown(
            "<div class='lab-badge-wrap'><span class='lab-badge'>" + survey_texts["badge"] + "</span></div>"
            "<div class='lab-hero-center'>" + survey_texts["center_10s"] + "</div>",
            unsafe_allow_html=True,
        )
        st.subheader(survey_texts["title"])
        st.markdown("<div style='text-align:center;'>" + survey_texts["prompt_lead"] + "</div>", unsafe_allow_html=True)
        st.write("")
        st.markdown(survey_texts["invite"])
        st.info(survey_texts["pre_ethics"])
        with st.expander(survey_texts["expander_label"], expanded=False):
            st.markdown(survey_texts["ethics_detail"])

        if not st.session_state["voted_in_session"]:
            emo_score = st.radio(
                survey_texts["q1_label"],
                options=[1, 2, 3, 4, 5],
                index=None,
                format_func=lambda x: survey_texts["q1_opts"][x],
            )
            act_score = st.radio(
                survey_texts["q2_label"],
                options=[1, 2, 3, 4, 5],
                index=None,
                format_func=lambda x: survey_texts["q2_opts"][x],
            )

            agreed = st.checkbox(survey_texts["consent_chk"], value=False)
            can_submit = (emo_score is not None) and (act_score is not None) and bool(agreed)

            if not can_submit:
                st.caption(survey_texts["unlock_hint"])

            if st.button(
                survey_texts["submit"],
                disabled=not can_submit,
                type="primary",
                use_container_width=True,
            ):
                emo_payload = str(emo_score) + " | " + survey_texts["q1_opts"][emo_score]
                act_payload = (
                    str(act_score)
                    + " | 126D_Win:"
                    + str(win_rates["126D"]["final_win_rate"])
                    + "% | "
                    + survey_texts["q2_opts"][act_score]
                )
                form_data = {
                    ENTRY_UPDATED_AT: str(data.get("updated_at", "")),
                    ENTRY_LANG: str(selected_lang),
                    ENTRY_CNN: str(cnn["score"]),
                    ENTRY_VIX: str(vix["vix"]),
                    ENTRY_AAII: str(aaii["bearish"]),
                    ENTRY_EMOTION: emo_payload,
                    ENTRY_ACTION: act_payload,
                }
                try:
                    req_lib.post(GOOGLE_FORM_ACTION_URL, data=form_data, timeout=5)
                except Exception:
                    pass
                st.session_state["thank_animal"] = random.choice(CUTE_ANIMALS)
                st.session_state["voted_in_session"] = True
                st.rerun()
        else:
            icon_ch, name_zh, name_en, name_ja = st.session_state["thank_animal"]
            if selected_lang == "zh-TW":
                animal_label = name_zh
            elif selected_lang == "en":
                animal_label = name_en
            else:
                animal_label = name_ja

            st.success(
                icon_ch
                + " **"
                + animal_label
                + "**："
                + survey_texts["thank_line"]
                + "\n\n"
                + survey_texts["thank_sub"]
            )

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

    if df_hist is not None and not df_hist.empty:
        st.subheader(t["chart_header"])
        selected_mode = st.radio(
            "chart_mode_switch",
            options=[0, 1],
            format_func=lambda i: t["chart_modes"][i],
            horizontal=True,
            label_visibility="collapsed",
        )
        selected_range = st.radio(
            "chart_range_switch",
            options=t["range_opts"],
            format_func=lambda r: t["range_labels"][r],
            index=len(t["range_opts"]) - 1,
            horizontal=True,
            label_visibility="collapsed",
        )

        max_dt = df_hist.index.max()
        range_days = {
            "3M": 92,
            "6M": 183,
            "1Y": 365,
            "3Y": 1096,
            "5Y": 1826,
        }
        if selected_range in range_days and pd.notna(max_dt):
            df_filtered = df_hist[df_hist.index >= (max_dt - pd.Timedelta(days=range_days[selected_range]))]
        elif selected_range == "2011+":
            df_filtered = df_hist[df_hist.index >= pd.Timestamp("2011-01-01")]
        else:
            df_filtered = df_hist

        if selected_mode == 0:
            df_chart_src = df_filtered
            chart_obj = build_aligned_fear_chart(df_chart_src, include_aaii=False)
            if chart_obj is not None:
                st.altair_chart(chart_obj, use_container_width=True)
                st.caption(t["chart_caption"])
        else:
            weekly_cols = [c for c in ["CNN_FG", "VIX", "AAII_Bearish", "SP500", "SP500_DD", "NDX"] if c in df_filtered.columns]
            if any(c in weekly_cols for c in ["CNN_FG", "VIX", "AAII_Bearish"]):
                df_chart_src = df_filtered[weekly_cols].resample("W-FRI").last().dropna(how="all")
                chart_obj = build_aligned_fear_chart(df_chart_src, include_aaii=True)
                if chart_obj is not None:
                    st.altair_chart(chart_obj, use_container_width=True)
                    st.caption(t["chart_caption"])
            else:
                df_chart_src = df_filtered
                st.info("Weekly series pending next GitHub Actions run.")

        with st.expander(t["bench_expander"], expanded=False):
            bench_choice = st.radio(
                "bench_index_switch",
                options=[0, 1],
                format_func=lambda i: t["bench_opts"][i],
                horizontal=True,
                label_visibility="collapsed",
            )
            target_col = "SP500" if bench_choice == 0 else "NDX"
            target_label = "S&P 500" if bench_choice == 0 else "NASDAQ-100"
            target_color = "#334155" if bench_choice == 0 else "#7C3AED"

            bench_chart = build_parallel_index_chart(df_chart_src, target_col, target_label, target_color)
            if bench_chart is not None:
                st.altair_chart(bench_chart, use_container_width=True)
                st.caption(t["bench_caption"])
            else:
                st.info(t["bench_pending"])

# ================= 分頁二：⚡ 點這裡直接看結論（極簡懶人漏斗） =================
with tab_brief:
    st.subheader(t["brief_title"])

    # 1. 置頂：60 秒「登、登、登」語音播放器
    st.markdown(f"**{t['brief_audio_title']}**")
    if os.path.exists(AUDIO_PATH) and os.path.getsize(AUDIO_PATH) > 1000:
        with open(AUDIO_PATH, "rb") as af:
            st.audio(af.read(), format="audio/mp3")
    else:
        st.info(t["brief_audio_pending"])

    # 2. 中央：直接呈現「等燈燈」爆款戰情圖卡（固定 6 個月基準、含日期與滿版 QR Code）
    date_slug = str(data.get("updated_at", "")).split(" ")[0] or "latest"
    poster_bytes = generate_dengdengdeng_poster_png(data)
    st.image(poster_bytes, use_container_width=True)

    # 3. 圖卡正下方：一鍵下載 ＋ 真剪貼簿一鍵複製按鈕 ＋ 各大社群分享列
    share_caption = build_brief_share_text(data)
    encoded_text = urllib.parse.quote(share_caption)
    encoded_url = urllib.parse.quote(APP_BRIEF_URL)

    threads_share_url = f"https://www.threads.net/intent/post?text={encoded_text}"
    fb_share_url = f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}&quote={encoded_text}"
    x_share_url = f"https://twitter.com/intent/tweet?text={encoded_text}"
    line_share_url = f"https://social-plugins.line.me/lineit/share?url={encoded_url}&text={encoded_text}"

    top_col1, top_col2 = st.columns(2)
    with top_col1:
        st.download_button(
            label=t["brief_download_btn"],
            data=poster_bytes,
            file_name=f"dengdengdeng_{date_slug}.png",
            mime="image/png",
            type="primary",
            use_container_width=True,
        )
    with top_col2:
        copy_html = f"""
        <button id="copyBriefBtn" onclick="copyBriefText()" style="
            width: 100%;
            height: 38.4px;
            background-color: #111827;
            color: #FACC15;
            border: 1.5px solid #111827;
            border-radius: 8px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
        ">📋 一鍵複製文案與連結（IG / 抖音 / 群組貼上）</button>
        <script>
        function copyBriefText() {{
            const text = {json.dumps(share_caption)};
            navigator.clipboard.writeText(text).then(function() {{
                const btn = document.getElementById('copyBriefBtn');
                btn.innerText = '✅ 已複製！可直接去 IG / 抖音 / 群組貼上';
                btn.style.backgroundColor = '#166534';
                btn.style.color = '#FFFFFF';
                setTimeout(function() {{
                    btn.innerText = '📋 一鍵複製文案與連結（IG / 抖音 / 群組貼上）';
                    btn.style.backgroundColor = '#111827';
                    btn.style.color = '#FACC15';
                }}, 3000);
            }});
        }}
        </script>
        """
        st.components.v1.html(copy_html, height=46)

    s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns(5)
    with s_col1:
        st.link_button("🧵 Threads", threads_share_url, use_container_width=True)
    with s_col2:
        st.link_button("📘 Facebook", fb_share_url, use_container_width=True)
    with s_col3:
        st.link_button("𝕏 X / Twitter", x_share_url, use_container_width=True)
    with s_col4:
        st.link_button("💬 LINE", line_share_url, use_container_width=True)
    with s_col5:
        st.link_button("📸 IG / 抖音", "https://www.instagram.com/", use_container_width=True)

    st.caption(f"🔗 乾淨快報網址（可直接長按或點擊右側複製圖示）：`{APP_BRIEF_URL}`")
    with st.expander(t["brief_copy_title"], expanded=False):
        st.code(share_caption, language=None)

# ================= 分頁三：維持原樣不改 =================
with tab_acad:
    st.markdown(t["academic_md"])
    st.link_button(t["github_btn"], GITHUB_REPO_URL)
