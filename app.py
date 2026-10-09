import time
import hmac
import hashlib
from urllib.parse import urlencode

import requests
import pandas as pd
import streamlit as st
import ccxt

# =========================================================
# CEX T1 - KRİPTO VE BALİNA RADARI
# Güvenli sürüm: otomatik emir göndermez.
# =========================================================

BASE_URL = "https://www.binance.tr"
TIMEOUT = 10

st.set_page_config(
    page_title="CEX T1 - Kripto Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🤖 CEX T1 - Kripto ve Balina Radarı")
st.caption("Canlı veri analizi • Gerçek emir gönderimi kapalı")

# ---------------- SESSION STATE --------------------------

DEFAULTS = {
    "toplam_bakiye": 0.0,
    "kullanilabilir_bakiye": 0.0,
    "bakiye_listesi": [],
    "ayarlar": {},
    "son_baglanti": "",
    "baglanti_durumu": "Bağlantı kurulmadı",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------- HTTP YARDIMCISI ------------------------

def api_get(path, params=None, headers=None):
    """HTTP isteği yapar; hatalı yanıtları gizlemez."""
    response = requests.get(
        BASE_URL + path,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        code = data.get("code")
        if code not in (None, 0, "0"):
            raise RuntimeError(
                f"Borsa API hatası: {data.get('msg', data)}"
            )

    return data


# ---------------- BINANCE TR SEMBOLLER -------------------

@st.cache_data(ttl=60, show_spinner=False)
def fetch_binance_tr_symbols():
    """Resmi sembol listesinden TRY paritelerini alır."""
    data = api_get("/open/v1/common/symbols")

    payload = data.get("data", {})
    if isinstance(payload, dict):
        symbols = payload.get("list", [])
    elif isinstance(payload, list):
        symbols = payload
    else:
        symbols = []

    result = []

    for item in symbols:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).upper()
        quote = str(item.get("quoteAsset", "")).upper()

        if quote == "TRY" or symbol.endswith("_TRY"):
            result.append(symbol)

    if not result:
        raise RuntimeError(
            "API yanıtında aktif TRY paritesi bulunamadı."
        )

    return sorted(set(result))


# ---------------- BINANCE TR HESAP -----------------------

def fetch_binance_tr_account(api_key, secret_key):
    """Salt okunur hesap bilgisi. Emir göndermez."""
    timestamp = int(time.time() * 1000)

    params = {
        "recvWindow": 10000,
        "timestamp": timestamp,
    }

    query = urlencode(params)

    signature = hmac.new(
        secret_key.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "X-MBX-APIKEY": api_key,
    }

    data = api_get(
        "/open/v1/account/spot",
        params={**params, "signature": signature},
        headers=headers,
    )

    account = data.get("data", {})

    if not isinstance(account, dict):
        raise RuntimeError("Hesap API yanıtı beklenen formatta değil.")

    assets = account.get("accountAssets", [])

    if not isinstance(assets, list):
        raise RuntimeError("Hesap varlık listesi geçersiz.")

    rows = []
    total_try = 0.0
    free_try = 0.0

    for item in assets:
        if not isinstance(item, dict):
            continue

        asset = str(item.get("asset", "")).upper()

        try:
            free = float(item.get("free", 0) or 0)
            locked = float(item.get("locked", 0) or 0)
        except (TypeError, ValueError):
            continue

        total = free + locked

        if total > 0:
            rows.append({
                "Varlık": asset,
                "Kullanılabilir": free,
                "Kilitlemiş / Emirde": locked,
                "Toplam": total,
            })

        if asset == "TRY":
            free_try = free
            total_try = total

    return rows, free_try, total_try


# ---------------- CCXT BAĞLANTISI ------------------------

def init_exchange(exchange_name, api_key, secret_key):
    if not api_key or not secret_key:
        raise ValueError("API Key ve Secret Key gerekli.")

    if exchange_name == "Binance USDT-M (Vadeli)":
        exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": secret_key,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
    elif exchange_name == "OKX Futures":
        exchange = ccxt.okx({
            "apiKey": api_key,
            "secret": secret_key,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
    else:
        return None

    return exchange


# ---------------- SIDEBAR --------------------------------

st.sidebar.header("🔌 Borsa ve Bağlantı")

borsa = st.sidebar.selectbox(
    "Borsa seçin",
    [
        "Binance TR (Spot - TRY)",
        "Binance USDT-M (Vadeli)",
        "OKX Futures",
    ],
)

api_key = st.sidebar.text_input(
    "API Key",
    type="password",
)

secret_key = st.sidebar.text_input(
    "Secret Key",
    type="password",
)

birim = "TRY" if borsa.startswith("Binance TR") else "USDT"

if st.sidebar.button("Bağlantıyı Kur / Yenile", type="primary"):
    if not api_key or not secret_key:
        st.sidebar.warning("İki API alanını da doldur.")
    else:
        try:
            if borsa.startswith("Binance TR"):
                rows, free, total = fetch_binance_tr_account(
                    api_key, secret_key
                )

                st.session_state["bakiye_listesi"] = rows
                st.session_state["kullanilabilir_bakiye"] = free
                st.session_state["toplam_bakiye"] = total

            else:
                exchange = init_exchange(
                    borsa, api_key, secret_key
                )

                balance = exchange.fetch_balance()

                total = float(
                    balance.get("total", {}).get("USDT") or 0
                )
                free = float(
                    balance.get("free", {}).get("USDT") or 0
                )

                st.session_state["toplam_bakiye"] = total
                st.session_state["kullanilabilir_bakiye"] = free

                totals = balance.get("total", {})
                frees = balance.get("free", {})
                used = balance.get("used", {})

                st.session_state["bakiye_listesi"] = [
                    {
                        "Varlık": asset,
                        "Kullanılabilir": float(frees.get(asset) or 0),
                        "Kilitlemiş / Emirde": float(used.get(asset) or 0),
                        "Toplam": float(amount or 0),
                    }
                    for asset, amount in totals.items()
                    if amount and float(amount) > 0
                ]

            st.session_state["baglanti_durumu"] = "Bağlantı başarılı"
            st.session_state["son_baglanti"] = time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            st.sidebar.success("Bağlantı başarılı.")

        except Exception as exc:
            st.session_state["baglanti_durumu"] = "Bağlantı hatası"
            st.sidebar.error(f"Bağlantı kurulamadı: {exc}")


# ---------------- HESAP ÖZETİ ----------------------------

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Toplam Bakiye",
    f"{st.session_state['toplam_bakiye']:,.2f} {birim}",
)
c2.metric(
    "Kullanılabilir",
    f"{st.session_state['kullanilabilir_bakiye']:,.2f} {birim}",
)
c3.metric("Gerçekleşen K/Z", "Hesaplanmadı")
c4.metric("Bağlantı", st.session_state["baglanti_durumu"])

if st.session_state["son_baglanti"]:
    st.caption("Son bağlantı: " + st.session_state["son_baglanti"])

st.warning(
    "Bu sürüm otomatik alım satım yapmaz. "
    "Toplam hesap değeri, bütün kripto varlıkların TRY/USDT "
    "karşılığını hesaplamaz; yalnızca seçili para birimindeki "
    "bakiye gösterilir."
)

# ---------------- SEKME YAPISI ---------------------------

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Genel Bakış",
    "⚙️ Strateji ve Risk",
    "🐋 Hacim Radarı",
    "🛡️ İğne Filtresi",
])


