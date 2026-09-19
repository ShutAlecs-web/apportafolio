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

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="CMA Terminal | Private Wealth",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. ESTILOS NEÓN INSTITUCIONALES
st.markdown("""<style translate="no" class="notranslate">
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Inter:wght@400;500;700&display=swap');
.stApp { background-color: #06070a !important; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #e5e7eb; }
.ticker-bar { background: #0d1117; border-bottom: 1px solid #1f2937; padding: 10px 20px; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; border-radius: 8px; margin-bottom: 24px; }
.metric-card { background: linear-gradient(145deg, #0d1117 0%, #11141d 100%); border: 1px solid #1e2533; border-radius: 12px; padding: 18px 20px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.8); transition: 0.2s; }
.metric-card:hover { transform: translateY(-2px); border-color: #2d3748; }
.metric-title { color: #a8b3bf; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; margin-bottom: 6px; }
.metric-value { font-family: 'JetBrains Mono', monospace; font-size: 1.55rem; font-weight: 800; color: #ffffff; }
.metric-subtext { font-size: 0.78rem; margin-top: 6px; font-weight: 500; }
.text-neon-green { color: #00ff88; } .text-neon-red { color: #ff3366; } .text-neon-cyan { color: #00f0ff; }
.text-neon-purple { color: #c084fc; } .text-neon-gold { color: #fbbf24; }
.pos-box { background-color: #11131c; border: 1px solid #1f2937; border-radius: 12px; padding: 20px; margin-top: 15px; }
.pos-row { display: flex; justify-content: space-between; margin-bottom: 15px; }
.pos-label { color: #a8b3bf; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; margin-bottom: 4px; display: block; }
.pos-val { color: #ffffff; font-size: 1.15rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.pos-green { color: #00ff88; font-size: 0.95rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; } 
.pos-red { color: #ff3366; font-size: 0.95rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
#MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>""", unsafe_allow_html=True)

# Escudo Anti-Hackeos Básicos
def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

PROMPT_MAESTRO = """
Eres el 'Motor Algorítmico V5', un analista cuantitativo y macroeconómico de inteligencia artificial, diseñado para operar sin emociones, sin FOMO y con pura frialdad matemática. Tu objetivo es proporcionar una radiografía táctica ('Due Diligence') de un activo financiero.

DATOS DEL ACTIVO A ANALIZAR:
- Ticker: {ticker}
- Precio Actual: {current_price} USD
- Rango 52 Semanas: {low_52w} - {high_52w}
- Ratio P/E: {pe_ratio}
- EPS: {eps}

DATOS DEL PORTAFOLIO DEL USUARIO:
- Costo Promedio (Entry): {avg_cost}
- Rendimiento Actual: {net_return_pct}%
- Peso en el Portafolio: {portfolio_weight}%

CONTEXTO MACROECONÓMICO Y NOTICIAS RECIENTES:
{macro_news_context}

CALENDARIO ECONÓMICO INMINENTE:
{fed_cpi_events}

REGLAS DE DECISIÓN V5:
1. Analiza la valoración (P/E y EPS) frente al precio actual y el rango de 52 semanas.
2. Evalúa el peso del portafolio. Si el activo ya representa un porcentaje muy alto (>15%), penaliza el rating de compra para evitar sobreexposición, sugiriendo mantener (HOLD).
3. Pondera agresivamente el contexto macroeconómico. Si hay tensión geopolítica grave o tipos de interés hostiles, reduce el rating. Si las noticias son catalizadores positivos, auméntalo.
4. Tu análisis debe justificar si es momento de 'DCA FUERTE' (compra escalonada en caídas), 'ZONA DE COMPRA' (entrada táctica), 'HOLD' (mantener inactivo), o 'ESPERAR' (riesgo de caída inminente).

INSTRUCCIÓN DE SALIDA ESTRICTA:
Responde ÚNICA Y EXCLUSIVAMENTE con un objeto JSON válido. No uses bloques de código, introducciones ni conclusiones. Solo el JSON puro con esta estructura exacta:

{{
  "verdict": "DCA FUERTE",
  "rating": 8,
  "bull_points": [
    "Punto positivo 1",
    "Punto positivo 2"
  ],
  "bear_points": [
    "Punto negativo/riesgo 1",
    "Punto negativo/riesgo 2"
  ],
  "macro_synthesis": "Síntesis profunda de 2 a 3 líneas del impacto global."
}}
"""

ASSET_CLASS = {
    "ISAC": "ETF", "XNAS": "ETF", "XDWH": "ETF", "EIMI": "ETF", "NUCL": "ETF",
    "GOOGL": "Acción", "MELI": "Acción", "NOW": "Acción",
    "ASML": "Acción", "NVO": "Acción", "MA": "Acción", "V": "Acción", "BTC": "Cripto"
}
ASSET_SECTOR = {
    "ISAC": "Renta Variable Global", "XNAS": "Tecnología (Índice)", "XDWH": "Salud Global", "EIMI": "Mercados Emergentes", "NUCL": "Energía/Utilities",
    "GOOGL": "Servicios de Comunicación", "MELI": "Comercio Electrónico", "NOW": "Software B2B",
    "ASML": "Semiconductores", "NVO": "Biotecnología / Salud", "MA": "Servicios Financieros", "V": "Servicios Financieros", "BTC": "Criptoactivos"
}

@st.cache_data(ttl=300, max_entries=50)
def get_live_usd():
    try: return float(yf.Ticker("MXN=X").fast_info.last_price)
    except: return 19.50

live_usd_rate = get_live_usd()

# 3. BASE DE DATOS POSTGRESQL
def get_connection(): 
    return psycopg2.connect(st.secrets["DATABASE_URL"])
    
def hash_password(password: str) -> str: 
    return hashlib.sha256(password.encode()).hexdigest()

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
    except Exception: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
        
    cur.execute(
        "INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", 
        ("USR-001", "alex_admin", hash_password(admin_pwd), "MENSUAL", "Fondo Institucional")
    )
    cur.close()
    conn.close()

init_db()

if "user_id" not in st.session_state: st.session_state["user_id"] = None

