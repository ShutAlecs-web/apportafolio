import streamlit as st
import pandas as pd
import yfinance as yf
import psycopg2 
import hashlib
from datetime import datetime
import os
import re

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Apportafolio | Fintech",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

# BASE DE DATOS MOCK/LOCAL
def get_connection(): return psycopg2.connect(st.secrets["DATABASE_URL"])
def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_connection(); conn.autocommit = True; cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);")
    try: admin_pwd = st.secrets["admin_password"]
    except: admin_pwd = "clave_temporal_local"
    cur.execute("INSERT INTO users (user_id, username, password_hash) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING", ("USR-001", "alex_admin", hash_password(admin_pwd)))
    cur.close(); conn.close()

init_db()

if "user_id" not in st.session_state: st.session_state["user_id"] = None

# ==========================================
# PORTADA 5.1: STEALTH MODE CORREGIDA (INTACTA)
# ==========================================
if st.session_state["user_id"] is None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@100;300;400&display=swap');
    [data-testid="stAppViewContainer"], .stApp { background-color: #000000 !important; background-image: none !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    .stealth-title { font-family: 'JetBrains Mono', monospace; font-weight: 100; font-size: 2.2rem; color: #ffffff; letter-spacing: 10px; text-align: center; text-transform: uppercase; margin-bottom: 5px; white-space: nowrap; }
    .stealth-subtitle { font-family: 'JetBrains Mono', monospace; font-weight: 300; font-size: 0.7rem; color: #4b5563; text-align: center; letter-spacing: 6px; text-transform: uppercase; margin-bottom: 80px; }
    [data-testid="stForm"] { background: transparent !important; border: none !important; box-shadow: none !important; padding: 2rem !important; }
    [data-testid="stForm"] label { display: none !important; }
    [data-testid="stForm"] input { background: transparent !important; border: none !important; border-bottom: 1px solid #1f2937 !important; color: #ffffff !important; border-radius: 0 !important; font-family: 'JetBrains Mono', monospace !important; font-weight: 300 !important; padding: 1rem 0 !important; font-size: 0.9rem !important; transition: border-color 0.5s ease !important; text-align: center; }
    [data-testid="stForm"] input::placeholder { color: #374151 !important; text-align: center; letter-spacing: 2px;}
    [data-testid="stForm"] input:focus { border-bottom: 1px solid #ffffff !important; box-shadow: none !important; outline: none !important; background: transparent !important; }
    [data-testid="stFormSubmitButton"] button { background: transparent !important; color: #4b5563 !important; font-weight: 300 !important; font-family: 'JetBrains Mono', monospace !important; border: 1px solid #1f2937 !important; border-radius: 0 !important; padding: 0.8rem !important; margin-top: 50px !important; letter-spacing: 5px !important; text-transform: uppercase !important; width: 100%; transition: all 0.5s ease !important; }
    [data-testid="stFormSubmitButton"] button:hover { color: #ffffff !important; border-color: #ffffff !important; }
    </style>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.5, 2.5, 0.5])
    with c2:
        st.markdown("<br><br><br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 class='stealth-title'>APPORTAFOLIO</h1>", unsafe_allow_html=True)
        st.markdown("<p class='stealth-subtitle'>Exclusivo y personalizado para ti.</p>", unsafe_allow_html=True)
        with st.form("login_form"):
            usr = st.text_input("Usuario", placeholder="IDENTIFICADOR")
            pwd = st.text_input("Contraseña", type="password", placeholder="CLAVE DE ACCESO")
            if st.form_submit_button("INGRESAR", use_container_width=True):
                conn = get_connection(); cur = conn.cursor()
                cur.execute("SELECT user_id FROM users WHERE username=%s AND password_hash=%s", (usr, hash_password(pwd)))
                user = cur.fetchone()
                cur.close(); conn.close()
                if user: st.session_state["user_id"] = user[0]; st.rerun()
                else: st.error("Acceso denegado.")
    st.stop()


# ==========================================
# APP PRINCIPAL (ESTILO C: NEO-BRÓKER / FINTECH)
# ==========================================

# CSS GLOBAL IOS/ROBINHOOD VIBE
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

/* Fondo Negro y tipografía Inter limpia */
[data-testid="stAppViewContainer"], .stApp { 
    background-color: #000000 !important; 
    font-family: 'Inter', sans-serif !important; 
    color: #ffffff;
}
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Estilo de Pestañas: Pastillas iOS Segmented Control */
div[data-testid="stTabs"] button {
    background-color: #1c1c1e !important;
    border-radius: 20px !important;
    border: none !important;
    color: #8e8e93 !important;
    padding: 8px 18px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    margin-right: 10px !important;
    transition: all 0.2s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    background-color: #2c2c2e !important;
    color: #ffffff !important;
    box-shadow: 0 4px 10px rgba(0,0,0,0.5) !important;
}

/* Tarjetas Móviles: Estilo Apple Wallet (Redondeadas y Suaves) */
.m-card {
    background: #1c1c1e;
    border-radius: 24px;
    padding: 24px;
    margin-bottom: 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.m-title { color: #8e8e93; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;}
.m-val { font-size: 2.6rem; font-weight: 800; color: #ffffff; letter-spacing: -1.5px; line-height: 1.1; }
.m-sub { font-size: 0.95rem; margin-top: 8px; font-weight: 600; color: #8e8e93;}

/* Colores iOS (Menta, Coral, Azul) */
.c-grn { color: #30d158; } 
.c-red { color: #ff453a; } 
.c-blu { color: #0a84ff; } 
.c-pur { color: #bf5af2; }
</style>
""", unsafe_allow_html=True)

# SIDEBAR TÁCTICO
st.sidebar.markdown("**HOLA, ALEX** 👋")
if st.sidebar.button("Cerrar Sesión", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

# DATOS DUMMY
tot_portafolio = 1250430.50
liquidez_mxn = 45000.00
pnl_glob = 120500.20
ret_glob = 15.4
salario_inv = 18400.00

# TICKER TAPE (Burbuja Flotante)
t_html = "<marquee behavior='scroll' direction='left' scrollamount='5' style='font-family: \"Inter\", sans-serif; font-size: 0.9rem; padding: 12px 20px; color:#8e8e93; font-weight:600;'>"
t_html += f"S&P 500: <span style='color:#ffffff;'>5,120</span> <span style='color:#30d158;'>(+1.2%)</span> &nbsp;&nbsp;🔥&nbsp;&nbsp; NASDAQ: <span style='color:#ffffff;'>16,200</span> <span style='color:#30d158;'>(+1.5%)</span> &nbsp;&nbsp;🚀&nbsp;&nbsp; USD/MXN: <span style='color:#ffffff;'>17.05</span> <span style='color:#ff453a;'>(-0.4%)</span> &nbsp;&nbsp;💎&nbsp;&nbsp; BTC: <span style='color:#ffffff;'>$68K</span> <span style='color:#30d158;'>(+2.1%)</span>"
t_html += "</marquee>"
st.markdown(f"<div style='background:#1c1c1e; border-radius:30px; margin-bottom: 25px; margin-top:-20px;'>{t_html}</div>", unsafe_allow_html=True)

# TABS NATIVAS
tab1, tab2, tab3, tab4 = st.tabs(["Cartera", "Radar V5", "Riesgo", "Historial"])

with tab1:
    # Tarjeta Principal Gigante
    c_pnl = "c-grn" if pnl_glob >= 0 else "c-red"
    st.markdown(f"<div class='m-card' style='text-align:center;'><div class='m-title'>Balance Total</div><div class='m-val'>${tot_portafolio:,.2f}</div><div class='m-sub {c_pnl}'>+${pnl_glob:,.0f} ({ret_glob}%) Todo el tiempo</div></div>", unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Poder de Compra</div><div class='m-val' style='font-size:1.8rem;'>${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>Ingreso Pasivo</div><div class='m-val c-blu' style='font-size:1.8rem;'>${salario_inv:,.0f}</div></div>", unsafe_allow_html=True)

    st.markdown("<h4 style='color:#ffffff; font-size:1.1rem; margin-top:20px; margin-bottom:15px; font-weight:800;'>Tus Movimientos ⚡</h4>", unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    ch1.markdown(f"<div class='m-card'><div class='m-title c-grn'>Top Activo</div><div class='m-val' style='font-size:1.5rem;'>NVDA</div><div class='m-sub c-grn'>+$35,200</div></div>", unsafe_allow_html=True)
    ch2.markdown(f"<div class='m-card'><div class='m-title c-red'>A la baja</div><div class='m-val' style='font-size:1.5rem;'>TSLA</div><div class='m-sub c-red'>-$4,100</div></div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<h4 style='color:#ffffff; font-size:1.1rem; margin-top:10px; margin-bottom:15px; font-weight:800;'>Inteligencia Artificial</h4>", unsafe_allow_html=True)
    sel_as = st.selectbox("Selecciona un activo para analizar:", ["Apple (AAPL)", "Microsoft (MSFT)", "S&P 500 (VOO)"], label_visibility="collapsed")
    st.markdown(f"<div class='m-card'><div class='m-title'>Veredicto: {sel_as}</div><div class='m-val c-blu' style='font-size:2rem;'>ZONA DE COMPRA <span style='font-size:1.2rem; color:#8e8e93;'>(8/10)</span></div><div class='m-sub' style='color:#ffffff; margin-top:15px;'>El activo presenta una valuación atractiva frente a su media móvil de 200 días. Sugerimos hacer DCA agresivo.</div></div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<h4 style='color:#ffffff; font-size:1.1rem; margin-top:10px; margin-bottom:15px; font-weight:800;'>Salud del Portafolio</h4>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Volatilidad</div><div class='m-val c-pur' style='font-size:1.8rem;'>0.85 Beta</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>Max Riesgo Diario</div><div class='m-val c-red' style='font-size:1.8rem;'>$24,000 VaR</div></div>", unsafe_allow_html=True)

with tab4:
    st.markdown("<h4 style='color:#ffffff; font-size:1.1rem; margin-top:10px; margin-bottom:15px; font-weight:800;'>Actividad Reciente</h4>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-card' style='padding:15px 24px;'><div style='display:flex; justify-content:space-between;'><div style='font-weight:600; color:#ffffff;'>Compra VOO</div><div class='c-red'>-$6,933.00</div></div><div class='m-sub'>Ayer</div></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-card' style='padding:15px 24px;'><div style='display:flex; justify-content:space-between;'><div style='font-weight:600; color:#ffffff;'>Dividendo FIBRAMQ</div><div class='c-grn'>+$1,200.00</div></div><div class='m-sub'>Hace 2 días</div></div>", unsafe_allow_html=True)
