import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import psycopg2 
from psycopg2 import pool as pg_pool
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import re
import io
import time
import uuid
import numpy as np
from seguridad_auth import autenticar, verificar_usuario, hash_password_seguro
from telegram_deeplink import render_boton_telegram

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Terminal Apportafolio | Private Wealth",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded"
)

plotly_config = {
    'locale': 'es', 
    'displaylogo': False,
    'modeBarButtonsToRemove': ['zoomIn2d', 'zoomOut2d', 'pan2d', 'select2d', 'lasso2d', 'autoScale2d'],
    'toImageButtonOptions': {'format': 'png', 'filename': 'Grafica_Apportafolio'}
}

# ==========================================
# 2. ESTILOS GLOBAL & QUIET LUXURY FINTECH
# ==========================================
st.markdown("""
<style translate="no" class="notranslate">
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@200;300;400&display=swap');

[data-testid="stAppViewContainer"], .stApp { background-color: #03050a !important; font-family: 'Inter', sans-serif !important; color: #cbd5e1; }
header[data-testid="stHeader"] { background-color: transparent !important; }

/* Tooltips Móviles ⓘ */
.tooltip-container { position: relative; display: inline-block; cursor: pointer; margin-left: 6px; color: #d4af37; font-weight: bold; font-family: 'Inter', sans-serif; font-size: 0.85rem;}
.tooltip-text { 
    visibility: hidden; background-color: #080b13; color: #cbd5e1; text-align: left; 
    padding: 10px 12px; border-radius: 8px; border: 1px solid rgba(212,175,55,0.3);
    position: absolute; z-index: 100; bottom: 130%; left: 50%; transform: translateX(-50%); 
    font-size: 0.8rem; width: 220px; box-shadow: 0 10px 20px rgba(0,0,0,0.6); 
    opacity: 0; transition: opacity 0.3s; text-transform: none; letter-spacing: normal; font-weight: normal; line-height: 1.4;
}
.tooltip-container:hover .tooltip-text, .tooltip-container:focus .tooltip-text, .tooltip-container:active .tooltip-text { visibility: visible; opacity: 1; }

div[data-testid="stTabs"] button { background-color: #080b13 !important; border-radius: 20px !important; border: 1px solid rgba(255,255,255,0.03) !important; color: #64748b !important; padding: 8px 18px !important; font-family: 'Inter', sans-serif !important; font-weight: 400 !important; font-size: 0.95rem !important; margin-right: 10px !important; transition: all 0.3s ease; }
div[data-testid="stTabs"] button[aria-selected="true"] { background-color: rgba(212, 175, 55, 0.05) !important; color: #d4af37 !important; border: 1px solid rgba(212, 175, 55, 0.3) !important; font-family: 'Playfair Display', serif !important; font-style: italic; letter-spacing: 1px; box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important; }

.metric-card, .pos-box { background: linear-gradient(145deg, #080b13 0%, #0a0e17 100%) !important; border-radius: 24px !important; border: 1px solid rgba(212, 175, 55, 0.15) !important; padding: 24px !important; margin-bottom: 16px !important; box-shadow: 0 8px 24px rgba(0,0,0,0.4) !important; transition: transform 0.2s ease;}
.metric-card:hover { transform: translateY(-2px); border-color: rgba(212, 175, 55, 0.3) !important; }

.metric-title { color: #8b949e !important; font-size: 0.75rem !important; font-weight: 400 !important; text-transform: uppercase !important; letter-spacing: 2px !important; margin-bottom: 8px !important; font-family: 'Inter', sans-serif !important; display: flex; align-items: center;}
.metric-value { font-family: 'Playfair Display', serif !important; font-size: 2.6rem !important; font-weight: 400 !important; color: #ffffff !important; letter-spacing: -0.5px !important; line-height: 1.1 !important; margin: 10px 0 !important;}
.metric-subtext { font-size: 0.9rem !important; margin-top: 8px !important; font-weight: 300 !important; color: #64748b !important; font-family: 'Inter', sans-serif !important; }

.text-neon-green, .pos-green { color: #34d399 !important; } 
.text-neon-red, .pos-red { color: #94a3b8 !important; } 
.text-neon-cyan { color: #00f0ff !important; }
.text-neon-purple { color: #c084fc !important; } 
.text-neon-gold { color: #d4af37 !important; }

.pos-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem;}
.pos-label { color: #8b949e; font-weight: 400;}
.pos-val { color: #ffffff; font-weight: 500; font-family: 'Inter', sans-serif;}

#MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2.1 ICONOS SVG (reemplazo minimalista de emojis)
# ==========================================
# Solo funcionan dentro de bloques st.markdown(..., unsafe_allow_html=True).
# Los widgets nativos de Streamlit (botones, expanders, toggles, tabs, selectbox,
# st.error/success/warning/info/toast) no renderizan HTML: ahí el emoji simplemente
# se elimina del texto, sin reemplazo visual.
_SVG_ICON_PATHS = {
    "trend":    '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline>',
    "shield":   '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>',
    "eye":      '<path d="M1 12S4 4 12 4s11 8 11 8-3 8-11 8S1 12 1 12z"></path><circle cx="12" cy="12" r="3"></circle>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>',
    "book":     '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>',
    "circle":   '<circle cx="12" cy="12" r="9"></circle>',
    "spark":    '<path d="M12 2l1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2z"></path>',
    "flame":    '<path d="M12 2s-6 6.5-6 11a6 6 0 0 0 12 0c0-2-1-3.5-2-5 .3 1.5-.5 2.5-1.5 2.5C13 10.5 13 8 12 2z"></path>',
    "bolt":     '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>',
    "award":    '<circle cx="12" cy="8" r="5"></circle><polyline points="8.21 13.89 7 22 12 19 17 22 15.79 13.88"></polyline>',
}

def svg_icon(kind, color="#d4af37", size=14):
    """SVG inline minimalista (trazo fino, sin relleno)."""
    path = _SVG_ICON_PATHS.get(kind, "")
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
            f'style="vertical-align:-2px;margin-right:6px;flex-shrink:0;">{path}</svg>')

# ==========================================
# 3. FUNCIONES CORE Y BASE DE DATOS
# ==========================================
try:
    from scipy.optimize import brentq as _brentq   # requiere `scipy` en requirements.txt
except Exception:
    _brentq = None                                  # sin scipy se usa la bisección interna (_biseccion)

def sanitize_ticker(t_str):
    if not t_str: return ""
    return re.sub(r'[^A-Z0-9\-\=\.]', '', str(t_str).upper().strip())

@st.cache_data(ttl=300, max_entries=50)
def get_live_usd():
    try: return float(yf.Ticker("MXN=X").fast_info.last_price)
    except: return 19.50

live_usd_rate = get_live_usd()

# --- POOL DE CONEXIONES (PostgreSQL / Neon) ---------------------------------
@st.cache_resource
def get_pool():
    return pg_pool.ThreadedConnectionPool(
        2, 10, dsn=st.secrets["DATABASE_URL"],
        connect_timeout=10, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5
    )

def _conexion_valida(conn):
    try:
        if conn.closed: return False
        conn.rollback()
        with conn.cursor() as cur: cur.execute("SELECT 1")
        conn.rollback()
        return True
    except Exception:
        return False

@contextmanager
def db_conn(autocommit=False):
    pool = get_pool()
    conn = None
    for intento in range(3):
        try:
            candidata = pool.getconn()
        except pg_pool.PoolError:
            time.sleep(0.3)
            continue
        if _conexion_valida(candidata):
            conn = candidata
            break
        try: pool.putconn(candidata, close=True)
        except Exception: pass
        if intento == 1:
            try: pool.closeall()
            except Exception: pass
            get_pool.clear()
            pool = get_pool()
    if conn is None:
        raise RuntimeError("No fue posible obtener una conexión válida a la base de datos.")
    try:
        conn.autocommit = autocommit
        yield conn
        if not autocommit: conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise
    finally:
        try: conn.autocommit = False
        except Exception: pass
        try: pool.putconn(conn)
        except Exception: pass

def read_df(sql, params=None):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columnas = [d[0] for d in cur.description]
            filas = cur.fetchall()
    return pd.DataFrame(filas, columns=columnas)

def get_user_profile(uid):
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (uid,))
            fila = cur.fetchone()
        return (fila[0] or "MENSUAL", fila[1] or "Libertad Financiera")
    except Exception:
        return ("MENSUAL", "Libertad Financiera")

def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

@st.cache_resource
def init_db():
    with db_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);
                CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, user_id TEXT, timestamp TEXT, fecha TEXT, tipo_operacion TEXT, ticker TEXT, clase TEXT, plataforma TEXT, moneda TEXT, titulos REAL, precio_unitario REAL, comision REAL, iva REAL, tipo_cambio REAL, total_mxn REAL);
                CREATE TABLE IF NOT EXISTS cash_movements (id TEXT PRIMARY KEY, user_id TEXT, fecha TEXT, tipo TEXT, concepto TEXT, monto_mxn REAL);
            """)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dca_frequency TEXT DEFAULT 'MENSUAL'")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_name TEXT DEFAULT 'Libertad Financiera'")
            try: admin_pwd = st.secrets["admin_password"]
            except Exception: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "clave_temporal_local")
            cur.execute("INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", ("USR-001", "alex_admin", hash_password(admin_pwd), "MENSUAL", "Fondo Institucional"))
    return True

init_db()

PROMPT_MAESTRO = """
Eres el 'Motor Algorítmico V5', un analista cuantitativo y macroeconómico de inteligencia artificial.
DATOS DEL ACTIVO: Ticker: {ticker} | Precio: {current_price} USD | Rango 52W: {low_52w} - {high_52w} | P/E: {pe_ratio} | EPS: {eps}
PORTAFOLIO: Costo Promedio: {avg_cost} | Retorno: {net_return_pct}% | Peso: {portfolio_weight}%
CONTEXTO MACRO: {macro_news_context}
Responde ÚNICA Y EXCLUSIVAMENTE con un JSON válido.
{{"verdict": "DCA FUERTE", "rating": 8, "bull_points": ["Punto 1"], "bear_points": ["Punto 1"], "macro_synthesis": "Síntesis de 2 líneas."}}
"""

ASSET_CLASS = {"ISAC": "ETF", "XNAS": "ETF", "XDWH": "ETF", "EIMI": "ETF", "NUCL": "ETF", "GOOGL": "Acción", "MELI": "Acción", "NOW": "Acción", "ASML": "Acción", "NVO": "Acción", "MA": "Acción", "V": "Acción", "BTC": "Cripto"}
ASSET_SECTOR = {"ISAC": "Renta Variable Global", "XNAS": "Tecnología (Índice)", "XDWH": "Salud Global", "EIMI": "Mercados Emergentes", "NUCL": "Energía/Utilities", "GOOGL": "Servicios de Comunicación", "MELI": "Comercio Electrónico", "NOW": "Software B2B", "ASML": "Semiconductores", "NVO": "Biotecnología / Salud", "MA": "Servicios Financieros", "V": "Servicios Financieros", "BTC": "Criptoactivos"}

# ==========================================
# 3.1 GEMINI: MODELOS Y HELPERS ROBUSTOS
# ==========================================
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELOS_DEFAULT = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]

def _cadena_modelos_gemini():
    cadena = []
    try:
        override = st.secrets["GEMINI_MODEL"]
        if override: cadena.append(str(override).strip())
    except Exception: pass
    for m in GEMINI_MODELOS_DEFAULT:
        if m not in cadena: cadena.append(m)
    return cadena

def llamar_gemini(prompt, api_key, temperature=0.2, json_mode=False, timeout=45):
    import requests
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': str(api_key).strip()}
    gen_cfg = {"temperature": temperature}
    if json_mode: gen_cfg["responseMimeType"] = "application/json"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg}
    ultimo_error = "Sin respuesta de la API."
    for modelo in _cadena_modelos_gemini():
        url = f"{GEMINI_API_BASE}/{modelo}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            ultimo_error = f"Fallo de conexión con {modelo}: {str(e)}"
            break
        if resp.status_code == 200:
            try:
                partes = resp.json()["candidates"][0]["content"]["parts"]
                texto = "".join(p.get("text", "") for p in partes if isinstance(p, dict) and not p.get("thought"))
                if texto.strip(): return texto, ""
                ultimo_error = f"{modelo}: respuesta vacía (posible bloqueo de seguridad)."
            except Exception as e:
                ultimo_error = f"{modelo}: estructura de respuesta inesperada ({str(e)})."
            break
        elif resp.status_code == 404:
            ultimo_error = f"Error 404: el modelo '{modelo}' no está disponible."
            continue
        else:
            ultimo_error = f"Error {resp.status_code}: {resp.text[:300]}"
            break
    return None, ultimo_error

