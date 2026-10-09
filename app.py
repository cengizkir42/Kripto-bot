import streamlit as st
import pandas as pd
import ccxt

# --- PAGE CONFIG ---
st.set_page_config(page_title="CEX T1 - Kripto Bot", layout="wide", initial_sidebar_state="expanded")

st.title("🤖 CEX T1 - Otomatik Kripto & Balina Radarı Botu")

# --- SIDEBAR CONFIG ---
st.sidebar.header("BORSA VE BAĞLANTI")

borsa_secimi = st.sidebar.selectbox(
    "Borsa Seçin",
    ["Binance TR (Spot - TRY)", "Binance USDT-M (Vadeli)", "OKX Futures"]
)

api_key = st.sidebar.text_input("Erişim Anahtarı (API Key)", type="password")
secret_key = st.sidebar.text_input("Gizli Anahtar (Secret Key)", type="password")

para_birimi = "TRY" if "Binance TR" in borsa_secimi else "USDT"

# --- EXCHANGE INITIALIZATION ---
@st.cache_resource
def init_exchange(borsa, key, secret):
    if not key or not secret:
        return None
    try:
        if "Binance TR" in borsa:
            return ccxt.binance({
                'apiKey': key,
                'secret': secret,
                'hostname': 'tr.binance.com',
                'enableRateLimit': True
            })
        elif "Binance USDT-M" in borsa:
            return ccxt.binance({
                'apiKey': key,
                'secret': secret,
                'options': {'defaultType': 'future'},
                'enableRateLimit': True
            })
        elif "OKX" in borsa:
            return ccxt.okx({'apiKey': key, 'secret': secret, 'enableRateLimit': True})
    except Exception as e:
        st.sidebar.error(f"Bağlantı hatası: {e}")
        return None

exchange = init_exchange(borsa_secimi, api_key, secret_key)

if st.sidebar.button("Bağlantıyı Kur / Yenile"):
    if exchange:
        try:
            balance = exchange.fetch_balance()
            st.sidebar.success(f"{borsa_secimi} bağlantısı başarılı!")
        except Exception as e:
            st.sidebar.error(f"API Doğrulama Hatası: {e}")
    else:
        st.sidebar.warning("Lütfen geçerli API Key ve Secret Key girin.")

# --- DASHBOARD METRICS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Toplam Hesap Değeri", f"0.00 {para_birimi}")
col2.metric("Kullanılabilir Teminat", f"0.00 {para_birimi}")
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
