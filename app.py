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
    page_title="Apportafolio | Private Wealth",
    page_icon="🗝️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Escudo Anti-Hackeos
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
# APP PRINCIPAL (ESTILO B: SWISS FAMILY OFFICE)
# ==========================================

# CSS GLOBAL OLD MONEY
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500&display=swap');

/* Fondo Azul Medianoche Profundo y Tipografía Editorial */
[data-testid="stAppViewContainer"], .stApp { 
    background-color: #050811 !important; 
    font-family: 'Inter', sans-serif !important; 
    color: #cbd5e1;
}
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Estilo de Pestañas: Minimalistas, sin botones, línea dorada */
div[data-testid="stTabs"] button {
    background-color: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    color: #64748b !important;
    padding: 10px 15px !important;
    font-family: 'Playfair Display', serif !important;
    font-size: 1.1rem !important;
    letter-spacing: 1px !important;
    margin-right: 15px !important;
    transition: all 0.3s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    border-bottom: 2px solid #d4af37 !important; /* Oro Pálido */
    color: #d4af37 !important;
    font-style: italic;
}

/* Tarjetas Móviles: Estilo Reporte Impreso (Sin cajas, solo divisores finos) */
.m-card {
    background: transparent;
    border-top: 1px solid rgba(212, 175, 55, 0.25);
    border-bottom: 1px solid transparent;
    padding: 22px 10px;
    margin-bottom: 5px;
    transition: background 0.3s ease;
}
.m-card:hover { background: rgba(255,255,255,0.01); }
.m-title { 
    font-family: 'Inter', sans-serif; 
    color: #94a3b8; 
    font-size: 0.75rem; 
    text-transform: uppercase; 
    letter-spacing: 3px; 
    margin-bottom: 10px; 
    font-weight: 400;
}
.m-val { 
    font-family: 'Playfair Display', serif; 
    font-size: 2.2rem; 
    font-weight: 400; 
    color: #ffffff; 
    line-height: 1.1; 
}
.m-sub { 
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem; 
    margin-top: 8px; 
    font-weight: 300; 
    color: #64748b; 
}

