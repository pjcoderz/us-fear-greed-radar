import json
import os
import re
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import StringIO

import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WIN_RATE_ALERT_THRESHOLD = 90.0
DEFAULT_ALERT_HORIZON = "126D"

DATA_DIR = "data"
JSON_PATH = os.path.join(DATA_DIR, "sentiment_data.json")
CSV_PATH = os.path.join(DATA_DIR, "history_backtest.csv")

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", GMAIL_USER)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/html, text/csv, */*",
}


def safe_request(url, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            if resp.text and len(resp.text.strip()) > 0:
                return resp
        except Exception as e:
            print("[Warn] Request retry", attempt + 1, url, str(e))
            time.sleep(2 * (attempt + 1))
    return None


def _parse_float(val, min_val=None, max_val=None):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "--", "n/a", ""):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", s)
    if not cleaned or cleaned in (".", "-"):
        return None
    try:
        num = float(cleaned)
        if np.isnan(num) or np.isinf(num):
            return None
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return round(num, 2)
    except Exception:
        return None


def fetch_cnn_data():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    resp = safe_request(url)

    score = None
    rating = "fear"
    prev_close = None
    df_recent = pd.DataFrame(columns=["Date", "CNN_FG"])

    if resp:
        try:
            data = resp.json()
            fg = data.get("fear_and_greed", {})
            score = _parse_float(fg.get("score"), 0, 100)
            rating = str(fg.get("rating", "fear")).lower()
            prev_close = _parse_float(fg.get("previous_close"), 0, 100)

            hist_list = data.get("fear_and_greed_historical", {}).get("data", [])
            if hist_list:
                tmp = pd.DataFrame(hist_list)
                if "x" in tmp.columns and "y" in tmp.columns:
                    tmp["Date"] = (
                        pd.to_datetime(tmp["x"], unit="ms", errors="coerce")
                        .dt.tz_localize(None)
                        .dt.normalize()
                    )
                    tmp["CNN_FG"] = pd.to_numeric(tmp["y"], errors="coerce")
                    df_recent = tmp[["Date", "CNN_FG"]].dropna()
        except Exception as e:
            print("[Warn] CNN parse:", str(e))

    archive_url = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"
    resp_arch = safe_request(archive_url)
    df_arch = pd.DataFrame(columns=["Date", "CNN_FG"])
    if resp_arch:
        try:
            arch = pd.read_csv(StringIO(resp_arch.text))
            date_col = "Date" if "Date" in arch.columns else arch.columns[0]
            val_col = "Fear Greed" if "Fear Greed" in arch.columns else arch.columns[1]
            arch["Date"] = (
                pd.to_datetime(arch[date_col], errors="coerce")
                .dt.tz_localize(None)
                .dt.normalize()
            )
            arch["CNN_FG"] = pd.to_numeric(arch[val_col], errors="coerce")
            df_arch = arch[["Date", "CNN_FG"]].dropna()
        except Exception as e:
            print("[Warn] CNN archive parse:", str(e))

    df_cnn = pd.concat([df_arch, df_recent], ignore_index=True).dropna()
    if not df_cnn.empty:
        df_cnn = (
            df_cnn.drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
            .set_index("Date")
        )
        if score is None:
            score = round(float(df_cnn["CNN_FG"].iloc[-1]), 2)
        if prev_close is None and len(df_cnn) >= 2:
            prev_close = round(float(df_cnn["CNN_FG"].iloc[-2]), 2)
    else:
        df_cnn = pd.DataFrame(columns=["CNN_FG"])

    if score is None:
        score = 20.0
    if prev_close is None:
        prev_close = score

    return {"score": score, "rating": rating, "prev_close": prev_close}, df_cnn


def _fetch_stooq_series(symbol):
    url = "https://stooq.com/q/d/l/?s=" + symbol + "&i=d"
    resp = safe_request(url)
    if not resp:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(StringIO(resp.text))
        if "Date" not in df.columns or "Close" not in df.columns:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = (
            df.dropna(subset=["Date", "Close"])
            .drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
        )
        df = df[df["Date"] >= "2011-01-01"]
        return df.set_index("Date")["Close"]
    except Exception as e:
        print("[Warn] Stooq series:", symbol, str(e))
        return pd.Series(dtype=float)


