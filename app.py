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
import io
import time
import numpy as np

# 1. CONFIGURACIÓN DE PÁGINA (Debe ser lo primero)
st.set_page_config(
    page_title="Terminal Apportafolio",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed" # Empieza cerrado en móvil para limpiar la pantalla
)

# Escudo Anti-Hackeos Básicos
def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

# PROMPT MAESTRO V5
PROMPT_MAESTRO = """
Eres el 'Motor Algorítmico V5', un analista cuantitativo de inteligencia artificial.
DATOS: Ticker: {ticker} | Precio: {current_price} | Rango: {low_52w}-{high_52w} | P/E: {pe_ratio} | EPS: {eps}
PORTAFOLIO: Costo: {avg_cost} | Retorno: {net_return_pct}% | Peso: {portfolio_weight}%
CONTEXTO: {macro_news_context}
Responde ÚNICA Y EXCLUSIVAMENTE con un objeto JSON válido:
{{ "verdict": "ZONA DE COMPRA", "rating": 8, "bull_points": ["Punto 1"], "bear_points": ["Punto 1"], "macro_synthesis": "Síntesis." }}
"""

ASSET_CLASS = {"ISAC": "ETF", "XNAS": "ETF", "XDWH": "ETF", "EIMI": "ETF", "NUCL": "ETF", "GOOGL": "Acción", "MELI": "Acción", "NOW": "Acción", "ASML": "Acción", "NVO": "Acción", "MA": "Acción", "V": "Acción", "BTC": "Cripto"}
ASSET_SECTOR = {"ISAC": "Renta Variable Global", "XNAS": "Tecnología (Índice)", "XDWH": "Salud Global", "EIMI": "Mercados Emergentes", "NUCL": "Energía/Utilities", "GOOGL": "Servicios de Comunicación", "MELI": "Comercio Electrónico", "NOW": "Software B2B", "ASML": "Semiconductores", "NVO": "Biotecnología / Salud", "MA": "Servicios Financieros", "V": "Servicios Financieros", "BTC": "Criptoactivos"}

@st.cache_data(ttl=300, max_entries=50)
def get_live_usd():
    try: return float(yf.Ticker("MXN=X").fast_info.last_price)
    except: return 19.50

live_usd_rate = get_live_usd()

