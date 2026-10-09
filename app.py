import streamlit as st
import requests, time, hmac, hashlib
from urllib.parse import urlencode
from decimal import Decimal, InvalidOperation
import pandas as pd

st.set_page_config(page_title="CEX T1 • Kripto Bot", page_icon="🤖", layout="wide")

TR_BASE = "https://www.binance.tr"
PUBLIC_BASES = ["https://api.binance.me", "https://www.binance.tr"]
TIMEOUT = 12

st.markdown(""" <style> .stApp {background: radial-gradient(circle at 15% 0%, #172b50 0, #080d1b 48%, #03060d 100%); color:#eaf6ff} [data-testid="stSidebar"] {background:linear-gradient(180deg,#17233e,#0a1020)} h1,h2,h3 {color:#eaf6ff} div[data-testid="stMetric"] {background:rgba(20,37,67,.65);padding:14px;border:1px solid #284666;border-radius:14px} div.stButton>button {border-radius:10px;font-weight:700} </style> """, unsafe_allow_html=True)

def request_json(url, params=None, method="GET", headers=None, timeout=TIMEOUT):
    r = requests.request(method, url, params=params if method == "GET" else None,
                         data=params if method != "GET" else None,
                         headers=headers, timeout=timeout)
    if r.status_code == 451:
        raise RuntimeError(f"HTTP 451: {url} bu sunucudan erişimi reddediyor. Bu kodun içinden düzeltilemeyebilir; farklı ağ/host veya borsa erişim izni gerekir.")
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"API JSON döndürmedi (HTTP {r.status_code}).")
    if isinstance(data, dict) and data.get("code") not in (None, 0, "0"):
        raise RuntimeError(f"API yanıtı: {data.get('msg') or data.get('message') or data.get('code')}")
    return data

def signed_request(path, api_key, secret, params=None, method="GET"):
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 5000
    query = urlencode(p)
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": api_key}
    url = TR_BASE + path
    if method == "GET" or method == "DELETE":
        return request_json(url + "?" + query + "&signature=" + signature,
                            method=method, headers=headers)
    body = p.copy()
    body["signature"] = signature
    return request_json(url, params=body, method=method, headers=headers)

def unwrap_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for key in ("list", "balances", "symbols", "rows"):
                if isinstance(data.get(key), list):
                    return data[key]
        if isinstance(data, list):
            return data
    return []

def get_symbols():
    errors = []
    # Official Binance TR symbols endpoint
    try:
        data = request_json(TR_BASE + "/open/v1/common/symbols")
        rows = unwrap_list(data)
        rows = [x for x in rows if isinstance(x, dict) and x.get("symbol")]
        if rows:
            return rows, "Binance TR sembol listesi"
    except Exception as e:
        errors.append(str(e))
    # Public market metadata fallback
    for base in PUBLIC_BASES:
        try:
            data = request_json(base + "/api/v3/exchangeInfo")
            rows = data.get("symbols", []) if isinstance(data, dict) else []
            if rows:
                converted = []
                for x in rows:
                    sym = x.get("symbol", "")
                    quote = x.get("quoteAsset", "")
                    if quote == "TRY":
                        converted.append({"symbol": sym, "baseAsset": x.get("baseAsset", ""),
                                          "quoteAsset": quote, "status": x.get("status", ""),
                                          "type": 1, "_raw_symbol": sym})
                if converted:
                    return converted, f"{base} exchangeInfo"
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError("Sembol listesi alınamadı. " + " | ".join(errors[-2:]))

def market_tickers():
    errors = []
    for base in PUBLIC_BASES:
        try:
            data = request_json(base + "/api/v3/ticker/24hr")
            if isinstance(data, list):
                return data, base
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError("Piyasa verileri alınamadı. " + " | ".join(errors[-2:]))

def symbol_api_name(symbol):
    return str(symbol).replace("_", "")

def get_account(api_key, secret):
    return signed_request("/open/v1/account/spot", api_key, secret)