def extraer_json_robusto(texto):
    if not texto: return {}
    limpio = re.sub(r"```(?:json)?", "", str(texto), flags=re.IGNORECASE).strip()
    m = re.search(r"\{.*\}", limpio, flags=re.DOTALL)
    candidato = m.group(0) if m else limpio
    for intento in (candidato, re.sub(r",\s*([}\]])", r"\1", candidato)):
        try:
            data = json.loads(intento)
            if isinstance(data, dict): return data
        except Exception: continue
    return {}

def _rating_seguro(valor, default=5):
    try:
        m = re.search(r"\d+(?:\.\d+)?", str(valor))
        n = int(round(float(m.group(0)))) if m else default
    except Exception: n = default
    return max(1, min(10, n))

def _como_lista(valor, default):
    if isinstance(valor, str) and valor.strip(): return [valor.strip()]
    if isinstance(valor, (list, tuple)):
        out = [str(x).strip() for x in valor if str(x).strip()]
        if out: return out
    return default

# ==========================================
# 3.2 APPORTAFOLIO FP · FINANZAS PERSONALES (Fase 3)
# Puntos 10 (Tu dinero hoy) y 20 (Registro rápido) + código de vinculación de Telegram.
# Lee las mismas tablas y funciones de Neon que el bot (fp_dinero_libre, fp_ledger, etc.).
# ==========================================
ZONA_MX = timezone(timedelta(hours=-6))          # CDMX: sin horario de verano desde 2022
SECCION_FP = "Tu dinero hoy"
SECCION_TERMINAL = "Terminal de inversiones"
_FP_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_FP_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
_FP_FUENTES = {"TELEGRAM_TEXTO": "Telegram", "REGLA_AUTOMATICA": "Telegram · regla",
               "WEB_MANUAL": "Web", "WHATSAPP_TEXTO": "WhatsApp"}
_FP_TEXTO_MONTOS = ("comprometido", "comprometido_pendiente", "ahorro_programado", "reservado_bolsas",
                    "gastado_periodo", "gastado_hoy", "dinero_libre", "presupuesto_hoy", "disponible_hoy",
                    "base", "ingresos_periodo", "ingresos_extra")

FP_ESTILOS = """
<style>
.fp-encabezado { font-family: 'Playfair Display', serif; font-style: italic; color: #ffffff; font-size: 2rem; font-weight: 400; margin: 0; letter-spacing: 0.5px; }
.fp-fecha { color: #8b949e; font-size: 0.9rem; font-weight: 300; margin: 4px 0 22px 0; letter-spacing: 0.5px; }
.fp-hero-valor { font-family: 'Playfair Display', serif; font-size: 3.4rem; font-weight: 400; line-height: 1.05; margin: 8px 0 6px 0; letter-spacing: -0.5px; }
.fp-barra { display: flex; width: 100%; height: 14px; border-radius: 7px; overflow: hidden; background: #111827; border: 1px solid #1f2937; margin: 14px 0 12px 0; }
.fp-barra div { height: 100%; }
.fp-leyenda { display: flex; flex-wrap: wrap; gap: 14px 22px; font-size: 0.8rem; color: #8b949e; }
.fp-leyenda span { display: inline-flex; align-items: center; gap: 7px; }
.fp-leyenda i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.fp-fila { display: flex; justify-content: space-between; align-items: baseline; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.9rem; }
.fp-fila:last-child { border-bottom: none; }
.fp-fila-sub { color: #64748b; font-size: 0.78rem; margin-top: 2px; }
.fp-codigo { font-family: 'Inter', monospace; font-size: 1.6rem; letter-spacing: 4px; color: #d4af37; text-align: center; padding: 14px 0 6px 0; }
.fp-nota { color: #8b949e; font-size: 0.8rem; line-height: 1.5; }
</style>
"""


def hoy_mx():
    return datetime.now(ZONA_MX).date()


def fp_dinero(valor):
    v = round(float(valor or 0), 2)
    signo = "-" if v < 0 else ""
    v = abs(v)
    return f"{signo}${v:,.0f}" if v == int(v) else f"{signo}${v:,.2f}"


def fp_fecha_larga(fecha):
    return f"{_FP_DIAS[fecha.weekday()].capitalize()} {fecha.day} de {_FP_MESES[fecha.month - 1]}"


@st.cache_data(ttl=300, show_spinner=False)
def fp_esquema_listo():
    """True si Neon ya tiene las tablas y funciones de FP (las crean las migraciones del bot)."""
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT to_regprocedure('fp_dinero_libre(text,date)') IS NOT NULL
                   AND to_regprocedure('fp_generar_codigo_vinculacion(text,integer)') IS NOT NULL
                   AND to_regprocedure('fp_buscar_compromiso(text,text,text,numeric,date)') IS NOT NULL
                   AND to_regclass('public.fp_bolsas') IS NOT NULL
            """)
            return bool(cur.fetchone()[0])
    except Exception:
        return False


def _fp_consulta(sql, params=None):
    """Lista de dicts (sin pandas, para conservar fechas y decimales tal cual)."""
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def fp_dinero_libre(uid, hoy):
    filas = _fp_consulta("SELECT * FROM fp_dinero_libre(%s, %s)", (uid, hoy))
    if not filas:
        return None
    dl = filas[0]
    for clave in _FP_TEXTO_MONTOS:
        dl[clave] = float(dl.get(clave) or 0)
    return dl


def fp_bolsas(uid):
    return _fp_consulta(
        "SELECT nombre, tipo, aporte_periodo, saldo_acumulado, monto_objetivo FROM fp_bolsas "
        "WHERE user_id = %s AND activa ORDER BY prioridad, nombre", (uid,))


def fp_proximos(uid, desde, hasta):
    return _fp_consulta(
        "SELECT fecha, nombre, tipo_movimiento, monto FROM fp_ocurrencias(%s, %s, %s) "
        "ORDER BY fecha, tipo_movimiento, nombre LIMIT 8", (uid, desde, hasta))


def fp_ultimos(uid):
    return _fp_consulta(
        """
        SELECT l.movimiento_id, l.fecha, l.tipo_movimiento::TEXT AS tipo, l.monto, l.fuente::TEXT AS fuente,
               COALESCE(NULLIF(l.concepto, ''), NULLIF(l.comercio, ''), '') AS concepto,
               COALESCE(c.nombre, '') AS categoria
          FROM fp_financial_ledger l
          LEFT JOIN fp_categorias c ON c.categoria_id = l.categoria_id
         WHERE l.user_id = %s AND l.estado <> 'DESCARTADO'
         ORDER BY l.creado_en DESC
         LIMIT 8
        """, (uid,))


def fp_categorias(uid):
    return _fp_consulta(
        "SELECT categoria_id, nombre FROM fp_categorias WHERE user_id = %s OR user_id IS NULL ORDER BY nombre", (uid,))


def fp_cuentas(uid):
    return _fp_consulta(
        "SELECT cuenta_id, nombre FROM fp_cuentas WHERE user_id = %s AND activa ORDER BY nombre", (uid,))


def fp_registrar(uid, tipo, monto, categoria_id, cuenta_id, concepto, fecha, token):
    """Inserta en fp_financial_ledger con el mismo criterio que el bot.
    Si es el pago de un compromiso programado, lo liga para no contarlo dos veces.
    El token evita duplicados por doble clic. Devuelve movimiento_id o None si ya existía."""
    with db_conn() as conn, conn.cursor() as cur:
        compromiso_id = None
        if tipo in ("GASTO", "INGRESO"):
            cur.execute("SELECT fp_buscar_compromiso(%s, %s, %s, %s, %s)",
                        (uid, tipo, categoria_id, monto, fecha))
            compromiso_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO fp_financial_ledger
                (movimiento_id, user_id, tipo_movimiento, cuenta_origen_id, categoria_id, monto, moneda,
                 concepto, fecha, fuente, estado, mensaje_origen_id, compromiso_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'MXN', %s, %s, 'WEB_MANUAL', 'CONFIRMADO', %s, %s)
            ON CONFLICT (mensaje_origen_id) DO NOTHING
            RETURNING movimiento_id
            """,
            (f"MOV-{uuid.uuid4().hex[:16]}", uid, tipo, cuenta_id, categoria_id, monto,
             (concepto or "").strip()[:200] or None, fecha, f"WEB-{token}", compromiso_id))
        fila = cur.fetchone()
    return fila[0] if fila else None


def fp_descartar(uid, movimiento_id):
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fp_financial_ledger SET estado = 'DESCARTADO' WHERE movimiento_id = %s AND user_id = %s",
                    (movimiento_id, uid))


def fp_vinculo_activo(uid):
    filas = _fp_consulta(
        "SELECT telegram_username, vinculado_en FROM fp_telegram_links WHERE user_id = %s AND estado = 'ACTIVO'", (uid,))
    return filas[0] if filas else None


def fp_generar_codigo(uid):
    """Llama a fp_generar_codigo_vinculacion (15 minutos) y devuelve (código, vence_en)."""
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT fp_generar_codigo_vinculacion(%s, 15)", (uid,))
        codigo = cur.fetchone()[0]
        cur.execute("SELECT expira_en FROM fp_telegram_links WHERE user_id = %s AND estado = 'PENDIENTE' "
                    "ORDER BY creado_en DESC LIMIT 1", (uid,))
        vence = cur.fetchone()[0]
    return codigo, vence


def fp_desconectar_telegram(uid):
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT fp_revocar_vinculo_telegram(%s)", (uid,))


def _fp_titulo(texto, icono=None):
    icono_html = svg_icon(icono, color="#d4af37", size=17) if icono else ""
    st.markdown(f"<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.15rem; font-style:italic; "
                f"margin:22px 0 12px 0; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' "
                f"translate='no'>{icono_html}{texto}</h4>", unsafe_allow_html=True)


def _fp_tooltip(texto):
    return f"<span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{texto}</span></span>"