/* Colores Sutiles y Elegantes */
.c-grn { color: #34d399; } /* Verde Esmeralda Suave */
.c-red { color: #fb7185; } /* Rojo Rosado/Burdeos */
.c-gld { color: #d4af37; } /* Oro Clásico */
</style>
""", unsafe_allow_html=True)

# SIDEBAR TÁCTICO
st.sidebar.markdown("<p style='font-family:\"Playfair Display\"; color:#d4af37; font-size:1.2rem; font-style:italic;'>ALEX_ADMIN</p>", unsafe_allow_html=True)
if st.sidebar.button("Cerrar Sesión", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

# DATOS DUMMY
tot_portafolio = 1250430.50
liquidez_mxn = 45000.00
pnl_glob = 120500.20
ret_glob = 15.4
salario_inv = 18400.00

# TICKER TAPE (ESTILO NOTICIERO FINANCIERO CLÁSICO)
t_html = "<marquee behavior='scroll' direction='left' scrollamount='5' style='font-family: \"Inter\", sans-serif; font-size: 0.85rem; padding: 12px 0; color:#64748b; font-weight:300; letter-spacing: 1px;'>"
t_html += f"COTIZACIONES DEL DÍA &nbsp;&nbsp;|&nbsp;&nbsp; S&P 500: <span style='color:#ffffff;'>5,120.40</span> <span style='color:#34d399;'>(+1.2%)</span> &nbsp;&nbsp;|&nbsp;&nbsp; NASDAQ: <span style='color:#ffffff;'>16,200.10</span> <span style='color:#34d399;'>(+1.5%)</span> &nbsp;&nbsp;|&nbsp;&nbsp; USD/MXN: <span style='color:#ffffff;'>17.05</span> <span style='color:#fb7185;'>(-0.4%)</span> &nbsp;&nbsp;|&nbsp;&nbsp; ORO: <span style='color:#ffffff;'>$2,150</span> <span style='color:#34d399;'>(+0.8%)</span>"
t_html += "</marquee>"
st.markdown(f"<div style='border-bottom:1px solid rgba(212,175,55,0.2); background:transparent; margin-bottom: 25px; margin-top:-30px;'>{t_html}</div>", unsafe_allow_html=True)

# TABS NATIVAS
tab1, tab2, tab3, tab4 = st.tabs(["Resumen Patrimonial", "Análisis Táctico", "Gestión de Riesgo", "Tesoreria"])

with tab1:
    st.markdown("<p style='color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; margin-bottom:5px; margin-top:10px;'>Posición Global</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Patrimonio Líquido</div><div class='m-val'>${tot_portafolio:,.0f}</div><div class='m-sub c-gld'>Efectivo: ${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    c_pnl = "c-grn" if pnl_glob >= 0 else "c-red"
    c2.markdown(f"<div class='m-card'><div class='m-title'>Rendimiento Histórico</div><div class='m-val {c_pnl}'>${pnl_glob:+,.0f}</div><div class='m-sub {c_pnl}'>{ret_glob:+.2f}% Neto Acumulado</div></div>", unsafe_allow_html=True)

    st.markdown("<p style='color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; margin-top:25px; margin-bottom:5px;'>Desempeño Destacado</p>", unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    ch1.markdown(f"<div class='m-card'><div class='m-title c-gld'>Rendimiento por Dividendo</div><div class='m-val'>${salario_inv:,.0f}</div><div class='m-sub'>Ingreso Pasivo Anualizado</div></div>", unsafe_allow_html=True)
    ch2.markdown(f"<div class='m-card'><div class='m-title c-grn'>Mayor Plusvalía</div><div class='m-val'>NVIDIA Corp.</div><div class='m-sub c-grn'>+ $35,200 MXN</div></div>", unsafe_allow_html=True)
    
    st.markdown(f"<div class='m-card' style='text-align:center; border-bottom:1px solid rgba(212, 175, 55, 0.25);'><div class='m-title c-red'>Corrección Actual</div><div class='m-val'>Tesla Inc.</div><div class='m-sub c-red'>- $4,100 MXN (No Realizado)</div></div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<p style='color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; margin-bottom:15px; margin-top:10px;'>Motor de Inteligencia Artificial</p>", unsafe_allow_html=True)
    sel_as = st.selectbox("Seleccione un instrumento:", ["Apple Inc. (AAPL)", "Microsoft Corp. (MSFT)", "Vanguard S&P 500 (VOO)"], label_visibility="collapsed")
    st.markdown(f"<div class='m-card' style='border-top: 1px solid #34d399;'><div class='m-title'>Veredicto Estructural: {sel_as}</div><div style='color:#34d399; font-family:\"Playfair Display\", serif; font-size:2rem; font-style:italic;'>Zona de Compra <span style='font-size:1.2rem; color:#64748b; font-family:\"Inter\", sans-serif;'>(8/10)</span></div><div class='m-sub' style='line-height:1.6;'>Valuación excepcionalmente atractiva frente a su media móvil de 200 días. Se sugiere acumulación gradual.</div></div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<p style='color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; margin-bottom:5px; margin-top:10px;'>Métricas Cuantitativas</p>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Volatilidad (Beta)</div><div class='m-val c-gld'>0.85</div><div class='m-sub'>Comparativa vs S&P 500</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title'>Exposición Diaria (VaR)</div><div class='m-val c-red'>$24,000</div><div class='m-sub'>Pérdida máxima esperada al 95%</div></div>", unsafe_allow_html=True)

with tab4:
    st.markdown("<p style='color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; margin-bottom:5px; margin-top:10px;'>Libro de Operaciones</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='m-card' style='border-bottom:1px solid rgba(212, 175, 55, 0.25);'><div class='m-sub' style='line-height:1.8;'><span style='color:#d4af37;'>24 Mar 2024</span> &nbsp;&nbsp; Adquisición Estratégica: 15.4 VOO @ $450.20<br><span style='color:#d4af37;'>23 Mar 2024</span> &nbsp;&nbsp; Flujo de Capital (Dividendo): FIBRAMQ @ $1,200.00<br><span style='color:#d4af37;'>20 Mar 2024</span> &nbsp;&nbsp; Inyección a Tesorería: $10,000.00 MXN</div></div>", unsafe_allow_html=True)
