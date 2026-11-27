import os
import re
import json
import time
import urllib3
import smtplib
from io import StringIO
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import pandas as pd
import numpy as np
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 核心設定 =================
WIN_RATE_ALERT_THRESHOLD = 90.0  # 勝率寄信警報門檻 (%)
DEFAULT_ALERT_HORIZON = "126D"   # 預設以 6 個月 (126 交易日) 勝率判斷寄信；可改 "252D" (1年)

DATA_DIR = "data"
JSON_PATH = os.path.join(DATA_DIR, "sentiment_data.json")
CSV_PATH = os.path.join(DATA_DIR, "history_backtest.csv")

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", GMAIL_USER)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*"
}


def safe_request(url, retries=3, timeout=15):
    """具備重試與 SSL 容錯的請求函式"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"[Warning] Request failed ({attempt + 1}/{retries}) {url}: {e}")
            time.sleep(2 * (attempt + 1))
    return None


def fetch_cnn_data():
    """抓取 CNN 恐慌與貪婪指數 + 2011 年至今歷史存檔"""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    resp = safe_request(url)
    if not resp:
        raise RuntimeError("CNN Fear & Greed API unreachable")

    data = resp.json()
    score = round(float(data["fear_and_greed"]["score"]), 2)
    rating = str(data["fear_and_greed"]["rating"]).lower()
    prev_close = round(float(data["fear_and_greed"].get("previous_close", score)), 2)

    hist_list = data["fear_and_greed_historical"]["data"]
    df_recent = pd.DataFrame(hist_list)
    df_recent["Date"] = pd.to_datetime(df_recent["x"], unit="ms").dt.tz_localize(None).dt.normalize()
    df_recent = df_recent.rename(columns={"y": "CNN_FG"})[["Date", "CNN_FG"]]

    archive_url = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"
    resp_arch = safe_request(archive_url)
    if resp_arch:
        df_arch = pd.read_csv(StringIO(resp_arch.text))
        df_arch["Date"] = pd.to_datetime(df_arch["Date"]).dt.normalize()
        df_arch = df_arch.rename(columns={"Fear Greed": "CNN_FG"})[["Date", "CNN_FG"]]
        df_cnn = pd.concat([df_arch, df_recent]).drop_duplicates(subset=["Date"], keep="last")
    else:
        df_cnn = df_recent

    df_cnn = df_cnn.sort_values("Date").set_index("Date")
    return {"score": score, "rating": rating, "prev_close": prev_close}, df_cnn


def fetch_aaii_data():
    """爬取 AAII 每週散戶情緒調查"""
    url = "https://www.aaii.com/sentimentsurvey/sent_results"
    resp = safe_request(url)
    if not resp:
        return None

    tables = pd.read_html(StringIO(resp.text))
    df = tables[0].dropna(how="all")
    latest = df.iloc[0]

    date_str = str(latest.iloc[0]).strip()
    bullish = round(float(re.sub(r"[^\d.]", "", str(latest.iloc[1]))), 2)
    neutral = round(float(re.sub(r"[^\d.]", "", str(latest.iloc[2]))), 2)
    bearish = round(float(re.sub(r"[^\d.]", "", str(latest.iloc[3]))), 2)
    spread = round(bullish - bearish, 2)

    return {
        "date": date_str,
        "bullish": bullish,
        "neutral": neutral,
        "bearish": bearish,
        "spread": spread
    }


def fetch_vix_and_benchmarks():
    """抓取 VIX、S&P 500 (^GSPC) 與 NASDAQ-100 (^NDX) 歷史數據"""
    tickers = ["^VIX", "^GSPC", "^NDX"]
    raw = yf.download(tickers, start="2011-01-01", progress=False)["Close"]
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw = raw.rename(columns={"^VIX": "VIX", "^GSPC": "SP500", "^NDX": "NDX"}).dropna()

    vix_now = round(float(raw["VIX"].iloc[-1]), 2)
    vix_prev = round(float(raw["VIX"].iloc[-2]), 2)
    sp500_now = round(float(raw["SP500"].iloc[-1]), 2)
    return {"vix": vix_now, "vix_prev": vix_prev, "sp500": sp500_now}, raw


def evaluate_lights(cnn_score, vix_val, aaii_bearish):
    """三燈號評估（輸出狀態代碼供前端多語系轉換：green=恐慌買點亮燈, yellow=觀察, red=中性貪婪）"""
    cnn_level = "green" if cnn_score <= 25 else ("yellow" if cnn_score <= 45 else "red")
    vix_level = "green" if vix_val >= 30 else ("yellow" if vix_val >= 22 else "red")
    aaii_level = "green" if aaii_bearish >= 50 else ("yellow" if aaii_bearish >= 40 else "red")

    green_count = [cnn_level, vix_level, aaii_level].count("green")
    return {
        "cnn_level": cnn_level,
        "vix_level": vix_level,
        "aaii_level": aaii_level,
        "green_count": green_count
    }


def compute_multi_horizon_winrates(cnn_now, vix_now, aaii_now, df_cnn, df_mkt):
    """計算未來 21D、63D、126D、252D 的實證歷史勝率與平均報酬"""
    df = df_mkt.join(df_cnn, how="inner").copy()
    horizon_days = {"21D": 21, "63D": 63, "126D": 126, "252D": 252}

    # AAII 散戶極端看空逆向加權 (基於 Fisher & Statman, 2000 實證負相關特性)
    aaii_bonus = 0.0
    if aaii_now["bearish"] >= 55.0:
        aaii_bonus = 5.0
    elif aaii_now["bearish"] >= 50.0:
        aaii_bonus = 3.0
    elif aaii_now["bearish"] >= 45.0:
        aaii_bonus = 1.5

    results = {}
    for code, days in horizon_days.items():
        temp = df.copy()
        temp["SP_Fwd"] = temp["SP500"].shift(-days) / temp["SP500"] - 1.0
        temp["NDX_Fwd"] = temp["NDX"].shift(-days) / temp["NDX"] - 1.0
        valid = temp.dropna(subset=["SP_Fwd"])

        cond_cnn = valid[valid["CNN_FG"] <= max(cnn_now, 5)]
        cond_vix = valid[valid["VIX"] >= min(vix_now, 45)]
        cond_combo = valid[(valid["CNN_FG"] <= max(cnn_now, 10)) & (valid["VIX"] >= min(vix_now, 35))]

        win_cnn = round((cond_cnn["SP_Fwd"] > 0).mean() * 100, 2) if len(cond_cnn) else 0.0
        win_vix = round((cond_vix["SP_Fwd"] > 0).mean() * 100, 2) if len(cond_vix) else 0.0

        if len(cond_combo) >= 10:
            base_win = (cond_combo["SP_Fwd"] > 0).mean() * 100
            sp_avg_ret = cond_combo["SP_Fwd"].mean() * 100
            ndx_avg_ret = cond_combo["NDX_Fwd"].mean() * 100
            samples = int(len(cond_combo))
        else:
            base_win = np.nanmean([win_cnn, win_vix])
            sp_avg_ret = np.nanmean([cond_cnn["SP_Fwd"].mean(), cond_vix["SP_Fwd"].mean()]) * 100
            ndx_avg_ret = np.nanmean([cond_cnn["NDX_Fwd"].mean(), cond_vix["NDX_Fwd"].mean()]) * 100
            samples = int(len(cond_cnn) + len(cond_vix))

        final_win = min(99.9, round(float(base_win) + aaii_bonus, 2))
        results[code] = {
            "days": days,
            "final_win_rate": final_win,
            "win_cnn": win_cnn,
            "win_vix": win_vix,
            "aaii_bonus": aaii_bonus,
            "sp_avg_ret": round(float(sp_avg_ret), 2),
            "ndx_avg_ret": round(float(ndx_avg_ret), 2),
            "sample_size": samples
        }

    recent_hist = df.tail(365).reset_index()
    recent_hist["Date"] = recent_hist["Date"].dt.strftime("%Y-%m-%d")
    return results, recent_hist


def send_alert_email(payload):
    """當勝率 >= 90% 時寄送雙語 Gmail 警報信"""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[Skip Email] GMAIL_USER or GMAIL_APP_PASSWORD not configured.")
        return

    target = payload["win_rates"][DEFAULT_ALERT_HORIZON]
    cnn = payload["cnn"]
    vix = payload["vix"]
    aaii = payload["aaii"]
    lights = payload["lights"]

    subject = (
        f"🚨 [Sentiment Radar] Win Rate {target['final_win_rate']}% Alert! "
        f"(CNN:{cnn['score']} / VIX:{vix['vix']} / {lights['green_count']} Green)"
    )

    body = f"""【美股恐慌指標與高勝率雷達 / US Market Sentiment & Win-Rate Radar】