def render_fp_telegram(uid):
    """Generador del código de vinculación (va dentro de 'Estrategia y Perfil')."""
    st.markdown("<p style='font-size:0.8rem; color:#e5e7eb; font-weight:600; margin:6px 0 2px 0;'>Telegram</p>",
                unsafe_allow_html=True)
    if not fp_esquema_listo():
        st.caption("La conexión con Telegram estará disponible cuando se instalen las tablas de finanzas personales.")
        return
    try:
        vinculo = fp_vinculo_activo(uid)
    except Exception:
        st.caption("No pude revisar tu conexión con Telegram. Intenta más tarde.")
        return

    if vinculo:
        usuario_tg = f"@{vinculo['telegram_username']}" if vinculo.get("telegram_username") else "tu Telegram"
        desde = vinculo["vinculado_en"].astimezone(ZONA_MX).strftime("%d/%m/%Y") if vinculo.get("vinculado_en") else ""
        st.markdown(f"<p class='fp-nota'>Conectado con <b style='color:#34d399;'>{usuario_tg}</b>"
                    f"{' desde el ' + desde if desde else ''}.</p>", unsafe_allow_html=True)
        if st.button("Desconectar Telegram", key="fp_tg_desconectar", use_container_width=True):
            fp_desconectar_telegram(uid)
            st.session_state.pop("fp_codigo_tg", None)
            st.rerun()
        return

    st.markdown("<p class='fp-nota'>Registra tus gastos por chat: genera un código y envíalo al bot.</p>",
                unsafe_allow_html=True)
    if st.button("Generar código de vinculación", key="fp_tg_generar", use_container_width=True):
        try:
            codigo, vence = fp_generar_codigo(uid)
            st.session_state["fp_codigo_tg"] = {"uid": uid, "codigo": codigo, "vence": vence}
        except Exception:
            st.error("No pude generar el código. Intenta de nuevo.")

    guardado = st.session_state.get("fp_codigo_tg")
    if guardado and guardado.get("uid") == uid:
        ahora = datetime.now(timezone.utc)
        if guardado["vence"] <= ahora:
            st.session_state.pop("fp_codigo_tg", None)
            st.caption("El código anterior venció. Genera uno nuevo.")
            return
        minutos = max(1, int((guardado["vence"] - ahora).total_seconds() // 60))
        hora = guardado["vence"].astimezone(ZONA_MX).strftime("%H:%M")
        st.markdown(f"<div class='fp-codigo notranslate' translate='no'>{guardado['codigo']}</div>"
                    f"<p class='fp-nota' style='text-align:center;'>Vence a las {hora} ({minutos} min). "
                    f"Envía este mensaje al bot:</p>", unsafe_allow_html=True)
        st.code(f"/vincular {guardado['codigo']}", language=None)
        render_boton_telegram(guardado['codigo'])
        try:
            bot = str(st.secrets["TELEGRAM_BOT_USERNAME"]).strip().lstrip("@")
        except Exception:
            bot = ""
        if bot:
            st.markdown(f"<p class='fp-nota' style='text-align:center;'><a href='https://t.me/{bot}' target='_blank' "
                        f"style='color:#d4af37; text-decoration:none;'>Abrir @{bot} en Telegram</a></p>",
                        unsafe_allow_html=True)


def _fp_render_sin_base(uid, dl, hoy):
    if dl and dl.get("proximo_ingreso"):
        mensaje = (f"Tu próximo ingreso llega el {dl['proximo_ingreso']:%d/%m}. Para decirte desde hoy cuánto puedes "
                   f"gastar, dime cuánto dinero tienes ahora.")
    else:
        mensaje = ("Todavía no tengo tus ingresos. Configúralos en Telegram con /configurar (1 minuto), "
                   "o dime cuánto dinero tienes hoy para empezar a calcular.")
    st.markdown(f"<div class='pos-box'><p class='metric-title'>Primer paso</p>"
                f"<p style='color:#e5e7eb; font-size:0.95rem; margin:0; line-height:1.6;'>{mensaje}</p></div>",
                unsafe_allow_html=True)
    with st.form("fp_form_saldo", clear_on_submit=True):
        saldo = st.number_input("¿Cuánto dinero tienes hoy? (MXN)", min_value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Guardar mi saldo", use_container_width=True):
            if saldo <= 0:
                st.error("Escribe un monto mayor a cero.")
            else:
                token = st.session_state.setdefault("fp_token", uuid.uuid4().hex)
                if fp_registrar(uid, "AJUSTE", round(saldo, 2), None, None, "Saldo declarado (web)", hoy, token):
                    st.session_state["fp_token"] = uuid.uuid4().hex
                    st.rerun()


def _fp_render_estado(dl):
    disponible, libre = dl["disponible_hoy"], dl["dinero_libre"]
    hasta = f"el {dl['proximo_ingreso']:%d/%m}" if dl.get("proximo_ingreso") else "tu próximo ingreso"

    if disponible >= 0:
        titulo, valor, color = "Hoy puedes gastar", fp_dinero(disponible), "#d4af37"
    else:
        titulo, valor, color = "Hoy ya usaste tu presupuesto", f"+{fp_dinero(-disponible)}", "#94a3b8"
    sub = f"Presupuesto de hoy {fp_dinero(dl['presupuesto_hoy'])} · gastado hoy {fp_dinero(dl['gastado_hoy'])}"
    tt_hoy = ("Lo que te queda libre hasta tu próximo ingreso, repartido entre los días que faltan. "
              "Lo que no gastas hoy se suma a los días siguientes.")
    st.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>{titulo} {_fp_tooltip(tt_hoy)}</div>"
                f"<div class='fp-hero-valor' style='color:{color};'>{valor}</div>"
                f"<div class='metric-subtext'>{sub}</div></div>", unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    color_libre = "#34d399" if libre >= 0 else "#94a3b8"
    tarjetas = [
        (k1, f"Libre hasta {hasta.replace('el ', '')}", fp_dinero(libre), f"{dl['dias_restantes']} días, hoy incluido",
         color_libre, "Dinero que no tiene dueño: ya descontados tus pagos fijos, lo que apartaste y lo que gastaste."),
        (k2, "Comprometido", fp_dinero(dl["comprometido"]), f"Faltan por pagar {fp_dinero(dl['comprometido_pendiente'])}",
         "#ffffff", "Tus pagos fijos del periodo: renta, servicios, suscripciones, transporte, deudas."),
        (k3, "Apartado", fp_dinero(dl["reservado_bolsas"] + dl["ahorro_programado"]),
         "Colchón, metas e inversión", "#ffffff", "Lo que reservas en tus bolsas y tu ahorro o inversión programados."),
        (k4, "Ya gastaste", fp_dinero(dl["gastado_periodo"]), "Gastos variables del periodo", "#ffffff",
         "Lo que registraste por Telegram o aquí, sin contar pagos fijos."),
    ]
    for col, t, v, s, c, tt in tarjetas:
        col.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>{t} {_fp_tooltip(tt)}</div>"
                     f"<div class='metric-value' style='font-size:1.9rem; color:{c} !important;'>{v}</div>"
                     f"<div class='metric-subtext'>{s}</div></div>", unsafe_allow_html=True)

    # Barra de las 5 bolsas sobre el total que entró en el periodo
    entradas = dl["base"] + dl["ingresos_periodo"] + dl["ingresos_extra"]
    partes = [("Comprometido", dl["comprometido"], "#475569"),
              ("Ahorro e inversión", dl["ahorro_programado"], "#64748b"),
              ("Apartado", dl["reservado_bolsas"], "rgba(212,175,55,0.65)"),
              ("Gastado", dl["gastado_periodo"], "#94a3b8"),
              ("Libre", max(libre, 0), "#34d399")]
    total = max(entradas, sum(p[1] for p in partes), 1)
    segmentos = "".join(f"<div style='width:{v / total * 100:.2f}%; background:{c};'></div>" for _, v, c in partes if v > 0)
    leyenda = "".join(f"<span><i style='background:{c};'></i>{n} {fp_dinero(v)}</span>" for n, v, c in partes if v > 0)
    origen = "saldo declarado" if dl["fuente_base"] == "SALDO" else "ingresos"
    desde = f"{dl['periodo_inicio']:%d/%m}" if dl.get("periodo_inicio") else ""
    nota_sobregiro = ("" if libre >= 0 else
                      f"<p class='fp-nota' style='margin-top:10px;'>Vas {fp_dinero(-libre)} por encima de lo que te alcanza "
                      f"hasta {hasta}. Frenar gastos variables unos días lo equilibra.</p>")
    st.markdown(f"<div class='pos-box notranslate' translate='no'><p class='metric-title'>Tus bolsas · entradas desde el {desde}: "
                f"{fp_dinero(entradas)} ({origen})</p><div class='fp-barra'>{segmentos}</div>"
                f"<div class='fp-leyenda'>{leyenda}</div>{nota_sobregiro}</div>", unsafe_allow_html=True)
    if dl["estado"] == "SIN_PROXIMO_INGRESO":
        st.caption("No encontré tu próximo ingreso, así que calculé a 30 días. Revísalo en Telegram con /configurar.")
    if dl["fuente_base"] == "INGRESO":
        st.caption("Para que el cálculo sea exacto al centavo, registra de vez en cuando tu saldo real (tipo «Saldo de hoy»).")


def _fp_render_registro(uid, hoy):
    _fp_titulo("Registro rápido", "spark")
    ultimo = st.session_state.get("fp_ultimo_registro")
    if ultimo and ultimo.get("uid") == uid:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"<p class='fp-nota' style='margin-top:8px;'>Registrado: {ultimo['texto']}</p>", unsafe_allow_html=True)
        if c2.button("Deshacer", key="fp_deshacer_ultimo", use_container_width=True):
            fp_descartar(uid, ultimo["movimiento_id"])
            st.session_state.pop("fp_ultimo_registro", None)
            st.rerun()

    tipo_txt = st.radio("Tipo de movimiento", ["Gasto", "Ingreso", "Saldo de hoy"], horizontal=True,
                        key="fp_tipo_registro", label_visibility="collapsed")
    tipo = {"Gasto": "GASTO", "Ingreso": "INGRESO", "Saldo de hoy": "AJUSTE"}[tipo_txt]
    categorias = fp_categorias(uid)
    if tipo == "GASTO":
        categorias = [c for c in categorias if c["nombre"].lower() != "ingresos"]
    elif tipo == "INGRESO":
        categorias.sort(key=lambda c: c["nombre"].lower() != "ingresos")
    cuentas = fp_cuentas(uid)

    with st.form("fp_form_registro", clear_on_submit=True):
        c1, c2 = st.columns([1, 1.4])
        monto = c1.number_input("Monto (MXN)", min_value=0.0, step=10.0, format="%.2f")
        if tipo == "AJUSTE":
            c2.markdown("<p class='fp-nota' style='margin-top:30px;'>El dinero que tienes hoy en total. "
                        "Recalibra el cálculo al centavo.</p>", unsafe_allow_html=True)
            categoria_id, concepto, fecha = None, "Saldo declarado (web)", hoy
        else:
            nombres = [c["nombre"] for c in categorias]
            elegido = c2.selectbox("Categoría", nombres, index=0 if nombres else None)
            categoria_id = next((c["categoria_id"] for c in categorias if c["nombre"] == elegido), None)
            c3, c4 = st.columns([1.4, 1])
            concepto = c3.text_input("Concepto", placeholder="Ej. tacos, uber, renta", max_chars=120)
            fecha = c4.date_input("Fecha", value=hoy, max_value=hoy, format="DD/MM/YYYY")
        cuenta_id = None
        if cuentas and tipo != "AJUSTE":
            opciones = ["Sin especificar"] + [c["nombre"] for c in cuentas]
            cuenta_nombre = st.selectbox("Cuenta", opciones)
            cuenta_id = next((c["cuenta_id"] for c in cuentas if c["nombre"] == cuenta_nombre), None)

        if st.form_submit_button("Registrar", use_container_width=True):
            if monto <= 0:
                st.error("Escribe un monto mayor a cero.")
            elif tipo != "AJUSTE" and not categoria_id:
                st.error("Elige una categoría.")
            else:
                token = st.session_state.setdefault("fp_token", uuid.uuid4().hex)
                try:
                    movimiento_id = fp_registrar(uid, tipo, round(monto, 2), categoria_id, cuenta_id, concepto, fecha, token)
                except Exception:
                    movimiento_id = None
                    st.error("No pude guardar el movimiento. Intenta de nuevo.")
                if movimiento_id:
                    st.session_state["fp_token"] = uuid.uuid4().hex
                    etiqueta = {"GASTO": "gasto", "INGRESO": "ingreso", "AJUSTE": "saldo de hoy"}[tipo]
                    detalle = f" · {concepto}" if concepto and tipo != "AJUSTE" else ""
                    st.session_state["fp_ultimo_registro"] = {"uid": uid, "movimiento_id": movimiento_id,
                                                              "texto": f"{etiqueta} de {fp_dinero(monto)}{detalle}"}
                    st.rerun()


def _fp_render_ultimos(uid):
    _fp_titulo("Últimos movimientos", "book")
    movimientos = fp_ultimos(uid)
    if not movimientos:
        st.caption("Aún no hay movimientos. Regístralos aquí o escríbelos al bot de Telegram (\"42 pasaje\").")
        return
    for m in movimientos:
        if m["tipo"] == "AJUSTE":
            monto_html = f"<span style='color:#d4af37;'>= {fp_dinero(m['monto'])}</span>"
            titulo = "Saldo declarado"
        elif m["tipo"] == "INGRESO":
            monto_html = f"<span style='color:#34d399;'>+{fp_dinero(m['monto'])}</span>"
            titulo = m["concepto"] or m["categoria"] or "Ingreso"
        else:
            monto_html = f"<span style='color:#e5e7eb;'>-{fp_dinero(m['monto'])}</span>"
            titulo = m["concepto"] or m["categoria"] or "Gasto"
        sub = " · ".join(x for x in (f"{m['fecha']:%d/%m}", m["categoria"] if m["tipo"] != "AJUSTE" else "",
                                     _FP_FUENTES.get(m["fuente"], m["fuente"])) if x)
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"<div class='fp-fila notranslate' translate='no'><div><div style='color:#e5e7eb;'>{titulo}</div>"
                    f"<div class='fp-fila-sub'>{sub}</div></div><div>{monto_html}</div></div>", unsafe_allow_html=True)
        if c2.button("Quitar", key=f"fp_quitar_{m['movimiento_id']}", help="Lo descarta de tus números (no se borra del historial)."):
            fp_descartar(uid, m["movimiento_id"])
            st.rerun()