# ---------------- TAB 1: GENEL BAKIŞ ---------------------

with tab1:
    st.subheader("Hesaptaki varlıklar")

    assets = st.session_state["bakiye_listesi"]

    if assets:
        st.dataframe(
            pd.DataFrame(assets),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Önce sol menüden hesap bağlantısını kur.")

    st.subheader("Binance TR işlem pariteleri")

    try:
        symbols = fetch_binance_tr_symbols()

        st.success(f"{len(symbols)} TRY paritesi listelendi.")

        st.dataframe(
            pd.DataFrame({
                "Sembol": symbols,
                "Borsa": ["Binance TR"] * len(symbols),
            }),
            use_container_width=True,
            hide_index=True,
        )

    except Exception as exc:
        st.error(f"Parite listesi alınamadı: {exc}")


# ---------------- TAB 2: STRATEJİ VE RİSK ----------------

with tab2:
    st.subheader("Strateji parametreleri")

    with st.form("strategy_form"):
        left, right = st.columns(2)

        with left:
            max_entry = st.number_input(
                f"Giriş tutarı üst sınırı ({birim})",
                min_value=0.0,
                value=1000.0 if birim == "TRY" else 40.0,
                step=10.0,
            )

            risk_pct = st.number_input(
                "Pozisyon başına risk (%)",
                min_value=0.1,
                max_value=100.0,
                value=1.0,
                step=0.1,
            )

            stop_loss = st.number_input(
                "Stop-loss (%)",
                min_value=0.1,
                max_value=50.0,
                value=1.5,
                step=0.1,
            )

            liquidation_buffer = st.number_input(
                "Tasfiye koruma mesafesi (%)",
                min_value=0.1,
                max_value=50.0,
                value=1.5,
                step=0.1,
            )

        with right:
            take_profit = st.number_input(
                "Kâr hedefi (%)",
                min_value=0.1,
                max_value=100.0,
                value=2.5,
                step=0.1,
            )

            trailing_stop = st.number_input(
                "Trailing stop (%)",
                min_value=0.1,
                max_value=50.0,
                value=1.0,
                step=0.1,
            )

            score_threshold = st.number_input(
                "Sinyal puanı eşiği",
                min_value=1,
                max_value=100,
                value=75,
            )

            max_positions = st.number_input(
                "Maksimum açık pozisyon",
                min_value=1,
                max_value=20,
                value=2,
                step=1,
            )

        submitted = st.form_submit_button("Ayarları Kaydet")

    if submitted:
        st.session_state["ayarlar"] = {
            "max_entry": max_entry,
            "risk_pct": risk_pct,
            "stop_loss": stop_loss,
            "liquidation_buffer": liquidation_buffer,
            "take_profit": take_profit,
            "trailing_stop": trailing_stop,
            "score_threshold": score_threshold,
            "max_positions": max_positions,
        }

        st.success("Ayarlar mevcut oturum için kaydedildi.")

    if st.session_state["ayarlar"]:
        st.json(st.session_state["ayarlar"])

    st.caption(
        "Ayarlar henüz işlem motoruna bağlı değil ve uygulama "
        "yeniden başlatıldığında kalıcı olarak saklanmaz."
    )


# ---------------- TAB 3: HACİM RADARI ---------------------

with tab3:
    st.subheader("🐋 Hacim ve olağan dışı hareket radarı")

    st.info(
        "Sembol listesi tek başına hacim analizi değildir. "
        "Gerçek hacim ve fiyat uç noktası doğrulanmadan "
        "balina sinyali üretilmez."
    )

    if st.button("Sembol listesini yenile"):
        fetch_binance_tr_symbols.clear()
        st.rerun()

    st.write(
        "Bir sonraki aşamada her parite için gerçek işlem hacmi, "
        "1 dakikalık mumlar ve büyük işlem verileri alınarak "
        "karşılaştırmalı sinyal tablosu eklenebilir."
    )


# ---------------- TAB 4: İĞNE FİLTRESİ -------------------

with tab4:
    st.subheader("🛡️ İğne ve sahte kırılım filtresi")

    enabled = st.checkbox(
        "İğne filtresi etkin",
        value=True,
    )

    timeframe = st.selectbox(
        "Kapanış teyit aralığı",
        ["1 dakika", "3 dakika", "5 dakika"],
    )

    wait_seconds = st.number_input(
        "Teyit bekleme süresi (saniye)",
        min_value=0,
        max_value=300,
        value=3,
    )

    st.write({
        "Filtre etkin": enabled,
        "Teyit aralığı": timeframe,
        "Bekleme saniyesi": wait_seconds,
    })

    st.caption(
        "Bu parametreler şu an yalnızca yapılandırmadır. "
        "Mum verisine uygulanan bir filtre veya otomatik emir "
        "mekanizması değildir."
    )

# ---------------- FOOTER ---------------------------------

st.divider()
st.caption(
    "CEX T1 • Piyasa verisi ve hesap görüntüleme prototipi • "
    "Otomatik emir gönderimi kapalı"
)
