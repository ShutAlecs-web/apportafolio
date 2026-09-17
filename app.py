import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import psycopg2 # CAMBIO: Motor PostgreSQL institucional
import hashlib
from datetime import datetime
import json
import re
import io

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

# PROMPT MAESTRO V5
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

CONTEXTO MACROECONÓMICO Y NOTICIAS RECIENTES (Top 5 inyectadas por el sistema):
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

# 3. BASE DE DATOS POSTGRESQL (NUBE)
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
        
    try:
        admin_pwd = st.secrets["admin_password"]
    except Exception:
        admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
        
    cur.execute(
        "INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", 
        ("USR-001", "alex_admin", hash_password(admin_pwd), "MENSUAL", "Fondo Institucional")
    )
    cur.close()
    conn.close()

init_db()

if "user_id" not in st.session_state: st.session_state["user_id"] = None

if st.session_state["user_id"] is None:
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<br><br><br><h1 style='text-align: center; color: white;'>CMA TERMINAL</h1>", unsafe_allow_html=True)
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
                else: st.error("Credenciales incorrectas.")
    st.stop()

# 4. GESTIÓN MULTI-CLIENTE (ADMIN PANEL)
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
                    except Exception:
                        st.error("El nombre de usuario ya existe.")
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
st.sidebar.toggle("🔬 Activar Modo Pro", key="modo_pro_toggle", help="Muestra herramientas institucionales (XIRR, Due Diligence, etc).")

with st.sidebar.expander("⚙️ Estrategia y Perfil", expanded=False):
    st.markdown("<p style='font-size:0.8rem; color:#8b949e;'>Personaliza tu experiencia financiera.</p>", unsafe_allow_html=True)
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (user_id,))
        user_data = cur.fetchone()
        current_freq, current_goal = user_data[0], user_data[1]
    except: 
        current_freq, current_goal = "MENSUAL", "Libertad Financiera"
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
                    if new_pwd and len(new_pwd) >= 6:
                        cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password(new_pwd), f_dca, f_goal, user_id))
                    else:
                        cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
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
    clean_df.rename(columns={
        "fecha": "Fecha", "tipo_operacion": "Tipo", "ticker": "Activo", 
        "clase": "Clase", "plataforma": "Plataforma", "moneda": "Moneda", 
        "titulos": "Títulos", "precio_unitario": "Precio Unitario", 
        "comision": "Comisión", "iva": "IVA", "tipo_cambio": "Tipo de Cambio", 
        "total_mxn": "Total MXN"
    }, inplace=True)
    
    col_dl1, col_dl2 = st.sidebar.columns(2)
    with col_dl1:
        st.download_button("📊 CSV", data=clean_df.to_csv(index=False).encode('utf-8'), file_name=f"Portafolio_{active_username}.csv", mime="text/csv", use_container_width=True)
    with col_dl2:
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                clean_df.to_excel(writer, index=False, sheet_name='CMA_Terminal')
            st.download_button("📗 Excel", data=buffer.getvalue(), file_name=f"Portafolio_{active_username}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except:
            st.download_button("📗 Excel", data=clean_df.to_csv(index=False, sep=";").encode('latin1'), file_name=f"Portafolio_{active_username}_EXCEL.csv", mime="text/csv", use_container_width=True)
else:
    st.sidebar.button("📊 Sin datos", disabled=True, use_container_width=True)

if active_client_id == "USR-001":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Control Operativo (Admin)")
    st.sidebar.markdown("<p style='font-size:0.8rem; color:#8b949e;'>1. Buscar activo y cotización</p>", unsafe_allow_html=True)
    col_b1, col_b2 = st.sidebar.columns([2, 1])
    with col_b1:
        search_ticker = st.text_input("Ticker", key="search_t", label_visibility="collapsed", placeholder="Ej. AAPL, O, BTC-USD...")
    with col_b2:
        if st.button("Validar", use_container_width=True):
            if search_ticker:
                tk_sym = search_ticker.upper().strip()
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
            f_tc = st.number_input("Tipo de Cambio", min_value=1.0, value=17.60, format="%.2f")
            f_fecha = st.date_input("Fecha", value=datetime.today())
            
            if st.form_submit_button("Ejecutar Operación", use_container_width=True):
                if f_ticker and f_titulos > 0 and f_precio > 0:
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
                                 (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, f_ticker.upper(), f_clase, f_plat, f_moneda, titulos_final, f_precio, f_comision, f_iva, f_tc, total_op_mxn))
                    
                    cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", 
                                 (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {f_ticker.upper()}", impacto_caja))
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    st.session_state["val_ticker"] = ""
                    st.session_state["val_price"] = 0.0
                    st.success(f"✅ {f_tipo_op} de {f_ticker.upper()} registrada exitosamente.")
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

@st.cache_data(ttl=300)
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
    total_activos = float(summary["valor_actual"].sum())
    total_invertido = float(summary["costo_total"].sum())
else:
    summary = pd.DataFrame(columns=["ticker", "Clase", "Sector", "titulos", "costo_promedio", "precio_mercado", "precio_mercado_usd", "valor_actual", "pnl", "retorno_pct", "Tendencia (30D)"])
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, sp500_chg, ndx_chg, dji_chg, gold_price, btc_price = get_prices_and_sparklines([], {})
    total_activos = 0.0
    total_invertido = 0.0

total_portafolio = total_activos + liquidez_mxn
pnl_global = total_activos - total_invertido
retorno_global = (pnl_global / total_invertido) * 100 if total_invertido > 0 else 0.0
if not summary.empty: summary["ponderacion_pct"] = (summary["valor_actual"] / total_portafolio) * 100
else: summary["ponderacion_pct"] = 0.0

# 6. TICKER TAPE Y MACROECONOMÍA
@st.cache_data(ttl=300)
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
        
        df_hoy = pd.DataFrame({
            "fecha": [pd.to_datetime(datetime.today().date())], 
            "capital_acumulado": [df_hist["capital_acumulado"].iloc[-1]]
        })
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

        fig_snow.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"),
            margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode="x unified"
        )
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

