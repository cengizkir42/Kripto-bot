import streamlit as st
import pandas as pd

# Sayfa Genişliği ve Başlık
st.set_page_config(page_title="CEX T1 - Vadeli İşlemler Botu", layout="wide")

# Özel Koyu Tema CSS Tasarımı
st.markdown("""
    <style>
        .stApp { background-color: #0b0e14; color: #ffffff; }
        div[data-testid="stMetricValue"] { color: #00f2fe; font-weight: bold; }
        .stButton>button { background-color: #0052ff; color: white; border-radius: 6px; font-weight: bold; width: 100%; }
        .stSelectbox label, .stTextInput label, .stNumberInput label { color: #848e9c !important; }
    </style>
""", unsafe_allow_html=True)

# --- SOL PANEL (Borsa Bağlantısı & Bot Kontrolü) ---
with st.sidebar:
    st.title("CEX T1")
    st.caption("VADELİ İŞLEMLER • CANLI HESAP")
    
    st.subheader("BORSA VE BAĞLANTI")
    exchange = st.selectbox("Borsa", ["Binance USDT-M", "OKX", "Bybit"])
    api_key = st.text_input("Erişim Anahtarı (API Key)", type="password")
    secret_key = st.text_input("Gizli Anahtar (Secret Key)", type="password")
    st.button("Bağlantıyı Kur")
    
    st.divider()
    
    st.subheader("BOT KONTROLÜ")
    if st.button("▶ BOTU BAŞLAT"):
        st.success("Bot Aktif!")
    if st.button("⏸ Yeni Girişleri Durdur"):
        st.warning("Yeni girişler durduruldu.")
    
    # Acil Durum Butonu
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚨 ACİL - TÜM POZİSYONLARI KAPAT"):
        st.error("Tüm pozisyonlar kapatılıyor!")

# --- SAĞ PANEL (Metrikler ve Sekmeler) ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Toplam Hesap Değeri", "193.77 USDT")
col2.metric("Kullanılabilir Teminat", "193.77 USDT")
col3.metric("Kâr / Zarar %", "+0.00%")
col4.metric("Sıfırlamadan Beri Değişim", "+0.00 USDT")

st.divider()

# Sekme Yapısı
tab1, tab2, tab3 = st.tabs(["📊 Genel Bakış", "⚙️ Strateji ve Risk", "📈 Göstergeler / Sinyaller"])

with tab1:
    st.write("### Açık Pozisyonlar")
    df_positions = pd.DataFrame({
        "Parite": ["BNB/USDT", "BOME/USDT"],
        "Yön": ["LONG", "SHORT"],
        "Miktar": [0.5, 1200],
        "Kaldıraç": ["10x", "5x"],
        "Giriş Fiyatı": [580.2, 0.0095],
        "Kâr / Zarar USDT": ["+1.20 USDT", "-0.40 USDT"]
    })
    st.dataframe(df_positions, use_container_width=True)

with tab2:
    st.write("### Risk ve Strateji Parametreleri")
    col_a, col_b = st.columns(2)
    with col_a:
        st.number_input("İlk Giriş Teminat Üst Sınırı (USDT)", value=40.0)
        st.number_input("Pozisyon Başına Risk Bütçesi %", value=0.5)
        st.number_input("Kesin Zarar Kes (Stop-Loss) %", value=0.7)
        st.number_input("Zorunlu Tasfiye Koruma Mesafesi %", value=1.5)
    with col_b:
        st.number_input("İlk Kâr Al Hedefi %", value=1.0)
        st.number_input("İzleyen Zarar Kes Mesafesi %", value=0.7)
        st.number_input("Giriş Puanı Eşiği (100 Üzerinden)", value=75)
        st.number_input("Aynı Anda Açık Pozisyon Sınırı", value=2)
    
    st.button("Ayarları Kaydet ve Uygula")

with tab3:
    st.write("### Piyasa Radarı & Göstergeler")
    df_indicators = pd.DataFrame({
        "Parite": ["BNB/USDT", "BOME/USDT"],
        "Piyasa Durumu": ["Yatay", "Yatay"],
        "Yön Gücü (ADX)": [16.4, 17.3],
        "Oynaklık (ATR)": [0.223, 0.000],
        "Göreli Güç (RSI)": [50.6, 64.3]
    })
    st.dataframe(df_indicators, use_container_width=True)