def _fp_render_proximos(uid, dl, hoy):
    _fp_titulo("Lo que viene", "trend")
    hasta = (dl.get("proximo_ingreso") if dl else None) or (hoy + timedelta(days=30))
    eventos = fp_proximos(uid, hoy, hasta + timedelta(days=1))
    if not eventos:
        st.caption("Sin pagos fijos ni ingresos programados. Configúralos en Telegram con /configurar.")
        return
    filas = ""
    for e in eventos:
        es_ingreso = e["tipo_movimiento"] == "INGRESO"
        color = "#34d399" if es_ingreso else "#e5e7eb"
        signo = "+" if es_ingreso else "-"
        filas += (f"<div class='fp-fila'><div><div style='color:#e5e7eb;'>{e['nombre']}</div>"
                  f"<div class='fp-fila-sub'>{_FP_DIAS[e['fecha'].weekday()][:3]} {e['fecha']:%d/%m}</div></div>"
                  f"<div style='color:{color};'>{signo}{fp_dinero(e['monto'])}</div></div>")
    st.markdown(f"<div class='pos-box notranslate' translate='no'>{filas}</div>", unsafe_allow_html=True)


def _fp_render_bolsas(uid):
    _fp_titulo("Tus bolsas", "shield")
    bolsas = fp_bolsas(uid)
    if not bolsas:
        st.caption("Aún no apartas dinero. Desde Telegram: /apartar 500 colchón (o el nombre de una meta).")
        return
    html = ""
    for b in bolsas:
        aporte, saldo, objetivo = float(b["aporte_periodo"] or 0), float(b["saldo_acumulado"] or 0), b["monto_objetivo"]
        detalle = f"{fp_dinero(aporte)} por periodo"
        barra = ""
        if objetivo:
            avance = min(saldo / float(objetivo) * 100, 100)
            detalle += f" · {fp_dinero(saldo)} de {fp_dinero(objetivo)}"
            barra = (f"<div style='width:100%; height:6px; background:#111827; border-radius:3px; margin-top:6px;'>"
                     f"<div style='width:{avance:.1f}%; height:100%; background:rgba(212,175,55,0.7); border-radius:3px;'></div></div>")
        html += (f"<div class='fp-fila' style='display:block;'><div style='display:flex; justify-content:space-between;'>"
                 f"<span style='color:#e5e7eb;'>{b['nombre']}</span><span style='color:#d4af37;'>{fp_dinero(aporte)}</span></div>"
                 f"<div class='fp-fila-sub'>{detalle}</div>{barra}</div>")
    st.markdown(f"<div class='pos-box notranslate' translate='no'>{html}</div>", unsafe_allow_html=True)


def render_fp_dashboard(uid, nombre_cliente, viendo_otro_cliente):
    """Punto 10 · Home de finanzas personales."""
    st.markdown(FP_ESTILOS, unsafe_allow_html=True)
    hoy = hoy_mx()
    st.markdown("<p class='fp-encabezado notranslate' translate='no'>Tu dinero hoy</p>", unsafe_allow_html=True)
    fecha_txt = fp_fecha_larga(hoy)
    if viendo_otro_cliente:
        fecha_txt += f" · viendo las finanzas de {nombre_cliente}"
    st.markdown(f"<p class='fp-fecha'>{fecha_txt}</p>", unsafe_allow_html=True)

    if not fp_esquema_listo():
        st.info("Las finanzas personales aún no están instaladas en la base de datos. "
                "Corre las migraciones del repositorio del bot (carpeta sql/) en Neon.")
        return
    try:
        dl = fp_dinero_libre(uid, hoy)
    except Exception:
        st.warning("No pude calcular tu dinero libre en este momento. Recarga la página en un minuto.")
        return

    if not dl or dl["estado"] == "SIN_BASE":
        _fp_render_sin_base(uid, dl, hoy)
    else:
        _fp_render_estado(dl)

    col_izq, col_der = st.columns([1.35, 1], gap="large")
    with col_izq:
        _fp_render_registro(uid, hoy)
        _fp_render_ultimos(uid)
    with col_der:
        _fp_render_proximos(uid, dl, hoy)
        _fp_render_bolsas(uid)
    st.markdown("<p style='font-size:0.75rem; color:#64748b; font-style:italic; text-align:center; margin-top:24px;'>"
                "Los montos son estimaciones con base en lo que registras y tus pagos programados; "
                "no sustituyen el saldo de tu banco.</p>", unsafe_allow_html=True)


if "user_id" not in st.session_state: st.session_state["user_id"] = None

