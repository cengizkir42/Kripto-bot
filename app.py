import time
import hmac
import hashlib
from urllib.parse import urlencode

import requests
import pandas as pd
import streamlit as st

BASE = "https://www.binance.tr"
TIMEOUT = 12

st.set_page_config(
    page_title="CEX T1 V2",
    page_icon="🐋",
    layout="wide",
)

st.title("🤖 CEX T1 V2 | Kripto Radar")
st.caption("Canlı piyasa • Hacim anomalisi • Risk izleme")
st.warning("Güvenli mod: Bu uygulama gerçek alım satım emri göndermez.")

if "account_assets" not in st.session_state:
    st.session_state.account_assets = []
if "account_status" not in st.session_state:
    st.session_state.account_status = "Bağlanmadı"
if "strategy" not in st.session_state:
    st.session_state.strategy = {}

# ---------- API YARDIMCILARI ----------

def get_json(url, params=None, headers=None):
    r = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
    )
    if r.status_code == 451:
        raise RuntimeError(
            "Borsa bu sunucu isteğini 451 ile reddetti. "
            "API erişim politikası veya ağ kaynaklı olabilir."
        )
    r.raise_for_status()
    data = r.json()

    if isinstance(data, dict):
        code = data.get("code")
        if code not in (None, 0, "0"):
            raise RuntimeError(
                str(data.get("msg", "Borsa API hatası"))
            )
    return data


def tr_get(path, params=None):
    return get_json(BASE + path, params=params)


def account_request(key, secret):
    params = {
        "recvWindow": 5000,
        "timestamp": int(time.time() * 1000),
    }
    query = urlencode(params)
    params["signature"] = hmac.new(
        secret.encode(),
        query.encode(),
        hashlib.sha256,
    ).hexdigest()

    return tr_get(
        "/open/v1/account/spot",
        params=params,
    ) if False else get_json(
        BASE + "/open/v1/account/spot",
        params=params,
        headers={"X-MBX-APIKEY": key},
    )


# ---------- SEMBOL LİSTESİ ----------

@st.cache_data(ttl=120, show_spinner=False)
def load_symbols():
    data = tr_get("/open/v1/common/symbols")
    body = data.get("data", {})
    items = body.get("list", []) if isinstance(body, dict) else body

    symbols = []
    for item in items:
        if not isinstance(item, dict):
            continue

        quote = str(item.get("quoteAsset", "")).upper()
        symbol = str(item.get("symbol", "")).upper()
        status = str(item.get("status", "")).upper()

        if quote == "TRY" or symbol.endswith("_TRY"):
            if status in ("", "TRADING", "1"):
                symbols.append(symbol)

    if not symbols:
        raise RuntimeError("API geçerli TRY paritesi döndürmedi.")

    return sorted(set(symbols))


# ---------- PİYASA VERİSİ ----------

def market_symbol(symbol):
    # Binance TR ana sembollerinde ADA_TRY gibi adlar kullanılır.
    return symbol.replace("_", "")


