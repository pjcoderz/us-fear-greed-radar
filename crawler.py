def _parse_pct(val):
    """安全擷取百分比浮點數，無法解析時回傳 None"""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-", "--", "n/a"):
        return None
    cleaned = re.sub(r"[^0-9.]", "", s)
    if not cleaned:
        return None
    try:
        num = float(cleaned)
        return round(num, 2) if 0.0 <= num <= 100.0 else None
    except ValueError:
        return None


def fetch_aaii_data():
    """爬取 AAII 最新每週散戶情緒調查，並具備多表格容錯與備援來源"""
    url = "https://www.aaii.com/sentimentsurvey/sent_results"
    resp = safe_request(url)

    if resp:
        try:
            tables = pd.read_html(StringIO(resp.text))
            for tbl in tables:
                df = tbl.dropna(how="all")
                for _, row in df.iterrows():
                    vals = [str(x).strip() for x in row.tolist()]
                    pct_cols = [_parse_pct(v) for v in vals if "%" in v]
                    # AAII 單週列通常包含 Bullish / Neutral / Bearish 三個百分比
                    if len(pct_cols) >= 3:
                        date_str = vals[0] if vals else "Latest"
                        bullish, neutral, bearish = pct_cols[0], pct_cols[1], pct_cols[2]
                        spread = round(bullish - bearish, 2)
                        return {
                            "date": date_str,
                            "bullish": bullish,
                            "neutral": neutral,
                            "bearish": bearish,
                            "spread": spread,
                        }
        except Exception as e:
            print(f"[Warning] AAII HTML table parse failed: {e}")

    # 備援來源：若 AAII 官網無法解析或回傳空白，改抓公開歷史存檔最新一筆
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
                    bullish = _parse_pct(last.get("Bullish", last.iloc[1] if len(last) > 1 else None))
                    neutral = _parse_pct(last.get("Neutral", last.iloc[2] if len(last) > 2 else None))
                    bearish = _parse_pct(last.get("Bearish", last.iloc[3] if len(last) > 3 else None))
                    if bullish is not None and bearish is not None:
                        neutral = neutral if neutral is not None else round(max(0.0, 100.0 - bullish - bearish), 2)
                        return {
                            "date": str(last.iloc[0]),
                            "bullish": bullish,
                            "neutral": neutral,
                            "bearish": bearish,
                            "spread": round(bullish - bearish, 2),
                        }
            except Exception as e:
                print(f"[Warning] AAII backup CSV parse failed ({b_url}): {e}")

    return None