# MODO PRO
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
                fig_attr.update_layout(
                    title=dict(text="Atribución Neta por Activo (MXN)", font=dict(size=14, color="#8b949e")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=30, b=0, l=10, r=10),
                    showlegend=False, xaxis_title="", yaxis_title="", height=280
                )
                fig_attr.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937")
                st.plotly_chart(fig_attr, use_container_width=True)
            else: st.info("Aún no hay P&L registrado.")
        else: st.info("Adquiere activos para medir atribución.")

    st.markdown("---")

    # 9. LUPA DE ACTIVOS - DUE DILIGENCE Y RATING V5
    st.markdown("<h4 style='color:#8b949e;font-size:0.9rem;' class='notranslate' translate='no'>🔍 RADIOGRAFÍA INDIVIDUAL Y RATING DE COMPRA (PROMPT V5)</h4>", unsafe_allow_html=True)

    if not summary.empty:
        selected_asset = st.selectbox("Selecciona un activo en cartera o busca uno nuevo para Deep Dive:", sorted(summary["ticker"].tolist()) + ["🔍 Buscar nuevo ticker (Ej: AAPL, SPY)"])
        if selected_asset.startswith("🔍"):
            search_ticker = st.text_input("Ingresa el Ticker de Yahoo Finance a analizar (Ej: NVDA, URA, SCHD):").upper()
            target_asset = search_ticker if search_ticker else None
        else: target_asset = selected_asset

        if target_asset:
            @st.cache_data(ttl=3600)
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
                            if isinstance(link, str) and link.startswith('http'):
                                safe_link = link
                            else:
                                safe_link = f"https://finance.yahoo.com/quote/{yf_sym}"
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
                
                ai_verdict, ai_rating, ai_bulls, ai_bears = "N/A", 5, [], []
                ai_macro = "Motor matemático local activo. Evaluando métricas estándar."
                noticias_texto = "\n".join([f"- {n['title']}" for n in asset_news]) if asset_news else "Sin noticias relevantes recientes."

                backend_api_key = None
                try:
                    backend_api_key = st.secrets["GEMINI_API_KEY"]
                except Exception: pass
                
                if not backend_api_key:
                    try:
                        secret_path = os.path.join(".streamlit", "secrets.toml")
                        if os.path.exists(secret_path):
                            with open(secret_path, "rb") as f:
                                raw_content = f.read()
                                content = raw_content.decode("utf-8", errors="ignore").replace("\x00", "")
                                match = re.search(r'GEMINI_API_KEY\s*=\s*[\'"]([^\'"]+)[\'"]', content)
                                if match: backend_api_key = match.group(1)
                    except: pass

                if not backend_api_key: backend_api_key = os.environ.get("GEMINI_API_KEY")

                error_api = ""
                if backend_api_key:
                    try:
                        import requests
                        # CAMBIO: Usamos gemini-pro para evitar errores 404
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={backend_api_key}"
                        headers = {'Content-Type': 'application/json'}
                        
                        prompt_filled = PROMPT_MAESTRO.format(
                            ticker=target_asset, current_price=round(current_price, 2), low_52w=round(low_52, 2), high_52w=round(high_52, 2),
                            pe_ratio=pe_ratio, eps=eps, avg_cost=round(p_costo_prom, 2), net_return_pct=round(p_retorno_total_pct, 2),
                            portfolio_weight=round(p_peso, 2), macro_news_context=noticias_texto, 
                            fed_cpi_events="Decisiones de tasas FED, datos de IPC e inflación global en seguimiento continuo."
                        )
                        
                        payload = {
                            "contents": [{"parts": [{"text": prompt_filled}]}],
                            "generationConfig": {"temperature": 0.2}
                        }
                        
                        response = requests.post(url, headers=headers, json=payload)
                        
                        if response.status_code == 200:
                            ai_response = response.json()['candidates'][0]['content']['parts'][0]['text']
                            clean_json = ai_response.replace("```json", "").replace("
