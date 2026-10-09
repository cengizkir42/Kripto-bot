import streamlit as st
import pandas as pd
import requests
import hmac
import hashlib
import time
import ccxt
import logging

# --- LOGGING AYARI ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("cex_t1_bot")

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="CEX T1 - Kripto Bot",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🤖 CEX T1 - Otomatik Kripto & Balina Radarı Botu")

# --- VARSAYILAN STRATEJİ PARAMETRELERİ ---
DEFAULT_STRATEGY = {
    "TRY": {
        "max_margin": 1000.0,
        "risk_pct": 1.00,
        "stop_loss_pct": 1.50,
        "liquidation_buffer_pct": 1.50,
        "take_profit_pct": 2.50,
        "trailing_stop_pct": 1.00,
        "entry_score_threshold": 75,
        "max_open_positions": 2,
    },
    "USDT": {
        "max_margin": 40.0,
        "risk_pct": 0.50,
        "stop_loss_pct": 1.50,
        "liquidation_buffer_pct": 1.50,
        "take_profit_pct": 2.50,
        "trailing_stop_pct": 1.00,
        "entry_score_threshold": 75,
        "max_open_positions": 2,
    },
}

# --- SESSION STATE INITIALIZATION ---
_defaults = {
    "toplam_bakiye": 0.0,
    "kullanilabilir_bakiye": 0.0,
    "bakiye_listesi": [],
    "api_key": "",
    "secret_key": "",
    "exchange": None,
    "baglanti_aktif": False,
    "borsa_secimi": "Binance TR (Spot - TRY)",
    "strategy": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- SIDEBAR CONFIG ---
st.sidebar.header("BORSA VE BAĞLANTI")

borsa_secimi = st.sidebar.selectbox(
    "Borsa Seçin",
    ["Binance TR (Spot - TRY)", "Binance USDT-M (Vadeli)", "OKX Futures"],
    index=0
)
st.session_state["borsa_secimi"] = borsa_secimi

api_key = st.sidebar.text_input(
    "Erişim Anahtarı (API Key)",
    value=st.session_state["api_key"],
    type="password"
)
secret_key = st.sidebar.text_input(
    "Gizli Anahtar (Secret Key)",
    value=st.session_state["secret_key"],
    type="password"
)

if api_key:
    st.session_state["api_key"] = api_key
if secret_key:
    st.session_state["secret_key"] = secret_key

para_birimi = "TRY" if "Binance TR" in borsa_secimi else "USDT"

# --- HELPER: HASSAS VERİ MASKELEME ---
def _mask_sensitive(text: str) -> str:
    txt = str(text)
    if st.session_state.get("api_key"):
        txt = txt.replace(st.session_state["api_key"], "***API_KEY***")
    if st.session_state.get("secret_key"):
        txt = txt.replace(st.session_state["secret_key"], "***SECRET***")
    return txt

# --- HELPER: BINANCE TR CANLI PİYASA PARİTELERİ ---
@st.cache_data(ttl=300)
def fetch_binance_tr_symbols():
    """Binance TR'deki TRY paritelerini döner."""
    try:
        url = "https://www.trbinance.com/open/v1/common/symbols"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and data.get("code") == 0 and "data" in data:
                symbols = [
                    s.get("symbol") for s in data["data"]
                    if isinstance(s, dict) and s.get("symbol", "").endswith("TRY")
                ]
                if symbols:
                    return symbols, None
    except Exception as e:
        logger.warning(f"Binance TR sembol listesi alınamadı: {_mask_sensitive(e)}")
        return [], _mask_sensitive(str(e))
    fallback = ["BTCTRY", "ETHTRY", "XRPTRY", "SOLTRY", "AVAXTRY", "1000SATSTRY", "AMPTRY"]
    return fallback, "Canlı veri alınamadı, önbellek liste kullanılıyor"

# --- HELPER: BINANCE TR HESAP SORGULAMA (DÜZELTİLMİŞ UÇ NOKTA) ---
def fetch_binance_tr_data(key, secret):
    """
    Binance TR hesap bakiyesini çeker.
    Doğru uç nokta: GET /open/v1/account/spot
    """
    timestamp = int(time.time() * 1000)
    query_string = f"recvWindow=10000&timestamp={timestamp}"
    signature = hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "X-MBX-APIKEY": key,
        "Content-Type": "application/json",
    }

    # ✅ DÜZELTİLMİŞ UÇ NOKTA
    url = f"https://www.trbinance.com/open/v1/account/spot?{query_string}&signature={signature}"
    res = requests.get(url, headers=headers, timeout=15)

    logger.info(f"Binance TR yanıt: HTTP {res.status_code}")

    if res.status_code in (200, 201, 202):
        try:
            data = res.json()
            if isinstance(data, dict):
                return data.get("data", data)
            return {}
        except Exception as e:
            logger.error(f"JSON parse hatası: {e}")
            return {}
    else:
        # Hata detayını göster
        try:
            err_body = res.json()
            err_msg = err_body.get("msg", err_body.get("message", str(err_body)))
        except Exception:
            err_msg = res.text[:200] if res.text else "Bilinmeyen hata"
        raise Exception(f"HTTP {res.status_code}: {err_msg}")