# BASE DE DATOS POSTGRESQL
def get_connection(): return psycopg2.connect(st.secrets["DATABASE_URL"])
def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_connection()
    conn.autocommit = True 
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);
        CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, user_id TEXT, timestamp TEXT, fecha TEXT, tipo_operacion TEXT, ticker TEXT, clase TEXT, plataforma TEXT, moneda TEXT, titulos REAL, precio_unitario REAL, comision REAL, iva REAL, tipo_cambio REAL, total_mxn REAL);
        CREATE TABLE IF NOT EXISTS cash_movements (id TEXT PRIMARY KEY, user_id TEXT, fecha TEXT, tipo TEXT, concepto TEXT, monto_mxn REAL);
    """)
    try: cur.execute("ALTER TABLE users ADD COLUMN dca_frequency TEXT DEFAULT 'MENSUAL'")
    except: pass
    try: cur.execute("ALTER TABLE users ADD COLUMN goal_name TEXT DEFAULT 'Libertad Financiera'")
    except: pass
    try: admin_pwd = st.secrets["admin_password"]
    except: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
    cur.execute("INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", ("USR-001", "alex_admin", hash_password(admin_pwd), "MENSUAL", "Fondo Institucional"))
    cur.close()
    conn.close()

init_db()

if "user_id" not in st.session_state: st.session_state["user_id"] = None

# ==========================================
# PANTALLA DE LOGIN (CORRECCIÓN PANTALLA NEGRA)
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
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT user_id FROM users WHERE username=%s AND password_hash=%s", (usr, hash_password(pwd)))
                user = cur.fetchone()
                cur.close()
                conn.close()
                if user:
                    st.session_state["user_id"] = user[0]
                    st.rerun()
                else: st.error("Acceso denegado.")
    # EL GRAN ARREGLO: ESTE STOP AHORA ESTÁ DENTRO DEL BLOQUE 'IF USER IS NONE'
    st.stop()


# ==========================================
# APP PRINCIPAL (MOBILE-FIRST REDESIGN)
# ==========================================

# CSS GLOBAL PREMIUM MOBILE-FIRST
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Inter:wght@400;500;700&display=swap');
[data-testid="stAppViewContainer"], .stApp { background-color: #040609 !important; font-family: 'Inter', sans-serif; color: #e5e7eb;}
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Estilo de Pestañas (Tabs) Nativas estilo iOS */
div[data-testid="stTabs"] button {
    border-radius: 12px !important;
    background-color: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    color: #8b949e !important;
    padding: 12px 18px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    margin-right: 8px !important;
    transition: all 0.3s ease;
}
div[data-testid="stTabs"] button[aria-selected="true"] {
    background-color: rgba(0, 240, 255, 0.1) !important;
    border: 1px solid #00f0ff !important;
    color: #ffffff !important;
}

/* Tarjetas Móviles (Mobile Cards) */
.m-card {
    background: linear-gradient(145deg, #090c13 0%, #0d1117 100%);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    margin-bottom: 20px;
    transition: transform 0.2s;
}
.m-card:hover { border-color: rgba(255,255,255,0.1); }
.m-title { color: #8b949e; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; margin-bottom: 8px; }
.m-val { font-family: 'JetBrains Mono', monospace; font-size: 1.7rem; font-weight: 800; color: #ffffff; line-height: 1.1; }
.m-sub { font-size: 0.8rem; margin-top: 8px; font-weight: 500; color: #6b7280;}

/* Colores Neón */
.c-grn { color: #00ff88; } .c-red { color: #ff3366; } .c-cyn { color: #00f0ff; } .c-pur { color: #c084fc; } .c-gld { color: #fbbf24; }
</style>
""", unsafe_allow_html=True)

# 4. GESTIÓN DE DATOS DEL USUARIO
user_id = st.session_state["user_id"]
conn = get_connection()
all_users = pd.read_sql("SELECT user_id, username FROM users", conn)
conn.close()

if user_id == "USR-001":
    client_dict = dict(zip(all_users["username"], all_users["user_id"]))
    selected_client_name = st.sidebar.selectbox("👑 Panel Gestor | Cliente:", list(client_dict.keys()))
    active_client_id = client_dict[selected_client_name]
    active_username = selected_client_name 
else:
    active_client_id = user_id
    active_username = all_users.loc[all_users["user_id"] == user_id, "username"].values[0]

# ==========================================
# SIDEBAR (MENÚ LATERAL DE TRABAJO)
# ==========================================
st.sidebar.markdown(f"**Usuario:** `{active_username}`")
if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.toggle("🔬 Activar Modo Pro", key="modo_pro_toggle")

with st.sidebar.expander("⚙️ Perfil y Meta", expanded=False):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (user_id,))
        user_data = cur.fetchone()
        current_freq, current_goal = user_data[0], user_data[1]
    except: current_freq, current_goal = "MENSUAL", "Libertad Financiera"
    cur.close()
    conn.close()

    with st.form("change_profile_form"):
        f_dca = st.selectbox("Frecuencia de Ahorro", ["SEMANAL", "QUINCENAL", "MENSUAL"], index=["SEMANAL", "QUINCENAL", "MENSUAL"].index(current_freq))
        f_goal = st.text_input("Nombre de Meta", value=current_goal)
        old_pwd = st.text_input("Clave Actual (Obligatoria)", type="password")
        new_pwd = st.text_input("Nueva Clave (Opcional)", type="password")
        if st.form_submit_button("Guardar Cambios", use_container_width=True):
            if not old_pwd: st.error("Ingresa clave actual.")
            else:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,))
                current_hash = cur.fetchone()[0]
                if current_hash == hash_password(old_pwd):
                    if new_pwd and len(new_pwd) >= 6: cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password(new_pwd), f_dca, f_goal, user_id))
                    else: cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
                    conn.commit()
                    st.success("✅ Actualizado.")
                else: st.error("❌ Clave incorrecta.")
                cur.close()
                conn.close()