def load_klines(symbol, interval="1m", limit=30):
    # Dokümantasyonda ana semboller için bu piyasa adresi belirtilir.
    params = {
        "symbol": market_symbol(symbol),
        "interval": interval,
        "limit": limit,
    }

    data = get_json(
        "https://api.binance.me/api/v1/klines",
        params=params,
    )

    rows = data.get("data", []) if isinstance(data, dict) else data

    if not rows:
        raise RuntimeError("Mum verisi boş geldi.")

    df = pd.DataFrame(
        rows,
        columns=[
            "time", "open", "high", "low", "close",
            "volume", "close_time", "quote_volume",
            "trades", "buy_volume", "buy_quote_volume", "ignore",
        ],
    )

    for col in [
        "open", "high", "low", "close",
        "volume", "quote_volume", "buy_quote_volume",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close", "volume"])
    return df


def analyze_symbol(symbol):
    df = load_klines(symbol)

    if len(df) < 5:
        raise RuntimeError("Analiz için yeterli mum yok.")

    # Son mum hâlâ açık olabileceği için kapanmış mumları kullan.
    closed = df.iloc[:-1].copy()
    if len(closed) < 4:
        raise RuntimeError("Yeterli kapanmış mum bulunamadı.")

    last = closed.iloc[-1]
    previous = closed.iloc[-4:-1]

    old_volume = float(previous["volume"].mean())
    current_volume = float(last["volume"])
    volume_ratio = (
        current_volume / old_volume if old_volume > 0 else 0
    )

    first_close = float(closed.iloc[-2]["close"])
    last_close = float(last["close"])
    change_pct = (
        (last_close / first_close - 1) * 100
        if first_close else 0
    )

    candle_range = float(last["high"] - last["low"])
    candle_body = abs(float(last["close"] - last["open"]))
    wick_ratio = (
        (candle_range - candle_body) / candle_range
        if candle_range > 0 else 0
    )

    if volume_ratio >= 3:
        signal = "HACİM SIÇRAMASI"
    elif change_pct >= 1:
        signal = "YUKARI HAREKET"
    elif change_pct <= -1:
        signal = "AŞAĞI HAREKET"
    else:
        signal = "TAKİPTE"

    return {
        "Parite": symbol,
        "Son kapanış": last_close,
        "Değişim %": round(change_pct, 3),
        "Hacim oranı": round(volume_ratio, 2),
        "Fitil oranı %": round(wick_ratio * 100, 1),
        "Durum": signal,
    }


# ---------- SOL MENÜ ----------

st.sidebar.header("Borsa bağlantısı")
st.sidebar.caption("API anahtarlarını GitHub koduna yazma.")

api_key = st.sidebar.text_input("API Key", type="password")
secret_key = st.sidebar.text_input("Secret Key", type="password")

if st.sidebar.button("Hesap bağlantısını kontrol et"):
    if not api_key or not secret_key:
        st.sidebar.warning("İki alanı da doldur.")
    else:
        try:
            result = account_request(api_key, secret_key)
            account = result.get("data", {})
            assets = account.get("accountAssets", [])

            if not isinstance(assets, list):
                raise RuntimeError(
                    "Hesap varlık yanıtı beklenen biçimde değil."
                )

            rows = []
            for item in assets:
                free = float(item.get("free", 0) or 0)
                locked = float(item.get("locked", 0) or 0)

                if free + locked > 0:
                    rows.append({
                        "Varlık": item.get("asset", "?"),
                        "Kullanılabilir": free,
                        "Kilitlemiş": locked,
                        "Toplam": free + locked,
                    })

            st.session_state.account_assets = rows
            st.session_state.account_status = "Bağlantı başarılı"
            st.sidebar.success("Hesap bilgisi alındı.")

        except Exception as e:
            st.session_state.account_status = "Bağlantı hatası"
            st.sidebar.error(str(e))

st.sidebar.write("Durum:", st.session_state.account_status)

# ---------- ÖZET ----------

a, b, c = st.columns(3)
a.metric("Çalışma modu", "Analiz")
b.metric("Gerçek emir", "Kapalı")
c.metric("Hesap", st.session_state.account_status)

tab1, tab2, tab3 = st.tabs([
    "📊 Genel Bakış",
    "🐋 Hacim Radarı",
    "🛡️ Risk ve İğne Filtresi",
])

# ---------- GENEL BAKIŞ ----------

with tab1:
    st.subheader("Hesaptaki varlıklar")

    if st.session_state.account_assets:
        st.dataframe(
            pd.DataFrame(st.session_state.account_assets),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Hesap bakiyesi için sol menüden bağlantı kur.")

    st.subheader("TRY pariteleri")

    if st.button("Parite listesini getir"):
        try:
            symbols = load_symbols()
            st.session_state["symbols"] = symbols
            st.success(f"{len(symbols)} parite bulundu.")
        except Exception as e:
            st.error(f"Parite listesi alınamadı: {e}")

    symbols = st.session_state.get("symbols", [])
    if symbols:
        st.dataframe(
            pd.DataFrame({"Parite": symbols}),
            use_container_width=True,
            hide_index=True,
        )

# ---------- HACİM RADARI ----------

with tab2:
    st.subheader("Gerçek mum verisiyle hacim taraması")

    try:
        symbols = st.session_state.get("symbols") or load_symbols()
        st.session_state["symbols"] = symbols

        # İstek yükünü kontrol altında tutmak için tarama sınırı.
        limit = st.slider(
            "Taranacak ilk parite sayısı",
            min_value=1,
            max_value=min(30, len(symbols)),
            value=min(10, len(symbols)),
        )

        if st.button("Taramayı başlat", type="primary"):
            results = []
            errors = []

            progress = st.progress(0)

            for i, symbol in enumerate(symbols[:limit]):
                try:
                    results.append(analyze_symbol(symbol))
                except Exception as e:
                    errors.append({
                        "Parite": symbol,
                        "Hata": str(e),
                    })

                progress.progress((i + 1) / limit)

            if results:
                result_df = pd.DataFrame(results)
                result_df = result_df.sort_values(
                    "Hacim oranı", ascending=False
                )
                st.dataframe(
                    result_df,
                    use_container_width=True,
                    hide_index=True,
                )

            if errors:
                with st.expander(
                    f"Veri alınamayan pariteler ({len(errors)})"
                ):
                    st.dataframe(
                        pd.DataFrame(errors),
                        use_container_width=True,
                        hide_index=True,
                    )

            if not results:
                st.error(
                    "Hiçbir pariteden veri alınamadı. "
                    "API erişimini ve sembol biçimini kontrol et."
                )

    except Exception as e:
        st.error(f"Radar başlatılamadı: {e}")

    st.caption(
        "Hacim oranı, son kapanmış mumun hacmini önceki "
        "3 kapanmış mumun ortalamasıyla karşılaştırır. "
        "Bu tek başına balina işlemi kanıtı değildir."
    )

# ---------- RİSK VE FİLTRE ----------

with tab3:
    st.subheader("Risk parametreleri")

    with st.form("risk_form"):
        budget = st.number_input(
            "İşlem bütçesi (TRY)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
        )
        risk_pct = st.number_input(
            "İşlem başına risk (%)",
            min_value=0.1,
            max_value=5.0,
            value=1.0,
            step=0.1,
        )
        stop_pct = st.number_input(
            "Stop-loss mesafesi (%)",
            min_value=0.1,
            max_value=20.0,
            value=1.5,
            step=0.1,
        )
        target_pct = st.number_input(
            "Kâr hedefi (%)",
            min_value=0.1,
            max_value=50.0,
            value=2.5,
            step=0.1,
        )
        wick_filter = st.checkbox(
            "Yüksek fitil oranını uyarı olarak göster",
            value=True,
        )
        threshold = st.slider(
            "Fitil uyarı eşiği (%)",
            min_value=20,
            max_value=95,
            value=65,
        )

        save = st.form_submit_button("Ayarları kaydet")

    if save:
        st.session_state.strategy = {
            "budget": budget,
            "risk_pct": risk_pct,
            "stop_pct": stop_pct,
            "target_pct": target_pct,
            "wick_filter": wick_filter,
            "wick_threshold": threshold,
        }

    if st.session_state.strategy:
        settings = st.session_state.strategy
        st.success("Ayarlar bu oturum için kaydedildi.")
        st.write(
            "Planlanan risk bütçesi:",
            round(
                settings["budget"] * settings["risk_pct"] / 100,
                2,
            ),
            "TRY",
        )
        st.write(
            "Stop mesafesi:",
            settings["stop_pct"],
            "%",
            "| Kâr hedefi:",
            settings["target_pct"],
            "%",
        )

        if settings["wick_filter"]:
            st.write(
                "Fitil uyarı eşiği:",
                settings["wick_threshold"],
                "%",
            )

    st.info(
        "Bu risk ayarları yalnızca hesaplama ve görüntüleme içindir. "
        "Emir oluşturmaz, stop emri göndermez ve tasfiyeyi engellemez."
    )

st.divider()
st.caption(
    "CEX T1 V2 • Veri alınamadığında hata gösterilir; "
    "örnek veriler gerçek piyasa verisi gibi sunulmaz."
)