# --- EXCHANGE INITIALIZATION ---
def init_exchange(borsa, key, secret):
    if not key or not secret:
        return None
    try:
        if "Binance USDT-M" in borsa:
            return ccxt.binance({
                "apiKey": key,
                "secret": secret,
                "options": {"defaultType": "future"},
                "enableRateLimit": True,
            })
        elif "OKX" in borsa:
            return ccxt.okx({
                "apiKey": key,
                "secret": secret,
                "enableRateLimit": True,
            })
        else:
            return "BINANCE_TR"
    except Exception as e:
        st.sidebar.error(f"Bağlantı hatası: {_mask_sensitive(e)}")
        logger.error(f"Exchange init hatası: {_mask_sensitive(e)}")
        return None

# --- BAĞLANTI KURMA ---
if st.sidebar.button("🔌 Bağlantıyı Kur / Yenile"):
    if not (api_key and secret_key):
        st.sidebar.warning("Lütfen geçerli API Key ve Secret Key girin.")
    else:
        with st.spinner("Bağlantı kuruluyor..."):
            try:
                exchange = init_exchange(borsa_secimi, api_key, secret_key)
                st.session_state["exchange"] = exchange

                if "Binance TR" in borsa_secimi:
                    account_data = fetch_binance_tr_data(api_key, secret_key)

                    try_free, try_total = 0.0, 0.0
                    asset_list = []

                    # Binance TR yanıt formatını esnek işle
                    balances = []
                    if isinstance(account_data, dict):
                        # Olası alan adları
                        balances = (
                            account_data.get("balances") or
                            account_data.get("assets") or
                            account_data.get("data") or
                            []
                        )
                        # Bazen direkt liste döner
                        if isinstance(account_data, list):
                            balances = account_data

                    for item in balances:
                        if not isinstance(item, dict):
                            continue
                        asset = str(
                            item.get("asset") or
                            item.get("symbol") or
                            item.get("coin") or ""
                        ).upper()
                        if not asset:
                            continue

                        free = float(item.get("free", 0.0) or 0.0)
                        locked = float(item.get("locked", 0.0) or 0.0)
                        total = free + locked

                        if total > 0:
                            asset_list.append({
                                "Varlık / Kripto": asset,
                                "Kullanılabilir Miktar": round(free, 6),
                                "Kilitli (Açık Emirde)": round(locked, 6),
                                "Toplam Miktar": round(total, 6),
                            })

                        if asset == "TRY":
                            try_free = free
                            try_total = total

                    st.session_state["toplam_bakiye"] = try_total
                    st.session_state["kullanilabilir_bakiye"] = try_free
                    st.session_state["bakiye_listesi"] = asset_list
                    st.session_state["baglanti_aktif"] = True
                    st.sidebar.success(f"✅ Binance TR bağlantısı başarılı! ({len(asset_list)} varlık)")

                else:
                    balance = exchange.fetch_balance()
                    st.session_state["toplam_bakiye"] = float(
                        balance.get("total", {}).get("USDT", 0.0) or 0.0
                    )
                    st.session_state["kullanilabilir_bakiye"] = float(
                        balance.get("free", {}).get("USDT", 0.0) or 0.0
                    )

                    asset_list = []
                    totals = balance.get("total", {}) or {}
                    frees = balance.get("free", {}) or {}
                    useds = balance.get("used", {}) or {}
                    for asset, total in totals.items():
                        try:
                            total_f = float(total or 0.0)
                        except Exception:
                            continue
                        if total_f > 0:
                            asset_list.append({
                                "Varlık / Kripto": asset,
                                "Kullanılabilir Miktar": round(float(frees.get(asset, 0.0) or 0.0), 6),
                                "Kilitli (Açık Emirde)": round(float(useds.get(asset, 0.0) or 0.0), 6),
                                "Toplam Miktar": round(total_f, 6),
                            })
                    st.session_state["bakiye_listesi"] = asset_list
                    st.session_state["baglanti_aktif"] = True
                    st.sidebar.success(f"✅ {borsa_secimi} bağlantısı başarılı!")

            except Exception as e:
                logger.error(f"API Doğrulama Hatası: {_mask_sensitive(e)}")
                st.sidebar.error(f"API Doğrulama Hatası: {_mask_sensitive(e)}")
                st.session_state["baglanti_aktif"] = False