if st.session_state["user_id"] is None:
    # --- CSS EXCLUSIVO PORTADA 3.2 (Deep Quant / Ocean Blue + Cyan) ---
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Anton&family=Space+Mono:wght@400;700&display=swap');

    /* 1. Fondo Océano Profundo / Datos */
    [data-testid="stAppViewContainer"], .stApp {
        background: linear-gradient(rgba(2, 6, 23, 0.8), rgba(2, 6, 23, 0.95)), 
                    url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=3000&auto=format&fit=crop') no-repeat center center fixed !important;
        background-size: cover !important;
    }
    
    /* 2. HUD Lines en Cyan Neón */
    .stApp::before { content: ""; position: fixed; top: 18%; left: 0; right: 0; height: 1px; background: rgba(0, 240, 255, 0.3); z-index: 0; pointer-events: none; }
    .stApp::after { content: ""; position: fixed; top: 0; bottom: 0; left: 8%; width: 1px; background: rgba(0, 240, 255, 0.3); z-index: 0; pointer-events: none; }
    header[data-testid="stHeader"] { background-color: transparent !important; }

    /* 3. Tipografía Gigante Tecnológica */
    .hud-brand { font-family: 'Space Mono', monospace; font-size: 0.8rem; color: #94a3b8; letter-spacing: 4px; margin-bottom: 40px; font-weight: 700; text-transform: uppercase; }
    .hud-badge { display: inline-block; border: 1px solid rgba(0,240,255,0.5); padding: 4px 15px; font-family: 'Space Mono', monospace; font-size: 0.7rem; color: #00f0ff; margin-bottom: 10px; letter-spacing: 2px; text-transform: uppercase; background: rgba(0,240,255,0.05); }
    
    .hud-giant-1 { font-family: 'Anton', sans-serif; font-size: 8rem; line-height: 0.85; color: #ffffff; margin: 0; letter-spacing: 1px; }
    .hud-giant-2 { font-family: 'Anton', sans-serif; font-size: 8rem; line-height: 0.85; color: #00f0ff; margin: 0; letter-spacing: 1px; text-shadow: 0 0 30px rgba(0, 240, 255, 0.2); }
    
    .hud-desc { font-family: 'Space Mono', monospace; font-size: 0.9rem; color: #cbd5e1; margin-top: 30px; border-left: 2px solid #00f0ff; padding-left: 15px; max-width: 420px; line-height: 1.6; }

    /* 4. Tarjeta de Login (Cristal Azulado) */
    [data-testid="stForm"] {
        background: rgba(2, 6, 23, 0.6) !important;
        border: 1px solid rgba(0, 240, 255, 0.2) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
        padding: 2.5rem !important;
        border-radius: 0px !important; 
        box-shadow: 0 20px 50px rgba(0,0,0,0.8) !important;
        position: relative;
        margin-top: 100px;
    }
    [data-testid="stForm"]::before { content: ''; position: absolute; top: -1px; left: -1px; width: 20px; height: 20px; border-top: 2px solid #00f0ff; border-left: 2px solid #00f0ff; }
    [data-testid="stForm"]::after { content: ''; position: absolute; bottom: -1px; right: -1px; width: 20px; height: 20px; border-bottom: 2px solid #00f0ff; border-right: 2px solid #00f0ff; }

    [data-testid="stForm"] label { color: #94a3b8 !important; font-family: 'Space Mono', monospace !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 2px;}
    [data-testid="stForm"] input { background: rgba(0, 0, 0, 0.4) !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; color: #00f0ff !important; font-family: 'Space Mono', monospace !important; border-radius: 0 !important; padding: 0.8rem !important; }
    [data-testid="stForm"] input:focus { border-color: #00f0ff !important; box-shadow: none !important; background: rgba(0, 0, 0, 0.7) !important; }

    [data-testid="stFormSubmitButton"] button {
        background: rgba(0, 240, 255, 0.1) !important; color: #00f0ff !important; border: 1px solid #00f0ff !important; font-weight: 700 !important; font-family: 'Space Mono', monospace !important; border-radius: 0 !important; padding: 0.9rem !important; margin-top: 20px !important; text-transform: uppercase !important; letter-spacing: 3px !important; width: 100%; transition: all 0.3s ease !important;
    }
    [data-testid="stFormSubmitButton"] button:hover { background: #00f0ff !important; color: #000000 !important; box-shadow: 0 0 25px rgba(0,240,255,0.4) !important;}
    </style>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([0.2, 2.5, 1.5, 0.2])
    with c2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("<div class='hud-brand'>APPORTAFOLIO // SYS</div>", unsafe_allow_html=True)
        st.markdown("<div class='hud-badge'>QUANTITATIVE EDGE</div>", unsafe_allow_html=True)
        st.markdown("<h1 class='hud-giant-1'>TERMINAL</h1>", unsafe_allow_html=True)
        st.markdown("<h1 class='hud-giant-2'>APPORTAFOLIO.</h1>", unsafe_allow_html=True)
        st.markdown("<p class='hud-desc'>Infraestructura de Grado Institucional. Procesamiento de datos y modelado de riesgos en tiempo real.</p>", unsafe_allow_html=True)
        
    with c3:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        with st.form("login_form"):
            usr = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Acceder", use_container_width=True):
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
st.stop()

# 4. GESTIÓN MULTI-CLIENTE
user_id = st.session_state["user_id"]
conn = get_connection()
all_users = pd.read_sql("SELECT user_id, username FROM users", conn)
conn.close()

if user_id == "USR-001":
    st.sidebar.markdown("### 👑 Panel de Gestor (Admin)")
    client_dict = dict(zip(all_users["username"], all_users["user_id"]))
    selected_client_name = st.sidebar.selectbox("Seleccionar Cliente Activo:", list(client_dict.keys()))
    active_client_id = client_dict[selected_client_name]
    active_username = selected_client_name 
    
    with st.sidebar.expander("➕ Registrar Nuevo Cliente", expanded=False):
        with st.form("new_client_form"):
            new_usr = st.text_input("Nombre de Usuario (ej. Hermano_CMA)")
            new_pwd = st.text_input("Contraseña Temporal", type="password")
            if st.form_submit_button("Crear Perfil"):
                if new_usr and new_pwd:
                    new_id = f"USR-{int(datetime.now().timestamp())}"
                    conn = get_connection()
                    cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO users (user_id, username, password_hash) VALUES (%s, %s, %s)", (new_id, new_usr, hash_password(new_pwd)))
                        conn.commit()
                        st.success(f"Cliente {new_usr} creado con éxito. Recarga la página.")
                    except Exception: st.error("El nombre de usuario ya existe.")
                    cur.close()
                    conn.close()
else:
    active_client_id = user_id
    active_username = all_users.loc[all_users["user_id"] == user_id, "username"].values[0]
    st.sidebar.markdown(f"**Cliente:** `{active_username}`")

if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
    st.session_state["user_id"] = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 👁️ Experiencia de Usuario")
st.sidebar.toggle("🔬 Activar Modo Pro", key="modo_pro_toggle", help="Muestra herramientas institucionales (XIRR, Due Diligence, Riesgo).")

with st.sidebar.expander("⚙️ Estrategia y Perfil", expanded=False):
    st.markdown("<p style='font-size:0.8rem; color:#8b949e;'>Personaliza tu experiencia financiera.</p>", unsafe_allow_html=True)
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
        f_goal = st.text_input("Nombre de tu Meta 🎯", value=current_goal, max_chars=30)
        st.markdown("<hr style='margin:10px 0; border-color:#1f2937;'>", unsafe_allow_html=True)
        old_pwd = st.text_input("Contraseña Actual (Confirmar)", type="password")
        new_pwd = st.text_input("Nueva Contraseña (Opcional)", type="password")
        if st.form_submit_button("Guardar Cambios", use_container_width=True):
            if not old_pwd: st.error("⚠️ Ingresa tu clave actual.")
            else:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,))
                current_hash = cur.fetchone()[0]
                if current_hash == hash_password(old_pwd):
                    if new_pwd and len(new_pwd) >= 6: cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password(new_pwd), f_dca, f_goal, user_id))
                    else: cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
                    conn.commit()
                    st.success("✅ Perfil actualizado.")
                else: st.error("❌ Clave incorrecta.")
                cur.close()
                conn.close()

st.sidebar.markdown("### 📥 Reportes Institucionales")
conn_export = get_connection()
export_df = pd.read_sql("SELECT * FROM transactions WHERE user_id=%s", conn_export, params=(active_client_id,))
conn_export.close()

if not export_df.empty:
    clean_df = export_df.drop(columns=["id", "user_id", "timestamp"], errors="ignore")
    clean_df.rename(columns={"fecha": "Fecha", "tipo_operacion": "Tipo", "ticker": "Activo", "clase": "Clase", "plataforma": "Plataforma", "moneda": "Moneda", "titulos": "Títulos", "precio_unitario": "Precio Unitario", "comision": "Comisión", "iva": "IVA", "tipo_cambio": "Tipo de Cambio", "total_mxn": "Total MXN"}, inplace=True)
    col_dl1, col_dl2 = st.sidebar.columns(2)
    with col_dl1: st.download_button("📊 CSV", data=clean_df.to_csv(index=False).encode('utf-8'), file_name=f"Portafolio_{active_username}.csv", mime="text/csv", use_container_width=True)
    with col_dl2:
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: clean_df.to_excel(writer, index=False, sheet_name='CMA_Terminal')
            st.download_button("📗 Excel", data=buffer.getvalue(), file_name=f"Portafolio_{active_username}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except: st.download_button("📗 Excel", data=clean_df.to_csv(index=False, sep=";").encode('latin1'), file_name=f"Portafolio_{active_username}_EXCEL.csv", mime="text/csv", use_container_width=True)
else: st.sidebar.button("📊 Sin datos", disabled=True, use_container_width=True)

if active_client_id == "USR-001":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Control Operativo (Admin)")
    st.sidebar.markdown("<p style='font-size:0.8rem; color:#8b949e;'>1. Buscar activo y cotización</p>", unsafe_allow_html=True)
    col_b1, col_b2 = st.sidebar.columns([2, 1])
    with col_b1: search_ticker = st.text_input("Ticker", key="search_t", label_visibility="collapsed", placeholder="Ej. AAPL, O, BTC-USD...")
    with col_b2:
        if st.button("Validar", use_container_width=True):
            if search_ticker:
                tk_sym = sanitize_ticker(search_ticker)
                with st.spinner("..."):
                    try:
                        tk_data = yf.Ticker(tk_sym)
                        p = tk_data.fast_info.last_price
                        if p:
                            st.session_state["val_ticker"] = tk_sym
                            st.session_state["val_price"] = float(p)
                            st.sidebar.success(f"✅ ${p:.2f}")
                        else: st.sidebar.error("❌ Sin datos.")
                    except: st.sidebar.error("❌ Inválido.")
            else: st.sidebar.warning("Escribe un ticker.")

    val_t = st.session_state.get("val_ticker", "")
    val_p = float(st.session_state.get("val_price", 0.0))

    with st.sidebar.expander("🛒 Registrar Operación", expanded=True):
        with st.form("form_nueva_compra"):
            f_tipo_op = st.selectbox("Tipo de Operación", ["COMPRA", "VENTA"])
            f_ticker = st.text_input("Activo (Ticker)", value=val_t)
            f_clase = st.selectbox("Clase de Activo", ["ACCION", "ETF", "FIBRA/REIT", "CRIPTO"])
            f_plat = st.selectbox("Plataforma", ["GBM_SIC", "GBM_USA", "BINGX", "BITSO"])
            f_moneda = st.selectbox("Moneda", ["MXN", "USD"])
            f_titulos = st.number_input("Títulos / Fracción", min_value=0.00000, format="%.5f", step=0.01)
            f_precio = st.number_input("Precio Unitario", min_value=0.0, value=val_p, format="%.2f", step=1.0)
            f_comision = st.number_input("Comisión", min_value=0.0, format="%.2f")
            f_iva = st.number_input("IVA", min_value=0.0, format="%.3f")
            f_tc = st.number_input("Tipo de Cambio (Live)", min_value=1.0, value=live_usd_rate, format="%.4f")
            f_fecha = st.date_input("Fecha", value=datetime.today())
            
            if st.form_submit_button("Ejecutar Operación", use_container_width=True):
                f_ticker_clean = sanitize_ticker(f_ticker)
                if f_ticker_clean and f_titulos > 0 and f_precio > 0:
                    valor_bruto_mxn = (f_titulos * f_precio) * f_tc
                    costos_mxn = (f_comision + f_iva) * f_tc
                    
                    if f_tipo_op == "COMPRA":
                        total_op_mxn = valor_bruto_mxn + costos_mxn
                        impacto_caja = -total_op_mxn
                        titulos_final = f_titulos
                    else:
                        total_op_mxn = valor_bruto_mxn - costos_mxn
                        impacto_caja = total_op_mxn
                        titulos_final = -f_titulos
                        
                    conn = get_connection()
                    cur = conn.cursor()
                    ts_id = datetime.now().timestamp()
                    
                    cur.execute("INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 
                                 (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, f_ticker_clean, f_clase, f_plat, f_moneda, titulos_final, f_precio, f_comision, f_iva, f_tc, total_op_mxn))
                    cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", 
                                 (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {f_ticker_clean}", impacto_caja))
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    st.session_state["val_ticker"] = ""
                    st.session_state["val_price"] = 0.0
                    st.success(f"✅ {f_tipo_op} de {f_ticker_clean} registrada exitosamente.")
                    st.rerun()
                else: st.error("⚠️ Verifica el Ticker, Títulos y Precio.")

    with st.sidebar.expander("💸 Tesorería (Ingresos/Egresos)", expanded=False):
        with st.form("form_nuevo_deposito"):
            c_tipo_op = st.selectbox("Tipo de Movimiento", ["DEPOSITO", "RETIRO"])
            f_concepto = st.text_input("Concepto", placeholder="Ej: Fondeo DCA")
            f_monto = st.number_input("Monto (MXN)", min_value=1.0, step=500.0)
            f_dep_fecha = st.date_input("Fecha de Registro", value=datetime.today())
            if st.form_submit_button("Actualizar Tesorería", use_container_width=True):
                monto_final = f_monto if c_tipo_op == "DEPOSITO" else -f_monto
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-TES-{datetime.now().timestamp()}", active_client_id, str(f_dep_fecha), c_tipo_op, f_concepto, float(monto_final)))
                conn.commit()
                cur.close()
                conn.close()
                st.success("Caja actualizada exitosamente.")
                st.rerun()

# 5. CARGA DE DATOS PARA EL CLIENTE ACTIVO
conn = get_connection()
tx_df = pd.read_sql("SELECT * FROM transactions WHERE user_id=%s", conn, params=(active_client_id,))
cash_df = pd.read_sql("SELECT * FROM cash_movements WHERE user_id=%s", conn, params=(active_client_id,))
conn.close()

def calc_liquidez_real(df_caja):
    if df_caja.empty: return 0.0
    inflows  = {"DEPOSITO", "VENTA", "DIVIDENDO"}
    outflows = {"COMPRA", "RETIRO", "COMISION", "IMPUESTO"}
    total = 0.0
    for _, row in df_caja.iterrows():
        monto = abs(float(row["monto_mxn"]))
        if row["tipo"] in inflows: total += monto
        elif row["tipo"] in outflows: total -= monto
    return max(total, 0.0)

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
    download_list = list(set(yf_tickers + macro_tickers))
    data = yf.download(download_list, period="1mo", progress=False)
    
    def get_latest(symbol):
        try: return float(data["Close"][symbol].dropna().iloc[-1])
        except: return 0.0
        
    def get_chg(symbol):
        try: 
            s = data["Close"][symbol].dropna()
            return ((float(s.iloc[-1]) - float(s.iloc[-2])) / float(s.iloc[-2])) * 100
        except: return 0.0

    usd = get_latest("USDMXN=X") or 18.50
    sp500_chg = get_chg("^GSPC")
    ndx_chg = get_chg("^NDX")
    dji_chg = get_chg("^DJI")
    gold_price = get_latest("GC=F")
    btc_price = get_latest("BTC-USD")
    
    pxs_mxn, pxs_usd, spark_data = {}, {}, {}
    if tickers:
        for t in tickers:
            try:
                yf_symbol = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
                raw_usd_series = data["Close"][yf_symbol].dropna()
                hist_prices_mxn = (raw_usd_series * usd).tolist()
                spark_data[t] = hist_prices_mxn
                pxs_usd[t] = raw_usd_series.iloc[-1] if not raw_usd_series.empty else 0.0
                pxs_mxn[t] = hist_prices_mxn[-1] if hist_prices_mxn else fallback.get(t, 0.0)
            except Exception: 
                pxs_mxn[t] = fallback.get(t, 0.0)
                pxs_usd[t] = 0.0
                spark_data[t] = [fallback.get(t, 0.0)] * 10
                
    return pxs_mxn, pxs_usd, spark_data, usd, sp500_chg, ndx_chg, dji_chg, gold_price, btc_price

# OBTENEDOR DE YIELD (SALARIO INVISIBLE)
@st.cache_data(ttl=86400, max_entries=50)
def get_asset_yields(tickers):
    yields = {}
    for t in tickers:
        try:
            yf_sym = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
            inf = yf.Ticker(yf_sym).info
            y = inf.get('dividendYield') or inf.get('trailingAnnualDividendYield') or 0.0
            yields[t] = float(y)
        except:
            yields[t] = 0.0
    return yields

if not tx_df.empty:
    summary = tx_df.groupby("ticker").agg(titulos=("titulos", "sum")).reset_index()
    summary = summary[summary["titulos"] > 0]
    compras_df = tx_df[tx_df["tipo_operacion"] == "COMPRA"]
    costos = compras_df.groupby("ticker").agg(titulos_comprados=("titulos", "sum"), total_invertido=("total_mxn", "sum")).reset_index()
    costos["costo_promedio"] = costos["total_invertido"] / costos["titulos_comprados"]
    summary = pd.merge(summary, costos[["ticker", "costo_promedio"]], on="ticker", how="left")
    summary["costo_total"] = summary["titulos"] * summary["costo_promedio"]
    summary["Clase"] = summary["ticker"].map(lambda t: ASSET_CLASS.get(t, "Otro"))
    summary["Sector"] = summary["ticker"].map(lambda t: ASSET_SECTOR.get(t, "Desconocido"))
    
    fallback_dict = dict(zip(summary["ticker"], summary["costo_promedio"]))
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, sp500_chg, ndx_chg, dji_chg, gold_price, btc_price = get_prices_and_sparklines(summary["ticker"].tolist(), fallback_dict)
    
    summary["precio_mercado"] = summary["ticker"].map(precios_mxn)
    summary["precio_mercado_usd"] = summary["ticker"].map(precios_usd_dict)
    summary["Tendencia (30D)"] = summary["ticker"].map(sparklines)
    summary["valor_actual"] = summary["titulos"] * summary["precio_mercado"]
    summary["pnl"] = summary["valor_actual"] - summary["costo_total"]
    summary["retorno_pct"] = (summary["pnl"] / summary["costo_total"]) * 100
    
    # Cálculo de Ingresos Pasivos
    asset_yields = get_asset_yields(summary["ticker"].tolist())
    summary["yield_pct"] = summary["ticker"].map(asset_yields)
    summary["ingreso_pasivo"] = summary["valor_actual"] * summary["yield_pct"]
    salario_invisible = summary["ingreso_pasivo"].sum()
    
    total_activos = float(summary["valor_actual"].sum())
    total_invertido = float(summary["costo_total"].sum())
else:
    summary = pd.DataFrame(columns=["ticker", "Clase", "Sector", "titulos", "costo_promedio", "precio_mercado", "precio_mercado_usd", "valor_actual", "pnl", "retorno_pct", "Tendencia (30D)", "yield_pct", "ingreso_pasivo"])
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, sp500_chg, ndx_chg, dji_chg, gold_price, btc_price = get_prices_and_sparklines([], {})
    total_activos = 0.0
    total_invertido = 0.0
    salario_invisible = 0.0

total_portafolio = total_activos + liquidez_mxn
pnl_global = total_activos - total_invertido
retorno_global = (pnl_global / total_invertido) * 100 if total_invertido > 0 else 0.0
if not summary.empty: summary["ponderacion_pct"] = (summary["valor_actual"] / total_portafolio) * 100
else: summary["ponderacion_pct"] = 0.0

# 6. TICKER TAPE
@st.cache_data(ttl=300, max_entries=50)
def get_market_data():
    symbols = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI", "Oro": "GC=F", "Plata": "SI=F", "Petróleo WTI": "CL=F", "USD/MXN": "MXN=X", "EUR/MXN": "EURMXN=X", "BTC/USD": "BTC-USD"}
    data = {}
    for name, tk in symbols.items():
        try:
            info = yf.Ticker(tk).fast_info
            price, prev_close = info.last_price, info.previous_close
            data[name] = {"price": price, "pct": ((price - prev_close) / prev_close) * 100}
        except: data[name] = {"price": 0.0, "pct": 0.0}
    return data

market_data = get_market_data()
ticker_html = "<marquee behavior='scroll' direction='left' scrollamount='6' style='font-family: monospace; font-size: 0.95rem; padding: 12px 0;'>&nbsp;&nbsp;&nbsp;&nbsp;🟢 <b style='color:#00ff88;'>EN VIVO</b> &nbsp;&nbsp;|&nbsp;&nbsp;"
for name, stats in market_data.items():
    color = "#00ff88" if stats['pct'] >= 0 else "#ff3366"
    sign = "+" if stats['pct'] >= 0 else ""
    if name == "BTC/USD": price_str = f"${stats['price']:,.0f}"
    elif "MXN" in name: price_str = f"${stats['price']:.4f}"
    else: price_str = f"${stats['price']:,.2f}"
    ticker_html += f"<span style='color: #8b949e;'>{name}:</span> <span style='color: white; font-weight: bold;'>{price_str}</span> <span style='color: {color};'>({sign}{stats['pct']:.2f}%)</span> &nbsp;&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;&nbsp;"
ticker_html += "</marquee>"
st.markdown(f"<div style='background-color: #0d1117; border: 1px solid #1f2937; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);'>{ticker_html}</div>", unsafe_allow_html=True)

# 7. KPIS PRINCIPALES
k1, k2, k3, k4 = st.columns(4)
tt_pat = "Todo el dinero que tienes actualmente, sumando tus ganancias y tu efectivo."
tt_cap = "El dinero exacto que ha salido de tu bolsillo hacia la aplicación."
tt_liq = "Dinero en efectivo listo para comprar oportunidades en el mercado."
tt_pnl = "Profit & Loss (Pérdidas o Ganancias Totales de tus inversiones)."

k1.markdown(f"<div class='metric-card notranslate' title='{tt_pat}' translate='no'><div class='metric-title'>Patrimonio Total ❓</div><div class='metric-value'>${total_portafolio:,.2f}</div></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='metric-card notranslate' title='{tt_cap}' translate='no'><div class='metric-title'>Capital Invertido ❓</div><div class='metric-value'>${total_invertido:,.2f}</div></div>", unsafe_allow_html=True)

if st.session_state.get("modo_pro_toggle", False):
    k3.markdown(f"<div class='metric-card notranslate' title='{tt_liq}' translate='no'><div class='metric-title'>Liquidez Disponible ❓</div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    c_pnl = "text-neon-green" if pnl_global >= 0 else "text-neon-red"
    k4.markdown(f"<div class='metric-card notranslate' title='{tt_pnl}' translate='no'><div class='metric-title'>P&L Neto Acumulado ❓</div><div class='metric-value {c_pnl}'>${pnl_global:+,.2f}</div><div class='metric-subtext {c_pnl}'>{retorno_global:+.2f}%</div></div>", unsafe_allow_html=True)
else:
    ganancia_neta = pnl_global
    c_gan = "#00ff88" if ganancia_neta >= 0 else "#ff3366"
    texto_simple = "Ganancia Generada" if ganancia_neta >= 0 else "Pérdida Temporal"
    k3.markdown(f"<div class='metric-card notranslate' title='{tt_liq}' translate='no'><div class='metric-title'>Dinero en Efectivo ❓</div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-card notranslate' title='Lo que tus inversiones han producido para ti.' translate='no'><div class='metric-title'>{texto_simple} ❓</div><div class='metric-value' style='color:{c_gan};'>${ganancia_neta:+,.2f}</div></div>", unsafe_allow_html=True)

# 7.8 GRÁFICA BOLA DE NIEVE
st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>📈 LA BOLA DE NIEVE (HISTÓRICO DE CAPITAL)</h4>", unsafe_allow_html=True)
if not cash_df.empty:
    df_hist = cash_df[cash_df["tipo"].isin(["DEPOSITO", "RETIRO"])].copy()
    if not df_hist.empty:
        df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
        df_hist = df_hist.sort_values("fecha")
        def calc_flujo(row):
            val = abs(float(row["monto_mxn"]))
            return val if row["tipo"] == "DEPOSITO" else -val
            
        df_hist["flujo_neto"] = df_hist.apply(calc_flujo, axis=1)
        df_hist["capital_acumulado"] = df_hist["flujo_neto"].cumsum()
        
        df_hoy = pd.DataFrame({"fecha": [pd.to_datetime(datetime.today().date())], "capital_acumulado": [df_hist["capital_acumulado"].iloc[-1]]})
        df_hist = pd.concat([df_hist, df_hoy], ignore_index=True)

        fig_snow = go.Figure()
        fig_snow.add_trace(go.Scatter(
            x=df_hist["fecha"], y=df_hist["capital_acumulado"], fill='tozeroy', mode='lines+markers',
            line=dict(color="#c084fc", width=3), marker=dict(size=6, color="#c084fc", symbol="circle"),
            fillcolor="rgba(192, 132, 252, 0.15)", name="Capital Invertido (Tu esfuerzo)", hovertemplate="<b>Fecha:</b> %{x|%d %b, %Y}<br><b>Capital Acumulado:</b> $%{y:,.2f} MXN<extra></extra>"
        ))
        
        color_brecha = "#00ff88" if total_portafolio >= df_hist["capital_acumulado"].iloc[-1] else "#ff3366"
        fig_snow.add_trace(go.Scatter(
            x=[df_hist["fecha"].iloc[0], df_hist["fecha"].iloc[-1]], y=[total_portafolio, total_portafolio],
            mode='lines', line=dict(color=color_brecha, width=2, dash='dash'), name="Valor Actual del Portafolio", hovertemplate="<b>Valor Actual:</b> $%{y:,.2f} MXN<extra></extra>"
        ))

        fig_snow.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode="x unified")
        fig_snow.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937", showgrid=True)
        fig_snow.update_yaxes(gridcolor="#1f2937", zerolinecolor="#1f2937", showgrid=True, tickprefix="$")
        st.plotly_chart(fig_snow, use_container_width=True)
    else: st.info("💡 Realiza tu primer depósito en la Tesorería para ver crecer tu Bola de Nieve.")
else: st.info("💡 Realiza tu primer depósito en la Tesorería para ver crecer tu Bola de Nieve.")

# 7.5 GAMIFICACIÓN
st.markdown("<br><h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🏆 PROGRESO Y FUTURO (SMART DCA)</h4>", unsafe_allow_html=True)
conn = get_connection()
cur = conn.cursor()
try:
    cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (active_client_id,))
    user_data = cur.fetchone()
    user_freq, meta_nombre = user_data[0], user_data[1]
except: user_freq, meta_nombre = "MENSUAL", "Libertad Financiera"
cur.close()
conn.close()

def get_period_index(date_str, freq):
    dt = pd.to_datetime(date_str)
    if freq == "SEMANAL": return int(dt.timestamp() // (7 * 86400))
    elif freq == "QUINCENAL": return dt.year * 24 + dt.month * 2 + (0 if dt.day <= 15 else 1)
    else: return dt.year * 12 + dt.month

racha_actual, racha_maxima, ahorro_racha = 0, 0, 0.0
txt_frecuencia = "Semanas" if user_freq == "SEMANAL" else ("Quincenas" if user_freq == "QUINCENAL" else "Meses")

if not cash_df.empty:
    dep_df = cash_df[cash_df["tipo"] == "DEPOSITO"].copy()
    if not dep_df.empty:
        dep_df["period_idx"] = dep_df["fecha"].apply(lambda x: get_period_index(x, user_freq))
        dep_idx = dep_df.groupby("period_idx")["monto_mxn"].sum().reset_index()
        periodos = sorted(dep_idx["period_idx"].tolist(), reverse=True)
        p_eval = get_period_index(datetime.today(), user_freq)
        if periodos and periodos[0] < p_eval: p_eval -= 1
            
        for p in periodos:
            if p == p_eval:
                racha_actual += 1
                ahorro_racha += float(dep_idx[dep_idx["period_idx"] == p]["monto_mxn"].iloc[0])
                p_eval -= 1
            elif p > p_eval: continue
            else: break
                
        p_asc = sorted(dep_idx["period_idx"].tolist())
        curr_strk = 1 if p_asc else 0
        max_strk = curr_strk
        if p_asc:
            for i in range(1, len(p_asc)):
                if p_asc[i] == p_asc[i-1] + 1: curr_strk += 1
                else: curr_strk = 1
                if curr_strk > max_strk: max_strk = curr_strk
        racha_maxima = max_strk

if racha_actual == 0: color_racha, emoji_racha, rango_txt = "#4b5563", "❄️", "Inactivo"
elif racha_actual <= 2: color_racha, emoji_racha, rango_txt = "#fbbf24", "✨", "Iniciador"
elif racha_actual <= 5: color_racha, emoji_racha, rango_txt = "#f97316", "🔥", "Constante"
elif racha_actual <= 11: color_racha, emoji_racha, rango_txt = "#00f0ff", "⚡", "Pro"
else: color_racha, emoji_racha, rango_txt = "#c084fc", "👑", "Leyenda"

hitos = [10000, 50000, 100000, 250000, 500000, 1000000, 2500000, 5000000, 10000000]
meta_actual = next((h for h in hitos if h > total_portafolio), hitos[-1])
progreso_meta = min((total_portafolio / meta_actual) * 100, 100)
faltante = max(0, meta_actual - total_portafolio)
tasa_anual = 0.10
aportacion_promedio = (ahorro_racha / racha_actual) if racha_actual > 0 else 0
if user_freq == "SEMANAL": pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 52, tasa_anual / 52
elif user_freq == "QUINCENAL": pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 24, tasa_anual / 24
else: pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 12, tasa_anual / 12

proyeccion_5a = (total_portafolio * ((1 + r_periodo)**n_periodos)) + (pmt * (((1 + r_periodo)**n_periodos - 1) / r_periodo)) if pmt > 0 else total_portafolio

col_g1, col_g2, col_g3 = st.columns([1.2, 1.5, 1.2])
with col_g1:
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='text-align:center; padding:15px; border-color:{color_racha}40;'>"
        f"<div class='metric-title'>Nivel DCA: <span style='color:{color_racha};'>{rango_txt}</span></div>"
        f"<div style='font-size:2.8rem; font-weight:900; color:{color_racha}; margin:5px 0;'>{racha_actual} {emoji_racha}</div>"
        f"<div class='metric-subtext' style='color:#8b949e; margin-bottom:8px;'>{txt_frecuencia} seguidas • Récord: <b style='color:white;'>{max(racha_actual, racha_maxima)}</b></div>"
        f"<div style='font-size:0.75rem; color:#00ff88; background:rgba(0,255,136,0.05); padding:6px; border-radius:6px; border:1px solid rgba(0,255,136,0.2);'>"
        f"Ahorro en racha: <b>${ahorro_racha:,.2f}</b></div></div>", unsafe_allow_html=True
    )
with col_g2:
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='padding:15px; display:flex; flex-direction:column; justify-content:center;'>"
        f"<div class='metric-title' style='color:#00f0ff;'>🎯 {meta_nombre}</div>"
        f"<div class='metric-value' style='font-size:1.1rem;'>Hito: ${meta_actual:,.2f} MXN</div>"
        f"<div style='width:100%;background-color:#1f2937;border-radius:12px;height:22px;position:relative; overflow:hidden; border: 1px solid #374151; margin-top:8px;'>"
        f"<div style='width:{progreso_meta}%;background:linear-gradient(90deg, #3b82f6 0%, #00f0ff 100%);height:100%; border-radius:12px;'></div>"
        f"</div><div class='metric-subtext' style='margin-top:12px; color:#8b949e;'>Faltan <b style='color:#e5e7eb;'>${faltante:,.2f} MXN</b></div></div>", unsafe_allow_html=True
    )
with col_g3:
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='padding:15px; border-color:#c084fc40; background:rgba(192, 132, 252, 0.02);'>"
        f"<div class='metric-title' style='color:#c084fc;'>🔮 Tu Futuro en 5 Años</div>"
        f"<div style='font-size:1.3rem; font-weight:900; color:white; margin:10px 0;'>${proyeccion_5a:,.2f}</div>"
        f"<div class='metric-subtext' style='color:#8b949e;'>Si mantienes tu racha {txt_frecuencia.lower()} de <b>${aportacion_promedio:,.0f}</b> a una tasa del 10% anual.</div></div>", unsafe_allow_html=True
    )
st.markdown("---")

# RAMIFICACIÓN MODO PRO vs MODO FÁCIL
if st.session_state.get("modo_pro_toggle", False):
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>ANÁLISIS DE RENDIMIENTO Y ATRIBUCIÓN GLOBAL</h4>", unsafe_allow_html=True)
    perf_col1, perf_col2 = st.columns([1, 2.5])

    with perf_col1:
        total_friccion = (tx_df["comision"] + tx_df["iva"]).mul(tx_df["tipo_cambio"]).sum() if not tx_df.empty else 0.0
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

        st.markdown(
            (
                f"<div style='background:#0d1117;border:1px solid #1e2533;border-radius:8px;padding:15px;margin-bottom:15px;' class='notranslate' translate='no'>"
                f"<p style='color:#8b949e;font-size:0.75rem;text-transform:uppercase;margin-bottom:5px;font-weight:bold;'>Fricción Financiera</p>"
                f"<p style='color:#ff3366;font-size:1.35rem;font-weight:800;font-family:monospace;margin:0;'>${total_friccion:,.2f} MXN</p></div>"
                f"<div style='background:#0d1117;border:1px solid #1e2533;border-radius:8px;padding:15px;margin-bottom:15px;' class='notranslate' translate='no'>"
                f"<p style='color:#8b949e;font-size:0.75rem;text-transform:uppercase;margin-bottom:5px;font-weight:bold;'>Rentabilidad Ponderada (XIRR)</p>"
                f"<p style='color:#00f0ff;font-size:1.35rem;font-weight:800;font-family:monospace;margin:0;'>{calc_xirr()}</p></div>"
            ),
            unsafe_allow_html=True
        )

    with perf_col2:
        if not summary.empty:
            attr_df = summary[summary["pnl"] != 0].copy()
            if not attr_df.empty:
                attr_df.sort_values("pnl", ascending=True, inplace=True)
                attr_df["color_pnl"] = attr_df["pnl"].apply(lambda x: "#00ff88" if x >= 0 else "#ff3366")
                fig_attr = go.Figure()
                fig_attr.add_trace(go.Bar(
                    y=attr_df["ticker"], x=attr_df["pnl"], orientation="h", marker_color=attr_df["color_pnl"],
                    text=attr_df["pnl"].apply(lambda x: f"${x:+,.0f}"), textposition="outside"
                ))
                fig_attr.update_layout(title=dict(text="Atribución Neta por Activo (MXN)", font=dict(size=14, color="#8b949e")), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=30, b=0, l=10, r=10), showlegend=False, xaxis_title="", yaxis_title="", height=280)
                fig_attr.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937")
                st.plotly_chart(fig_attr, use_container_width=True)
            else: st.info("Aún no hay P&L registrado.")
        else: st.info("Adquiere activos para medir atribución.")

    st.markdown("---")

    if "ai_memory" not in st.session_state: st.session_state["ai_memory"] = {}

    # 9. LUPA DE ACTIVOS - DUE DILIGENCE Y RATING V5
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🔍 RADIOGRAFÍA INDIVIDUAL Y RATING DE COMPRA (PROMPT V5)</h4>", unsafe_allow_html=True)
    if not summary.empty:
        selected_asset = st.selectbox("Selecciona un activo en cartera o busca uno nuevo para Deep Dive:", sorted(summary["ticker"].tolist()) + ["🔍 Buscar nuevo ticker (Ej: AAPL, SPY)"])
        if selected_asset.startswith("🔍"):
            search_ticker = st.text_input("Ingresa el Ticker de Yahoo Finance a analizar (Ej: NVDA, URA, SCHD):").upper()
            target_asset = sanitize_ticker(search_ticker) if search_ticker else None
        else: target_asset = sanitize_ticker(selected_asset)

        if target_asset:
            @st.cache_data(ttl=3600, max_entries=50)
            def fetch_asset_deep_dive(t):
                try:
                    yf_sym = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
                    tk = yf.Ticker(yf_sym)
                    hist = tk.history(period="1y")
                    info = tk.info
                    news_data = tk.news[:5] if tk.news else []
                    clean_news = []
                    for n in news_data:
                        title = n.get('title')
                        link = n.get('link')
                        if title and isinstance(title, str): 
                            if isinstance(link, str) and link.startswith('http'): safe_link = link
                            else: safe_link = f"https://finance.yahoo.com/quote/{yf_sym}"
                            clean_news.append({"title": title, "link": safe_link})
                    return hist, info, clean_news
                except: return pd.DataFrame(), {}, []

            with st.spinner(f"Extrayendo telemetría y corriendo motor de Scoring V5 para {target_asset}..."):
                hist_data, asset_info, asset_news = fetch_asset_deep_dive(target_asset)
            
            if not hist_data.empty:
                if target_asset in summary["ticker"].values:
                    pos_data = summary[summary["ticker"] == target_asset].iloc[0]
                    p_titulos, p_val_mercado, p_costo_prom, p_peso, p_retorno_total_pct, p_retorno_total_mxn = pos_data["titulos"], pos_data["valor_actual"], pos_data["costo_promedio"], pos_data["ponderacion_pct"], pos_data["retorno_pct"], pos_data["pnl"]
                    is_owned = True
                else:
                    p_titulos = p_val_mercado = p_costo_prom = p_peso = p_retorno_total_pct = p_retorno_total_mxn = 0.0
                    is_owned = False
                
                current_price = hist_data['Close'].iloc[-1]
                start_price = hist_data['Close'].iloc[0]
                pct_change_1y = ((current_price - start_price) / start_price) * 100
                color_line = "#00ff88" if pct_change_1y >= 0 else "#ff3366"
                
                pe_ratio = asset_info.get("trailingPE", "N/A")
                eps = asset_info.get("trailingEps", "N/A")
                high_52 = asset_info.get("fiftyTwoWeekHigh", current_price * 1.1)
                low_52 = asset_info.get("fiftyTwoWeekLow", current_price * 0.9)
                noticias_texto = "\n".join([f"- {n['title']}" for n in asset_news]) if asset_news else "Sin noticias relevantes recientes."

                mem_data = st.session_state["ai_memory"].get(target_asset)
                if mem_data:
                    ai_verdict = mem_data["verdict"]
                    ai_rating = mem_data["rating"]
                    ai_bulls = mem_data["bulls"]
                    ai_bears = mem_data["bears"]
                    ai_macro = mem_data["macro"]
                else:
                    ai_verdict, ai_rating, ai_bulls, ai_bears = "N/A", 5, [], []
                    ai_macro = "Motor matemático local activo. Evaluando métricas estándar."
                    error_api = ""
                    backend_api_key = None
                    try: backend_api_key = st.secrets["GEMINI_API_KEY"]
                    except Exception: pass

                    if backend_api_key:
                        current_time = time.time()
                        last_call = st.session_state.get("last_gemini_call", 0)
                        time_left = 10.0 - (current_time - last_call)
                        if time_left > 0:
                            error_api = f"Rate Limit: Espera {int(time_left)}s"
                            ai_verdict = "ERROR API"
                            st.toast(f"⏳ Escudo Anti-Baneo activo. Espera {int(time_left)}s para un nuevo análisis.", icon="🛡️")
                        else:
                            st.session_state["last_gemini_call"] = current_time
                            try:
                                import requests
                                clean_key = str(backend_api_key).strip()
                                headers = {'Content-Type': 'application/json', 'x-goog-api-key': clean_key}
                                prompt_filled = PROMPT_MAESTRO.format(ticker=target_asset, current_price=round(current_price, 2), low_52w=round(low_52, 2), high_52w=round(high_52, 2), pe_ratio=pe_ratio, eps=eps, avg_cost=round(p_costo_prom, 2), net_return_pct=round(p_retorno_total_pct, 2), portfolio_weight=round(p_peso, 2), macro_news_context=noticias_texto, fed_cpi_events="Decisiones de tasas FED, datos de IPC e inflación global en seguimiento continuo.")
                                payload = {"contents": [{"parts": [{"text": prompt_filled}]}], "generationConfig": {"temperature": 0.2}}
                                response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers=headers, json=payload)
                                if response.status_code == 200:
                                    ai_response = response.json()['candidates'][0]['content']['parts'][0]['text']
                                    clean_json = ai_response.replace(chr(96)*3 + "json", "").replace(chr(96)*3, "").strip()
                                    parsed_response = json.loads(clean_json)
                                    ai_verdict = parsed_response.get("verdict", "HOLD")
                                    ai_rating = int(parsed_response.get("rating", 5))
                                    ai_bulls = parsed_response.get("bull_points", [])
                                    ai_bears = parsed_response.get("bear_points", [])
                                    ai_macro = parsed_response.get("macro_synthesis", "")
                                    st.session_state["ai_memory"][target_asset] = {"verdict": ai_verdict, "rating": ai_rating, "bulls": ai_bulls, "bears": ai_bears, "macro": ai_macro}
                                else:
                                    ai_verdict = "ERROR API"
                                    error_api = f"Error {response.status_code}: {response.text}"
                            except Exception as e:
                                ai_verdict = "ERROR API"
                                error_api = f"Error interno: {str(e)}"
                    
                    if not backend_api_key or ai_verdict in ["N/A", "ERROR API"]:
                        score = 5.0
                        ma50 = hist_data['Close'].tail(50).mean()
                        ma200 = hist_data['Close'].mean()
                        if current_price < ma50 and current_price > ma200: score += 2.0; ai_bulls.append("Corrección saludable a corto plazo.")
                        elif current_price < ma200: score += 3.0; ai_bulls.append("Cotiza bajo su MA200. Descuento profundo.")
                        elif current_price > ma50 * 1.15: score -= 2.0; ai_bears.append("Sobrecomprado (>15% arriba de la MA50).")
                        if isinstance(pe_ratio, float):
                            if pe_ratio < 20: score += 2.0; ai_bulls.append(f"Valuación atractiva (P/E: {pe_ratio:.1f}).")
                            elif pe_ratio > 40: score -= 1.5; ai_bears.append(f"Valuación exigente/Premium (P/E: {pe_ratio:.1f}).")
                        if is_owned and p_peso > 20.0: score -= 2.0; ai_bears.append(f"Riesgo de Concentración ({p_peso:.1f}% del portafolio).")
                        ai_rating = max(1, min(10, int(score)))
                        ai_verdict = "ZONA DE COMPRA" if ai_rating >= 7 else ("HOLD" if ai_rating >= 4 else "ESPERAR")
                        if error_api: ai_macro = f"⚠️ Fallo conexión IA o Anti-Baneo activo: {error_api}"
                        elif not backend_api_key: ai_macro = "⚠️ Llave de Gemini no detectada en secrets.toml."
                        else: ai_macro = "Motor matemático local activo."

                score_color = "#00ff88" if ai_rating >= 7 else ("#fbbf24" if ai_rating >= 4 else "#ff3366")

                col_chart, col_stats = st.columns([2.5, 1])
                with col_chart:
                    fig_deep = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
                    fig_deep.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'], fill='tozeroy', mode='lines', name='Precio', line=dict(color=color_line, width=2), fillcolor=f"rgba({0 if pct_change_1y>=0 else 255}, {255 if pct_change_1y>=0 else 51}, {136 if pct_change_1y>=0 else 102}, 0.15)"), row=1, col=1)
                    fig_deep.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume'], name='Volumen', marker_color='rgba(139, 148, 158, 0.4)'), row=2, col=1)
                    fig_deep.update_layout(title=f"{target_asset} | Análisis de 1 Año", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=40,b=10,l=10,r=10), showlegend=False, xaxis2=dict(showgrid=False), yaxis=dict(gridcolor="#1f2937"), yaxis2=dict(showgrid=False, showticklabels=False))
                    st.plotly_chart(fig_deep, use_container_width=True)
                    bulls_html = "".join([f"<li style='margin-bottom:4px;'>{r}</li>" for r in ai_bulls])
                    bears_html = "".join([f"<li style='margin-bottom:4px;'>{r}</li>" for r in ai_bears])
                    st.markdown(
                        (
                            f"<div style='background:#11131c;border:1px solid {score_color};border-radius:12px;padding:20px;margin-top:10px;' class='notranslate' translate='no'>"
                            f"<div style='display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid #1f2937;padding-bottom:15px;margin-bottom:15px;'>"
                            f"<div><p style='color:#8b949e;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px;'>Veredicto Algorítmico V5</p>"
                            f"<h3 style='color:{score_color};margin:0;font-size:1.5rem;font-weight:800;'>{ai_verdict}</h3></div>"
                            f"<div style='background:{score_color};color:black;font-weight:900;font-size:1.8rem;padding:5px 15px;border-radius:8px;display:flex;align-items:center;box-shadow:0 4px 15px {score_color}40;'>"
                            f"{ai_rating}<span style='font-size:1rem;margin-left:2px;opacity:0.8;'>/10</span></div></div>"
                            f"<div style='display:flex;gap:20px;margin-bottom:15px;'>"
                            f"<div style='flex:1;background:rgba(0,255,136,0.05);border:1px solid rgba(0,255,136,0.2);border-radius:8px;padding:12px;'>"
                            f"<p style='color:#00ff88;font-weight:bold;font-size:0.85rem;text-transform:uppercase;margin-top:0;margin-bottom:8px;'>🟢 Puntos Fuertes (Bulls)</p>"
                            f"<ul style='color:#e5e7eb;font-size:0.85rem;padding-left:20px;margin:0;'>{bulls_html}</ul></div>"
                            f"<div style='flex:1;background:rgba(255,51,102,0.05);border:1px solid rgba(255,51,102,0.2);border-radius:8px;padding:12px;'>"
                            f"<p style='color:#ff3366;font-weight:bold;font-size:0.85rem;text-transform:uppercase;margin-top:0;margin-bottom:8px;'>🔴 Riesgos (Bears)</p>"
                            f"<ul style='color:#e5e7eb;font-size:0.85rem;padding-left:20px;margin:0;'>{bears_html}</ul></div></div>"
                            f"<div style='background:#0d1117;padding:12px;border-radius:8px;'>"
                            f"<p style='color:#8b949e;font-size:0.75rem;text-transform:uppercase;font-weight:bold;margin-bottom:5px;'>Síntesis Macroeconómica</p>"
                            f"<p style='color:#d1d5db;font-size:0.9rem;margin:0;line-height:1.5;'><i>\"{ai_macro}\"</i></p></div></div>"
                        ),
                        unsafe_allow_html=True
                    )
                    if asset_news:
                        news_html = "".join([f"<li style='margin-bottom:6px;'><a href='{n['link']}' target='_blank' style='color:#00f0ff; text-decoration:none;'>{n['title']}</a></li>" for n in asset_news])
                        st.markdown(f"<div style='margin-top:15px;' class='notranslate' translate='no'><p style='color:#8b949e;font-size:0.75rem;text-transform:uppercase;font-weight:bold;margin-bottom:8px;'>📰 Data Feed Inyectada al Modelo (Live News)</p><div style='background:#11131c;border:1px solid #1f2937;border-radius:8px;padding:12px;'><ul style='color:#9ca3af;font-size:0.85rem;margin:0;padding-left:15px;'>{news_html}</ul></div></div>", unsafe_allow_html=True)
                    
                with col_stats:
                    if is_owned:
                        ret_color_class = "pos-green" if p_retorno_total_mxn >= 0 else "pos-red"
                        st.markdown(
                            (
                                f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'>"
                                f"<h3 style='color:white;margin-top:0;margin-bottom:20px;font-size:1.1rem;'>Tu Posición (MXN)</h3>"
                                f"<div class='pos-row'><div><span class='pos-label'>Acciones / Títulos</span><span class='pos-val'>{p_titulos:.5f}</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Valor de Mercado</span><span class='pos-val'>${p_val_mercado:,.2f}</span></div></div>"
                                f"<div class='pos-row'><div><span class='pos-label'>Costo Promedio</span><span class='pos-val'>${p_costo_prom:,.2f}</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Diversidad Portafolio</span><span class='pos-val'>{p_peso:.2f}%</span></div></div>"
                                f"<div class='pos-row' style='margin-bottom:0;'><div><span class='pos-label'>Retorno Total (Neto MXN)</span>"
                                f"<span class='{ret_color_class}'>${p_retorno_total_mxn:+,.2f} ({p_retorno_total_pct:+.2f}%)</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Cotización Pura (Origen)</span>"
                                f"<span class='pos-val text-neon-cyan'>${current_price:,.2f} USD</span></div></div></div>"
                            ),
                            unsafe_allow_html=True
                        )
                    else: 
                        st.markdown(f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'><h3 style='color:white;margin-top:0;margin-bottom:20px;font-size:1.1rem;'>Estado de Cartera</h3><p style='color:#8b949e;font-size:0.85rem;'>Actualmente no posees {target_asset} en tu portafolio. Este activo es un candidato de observación.</p></div>", unsafe_allow_html=True)

                    if isinstance(pe_ratio, float): pe_ratio = f"{pe_ratio:.2f}x"
                    if isinstance(eps, float): eps = f"${eps:.2f}"
                    if high_52 != low_52 and high_52 != "N/A": range_pct = max(0, min(100, ((current_price - low_52) / (high_52 - low_52)) * 100))
                    else: range_pct = 50

                    st.markdown(
                        (
                            f"<div class='pos-box notranslate' translate='no' style='margin-top:15px;'>"
                            f"<h3 style='color:white;margin-top:0;margin-bottom:15px;font-size:1.1rem;'>Fundamentales y Rango</h3>"
                            f"<span class='pos-label'>Rango de 52 Semanas</span>"
                            f"<div style='display:flex;justify-content:space-between;font-size:0.8rem;color:#8b949e;margin-bottom:5px;'>"
                            f"<span>${low_52:,.2f}</span><span style='color:white;font-weight:bold;'>${current_price:,.2f}</span><span>${high_52:,.2f}</span></div>"
                            f"<div style='width:100%;background-color:#1f2937;border-radius:4px;height:8px;margin-bottom:20px;position:relative;'>"
                            f"<div style='position:absolute;left:{range_pct}%;top:-4px;width:4px;height:16px;background-color:#00f0ff;border-radius:2px;'></div>"
                            f"<div style='width:{range_pct}%;background-color:#3b82f6;height:100%;border-radius:4px;'></div></div>"
                            f"<div class='pos-row' style='margin-bottom:0;'><div><span class='pos-label'>Ratio P/E</span><span class='pos-val'>{pe_ratio}</span></div>"
                            f"<div style='text-align:right;'><span class='pos-label'>EPS (Beneficio)</span><span class='pos-val'>{eps}</span></div></div></div>"
                        ),
                        unsafe_allow_html=True
                    )
            else: st.warning(f"No se pudieron cargar los datos históricos de Yahoo Finance para el ticker: {target_asset}")
    else: st.info("Agrega activos a tu portafolio para activar la Radiografía Individual.")

    # FASE 3: MÓDULO CUANTITATIVO DE RIESGO
    st.markdown("---")
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🛡️ MÓDULO CUANTITATIVO DE RIESGO Y CORRELACIÓN</h4>", unsafe_allow_html=True)
    if not summary.empty:
        @st.cache_data(ttl=86400, max_entries=50) 
        def get_advanced_risk_metrics(tickers):
            try:
                yf_tickers = ["BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t) for t in tickers]
                data = yf.download(yf_tickers, period="1y", progress=False)
                if 'Close' in data:
                    close_data = data['Close']
                    if isinstance(close_data, pd.Series): close_data = pd.DataFrame({tickers[0]: close_data})
                    else:
                        name_map = dict(zip(yf_tickers, tickers))
                        close_data.rename(columns=name_map, inplace=True)
                    returns = close_data.pct_change().dropna()
                    
                    betas = {}
                    for yf_sym, real_t in zip(yf_tickers, tickers):
                        try: b = yf.Ticker(yf_sym).info.get('beta', 1.0)
                        except: b = 1.0
                        betas[real_t] = b if b is not None else 1.0
                        
                    return returns, betas
                return pd.DataFrame(), {}
            except: return pd.DataFrame(), {}
        
        tickers_list = summary["ticker"].tolist()
        returns_df, asset_betas = get_advanced_risk_metrics(tickers_list)
        
        if not returns_df.empty:
            summary["beta"] = summary["ticker"].map(asset_betas)
            port_beta = (summary["ponderacion_pct"] / 100 * summary["beta"]).sum()
            
            weights = (summary.set_index("ticker")["ponderacion_pct"] / 100).to_dict()
            port_returns = pd.Series(0.0, index=returns_df.index)
            for t in returns_df.columns:
                if t in weights: port_returns += returns_df[t] * weights[t]
            
            rf = 0.05
            ann_ret = port_returns.mean() * 252
            ann_vol = port_returns.std() * np.sqrt(252)
            sharpe_ratio = (ann_ret - rf) / ann_vol if ann_vol > 0 else 0
            
            var_95_pct = np.percentile(port_returns, 5) * 100
            var_95_mxn = total_portafolio * (abs(var_95_pct) / 100)
            
            cum_rets = (1 + port_returns).cumprod()
            rolling_max = cum_rets.cummax()
            drawdowns = (cum_rets - rolling_max) / rolling_max
            max_dd = drawdowns.min() * 100

            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            beta_c = "text-neon-red" if port_beta > 1.2 else ("text-neon-cyan" if port_beta < 0.8 else "text-neon-green")
            col_k1.markdown(f"<div class='metric-card'><div class='metric-title'>Beta (Volatilidad)</div><div class='metric-value {beta_c}'>{port_beta:.2f}</div><div class='metric-subtext'>Vs S&P 500</div></div>", unsafe_allow_html=True)
            sharpe_c = "text-neon-green" if sharpe_ratio > 1 else ("text-neon-gold" if sharpe_ratio > 0.5 else "text-neon-red")
            col_k2.markdown(f"<div class='metric-card'><div class='metric-title'>Sharpe Ratio</div><div class='metric-value {sharpe_c}'>{sharpe_ratio:.2f}</div><div class='metric-subtext'>Rendimiento / Riesgo</div></div>", unsafe_allow_html=True)
            col_k3.markdown(f"<div class='metric-card'><div class='metric-title'>Max Drawdown (1Y)</div><div class='metric-value text-neon-red'>{max_dd:.1f}%</div><div class='metric-subtext'>Peor caída histórica</div></div>", unsafe_allow_html=True)
            col_k4.markdown(f"<div class='metric-card'><div class='metric-title'>Value at Risk (95%)</div><div class='metric-value text-neon-purple'>${var_95_mxn:,.0f}</div><div class='metric-subtext'>Pérdida máxima esperada diaria</div></div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            col_r1, col_r2 = st.columns([1, 1.5])
            with col_r1:
                st.markdown("<p style='color:#8b949e;font-size:0.85rem;margin-bottom:5px;font-weight:bold;'>Simulador de Estrés del Mercado</p>", unsafe_allow_html=True)
                stress_drop = st.slider("Si el S&P 500 cae...", min_value=-50, max_value=0, value=-20, step=5, format="%d%%")
                simulated_drop = stress_drop * port_beta
                simulated_loss = total_portafolio * (simulated_drop / 100)
                st.markdown(f"<div style='background:#11131c;border:1px solid #ff3366;border-radius:8px;padding:15px;margin-top:10px;'><p style='color:#8b949e;font-size:0.75rem;margin-bottom:5px;text-transform:uppercase;'>Impacto Matemático Estimado</p><h3 style='color:#ff3366;margin:0;'>${simulated_loss:,.2f} MXN ({simulated_drop:+.2f}%)</h3></div>", unsafe_allow_html=True)
                
                st.markdown("<br><p style='color:#8b949e;font-size:0.85rem;margin-bottom:10px;font-weight:bold;'>Plan de Contingencia Táctica (IA)</p>", unsafe_allow_html=True)
                if st.button("🧠 Generar Protocolo de Emergencia", use_container_width=True):
                    with st.spinner("Calculando exposición al riesgo y redactando plan táctico..."):
                        backend_api_key = None
                        try: backend_api_key = st.secrets["GEMINI_API_KEY"]
                        except: pass
                        if backend_api_key:
                            try:
                                import requests
                                headers = {'Content-Type': 'application/json', 'x-goog-api-key': str(backend_api_key).strip()}
                                assets_list = ", ".join(tickers_list)
                                prompt_risk = f"Eres el CIO de un Multi-Family Office. Portafolio Beta: {port_beta:.2f}. Activos: {assets_list}. Escenario: S&P 500 cae {stress_drop}%. Portafolio cae {simulated_drop:.2f}%. Genera 'Plan de Contingencia Táctico'. Usa formato: \nDIAGNÓSTICO DE EXPOSICIÓN: [Texto]\nOPORTUNIDAD DCA: [Texto]\nREFUGIO TÁCTICO: [Texto]"
                                payload = {"contents": [{"parts": [{"text": prompt_risk}]}], "generationConfig": {"temperature": 0.2}}
                                response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers=headers, json=payload)
                                if response.status_code == 200: st.session_state["contingency_plan"] = response.json()['candidates'][0]['content']['parts'][0]['text']
                            except Exception as e: st.error(f"Error: {e}")
                
                if st.session_state.get("contingency_plan"):
                    st.markdown(f"<div style='background:rgba(0,240,255,0.05);border:1px solid rgba(0,240,255,0.2);padding:15px;border-radius:8px;margin-top:10px;'><p style='color:#e5e7eb;font-size:0.9rem;line-height:1.6;white-space:pre-wrap;'>{st.session_state['contingency_plan']}</p></div>", unsafe_allow_html=True)

            with col_r2:
                st.markdown("<p style='color:#8b949e;font-size:0.85rem;margin-bottom:5px;font-weight:bold;'>Matriz de Correlación (Diversificación Real)</p>", unsafe_allow_html=True)
                if len(tickers_list) > 1:
                    corr_matrix = returns_df.corr()
                    fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale="RdBu_r", aspect="auto")
                    fig_corr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=10,b=10,l=10,r=10), height=350)
                    st.plotly_chart(fig_corr, use_container_width=True)
                else: st.info("Necesitas al menos 2 activos en tu portafolio para generar el mapa de calor de correlación.")
    else: st.info("💡 Necesitas registrar activos en tu portafolio para poder calcular tu Nivel de Riesgo.")

    # NUEVO: CIO VIRTUAL (EARNINGS Y DIVIDENDOS)
    st.markdown("---")
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>👔 CIO VIRTUAL: REPORTES Y EARNINGS</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color:#6b7280;font-size:0.8rem;'>Cruza datos de dividendos y reportes trimestrales con el entorno macroeconómico para generar tu informe ejecutivo semanal.</p>", unsafe_allow_html=True)
    
    if not summary.empty:
        if st.button("📊 Generar Reporte de Earnings & Macro (IA)", use_container_width=True):
            with st.spinner("Recopilando calendarios de reportes y redactando informe del CIO..."):
                backend_api_key = None
                try: backend_api_key = st.secrets["GEMINI_API_KEY"]
                except: pass
                
                if backend_api_key:
                    try:
                        import requests
                        clean_key = str(backend_api_key).strip()
                        headers = {'Content-Type': 'application/json', 'x-goog-api-key': clean_key}
                        assets_list = ", ".join(summary["ticker"].tolist())
                        
                        prompt_cio = f"""
                        Eres el 'CIO Virtual' (Chief Investment Officer) de un Multi-Family Office. 
                        El portafolio tiene exposición a estos activos: {assets_list}.
                        
                        Instrucción: Escribe un 'Resumen Ejecutivo Semanal' enfocado en Earnings (Reportes Trimestrales) y Dividendos de estos activos.
                        Cruza esta información con los eventos macroeconómicos más relevantes del momento para anticipar movimientos del mercado. 
                        Mantén un tono institucional, claro y directo. Usa viñetas para la legibilidad.
                        
                        Estructura estricta (sin usar asteriscos de markdown):
                        RESUMEN MACROECONÓMICO: [1 párrafo del panorama global actual]
                        EXPECTATIVAS DE EARNINGS: [Menciona 2 o 3 activos clave del portafolio que deban vigilarse pronto]
                        ESTRATEGIA DE DIVIDENDOS E IMPUESTOS: [Cómo preparar estos ingresos pasivos para la próxima etapa contable]
                        """
                        
                        payload = {"contents": [{"parts": [{"text": prompt_cio}]}], "generationConfig": {"temperature": 0.3}}
                        response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent", headers=headers, json=payload)
                        if response.status_code == 200:
                            st.session_state["cio_report"] = response.json()['candidates'][0]['content']['parts'][0]['text']
                        else: st.error("Error al generar el reporte de la IA.")
                    except Exception as e: st.error(f"Error de conexión: {e}")
                else: st.warning("Configura tu API Key de Gemini para activar al CIO Virtual.")
                    
        if st.session_state.get("cio_report"):
            st.markdown(f"<div style='background:#11131c; border:1px solid #1f2937; padding:20px; border-radius:12px; margin-top:15px;'><p style='color:#e5e7eb; font-size:0.95rem; line-height:1.6; white-space:pre-wrap;'>{st.session_state['cio_report']}</p></div>", unsafe_allow_html=True)

    # 11. SMART DCA Y SEMÁFORO DE REBALANCEO
    st.markdown("---")
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🎯 SMART DCA Y SEMÁFORO DE REBALANCEO</h4>", unsafe_allow_html=True)
    c_tgt1, c_tgt2, c_tgt3, c_dca = st.columns(4)
    with c_tgt1: tgt_etf = st.number_input("Objetivo ETF (%)", min_value=0.0, max_value=100.0, value=60.0, step=1.0)
    with c_tgt2: tgt_acc = st.number_input("Objetivo Acción (%)", min_value=0.0, max_value=100.0, value=25.0, step=1.0)
    with c_tgt3: tgt_cripto = st.number_input("Objetivo Cripto (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
    with c_dca: new_capital = st.number_input("Capital a Inyectar (MXN)", min_value=0.0, value=5000.0, step=500.0)

    suma_tgt = tgt_etf + tgt_acc + tgt_cripto
    if suma_tgt != 100.0: st.warning(f"⚠️ La suma de los objetivos debe ser 100%. Actualmente es {suma_tgt}%. Ajusta los parámetros.")
    else:
        if not summary.empty:
            tgt_dict = {"ETF": tgt_etf, "Acción": tgt_acc, "Cripto": tgt_cripto}
            new_total_portafolio = total_activos + new_capital
            rebal_data = []
            deficits = {}
            for cls, tgt in tgt_dict.items():
                current_val = summary.loc[summary["Clase"]==cls, "valor_actual"].sum() if cls in summary["Clase"].values else 0.0
                current_pct = (current_val / total_activos * 100) if total_activos > 0 else 0.0
                target_val = new_total_portafolio * (tgt / 100.0)
                deficit = target_val - current_val
                deficits[cls] = max(0, deficit)
                diff = current_pct - tgt
                action = "🔴 COMPRAR FUERTE" if diff < -2.0 else ("🟡 PAUSAR" if diff > 2.0 else "🟢 EN BALANCE")
                rebal_data.append({"Clase": cls, "Actual_Pct": current_pct, "Objetivo_Pct": tgt, "Diferencia": diff, "Accion": action, "Valor_Actual": current_val})
                
            total_deficit = sum(deficits.values())
            compras_sugeridas = {}
            for cls in tgt_dict.keys():
                if total_deficit > 0: compras_sugeridas[cls] = new_capital * (deficits[cls] / total_deficit)
                else: compras_sugeridas[cls] = new_capital * (tgt_dict[cls] / 100.0)
            
            rebal_df = pd.DataFrame(rebal_data)
            rebal_df["Compra Sugerida (MXN)"] = rebal_df["Clase"].map(compras_sugeridas)
            
            col_graf, col_tabla = st.columns([1.2, 1])
            with col_graf:
                fig_reb = go.Figure()
                fig_reb.add_trace(go.Bar(y=rebal_df['Clase'], x=rebal_df['Actual_Pct'], name='Asignación Actual', orientation='h', marker_color='#c084fc'))
                fig_reb.add_trace(go.Bar(y=rebal_df['Clase'], x=rebal_df['Objetivo_Pct'], name='Meta (Objetivo)', orientation='h', marker_color='rgba(0,0,0,0)', marker_line_color='#00ff88', marker_line_width=2))
                fig_reb.update_layout(barmode='overlay', paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=30,b=10,l=10,r=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), xaxis_title="Porcentaje (%)", height=280)
                fig_reb.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937")
                st.plotly_chart(fig_reb, use_container_width=True)
                
            with col_tabla:
                st.markdown("<br>", unsafe_allow_html=True)
                st.dataframe(rebal_df[["Clase", "Diferencia", "Accion"]].style.format({"Diferencia": "{:+.1f}%"}), hide_index=True, use_container_width=True)
                st.markdown(
                    (
                        f"<div class='pos-box notranslate' translate='no' style='padding:15px;margin-top:0;'>"
                        f"<p style='color:#8b949e;font-size:0.75rem;margin-bottom:5px;text-transform:uppercase;'>Plan de Acción (Smart DCA)</p>"
                        f"<p style='color:white;font-size:0.9rem;line-height:1.4;'>Para inyectar <b>${new_capital:,.2f} MXN</b>, el algoritmo sugiere destinar:</p>"
                        f"<ul style='color:#00ff88;font-family:monospace;font-size:0.95rem;margin-top:5px;margin-bottom:0;'>"
                        f"<li>ETFs: ${compras_sugeridas['ETF']:,.2f}</li><li>Acciones: ${compras_sugeridas['Acción']:,.2f}</li><li>Cripto: ${compras_sugeridas['Cripto']:,.2f}</li></ul></div>"
                    ), unsafe_allow_html=True)
        else: st.info("Agrega activos a tu portafolio para activar el Semáforo de Rebalanceo.")

# MODO FÁCIL (NUEVO DASHBOARD CERO ESTRÉS)
else:
    st.markdown("<br><h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🌱 TU PORTAFOLIO SIMPLIFICADO</h4>", unsafe_allow_html=True)
    
    if not summary.empty:
        best_idx = summary['pnl'].idxmax()
        worst_idx = summary['pnl'].idxmin()
        best_row = summary.loc[best_idx]
        worst_row = summary.loc[worst_idx]
        
        col_easy1, col_easy2, col_easy3 = st.columns(3)
        with col_easy1:
            st.markdown(
                f"<div class='metric-card' style='border-color:#00ff8840;'>"
                f"<div class='metric-title' style='color:#00ff88;'>💵 El Salario Invisible</div>"
                f"<div style='font-size:1.8rem; font-weight:900; color:white; margin:10px 0;'>${salario_invisible:,.2f} <span style='font-size:1rem;color:#8b949e;'>MXN / año</span></div>"
                f"<div class='metric-subtext' style='color:#8b949e;'>Ingreso pasivo estimado por dividendos. (Tus criptos y oro no pagan renta, ¡pero crecen!)</div></div>", 
                unsafe_allow_html=True
            )
            
        with col_easy2:
            c_best = "text-neon-green" if best_row['pnl'] >= 0 else "text-neon-red"
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-title' style='color:#fbbf24;'>🏆 Tu Empleado del Mes (MVP)</div>"
                f"<div style='font-size:1.8rem; font-weight:900; color:white; margin:10px 0;'>{best_row['ticker']} <span class='{c_best}' style='font-size:1.2rem;'>({best_row['pnl']:+,.2f} MXN)</span></div>"
                f"<div class='metric-subtext' style='color:#8b949e;'>Este activo está cargando con el rendimiento de tu portafolio actual.</div></div>", 
                unsafe_allow_html=True
            )
            
        with col_easy3:
            c_worst = "text-neon-green" if worst_row['pnl'] >= 0 else "text-neon-red"
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-title' style='color:#ff3366;'>🩹 En Recuperación</div>"
                f"<div style='font-size:1.8rem; font-weight:900; color:white; margin:10px 0;'>{worst_row['ticker']} <span class='{c_worst}' style='font-size:1.2rem;'>({worst_row['pnl']:+,.2f} MXN)</span></div>"
                f"<div class='metric-subtext' style='color:#8b949e;'>Está tropezando temporalmente, pero el mercado da revanchas.</div></div>", 
                unsafe_allow_html=True
            )
            
        st.markdown("<p style='font-size:0.75rem; color:#6b7280; font-style:italic; text-align:center; margin-top:10px;'>* Nota legal: Las ganancias o pérdidas de tus activos son <b>NO REALIZADAS</b>. No has ganado ni perdido este dinero realmente hasta que decidas vender. Es solo una radiografía de hoy.</p>", unsafe_allow_html=True)
        
        st.markdown("<br><h4 style='color:#8b949e;font-size:0.9rem;text-align:center;' class='notranslate' translate='no'>🍩 RADIOGRAFÍA VISUAL DE TU DINERO</h4>", unsafe_allow_html=True)
        st.markdown("<p style='color:#6b7280;font-size:0.8rem;text-align:center;'>Haz clic en el centro o en las categorías para navegar por tu portafolio.</p>", unsafe_allow_html=True)
        
        summary_plot = summary.copy()
        summary_plot['Clase'] = summary_plot['Clase'].fillna('Otro')
        summary_plot['Sector'] = summary_plot['Sector'].fillna('Desconocido')
        
        fig_sun = px.sunburst(
            summary_plot, 
            path=['Clase', 'Sector', 'ticker'], 
            values='valor_actual',
            color='retorno_pct', 
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0
        )
        fig_sun.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=20, b=20, l=10, r=10), height=550)
        st.plotly_chart(fig_sun, use_container_width=True)
        
    else:
        st.info("💡 **Modo Simple Activo:** Aún no tienes activos en tu portafolio. Registra tus primeras compras en el panel lateral para ver tu Salario Invisible y tu Radiografía de inversiones.")
    st.markdown("---")