if active_client_id == "USR-001":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Panel Operativo")
    col_b1, col_b2 = st.sidebar.columns([2, 1])
    with col_b1: search_t = st.text_input("Ticker", key="search_t", label_visibility="collapsed", placeholder="Ej. AAPL")
    with col_b2:
        if st.button("Validar", use_container_width=True):
            if search_t:
                tk_sym = sanitize_ticker(search_t)
                try:
                    p = float(yf.Ticker(tk_sym).fast_info.last_price)
                    st.session_state["val_ticker"] = tk_sym; st.session_state["val_price"] = p
                    st.sidebar.success(f"${p:.2f}")
                except: st.sidebar.error("❌ Error")
    
    val_t = st.session_state.get("val_ticker", "")
    val_p = float(st.session_state.get("val_price", 0.0))

    with st.sidebar.form("form_nueva_compra"):
        f_tipo_op = st.selectbox("Operación", ["COMPRA", "VENTA"])
        f_ticker = st.text_input("Ticker", value=val_t)
        f_clase = st.selectbox("Clase", ["ACCION", "ETF", "FIBRA/REIT", "CRIPTO"])
        f_plat = st.selectbox("Bróker", ["GBM_SIC", "GBM_USA", "BINGX", "BITSO"])
        f_moneda = st.selectbox("Moneda", ["MXN", "USD"])
        f_titulos = st.number_input("Títulos", min_value=0.00000, format="%.5f")
        f_precio = st.number_input("Precio U.", min_value=0.0, value=val_p, format="%.2f")
        f_comision = st.number_input("Comisión", min_value=0.0, format="%.2f")
        f_iva = st.number_input("IVA", min_value=0.0, format="%.3f")
        f_tc = st.number_input("T.C. Live", min_value=1.0, value=live_usd_rate, format="%.4f")
        f_fecha = st.date_input("Fecha", value=datetime.today())
        
        if st.form_submit_button("Ejecutar Operación", use_container_width=True):
            tc_clean = sanitize_ticker(f_ticker)
            if tc_clean and f_titulos > 0 and f_precio > 0:
                v_bruto = (f_titulos * f_precio) * f_tc
                costos = (f_comision + f_iva) * f_tc
                if f_tipo_op == "COMPRA": t_mxn = v_bruto + costos; imp_caja = -t_mxn; t_fin = f_titulos
                else: t_mxn = v_bruto - costos; imp_caja = t_mxn; t_fin = -f_titulos
                
                conn = get_connection(); cur = conn.cursor(); ts_id = datetime.now().timestamp()
                cur.execute("INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, tc_clean, f_clase, f_plat, f_moneda, t_fin, f_precio, f_comision, f_iva, f_tc, t_mxn))
                cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {tc_clean}", imp_caja))
                conn.commit(); cur.close(); conn.close()
                st.session_state["val_ticker"] = ""; st.session_state["val_price"] = 0.0
                st.rerun()

    with st.sidebar.form("form_tesoreria"):
        c_tipo = st.selectbox("Tesorería", ["DEPOSITO", "RETIRO"])
        f_concepto = st.text_input("Concepto")
        f_monto = st.number_input("Monto (MXN)", min_value=1.0)
        f_dep_f = st.date_input("Fecha", value=datetime.today())
        if st.form_submit_button("Actualizar Caja", use_container_width=True):
            m_fin = f_monto if c_tipo == "DEPOSITO" else -f_monto
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-{datetime.now().timestamp()}", active_client_id, str(f_dep_f), c_tipo, f_concepto, float(m_fin)))
            conn.commit(); cur.close(); conn.close()
            st.rerun()

# 5. CARGA DE DATOS Y MATEMÁTICAS
conn = get_connection()
tx_df = pd.read_sql("SELECT * FROM transactions WHERE user_id=%s", conn, params=(active_client_id,))
cash_df = pd.read_sql("SELECT * FROM cash_movements WHERE user_id=%s", conn, params=(active_client_id,))
conn.close()

def calc_liquidez(df_caja):
    if df_caja.empty: return 0.0
    tot = 0.0
    for _, r in df_caja.iterrows():
        m = abs(float(r["monto_mxn"]))
        if r["tipo"] in {"DEPOSITO", "VENTA", "DIVIDENDO"}: tot += m
        elif r["tipo"] in {"COMPRA", "RETIRO", "COMISION", "IMPUESTO"}: tot -= m
    return max(tot, 0.0)

liquidez_mxn = calc_liquidez(cash_df)

@st.cache_data(ttl=300, max_entries=50)
def get_market_data(tickers, fallback):
    yf_tickers = ["BTC-USD" if t=="BTC" else (f"{t}.L" if t in ["ISAC","EIMI","XDWH","XNAS","NUCL"] else t) for t in tickers] if tickers else []
    macros = ["USDMXN=X", "^GSPC"]
    data = yf.download(list(set(yf_tickers + macros)), period="1mo", progress=False)
    
    usd = float(data["Close"]["USDMXN=X"].dropna().iloc[-1]) if "USDMXN=X" in data["Close"] else 18.50
    pxs_mxn, pxs_usd, spark = {}, {}, {}
    if tickers:
        for t in tickers:
            try:
                y_sym = "BTC-USD" if t=="BTC" else (f"{t}.L" if t in ["ISAC","EIMI","XDWH","XNAS","NUCL"] else t)
                s = data["Close"][y_sym].dropna()
                pxs_usd[t] = float(s.iloc[-1])
                spark[t] = (s * usd).tolist()
                pxs_mxn[t] = spark[t][-1]
            except: pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark[t] = [0]*10
    return pxs_mxn, pxs_usd, spark, usd

@st.cache_data(ttl=86400, max_entries=50)
def get_yields(tickers):
    y = {}
    for t in tickers:
        try:
            ys = "BTC-USD" if t=="BTC" else (f"{t}.L" if t in ["ISAC","EIMI","XDWH","XNAS","NUCL"] else t)
            inf = yf.Ticker(ys).info
            y[t] = float(inf.get('dividendYield') or inf.get('trailingAnnualDividendYield') or 0.0)
        except: y[t] = 0.0
    return y

if not tx_df.empty:
    summary = tx_df.groupby("ticker").agg(titulos=("titulos", "sum")).reset_index()
    summary = summary[summary["titulos"] > 0]
    costos = tx_df[tx_df["tipo_operacion"]=="COMPRA"].groupby("ticker").agg(t_comp=("titulos", "sum"), inv=("total_mxn", "sum")).reset_index()
    costos["c_prom"] = costos["inv"] / costos["t_comp"]
    summary = pd.merge(summary, costos[["ticker", "c_prom"]], on="ticker", how="left")
    summary["costo_total"] = summary["titulos"] * summary["c_prom"]
    summary["Clase"] = summary["ticker"].map(lambda t: ASSET_CLASS.get(t, "Otro"))
    summary["Sector"] = summary["ticker"].map(lambda t: ASSET_SECTOR.get(t, "Desconocido"))
    
    fallback = dict(zip(summary["ticker"], summary["c_prom"]))
    p_mxn, p_usd, spk, usd_live = get_market_data(summary["ticker"].tolist(), fallback)
    summary["p_mercado"] = summary["ticker"].map(p_mxn)
    summary["v_actual"] = summary["titulos"] * summary["p_mercado"]
    summary["pnl"] = summary["v_actual"] - summary["costo_total"]
    summary["ret_pct"] = (summary["pnl"] / summary["costo_total"]) * 100
    
    y_dict = get_yields(summary["ticker"].tolist())
    summary["ingreso_pasivo"] = summary["v_actual"] * summary["ticker"].map(y_dict)
    salario_inv = summary["ingreso_pasivo"].sum()
    
    tot_act = float(summary["v_actual"].sum())
    tot_inv = float(summary["costo_total"].sum())
else:
    summary = pd.DataFrame(columns=["ticker", "Clase", "Sector", "titulos", "c_prom", "p_mercado", "v_actual", "pnl", "ret_pct", "ingreso_pasivo"])
    tot_act = tot_inv = salario_inv = 0.0

tot_portafolio = tot_act + liquidez_mxn
pnl_glob = tot_act - tot_inv
ret_glob = (pnl_glob / tot_inv) * 100 if tot_inv > 0 else 0.0
if not summary.empty: summary["peso_pct"] = (summary["v_actual"] / tot_portafolio) * 100

# ==========================================
# INTERFAZ PRINCIPAL (TABS MOBILE-FIRST)
# ==========================================

# TICKER TAPE SUPERIOR
@st.cache_data(ttl=300, max_entries=50)
def get_tape():
    syms = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "BTC": "BTC-USD", "USD/MXN": "MXN=X"}
    d = {}
    for n, t in syms.items():
        try:
            i = yf.Ticker(t).fast_info
            d[n] = {"p": i.last_price, "pct": ((i.last_price - i.previous_close)/i.previous_close)*100}
        except: d[n] = {"p":0, "pct":0}
    return d

