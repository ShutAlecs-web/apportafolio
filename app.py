import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import psycopg2 
import hashlib
from datetime import datetime
import json
import re

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Terminal Apportafolio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Escudo Anti-Hackeos Básicos
def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

@st.cache_data(ttl=300, max_entries=50)
def get_live_usd():
    try: return float(yf.Ticker("MXN=X").fast_info.last_price)
    except: return 19.50

live_usd_rate = get_live_usd()

# BASE DE DATOS MOCK/LOCAL PARA PRUEBA DE INTERFAZ
def get_connection(): return psycopg2.connect(st.secrets["DATABASE_URL"])
def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_connection()
    conn.autocommit = True 
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);")
    try: admin_pwd = st.secrets["admin_password"]
    except: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
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
# APP PRINCIPAL (ESTILO A: BLOOMBERG TERMINAL)
# ==========================================

# CSS GLOBAL HARDCORE QUANT
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');

/* Fondo negro absoluto y tipografía de programación */
[data-testid="stAppViewContainer"], .stApp { 
    background-color: #000000 !important; 
    font-family: 'JetBrains Mono', monospace !important; 
    color: #d4d4d8;
}
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Estilo de Pestañas: Cuadradas, bordes duros, contraste Ámbar */
div[data-testid="stTabs"] button {
    border-radius: 0px !important;
    background-color: transparent !important;
    border: 1px solid #27272a !important;
    color: #71717a !important;
    padding: 10px 20px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 0.8rem !important;
    text-transform: uppercase !important;
    margin-right: 5px !important;
    letter-spacing: 1px !important;
    transition: all 0.2s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    background-color: #f59e0b !important; /* Ámbar Bloomberg */
    border: 1px solid #f59e0b !important;
    color: #000000 !important;
}

