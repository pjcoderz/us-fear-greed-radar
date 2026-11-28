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
AAII_HISTORY_CSV_PATH = os.path.join(DATA_DIR, "aaii_history.csv")

# 本地歷史檔候選路徑（支援放在專案根目錄或 data/ 下）
VIX_LOCAL_CANDIDATES = [
    os.path.join(DATA_DIR, "VIX_History.csv"),
    "VIX_History.csv",
]
FG_LOCAL_CANDIDATES = [
    os.path.join(DATA_DIR, "fear-greed.csv"),
    "fear-greed.csv",
]
AAII_LOCAL_CANDIDATES = [
    AAII_HISTORY_CSV_PATH,
    "aaii_history.csv",
]

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


def _find_existing_file(candidates):
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _parse_fg_df(df):
    if df is None or df.empty:
        return pd.Series(dtype=float)
    cols_map = {str(c).strip().lower(): c for c in df.columns}
    date_col = cols_map.get("date", df.columns[0])
    val_col = cols_map.get("fear greed", cols_map.get("cnn_fg", df.columns[1] if len(df.columns) > 1 else None))
    if val_col is None:
        return pd.Series(dtype=float)

    out = pd.DataFrame({
        "Date": pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None).dt.normalize(),
        "CNN_FG": pd.to_numeric(df[val_col], errors="coerce"),
    }).dropna(subset=["Date", "CNN_FG"])

    out = out[(out["CNN_FG"] >= 0.0) & (out["CNN_FG"] <= 100.0)]
    if out.empty:
        return pd.Series(dtype=float)
    out = out.drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
    return out.set_index("Date")["CNN_FG"]