# ==========================================
# 4. PORTADA DIVIDIDA ESTRELLADA Y ORO (RESPONSIVA)
# ==========================================
if st.session_state["user_id"] is None:
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], .stApp {
        background: linear-gradient(rgba(2, 5, 10, 0.75), rgba(2, 5, 10, 0.95)), 
                    url('https://images.unsplash.com/photo-1506318137071-a8e063b4bec0?q=80&w=3000&auto=format&fit=crop') no-repeat center center fixed !important;
        background-size: cover !important;
    }
    
    .portada-title {
        font-family: 'Montserrat', sans-serif;
        font-weight: 200;
        font-size: clamp(2.5rem, 8vw, 4.5rem); 
        letter-spacing: 0.15em;
        text-align: left;
        line-height: 1.1;
        margin-bottom: 5px;
        background: linear-gradient(to right, #bf953f 0%, #fcf6ba 25%, #b38728 50%, #fbf5b7 75%, #aa771c 100%);
        background-size: 200% auto;
        color: #000;
        background-clip: text;
        text-fill-color: transparent;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shine 6s linear infinite;
    }
    @keyframes shine { to { background-position: 200% center; } }

    .portada-subtitle { font-family: 'Playfair Display', serif; font-style: italic; color: #8b949e; text-align: left; font-size: 1.2rem; letter-spacing: 0.15em; margin-bottom: 40px; margin-top: 10px; }

    [data-testid="stForm"] {
        background: rgba(9, 23, 46, 0.2) !important; border: 1px solid rgba(191, 149, 63, 0.25) !important; border-radius: 16px !important;
        backdrop-filter: blur(15px) !important; -webkit-backdrop-filter: blur(15px) !important; padding: 3rem 2.5rem !important;
        box-shadow: 0 20px 40px rgba(0,0,0,0.8) !important; margin-top: 20px;
    }
    [data-testid="stForm"] label { display: none !important; }
    [data-testid="stForm"] input { background: transparent !important; border: none !important; border-bottom: 1px solid #1f2937 !important; color: #ffffff !important; border-radius: 0 !important; font-family: 'Inter', sans-serif !important; font-weight: 300 !important; padding: 1rem 0 !important; font-size: 0.9rem !important; transition: border-color 0.5s ease !important; text-align: center; }
    [data-testid="stForm"] input::placeholder { color: #8b949e !important; text-align: center; letter-spacing: 2px; text-transform: uppercase;}
    [data-testid="stForm"] input:focus { border-bottom: 1px solid #d4af37 !important; box-shadow: none !important; outline: none !important; background: transparent !important; }
    [data-testid="stFormSubmitButton"] button { background: linear-gradient(135deg, #bf953f 0%, #e2c575 100%) !important; color: #02050a !important; font-weight: 600 !important; font-family: 'Montserrat', sans-serif !important; letter-spacing: 3px !important; text-transform: uppercase !important; border: none !important; border-radius: 8px !important; padding: 0.8rem !important; margin-top: 40px !important; width: 100%; transition: all 0.3s ease !important;}
    [data-testid="stFormSubmitButton"] button:hover { transform: translateY(-2px) !important; box-shadow: 0 10px 20px rgba(191, 149, 63, 0.4) !important; }
    
    @media (max-width: 800px) { .portada-title { text-align: center; letter-spacing: 0.1em; } .portada-subtitle { text-align: center; } }
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
            usr = st.text_input("Usuario", placeholder="IDENTIFICADOR")
            pwd = st.text_input("Contraseña", type="password", placeholder="CLAVE DE ACCESO")
            if st.form_submit_button("ACCEDER", use_container_width=True):
                uid_ok = autenticar(db_conn, usr, pwd)
                if uid_ok: st.session_state["user_id"] = uid_ok; st.rerun()
                else: st.error("Credenciales incorrectas.")
    st.stop()

# ==========================================
# 5. GESTIÓN MULTI-CLIENTE Y SIDEBAR
# ==========================================
user_id = st.session_state["user_id"]
all_users = read_df("SELECT user_id, username FROM users")

if user_id == "USR-001":
    st.sidebar.markdown(f"<h3 style='color:#d4af37; font-family:\"Playfair Display\"; font-style:italic; display:flex; align-items:center;'>{svg_icon('shield', color='#d4af37', size=18)}Panel de Gestor</h3>", unsafe_allow_html=True)
    client_dict = dict(zip(all_users["username"], all_users["user_id"]))
    selected_client_name = st.sidebar.selectbox("Cliente Activo:", list(client_dict.keys()))
    active_client_id = client_dict[selected_client_name]
    active_username = selected_client_name 
    
    with st.sidebar.expander("Registrar Nuevo Cliente", expanded=False):
        with st.form("new_client_form"):
            new_usr = st.text_input("Nombre de Usuario")
            new_pwd = st.text_input("Contraseña Temporal", type="password")
            if st.form_submit_button("Crear Perfil"):
                if new_usr and new_pwd:
                    try:
                        with db_conn() as conn, conn.cursor() as cur:
                            cur.execute("INSERT INTO users (user_id, username, password_hash) VALUES (%s, %s, %s)", (f"USR-{int(datetime.now().timestamp())}", new_usr, hash_password(new_pwd)))
                        st.success("Creado con éxito. Recarga la página.")
                    except: st.error("El usuario ya existe.")
else:
    active_client_id = user_id
    active_username = all_users.loc[all_users["user_id"] == user_id, "username"].values[0]
    st.sidebar.markdown(f"<h3 style='color:#d4af37; font-family:\"Playfair Display\"; font-style:italic;'>Cliente: {active_username}</h3>", unsafe_allow_html=True)

# 5.1 NAVEGACIÓN PRINCIPAL (Fase 3): "Tu dinero hoy" es el home; la Terminal sigue intacta.
if "modo_pro_toggle" in st.session_state:
    st.session_state["modo_pro_toggle"] = st.session_state["modo_pro_toggle"]   # conserva el Modo Pro al cambiar de sección
seccion = st.sidebar.radio("Sección", [SECCION_FP, SECCION_TERMINAL], key="seccion_app", label_visibility="collapsed")

if st.sidebar.button("Cerrar Sesión", use_container_width=True):
    st.session_state.clear()   # nada del usuario anterior (código de Telegram, reportes de IA) queda en pantalla
    st.session_state["user_id"] = None; st.rerun()

st.sidebar.markdown("---")
if seccion == SECCION_TERMINAL:
    st.sidebar.markdown(f"<h3 style='color:#e5e7eb; font-family:\"Inter\", sans-serif; font-size:0.95rem; font-weight:600; margin:0.6rem 0 0.3rem 0; display:flex; align-items:center;'>{svg_icon('eye', color='#d4af37', size=16)}Experiencia de Usuario</h3>", unsafe_allow_html=True)
    st.sidebar.toggle("Activar Modo Pro", key="modo_pro_toggle", help="Muestra herramientas institucionales (XIRR, Due Diligence, Riesgo).")

with st.sidebar.expander("Estrategia y Perfil", expanded=False):
    st.markdown("<p style='font-size:0.8rem; color:#8b949e;'>Personaliza tu experiencia financiera.</p>", unsafe_allow_html=True)
    current_freq, current_goal = get_user_profile(user_id)

    with st.form("change_profile_form"):
        f_dca = st.selectbox("Frecuencia de Ahorro", ["SEMANAL", "QUINCENAL", "MENSUAL"], index=["SEMANAL", "QUINCENAL", "MENSUAL"].index(current_freq))
        f_goal = st.text_input("Nombre de tu Meta", value=current_goal, max_chars=30)
        st.markdown("<hr style='margin:10px 0; border-color:#1f2937;'>", unsafe_allow_html=True)
        old_pwd = st.text_input("Contraseña Actual (Confirmar)", type="password")
        new_pwd = st.text_input("Nueva Contraseña (Opcional)", type="password")
        if st.form_submit_button("Guardar Cambios", use_container_width=True):
            if not old_pwd: st.error("Ingresa tu clave actual.")
            else:
                perfil_ok = False
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,))
                    fila_pwd = cur.fetchone()
                    if fila_pwd and verificar_usuario(db_conn, user_id, old_pwd):
                        if new_pwd and len(new_pwd) >= 6:
                            cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password_seguro(new_pwd), f_dca, f_goal, user_id))
                        else:
                            cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
                        perfil_ok = True
                if perfil_ok: st.success("Perfil actualizado.")
                else: st.error("Clave incorrecta.")

    st.markdown("<hr style='margin:14px 0 8px 0; border-color:#1f2937;'>", unsafe_allow_html=True)
    render_fp_telegram(user_id)   # siempre del usuario que inició sesión (nunca del cliente que se está viendo)

if seccion == SECCION_FP:
    render_fp_dashboard(active_client_id, active_username, viendo_otro_cliente=(active_client_id != user_id))
    st.stop()   # la Terminal (cotizaciones, riesgo, IA) no se calcula mientras no se abra

st.sidebar.markdown(f"<h3 style='color:#e5e7eb; font-family:\"Inter\", sans-serif; font-size:0.95rem; font-weight:600; margin:0.6rem 0 0.3rem 0; display:flex; align-items:center;'>{svg_icon('download', color='#d4af37', size=16)}Reportes Institucionales</h3>", unsafe_allow_html=True)
export_df = read_df("SELECT * FROM transactions WHERE user_id=%s", (active_client_id,))

if not export_df.empty:
    clean_df = export_df.drop(columns=["id", "user_id", "timestamp"], errors="ignore")
    clean_df.rename(columns={"fecha": "Fecha", "tipo_operacion": "Tipo", "ticker": "Activo", "clase": "Clase", "plataforma": "Plataforma", "moneda": "Moneda", "titulos": "Títulos", "precio_unitario": "Precio Unitario", "comision": "Comisión", "iva": "IVA", "tipo_cambio": "Tipo de Cambio", "total_mxn": "Total MXN"}, inplace=True)
    col_dl1, col_dl2 = st.sidebar.columns(2)
    with col_dl1: st.download_button("CSV", data=clean_df.to_csv(index=False).encode('utf-8'), file_name=f"Portafolio_{active_username}.csv", mime="text/csv", use_container_width=True)
    with col_dl2:
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: clean_df.to_excel(writer, index=False, sheet_name='Terminal')
            st.download_button("Excel", data=buffer.getvalue(), file_name=f"Portafolio_{active_username}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except: st.download_button("Excel", data=clean_df.to_csv(index=False, sep=";").encode('latin1'), file_name=f"Portafolio_{active_username}_EXCEL.csv", mime="text/csv", use_container_width=True)
else: st.sidebar.button("Sin datos", disabled=True, use_container_width=True)

if active_client_id == "USR-001":
    st.sidebar.markdown("---")
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
                            st.session_state["val_ticker"] = tk_sym; st.session_state["val_price"] = float(p)
                            st.sidebar.success(f"${p:.2f}")
                        else: st.sidebar.error("Sin datos.")
                    except: st.sidebar.error("Inválido.")
            else: st.sidebar.warning("Escribe un ticker.")

    val_t = st.session_state.get("val_ticker", "")
    val_p = float(st.session_state.get("val_price", 0.0))

    with st.sidebar.expander("Registrar Operación", expanded=True):
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
                    if f_tipo_op == "COMPRA": total_mxn = valor_bruto_mxn + costos_mxn; imp_caja = -total_mxn; t_fin = f_titulos
                    else: total_mxn = valor_bruto_mxn - costos_mxn; imp_caja = total_mxn; t_fin = -f_titulos
                        
                    ts_id = datetime.now().timestamp()
                    with db_conn() as conn, conn.cursor() as cur:
                        cur.execute("INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, f_ticker_clean, f_clase, f_plat, f_moneda, t_fin, f_precio, f_comision, f_iva, f_tc, total_mxn))
                        cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {f_ticker_clean}", imp_caja))
                    st.session_state["val_ticker"] = ""; st.session_state["val_price"] = 0.0
                    st.success(f"{f_tipo_op} de {f_ticker_clean} registrada exitosamente."); st.rerun()
                else: st.error("Verifica el Ticker, Títulos y Precio.")

    with st.sidebar.expander("Tesorería (Ingresos/Egresos)", expanded=False):
        with st.form("form_nuevo_deposito"):
            c_tipo_op = st.selectbox("Tipo de Movimiento", ["DEPOSITO", "RETIRO"])
            f_concepto = st.text_input("Concepto", placeholder="Ej: Fondeo DCA")
            f_monto = st.number_input("Monto (MXN)", min_value=1.0, step=500.0)
            f_dep_fecha = st.date_input("Fecha de Registro", value=datetime.today())
            if st.form_submit_button("Actualizar Tesorería", use_container_width=True):
                monto_final = f_monto if c_tipo_op == "DEPOSITO" else -f_monto
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-TES-{datetime.now().timestamp()}", active_client_id, str(f_dep_fecha), c_tipo_op, f_concepto, float(monto_final)))
                st.success("Caja actualizada exitosamente."); st.rerun()

# ==========================================
# 6. CARGA DE DATOS Y MATEMÁTICAS
# ==========================================
tx_df = read_df("SELECT * FROM transactions WHERE user_id=%s", (active_client_id,))
cash_df = read_df("SELECT * FROM cash_movements WHERE user_id=%s", (active_client_id,))

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

def _biseccion(f, lo, hi, tol=1e-12, max_iter=300):
    f_lo, f_hi = f(lo), f(hi)
    if not (np.isfinite(f_lo) and np.isfinite(f_hi)) or f_lo * f_hi > 0: return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if not np.isfinite(f_mid): return None
        if f_mid == 0 or (hi - lo) < tol * max(1.0, abs(mid)): return mid
        if f_lo * f_mid < 0: hi = mid
        else: lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)

def resolver_xirr(flujos, min_dias=30):
    try:
        if not flujos or len(flujos) < 2: return None
        flujos = sorted(flujos, key=lambda x: x[0])
        t0 = flujos[0][0]
        dias = np.array([(d - t0).days for d, _ in flujos], dtype=float)
        montos = np.array([float(a) for _, a in flujos], dtype=float)
        if dias[-1] < min_dias: return None
        if not (np.any(montos > 0) and np.any(montos < 0)): return None
        tiempos = dias / 365.0

        def npv(r):
            with np.errstate(all="ignore"):
                return float(np.sum(montos / np.power(1.0 + r, tiempos)))

        lo = -0.999999
        for hi in (1.0, 10.0, 100.0, 1e3, 1e4, 1e5):
            f_lo, f_hi = npv(lo), npv(hi)
            if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo * f_hi < 0:
                raiz = None
                if _brentq is not None:
                    try: raiz = _brentq(npv, lo, hi, xtol=1e-12, rtol=1e-12, maxiter=300)
                    except Exception: raiz = None
                if raiz is None: raiz = _biseccion(npv, lo, hi)
                if raiz is not None and np.isfinite(raiz): return float(raiz)
        return None
    except Exception:
        return None

def _serie_cierre(data, symbol):
    try:
        s = data["Close"][symbol]
        return s.dropna()
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300, max_entries=50)
def get_prices_and_sparklines(tickers, fallback):
    yf_tickers = []
    if tickers:
        for t in tickers:
            if t == "BTC": yf_tickers.append("BTC-USD")
            elif t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"]: yf_tickers.append(f"{t}.L")
            else: yf_tickers.append(t)
    
    macro_tickers = ["USDMXN=X", "EURMXN=X", "GBPMXN=X", "^GSPC", "^NDX", "^DJI", "GC=F", "BTC-USD"]
    download_list = list(set(yf_tickers + macro_tickers))
    try:
        data = yf.download(download_list, period="1mo", progress=False)
    except Exception:
        data = pd.DataFrame()
    
    def get_latest(symbol):
        s = _serie_cierre(data, symbol)
        try: return float(s.iloc[-1]) if not s.empty else 0.0
        except Exception: return 0.0

    usd = get_latest("USDMXN=X") or 18.50
    pxs_mxn, pxs_usd, spark_data = {}, {}, {}
    if tickers:
        for t in tickers:
            try:
                yf_symbol = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
                raw_usd_series = _serie_cierre(data, yf_symbol)
                if raw_usd_series.empty:
                    pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark_data[t] = [fallback.get(t, 0.0)] * 10
                    continue
                hist_prices_mxn = (raw_usd_series * usd).tolist()
                spark_data[t] = hist_prices_mxn
                pxs_usd[t] = raw_usd_series.iloc[-1]
                pxs_mxn[t] = hist_prices_mxn[-1] if hist_prices_mxn else fallback.get(t, 0.0)
            except Exception: 
                pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark_data[t] = [fallback.get(t, 0.0)] * 10
                
    macro_data = {}
    for m in macro_tickers:
        macro_data[m] = {"price": 0.0, "p": 0.0, "pct": 0.0}
        try:
            s = _serie_cierre(data, m)
            if not s.empty:
                last_px = float(s.iloc[-1])
                pct = 0.0
                if len(s) >= 2 and float(s.iloc[-2]) != 0:
                    pct = float(((s.iloc[-1] - s.iloc[-2]) / s.iloc[-2]) * 100)
                if np.isfinite(last_px):
                    macro_data[m] = {"price": last_px, "p": last_px, "pct": pct if np.isfinite(pct) else 0.0}
        except Exception:
            pass
        
    return pxs_mxn, pxs_usd, spark_data, usd, macro_data

@st.cache_data(ttl=86400, max_entries=50)
def get_asset_yields(tickers):
    yields = {}
    for t in tickers:
        try:
            yf_sym = "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)
            inf = yf.Ticker(yf_sym).info
            y = inf.get('dividendYield') or inf.get('trailingAnnualDividendYield') or 0.0
            yields[t] = float(y)
        except: yields[t] = 0.0
    return yields

def _yf_symbol(t):
    return "BTC-USD" if t == "BTC" else (f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t)

@st.cache_data(ttl=86400, max_entries=50)
def _descargar_cierres_riesgo(simbolos):
    data = yf.download(list(simbolos), period="1y", progress=False)
    if data is None or data.empty: raise ValueError("Yahoo Finance no devolvió datos.")
    close = data["Close"]
    if isinstance(close, pd.Series): close = close.to_frame(name=simbolos[0])
    close = close.dropna(how="all")
    if close.empty: raise ValueError("Sin cierres disponibles.")
    return close

def get_advanced_risk_metrics(tickers):
    vacio = (pd.DataFrame(), pd.DataFrame(), {})
    try:
        tickers = list(tickers)
        if not tickers: return vacio
        yf_syms = [_yf_symbol(t) for t in tickers]
        benchmark, fx_sym = "^GSPC", "USDMXN=X"
        simbolos = tuple(dict.fromkeys(yf_syms + [benchmark, fx_sym]))
        close = _descargar_cierres_riesgo(simbolos)
        if benchmark not in close.columns or fx_sym not in close.columns: return vacio

        idx_mercado = close[benchmark].dropna().index
        close = close.reindex(idx_mercado).ffill()

        mapa = {s: t for s, t in zip(yf_syms, tickers) if s in close.columns}
        if not mapa: return vacio
        activos = close[list(mapa.keys())].rename(columns=mapa).dropna(axis=1, how="all")
        if activos.empty: return vacio

        panel = pd.concat([activos, close[benchmark].rename("__MKT__"), close[fx_sym].rename("__FX__")], axis=1).dropna()
        if len(panel) < 30: return vacio

        precios_usd = panel[activos.columns]
        r_usd = precios_usd.pct_change(fill_method=None).dropna()
        r_mkt = panel["__MKT__"].pct_change(fill_method=None).dropna()
        precios_mxn = precios_usd.mul(panel["__FX__"], axis=0)
        r_mxn = precios_mxn.pct_change(fill_method=None).dropna()

        var_m = float(r_mkt.var())
        betas = {}
        for t in tickers:
            b = 1.0
            if t in r_usd.columns and np.isfinite(var_m) and var_m > 0:
                b_calc = float(r_usd[t].cov(r_mkt)) / var_m
                if np.isfinite(b_calc): b = b_calc
            betas[t] = b
        return r_usd, r_mxn, betas
    except Exception:
        return vacio

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
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, macros = get_prices_and_sparklines(summary["ticker"].tolist(), fallback_dict)
    
    summary["precio_mercado"] = summary["ticker"].map(precios_mxn)
    summary["precio_mercado_usd"] = summary["ticker"].map(precios_usd_dict)
    summary["Tendencia (30D)"] = summary["ticker"].map(sparklines)
    summary["valor_actual"] = summary["titulos"] * summary["precio_mercado"]
    summary["pnl"] = summary["valor_actual"] - summary["costo_total"]
    summary["retorno_pct"] = (summary["pnl"] / summary["costo_total"]) * 100
    
    asset_yields = get_asset_yields(summary["ticker"].tolist())
    summary["yield_pct"] = summary["ticker"].map(asset_yields)
    summary["ingreso_pasivo"] = summary["valor_actual"] * summary["yield_pct"]
    salario_invisible = summary["ingreso_pasivo"].sum()
    
    total_activos = float(summary["valor_actual"].sum())
    total_invertido = float(summary["costo_total"].sum())
else:
    summary = pd.DataFrame(columns=["ticker", "Clase", "Sector", "titulos", "costo_promedio", "precio_mercado", "precio_mercado_usd", "valor_actual", "pnl", "retorno_pct", "Tendencia (30D)", "yield_pct", "ingreso_pasivo"])
    precios_mxn, precios_usd_dict, sparklines, usd_mxn, macros = get_prices_and_sparklines([], {})
    total_activos = total_invertido = salario_invisible = 0.0

total_portafolio = total_activos + liquidez_mxn
pnl_global = total_activos - total_invertido
retorno_global = (pnl_global / total_invertido) * 100 if total_invertido > 0 else 0.0
summary["ponderacion_pct"] = (summary["valor_actual"] / total_portafolio) * 100 if not summary.empty else 0.0

# ==========================================
# 7. TICKER TAPE (BUCLE INFINITO CSS - MACRO ONLY)
# ==========================================
items_html = ""
for name, stats in macros.items():
    if name == "^GSPC": display_name = "S&P 500"
    elif name == "^NDX": display_name = "NASDAQ"
    elif name == "^DJI": display_name = "DOW JONES"
    elif name == "GC=F": display_name = "ORO"
    elif name == "USDMXN=X": display_name = "USD/MXN"
    elif name == "EURMXN=X": display_name = "EUR/MXN"
    elif name == "GBPMXN=X": display_name = "GBP/MXN"
    elif name == "BTC-USD": display_name = "BTC/USD"
    else: continue

    stats = stats if isinstance(stats, dict) else {}
    try: pct_val = float(stats.get('pct', 0.0) or 0.0)
    except Exception: pct_val = 0.0
    try: p_val = float(stats.get('price', stats.get('p', 0.0)) or 0.0)
    except Exception: p_val = 0.0

    if p_val <= 0:
        items_html += f"<b>{display_name}:</b> <span style='color: #64748b;'>N/D</span> &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp;"
        continue
    
    color = "#34d399" if pct_val >= 0 else "#94a3b8"
    sign = "+" if pct_val >= 0 else ""
    
    if "MXN" in display_name:
        price_str = f"${p_val:.4f}"
    elif "BTC" in display_name:
        price_str = f"${p_val:,.0f}"
    else:
        price_str = f"${p_val:,.2f}"
        
    items_html += f"<b>{display_name}:</b> <span style='color: white;'>{price_str}</span> <span style='color: {color};'>({sign}{pct_val:.2f}%)</span> &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp;"

ticker_content = items_html * 4

ticker_html_css = f"""
<style>
.marquee-wrapper {{ overflow: hidden; white-space: nowrap; padding: 12px 20px; background: rgba(8, 11, 19, 0.8); border: 1px solid rgba(212, 175, 55, 0.2); border-radius: 30px; margin-bottom: 25px; margin-top: -20px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
.marquee-content {{ display: inline-block; animation: marquee-anim 80s linear infinite; font-family: 'Inter', sans-serif; font-size: 0.95rem; color:#8b949e; font-weight:400; letter-spacing: 1px;}}
@keyframes marquee-anim {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
</style>
<div class="marquee-wrapper">
    <div class="marquee-content">{ticker_content}</div>
</div>
"""
st.markdown(ticker_html_css, unsafe_allow_html=True)

# ==========================================
# 8. DASHBOARD: ESTRUCTURA LINEAL ORIGINAL
# ==========================================
tt_pat = "Todo el dinero que tienes actualmente, sumando tus ganancias y tu efectivo."
tt_cap = "El dinero exacto que ha salido de tu bolsillo hacia la aplicación."
tt_liq = "Dinero en efectivo listo para aprovechar oportunidades en el mercado."
tt_pnl = "Profit & Loss (Pérdidas o Ganancias Totales de tus inversiones)."

k1, k2, k3, k4 = st.columns(4)
k1.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>Patrimonio Total <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_pat}</span></span></div><div class='metric-value'>${total_portafolio:,.2f}</div></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>{'Capital Invertido' if st.session_state.get('modo_pro_toggle', False) else 'Dinero de tu Bolsillo'} <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_cap}</span></span></div><div class='metric-value'>${total_invertido:,.2f}</div></div>", unsafe_allow_html=True)

if st.session_state.get("modo_pro_toggle", False):
    k3.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>Liquidez Disponible <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_liq}</span></span></div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    c_pnl = "text-neon-green" if pnl_global >= 0 else "text-neon-red"
    k4.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>P&L Neto Acumulado <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_pnl}</span></span></div><div class='metric-value {c_pnl}'>${pnl_global:+,.2f}</div><div class='metric-subtext {c_pnl}'>{retorno_global:+.2f}%</div></div>", unsafe_allow_html=True)
