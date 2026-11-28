import asyncio
import datetime
import glob
import json
import math
import os
import smtplib
import struct
import subprocess
import tempfile
import wave
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
AUDIO_PATH = os.path.join(DATA_DIR, "daily_brief.mp3")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/",
}


def find_csv_case_insensitive(keywords, exclude_names=None):
    exclude_names = {n.lower() for n in (exclude_names or [])}
    candidates = []
    for folder in [".", DATA_DIR]:
        if os.path.isdir(folder):
            for path in glob.glob(os.path.join(folder, "*.csv")):
                fname = os.path.basename(path).lower()
                if fname in exclude_names:
                    continue
                if any(kw in fname for kw in keywords):
                    candidates.append(path)
    candidates.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return candidates[0] if candidates else None


def load_local_vix():
    path = find_csv_case_insensitive(["vix"], exclude_names=["history_backtest.csv"])
    if not path:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
        close_col = next((c for c in df.columns if "close" in c.lower() or "vix" in c.lower()), df.columns[-1])
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df["VIX"] = pd.to_numeric(df[close_col], errors="coerce")
        df = df.dropna(subset=["Date", "VIX"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        return df.set_index("Date")["VIX"]
    except Exception as e:
        print(f"[WARN] load_local_vix failed ({path}): {e}")
        return pd.Series(dtype=float)


def load_local_cnn():
    path = find_csv_case_insensitive(["fear", "greed", "cnn"], exclude_names=["history_backtest.csv"])
    if not path:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
        val_col = next(
            (c for c in df.columns if any(k in c.lower() for k in ["fear", "greed", "score", "value", "cnn", "close"])),
            df.columns[-1],
        )
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df["CNN_FG"] = pd.to_numeric(df[val_col], errors="coerce")
        df = df.dropna(subset=["Date", "CNN_FG"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        return df.set_index("Date")["CNN_FG"]
    except Exception as e:
        print(f"[WARN] load_local_cnn failed ({path}): {e}")
        return pd.Series(dtype=float)


def load_local_aaii():
    path = find_csv_case_insensitive(["aaii", "sentiment"], exclude_names=["history_backtest.csv"])
    if not path:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
        bear_col = next((c for c in df.columns if "bear" in c.lower()), None)
        if not bear_col:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        df[bear_col] = (
            df[bear_col]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        df["AAII_Bearish"] = pd.to_numeric(df[bear_col], errors="coerce")
        df = df.dropna(subset=["Date", "AAII_Bearish"]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
        if not df.empty and df["AAII_Bearish"].max() <= 1.0:
            df["AAII_Bearish"] = df["AAII_Bearish"] * 100.0
        return df.set_index("Date")["AAII_Bearish"]
    except Exception as e:
        print(f"[WARN] load_local_aaii failed ({path}): {e}")
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
            df_live = (
                pd.DataFrame(rows, columns=["Date", "CNN_FG"])
                .drop_duplicates(subset=["Date"], keep="last")
                .sort_values("Date")
            )
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

        cnn_thresh = min(max(cnn_now + 3.0, 25.0), 45.0) if cnn_now <= 45 else 45.0
        mask_cnn = df["CNN_FG"].notna() & (df["CNN_FG"] <= cnn_thresh) & fwd_sp.notna()
        if mask_cnn.sum() >= 15:
            win_cnn = float((fwd_sp[mask_cnn] > 0).mean() * 100.0)
        else:
            valid_cnn = df["CNN_FG"].notna() & fwd_sp.notna()
            win_cnn = float((fwd_sp[valid_cnn] > 0).mean() * 100.0) if valid_cnn.sum() > 0 else 70.0

        vix_thresh = max(min(vix_now - 2.0, 30.0), 20.0) if vix_now >= 20 else 20.0
        mask_vix = df["VIX"].notna() & (df["VIX"] >= vix_thresh) & fwd_sp.notna()
        if mask_vix.sum() >= 15:
            win_vix = float((fwd_sp[mask_vix] > 0).mean() * 100.0)
        else:
            valid_vix = df["VIX"].notna() & fwd_sp.notna()
            win_vix = float((fwd_sp[valid_vix] > 0).mean() * 100.0) if valid_vix.sum() > 0 else 72.0

        if aaii_bear_now >= 50.0:
            aaii_bonus = 6.0
        elif aaii_bear_now >= 40.0:
            aaii_bonus = 3.0
        else:
            aaii_bonus = 1.5

        final_win = min(round(0.5 * win_cnn + 0.5 * win_vix + aaii_bonus, 2), 99.5)

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


def build_dengdengdeng_chime_wav(wav_path):
    """合成開頭清脆『登、登、登』三連音提示音效（C5 -> E5 -> G5）"""
    sample_rate = 24000
    notes = [(523.25, 0.22), (659.25, 0.22), (783.99, 0.36)]
    gap_sec = 0.06
    frames = bytearray()

    for freq, dur in notes:
        total_samples = int(sample_rate * dur)
        for i in range(total_samples):
            t = i / sample_rate
            env = min(1.0, i / (sample_rate * 0.015)) * math.exp(-3.2 * t)
            val = 0.45 * env * (
                math.sin(2 * math.pi * freq * t)
                + 0.25 * math.sin(2 * math.pi * freq * 2 * t)
            )
            sample_int = max(-32767, min(32767, int(val * 32767)))
            frames.extend(struct.pack("<h", sample_int))
        for _ in range(int(sample_rate * gap_sec)):
            frames.extend(struct.pack("<h", 0))

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


def build_brief_scripts(payload):
    """回傳 (主講稿, 專業快速財經警語)"""
    g_cnt = payload["lights"]["green_count"]
    cnn_val = payload["cnn"]["score"]
    vix_val = payload["vix"]["vix"]
    aaii_val = payload["aaii"]["bearish"]
    win_126 = payload["win_rates"]["126D"]["final_win_rate"]
    sp_avg = payload["win_rates"]["126D"]["sp_avg_ret"]
    sp_dd = payload["sp500"]["drawdown_pct"]

    if g_cnt >= 3:
        action_line = "三盞逆向綠燈已經全面亮起，歷史上屬於中長線均值回歸的高勝率區間，適合依紀律分批布局。"
    elif g_cnt == 2:
        action_line = "目前已經亮起兩盞綠燈，恐慌正在累積但尚未全面投降，建議分批試單，不急著一次重壓。"
    elif g_cnt == 1:
        action_line = "目前只有單燈初亮，局部情緒開始緊繃，先列入觀察清單、保留現金彈性即可。"
    else:
        action_line = "目前三盞燈都還沒亮起，市場情緒相對冷靜，維持原本節奏，不追高也不急著猜底。"

    main_script = (
        f"這裡是等燈燈美股逆向雷達，今天，你的燈亮了嗎？"
        f"新聞在賣驚嚇，數據在算機率，別猜底，等燈燈。"
        f"最新掃描結果，三大情緒指標共亮起 {g_cnt} 盞綠燈。"
        f"CNN 恐慌與貪婪指數 {cnn_val}，VIX 波動率 {vix_val}，AAII 散戶看空比例 {aaii_val}%；"
        f"標普五百指數目前距離歷史前高回檔 {abs(sp_dd):.1f}%。"
        f"以六個月持有週期來看，歷史相似條件上漲勝率 {win_126}%，平均報酬 {sp_avg:+.1f}%。"
        f"{action_line}"
        f"我們不帶風向，我們分享趨勢；認同就分享，讓更多人站在你這邊。"
        f"記下網址，每天搶先收到最新資訊。今天燈號就到這裡，登登燈，我們下次亮燈見。"
    )

    disclaimer_script = (
        "本節目內容僅供行為財務學與歷史數據研究參考，不構成任何投資買賣建議，投資人應獨立判斷並自負風險。"
    )
    return main_script, disclaimer_script


def generate_daily_brief_audio(payload):
    """合成『登、登、登』三連音 ＋ 主講稿（正常語速）＋ 警語（快速財經節奏）MP3"""
    try:
        import edge_tts

        main_script, disclaimer_script = build_brief_scripts(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            chime_wav = os.path.join(tmpdir, "chime.wav")
            main_mp3 = os.path.join(tmpdir, "main.mp3")
            disc_mp3 = os.path.join(tmpdir, "disclaimer.mp3")
            build_dengdengdeng_chime_wav(chime_wav)

            async def _run_tts():
                comm_main = edge_tts.Communicate(main_script, voice="zh-TW-HsiaoChenNeural", rate="+4%")
                await comm_main.save(main_mp3)
                comm_disc = edge_tts.Communicate(disclaimer_script, voice="zh-TW-HsiaoChenNeural", rate="+28%")
                await comm_disc.save(disc_mp3)

            asyncio.run(_run_tts())

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                chime_wav,
                "-i",
                main_mp3,
                "-i",
                disc_mp3,
                "-filter_complex",
                "[0:a]aresample=24000,aformat=channel_layouts=mono[a0];[1:a]aresample=24000,aformat=channel_layouts=mono[a1];[2:a]aresample=24000,aformat=channel_layouts=mono[a2];[a0][a1][a2]concat=n=3:v=0:a=1[out]",
                "-map",
                "[out]",
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                "4",
                AUDIO_PATH,
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0 or not os.path.exists(AUDIO_PATH):
                with open(main_mp3, "rb") as src_f, open(AUDIO_PATH, "wb") as dst_f:
                    dst_f.write(src_f.read())
        print(f"[INFO] Generated daily brief audio at {AUDIO_PATH}")
    except Exception as e:
        print(f"[WARN] generate_daily_brief_audio skipped: {e}")


def send_alert_email(payload):
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.environ.get("ALERT_RECIPIENT", gmail_user).strip()

    if not gmail_user or not gmail_pass or not recipient:
        return

    win_126 = payload["win_rates"]["126D"]["final_win_rate"]
    threshold = payload.get("alert_threshold", 90.0)
    if win_126 < threshold:
        return

    subject = f"🚨 等燈燈美股逆向雷達警報：6個月實證勝率達 {win_126}%（{payload['lights']['green_count']}/3 綠燈）"
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

    generate_daily_brief_audio(payload)
    send_alert_email(payload)
    print("[SUCCESS] Sentiment data, backtest CSV & daily brief audio updated.")


if __name__ == "__main__":
    main()