if st.session_state["baglanti_aktif"]:
    st.sidebar.info(f"🟢 Bağlı: {borsa_secimi}")
else:
    st.sidebar.info("🔴 Bağlantı kurulmadı")

# --- DASHBOARD METRICS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Toplam Hesap Değeri", f"{st.session_state['toplam_bakiye']:.2f} {para_birimi}")
col2.metric("Kullanılabilir Teminat", f"{st.session_state['kullanilabilir_bakiye']:.2f} {para_birimi}")
col3.metric("Kâr / Zarar %", "+0.00%")
col4.metric("Aktif Para Birimi", para_birimi)

st.markdown("---")

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Genel Bakış",
    "⚙️ Strateji ve Risk",
    "🐋 Balina & Hacim Radarı",
    "🛡️ İğne & Sahte Kırılım Filtresi",
])

# --- CANLI PİYASA PARİTELERİ ---
market_symbols, market_error = fetch_binance_tr_symbols()
if market_error:
    st.caption(f"ℹ️ Piyasa verisi notu: {market_error}")

# --- TAB 1: GENEL BAKIŞ ---
with tab1:
    st.subheader("Açık Pozisyonlar ve Canlı İşlemler")
    st.info(f"Seçili Borsa: **{borsa_secimi}** | Birim: **{para_birimi}**")

    st.write("### 💼 Hesaptaki Varlıklar & Kripto Paralar")
    if st.session_state["bakiye_listesi"]:
        st.dataframe(
            pd.DataFrame(st.session_state["bakiye_listesi"]),
            use_container_width=True
        )
    else:
        st.info("Hesap bakiye detayları bekleniyor veya cüzdanda bakiye bulunmuyor.")

    st.write("### 📈 Binance TR Canlı İşlem Gören Pariteler")
    if market_symbols:
        df_market = pd.DataFrame([
            {"Aktif Sembol": sym, "Borsa": "Binance TR", "Durum": "İşleme Açık"}
            for sym in market_symbols
        ])
        st.dataframe(df_market, use_container_width=True)
        st.caption(f"Toplam {len(market_symbols)} adet TRY paritesi bulundu.")
    else:
        st.warning("Piyasa pariteleri şu anda alınamadı.")

# --- TAB 2: STRATEJİ VE RİSK ---
with tab2:
    st.subheader("Risk ve Strateji Parametreleri")
    defaults = DEFAULT_STRATEGY[para_birimi]
    saved = st.session_state.get("strategy") or defaults

    c1, c2 = st.columns(2)
    with c1:
        max_margin = st.number_input(
            f"İlk Giriş Teminat Üst Sınırı ({para_birimi})",
            value=float(saved.get("max_margin", defaults["max_margin"]))
        )
        risk_pct = st.number_input(
            "Pozisyon Başına Risk Bütçesi %",
            value=float(saved.get("risk_pct", defaults["risk_pct"]))
        )
        stop_loss_pct = st.number_input(
            "Kesin Zarar Kes (Stop-Loss) %",
            value=float(saved.get("stop_loss_pct", defaults["stop_loss_pct"]))
        )
        liq_buffer = st.number_input(
            "Zorunlu Tasfiye Koruma Mesafesi %",
            value=float(saved.get("liquidation_buffer_pct", defaults["liquidation_buffer_pct"]))
        )
    with c2:
        take_profit_pct = st.number_input(
            "İlk Kâr Al Hedefi %",
            value=float(saved.get("take_profit_pct", defaults["take_profit_pct"]))
        )
        trailing_stop_pct = st.number_input(
            "İzleyen Zarar Kesişi (Trailing Stop) %",
            value=float(saved.get("trailing_stop_pct", defaults["trailing_stop_pct"]))
        )
        entry_score = st.number_input(
            "Giriş Puanı Eşiği (100 Üzerinden)",
            value=int(saved.get("entry_score_threshold", defaults["entry_score_threshold"])),
            min_value=0, max_value=100
        )
        max_positions = st.number_input(
            "Aynı Anda Açık Pozisyon Sınırı",
            value=int(saved.get("max_open_positions", defaults["max_open_positions"])),
            min_value=1, max_value=50
        )

    if st.button("💾 Ayarları Kaydet ve Uygula"):
        st.session_state["strategy"] = {
            "max_margin": max_margin,
            "risk_pct": risk_pct,
            "stop_loss_pct": stop_loss_pct,
            "liquidation_buffer_pct": liq_buffer,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "entry_score_threshold": entry_score,
            "max_open_positions": max_positions,
        }
        st.success("Strateji ayarları başarıyla kaydedildi!")

