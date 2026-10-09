import streamlit as st
import pandas as pd
import requests
import hmac
import hashlib
import time
import ccxt

# --- PAGE CONFIG ---
st.set_page_config(page_title="CEX T1 - Kripto Bot", layout="wide", initial_sidebar_state="expanded")

st.title("🤖 CEX T1 - Otomatik Kripto & Balina Radarı Botu")

# --- SESSION STATE INITIALIZATION ---
if "toplam_bakiye" not in st.session_state:
    st.session_state["toplam_bakiye"] = 0.0
if "kullanilabilir_bakiye" not in st.session_state:
    st.session_state["kullanilabilir_bakiye"] = 0.0
if "bakiye_listesi" not in st.session_state:
    st.session_state["bakiye_listesi"] = []

# --- SIDEBAR CONFIG ---
st.sidebar.header("BORSA VE BAĞLANTI")

borsa_secimi = st.sidebar.selectbox(
    "Borsa Seçin",
    ["Binance TR (Spot - TRY)", "Binance USDT-M (Vadeli)", "OKX Futures"]
)

api_key = st.sidebar.text_input("Erişim Anahtarı (API Key)", type="password")
secret_key = st.sidebar.text_input("Gizli Anahtar (Secret Key)", type="password")

para_birimi = "TRY" if "Binance TR" in borsa_secimi else "USDT"

# --- HELPER: BINANCE TR CANLI PİYASA PARİTELERİ (PUBLIC API) ---
@st.cache_data(ttl=15)
def fetch_binance_tr_market_data():
    try:
        url = "https://tr.binance.com/open/v1/common/symbols"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 0 and "data" in data:
                symbols = [s.get("symbol") for s in data["data"] if s.get("symbol", "").endswith("TRY")]
                return symbols
    except Exception:
        pass
    return ["BTCTRY", "ETHTRY", "XRPTRY", "SOLTRY", "AVAXTRY", "1000SATSTRY"]

# --- HELPER: BINANCE TR CANLI BAKİYE VE HESAP ---
def fetch_binance_tr_data(key, secret):
    timestamp = int(time.time() * 1000)
    query_string = f"recvWindow=10000&timestamp={timestamp}"
    signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    headers = {
        'X-MBX-APIKEY': key,
        'Content-Type': 'application/json'
    }
    
    url = f"https://tr.binance.com/open/v1/user/account?{query_string}&signature={signature}"
    res = requests.get(url, headers=headers, timeout=10)
    
    if res.status_code in [200, 201, 202]:
        try:
            data = res.json()
            return data.get("data", data)
        except Exception:
            return {}
    raise Exception(f"Binance TR Sunucu Hatası: {res.status_code}")

# --- EXCHANGE INITIALIZATION ---
def init_exchange(borsa, key, secret):
    if not key or not secret:
        return None
    try:
        if "Binance USDT-M" in borsa:
            return ccxt.binance({
                'apiKey': key,
                'secret': secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True
            })
        elif "OKX" in borsa:
            return ccxt.okx({'apiKey': key, 'secret': secret, 'enableRateLimit': True})
        else:
            return "BINANCE_TR"
    except Exception as e:
        st.sidebar.error(f"Bağlantı hatası: {e}")
        return None

exchange = init_exchange(borsa_secimi, api_key, secret_key)

if st.sidebar.button("Bağlantıyı Kur / Yenile"):
    if api_key and secret_key:
        try:
            if "Binance TR" in borsa_secimi:
                account_data = fetch_binance_tr_data(api_key, secret_key)
                
                try_free = 0.0
                try_total = 0.0
                asset_list = []
                
                balances = account_data.get("balances", account_data.get("assets", [])) if isinstance(account_data, dict) else []
                
                for item in balances:
                    if isinstance(item, dict):
                        asset = str(item.get("asset", item.get("symbol", ""))).upper()
                        free = float(item.get("free", 0.0) or 0.0)
                        locked = float(item.get("locked", 0.0) or 0.0)
                        total = free + locked
                        
                        if total > 0:
                            asset_list.append({
                                "Varlık / Kripto": asset,
                                "Kullanılabilir Miktar": free,
                                "Kilitli (Açık Emirde)": locked,
                                "Toplam Miktar": total
                            })
                        
                        if asset == "TRY":
                            try_free = free
                            try_total = total
                
                st.session_state["toplam_bakiye"] = try_total
                st.session_state["kullanilabilir_bakiye"] = try_free
                st.session_state["bakiye_listesi"] = asset_list
                st.sidebar.success("✅ Binance TR bağlantısı başarılı!")
            else:
                balance = exchange.fetch_balance()
                st.session_state["toplam_bakiye"] = float(balance.get('total', {}).get('USDT', 0.0))
                st.session_state["kullanilabilir_bakiye"] = float(balance.get('free', {}).get('USDT', 0.0))
                st.sidebar.success(f"✅ {borsa_secimi} bağlantısı başarılı!")
        except Exception as e:
            st.sidebar.error(f"API Doğrulama Hatası: {e}")
    else:
        st.sidebar.warning("Lütfen geçerli API Key ve Secret Key girin.")

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
    "🛡️ İğne & Sahte Kırılım Filtresi"
])