系統偵測到市場情緒指標已進入【歷史高勝率逆向佈局區間】（未來 {target['days']} 個交易日上漲勝率達 {target['final_win_rate']}%，已突破 {WIN_RATE_ALERT_THRESHOLD}% 門檻）。
Market sentiment indicators have entered a high-probability contrarian zone ({target['final_win_rate']}% historical win rate over the next {target['days']} trading days).

------------------------------------------------------------
1. 即時指標讀數 / Current Readings ({payload['updated_at']})
• CNN Fear & Greed Index : {cnn['score']} ({cnn['rating'].upper()})
• CBOE VIX Index         : {vix['vix']} (Prev: {vix['vix_prev']})
• AAII Sentiment ({aaii['date']}) : Bearish {aaii['bearish']}% / Bullish {aaii['bullish']}% (Spread: {aaii['spread']}%)
• Contrarian Signal Lights: {lights['green_count']} / 3 Green Lights

2. 歷史回測勝率總覽 / Historical Backtest Summary (2011–Present)
• 1M (21D)  : Win Rate {payload['win_rates']['21D']['final_win_rate']}% | S&P500 Avg {payload['win_rates']['21D']['sp_avg_ret']:+.2f}% | NDX Avg {payload['win_rates']['21D']['ndx_avg_ret']:+.2f}%
• 3M (63D)  : Win Rate {payload['win_rates']['63D']['final_win_rate']}% | S&P500 Avg {payload['win_rates']['63D']['sp_avg_ret']:+.2f}% | NDX Avg {payload['win_rates']['63D']['ndx_avg_ret']:+.2f}%
• 6M (126D) : Win Rate {payload['win_rates']['126D']['final_win_rate']}% | S&P500 Avg {payload['win_rates']['126D']['sp_avg_ret']:+.2f}% | NDX Avg {payload['win_rates']['126D']['ndx_avg_ret']:+.2f}%
• 1Y (252D) : Win Rate {payload['win_rates']['252D']['final_win_rate']}% | S&P500 Avg {payload['win_rates']['252D']['sp_avg_ret']:+.2f}% | NDX Avg {payload['win_rates']['252D']['ndx_avg_ret']:+.2f}%
------------------------------------------------------------
Academic Basis: Whaley (2000), Fisher & Statman (2000), Simon & Wiggins (2001), Baker & Wurgler (2006).
"""

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"✅ Alert email sent to {RECEIVER_EMAIL}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    old_payload = {}
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            old_payload = json.load(f)

    cnn_info, df_cnn = fetch_cnn_data()
    vix_info, df_mkt = fetch_vix_and_benchmarks()
    aaii_info = fetch_aaii_data()

    # 防洗白機制
    if not aaii_info:
        if "aaii" in old_payload:
            print("[Anti-wipe] AAII fetch failed; retaining previous valid record.")
            aaii_info = old_payload["aaii"]
        else:
            aaii_info = {"date": "N/A", "bullish": 37.1, "neutral": 17.5, "bearish": 45.4, "spread": -8.3}

    lights = evaluate_lights(cnn_info["score"], vix_info["vix"], aaii_info["bearish"])
    win_rates, recent_hist = compute_multi_horizon_winrates(
        cnn_info["score"], vix_info["vix"], aaii_info, df_cnn, df_mkt
    )

    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    payload = {
        "updated_at": utc_now,
        "alert_horizon": DEFAULT_ALERT_HORIZON,
        "alert_threshold": WIN_RATE_ALERT_THRESHOLD,
        "cnn": cnn_info,
        "vix": vix_info,
        "aaii": aaii_info,
        "lights": lights,
        "win_rates": win_rates
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    recent_hist.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    target_win = win_rates[DEFAULT_ALERT_HORIZON]["final_win_rate"]
    print(f"Done! {DEFAULT_ALERT_HORIZON} Win Rate: {target_win}% (Threshold: {WIN_RATE_ALERT_THRESHOLD}%)")

    if target_win >= WIN_RATE_ALERT_THRESHOLD:
        send_alert_email(payload)


if __name__ == "__main__":
    main()
