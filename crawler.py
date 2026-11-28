import datetime
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import StringIO

import numpy as np
import pandas as pd
import requests
import yfinance as yf

DATA_DIR = "data"
JSON_PATH = os.path.join(DATA_DIR, "sentiment_data.json")
CSV_PATH = os.path.join(DATA_DIR, "history_backtest.csv")

LOCAL_VIX_PATH = "VIX_History.csv"
LOCAL_CNN_PATH = "fear-greed.csv"
LOCAL_AAII_PATH = "aaii_history.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/",
}


def load_local_vix():
    if not os.path.exists(LOCAL_VIX_PATH):
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(LOCAL_VIX_PATH)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        close_col = next((c for c in df.columns if "close" in c.lower()), None)
        if not date_col or not close_col:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df["VIX"] = pd.to_numeric(df[close_col], errors="coerce")
        df = df.dropna(subset=["Date", "VIX"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        return df.set_index("Date")["VIX"]
    except Exception as e:
        print(f"[WARN] load_local_vix failed: {e}")
        return pd.Series(dtype=float)


def load_local_cnn():
    if not os.path.exists(LOCAL_CNN_PATH):
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(LOCAL_CNN_PATH)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        val_col = next((c for c in df.columns if "fear" in c.lower() or "score" in c.lower() or "value" in c.lower()), None)
        if not date_col or not val_col:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df["CNN_FG"] = pd.to_numeric(df[val_col], errors="coerce")
        df = df.dropna(subset=["Date", "CNN_FG"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        return df.set_index("Date")["CNN_FG"]
    except Exception as e:
        print(f"[WARN] load_local_cnn failed: {e}")
        return pd.Series(dtype=float)


def load_local_aaii():
    if not os.path.exists(LOCAL_AAII_PATH):
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(LOCAL_AAII_PATH)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        bear_col = next((c for c in df.columns if "bear" in c.lower()), None)
        if not date_col or not bear_col:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df["AAII_Bearish"] = pd.to_numeric(df[bear_col], errors="coerce")
        df = df.dropna(subset=["Date", "AAII_Bearish"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        return df.set_index("Date")["AAII_Bearish"]
    except Exception as e:
        print(f"[WARN] load_local_aaii failed: {e}")
        return pd.Series(dtype=float)


def fetch_cnn_fear_greed(local_cnn_series):
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    live_series = pd.Series(dtype=float)
    current_score = None
    rating = "Unknown"
    prev_close = None

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        fg = data.get("fear_and_greed", {})
        if fg.get("score") is not None:
            current_score = round(float(fg["score"]), 2)
        rating = str(fg.get("rating", "Unknown"))
        if fg.get("previous_close") is not None:
            prev_close = round(float(fg["previous_close"]), 2)

        hist_list = data.get("fear_and_greed_historical", {}).get("data", [])
        rows = []
        for item in hist_list:
            ts = item.get("x")
            val = item.get("y")
            if ts is not None and val is not None:
                dt = pd.to_datetime(ts, unit="ms").normalize()
                rows.append((dt, float(val)))
        if rows:
            df_live = pd.DataFrame(rows, columns=["Date", "CNN_FG"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
            live_series = df_live.set_index("Date")["CNN_FG"]
    except Exception as e:
        print(f"[WARN] CNN live API fetch failed: {e}")

    combined = pd.concat([local_cnn_series, live_series])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    if not combined.empty:
        if current_score is None:
            current_score = round(float(combined.iloc[-1]), 2)
        if prev_close is None and len(combined) >= 2:
            prev_close = round(float(combined.iloc[-2]), 2)
        if prev_close is None:
            prev_close = current_score
        if rating == "Unknown":
            if current_score <= 25:
                rating = "Extreme Fear"
            elif current_score <= 45:
                rating = "Fear"
            elif current_score <= 55:
                rating = "Neutral"
            elif current_score <= 75:
                rating = "Greed"
            else:
                rating = "Extreme Greed"
    else:
        current_score = 50.0
        prev_close = 50.0
        rating = "Neutral"

    return {
        "score": current_score,
        "rating": rating,
        "prev_close": prev_close,
        "series": combined,
    }


def fetch_aaii_sentiment(local_aaii_series):
    latest = {
        "date": str(local_aaii_series.index.max().date()) if not local_aaii_series.empty else "N/A",
        "bullish": 35.0,
        "neutral": 30.0,
        "bearish": round(float(local_aaii_series.iloc[-1]), 2) if not local_aaii_series.empty else 35.0,
    }
    latest["spread"] = round(latest["bullish"] - latest["bearish"], 2)
    live_series = pd.Series(dtype=float)

    try:
        resp = requests.get("https://www.aaii.com/sentimentsurvey/sent_results", headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            tables = pd.read_html(StringIO(resp.text))
            for tbl in tables:
                cols = [str(c).lower() for c in tbl.columns]
                if any("bull" in c for c in cols) and any("bear" in c for c in cols):
                    tbl.columns = [str(c).strip() for c in tbl.columns]
                    date_col = tbl.columns[0]
                    bull_col = next(c for c in tbl.columns if "bull" in c.lower())
                    neut_col = next(c for c in tbl.columns if "neut" in c.lower())
                    bear_col = next(c for c in tbl.columns if "bear" in c.lower())

                    sub = tbl[[date_col, bull_col, neut_col, bear_col]].copy()
                    sub["Date"] = pd.to_datetime(sub[date_col], errors="coerce").dt.normalize()
                    for col in [bull_col, neut_col, bear_col]:
                        sub[col] = (
                            sub[col]
                            .astype(str)
                            .str.replace("%", "", regex=False)
                            .str.strip()
                        )
                        sub[col] = pd.to_numeric(sub[col], errors="coerce")
                    sub = sub.dropna(subset=["Date", bear_col]).sort_values("Date")
                    if not sub.empty:
                        last_row = sub.iloc[-1]
                        latest = {
                            "date": str(last_row["Date"].date()),
                            "bullish": round(float(last_row[bull_col]), 2),
                            "neutral": round(float(last_row[neut_col]), 2),
                            "bearish": round(float(last_row[bear_col]), 2),
                            "spread": round(float(last_row[bull_col] - last_row[bear_col]), 2),
                        }
                        live_series = sub.drop_duplicates(subset=["Date"], keep="last").set_index("Date")[bear_col]
                        break
    except Exception as e:
        print(f"[WARN] AAII live scrape skipped: {e}")

    combined = pd.concat([local_aaii_series, live_series])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    if not combined.empty and latest["date"] == "N/A":
        latest["date"] = str(combined.index.max().date())
        latest["bearish"] = round(float(combined.iloc[-1]), 2)
        latest["spread"] = round(latest["bullish"] - latest["bearish"], 2)

    return latest, combined


def download_close_series(ticker, start_date="1990-01-01"):
    try:
        df = yf.download(ticker, start=start_date, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        if isinstance(df.columns, pd.MultiIndex):
            s = df["Close"][ticker]
        else:
            s = df["Close"]
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
        return s[~s.index.duplicated(keep="last")]
    except Exception as e:
        print(f"[WARN] yfinance download failed for {ticker}: {e}")
        return pd.Series(dtype=float)


def compute_empirical_win_rates(df, cnn_now, vix_now, aaii_bear_now):
    horizons = {"21D": 21, "63D": 63, "126D": 126, "252D": 252}
    results = {}

    for code, days in horizons.items():
        fwd_sp = df["SP500"].shift(-days) / df["SP500"] - 1.0
        fwd_ndx = df["NDX"].shift(-days) / df["NDX"] - 1.0

        # CNN Fear condition (historical subset where CNN_FG exists)
        cnn_thresh = min(max(cnn_now + 3.0, 25.0), 45.0) if cnn_now <= 45 else 45.0
        mask_cnn = df["CNN_FG"].notna() & (df["CNN_FG"] <= cnn_thresh) & fwd_sp.notna()
        if mask_cnn.sum() >= 15:
            win_cnn = float((fwd_sp[mask_cnn] > 0).mean() * 100.0)
        else:
            valid_cnn = df["CNN_FG"].notna() & fwd_sp.notna()
            win_cnn = float((fwd_sp[valid_cnn] > 0).mean() * 100.0) if valid_cnn.sum() > 0 else 70.0

        # VIX Fear condition (full 1990-present history)
        vix_thresh = max(min(vix_now - 2.0, 30.0), 20.0) if vix_now >= 20 else 20.0
        mask_vix = df["VIX"].notna() & (df["VIX"] >= vix_thresh) & fwd_sp.notna()
        if mask_vix.sum() >= 15:
            win_vix = float((fwd_sp[mask_vix] > 0).mean() * 100.0)
        else:
            valid_vix = df["VIX"].notna() & fwd_sp.notna()
            win_vix = float((fwd_sp[valid_vix] > 0).mean() * 100.0) if valid_vix.sum() > 0 else 72.0

        # AAII extreme bearish bonus
        if aaii_bear_now >= 50.0:
            aaii_bonus = 6.0
        elif aaii_bear_now >= 40.0:
            aaii_bonus = 3.0
        else:
            aaii_bonus = 1.5

        final_win = min(round(0.5 * win_cnn + 0.5 * win_vix + aaii_bonus, 2), 99.5)

        # Analogous historical days for sample size & average returns
        mask_combo = mask_vix if cnn_now > 45 else (mask_cnn | mask_vix)
        if mask_combo.sum() < 10:
            mask_combo = fwd_sp.notna()

        sp_avg = float(fwd_sp[mask_combo].mean() * 100.0) if mask_combo.sum() > 0 else 0.0
        ndx_valid = mask_combo & fwd_ndx.notna()
        ndx_avg = float(fwd_ndx[ndx_valid].mean() * 100.0) if ndx_valid.sum() > 0 else sp_avg

        results[code] = {
            "final_win_rate": final_win,
            "win_cnn": round(win_cnn, 2),
            "win_vix": round(win_vix, 2),
            "aaii_bonus": round(aaii_bonus, 2),
            "sp_avg_ret": round(sp_avg, 2),
            "ndx_avg_ret": round(ndx_avg, 2),
            "sample_size": int(mask_combo.sum()),
        }

    return results


def send_alert_email(payload):
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.environ.get("ALERT_RECIPIENT", gmail_user).strip()

    if not gmail_user or not gmail_pass or not recipient:
        print("[INFO] Email credentials not set; skipping alert email.")
        return

    win_126 = payload["win_rates"]["126D"]["final_win_rate"]
    threshold = payload.get("alert_threshold", 90.0)
    if win_126 < threshold:
        print(f"[INFO] 126D win rate {win_126}% < {threshold}%, no alert sent.")
        return

    subject = f"🚨 美股恐慌逆向雷達警報：6個月實證勝率達 {win_126}%（{payload['lights']['green_count']}/3 綠燈）"
    body = (
        f"資料更新時間：{payload['updated_at']}\n"
        f"1. CNN Fear & Greed：{payload['cnn']['score']} ({payload['cnn']['rating']})\n"
        f"2. CBOE VIX：{payload['vix']['vix']}\n"
        f"3. AAII 散戶看空比例：{payload['aaii']['bearish']}%（{payload['aaii']['date']}）\n"
        f"4. 6個月（126交易日）歷史綜合勝率：{win_126}%\n"
        f"5. S&P 500 距離歷史前高回檔：{payload['sp500']['drawdown_pct']}%\n"
    )

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [recipient], msg.as_string())
        print(f"[INFO] Alert email sent to {recipient}")
    except Exception as e:
        print(f"[WARN] Failed to send alert email: {e}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    local_vix = load_local_vix()
    local_cnn = load_local_cnn()
    local_aaii = load_local_aaii()

    cnn_res = fetch_cnn_fear_greed(local_cnn)
    aaii_latest, aaii_series = fetch_aaii_sentiment(local_aaii)

    vix_yf = download_close_series("^VIX", start_date="1990-01-01")
    vix_series = pd.concat([local_vix, vix_yf])
    vix_series = vix_series[~vix_series.index.duplicated(keep="last")].sort_index()

    sp_series = download_close_series("^GSPC", start_date="1990-01-01")
    ndx_series = download_close_series("^NDX", start_date="1990-01-01")

    master_idx = sp_series.index.union(vix_series.index).sort_values()
    df = pd.DataFrame(index=master_idx)
    df.index.name = "Date"
    df["SP500"] = sp_series.reindex(master_idx).ffill()
    df["NDX"] = ndx_series.reindex(master_idx).ffill()
    df["SP500_DD"] = ((df["SP500"] / df["SP500"].cummax()) - 1.0) * 100.0
    df["VIX"] = vix_series.reindex(master_idx)
    df["CNN_FG"] = cnn_res["series"].reindex(master_idx)

    if not aaii_series.empty:
        aaii_union = master_idx.union(aaii_series.index).sort_values()
        df["AAII_Bearish"] = aaii_series.reindex(aaii_union).ffill(limit=10).reindex(master_idx)
    else:
        df["AAII_Bearish"] = np.nan

    df_export = df.reset_index()
    df_export["Date"] = df_export["Date"].dt.strftime("%Y-%m-%d")
    for col in ["SP500", "NDX", "SP500_DD", "VIX", "CNN_FG", "AAII_Bearish"]:
        df_export[col] = pd.to_numeric(df_export[col], errors="coerce").round(2)
    df_export.to_csv(CSV_PATH, index=False)

    vix_valid = vix_series.dropna()
    vix_now = round(float(vix_valid.iloc[-1]), 2) if not vix_valid.empty else 20.0
    vix_prev = round(float(vix_valid.iloc[-2]), 2) if len(vix_valid) >= 2 else vix_now

    cnn_now = cnn_res["score"]
    aaii_bear_now = aaii_latest["bearish"]

    cnn_level = "green" if cnn_now <= 25 else ("yellow" if cnn_now <= 45 else "red")
    vix_level = "green" if vix_now >= 30 else ("yellow" if vix_now >= 20 else "red")
    aaii_level = "green" if aaii_bear_now >= 50 else ("yellow" if aaii_bear_now >= 40 else "red")
    green_count = sum(1 for lvl in [cnn_level, vix_level, aaii_level] if lvl == "green")

    win_rates = compute_empirical_win_rates(df, cnn_now, vix_now, aaii_bear_now)

    sp_valid = df["SP500"].dropna()
    dd_valid = df["SP500_DD"].dropna()
    sp_now = round(float(sp_valid.iloc[-1]), 2) if not sp_valid.empty else 0.0
    dd_now = round(float(dd_valid.iloc[-1]), 2) if not dd_valid.empty else 0.0

    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    updated_str = datetime.datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M UTC+8")

    payload = {
        "updated_at": updated_str,
        "alert_threshold": 90.0,
        "sp500": {
            "close": sp_now,
            "drawdown_pct": dd_now,
        },
        "cnn": {
            "score": cnn_now,
            "rating": cnn_res["rating"],
            "prev_close": cnn_res["prev_close"],
        },
        "vix": {
            "vix": vix_now,
            "vix_prev": vix_prev,
        },
        "aaii": aaii_latest,
        "lights": {
            "cnn_level": cnn_level,
            "vix_level": vix_level,
            "aaii_level": aaii_level,
            "green_count": green_count,
        },
        "win_rates": win_rates,
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    send_alert_email(payload)
    print("[SUCCESS] Sentiment data & backtest CSV updated successfully.")


if __name__ == "__main__":
    main()