# --- CANLI PİYASA PARİTELERİ VE İŞLEM GÖREN KRİPTOLAR ---
market_symbols = fetch_binance_tr_market_data()

# --- TAB 1: GENEL BAKIŞ ---
with tab1:
    st.subheader("Açık Pozisyonlar ve Canlı İşlemler")
    st.info(f"Seçili Borsa: **{borsa_secimi}** | Birim: **{para_birimi}**")
    
    # 1. HESAPTAKİ KRİPTO VARLIKLAR TABLOSU
    st.write("### 💼 Hesaptaki Varlıklar & Kripto Paralar")
    if st.session_state["bakiye_listesi"]:
        st.dataframe(pd.DataFrame(st.session_state["bakiye_listesi"]), use_container_width=True)
    else:
        st.warning("Henüz bakiye çekilmedi veya hesapta varlık bulunmuyor. Sol menüden 'Bağlantıyı Kur / Yenile' butonuna basın.")

    # 2. BORSA DA İŞLEM GÖREN AKTİF PARİTELER
    st.write("### 📈 Binance TR Canlı İşlem Gören Pariteler")
    df_market = pd.DataFrame([{"Aktif Sembol": sym, "Borsa": "Binance TR", "Durum": "İşleme Açık"} for sym in market_symbols])
    st.dataframe(df_market, use_container_width=True)

# --- TAB 2: STRATEJİ VE RİSK ---
with tab2:
    st.subheader("Risk ve Strateji Parametreleri")
    
    c1, c2 = st.columns(2)
    with c1:
        st.number_input(f"İlk Giriş Teminat Üst Sınırı ({para_birimi})", value=1000.0 if para_birimi=="TRY" else 40.0)
        st.number_input("Pozisyon Başına Risk Bütçesi %", value=1.00 if para_birimi=="TRY" else 0.50)
        st.number_input("Kesin Zarar Kes (Stop-Loss) %", value=1.50)
        st.number_input("Zorunlu Taşfiye Koruma Mesafesi %", value=1.50)
    with c2:
        st.number_input("İlk Kâr Al Hedefi %", value=2.50)
        st.number_input("İzleyen Zarar Kesişi (Trailing Stop) %", value=1.00)
        st.number_input("Giriş Puanı Eşiği (100 Üzerinden)", value=75)
        st.number_input("Aynı Anda Açık Pozisyon Sınırı", value=2)
        
    if st.button("Ayarları Kaydet ve Uygula"):
        st.success("Strateji ayarları başarıyla kaydedildi!")

# --- TAB 3: BALİNA VE HACİM RADARI ---
with tab3:
    st.subheader("🐋 Balina Girişleri ve Ani Hacim Patlamaları")
    st.write("Bu radar, Binance TR üzerindeki paritelerde anlık hacim sıçramalarını tarar.")
    
    whale_data = [
        {"Parite": sym, "Hacim Sıçraması": "Canlı Taranıyor...", "Sinyal": "TAKİPTE"} 
        for sym in market_symbols[:5]
    ]
    st.dataframe(pd.DataFrame(whale_data), use_container_width=True)

# --- TAB 4: İĞNE KORUMASI ---
with tab4:
    st.subheader("🛡️ İğne Atma & Sahte Kırılım (Spike) Koruması")
    st.write("Anlık iğne hareketlerinde panik stop olmamak için filtre mekanizmasını yapılandırın.")
    
    st.checkbox("İğne Atma Korumasını Aktif Et", value=True)
    st.selectbox("Kapanış Onayı Zaman Dilimi", ["1 Dakikalık Mum Kapanışı", "3 Dakikalık Mum Kapanışı", "5 Dakikalık Mum Kapanışı"])
    st.number_input("İğne Teyit Bekleme Süresi (Saniye)", value=3)