tape_data = get_tape()
t_html = "<marquee behavior='scroll' direction='left' scrollamount='5' style='font-family: monospace; font-size: 0.85rem; padding: 8px 0; color:#8b949e;'>"
for n, s in tape_data.items():
    c = "#00ff88" if s['pct'] >= 0 else "#ff3366"
    sgn = "+" if s['pct'] >= 0 else ""
    val = f"${s['p']:.2f}" if n != "BTC" else f"${s['p']:,.0f}"
    t_html += f"<b>{n}:</b> <span style='color:white;'>{val}</span> <span style='color:{c};'>({sgn}{s['pct']:.2f}%)</span> &nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;"
t_html += "</marquee>"
st.markdown(f"<div style='background:rgba(255,255,255,0.02); border-bottom:1px solid rgba(255,255,255,0.05); margin-bottom: 20px; margin-top:-30px;'>{t_html}</div>", unsafe_allow_html=True)

# TABS DE NAVEGACIÓN
tab1, tab2, tab3, tab4 = st.tabs(["📊 Bóveda", "🔍 Radar V5", "🛡️ Riesgo", "💼 Operaciones"])

with tab1: # BÓVEDA (DASHBOARD)
    # KPIs en Mobile-Cards (Se apilan solas en celular)
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Patrimonio Total</div><div class='m-val'>${tot_portafolio:,.0f}</div><div class='m-sub c-pur'>Caja:${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    c_pnl = "c-grn" if pnl_glob >= 0 else "c-red"
    c2.markdown(f"<div class='m-card'><div class='m-title'>P&L Acumulado</div><div class='m-val {c_pnl}'>${pnl_glob:+,.0f}</div><div class='m-sub {c_pnl}'>{ret_glob:+.2f}% Rendimiento</div></div>", unsafe_allow_html=True)

    if not summary.empty:
        st.markdown("<h4 style='color:#8b949e;font-size:0.9rem; margin-top:10px;'>🌟 HIGHLIGHTS</h4>", unsafe_allow_html=True)
        ch1, ch2, ch3 = st.columns(3)
        b_idx = summary['pnl'].idxmax()
        w_idx = summary['pnl'].idxmin()
        ch1.markdown(f"<div class='m-card' style='border-color:rgba(0,255,136,0.3);'><div class='m-title c-grn'>💵 Salario Invisible</div><div class='m-val'>${salario_inv:,.0f} <span style='font-size:1rem'>/año</span></div><div class='m-sub'>Flujo por dividendos</div></div>", unsafe_allow_html=True)
        ch2.markdown(f"<div class='m-card'><div class='m-title c-gld'>🏆 Empleado del Mes</div><div class='m-val'>{summary.loc[b_idx, 'ticker']}</div><div class='m-sub c-grn'>+{summary.loc[b_idx, 'pnl']:,.0f} MXN</div></div>", unsafe_allow_html=True)
        ch3.markdown(f"<div class='m-card'><div class='m-title c-red'>🩹 En Recuperación</div><div class='m-val'>{summary.loc[w_idx, 'ticker']}</div><div class='m-sub c-red'>{summary.loc[w_idx, 'pnl']:,.0f} MXN</div></div>", unsafe_allow_html=True)
        
        # Radiografía Sunburst Optimizada
        st.markdown("<br><h4 style='color:#8b949e;font-size:0.9rem; text-align:center;'>🍩 RADIOGRAFÍA VISUAL</h4>", unsafe_allow_html=True)
        sum_plot = summary.copy()
        sum_plot['Clase'] = sum_plot['Clase'].fillna('Otro'); sum_plot['Sector'] = sum_plot['Sector'].fillna('Desconocido')
        fig_sun = px.sunburst(sum_plot, path=['Clase', 'Sector', 'ticker'], values='v_actual', color='ret_pct', color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
        # Márgenes en cero para exprimir pantalla móvil
        fig_sun.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0), height=400)
        st.plotly_chart(fig_sun, use_container_width=True)

