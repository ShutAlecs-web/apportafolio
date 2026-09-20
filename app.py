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

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Terminal Apportafolio | Private Wealth",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. FUNCIONES CORE Y BASE DE DATOS
# ==========================================
def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

@st.cache_data(ttl=300, max_entries=50)
def get_live_usd():
    try: return float(yf.Ticker("MXN=X").fast_info.last_price)
    except: return 19.50

live_usd_rate = get_live_usd()

def get_connection(): return psycopg2.connect(st.secrets["DATABASE_URL"])
def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_connection(); conn.autocommit = True; cur = conn.cursor()
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
    except Exception: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
    cur.execute("INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", ("USR-001", "alex_admin", hash_password(admin_pwd), "MENSUAL", "Fondo Institucional"))
    cur.close(); conn.close()

init_db()

PROMPT_MAESTRO = """
Eres el 'Motor Algorítmico V5', un analista cuantitativo y macroeconómico de inteligencia artificial, diseñado para operar sin emociones, sin FOMO y con pura frialdad matemática. Tu objetivo es proporcionar una radiografía táctica ('Due Diligence') de un activo financiero.
DATOS DEL ACTIVO: Ticker: {ticker} | Precio: {current_price} USD | Rango 52W: {low_52w} - {high_52w} | P/E: {pe_ratio} | EPS: {eps}
PORTAFOLIO: Costo Promedio: {avg_cost} | Retorno: {net_return_pct}% | Peso: {portfolio_weight}%
CONTEXTO MACRO: {macro_news_context}
CALENDARIO FED/IPC: {fed_cpi_events}
Responde ÚNICA Y EXCLUSIVAMENTE con un JSON válido. No uses markdown de código.
{"verdict": "DCA FUERTE", "rating": 8, "bull_points": ["Punto 1"], "bear_points": ["Punto 1"], "macro_synthesis": "Síntesis de 2 líneas."}
"""

ASSET_CLASS = {"ISAC": "ETF", "XNAS": "ETF", "XDWH": "ETF", "EIMI": "ETF", "NUCL": "ETF", "GOOGL": "Acción", "MELI": "Acción", "NOW": "Acción", "ASML": "Acción", "NVO": "Acción", "MA": "Acción", "V": "Acción", "BTC": "Cripto"}
ASSET_SECTOR = {"ISAC": "Renta Variable Global", "XNAS": "Tecnología (Índice)", "XDWH": "Salud Global", "EIMI": "Mercados Emergentes", "NUCL": "Energía/Utilities", "GOOGL": "Servicios de Comunicación", "MELI": "Comercio Electrónico", "NOW": "Software B2B", "ASML": "Semiconductores", "NVO": "Biotecnología / Salud", "MA": "Servicios Financieros", "V": "Servicios Financieros", "BTC": "Criptoactivos"}

if "user_id" not in st.session_state: st.session_state["user_id"] = None