def _extract_ticker_close(raw_df, ticker):
    if raw_df is None or raw_df.empty:
        return pd.Series(dtype=float)
    try:
        if isinstance(raw_df.columns, pd.MultiIndex):
            if "Close" in raw_df.columns.get_level_values(0):
                sub = raw_df["Close"]
                if isinstance(sub, pd.DataFrame) and ticker in sub.columns:
                    s = sub[ticker]
                elif isinstance(sub, pd.Series):
                    s = sub
                else:
                    s = pd.Series(dtype=float)
            else:
                s = pd.Series(dtype=float)
        else:
            if ticker in raw_df.columns:
                s = raw_df[ticker]
            elif "Close" in raw_df.columns:
                s = raw_df["Close"]
            else:
                s = pd.Series(dtype=float)

        if s.empty:
            return pd.Series(dtype=float)
        s.index = pd.to_datetime(s.index, errors="coerce").tz_localize(None).normalize()
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[~s.index.isna()].sort_index()
        return s[~s.index.duplicated(keep="last")]
    except Exception as e:
        print("[Warn] Extract ticker:", ticker, str(e))
        return pd.Series(dtype=float)


def fetch_vix_and_benchmarks():
    vix_s = pd.Series(dtype=float)
    sp_s = pd.Series(dtype=float)
    ndx_s = pd.Series(dtype=float)

    try:
        raw = yf.download(
            ["^VIX", "^GSPC", "^NDX"],
            start="2011-01-01",
            progress=False,
            auto_adjust=True,
        )
        vix_s = _extract_ticker_close(raw, "^VIX")
        sp_s = _extract_ticker_close(raw, "^GSPC")
        ndx_s = _extract_ticker_close(raw, "^NDX")
    except Exception as e:
        print("[Warn] yfinance:", str(e))

    if vix_s.empty:
        vix_s = _fetch_stooq_series("^vix")
    if sp_s.empty:
        sp_s = _fetch_stooq_series("^spx")
    if ndx_s.empty:
        ndx_s = _fetch_stooq_series("^ndx")

    df_mkt = pd.DataFrame({"VIX": vix_s, "SP500": sp_s, "NDX": ndx_s}).dropna(subset=["VIX", "SP500"])
    if df_mkt["NDX"].isna().all():
        df_mkt["NDX"] = df_mkt["SP500"]
    else:
        df_mkt["NDX"] = df_mkt["NDX"].ffill().bfill()

    df_mkt = df_mkt.sort_index()
    if df_mkt.empty:
        raise RuntimeError("Market data empty from both sources.")

    vix_now = round(float(df_mkt["VIX"].iloc[-1]), 2)
    vix_prev = round(float(df_mkt["VIX"].iloc[-2]), 2) if len(df_mkt) >= 2 else vix_now
    sp500_now = round(float(df_mkt["SP500"].iloc[-1]), 2)

    return {"vix": vix_now, "vix_prev": vix_prev, "sp500": sp500_now}, df_mkt