/* Tarjetas Móviles Cuadradas (Zero Radius) */
.m-card {
    background: #000000;
    border: 1px solid #27272a;
    border-radius: 0px;
    padding: 20px;
    margin-bottom: 15px;
    transition: border-color 0.2s;
}
.m-card:hover { border-color: #f59e0b; }
.m-title { color: #a1a1aa; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; font-weight: 700;}
.m-val { font-size: 1.6rem; font-weight: 800; color: #ffffff; line-height: 1.2; }
.m-sub { font-size: 0.75rem; margin-top: 8px; font-weight: 400; color: #71717a; text-transform: uppercase;}

/* Colores de Terminal */
.c-grn { color: #10b981; } /* Verde Terminal */
.c-red { color: #ef4444; } /* Rojo Terminal */
.c-amb { color: #f59e0b; } /* Ámbar */
</style>
""", unsafe_allow_html=True)

# SIDEBAR TÁCTICO
st.sidebar.markdown("**USER:** `ALEX_ADMIN`")
if st.sidebar.button("LOGOUT", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

# DATOS DUMMY PARA MOSTRAR UI RÁPIDO
tot_portafolio = 1250430.50
liquidez_mxn = 45000.00
pnl_glob = 120500.20
ret_glob = 15.4
salario_inv = 18400.00

# TICKER TAPE (ESTILO BLOOMBERG)
t_html = "<marquee behavior='scroll' direction='left' scrollamount='6' style='font-family: \"JetBrains Mono\", monospace; font-size: 0.8rem; padding: 10px 0; color:#f59e0b; font-weight:bold;'>"
t_html += f"SYS_MSG: ALGORITMO V5 ONLINE &nbsp;|&nbsp; S&P 500: <span style='color:#ffffff;'>5,120.40</span> <span style='color:#10b981;'>(+1.2%)</span> &nbsp;|&nbsp; NASDAQ: <span style='color:#ffffff;'>16,200.10</span> <span style='color:#10b981;'>(+1.5%)</span> &nbsp;|&nbsp; USD/MXN: <span style='color:#ffffff;'>17.05</span> <span style='color:#ef4444;'>(-0.4%)</span> &nbsp;|&nbsp; BTC/USD: <span style='color:#ffffff;'>$68,400</span> <span style='color:#10b981;'>(+2.1%)</span>"
t_html += "</marquee>"
st.markdown(f"<div style='border-top:1px solid #27272a; border-bottom:1px solid #27272a; background:#000000; margin-bottom: 25px; margin-top:-30px;'>{t_html}</div>", unsafe_allow_html=True)

# TABS NATIVAS
tab1, tab2, tab3, tab4 = st.tabs(["[ PORTAFOLIO ]", "[ RADAR_V5 ]", "[ RIESGO ]", "[ SYS_LOGS ]"])

with tab1:
    st.markdown("<p style='color:#71717a; font-size:0.7rem; text-transform:uppercase; margin-bottom:5px;'>-- METRICAS GLOBALES --</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>CAPITAL TOTAL</div><div class='m-val'>${tot_portafolio:,.0f}</div><div class='m-sub c-amb'>LIQUIDEZ:${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    c_pnl = "c-grn" if pnl_glob >= 0 else "c-red"
    c2.markdown(f"<div class='m-card'><div class='m-title'>P&L NETA</div><div class='m-val {c_pnl}'>${pnl_glob:+,.0f}</div><div class='m-sub {c_pnl}'>ROI: {ret_glob:+.2f}%</div></div>", unsafe_allow_html=True)

    st.markdown("<p style='color:#71717a; font-size:0.7rem; text-transform:uppercase; margin-top:15px; margin-bottom:5px;'>-- ANALISIS DE FLUJO --</p>", unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    ch1.markdown(f"<div class='m-card'><div class='m-title c-amb'>YIELD ANUAL (EST)</div><div class='m-val'>${salario_inv:,.0f}</div><div class='m-sub'>CASHFLOW PROYECTADO</div></div>", unsafe_allow_html=True)
    ch2.markdown(f"<div class='m-card'><div class='m-title c-grn'>TOP GAINER</div><div class='m-val'>NVDA</div><div class='m-sub c-grn'>+ $35,200 MXN</div></div>", unsafe_allow_html=True)
    
    st.markdown(f"<div class='m-card' style='text-align:center;'><div class='m-title c-red'>UNDERPERFORMER</div><div class='m-val'>TSLA</div><div class='m-sub c-red'>- $4,100 MXN</div></div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<p style='color:#71717a; font-size:0.7rem; text-transform:uppercase; margin-bottom:5px;'>-- SCANNER DE ACTIVOS --</p>", unsafe_allow_html=True)
    sel_as = st.selectbox("TICKER:", ["AAPL", "MSFT", "VOO", "BTC-USD"], label_visibility="collapsed")
    st.markdown(f"<div class='m-card' style='border-color:#10b981;'><div class='m-title'>VEREDICTO ALG V5: {sel_as}</div><div style='color:#10b981; font-size:1.6rem; font-weight:800;'>ZONA DE COMPRA <span style='font-size:1rem; color:#71717a;'>[8/10]</span></div><div class='m-sub'>VALUACION ATRACTIVA FRENTE A MEDIA MOVIL 200 DIAS.</div></div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<p style='color:#71717a; font-size:0.7rem; text-transform:uppercase; margin-bottom:5px;'>-- PARAMETROS DE RIESGO --</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>BETA</div><div class='m-val c-amb'>0.85</div><div class='m-sub'>VS S&P 500</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>VaR 95%</div><div class='m-val c-red'>$24,000</div><div class='m-sub'>MAX DRAWDOWN DIR.</div></div>", unsafe_allow_html=True)

with tab4:
    st.markdown("<p style='color:#71717a; font-size:0.7rem; text-transform:uppercase; margin-bottom:5px;'>-- SYSTEM LOGS --</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-card'><div class='m-sub'>[2024-03-24 10:15:22] > COMPRA EJECUTADA: 15.4 VOO @ $450.20<br>[2024-03-23 14:02:11] > DIVIDENDO RECIBIDO: FIBRAMQ @ $1,200.00<br>[2024-03-20 09:30:00] > DEPOSITO TESORERIA: $10,000.00</div></div>", unsafe_allow_html=True)
