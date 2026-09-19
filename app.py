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
    page_title="Apportafolio | Tactical HUD",
    page_icon="🎯",
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
# APP PRINCIPAL (ESTILO D: HUD CINEMÁTICO)
# ==========================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Mono:wght@400;700&display=swap');

/* Fondo Negro con Grid Táctico (Cuadrícula fina) */
[data-testid="stAppViewContainer"], .stApp { 
    background-color: #050505 !important; 
    background-image: 
        linear-gradient(rgba(255, 215, 0, 0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 215, 0, 0.04) 1px, transparent 1px) !important;
    background-size: 40px 40px !important;
    font-family: 'Space Mono', monospace !important; 
    color: #ffffff;
}
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Estilo de Pestañas: Consola Militar */
div[data-testid="stTabs"] button {
    background-color: transparent !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 0px !important;
    color: #71717a !important;
    padding: 8px 16px !important;
    font-family: 'Space Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 0.8rem !important;
    margin-right: 8px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    transition: all 0.2s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    background-color: rgba(255, 51, 102, 0.1) !important;
    border: 1px solid #ff3366 !important; /* Acento Rojo Neón */
    color: #ffffff !important;
    box-shadow: inset 0 0 10px rgba(255,51,102,0.2) !important;
}

/* Tarjetas HUD: Cuadradas, transparentes, con esquinas marcadas */
.m-card {
    background: rgba(5, 5, 5, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0px;
    padding: 25px 20px;
    margin-bottom: 20px;
    position: relative;
    box-shadow: 0 15px 30px rgba(0,0,0,0.9);
}
/* Esquinas de mira (Crosshairs) */
.m-card::before {
    content: ''; position: absolute; top: -1px; left: -1px; width: 12px; height: 12px;
    border-top: 2px solid #ffd700; border-left: 2px solid #ffd700; /* Oro HUD */
}
.m-card::after {
    content: ''; position: absolute; bottom: -1px; right: -1px; width: 12px; height: 12px;
    border-bottom: 2px solid #ffd700; border-right: 2px solid #ffd700;
}

.m-title { color: #a1a1aa; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 3px; margin-bottom: 5px; font-family: 'Space Mono', monospace;}
.m-val { font-family: 'Bebas Neue', sans-serif; font-size: 3.5rem; color: #ffffff; letter-spacing: 1.5px; line-height: 0.95; margin: 10px 0;}
.m-sub { font-size: 0.7rem; font-weight: 400; color: #71717a; text-transform: uppercase; letter-spacing: 1px; font-family: 'Space Mono', monospace;}

/* Colores Neón Táctico */
.c-grn { color: #00ff88; text-shadow: 0 0 10px rgba(0,255,136,0.3); } 
.c-red { color: #ff3366; text-shadow: 0 0 10px rgba(255,51,102,0.3); } 
.c-gld { color: #ffd700; } 
</style>
""", unsafe_allow_html=True)

# SIDEBAR TÁCTICO
st.sidebar.markdown("**ID:** `ALEX_ADMIN`")
if st.sidebar.button("CERRAR SESIÓN", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

# DATOS DUMMY
tot_portafolio = 1250430.50
liquidez_mxn = 45000.00
pnl_glob = 120500.20
ret_glob = 15.4
salario_inv = 18400.00

# TICKER TAPE (Banda Inferior estilo Película)
t_html = "<marquee behavior='scroll' direction='left' scrollamount='6' style='font-family: \"Space Mono\", monospace; font-size: 0.75rem; padding: 10px; color:#a1a1aa; font-weight:700; text-transform: uppercase; letter-spacing: 2px;'>"
t_html += f"SYS_DATA FEED: <span style='color:#ffd700;'>[ ACTIVO ]</span> &nbsp;&nbsp;//&nbsp;&nbsp; SPX: <span style='color:#ffffff;'>5120.40</span> <span style='color:#00ff88;'>(+1.2%)</span> &nbsp;&nbsp;//&nbsp;&nbsp; NDX: <span style='color:#ffffff;'>16200.10</span> <span style='color:#00ff88;'>(+1.5%)</span> &nbsp;&nbsp;//&nbsp;&nbsp; USD/MXN: <span style='color:#ffffff;'>17.05</span> <span style='color:#ff3366;'>(-0.4%)</span> &nbsp;&nbsp;//&nbsp;&nbsp; BTC: <span style='color:#ffffff;'>68400.00</span> <span style='color:#00ff88;'>(+2.1%)</span>"
t_html += "</marquee>"
st.markdown(f"<div style='border-bottom:1px solid rgba(255,255,255,0.1); border-top:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.8); margin-bottom: 25px; margin-top:-25px;'>{t_html}</div>", unsafe_allow_html=True)

# TABS NATIVAS
tab1, tab2, tab3, tab4 = st.tabs(["[ GLOBAL ]", "[ RADAR ]", "[ RIESGO ]", "[ LOGS ]"])

with tab1:
    c_pnl = "c-grn" if pnl_glob >= 0 else "c-red"
    st.markdown(f"<div class='m-card'><div class='m-title'>CAPITAL NETO</div><div class='m-val'>${tot_portafolio:,.2f}</div><div class='m-sub c-gld'>LIQUIDEZ_DISP:${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>P&L ACUM.</div><div class='m-val {c_pnl}' style='font-size:2.4rem;'>${pnl_glob:+,.0f}</div><div class='m-sub {c_pnl}'>ROI: {ret_glob}%</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>FLUJO PASIVO</div><div class='m-val c-gld' style='font-size:2.4rem;'>${salario_inv:,.0f}</div><div class='m-sub'>YIELD ANUAL</div></div>", unsafe_allow_html=True)

    st.markdown("<p style='color:#71717a; font-size:0.65rem; text-transform:uppercase; letter-spacing:3px; margin-top:20px; font-weight:700;'>// ATRIBUCIÓN TÁCTICA</p>", unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    ch1.markdown(f"<div class='m-card' style='border-color:rgba(0,255,136,0.3);'><div class='m-title c-grn'>TOP MOVER</div><div class='m-val' style='font-size:2.2rem;'>NVDA</div><div class='m-sub c-grn'>+ $35,200.00</div></div>", unsafe_allow_html=True)
    ch2.markdown(f"<div class='m-card' style='border-color:rgba(255,51,102,0.3);'><div class='m-title c-red'>UNDERPERFORMER</div><div class='m-val' style='font-size:2.2rem;'>TSLA</div><div class='m-sub c-red'>- $4,100.00</div></div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<p style='color:#71717a; font-size:0.65rem; text-transform:uppercase; letter-spacing:3px; margin-top:10px; font-weight:700;'>// ALGORITMO V5</p>", unsafe_allow_html=True)
    sel_as = st.selectbox("IDENTIFICADOR DE ACTIVO:", ["AAPL", "MSFT", "VOO", "BTC"], label_visibility="collapsed")
    st.markdown(f"<div class='m-card' style='border-left: 4px solid #00ff88;'><div class='m-title'>STATUS: {sel_as}</div><div class='m-val c-grn' style='font-size:2.8rem;'>ZONA DE COMPRA <span style='font-size:1.2rem; color:#71717a; font-family:\"Space Mono\";'>(8/10)</span></div><div class='m-sub' style='color:#d4d4d8; margin-top:10px; line-height: 1.5; text-transform:none;'>Valuación detectada por debajo de la media móvil 200. Riesgo asimétrico favorable para acumulación táctica.</div></div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<p style='color:#71717a; font-size:0.65rem; text-transform:uppercase; letter-spacing:3px; margin-top:10px; font-weight:700;'>// MATRIZ DE RIESGO</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>VOLATILIDAD (BETA)</div><div class='m-val c-gld' style='font-size:2.5rem;'>0.85</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>MAX DD. (VaR)</div><div class='m-val c-red' style='font-size:2.5rem;'>$24K</div></div>", unsafe_allow_html=True)

with tab4:
    st.markdown("<p style='color:#71717a; font-size:0.65rem; text-transform:uppercase; letter-spacing:3px; margin-top:10px; font-weight:700;'>// HISTORIAL DE EJECUCIÓN</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-card' style='padding:20px;'><div class='m-sub' style='text-transform:none; line-height:1.8; color:#a1a1aa;'>> [24-MAR 10:15] <span style='color:#ffffff;'>EJECUCIÓN: COMPRA VOO</span> <span style='color:#ff3366;'>(-$6,933)</span><br>> [23-MAR 09:00] <span style='color:#ffffff;'>COBRO: DIV. FIBRAMQ</span> <span style='color:#00ff88;'>(+$1,200)</span><br>> [20-MAR 14:30] <span style='color:#ffffff;'>FONDEO: TESORERIA</span> <span style='color:#00ff88;'>(+$10,000)</span></div></div>", unsafe_allow_html=True)