def fetch_cnn_data():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    resp = safe_request(url)

    score = None
    rating = "fear"
    prev_close = None
    s_recent = pd.Series(dtype=float)

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
                    tmp = tmp.dropna(subset=["Date", "CNN_FG"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
                    if not tmp.empty:
                        s_recent = tmp.set_index("Date")["CNN_FG"]
        except Exception as e:
            print("[Warn] CNN parse:", str(e))

    s_local = pd.Series(dtype=float)
    local_fg_path = _find_existing_file(FG_LOCAL_CANDIDATES)
    if local_fg_path:
        try:
            s_local = _parse_fg_df(pd.read_csv(local_fg_path))
            print("[Info] Loaded local CNN history rows:", len(s_local), "from", local_fg_path)
        except Exception as e:
            print("[Warn] Local CNN CSV:", str(e))

    s_arch = pd.Series(dtype=float)
    archive_url = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"
    resp_arch = safe_request(archive_url)
    if resp_arch:
        try:
            s_arch = _parse_fg_df(pd.read_csv(StringIO(resp_arch.text)))
        except Exception as e:
            print("[Warn] CNN archive parse:", str(e))

    # 合併順序：本地歷史檔 -> GitHub 存檔 -> 線上即時歷史（最新值覆蓋舊值）
    combined = pd.concat([s_local, s_arch, s_recent])
    combined = combined[~combined.index.isna()].sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]

    if not combined.empty:
        if score is None:
            score = round(float(combined.iloc[-1]), 2)
        if prev_close is None and len(combined) >= 2:
            prev_close = round(float(combined.iloc[-2]), 2)
        df_cnn = combined.to_frame(name="CNN_FG")
    else:
        df_cnn = pd.DataFrame(columns=["CNN_FG"])

    if score is None:
        score = 20.0
    if prev_close is None:
        prev_close = score

    return {"score": score, "rating": rating, "prev_close": prev_close}, df_cnn


def _load_local_vix_series():
    vix_path = _find_existing_file(VIX_LOCAL_CANDIDATES)
    if not vix_path:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(vix_path)
        cols_map = {str(c).strip().lower(): c for c in df.columns}
        date_col = cols_map.get("date", df.columns[0])
        close_col = cols_map.get("close", cols_map.get("vix", df.columns[4] if len(df.columns) > 4 else None))
        if close_col is None:
            return pd.Series(dtype=float)
        out = pd.DataFrame({
            "Date": pd.to_datetime(df[date_col], errors="coerce").dt.tz_localize(None).dt.normalize(),
            "VIX": pd.to_numeric(df[close_col], errors="coerce"),
        }).dropna(subset=["Date", "VIX"])
        out = out.drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        print("[Info] Loaded local VIX rows:", len(out), "from", vix_path)
        return out.set_index("Date")["VIX"]
    except Exception as e:
        print("[Warn] Local VIX CSV:", str(e))
        return pd.Series(dtype=float)


def _fetch_stooq_series(symbol, start_date="1990-01-01"):
    url = "https://stooq.com/q/d/l/?s=" + symbol + "&i=d"
    resp = safe_request(url)
    if not resp:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(StringIO(resp.text))
        if "Date" not in df.columns or "Close" not in df.columns:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.tz_localize(None).dt.normalize()
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = (
            df.dropna(subset=["Date", "Close"])
            .drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
        )
        df = df[df["Date"] >= start_date]
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
    start_date = "1990-01-01"
    vix_local = _load_local_vix_series()
    vix_live = pd.Series(dtype=float)
    sp_s = pd.Series(dtype=float)
    ndx_s = pd.Series(dtype=float)

    try:
        raw = yf.download(
            ["^VIX", "^GSPC", "^NDX"],
            start=start_date,
            progress=False,
            auto_adjust=True,
        )
        vix_live = _extract_ticker_close(raw, "^VIX")
        sp_s = _extract_ticker_close(raw, "^GSPC")
        ndx_s = _extract_ticker_close(raw, "^NDX")
    except Exception as e:
        print("[Warn] yfinance:", str(e))

    if vix_live.empty:
        vix_live = _fetch_stooq_series("^vix", start_date=start_date)
    if sp_s.empty:
        sp_s = _fetch_stooq_series("^spx", start_date=start_date)
    if ndx_s.empty:
        ndx_s = _fetch_stooq_series("^ndx", start_date=start_date)

    # 合併本地 VIX_History.csv 與最新線上 VIX
    vix_merged = pd.concat([vix_local, vix_live])
    vix_merged = vix_merged[~vix_merged.index.isna()].sort_index()
    vix_merged = vix_merged[~vix_merged.index.duplicated(keep="last")]

    # 若既有 history_backtest.csv 有歷史 SP500/NDX，作為早期基準備援
    old_sp = pd.Series(dtype=float)
    old_ndx = pd.Series(dtype=float)
    if os.path.exists(CSV_PATH):
        try:
            old_csv = pd.read_csv(CSV_PATH)
            old_csv["dt"] = pd.to_datetime(old_csv["Date"], errors="coerce").dt.tz_localize(None).dt.normalize()
            old_csv = old_csv.dropna(subset=["dt"]).drop_duplicates(subset=["dt"], keep="last").set_index("dt").sort_index()
            if "SP500" in old_csv.columns:
                old_sp = pd.to_numeric(old_csv["SP500"], errors="coerce").dropna()
            if "NDX" in old_csv.columns:
                old_ndx = pd.to_numeric(old_csv["NDX"], errors="coerce").dropna()
        except Exception as e:
            print("[Warn] CSV fallback:", str(e))

    sp_all = pd.concat([old_sp, sp_s])
    sp_all = sp_all[~sp_all.index.isna()].sort_index()
    sp_all = sp_all[~sp_all.index.duplicated(keep="last")]

    ndx_all = pd.concat([old_ndx, ndx_s])
    ndx_all = ndx_all[~ndx_all.index.isna()].sort_index()
    ndx_all = ndx_all[~ndx_all.index.duplicated(keep="last")]

    if vix_merged.empty:
        raise RuntimeError("VIX data empty from all sources.")

    df_mkt = pd.DataFrame({"VIX": vix_merged}, index=vix_merged.index)
    if not sp_all.empty:
        df_mkt["SP500"] = sp_all.reindex(df_mkt.index)
    else:
        df_mkt["SP500"] = np.nan

    if not ndx_all.empty:
        df_mkt["NDX"] = ndx_all.reindex(df_mkt.index)
    else:
        df_mkt["NDX"] = df_mkt["SP500"]

    df_mkt = df_mkt.sort_index()
    vix_now = round(float(df_mkt["VIX"].iloc[-1]), 2)
    vix_prev = round(float(df_mkt["VIX"].iloc[-2]), 2) if len(df_mkt) >= 2 else vix_now
    sp_valid = df_mkt["SP500"].dropna()
    sp500_now = round(float(sp_valid.iloc[-1]), 2) if not sp_valid.empty else 0.0

    return {"vix": vix_now, "vix_prev": vix_prev, "sp500": sp500_now}, df_mkt


def _parse_aaii_date(raw_str):
    if not raw_str:
        return pd.NaT
    s = str(raw_str).strip()
    dt = pd.to_datetime(s, errors="coerce")
    if pd.isna(dt):
        cur_year = datetime.now(timezone.utc).year
        dt = pd.to_datetime(s + " " + str(cur_year), errors="coerce")
    if pd.notna(dt):
        return dt.tz_localize(None).normalize()
    return pd.NaT


def _normalize_aaii_df(df_raw):
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["Date", "Bullish", "Neutral", "Bearish"])

    cols_map = {str(c).strip().lower(): c for c in df_raw.columns}
    date_col = cols_map.get("date", df_raw.columns[0])
    bear_col = cols_map.get("bearish", df_raw.columns[3] if len(df_raw.columns) > 3 else None)
    bull_col = cols_map.get("bullish")
    neut_col = cols_map.get("neutral")

    if bear_col is None:
        return pd.DataFrame(columns=["Date", "Bullish", "Neutral", "Bearish"])

    out = pd.DataFrame()
    out["Date"] = df_raw[date_col].apply(_parse_aaii_date)
    out["Bearish"] = df_raw[bear_col].apply(lambda x: _parse_float(x, 0, 100))

    if not out["Bearish"].dropna().empty and out["Bearish"].dropna().max() <= 1.0:
        out["Bearish"] = (out["Bearish"] * 100.0).round(2)

    if bull_col is not None:
        out["Bullish"] = df_raw[bull_col].apply(lambda x: _parse_float(x, 0, 100))
        if not out["Bullish"].dropna().empty and out["Bullish"].dropna().max() <= 1.0:
            out["Bullish"] = (out["Bullish"] * 100.0).round(2)
    else:
        out["Bullish"] = np.nan

    if neut_col is not None:
        out["Neutral"] = df_raw[neut_col].apply(lambda x: _parse_float(x, 0, 100))
        if not out["Neutral"].dropna().empty and out["Neutral"].dropna().max() <= 1.0:
            out["Neutral"] = (out["Neutral"] * 100.0).round(2)
    else:
        out["Neutral"] = np.nan

    out = (
        out.dropna(subset=["Date", "Bearish"])
        .drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    return out


def fetch_aaii_data():
    url = "https://www.aaii.com/sentimentsurvey/sent_results"
    resp = safe_request(url)
    hist_records = []

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
                        dt_val = _parse_aaii_date(vals[0] if vals else "")
                        hist_records.append({
                            "Date": dt_val,
                            "date_str": vals[0] if vals else "Latest",
                            "bullish": bullish,
                            "neutral": neutral,
                            "bearish": bearish,
                            "spread": round(bullish - bearish, 2),
                        })
        except Exception as e:
            print("[Warn] AAII HTML:", str(e))

    frames = []
    local_aaii_path = _find_existing_file(AAII_LOCAL_CANDIDATES)
    if local_aaii_path:
        try:
            local_df = pd.read_csv(local_aaii_path)
            norm_local = _normalize_aaii_df(local_df)
            if not norm_local.empty:
                frames.append(norm_local)
                print("[Info] Loaded local AAII history rows:", len(norm_local), "from", local_aaii_path)
        except Exception as e:
            print("[Warn] Local AAII history CSV:", str(e))

    backup_urls = [
        "https://raw.githubusercontent.com/datasets/aaii-sentiment/main/data/aaii-sentiment.csv",
        "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/aaii-sentiment.csv",
    ]
    latest_from_backup = None

    for b_url in backup_urls:
        b_resp = safe_request(b_url)
        if b_resp:
            try:
                bdf = pd.read_csv(StringIO(b_resp.text)).dropna(how="all")
                norm_b = _normalize_aaii_df(bdf)
                if not norm_b.empty:
                    frames.append(norm_b)
                    last = norm_b.iloc[-1]
                    bull_val = float(last["Bullish"]) if pd.notna(last["Bullish"]) else 37.5
                    neut_val = float(last["Neutral"]) if pd.notna(last["Neutral"]) else round(max(0.0, 100.0 - bull_val - float(last["Bearish"])), 2)
                    bear_val = float(last["Bearish"])
                    latest_from_backup = {
                        "date": str(last["Date"].strftime("%Y-%m-%d")),
                        "bullish": round(bull_val, 2),
                        "neutral": round(neut_val, 2),
                        "bearish": round(bear_val, 2),
                        "spread": round(bull_val - bear_val, 2),
                    }
            except Exception as e:
                print("[Warn] AAII backup:", str(e))

    latest_obj = None
    if hist_records:
        first_rec = hist_records[0]
        dt_iso = first_rec["Date"].strftime("%Y-%m-%d") if pd.notna(first_rec["Date"]) else first_rec["date_str"]
        latest_obj = {
            "date": dt_iso,
            "bullish": first_rec["bullish"],
            "neutral": first_rec["neutral"],
            "bearish": first_rec["bearish"],
            "spread": first_rec["spread"],
        }
        df_web = pd.DataFrame(hist_records).dropna(subset=["Date"])
        if not df_web.empty:
            web_norm = pd.DataFrame({
                "Date": df_web["Date"],
                "Bullish": df_web["bullish"],
                "Neutral": df_web["neutral"],
                "Bearish": df_web["bearish"],
            })
            frames.append(_normalize_aaii_df(web_norm))

    if latest_obj is None:
        latest_obj = latest_from_backup

    if latest_obj is not None:
        parsed_latest_dt = _parse_aaii_date(latest_obj.get("date"))
        if pd.notna(parsed_latest_dt):
            frames.append(
                pd.DataFrame([{
                    "Date": parsed_latest_dt,
                    "Bullish": latest_obj.get("bullish"),
                    "Neutral": latest_obj.get("neutral"),
                    "Bearish": latest_obj.get("bearish"),
                }])
            )

    if frames:
        merged_all = (
            pd.concat(frames, ignore_index=True)
            .dropna(subset=["Date", "Bearish"])
            .sort_values("Date")
        )
        merged_all = merged_all.groupby("Date", as_index=False).agg({
            "Bullish": "last",
            "Neutral": "last",
            "Bearish": "last",
        })
        save_df = merged_all.copy()
        save_df["Date"] = save_df["Date"].dt.strftime("%Y-%m-%d")
        save_df.to_csv(AAII_HISTORY_CSV_PATH, index=False, encoding="utf-8-sig")

        aaii_series = merged_all.set_index("Date")[["Bearish"]].rename(columns={"Bearish": "AAII_Bearish"})
        return latest_obj, aaii_series

    return latest_obj, pd.DataFrame(columns=["AAII_Bearish"])


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


def compute_multi_horizon_winrates(cnn_now, vix_now, aaii_now, df_cnn, df_mkt, df_aaii_hist):
    df = df_mkt.copy().sort_index()

    # CNN：只對齊真實存在的日期，不回填尚未有資料的早期區間
    if df_cnn is not None and not df_cnn.empty:
        df = df.join(df_cnn[["CNN_FG"]], how="left")
    else:
        df["CNN_FG"] = np.nan

    # AAII：僅做前向填補（最多 10 天），不做 bfill 與早期回填
    if df_aaii_hist is not None and not df_aaii_hist.empty:
        combined_idx = df.index.union(df_aaii_hist.index).sort_values()
        s_aaii = df_aaii_hist["AAII_Bearish"].reindex(combined_idx).ffill(limit=10)
        df["AAII_Bearish"] = s_aaii.reindex(df.index)
    else:
        df["AAII_Bearish"] = np.nan

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
        valid_sp = temp.dropna(subset=["SP_Fwd"])

        if valid_sp.empty:
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

        valid_cnn = valid_sp.dropna(subset=["CNN_FG"])
        valid_vix = valid_sp.dropna(subset=["VIX"])

        cond_cnn = valid_cnn[valid_cnn["CNN_FG"] <= max(cnn_now, 5)]
        cond_vix = valid_vix[valid_vix["VIX"] >= min(vix_now, 45)]
        cond_combo = valid_cnn[
            (valid_cnn["CNN_FG"] <= max(cnn_now, 10)) & (valid_cnn["VIX"] >= min(vix_now, 35))
        ]

        win_cnn = round(float((cond_cnn["SP_Fwd"] > 0).mean() * 100), 2) if len(cond_cnn) else 50.0
        win_vix = round(float((cond_vix["SP_Fwd"] > 0).mean() * 100), 2) if len(cond_vix) else 50.0

        if len(cond_combo) >= 10:
            base_win = float((cond_combo["SP_Fwd"] > 0).mean() * 100)
            sp_avg_ret = float(cond_combo["SP_Fwd"].mean() * 100)
            ndx_avg_ret = float(cond_combo["NDX_Fwd"].dropna().mean() * 100) if not cond_combo["NDX_Fwd"].dropna().empty else 0.0
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
                    cond_cnn["NDX_Fwd"].dropna().mean() if (len(cond_cnn) and not cond_cnn["NDX_Fwd"].dropna().empty) else np.nan,
                    cond_vix["NDX_Fwd"].dropna().mean() if (len(cond_vix) and not cond_vix["NDX_Fwd"].dropna().empty) else np.nan,
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

    # 輸出完整歷史序列（保留 NaN 讓圖表在無資料區間自然留白）
    full_hist = df.reset_index()
    date_col = full_hist.columns[0]
    full_hist["Date"] = pd.to_datetime(full_hist[date_col]).dt.strftime("%Y-%m-%d")
    return results, full_hist[["Date", "CNN_FG", "VIX", "AAII_Bearish", "SP500", "NDX"]]


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
    aaii_info, df_aaii_hist = fetch_aaii_data()

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
    win_rates, full_hist = compute_multi_horizon_winrates(
        cnn_info["score"], vix_info["vix"], aaii_info, df_cnn, df_mkt, df_aaii_hist
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
    full_hist.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    target_win = win_rates[DEFAULT_ALERT_HORIZON]["final_win_rate"]
    print("Success! Win Rate:", target_win, "% Threshold:", WIN_RATE_ALERT_THRESHOLD)

    if target_win >= WIN_RATE_ALERT_THRESHOLD:
        send_alert_email(payload)


if __name__ == "__main__":
    main()