else:
    ganancia_neta = pnl_global
    c_gan = "text-neon-green" if ganancia_neta >= 0 else "text-neon-red"
    texto_simple = "Ganancia Generada" if ganancia_neta >= 0 else "Pérdida Temporal"
    k3.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>Efectivo Libre <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_liq}</span></span></div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>{texto_simple} <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>Lo que tus inversiones han producido para ti.</span></span></div><div class='metric-value {c_gan}'>${ganancia_neta:+,.2f}</div></div>", unsafe_allow_html=True)

# 8.1 LA BOLA DE NIEVE Y GAMIFICACIÓN
st.markdown(f"<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-top:20px; margin-bottom:15px; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' translate='no'>{svg_icon('trend', color='#d4af37', size=18)}La Bola de Nieve (Histórico)</h4>", unsafe_allow_html=True)
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
            line=dict(color="#d4af37", width=3), marker=dict(size=6, color="#d4af37", symbol="circle"),
            fillcolor="rgba(212, 175, 55, 0.15)", name="Capital Invertido", hovertemplate="<b>Fecha:</b> %{x|%d %b, %Y}<br><b>Capital Acumulado:</b> $%{y:,.2f} MXN<extra></extra>"
        ))
        
        color_brecha = "#34d399" if total_portafolio >= df_hist["capital_acumulado"].iloc[-1] else "#94a3b8"
        fig_snow.add_trace(go.Scatter(
            x=[df_hist["fecha"].iloc[0], df_hist["fecha"].iloc[-1]], y=[total_portafolio, total_portafolio],
            mode='lines', line=dict(color=color_brecha, width=2, dash='dash'), name="Valor Portafolio Hoy", hovertemplate="<b>Valor Actual:</b> $%{y:,.2f} MXN<extra></extra>"
        ))

        fig_snow.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=10, b=10, l=10, r=10), height=320, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode="x unified")
        fig_snow.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937", showgrid=True)
        fig_snow.update_yaxes(gridcolor="#1f2937", zerolinecolor="#1f2937", showgrid=True, tickprefix="$")
        st.plotly_chart(fig_snow, use_container_width=True, config=plotly_config)
    else: st.info("Realiza tu primer depósito en la Tesorería para ver crecer tu Bola de Nieve.")
else: st.info("Realiza tu primer depósito en la Tesorería para ver crecer tu Bola de Nieve.")

st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Progreso y Futuro (Smart DCA)</h4>", unsafe_allow_html=True)
user_freq, meta_nombre = get_user_profile(active_client_id)

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

if racha_actual == 0: color_racha, icon_racha, rango_txt = "#64748b", "circle", "Inactivo"
elif racha_actual <= 2: color_racha, icon_racha, rango_txt = "#fbbf24", "spark", "Iniciador"
elif racha_actual <= 5: color_racha, icon_racha, rango_txt = "#f97316", "flame", "Constante"
elif racha_actual <= 11: color_racha, icon_racha, rango_txt = "#00f0ff", "bolt", "Pro"
else: color_racha, icon_racha, rango_txt = "#d4af37", "award", "Leyenda"

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
        f"<div class='metric-card notranslate' translate='no' style='text-align:center; border-color:{color_racha}40;'>"
        f"<div class='metric-title'>Nivel DCA: <span style='color:{color_racha};'>{rango_txt}</span></div>"
        f"<div style='font-family:\"Playfair Display\", serif; font-size:2.8rem; font-weight:400; color:{color_racha}; margin:5px 0; display:flex; align-items:center; justify-content:center; gap:8px;'>{racha_actual}{svg_icon(icon_racha, color=color_racha, size=26)}</div>"
        f"<div class='metric-subtext' style='margin-bottom:8px;'>{txt_frecuencia} seguidas • Récord: <b style='color:white;'>{max(racha_actual, racha_maxima)}</b></div>"
        f"<div style='font-size:0.75rem; color:#34d399; background:rgba(52, 211, 153, 0.05); padding:6px; border-radius:6px; border:1px solid rgba(52, 211, 153, 0.2);'>"
        f"Ahorro en racha: <b>${ahorro_racha:,.2f}</b></div></div>", unsafe_allow_html=True
    )
with col_g2:
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='display:flex; flex-direction:column; justify-content:center;'>"
        f"<div class='metric-title' style='color:#d4af37 !important;'>{meta_nombre}</div>"
        f"<div class='metric-value' style='font-size:1.1rem;'>Hito: ${meta_actual:,.2f} MXN</div>"
        f"<div style='width:100%;background-color:#1f2937;border-radius:12px;height:22px;position:relative; overflow:hidden; border: 1px solid #374151; margin-top:8px;'>"
        f"<div style='width:{progreso_meta}%;background:linear-gradient(90deg, #d4af37 0%, #fcf6ba 100%);height:100%; border-radius:12px;'></div>"
        f"</div><div class='metric-subtext' style='margin-top:12px;'>Faltan <b style='color:#e5e7eb;'>${faltante:,.2f} MXN</b></div></div>", unsafe_allow_html=True
    )
with col_g3:
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='border-color:#c084fc40; background:rgba(192, 132, 252, 0.02) !important;'>"
        f"<div class='metric-title' style='color:#c084fc !important;'>Tu Futuro en 5 Años</div>"
        f"<div style='font-family:\"Playfair Display\", serif; font-size:1.6rem; font-weight:400; color:white; margin:10px 0;'>${proyeccion_5a:,.2f}</div>"
        f"<div class='metric-subtext'>Si mantienes tu racha {txt_frecuencia.lower()} de <b>${aportacion_promedio:,.0f}</b> a una tasa del 10% anual.</div></div>", unsafe_allow_html=True
    )
st.markdown("---")