def normalize_balances(payload):
    rows = unwrap_list(payload)
    if rows and any(("asset" in x or "a" in x) for x in rows if isinstance(x, dict)):
        return rows
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if isinstance(data, dict):
        if "balances" in data and isinstance(data["balances"], list):
            return data["balances"]
        if "asset" in data:
            return [data]
    return []

def submit_order(api_key, secret, symbol, side, order_type, quantity, quote_qty, price):
    # Binance TR docs: side 0=BUY, 1=SELL; type 1=LIMIT, 2=MARKET.
    params = {"symbol": symbol, "side": 0 if side == "AL" else 1,
              "type": 2 if order_type == "MARKET" else 1}
    if order_type == "MARKET" and side == "AL" and quote_qty:
        params["quoteOrderQty"] = str(quote_qty)
    else:
        params["quantity"] = str(quantity)
    if order_type == "LIMIT":
        params["price"] = str(price)
        params["timeInForce"] = 1
    return signed_request("/open/v1/orders", api_key, secret, params, "POST")

def fmt_num(v, digits=2):
    try:
        return f"{float(v):,.{digits}f}"
    except Exception:
        return "—"

st.title("🤖 CEX T1 — Otomatik Kripto & Balina Radarı")
st.caption("Binance TR • Spot / TRY • Piyasa taraması, hesap bağlantısı ve kontrollü emir paneli")

with st.sidebar:
    st.header("BORSA VE BAĞLANTI")
    st.selectbox("Borsa Seçin", ["Binance TR (Spot - TRY)"], key="exchange")
    api_key = st.text_input("Erişim Anahtarı (API Key)", type="password", key="api_key")
    secret = st.text_input("Gizli Anahtar (Secret Key)", type="password", key="secret")
    connect = st.button("🔌 Bağlantıyı Kur / Yenile", use_container_width=True)
    if connect:
        if not api_key or not secret:
            st.error("API Key ve Secret Key gir.")
        else:
            try:
                acc = get_account(api_key, secret)
                st.session_state["account_payload"] = acc
                st.session_state["connected"] = True
                st.success("Binance TR özel API yanıt verdi.")
            except Exception as e:
                st.session_state["connected"] = False
                st.error(f"Bağlantı doğrulanamadı: {e}")
    if st.session_state.get("connected"):
        st.success("✅ Özel API bağlantısı doğrulandı")
    else:
        st.info("API bilgilerini girip bağlantıyı doğrula.")
    st.caption("Güvenlik: API anahtarlarını sohbetle paylaşma. Mümkünse yalnızca okuma ve spot işlem izinleri ver; çekim iznini kapalı tut.")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Genel Bakış", "⚙️ Strateji ve Risk", "🐋 Balina & Hacim Radarı", "🛒 Emir / Otomasyon"])

with st.spinner("Piyasa verileri kontrol ediliyor..."):
    try:
        symbols, symbols_source = get_symbols()
        tickers, ticker_source = market_tickers()
        tickmap = {str(t.get("symbol", "")): t for t in tickers if isinstance(t, dict)}
        market_rows = []
        for s in symbols:
            symbol = str(s.get("symbol", ""))
            quote = s.get("quoteAsset", "")
            status = s.get("status", "")
            if quote and quote != "TRY":
                continue
            if status and status not in ("TRADING", "1", 1):
                continue
            api_symbol = symbol_api_name(symbol)
            t = tickmap.get(api_symbol) or tickmap.get(symbol)
            if not t:
                continue
            try:
                price = float(t.get("lastPrice", t.get("last", 0)) or 0)
                change = float(t.get("priceChangePercent", t.get("priceChangePercent24h", 0)) or 0)
                volume = float(t.get("quoteVolume", t.get("quoteVolume24h", 0)) or 0)
                market_rows.append({"Parite": symbol.replace("_", "/"), "API sembolü": api_symbol,
                                    "Fiyat": price, "24s değişim %": change, "24s hacim": volume})
            except (ValueError, TypeError):
                continue
        market_df = pd.DataFrame(market_rows)
        if not market_df.empty:
            market_df = market_df.sort_values("24s hacim", ascending=False).reset_index(drop=True)
        st.session_state["market_df"] = market_df
        st.session_state["symbols_source"] = symbols_source
        st.session_state["ticker_source"] = ticker_source
        market_error = None
    except Exception as e:
        market_error = str(e)
        market_df = st.session_state.get("market_df", pd.DataFrame())