# 12. HISTORIAL CONTABLE
st.markdown("<br><h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>📚 HISTORIAL DE MOVIMIENTOS Y CAJA</h4>", unsafe_allow_html=True)
tab_ops, tab_caja = st.tabs(["📊 Historial de Transacciones", "🏦 Flujo de Caja"])

with tab_ops:
    if not tx_df.empty:
        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            tickers_disp = ["Todos"] + sorted(tx_df["ticker"].unique().tolist())
            filtro_t = st.selectbox("Filtrar por Activo", tickers_disp, key="filtro_ticker_hist")
        
        df_mostrar_tx = tx_df[tx_df["ticker"] == filtro_t] if filtro_t != "Todos" else tx_df.copy()
        
        st.dataframe(
            df_mostrar_tx[["fecha", "tipo_operacion", "ticker", "clase", "titulos", "precio_unitario", "tipo_cambio", "total_mxn"]].rename(
                columns={"fecha": "Fecha", "tipo_operacion": "Tipo", "ticker": "Ticker", "clase": "Clase", "titulos": "Títulos", "precio_unitario": "Precio U.", "tipo_cambio": "T.C.", "total_mxn": "Total MXN"}
            ).style.format({"Títulos": "{:.5f}", "Precio U.": "${:,.2f}", "T.C.": "${:,.2f}", "Total MXN": "${:,.2f}"}), 
            hide_index=True, use_container_width=True, height=280
        )
    else: 
        st.caption("Aún no tienes transacciones registradas.")

with tab_caja:
    if not cash_df.empty:
        col_c1, col_c2 = st.columns([1, 3])
        with col_c1:
            tipos_disp = ["Todos"] + sorted(cash_df["tipo"].unique().tolist())
            filtro_c = st.selectbox("Filtrar por Tipo", tipos_disp, key="filtro_tipo_caja")
            
        df_mostrar_cash = cash_df[cash_df["tipo"] == filtro_c] if filtro_c != "Todos" else cash_df.copy()
        
        st.dataframe(
            df_mostrar_cash[["fecha", "tipo", "concepto", "monto_mxn"]].rename(
                columns={"fecha": "Fecha", "tipo": "Tipo", "concepto": "Concepto", "monto_mxn": "Monto MXN"}
            ).style.format({"Monto MXN": "${:+,.2f}"}), 
            hide_index=True, use_container_width=True, height=280
        )
    else: 
        st.caption("Aún no tienes movimientos de caja registrados.")