# ==========================================
# RAMIFICACIÓN MODO PRO vs MODO FÁCIL
# ==========================================
if st.session_state.get("modo_pro_toggle", False):
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Análisis de Rendimiento y Atribución Global</h4>", unsafe_allow_html=True)
    perf_col1, perf_col2 = st.columns([1, 2.5])

    with perf_col1:
        total_friccion = (tx_df["comision"] + tx_df["iva"]).mul(tx_df["tipo_cambio"]).sum() if not tx_df.empty else 0.0
        def calc_xirr():
            if cash_df.empty: return "N/A"
            try:
                cfs = []
                for _, r in cash_df.iterrows():
                    monto = abs(float(r["monto_mxn"]))
                    if r["tipo"] == "DEPOSITO": cfs.append((pd.to_datetime(r["fecha"]), -monto))
                    elif r["tipo"] == "RETIRO": cfs.append((pd.to_datetime(r["fecha"]), monto))
                if not cfs: return "N/A"
                cfs.append((pd.to_datetime(datetime.today().date()), float(total_portafolio)))
                tasa = resolver_xirr(cfs)
                return f"{tasa * 100:+.2f}%" if tasa is not None else "N/A"
            except: return "N/A"

        tt_fric = "Total pagado al bróker en comisiones operativas e impuestos (IVA)."
        tt_xirr = "Tasa Interna de Retorno. Mide el rendimiento real anualizado tomando en cuenta las fechas exactas de tus depósitos y retiros."
        st.markdown(
            (
                f"<div class='pos-box notranslate' translate='no'>"
                f"<p class='metric-title'>Fricción Financiera <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_fric}</span></span></p>"
                f"<p style='color:#94a3b8;font-size:1.35rem;font-weight:600;font-family:\"Inter\", sans-serif;margin:0;'>${total_friccion:,.2f} MXN</p></div>"
                f"<div class='pos-box notranslate' translate='no'>"
                f"<p class='metric-title'>Rentabilidad Ponderada (XIRR) <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_xirr}</span></span></p>"
                f"<p style='color:#00f0ff;font-size:1.35rem;font-weight:600;font-family:\"Inter\", sans-serif;margin:0;'>{calc_xirr()}</p></div>"
            ),
            unsafe_allow_html=True
        )

    with perf_col2:
        if not summary.empty:
            attr_df = summary[summary["pnl"] != 0].copy()
            if not attr_df.empty:
                attr_df.sort_values("pnl", ascending=True, inplace=True)
                attr_df["color_pnl"] = attr_df["pnl"].apply(lambda x: "#34d399" if x >= 0 else "#94a3b8")
                fig_attr = go.Figure()
                fig_attr.add_trace(go.Bar(
                    y=attr_df["ticker"], x=attr_df["pnl"], orientation="h", marker_color=attr_df["color_pnl"],
                    text=attr_df["pnl"].apply(lambda x: f"${x:+,.0f}"), textposition="outside"
                ))
                fig_attr.update_layout(title=dict(text="Atribución Neta por Activo (MXN)", font=dict(size=14, color="#8b949e")), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=30, b=0, l=10, r=10), showlegend=False, xaxis_title="", yaxis_title="", height=280)
                fig_attr.update_xaxes(gridcolor="#1f2937", zerolinecolor="#1f2937")
                st.plotly_chart(fig_attr, use_container_width=True, config=plotly_config)
            else: st.info("Aún no hay P&L registrado.")
        else: st.info("Adquiere activos para medir atribución.")

    st.markdown("---")

    if "ai_memory" not in st.session_state: st.session_state["ai_memory"] = {}

    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Radiografía Individual y Rating de Compra (Motor V5)</h4>", unsafe_allow_html=True)
    if not summary.empty:
        selected_asset = st.selectbox("Selecciona un activo en cartera o busca uno nuevo para análisis a profundidad:", sorted(summary["ticker"].tolist()) + ["+ Buscar nuevo ticker (Ej: AAPL, SPY)"], label_visibility="collapsed")
        if selected_asset.startswith("+ Buscar"):
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
                color_line = "#34d399" if pct_change_1y >= 0 else "#94a3b8"
                
                pe_ratio = asset_info.get("trailingPE", "N/A")
                eps = asset_info.get("trailingEps", "N/A")
                high_52 = asset_info.get("fiftyTwoWeekHigh") or current_price * 1.1
                low_52 = asset_info.get("fiftyTwoWeekLow") or current_price * 0.9
                noticias_texto = "\n".join([f"- {n['title']}" for n in asset_news]) if asset_news else "Sin noticias relevantes recientes."

                mem_data = st.session_state["ai_memory"].get(target_asset)
                if mem_data:
                    ai_verdict = mem_data.get("v", "HOLD")
                    ai_rating = mem_data.get("r", 5)
                    ai_bulls = mem_data.get("bl", [])
                    ai_bears = mem_data.get("br", [])
                    ai_macro = mem_data.get("m", "")
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
                            st.toast(f"Escudo Anti-Baneo activo. Espera {int(time_left)}s para un nuevo análisis.")
                        else:
                            st.session_state["last_gemini_call"] = current_time
                            try:
                                prompt_filled = PROMPT_MAESTRO.format(ticker=target_asset, current_price=round(current_price, 2), low_52w=round(low_52, 2), high_52w=round(high_52, 2), pe_ratio=pe_ratio, eps=eps, avg_cost=round(p_costo_prom, 2), net_return_pct=round(p_retorno_total_pct, 2), portfolio_weight=round(p_peso, 2), macro_news_context=noticias_texto, fed_cpi_events="Decisiones de tasas FED, datos de IPC e inflación global en seguimiento continuo.")
                                texto_ia, err_ia = llamar_gemini(prompt_filled, backend_api_key, temperature=0.2, json_mode=True)
                                if texto_ia:
                                    parsed_response = extraer_json_robusto(texto_ia)
                                    if parsed_response:
                                        ai_verdict = str(parsed_response.get("verdict") or "HOLD").strip()
                                        ai_rating = _rating_seguro(parsed_response.get("rating", 5))
                                        ai_bulls = _como_lista(parsed_response.get("bull_points"), ["Puntos fuertes en evaluación."])
                                        ai_bears = _como_lista(parsed_response.get("bear_points"), ["Riesgos en evaluación."])
                                        ai_macro = str(parsed_response.get("macro_synthesis") or "Evaluación macro en proceso.").strip()
                                        st.session_state["ai_memory"][target_asset] = {"v": ai_verdict, "r": ai_rating, "bl": ai_bulls, "br": ai_bears, "m": ai_macro}
                                    else:
                                        ai_verdict, error_api = "ERROR PARSEO", "La IA no devolvió un JSON legible."
                                else:
                                    ai_verdict, error_api = "ERROR API", err_ia
                            except Exception as e:
                                ai_verdict, error_api = "ERROR API", f"Error interno: {str(e)}"
                    
                    if not backend_api_key or ai_verdict in ["N/A", "ERROR API", "ERROR PARSEO"]:
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
                        if error_api: ai_macro = f"Fallo conexión IA o Anti-Baneo activo: {error_api}"
                        elif not backend_api_key: ai_macro = "Llave de Gemini no detectada en secrets.toml."
                        else: ai_macro = "Motor matemático local activo."

                score_color = "#34d399" if ai_rating >= 7 else ("#d4af37" if ai_rating >= 4 else "#94a3b8")

                col_chart, col_stats = st.columns([2.5, 1])
                with col_chart:
                    fig_deep = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
                    fig_deep.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'], fill='tozeroy', mode='lines', name='Precio', line=dict(color=color_line, width=2), fillcolor=f"rgba({52 if pct_change_1y>=0 else 148}, {211 if pct_change_1y>=0 else 163}, {153 if pct_change_1y>=0 else 184}, 0.15)"), row=1, col=1)
                    fig_deep.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume'], name='Volumen', marker_color='rgba(212, 175, 55, 0.4)'), row=2, col=1)
                    fig_deep.update_layout(title=dict(text=f"{target_asset} | Análisis de 1 Año", font=dict(family="Playfair Display", size=18, color="#cbd5e1")), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=40,b=10,l=10,r=10), showlegend=False, xaxis2=dict(showgrid=False), yaxis=dict(gridcolor="#1f2937"), yaxis2=dict(showgrid=False, showticklabels=False))
                    st.plotly_chart(fig_deep, use_container_width=True, config=plotly_config)
                    
                    bulls_html = "".join([f"<li style='margin-bottom:4px;'>{r}</li>" for r in ai_bulls])
                    bears_html = "".join([f"<li style='margin-bottom:4px;'>{r}</li>" for r in ai_bears])
                    st.markdown(
                        (
                            f"<div class='pos-box notranslate' translate='no' style='border-top: 2px solid {score_color};'>"
                            f"<div style='display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid rgba(212, 175, 55, 0.15);padding-bottom:15px;margin-bottom:15px;'>"
                            f"<div><p class='metric-title'>Veredicto Algorítmico V5</p>"
                            f"<h3 style='color:{score_color};margin:0;font-size:2rem;font-weight:400;font-family:\"Playfair Display\", serif;font-style:italic;'>{ai_verdict}</h3></div>"
                            f"<div style='background:transparent;color:{score_color};border:1px solid {score_color};font-weight:600;font-size:1.4rem;padding:5px 15px;border-radius:20px;display:flex;align-items:center;'>"
                            f"{ai_rating}<span style='font-size:0.9rem;margin-left:2px;opacity:0.8;'>/10</span></div></div>"
                            f"<div style='display:flex;gap:20px;margin-bottom:15px;'>"
                            f"<div style='flex:1;background:rgba(52, 211, 153, 0.05);border:1px solid rgba(52, 211, 153, 0.2);border-radius:12px;padding:15px;'>"
                            f"<p style='color:#34d399;font-weight:600;font-size:0.85rem;text-transform:uppercase;margin-top:0;margin-bottom:8px;'>Puntos Fuertes (Bulls)</p>"
                            f"<ul style='color:#cbd5e1;font-size:0.85rem;padding-left:20px;margin:0;'>{bulls_html}</ul></div>"
                            f"<div style='flex:1;background:rgba(148, 163, 184, 0.08);border:1px solid rgba(148, 163, 184, 0.25);border-radius:12px;padding:15px;'>"
                            f"<p style='color:#94a3b8;font-weight:600;font-size:0.85rem;text-transform:uppercase;margin-top:0;margin-bottom:8px;'>Riesgos (Bears)</p>"
                            f"<ul style='color:#cbd5e1;font-size:0.85rem;padding-left:20px;margin:0;'>{bears_html}</ul></div></div>"
                            f"<div style='background:rgba(8, 11, 19, 0.5);padding:15px;border-radius:12px;'>"
                            f"<p class='metric-title'>Síntesis Macroeconómica</p>"
                            f"<p style='color:#e5e7eb;font-size:0.9rem;margin:0;line-height:1.6;'><i>\"{ai_macro}\"</i></p></div></div>"
                        ),
                        unsafe_allow_html=True
                    )
                    if asset_news:
                        news_html = "".join([f"<li style='margin-bottom:6px;'><a href='{n['link']}' target='_blank' style='color:#d4af37; text-decoration:none;'>{n['title']}</a></li>" for n in asset_news])
                        st.markdown(f"<div style='margin-top:15px;' class='notranslate' translate='no'><p class='metric-title'>Data Feed Inyectada al Modelo (Live News)</p><div class='pos-box'><ul style='color:#9ca3af;font-size:0.85rem;margin:0;padding-left:15px;'>{news_html}</ul></div></div>", unsafe_allow_html=True)
                    
                with col_stats:
                    if is_owned:
                        ret_color_class = "pos-green" if p_retorno_total_mxn >= 0 else "pos-red"
                        st.markdown(
                            (
                                f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'>"
                                f"<h3 style='color:#d4af37;font-family:\"Playfair Display\", serif;font-style:italic;margin-top:0;margin-bottom:20px;font-size:1.3rem;font-weight:400;'>Tu Posición (MXN)</h3>"
                                f"<div class='pos-row'><div><span class='pos-label'>Acciones / Títulos</span><br><span class='pos-val'>{p_titulos:.5f}</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Valor de Mercado</span><br><span class='pos-val'>${p_val_mercado:,.2f}</span></div></div>"
                                f"<div class='pos-row'><div><span class='pos-label'>Costo Promedio</span><br><span class='pos-val'>${p_costo_prom:,.2f}</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Diversidad Portafolio</span><br><span class='pos-val'>{p_peso:.2f}%</span></div></div>"
                                f"<div class='pos-row' style='margin-bottom:0;'><div><span class='pos-label'>Retorno Total</span><br>"
                                f"<span class='{ret_color_class}'>${p_retorno_total_mxn:+,.2f} ({p_retorno_total_pct:+.2f}%)</span></div>"
                                f"<div style='text-align:right;'><span class='pos-label'>Cotización Pura</span><br>"
                                f"<span class='pos-val' style='color:#d4af37;'>${current_price:,.2f} USD</span></div></div></div>"
                            ),
                            unsafe_allow_html=True
                        )
                    else: 
                        st.markdown(f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'><h3 style='color:#d4af37;font-family:\"Playfair Display\", serif;font-style:italic;margin-top:0;margin-bottom:20px;font-size:1.3rem;font-weight:400;'>Estado de Cartera</h3><p style='color:#8b949e;font-size:0.85rem;'>Actualmente no posees {target_asset} en tu portafolio. Este activo es un candidato de observación.</p></div>", unsafe_allow_html=True)

                    if isinstance(pe_ratio, float): pe_ratio = f"{pe_ratio:.2f}x"
                    if isinstance(eps, float): eps = f"${eps:.2f}"
                    if high_52 != low_52 and high_52 != "N/A": range_pct = max(0, min(100, ((current_price - low_52) / (high_52 - low_52)) * 100))
                    else: range_pct = 50

                    tt_fnd = "El Ratio P/E indica cuántos años de beneficios estás pagando por la acción. El EPS es la ganancia reportada por cada acción en circulación."
                    st.markdown(
                        (
                            f"<div class='pos-box notranslate' translate='no' style='margin-top:15px;'>"
                            f"<h3 style='color:#d4af37;font-family:\"Playfair Display\", serif;font-style:italic;margin-top:0;margin-bottom:15px;font-size:1.3rem;font-weight:400;'>Fundamentales y Rango <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_fnd}</span></span></h3>"
                            f"<span class='pos-label'>Rango de 52 Semanas</span>"
                            f"<div style='display:flex;justify-content:space-between;font-size:0.8rem;color:#8b949e;margin-bottom:5px;'>"
                            f"<span>${low_52:,.2f}</span><span style='color:white;font-weight:bold;'>${current_price:,.2f}</span><span>${high_52:,.2f}</span></div>"
                            f"<div style='width:100%;background-color:#1f2937;border-radius:4px;height:8px;margin-bottom:20px;position:relative;'>"
                            f"<div style='position:absolute;left:{range_pct}%;top:-4px;width:4px;height:16px;background-color:#d4af37;border-radius:2px;'></div>"
                            f"<div style='width:{range_pct}%;background:linear-gradient(90deg, #d4af37 0%, #fcf6ba 100%);height:100%;border-radius:4px;'></div></div>"
                            f"<div class='pos-row' style='margin-bottom:0;'><div><span class='pos-label'>Ratio P/E</span><br><span class='pos-val'>{pe_ratio}</span></div>"
                            f"<div style='text-align:right;'><span class='pos-label'>EPS (Beneficio)</span><br><span class='pos-val'>{eps}</span></div></div></div>"
                        ),
                        unsafe_allow_html=True
                    )
            else: st.warning(f"No se pudieron cargar los datos históricos de Yahoo Finance para el ticker: {target_asset}")
    else: st.info("Agrega activos a tu portafolio para activar la Radiografía Individual.")

    st.markdown("---")
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Módulo Cuantitativo de Riesgo y Correlación</h4>", unsafe_allow_html=True)
    if not summary.empty:
        tickers_list = summary["ticker"].tolist()
        returns_df, returns_mxn_df, asset_betas = get_advanced_risk_metrics(tickers_list)
        
        if not returns_df.empty and not returns_mxn_df.empty:
            summary["beta"] = summary["ticker"].map(asset_betas).fillna(1.0)
            port_beta = (summary["ponderacion_pct"] / 100 * summary["beta"]).sum()
            
            weights = (summary.set_index("ticker")["ponderacion_pct"] / 100).to_dict()
            port_returns = pd.Series(0.0, index=returns_mxn_df.index)
            for t in returns_mxn_df.columns:
                if t in weights: port_returns += returns_mxn_df[t] * weights[t]
            
            try: rf = float(st.secrets["RISK_FREE_RATE_MXN"])
            except Exception: rf = 0.05
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
            tt_beta = "Mide la volatilidad frente al mercado. >1 es más agresivo, <1 es más defensivo."
            col_k1.markdown(f"<div class='metric-card'><div class='metric-title'>Beta (Volatilidad) <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_beta}</span></span></div><div class='metric-value {beta_c}' style='font-size:1.8rem;'>{port_beta:.2f}</div><div class='metric-subtext'>Vs S&P 500</div></div>", unsafe_allow_html=True)
            
            tt_sharpe = "Retorno ajustado al riesgo. Valores superiores a 1 indican una excelente gestión del riesgo."
            sharpe_c = "text-neon-green" if sharpe_ratio > 1 else ("text-neon-gold" if sharpe_ratio > 0.5 else "text-neon-red")
            col_k2.markdown(f"<div class='metric-card'><div class='metric-title'>Sharpe Ratio <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_sharpe}</span></span></div><div class='metric-value {sharpe_c}' style='font-size:1.8rem;'>{sharpe_ratio:.2f}</div><div class='metric-subtext'>Rendimiento / Riesgo</div></div>", unsafe_allow_html=True)
            
            tt_mdd = "La peor caída histórica que ha sufrido el portafolio desde su punto más alto."
            col_k3.markdown(f"<div class='metric-card'><div class='metric-title'>Drawdown Máximo (1A) <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_mdd}</span></span></div><div class='metric-value text-neon-red' style='font-size:1.8rem;'>{max_dd:.1f}%</div><div class='metric-subtext'>Peor caída histórica</div></div>", unsafe_allow_html=True)
            
            tt_var = "El umbral de pérdida que se superará estadísticamente solo el 5% de los días."
            col_k4.markdown(f"<div class='metric-card'><div class='metric-title'>Value at Risk (95%) <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_var}</span></span></div><div class='metric-value text-neon-purple' style='font-size:1.8rem;'>${var_95_mxn:,.0f}</div><div class='metric-subtext'>Pérdida máxima esperada diaria</div></div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            col_r1, col_r2 = st.columns([1, 1.5])
            with col_r1:
                st.markdown("<p style='color:#8b949e;font-size:0.85rem;margin-bottom:5px;font-weight:bold;'>Simulador de Estrés del Mercado</p>", unsafe_allow_html=True)
                stress_drop = st.slider("Si el S&P 500 cae...", min_value=-50, max_value=0, value=-20, step=5, format="%d%%")
                simulated_drop = stress_drop * port_beta
                simulated_loss = total_portafolio * (simulated_drop / 100)
                st.markdown(f"<div class='pos-box'><p class='metric-title'>Impacto Matemático Estimado</p><h3 style='color:#94a3b8;margin:0;font-family:\"Playfair Display\", serif; font-size:1.8rem; font-weight:400;'>${simulated_loss:,.2f} MXN ({simulated_drop:+.2f}%)</h3></div>", unsafe_allow_html=True)
                
            with col_r2:
                tt_corr = "Mide cómo se mueven tus activos entre sí. Un valor cercano a +1 significa que se mueven igual, -1 en direcciones opuestas (buena diversificación), y 0 que no tienen relación."
                st.markdown(f"<p style='color:#8b949e;font-size:0.85rem;margin-bottom:5px;font-weight:bold;'>Matriz de Correlación (Diversificación Real) <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_corr}</span></span></p>", unsafe_allow_html=True)
                if len(tickers_list) > 1:
                    corr_matrix = returns_df.corr()
                    fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale=[[0, '#94a3b8'], [0.5, '#d4af37'], [1, '#34d399']], aspect="auto")
                    fig_corr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=10,b=10,l=10,r=10), height=350)
                    st.plotly_chart(fig_corr, use_container_width=True, config=plotly_config)
                else: st.info("Necesitas al menos 2 activos en tu portafolio para generar el mapa de calor de correlación.")
    else: st.info("Necesitas registrar activos en tu portafolio para poder calcular tu Nivel de Riesgo.")

    st.markdown("---")
    st.markdown("<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:5px; letter-spacing:1px;' class='notranslate' translate='no'>CIO Virtual: Reportes y Earnings</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color:#64748b;font-size:0.85rem;'>Cruza datos de dividendos y reportes trimestrales con el entorno macroeconómico para generar tu informe ejecutivo semanal.</p>", unsafe_allow_html=True)
    
    if not summary.empty:
        if st.button("Generar Reporte de Earnings & Macro", use_container_width=True):
            with st.spinner("Recopilando calendarios de reportes y redactando informe del CIO..."):
                backend_api_key = None
                try: backend_api_key = st.secrets["GEMINI_API_KEY"]
                except: pass
                
                if backend_api_key:
                    try:
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
                        
                        texto_cio, err_cio = llamar_gemini(prompt_cio, backend_api_key, temperature=0.3)
                        if texto_cio: st.session_state["cio_report"] = texto_cio
                        else: st.error(f"Error al generar el reporte de la IA. {err_cio}")
                    except Exception as e: st.error(f"Error de conexión: {e}")
                else: st.warning("Configura tu API Key de Gemini para activar al CIO Virtual.")
                    
        if st.session_state.get("cio_report"):
            st.markdown(f"<div class='pos-box'><p style='color:#e5e7eb; font-size:0.95rem; line-height:1.6; white-space:pre-wrap;'>{st.session_state['cio_report']}</p></div>", unsafe_allow_html=True)

    st.markdown("---")
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