account_payload = st.session_state.get("account_payload")
balances = normalize_balances(account_payload) if account_payload else []
balance_rows = []
for b in balances:
    if not isinstance(b, dict):
        continue
    asset = b.get("asset", b.get("a", ""))
    free = b.get("free", b.get("f", 0))
    locked = b.get("locked", b.get("l", 0))
    try:
        if float(free or 0) or float(locked or 0):
            balance_rows.append({"Varlık": asset, "Kullanılabilir": float(free or 0), "Kilitte": float(locked or 0)})
    except Exception:
        pass

with tab1:
    if market_error:
        st.error("Piyasa verisi sorunu: " + market_error)
        st.caption("HTTP 451 görülüyorsa bu, isteğin çalıştığı sunucu/ağ için erişim engelidir; başka endpoint denemek her zaman çözmez.")
    else:
        st.caption(f"Sembol kaynağı: {st.session_state.get('symbols_source','—')} • Fiyat kaynağı: {st.session_state.get('ticker_source','—')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gösterilen parite", str(len(market_df)))
    c2.metric("Piyasa", "TRY Spot")
    c3.metric("Hesap API", "Bağlı" if st.session_state.get("connected") else "Bağlı değil")
    c4.metric("Varlık satırı", str(len(balance_rows)))
    st.subheader("Canlı Piyasa Radarı")
    if not market_df.empty:
        st.dataframe(market_df[["Parite", "Fiyat", "24s değişim %", "24s hacim"]], use_container_width=True, hide_index=True)
    else:
        st.warning("Henüz piyasa tablosu alınamadı. Sunucu erişimi engelliyse kod tek başına bu engeli kaldıramaz.")
    st.subheader("Hesap Bakiyeleri")
    if not st.session_state.get("connected"):
        st.info("Bakiyeyi görmek için sol taraftan API bağlantısını doğrula.")
    elif balance_rows:
        st.dataframe(pd.DataFrame(balance_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("API yanıt verdi fakat bakiye alanları tanınamadı. Yanıt şeması kontrol edilmeli.")

with tab2:
    st.subheader("Strateji ve Risk Ayarları")
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Strateji", ["Hacim + momentum + emir defteri", "Hareketli ortalama kesişimi", "RSI tabanlı"], key="strategy")
        st.number_input("İşlem başına azami bütçe (TRY)", min_value=0.0, value=100.0, step=25.0, key="max_budget")
        st.number_input("Kâr alma (%)", min_value=0.1, value=2.0, step=0.1, key="take_profit")
    with col2:
        st.number_input("Zarar durdur (%)", min_value=0.1, value=1.0, step=0.1, key="stop_loss")
        st.number_input("Günlük azami işlem sayısı", min_value=1, value=3, step=1, key="max_trades")
        st.number_input("Büyük işlem eşiği (TRY)", min_value=1000.0, value=50000.0, step=5000.0, key="whale_threshold")
    st.warning("Bu ayarlar burada saklanan strateji parametreleridir. Otomatik döngü ve pozisyon takibi, güvenilir sürekli çalışan bir sunucu ve borsa emir/işlem sorgularıyla ayrıca işletilmelidir.")

with tab3:
    st.subheader("Balina & Hacim Radarı")
    threshold = float(st.session_state.get("whale_threshold", 50000.0))
    if not market_df.empty:
        radar = market_df.copy()
        radar["Sinyal"] = radar["24s değişim %"].apply(lambda x: "AL adayı" if x >= 2 else ("SAT baskısı" if x <= -2 else "BEKLE"))
        radar["Hacim etiketi"] = radar["24s hacim"].apply(lambda x: "Yüksek hacim" if x >= (radar["24s hacim"].median() if len(radar) else 0) else "Normal")
        st.dataframe(radar[["Parite", "Fiyat", "24s değişim %", "24s hacim", "Sinyal", "Hacim etiketi"]], use_container_width=True, hide_index=True)
        st.caption("Bu ekran 24 saatlik fiyat/hacim verisinden aday çıkarır; gerçek büyük işlemleri/cüzdanları tespit ettiğini iddia etmez.")
    else:
        st.info("Balina radarı için piyasa verisi gerekli.")

with tab4:
    st.subheader("Manuel Emir")
    if not api_key or not secret:
        st.info("Emir göndermek için API bilgilerini gir ve bağlantıyı doğrula.")
    col1, col2 = st.columns(2)
    with col1:
        if not market_df.empty:
            options = market_df["API sembolü"].tolist()
            selected_symbol = st.selectbox("Parite", options, key="order_symbol")
        else:
            selected_symbol = st.text_input("Parite (ör. BTC_TRY)", value="BTC_TRY")
        side = st.radio("İşlem", ["AL", "SAT"], horizontal=True)
        order_type = st.radio("Emir türü", ["MARKET", "LIMIT"], horizontal=True)
    with col2:
        quantity = st.text_input("Miktar (coin) — SAT veya LIMIT AL için", value="")
        quote_qty = st.text_input("MARKET AL için harcanacak TRY tutarı", value="")
        price = st.text_input("Limit fiyatı (LIMIT seçildiğinde)", value="")
    st.warning("Gerçek emir bakiyeni etkiler. Önce küçük tutarla test et. Market alışta TRY tutarı kullanılır; satışta coin miktarı gerekir.")
    confirm_live = st.checkbox("Gerçek emir göndereceğimi ve bakiyemin etkilenebileceğini anlıyorum.")
    if st.button("📨 Emri Gönder", type="primary", use_container_width=True):
        if not api_key or not secret:
            st.error("API Key ve Secret Key gerekli.")
        elif not confirm_live:
            st.error("Gerçek emir onay kutusunu işaretlemelisin.")
        else:
            try:
                # Validate fields before request
                if order_type == "MARKET" and side == "AL":
                    if not quote_qty or Decimal(quote_qty) <= 0:
                        raise ValueError("Pozitif TRY tutarı gir.")
                    qty = None
                else:
                    if not quantity or Decimal(quantity) <= 0:
                        raise ValueError("Pozitif coin miktarı gir.")
                    qty = quantity
                if order_type == "LIMIT" and (not price or Decimal(price) <= 0):
                    raise ValueError("Limit fiyatı pozitif olmalı.")
                # Last explicit confirmation required immediately before sending.
                with st.spinner("Borsa emri yanıtlıyor..."):
                    result = submit_order(api_key, secret, selected_symbol, side, order_type,
                                          qty, quote_qty if order_type == "MARKET" and side == "AL" else None,
                                          price if order_type == "LIMIT" else None)
                st.success("Borsadan emir yanıtı alındı:")
                st.json(result)
            except Exception as e:
                st.error(f"Emir gönderilemedi veya sonucu doğrulanamadı: {e}")
    st.divider()
    st.subheader("Otomatik işlem durumu")
    st.info("Bu tek dosyalı Streamlit sürümünde otomatik emir döngüsü varsayılan olarak ÇALIŞMAZ. Sayfa yenilenmesi/uyku nedeniyle canlı otomasyon güvenilir değildir. Strateji parametreleri ve manuel emir bağlantısı mevcuttur; gerçek otomatik bot için sürekli çalışan bir worker, emir durum takibi, stop/kâr alma yönetimi ve günlük limitler eklenmelidir.")
    st.checkbox("Otomatik işlem için niyet/onay (yalnızca arayüz; döngüyü başlatmaz)", key="auto_intent")
    st.caption("Bu onay otomasyonu başlatmaz; yanlışlıkla gerçek emir döngüsü çalıştırılmaması için bu sürümde otomatik emir gönderimi kapalıdır.")

st.divider()
st.caption("CEX T1 • Binance TR API • Gerçek piyasa ve hesap API'si erişilebilirliği barındırma sunucusuna bağlıdır. API anahtarlarında para çekme izni açmayın.")