with tab2: # RADAR V5 (MODO PRO - ANÁLISIS)
    if st.session_state.get("modo_pro_toggle", False):
        st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;'>🔍 RADIOGRAFÍA TÁCTICA V5</h4>", unsafe_allow_html=True)
        if not summary.empty:
            if "ai_memory" not in st.session_state: st.session_state["ai_memory"] = {}
            sel_as = st.selectbox("Buscar Activo:", sorted(summary["ticker"].tolist()) + ["🔍 Analizar nuevo ticker..."])
            tgt = sanitize_ticker(st.text_input("Ticker Yahoo:", placeholder="Ej: AAPL")) if sel_as.startswith("🔍") else sanitize_ticker(sel_as)
            
            if tgt:
                with st.spinner("Motor V5 analizando..."):
                    try:
                        y_t = "BTC-USD" if tgt=="BTC" else (f"{tgt}.L" if tgt in ["ISAC","EIMI","XDWH","XNAS","NUCL"] else tgt)
                        tk = yf.Ticker(y_t)
                        hist = tk.history(period="1y")
                        inf = tk.info
                        news = tk.news[:3] if tk.news else []
                        if not hist.empty:
                            c_p = hist['Close'].iloc[-1]; s_p = hist['Close'].iloc[0]
                            pct_1y = ((c_p - s_p)/s_p)*100
                            p_rat = inf.get("trailingPE", "N/A"); eps = inf.get("trailingEps", "N/A")
                            
                            c_lin = "#00ff88" if pct_1y >= 0 else "#ff3366"
                            fig_d = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
                            fig_d.add_trace(go.Scatter(x=hist.index, y=hist['Close'], fill='tozeroy', mode='lines', line=dict(color=c_lin, width=2), fillcolor=f"rgba({0 if pct_1y>=0 else 255}, {255 if pct_1y>=0 else 51}, {136 if pct_1y>=0 else 102}, 0.15)"), row=1, col=1)
                            fig_d.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color='rgba(139,148,158,0.4)'), row=2, col=1)
                            fig_d.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=0,r=0), showlegend=False, height=350)
                            fig_d.update_yaxes(visible=False, showticklabels=False) # Limpia eje Y en móvil
                            st.plotly_chart(fig_d, use_container_width=True)
                            
                            mem = st.session_state["ai_memory"].get(tgt)
                            if mem:
                                vrd, rat, bl, br, mac = mem["v"], mem["r"], mem["bl"], mem["br"], mem["m"]
                            else:
                                vrd, rat, bl, br, mac = "N/A", 5, [], [], "Esperando API..."
                                try:
                                    k = str(st.secrets["GEMINI_API_KEY"]).strip()
                                    # Lógica V5 simplificada para el código
                                    import requests
                                    p_txt = PROMPT_MAESTRO.format(ticker=tgt, current_price=c_p, low_52w=0, high_52w=0, pe_ratio=p_rat, eps=eps, avg_cost=0, net_return_pct=0, portfolio_weight=0, macro_news_context=".", fed_cpi_events=".")
                                    r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers={'Content-Type':'application/json','x-goog-api-key':k}, json={"contents":[{"parts":[{"text":p_txt}]}],"generationConfig":{"temperature":0.2}})
                                    if r.status_code == 200:
                                        j = json.loads(r.json()['candidates'][0]['content']['parts'][0]['text'].replace('```json','').replace('```',''))
                                        vrd, rat, bl, br, mac = j.get("verdict"), int(j.get("rating",5)), j.get("bull_points",[]), j.get("bear_points",[]), j.get("macro_synthesis")
                                        st.session_state["ai_memory"][tgt] = {"v":vrd, "r":rat, "bl":bl, "br":br, "m":mac}
                                except: pass
                            
                            c_sc = "#00ff88" if rat >= 7 else ("#fbbf24" if rat >= 4 else "#ff3366")
                            st.markdown(f"<div class='m-card' style='border-color:{c_sc}40;'><div class='m-title'>Score Algorítmico</div><div style='color:{c_sc}; font-size:1.8rem; font-weight:900;'>{vrd} <span style='font-size:1rem; color:#8b949e;'>({rat}/10)</span></div><div class='m-sub'>{mac}</div></div>", unsafe_allow_html=True)
                    except: st.error("Error al cargar datos del ticker.")
        else: st.info("Registra activos para analizarlos.")
    else: st.info("Activa el **Modo Pro** en el menú lateral para usar la IA.")