else:
    st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Tu Portafolio Simplificado</h4>", unsafe_allow_html=True)
    
    if not summary.empty:
        best_idx = summary['pnl'].idxmax()
        worst_idx = summary['pnl'].idxmin()
        best_row = summary.loc[best_idx]
        worst_row = summary.loc[worst_idx]
        
        col_easy1, col_easy2, col_easy3 = st.columns(3)
        with col_easy1:
            st.markdown(
                f"<div class='metric-card' style='border-color:rgba(52, 211, 153, 0.3) !important;'>"
                f"<div class='metric-title' style='color:#34d399 !important;'>El Salario Invisible</div>"
                f"<div style='font-family:\"Playfair Display\", serif; font-size:1.8rem; font-weight:400; color:white; margin:10px 0;'>${salario_invisible:,.2f} <span style='font-size:1rem;color:#8b949e;font-family:\"Inter\";'>MXN / año</span></div>"
                f"<div class='metric-subtext'>Ingreso pasivo estimado por dividendos. (Tus criptos y oro no pagan renta, ¡pero crecen!)</div></div>", 
                unsafe_allow_html=True
            )
            
        with col_easy2:
            c_best = "text-neon-green" if best_row['pnl'] >= 0 else "text-neon-red"
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-title' style='color:#d4af37 !important;'>Tu Empleado del Mes (MVP)</div>"
                f"<div style='font-family:\"Playfair Display\", serif; font-size:1.8rem; font-weight:400; color:white; margin:10px 0;'>{best_row['ticker']} <span class='{c_best}' style='font-size:1.2rem;font-family:\"Inter\";'>({best_row['pnl']:+,.2f} MXN)</span></div>"
                f"<div class='metric-subtext'>Este activo está cargando con el rendimiento de tu portafolio actual.</div></div>", 
                unsafe_allow_html=True
            )
            
        with col_easy3:
            c_worst = "text-neon-green" if worst_row['pnl'] >= 0 else "text-neon-red"
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-title' style='color:#94a3b8 !important;'>En Recuperación</div>"
                f"<div style='font-family:\"Playfair Display\", serif; font-size:1.8rem; font-weight:400; color:white; margin:10px 0;'>{worst_row['ticker']} <span class='{c_worst}' style='font-size:1.2rem;font-family:\"Inter\";'>({worst_row['pnl']:+,.2f} MXN)</span></div>"
                f"<div class='metric-subtext'>Está tropezando temporalmente, pero el mercado da revanchas.</div></div>", 
                unsafe_allow_html=True
            )
            
        st.markdown("<p style='font-size:0.75rem; color:#64748b; font-style:italic; text-align:center; margin-top:10px;'>* Nota legal: Las ganancias o pérdidas de tus activos son <b>NO REALIZADAS</b>. No has ganado ni perdido este dinero realmente hasta que decidas vender. Es solo una radiografía de hoy.</p>", unsafe_allow_html=True)
        
        st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; text-align:center;' class='notranslate' translate='no'>Radiografía Visual de tu Dinero</h4>", unsafe_allow_html=True)
        st.markdown("<p style='color:#64748b;font-size:0.8rem;text-align:center;'>Haz clic en el centro o en las categorías para navegar por tu portafolio.</p>", unsafe_allow_html=True)
        
        summary_plot = summary.copy()
        summary_plot['Clase'] = summary_plot['Clase'].fillna('Otro')
        summary_plot['Sector'] = summary_plot['Sector'].fillna('Desconocido')
        
        fig_sun = px.sunburst(
            summary_plot, 
            path=['Clase', 'Sector', 'ticker'], 
            values='valor_actual',
            color='retorno_pct', 
            color_continuous_scale=[[0, '#94a3b8'], [0.5, '#d4af37'], [1, '#34d399']],
            color_continuous_midpoint=0
        )
        fig_sun.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ca3af"), margin=dict(t=20, b=20, l=10, r=10), height=550)
        st.plotly_chart(fig_sun, use_container_width=True, config=plotly_config)
        
    else:
        st.info("**Modo Simple Activo:** Aún no tienes activos en tu portafolio. Registra tus primeras compras en el panel lateral para ver tu Salario Invisible y tu Radiografía de inversiones.")
    st.markdown("---")

# ==========================================
# 10. HISTORIAL CONTABLE Y CAJA
# ==========================================
st.markdown(f"<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' translate='no'>{svg_icon('book', color='#d4af37', size=18)}Historial de Movimientos y Caja</h4>", unsafe_allow_html=True)
tab_ops, tab_caja = st.tabs(["Historial de Transacciones", "Flujo de Caja"])

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