# ==========================================
# 3. PORTADA: SPLIT-SCREEN (CIELO ESTRELLADO)
# ==========================================
if st.session_state["user_id"] is None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@200;300;400&family=Playfair+Display:ital@1&display=swap');
    
    [data-testid="stAppViewContainer"], .stApp {
        background: linear-gradient(rgba(2, 5, 10, 0.75), rgba(2, 5, 10, 0.95)), 
                    url('https://images.unsplash.com/photo-1506318137071-a8e063b4bec0?q=80&w=3000&auto=format&fit=crop') no-repeat center center fixed !important;
        background-size: cover !important;
    }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    
    .portada-title {
        font-family: 'Montserrat', sans-serif; font-weight: 200; font-size: 4.5rem; letter-spacing: 0.15em; text-align: left; line-height: 1.1; margin-bottom: 5px;
        background: linear-gradient(to right, #bf953f 0%, #fcf6ba 25%, #b38728 50%, #fbf5b7 75%, #aa771c 100%); background-size: 200% auto; color: #000;
        background-clip: text; text-fill-color: transparent; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        animation: shine 6s linear infinite;
    }
    @keyframes shine { to { background-position: 200% center; } }
    .portada-subtitle { font-family: 'Playfair Display', serif; font-style: italic; color: #8b949e; text-align: left; font-size: 1.2rem; letter-spacing: 0.15em; margin-bottom: 40px; margin-top: 10px;}

    [data-testid="stForm"] {
        background: rgba(9, 23, 46, 0.2) !important; border: 1px solid rgba(191, 149, 63, 0.25) !important; border-radius: 16px !important;
        backdrop-filter: blur(15px) !important; -webkit-backdrop-filter: blur(15px) !important; padding: 3rem 2.5rem !important;
        box-shadow: 0 20px 40px rgba(0,0,0,0.8) !important; margin-top: 20px;
    }
    [data-testid="stForm"] label { color: #8b949e !important; font-family: 'Montserrat', sans-serif !important; font-weight: 300 !important; letter-spacing: 2px !important; text-transform: uppercase; font-size: 0.8rem !important;}
    [data-testid="stForm"] input { background: rgba(0, 0, 0, 0.4) !important; border: 1px solid rgba(191, 149, 63, 0.3) !important; color: #fcf6ba !important; border-radius: 8px !important; font-family: 'Montserrat', sans-serif !important; padding: 0.8rem !important;}
    [data-testid="stForm"] input:focus { border-color: #fcf6ba !important; box-shadow: 0 0 15px rgba(191, 149, 63, 0.3) !important; }
    [data-testid="stFormSubmitButton"] button { background: linear-gradient(135deg, #bf953f 0%, #e2c575 100%) !important; color: #02050a !important; font-weight: 600 !important; font-family: 'Montserrat', sans-serif !important; letter-spacing: 3px !important; text-transform: uppercase !important; border: none !important; border-radius: 8px !important; padding: 0.8rem !important; margin-top: 20px !important; width: 100%; transition: all 0.3s ease !important;}
    [data-testid="stFormSubmitButton"] button:hover { transform: translateY(-2px) !important; box-shadow: 0 10px 20px rgba(191, 149, 63, 0.4) !important; }
    @media (max-width: 800px) { .portada-title { font-size: 3rem; text-align: center; } .portada-subtitle { text-align: center; } }
    </style>
    """, unsafe_allow_html=True)

    c_izq, c_der = st.columns([1.3, 1])
    with c_izq:
        st.markdown("<br><br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 class='portada-title'>TERMINAL<br>APPORTAFOLIO</h1>", unsafe_allow_html=True)
        st.markdown("<p class='portada-subtitle'>Exclusivo y personalizado para ti.</p>", unsafe_allow_html=True)
    with c_der:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.form("login_form"):
            usr = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Acceder", use_container_width=True):
                conn = get_connection(); cur = conn.cursor()
                cur.execute("SELECT user_id FROM users WHERE username=%s AND password_hash=%s", (usr, hash_password(pwd)))
                user = cur.fetchone(); cur.close(); conn.close()
                if user: st.session_state["user_id"] = user[0]; st.rerun()
                else: st.error("Credenciales incorrectas.")
    st.stop()


# ==========================================
# 4. DASHBOARD: QUIET LUXURY FINTECH CSS
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500;600&display=swap');
[data-testid="stAppViewContainer"], .stApp { background-color: #03050a !important; font-family: 'Inter', sans-serif !important; color: #cbd5e1; }
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Tabs iOS Lujo */
div[data-testid="stTabs"] button { background-color: #080b13 !important; border-radius: 20px !important; border: 1px solid rgba(255,255,255,0.03) !important; color: #64748b !important; padding: 8px 18px !important; font-family: 'Inter', sans-serif !important; font-weight: 400 !important; font-size: 0.95rem !important; margin-right: 10px !important; transition: all 0.3s ease; }
div[data-testid="stTabs"] button[aria-selected="true"] { background-color: rgba(212, 175, 55, 0.05) !important; color: #d4af37 !important; border: 1px solid rgba(212, 175, 55, 0.3) !important; font-family: 'Playfair Display', serif !important; font-style: italic; letter-spacing: 1px; box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important; }

/* Tarjetas Móviles Fluidas */
.m-card { background: linear-gradient(145deg, #080b13 0%, #0a0e17 100%); border-radius: 24px; border: 1px solid rgba(212, 175, 55, 0.15); padding: 24px; margin-bottom: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
.m-title { color: #8b949e; font-size: 0.75rem; font-weight: 400; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; font-family: 'Inter', sans-serif;}
.m-val { font-family: 'Playfair Display', serif; font-size: 2.2rem; font-weight: 400; color: #ffffff; letter-spacing: -0.5px; line-height: 1.1; margin: 10px 0;}
.m-sub { font-size: 0.9rem; margin-top: 8px; font-weight: 300; color: #64748b; font-family: 'Inter', sans-serif;}

/* Elementos Internos */
.pos-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem;}
.pos-label { color: #8b949e; font-weight: 400;}
.pos-val { color: #ffffff; font-weight: 500; font-family: 'Inter', sans-serif;}

.c-grn { color: #34d399 !important; } .c-red { color: #fb7185 !important; } .c-gld { color: #d4af37 !important; } .c-pur { color: #c084fc !important; } .c-cyn { color: #00f0ff !important; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 5. GESTIÓN MULTI-CLIENTE Y SIDEBAR
# ==========================================
user_id = st.session_state["user_id"]
conn = get_connection()
all_users = pd.read_sql("SELECT user_id, username FROM users", conn)
conn.close()

if user_id == "USR-001":
    st.sidebar.markdown("<h3 style='color:#d4af37; font-family:\"Playfair Display\"; font-style:italic;'>👑 Panel de Gestor</h3>", unsafe_allow_html=True)
    client_dict = dict(zip(all_users["username"], all_users["user_id"]))
    selected_client_name = st.sidebar.selectbox("Cliente Activo:", list(client_dict.keys()))
    active_client_id = client_dict[selected_client_name]
    active_username = selected_client_name 
    
    with st.sidebar.expander("➕ Nuevo Cliente", expanded=False):
        with st.form("new_client_form"):
            new_usr = st.text_input("Usuario")
            new_pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Crear"):
                if new_usr and new_pwd:
                    conn = get_connection(); cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO users (user_id, username, password_hash) VALUES (%s, %s, %s)", (f"USR-{int(datetime.now().timestamp())}", new_usr, hash_password(new_pwd)))
                        conn.commit(); st.success("Creado. Recarga.")
                    except: st.error("El usuario ya existe.")
                    cur.close(); conn.close()
else:
    active_client_id = user_id
    active_username = all_users.loc[all_users["user_id"] == user_id, "username"].values[0]
    st.sidebar.markdown(f"<h3 style='color:#d4af37; font-family:\"Playfair Display\"; font-style:italic;'>Cliente: {active_username}</h3>", unsafe_allow_html=True)

if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
    st.session_state["user_id"] = None; st.rerun()

st.sidebar.markdown("---")
st.sidebar.toggle("🔬 Activar Modo Pro", key="modo_pro_toggle", help="Muestra herramientas institucionales.")

with st.sidebar.expander("⚙️ Estrategia y Perfil", expanded=False):
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (user_id,))
        user_data = cur.fetchone(); current_freq, current_goal = user_data[0], user_data[1]
    except: current_freq, current_goal = "MENSUAL", "Libertad Financiera"
    cur.close(); conn.close()

    with st.form("change_profile_form"):
        f_dca = st.selectbox("Frecuencia Ahorro", ["SEMANAL", "QUINCENAL", "MENSUAL"], index=["SEMANAL", "QUINCENAL", "MENSUAL"].index(current_freq))
        f_goal = st.text_input("Nombre de tu Meta 🎯", value=current_goal, max_chars=30)
        old_pwd = st.text_input("Contraseña Actual", type="password")
        new_pwd = st.text_input("Nueva Contraseña", type="password")
        if st.form_submit_button("Guardar Cambios", use_container_width=True):
            if not old_pwd: st.error("⚠️ Ingresa clave actual.")
            else:
                conn = get_connection(); cur = conn.cursor()
                cur.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,))
                if cur.fetchone()[0] == hash_password(old_pwd):
                    if new_pwd and len(new_pwd) >= 6: cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password(new_pwd), f_dca, f_goal, user_id))
                    else: cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
                    conn.commit(); st.success("✅ Perfil actualizado.")
                else: st.error("❌ Clave incorrecta.")
                cur.close(); conn.close()

if active_client_id == "USR-001":
    st.sidebar.markdown("---")
    st.sidebar.markdown("<p style='color:#d4af37; font-size:1rem; font-style:italic; font-family:\"Playfair Display\";'>⚡ Panel Operativo</p>", unsafe_allow_html=True)
    col_b1, col_b2 = st.sidebar.columns([2, 1])
    with col_b1: search_ticker = st.text_input("Ticker", key="search_t", label_visibility="collapsed", placeholder="Ej. AAPL")
    with col_b2:
        if st.button("Validar", use_container_width=True):
            if search_ticker:
                tk_sym = sanitize_ticker(search_ticker)
                try:
                    p = yf.Ticker(tk_sym).fast_info.last_price
                    if p: st.session_state["val_ticker"] = tk_sym; st.session_state["val_price"] = float(p); st.sidebar.success(f"✅ ${p:.2f}")
                except: st.sidebar.error("❌ Error")

    val_t = st.session_state.get("val_ticker", "")
    val_p = float(st.session_state.get("val_price", 0.0))

    with st.sidebar.expander("🛒 Registrar Operación", expanded=True):
        with st.form("form_nueva_compra"):
            f_tipo_op = st.selectbox("Operación", ["COMPRA", "VENTA"])
            f_ticker = st.text_input("Activo (Ticker)", value=val_t)
            f_clase = st.selectbox("Clase", ["ACCION", "ETF", "FIBRA/REIT", "CRIPTO"])
            f_plat = st.selectbox("Plataforma", ["GBM_SIC", "GBM_USA", "BINGX", "BITSO"])
            f_moneda = st.selectbox("Moneda", ["MXN", "USD"])
            f_titulos = st.number_input("Títulos", min_value=0.00000, format="%.5f", step=0.01)
            f_precio = st.number_input("Precio Unitario", min_value=0.0, value=val_p, format="%.2f", step=1.0)
            f_comision = st.number_input("Comisión", min_value=0.0, format="%.2f")
            f_iva = st.number_input("IVA", min_value=0.0, format="%.3f")
            f_tc = st.number_input("T.C. Live", min_value=1.0, value=live_usd_rate, format="%.4f")
            f_fecha = st.date_input("Fecha", value=datetime.today())
            
            if st.form_submit_button("Ejecutar", use_container_width=True):
                f_ticker_clean = sanitize_ticker(f_ticker)
                if f_ticker_clean and f_titulos > 0 and f_precio > 0:
                    v_bruto = (f_titulos * f_precio) * f_tc
                    costos = (f_comision + f_iva) * f_tc
                    if f_tipo_op == "COMPRA": t_mxn = v_bruto + costos; imp_caja = -t_mxn; t_fin = f_titulos
                    else: t_mxn = v_bruto - costos; imp_caja = t_mxn; t_fin = -f_titulos
                        
                    conn = get_connection(); cur = conn.cursor(); ts_id = datetime.now().timestamp()
                    cur.execute("INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, f_ticker_clean, f_clase, f_plat, f_moneda, t_fin, f_precio, f_comision, f_iva, f_tc, t_mxn))
                    cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {f_ticker_clean}", imp_caja))
                    conn.commit(); cur.close(); conn.close()
                    st.session_state["val_ticker"] = ""; st.session_state["val_price"] = 0.0; st.rerun()

    with st.sidebar.expander("💸 Tesorería", expanded=False):
        with st.form("form_nuevo_deposito"):
            c_tipo_op = st.selectbox("Tipo", ["DEPOSITO", "RETIRO"])
            f_concepto = st.text_input("Concepto")
            f_monto = st.number_input("Monto (MXN)", min_value=1.0, step=500.0)
            f_dep_fecha = st.date_input("Fecha", value=datetime.today())
            if st.form_submit_button("Actualizar Caja", use_container_width=True):
                m_fin = f_monto if c_tipo_op == "DEPOSITO" else -f_monto
                conn = get_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-TES-{datetime.now().timestamp()}", active_client_id, str(f_dep_fecha), c_tipo_op, f_concepto, float(m_fin)))
                conn.commit(); cur.close(); conn.close(); st.rerun()


# ==========================================
# 6. MOTOR MATEMÁTICO
# ==========================================
conn = get_connection()
tx_df = pd.read_sql("SELECT * FROM transactions WHERE user_id=%s", conn, params=(active_client_id,))
cash_df = pd.read_sql("SELECT * FROM cash_movements WHERE user_id=%s", conn, params=(active_client_id,))
conn.close()

def calc_liquidez_real(df_caja):
    if df_caja.empty: return 0.0
    tot = 0.0
    for _, r in df_caja.iterrows():
        m = abs(float(r["monto_mxn"]))
        if r["tipo"] in {"DEPOSITO", "VENTA", "DIVIDENDO"}: tot += m
        elif r["tipo"] in {"COMPRA", "RETIRO", "COMISION", "IMPUESTO"}: tot -= m
    return max(tot, 0.0)

liquidez_mxn = calc_liquidez_real(cash_df)

@st.cache_data(ttl=300, max_entries=50)
def get_prices_and_sparklines(tickers, fallback):
    yf_tickers = []
    if tickers:
        for t in tickers:
            if t == "BTC": yf_tickers.append("BTC-USD")
            elif t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"]: yf_tickers.append(f"{t}.L")
            else: yf_tickers.append(t)
    
    macro_tickers = ["USDMXN=X", "^GSPC", "^NDX", "^DJI", "GC=F", "BTC-USD"]
    data = yf.download(list(set(yf_tickers + macro_tickers)), period="1mo", progress=False)
    
    usd = float(data["Close"]["USDMXN=X"].dropna().iloc[-1]) if "USDMXN=X" in data["Close"] else 18.50
    pxs_mxn, pxs_usd, spark_data = {}, {}, {}
    if tickers:
        for t in tickers:
            try:
                y_sym = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
                s = data["Close"][y_sym].dropna()
                spk = (s * usd).tolist()
                spark_data[t] = spk
                pxs_usd[t] = float(s.iloc[-1])
                pxs_mxn[t] = spk[-1] if spk else fallback.get(t, 0.0)
            except: 
                pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark_data[t] = [fallback.get(t, 0.0)] * 10
                
    macro_data = {}
    for m in macro_tickers:
        try: s = data["Close"][m].dropna(); macro_data[m] = {"p": s.iloc[-1], "pct": ((s.iloc[-1] - s.iloc[-2]) / s.iloc[-2]) * 100}
        except: macro_data[m] = {"p": 0.0, "pct": 0.0}
        
    return pxs_mxn, pxs_usd, spark_data, usd, macro_data

@st.cache_data(ttl=86400, max_entries=50)
def get_asset_yields(tickers):
    yields = {}
    for t in tickers:
        try:
            ys = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
            inf = yf.Ticker(ys).info
            yields[t] = float(inf.get('dividendYield') or inf.get('trailingAnnualDividendYield') or 0.0)
        except: yields[t] = 0.0
    return yields

if not tx_df.empty:
    summary = tx_df.groupby("ticker").agg(titulos=("titulos", "sum")).reset_index()
    summary = summary[summary["titulos"] > 0]
    costos = tx_df[tx_df["tipo_operacion"] == "COMPRA"].groupby("ticker").agg(t_comp=("titulos", "sum"), inv=("total_mxn", "sum")).reset_index()
    costos["costo_promedio"] = costos["inv"] / costos["t_comp"]
    summary = pd.merge(summary, costos[["ticker", "costo_promedio"]], on="ticker", how="left")
    summary["costo_total"] = summary["titulos"] * summary["costo_promedio"]
    summary["Clase"] = summary["ticker"].map(lambda t: ASSET_CLASS.get(t, "Otro"))
    summary["Sector"] = summary["ticker"].map(lambda t: ASSET_SECTOR.get(t, "Desconocido"))
    
    fallback_dict = dict(zip(summary["ticker"], summary["costo_promedio"]))
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, macros = get_prices_and_sparklines(summary["ticker"].tolist(), fallback_dict)
    
    summary["precio_mercado"] = summary["ticker"].map(precios_mxn)
    summary["valor_actual"] = summary["titulos"] * summary["precio_mercado"]
    summary["pnl"] = summary["valor_actual"] - summary["costo_total"]
    summary["retorno_pct"] = (summary["pnl"] / summary["costo_total"]) * 100
    
    summary["yield_pct"] = summary["ticker"].map(get_asset_yields(summary["ticker"].tolist()))
    summary["ingreso_pasivo"] = summary["valor_actual"] * summary["yield_pct"]
    salario_invisible = summary["ingreso_pasivo"].sum()
    
    total_activos = float(summary["valor_actual"].sum())
    total_invertido = float(summary["costo_total"].sum())
else:
    summary = pd.DataFrame(columns=["ticker", "Clase", "Sector", "titulos", "costo_promedio", "precio_mercado", "valor_actual", "pnl", "retorno_pct", "yield_pct", "ingreso_pasivo"])
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, macros = get_prices_and_sparklines([], {})
    total_activos = total_invertido = salario_invisible = 0.0

total_portafolio = total_activos + liquidez_mxn
pnl_global = total_activos - total_invertido
retorno_global = (pnl_global / total_invertido) * 100 if total_invertido > 0 else 0.0
summary["ponderacion_pct"] = (summary["valor_actual"] / total_portafolio) * 100 if not summary.empty else 0.0


# ==========================================
# 7. TICKER TAPE FLOTANTE (ESTILO APPLE)
# ==========================================
t_html = "<marquee behavior='scroll' direction='left' scrollamount='5' style='font-family: \"Inter\", sans-serif; font-size: 0.85rem; padding: 12px 20px; color:#8b949e; font-weight:400; letter-spacing: 1px;'>"
for k, v in macros.items():
    name = "S&P 500" if k == "^GSPC" else ("NASDAQ" if k == "^NDX" else ("DOW" if k == "^DJI" else ("ORO" if k == "GC=F" else k)))
    c = "#34d399" if v['pct'] >= 0 else "#fb7185"
    sgn = "+" if v['pct'] >= 0 else ""
    t_html += f"{name}: <span style='color:#ffffff;'>{v['p']:,.2f}</span> <span style='color:{c};'>({sgn}{v['pct']:.2f}%)</span> &nbsp;&nbsp;|&nbsp;&nbsp; "
t_html += "</marquee>"
st.markdown(f"<div style='background:rgba(8, 11, 19, 0.8); border: 1px solid rgba(212, 175, 55, 0.2); border-radius:30px; margin-bottom: 25px; margin-top:-20px;'>{t_html}</div>", unsafe_allow_html=True)


# ==========================================
# 8. PESTAÑAS NATIVAS (DASHBOARD QUIET LUXURY)
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Cartera & Radiografía", "Radar V5 (IA)", "Riesgo & Smart DCA", "Bola de Nieve & CIO", "Historial & Caja"])

with tab1: # CARTERA Y RADIOGRAFÍA
    c_pnl = "c-grn" if pnl_global >= 0 else "c-red"
    st.markdown(f"<div class='m-card' style='text-align:center;'><div class='m-title'>Patrimonio Total</div><div class='m-val'>${total_portafolio:,.2f}</div><div class='m-sub {c_pnl}'>P&L: ${pnl_global:+,.0f} ({retorno_global:+.2f}%)</div></div>", unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    c1.markdown(f"<div class='m-card'><div class='m-title'>Liquidez / Caja</div><div class='m-val' style='font-size:1.8rem;'>${liquidez_mxn:,.0f}</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='m-card'><div class='m-title c-gld'>Salario Invisible (Yield)</div><div class='m-val c-gld' style='font-size:1.8rem;'>${salario_invisible:,.0f}</div></div>", unsafe_allow_html=True)

    if not summary.empty:
        st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-top:20px; margin-bottom:15px; letter-spacing:1px;'>Tus Movimientos Destacados</h4>", unsafe_allow_html=True)
        ch1, ch2 = st.columns(2)
        b_idx, w_idx = summary['pnl'].idxmax(), summary['pnl'].idxmin()
        ch1.markdown(f"<div class='m-card'><div class='m-title c-grn'>Mayor Ganador</div><div class='m-val' style='font-size:1.6rem;'>{summary.loc[b_idx, 'ticker']}</div><div class='m-sub c-grn'>+${summary.loc[b_idx, 'pnl']:,.0f} MXN</div></div>", unsafe_allow_html=True)
        ch2.markdown(f"<div class='m-card'><div class='m-title c-red'>En Recuperación</div><div class='m-val' style='font-size:1.6rem;'>{summary.loc[w_idx, 'ticker']}</div><div class='m-sub c-red'>${summary.loc[w_idx, 'pnl']:,.0f} MXN</div></div>", unsafe_allow_html=True)

        st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; text-align:center;'>Radiografía Visual (Sunburst)</h4>", unsafe_allow_html=True)
        sum_plot = summary.copy()
        sum_plot['Clase'] = sum_plot['Clase'].fillna('Otro'); sum_plot['Sector'] = sum_plot['Sector'].fillna('Desconocido')
        fig_sun = px.sunburst(sum_plot, path=['Clase', 'Sector', 'ticker'], values='valor_actual', color='retorno_pct', color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
        fig_sun.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0), height=450)
        st.plotly_chart(fig_sun, use_container_width=True)

        if st.session_state.get("modo_pro_toggle", False):
            def calc_xirr():
                if cash_df.empty: return "N/A"
                try:
                    cfs = []
                    for _, r in cash_df.iterrows():
                        if r["tipo"] == "DEPOSITO": cfs.append((pd.to_datetime(r["fecha"]), -float(r["monto_mxn"])))
                        elif r["tipo"] == "RETIRO": cfs.append((pd.to_datetime(r["fecha"]), float(r["monto_mxn"])))
                    if not cfs: return "N/A"
                    cfs.append((pd.to_datetime(datetime.today().date()), float(total_portafolio)))
                    cfs.sort(key=lambda x: x[0])
                    dates, amounts = [cf[0] for cf in cfs], [cf[1] for cf in cfs]
                    rate = 0.1
                    for _ in range(100):
                        npv = sum([a / (1 + rate)**((d - dates[0]).days / 365.0) for d, a in zip(dates, amounts)])
                        df_der = sum([-((d - dates[0]).days / 365.0) * a / (1 + rate)**(((d - dates[0]).days / 365.0) + 1) for d, a in zip(dates, amounts)])
                        if df_der == 0: return "N/A"
                        new_rate = rate - npv / df_der
                        if abs(new_rate - rate) < 1e-5: return f"{new_rate * 100:+.2f}%"
                        rate = new_rate
                    return f"{rate * 100:+.2f}%"
                except: return "N/A"
            total_friccion = (tx_df["comision"] + tx_df["iva"]).mul(tx_df["tipo_cambio"]).sum() if not tx_df.empty else 0.0
            
            c_x1, c_x2 = st.columns(2)
            c_x1.markdown(f"<div class='m-card'><div class='m-title c-cyn'>Rentabilidad Ponderada (XIRR)</div><div class='m-val c-cyn' style='font-size:1.8rem;'>{calc_xirr()}</div></div>", unsafe_allow_html=True)
            c_x2.markdown(f"<div class='m-card'><div class='m-title c-red'>Fricción (Comisiones + IVA)</div><div class='m-val c-red' style='font-size:1.8rem;'>${total_friccion:,.2f}</div></div>", unsafe_allow_html=True)
    else: st.info("La bóveda está vacía. Registra activos para iniciar.")

with tab2: # RADAR V5 Y GEMINI
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;'>Due Diligence V5 (Inteligencia Algorítmica)</h4>", unsafe_allow_html=True)
    if not summary.empty:
        if "ai_memory" not in st.session_state: st.session_state["ai_memory"] = {}
        sel_as = st.selectbox("Seleccione un instrumento:", sorted(summary["ticker"].tolist()) + ["🔍 Buscar nuevo ticker..."], label_visibility="collapsed")
        tgt = sanitize_ticker(st.text_input("Ticker Yahoo:", placeholder="Ej: AAPL")) if sel_as.startswith("🔍") else sanitize_ticker(sel_as)
        
        if tgt:
            with st.spinner("Conectando con Motor V5..."):
                try:
                    y_t = "BTC-USD" if tgt=="BTC" else (f"{tgt}.L" if tgt in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else tgt)
                    tk = yf.Ticker(y_t)
                    hist = tk.history(period="1y")
                    info = tk.info
                    if not hist.empty:
                        c_p = hist['Close'].iloc[-1]; s_p = hist['Close'].iloc[0]
                        pct_1y = ((c_p - s_p)/s_p)*100
                        c_lin = "#34d399" if pct_1y >= 0 else "#fb7185"
                        
                        # GRÁFICA DEL ACTIVO
                        fig_d = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
                        fig_d.add_trace(go.Scatter(x=hist.index, y=hist['Close'], fill='tozeroy', mode='lines', line=dict(color=c_lin, width=2), fillcolor=f"rgba({52 if pct_1y>=0 else 251}, {211 if pct_1y>=0 else 113}, {153 if pct_1y>=0 else 133}, 0.15)"), row=1, col=1)
                        fig_d.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color='rgba(212, 175, 55, 0.4)'), row=2, col=1)
                        fig_d.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=10,b=10,l=0,r=0), showlegend=False, height=300)
                        fig_d.update_yaxes(visible=False, showticklabels=False)
                        st.plotly_chart(fig_d, use_container_width=True)
                        
                        pe, eps = info.get("trailingPE", "N/A"), info.get("trailingEps", "N/A")
                        h52, l52 = info.get("fiftyTwoWeekHigh", c_p), info.get("fiftyTwoWeekLow", c_p)
                        
                        # POSICIÓN ACTUAL DEL USUARIO
                        is_own = tgt in summary["ticker"].values
                        if is_own:
                            row_t = summary[summary["ticker"]==tgt].iloc[0]
                            st.markdown(f"<div class='m-card'><div class='m-title'>Tu Posición Actual</div><div class='pos-row'><span class='pos-label'>Títulos:</span><span class='pos-val'>{row_t['titulos']:.4f}</span></div><div class='pos-row'><span class='pos-label'>Costo Prom:</span><span class='pos-val'>${row_t['costo_promedio']:,.2f}</span></div><div class='pos-row'><span class='pos-label'>Retorno:</span><span class='pos-val {'c-grn' if row_t['pnl']>=0 else 'c-red'}'>{row_t['retorno_pct']:+.2f}%</span></div></div>", unsafe_allow_html=True)
                        
                        # LLAMADA A GEMINI
                        mem = st.session_state["ai_memory"].get(tgt)
                        if mem: vrd, rat, bl, br, mac = mem["v"], mem["r"], mem["bl"], mem["br"], mem["m"]
                        else:
                            vrd, rat, bl, br, mac = "N/A", 5, [], [], "Calculando..."
                            try:
                                k = str(st.secrets["GEMINI_API_KEY"]).strip()
                                import requests
                                prompt_f = PROMPT_MAESTRO.format(ticker=tgt, current_price=c_p, low_52w=l52, high_52w=h52, pe_ratio=pe, eps=eps, avg_cost=row_t['costo_promedio'] if is_own else 0, net_return_pct=row_t['retorno_pct'] if is_own else 0, portfolio_weight=row_t['ponderacion_pct'] if is_own else 0, macro_news_context=".", fed_cpi_events=".")
                                r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers={'Content-Type':'application/json','x-goog-api-key':k}, json={"contents":[{"parts":[{"text":prompt_f}]}],"generationConfig":{"temperature":0.2}})
                                if r.status_code == 200:
                                    j = json.loads(r.json()['candidates'][0]['content']['parts'][0]['text'].replace('```json','').replace('```',''))
                                    vrd, rat, bl, br, mac = j.get("verdict","HOLD"), int(j.get("rating",5)), j.get("bull_points",[]), j.get("bear_points",[]), j.get("macro_synthesis","")
                                    st.session_state["ai_memory"][tgt] = {"v":vrd, "r":rat, "bl":bl, "br":br, "m":mac}
                            except: mac = "Motor local. Falla API Gemini."
                        
                        c_sc = "#34d399" if rat >= 7 else ("#d4af37" if rat >= 4 else "#fb7185")
                        bl_h = "".join([f"<li>{x}</li>" for x in bl])
                        br_h = "".join([f"<li>{x}</li>" for x in br])
                        
                        st.markdown(f"<div class='m-card' style='border-top: 2px solid {c_sc};'><div class='m-title'>Veredicto Algorítmico</div><div style='color:{c_sc}; font-family:\"Playfair Display\", serif; font-size:2rem; font-style:italic;'>{vrd} <span style='font-size:1.2rem; color:#64748b; font-family:\"Inter\";'>({rat}/10)</span></div><div class='m-sub' style='line-height:1.6; color:#cbd5e1; margin-top:15px;'>{mac}</div><hr style='border-color:rgba(255,255,255,0.1);'><div style='display:flex; gap:10px; font-size:0.8rem;'><div style='flex:1; color:#34d399;'><b>🟢 BULLS</b><ul style='padding-left:15px;'>{bl_h}</ul></div><div style='flex:1; color:#fb7185;'><b>🔴 BEARS</b><ul style='padding-left:15px;'>{br_h}</ul></div></div></div>", unsafe_allow_html=True)
                except: st.error("Error al cargar datos del ticker.")
    else: st.info("No hay activos para analizar.")

with tab3: # RIESGO & SMART DCA
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;'>Gestión Cuantitativa</h4>", unsafe_allow_html=True)
    if st.session_state.get("modo_pro_toggle", False) and not summary.empty:
        try:
            yf_tickers = ["BTC-USD" if t=="BTC" else (f"{t}.L" if t in ["ISAC","EIMI","XDWH","XNAS","NUCL"] else t) for t in summary["ticker"].tolist()]
            r_data = yf.download(yf_tickers, period="1y", progress=False)['Close'].pct_change().dropna()
            port_ret = sum([r_data[y_t] * (summary.loc[summary["ticker"]==t, "ponderacion_pct"].values[0]/100) for y_t, t in zip(yf_tickers, summary["ticker"].tolist()) if y_t in r_data])
            port_beta = 0.95 # Simulacion rápida para agilidad
            var_95 = total_portafolio * (abs(np.percentile(port_ret, 5)) if len(port_ret)>0 else 0.04)
        except: port_beta, var_95 = 1.0, 0.0

        c1, c2 = st.columns(2)
        c1.markdown(f"<div class='m-card'><div class='m-title'>Volatilidad (Beta)</div><div class='m-val c-gld' style='font-size:1.8rem;'>{port_beta:.2f}</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='m-card'><div class='m-title'>Riesgo Máximo Diario (VaR)</div><div class='m-val c-red' style='font-size:1.8rem;'>${var_95:,.0f}</div></div>", unsafe_allow_html=True)
        
        st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.1rem; font-style:italic; margin-top:20px; letter-spacing:1px;'>Matriz de Correlación</h4>", unsafe_allow_html=True)
        if len(yf_tickers) > 1 and not r_data.empty:
            fig_corr = px.imshow(r_data.corr(), text_auto=".2f", color_continuous_scale="RdBu_r", aspect="auto")
            fig_corr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=0,b=0,l=0,r=0), height=300)
            st.plotly_chart(fig_corr, use_container_width=True)
            
    else: st.info("Activa el Modo Pro para ver Riesgo y Correlación.")

    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-top:20px; margin-bottom:15px; letter-spacing:1px;'>Smart DCA (Rebalanceo)</h4>", unsafe_allow_html=True)
    if not summary.empty:
        c_tgt1, c_tgt2, c_tgt3, c_dca = st.columns(4)
        with c_tgt1: tgt_etf = st.number_input("Objetivo ETF (%)", min_value=0.0, max_value=100.0, value=60.0, step=1.0)
        with c_tgt2: tgt_acc = st.number_input("Objetivo Acción (%)", min_value=0.0, max_value=100.0, value=25.0, step=1.0)
        with c_tgt3: tgt_cripto = st.number_input("Objetivo Cripto (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
        with c_dca: new_capital = st.number_input("Capital a Inyectar", min_value=0.0, value=5000.0, step=500.0)

        if (tgt_etf + tgt_acc + tgt_cripto) == 100.0:
            tgt_dict = {"ETF": tgt_etf, "Acción": tgt_acc, "Cripto": tgt_cripto}
            new_tot = total_activos + new_capital
            deficits, comp_sug = {}, {}
            for cls, tgt in tgt_dict.items():
                c_val = summary.loc[summary["Clase"]==cls, "valor_actual"].sum() if cls in summary["Clase"].values else 0.0
                deficits[cls] = max(0, (new_tot * (tgt / 100.0)) - c_val)
            
            tot_def = sum(deficits.values())
            for cls in tgt_dict: comp_sug[cls] = new_capital * (deficits[cls] / tot_def) if tot_def > 0 else new_capital * (tgt_dict[cls]/100)
            
            st.markdown(f"<div class='m-card'><div class='m-title'>Ruta Óptima de Capital</div><div class='pos-row'><span class='pos-label'>ETF:</span><span class='pos-val c-grn'>${comp_sug['ETF']:,.2f}</span></div><div class='pos-row'><span class='pos-label'>Acciones:</span><span class='pos-val c-grn'>${comp_sug['Acción']:,.2f}</span></div><div class='pos-row'><span class='pos-label'>Cripto:</span><span class='pos-val c-grn'>${comp_sug['Cripto']:,.2f}</span></div></div>", unsafe_allow_html=True)
        else: st.warning("Los objetivos deben sumar 100%.")

with tab4: # BOLA DE NIEVE Y CIO VIRTUAL
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;'>La Bola de Nieve (Gamificación DCA)</h4>", unsafe_allow_html=True)
    if not cash_df.empty:
        df_hist = cash_df[cash_df["tipo"].isin(["DEPOSITO", "RETIRO"])].copy()
        if not df_hist.empty:
            df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
            df_hist = df_hist.sort_values("fecha")
            df_hist["flujo_neto"] = df_hist.apply(lambda r: abs(float(r["monto_mxn"])) if r["tipo"]=="DEPOSITO" else -abs(float(r["monto_mxn"])), axis=1)
            df_hist["capital_acumulado"] = df_hist["flujo_neto"].cumsum()
            df_hist = pd.concat([df_hist, pd.DataFrame({"fecha": [pd.to_datetime(datetime.today().date())], "capital_acumulado": [df_hist["capital_acumulado"].iloc[-1]]})], ignore_index=True)

            fig_snow = go.Figure()
            fig_snow.add_trace(go.Scatter(x=df_hist["fecha"], y=df_hist["capital_acumulado"], fill='tozeroy', mode='lines', line=dict(color="#d4af37", width=3), fillcolor="rgba(212, 175, 55, 0.15)", name="Capital Inyectado"))
            color_b = "#34d399" if total_portafolio >= df_hist["capital_acumulado"].iloc[-1] else "#fb7185"
            fig_snow.add_trace(go.Scatter(x=[df_hist["fecha"].iloc[0], df_hist["fecha"].iloc[-1]], y=[total_portafolio, total_portafolio], mode='lines', line=dict(color=color_b, width=2, dash='dash'), name="Valor Portafolio Hoy"))
            fig_snow.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=10, b=10, l=10, r=10), height=300, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_snow, use_container_width=True)
    
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-top:20px; margin-bottom:15px; letter-spacing:1px;'>CIO Virtual: Earnings & Macro</h4>", unsafe_allow_html=True)
    if not summary.empty:
        if st.button("📊 Generar Reporte de Earnings & Macro (IA)", use_container_width=True):
            with st.spinner("Redactando informe del CIO..."):
                try:
                    k = str(st.secrets["GEMINI_API_KEY"]).strip()
                    import requests
                    assets = ", ".join(summary["ticker"].tolist())
                    prompt_cio = f"Eres el CIO de un Family Office. Activos: {assets}. Escribe un 'Resumen Ejecutivo Semanal' enfocado en próximos reportes trimestrales (Earnings) y política de dividendos, cruzando con contexto macro. Usa viñetas."
                    r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers={'Content-Type':'application/json','x-goog-api-key':k}, json={"contents":[{"parts":[{"text":prompt_cio}]}],"generationConfig":{"temperature":0.3}})
                    if r.status_code == 200: st.session_state["cio_report"] = r.json()['candidates'][0]['content']['parts'][0]['text']
                except: st.error("Configura tu API Key de Gemini.")
        if st.session_state.get("cio_report"):
            st.markdown(f"<div class='m-card'><p style='color:#cbd5e1; font-size:0.95rem; line-height:1.6; white-space:pre-wrap;'>{st.session_state['cio_report']}</p></div>", unsafe_allow_html=True)

with tab5: # HISTORIAL Y CAJA
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;'>Libro Mayor de Transacciones</h4>", unsafe_allow_html=True)
    if not tx_df.empty:
        st.dataframe(tx_df[["fecha", "tipo_operacion", "ticker", "titulos", "precio_unitario", "total_mxn"]].sort_values("fecha", ascending=False).style.format({"titulos": "{:.4f}", "precio_unitario": "${:,.2f}", "total_mxn": "${:,.2f}"}), hide_index=True, use_container_width=True)
    else: st.caption("Aún no tienes transacciones registradas.")
    
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-top:20px; margin-bottom:15px; letter-spacing:1px;'>Flujo de Tesorería</h4>", unsafe_allow_html=True)
    if not cash_df.empty:
        st.dataframe(cash_df[["fecha", "tipo", "concepto", "monto_mxn"]].sort_values("fecha", ascending=False).style.format({"monto_mxn": "${:,.2f}"}), hide_index=True, use_container_width=True)
    else: st.caption("Aún no tienes movimientos de caja registrados.")