def fetch_aaii_data():
    url = "https://www.aaii.com/sentimentsurvey/sent_results"
    resp = safe_request(url)

    if resp:
        try:
            tables = pd.read_html(StringIO(resp.text))
            for tbl in tables:
                df = tbl.dropna(how="all")
                for _, row in df.iterrows():
                    vals = [str(x).strip() for x in row.tolist()]
                    pct_nums = []
                    for v in vals:
                        if "%" in v:
                            parsed = _parse_float(v, 0.0, 100.0)
                            if parsed is not None:
                                pct_nums.append(parsed)
                    if len(pct_nums) >= 3:
                        bullish, neutral, bearish = pct_nums[0], pct_nums[1], pct_nums[2]
                        return {
                            "date": vals[0] if vals else "Latest",
                            "bullish": bullish,
                            "neutral": neutral,
                            "bearish": bearish,
                            "spread": round(bullish - bearish, 2),
                        }
        except Exception as e:
            print("[Warn] AAII HTML:", str(e))

    backup_urls = [
        "https://raw.githubusercontent.com/datasets/aaii-sentiment/main/data/aaii-sentiment.csv",
    ]
    for b_url in backup_urls:
        b_resp = safe_request(b_url)
        if b_resp:
            try:
                bdf = pd.read_csv(StringIO(b_resp.text)).dropna(how="all")
                if not bdf.empty:
                    last = bdf.iloc[-1]
                    bullish = _parse_float(
                        last.get("Bullish", last.iloc[1] if len(last) > 1 else None), 0, 100
                    )
                    neutral = _parse_float(
                        last.get("Neutral", last.iloc[2] if len(last) > 2 else None), 0, 100
                    )
                    bearish = _parse_float(
                        last.get("Bearish", last.iloc[3] if len(last) > 3 else None), 0, 100
                    )
                    if bullish is not None and bearish is not None:
                        if neutral is None:
                            neutral = round(max(0.0, 100.0 - bullish - bearish), 2)
                        return {
                            "date": str(last.iloc[0]),
                            "bullish": bullish,
                            "neutral": neutral,
                            "bearish": bearish,
                            "spread": round(bullish - bearish, 2),
                        }
            except Exception as e:
                print("[Warn] AAII backup:", str(e))

    return None


def evaluate_lights(cnn_score, vix_val, aaii_bearish):
    cnn_level = "green" if cnn_score <= 25 else ("yellow" if cnn_score <= 45 else "red")
    vix_level = "green" if vix_val >= 30 else ("yellow" if vix_val >= 22 else "red")
    aaii_level = "green" if aaii_bearish >= 50 else ("yellow" if aaii_bearish >= 40 else "red")
    green_count = [cnn_level, vix_level, aaii_level].count("green")
    return {
        "cnn_level": cnn_level,
        "vix_level": vix_level,
        "aaii_level": aaii_level,
        "green_count": green_count,
    }


def compute_multi_horizon_winrates(cnn_now, vix_now, aaii_now, df_cnn, df_mkt):
    if df_cnn is not None and not df_cnn.empty:
        df = df_mkt.join(df_cnn, how="left")
        df["CNN_FG"] = df["CNN_FG"].ffill().fillna(cnn_now)
    else:
        df = df_mkt.copy()
        df["CNN_FG"] = cnn_now

    horizon_days = {"21D": 21, "63D": 63, "126D": 126, "252D": 252}

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

        if valid.empty:
            results[code] = {
                "days": days,
                "final_win_rate": 50.0,
                "win_cnn": 50.0,
                "win_vix": 50.0,
                "aaii_bonus": aaii_bonus,
                "sp_avg_ret": 0.0,
                "ndx_avg_ret": 0.0,
                "sample_size": 0,
            }
            continue

        cond_cnn = valid[valid["CNN_FG"] <= max(cnn_now, 5)]
        cond_vix = valid[valid["VIX"] >= min(vix_now, 45)]
        cond_combo = valid[
            (valid["CNN_FG"] <= max(cnn_now, 10)) & (valid["VIX"] >= min(vix_now, 35))
        ]

        win_cnn = round(float((cond_cnn["SP_Fwd"] > 0).mean() * 100), 2) if len(cond_cnn) else 50.0
        win_vix = round(float((cond_vix["SP_Fwd"] > 0).mean() * 100), 2) if len(cond_vix) else 50.0

        if len(cond_combo) >= 10:
            base_win = float((cond_combo["SP_Fwd"] > 0).mean() * 100)
            sp_avg_ret = float(cond_combo["SP_Fwd"].mean() * 100)
            ndx_avg_ret = float(cond_combo["NDX_Fwd"].mean() * 100)
            samples = int(len(cond_combo))
        else:
            sp_rets = [
                x
                for x in [
                    cond_cnn["SP_Fwd"].mean() if len(cond_cnn) else np.nan,
                    cond_vix["SP_Fwd"].mean() if len(cond_vix) else np.nan,
                ]
                if not np.isnan(x)
            ]
            ndx_rets = [
                x
                for x in [
                    cond_cnn["NDX_Fwd"].mean() if len(cond_cnn) else np.nan,
                    cond_vix["NDX_Fwd"].mean() if len(cond_vix) else np.nan,
                ]
                if not np.isnan(x)
            ]
            base_win = float(np.mean([win_cnn, win_vix]))
            sp_avg_ret = float(np.mean(sp_rets) * 100) if sp_rets else 0.0
            ndx_avg_ret = float(np.mean(ndx_rets) * 100) if ndx_rets else 0.0
            samples = int(len(cond_cnn) + len(cond_vix))

        final_win = min(99.9, round(base_win + aaii_bonus, 2))
        results[code] = {
            "days": days,
            "final_win_rate": final_win,
            "win_cnn": win_cnn,
            "win_vix": win_vix,
            "aaii_bonus": aaii_bonus,
            "sp_avg_ret": round(sp_avg_ret, 2),
            "ndx_avg_ret": round(ndx_avg_ret, 2),
            "sample_size": samples,
        }

    recent_hist = df.tail(365).reset_index()
    date_col = recent_hist.columns[0]
    recent_hist["Date"] = pd.to_datetime(recent_hist[date_col]).dt.strftime("%Y-%m-%d")
    return results, recent_hist[["Date", "CNN_FG", "VIX", "SP500", "NDX"]]