# --- TAB 3: BALİNA VE HACİM RADARI (DÜZELTİLMİŞ) ---
with tab3:
    st.subheader("🐋 Balina Girişleri ve Ani Hacim Patlamaları")
    st.write("Bu radar, seçili borsadaki pariteleri canlı takip eder.")

    # Binance TR'de ticker endpoint'i yok, Binance ana platform kullanılacak
    st.caption("ℹ️ Binance TR'de halka açık ticker endpoint'i bulunmadığından, referans fiyat için Binance ana platform kullanılmaktadır.")

    if st.button("🔍 Piyasayı Şimdi Tara"):
        scan_symbols = market_symbols[:15] if market_symbols else []
        if not scan_symbols:
            st.warning("Önce piyasa sembolleri yüklenmeli.")
        else:
            with st.spinner(f"{len(scan_symbols)} parite taranıyor..."):
                rows = []
                for sym in scan_symbols:
                    try:
                        # Binance TR sembolünü Binance formatına çevir: BTCTRY -> BTCUSDT
                        base = sym.replace("TRY", "")
                        if base.startswith("1000"):
                            base = base[4:]  # 1000SHIB -> SHIB
                        binance_sym = f"{base}USDT"

                        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_sym}"
                        r = requests.get(url, timeout=5)
                        if r.status_code != 200:
                            continue
                        t = r.json()
                        last = float(t.get("lastPrice", 0) or 0)
                        qvol = float(t.get("quoteVolume", 0) or 0)
                        chg = float(t.get("priceChangePercent", 0) or 0)

                        rows.append({
                            "Parite (TR)": sym,
                            "Referans": binance_sym,
                            "Son Fiyat (USDT)": last,
                            "24s Hacim (USDT)": round(qvol, 2),
                            "Değişim %": round(chg, 2),
                        })
                    except Exception as e:
                        logger.debug(f"Ticker hatası {sym}: {e}")
                        continue

                if rows:
                    df = pd.DataFrame(rows).sort_values("24s Hacim (USDT)", ascending=False)
                    st.dataframe(df, use_container_width=True)
                    st.caption("Hacmi en yüksek olanlar potansiyel balina aktivitesi bölgesidir.")
                else:
                    st.info("Tarama sonucu veri alınamadı.")
    else:
        st.info("Tarama başlatmak için butona basın.")

# --- TAB 4: İĞNE KORUMASI ---
with tab4:
    st.subheader("🛡️ İğne Atma & Sahte Kırılım (Spike) Koruması")
    st.write("Anlık iğne hareketlerinde panik stop olmamak için filtre mekanizmasını yapılandırın.")

    st.checkbox("İğne Atma Korumasını Aktif Et", value=True, key="spike_protection")
    st.selectbox(
        "Kapanış Onayı Zaman Dilimi",
        ["1 Dakikalık Mum Kapanışı", "3 Dakikalık Mum Kapanışı", "5 Dakikalık Mum Kapanışı"],
        key="spike_tf"
    )
    st.number_input(
        "İğne Teyit Bekleme Süresi (Saniye)",
        value=3, min_value=1, max_value=60, key="spike_wait"
    )