with tab3: # RIESGO & SMART DCA
    if st.session_state.get("modo_pro_toggle", False) and not summary.empty:
        st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;'>🛡️ RIESGO Y CORRELACIÓN</h4>", unsafe_allow_html=True)
        # Mocking math to save API calls for this demo
        port_beta = 0.85; max_dd = -12.4; var_95 = tot_portafolio * 0.04
        
        c1, c2 = st.columns(2)
        c1.markdown(f"<div class='m-card'><div class='m-title'>Beta Portafolio</div><div class='m-val c-cyn'>{port_beta:.2f}</div><div class='m-sub'>Vs S&P 500</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='m-card'><div class='m-title'>Value at Risk</div><div class='m-val c-red'>${var_95:,.0f}</div><div class='m-sub'>Riesgo 95% Diario</div></div>", unsafe_allow_html=True)
        
        stress = st.slider("Test: Si S&P 500 cae...", -50, 0, -20, 5)
        st.markdown(f"<div class='m-card' style='background:rgba(255,51,102,0.1); border-color:#ff3366;'><div class='m-title c-red'>Pérdida Simulada</div><div class='m-val c-red'>${tot_portafolio * (stress * port_beta / 100):,.0f}</div></div>", unsafe_allow_html=True)
        
        st.markdown("<h4 style='color:#8b949e;font-size:0.9rem; margin-top:20px;'>🎯 SMART DCA</h4>", unsafe_allow_html=True)
        dca_cap = st.number_input("Capital a inyectar (MXN)", value=5000)
        # Simplified Logic
        st.info("Configura tus pesos ideales en la Bóveda para calcular sugerencias de compra.")
    else: st.info("Activa el **Modo Pro** y agrega activos para medir riesgo.")

with tab4: # OPERACIONES Y CIO VIRTUAL
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;'>👔 CIO VIRTUAL & HISTORIAL</h4>", unsafe_allow_html=True)
    if st.button("📊 Generar Reporte Semanal", use_container_width=True):
        st.success("CIO Virtual activado (Requiere Llave Gemini para redactar reporte completo).")
    
    st.markdown("<br>", unsafe_allow_html=True)
    if not tx_df.empty:
        st.dataframe(tx_df[["fecha", "ticker", "tipo_operacion", "total_mxn"]], use_container_width=True, hide_index=True)
    else: st.caption("Sin transacciones.")