def send_alert_email(payload):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[Skip Email] Missing GMAIL_USER or GMAIL_APP_PASSWORD.")
        return

    target = payload["win_rates"][DEFAULT_ALERT_HORIZON]
    cnn = payload["cnn"]
    vix = payload["vix"]
    aaii = payload["aaii"]
    lights = payload["lights"]

    subject = (
        "[Sentiment Radar] Win Rate "
        + str(target["final_win_rate"])
        + "% Alert! (CNN:"
        + str(cnn["score"])
        + " / VIX:"
        + str(vix["vix"])
        + " / "
        + str(lights["green_count"])
        + " Green)"
    )

    body = (
        "US Market Sentiment & Win-Rate Radar\n"
        "Updated: " + str(payload["updated_at"]) + "\n"
        "Target Horizon: " + str(target["days"]) + " trading days\n"
        "Win Rate: " + str(target["final_win_rate"]) + "% (Threshold: " + str(WIN_RATE_ALERT_THRESHOLD) + "%)\n\n"
        "CNN Fear & Greed: " + str(cnn["score"]) + " (" + str(cnn["rating"]).upper() + ")\n"
        "CBOE VIX: " + str(vix["vix"]) + " (Prev: " + str(vix["vix_prev"]) + ")\n"
        "AAII (" + str(aaii["date"]) + "): Bearish " + str(aaii["bearish"]) + "% / Bullish " + str(aaii["bullish"]) + "%\n"
        "Green Lights: " + str(lights["green_count"]) + " / 3\n"
    )

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print("Alert email sent to", RECEIVER_EMAIL)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    old_payload = {}
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                old_payload = json.load(f)
        except Exception:
            old_payload = {}

    cnn_info, df_cnn = fetch_cnn_data()
    vix_info, df_mkt = fetch_vix_and_benchmarks()
    aaii_info = fetch_aaii_data()

    if not aaii_info:
        if "aaii" in old_payload and isinstance(old_payload["aaii"], dict):
            print("[Anti-wipe] Keeping previous AAII data.")
            aaii_info = old_payload["aaii"]
        else:
            aaii_info = {
                "date": "Baseline",
                "bullish": 37.1,
                "neutral": 17.5,
                "bearish": 45.4,
                "spread": -8.3,
            }

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
        "win_rates": win_rates,
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    recent_hist.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    target_win = win_rates[DEFAULT_ALERT_HORIZON]["final_win_rate"]
    print("Success! Win Rate:", target_win, "% Threshold:", WIN_RATE_ALERT_THRESHOLD)

    if target_win >= WIN_RATE_ALERT_THRESHOLD:
        send_alert_email(payload)


if __name__ == "__main__":
    main()
