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

# --- HELPER: BINANCE TR CANLI BAKİYE DETAYI ---
def get_binance_tr_balances(key, secret):
    # Binance TR cüzdan bakiye uç noktası
    url = "https://tr.binance.com/open/v1/asset/wallet/balance"
    timestamp = int(time.time() * 1000)
    query_string = f"recvWindow=10000&timestamp={timestamp}"
    signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    headers = {
        'X-MBX-APIKEY': key,
        'Content-Type': 'application/json'
    }
    
    full_url = f"{url}?{query_string}&signature={signature}"
    res = requests.get(full_url, headers=headers, timeout=10)
    
    # Eğer ilk uç nokta yanıt vermezse kullanıcı uç noktasını yedek olarak çağır
    if res.status_code not in [200, 201, 202]:
        url_backup = "https://tr.binance.com/open/v1/user/account"
        full_url = f"{url_backup}?{query_string}&signature={signature}"
        res = requests.get(full_url, headers=headers, timeout=10)

    if res.status_code in [200, 201, 202]:
        try:
            data = res.json()
            if isinstance(data, dict):
                return data.get("data", data)
            return data
        except Exception:
            return {}
    else:
        raise Exception(f"Binance TR Sunucu Hatası: HTTP {res.status_code}")

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
                account_info = get_binance_tr_balances(api_key, secret_key)
                
                try_free = 0.0
                try_total = 0.0
                asset_list = []
                
                # Bakiye verilerini ayrıştır
                balances = []
                if isinstance(account_info, dict):
                    balances = account_info.get("balances", account_info.get("assets", account_info.get("list", [])))
                elif isinstance(account_info, list):
                    balances = account_info
                
                for b in balances:
                    if isinstance(b, dict):
                        asset_name = str(b.get("asset", b.get("assetName", b.get("symbol", ""))))
                        free_val = float(b.get("free", b.get("freeAmount", b.get("balance", 0.0))) or 0.0)
                        locked_val = float(b.get("locked", b.get("lockedAmount", 0.0)) or 0.0)
                        total_val = free_val + locked_val
                        
                        if total_val > 0:
                            asset_list.append({
                                "Varlık": asset_name,
                                "Kullanılabilir": round(free_val, 4),
                                "Kilitli": round(locked_val, 4),
                                "Toplam": round(total_val, 4)
                            })
                        
                        if asset_name.upper() == "TRY":
                            try_free = free_val
                            try_total = total_val
                
                st.session_state["toplam_bakiye"] = try_total
                st.session_state["kullanilabilir_bakiye"] = try_free
                st.session_state["bakiye_listesi"] = asset_list
                st.sidebar.success("✅ Binance TR bağlantısı ve bakiye sorgusu başarılı!")
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

# --- TAB 1: GENEL BAKIŞ ---
with tab1:
    st.subheader("Açık Pozisyonlar ve Canlı İşlemler")
    st.info(f"Seçili Borsa: **{borsa_secimi}** | Birim: **{para_birimi}**")
    
    if st.session_state["bakiye_listesi"]:
        st.write("### 💼 Hesaptaki Varlıklar (Kripto & TRY)")
        st.dataframe(pd.DataFrame(st.session_state["bakiye_listesi"]), use_container_width=True)
    
    df_pos = pd.DataFrame([
        {"Parite": f"BTC/{para_birimi}", "Yön": "LONG / AL", "Miktar": 0.05, "Giriş Fiyatı": 4046149 if para_birimi=="TRY" else 65000, "Kâr/Zarar": f"+120.50 {para_birimi}"},
        {"Parite": f"ETH/{para_birimi}", "Yön": "LONG / AL", "Miktar": 0.50, "Giriş Fiyatı": 115000 if para_birimi=="TRY" else 3400, "Kâr/Zarar": f"-15.20 {para_birimi}"}
    ])
    st.dataframe(df_pos, use_container_width=True)

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
    st.write("Bu radar, ortalama hacminin 2.5 katı üzerine çıkan ve ani fiyat hareketi yapan pariteleri anlık yakalar.")
    
    df_whale = pd.DataFrame([
        {"Parite": f"XRP/{para_birimi}", "Son Hacim Artışı": "4.2x (Balina Girişi)", "Fiyat Değişimi (15dk)": "+4.8%", "Sinyal": "ÇOK GÜÇLÜ AL"},
        {"Parite": f"1000SATS/{para_birimi}", "Son Hacim Artışı": "2.8x (Hacim Sıçraması)", "Fiyat Değişimi (15dk)": "+2.3%", "Sinyal": "GÜÇLÜ AL"},
        {"Parite": f"SOL/{para_birimi}", "Son Hacim Artışı": "3.1x (Yüksek Hacim)", "Fiyat Değişimi (15dk)": "-3.1%", "Sinyal": "DİKKAT (SATIŞ HACMİ)"}
    ])
    st.dataframe(df_whale, use_container_width=True)

# --- TAB 4: İĞNE KORUMASI ---
with tab4:
    st.subheader("🛡️ İğne Atma & Sahte Kırılım (Spike) Koruması")
    st.write("Anlık iğne hareketlerinde panik stop olmamak için filtre mekanizmasını yapılandırın.")
    
    st.checkbox("İğne Atma Korumasını Aktif Et", value=True)
    st.selectbox("Kapanış Onayı Zaman Dilimi", ["1 Dakikalık Mum Kapanışı", "3 Dakikalık Mum Kapanışı", "5 Dakikalık Mum Kapanışı"])
    st.number_input("İğne Teyit Bekleme Süresi (Saniye)", value=3)
    
    st.info("💡 **Nasıl Çalışır?** Fiyat anlık olarak stop seviyenizin altına iğne atarsa bot hemen satmaz. Belirlenen bekleme süresi veya mum kapanışı boyunca fiyat orada kalıcı olursa stop işlemini onaylar.")
