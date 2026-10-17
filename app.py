import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import psycopg2
import psycopg2.extensions
from psycopg2 import pool as pg_pool
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import re
import io
import time
import threading
import uuid
from decimal import Decimal, ROUND_HALF_UP
import html as _html
import logging
import random
import unicodedata
import numpy as np
from seguridad_auth import autenticar, verificar_usuario, hash_password_seguro, bcrypt_disponible
from telegram_deeplink import render_boton_telegram
from fp_edicion_ui import ui_boton_bolsas, ui_boton_compromisos, ui_boton_perfil
from fp_fase4_ui import ui_planificacion, ui_boton_cascada, ui_boton_deudas, ui_boton_metas
from fp_fase5_inteligencia import ui_panel_inteligencia, limpiar_cache as limpiar_cache_inteligencia
from types import SimpleNamespace
from contextlib import nullcontext
try:   # Rediseño 2026-10 · Modo Pro y encabezado en un módulo aparte; si falla, la Terminal sigue con las vistas previas
    import pro_ui
except Exception as _ex_pro_ui:
    pro_ui = None
    logging.getLogger("apportafolio.terminal").warning("pro_ui no disponible: %s", _ex_pro_ui)
try:   # Carta CMA edición Pro (PDF con gráficas); si falta, el Modo Pro entrega la carta base
    import carta_pro
except Exception as _ex_carta_pro:
    carta_pro = None
    logging.getLogger("apportafolio.terminal").warning("carta_pro no disponible: %s", _ex_carta_pro)
try:   # Rediseño 2026-10 · «Tu dinero hoy» (tier gratuito); si falla, se dibuja la versión anterior
    import fp_ui
except Exception as _ex_fp_ui:
    fp_ui = None
    logging.getLogger("apportafolio.terminal").warning("fp_ui no disponible: %s", _ex_fp_ui)


def _modulo_fresco(mod):
    """Streamlit Cloud, tras un push, vuelve a correr app.py pero puede conservar en memoria la versión VIEJA de los módulos
    importados (pro_ui, carta_pro). Si el archivo cambió desde que se cargó, se recarga; así app.py y sus módulos van parejos."""
    if mod is None:
        return None
    try:
        import importlib
        mt = os.path.getmtime(mod.__file__)
        if getattr(mod, "_ap_mtime", None) != mt:
            mod = importlib.reload(mod)
            mod._ap_mtime = mt
    except Exception as ex:
        logging.getLogger("apportafolio.terminal").warning("Recarga de módulo %s: %s", getattr(mod, "__name__", "?"), ex)
    return mod


pro_ui, carta_pro = _modulo_fresco(pro_ui), _modulo_fresco(carta_pro)
fp_ui = _modulo_fresco(fp_ui)
from fp_fase6_ui_importacion import ui_boton_importacion

log_app = logging.getLogger("apportafolio.terminal")
if not logging.getLogger().handlers: logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

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

# Paleta institucional para Plotly (espejo de las variables CSS --ap-* y de .streamlit/config.toml).
AP_COLORS = {
    "bg": "#050608",
    "surface": "#0b0f17",
    "surface_2": "#111723",
    "border": "#1c2331",
    "border_strong": "#2a3344",
    "grid": "rgba(139, 148, 167, 0.10)",
    "text": "#e6e9ef",
    "text_muted": "#8b94a7",
    "text_faint": "#5b6475",
    "gold": "#d4af37",
    "gold_fill": "rgba(212, 175, 55, 0.15)",
    "positive": "#34d399",
    "positive_fill": "rgba(52, 211, 153, 0.12)",
    "negative": "#94a3b8",
    "negative_fill": "rgba(148, 163, 184, 0.12)",
    "info": "#c084fc",
}
AP_FONT_SANS = "Inter, -apple-system, Segoe UI, sans-serif"
AP_FONT_SERIF = "Playfair Display, Georgia, serif"


def style_financial_figure(fig, height=None, title=None, senior=False, showlegend=None, margin=None,
                           xgrid=False, ygrid=True):
    """Estética institucional común a todas las gráficas: fondo transparente, tipografía Inter/Playfair,
    grids discretos (solo el eje de valores por defecto) y tooltips oscuros. No toca trazas ni datos;
    cada gráfica puede sobrescribir después lo que necesite (hovermode, tickprefix, ejes secundarios)."""
    base = 15 if senior else 12
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=AP_FONT_SANS, color=AP_COLORS["text_muted"], size=base),
        margin=margin or dict(t=40 if title else 10, b=10, l=10, r=10),
        hoverlabel=dict(bgcolor=AP_COLORS["surface_2"], bordercolor=AP_COLORS["border_strong"],
                        font=dict(family=AP_FONT_SANS, color=AP_COLORS["text"], size=base)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=AP_COLORS["text_muted"], size=base - 1)),
    )
    if height: layout["height"] = height
    if showlegend is not None: layout["showlegend"] = showlegend
    if title:
        layout["title"] = dict(text=title, x=0, xanchor="left",
                               font=dict(family=AP_FONT_SERIF, size=base + 4, color=AP_COLORS["text"]))
    fig.update_layout(**layout)
    ejes = dict(gridcolor=AP_COLORS["grid"], zerolinecolor=AP_COLORS["border_strong"],
                linecolor=AP_COLORS["border"], tickfont=dict(color=AP_COLORS["text_faint"]))
    fig.update_xaxes(showgrid=xgrid, **ejes)
    fig.update_yaxes(showgrid=ygrid, **ejes)
    if fig.layout.coloraxis.colorscale is not None:   # px.imshow / px.sunburst con escala continua
        fig.update_coloraxes(colorbar=dict(outlinewidth=0, thickness=10,
                                           tickfont=dict(color=AP_COLORS["text_faint"], size=base - 1)))
    return fig

# ==========================================
# 2. ESTILOS GLOBALES · PRIVATE WEALTH TERMINAL
# ==========================================
# Paleta centralizada en variables CSS (:root). Los mismos valores viven en
# .streamlit/config.toml (tema nativo) y en AP_COLORS (gráficas Plotly).
st.markdown("""
<style translate="no" class="notranslate">
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=Inter:wght@300;400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@200;300;400;600&display=swap');

:root {
    --ap-bg: #050608;
    --ap-surface: #0b0f17;
    --ap-surface-2: #111723;
    --ap-border: #1c2331;
    --ap-border-strong: #2a3344;
    --ap-text: #e6e9ef;
    --ap-text-muted: #8b94a7;
    --ap-text-faint: #5b6475;
    --ap-gold: #d4af37;
    --ap-gold-soft: rgba(212, 175, 55, 0.10);
    --ap-gold-line: rgba(212, 175, 55, 0.28);
    --ap-positive: #34d399;
    --ap-negative: #94a3b8;
    --ap-info: #c084fc;
    --ap-cyan: #00f0ff;
    --ap-font-sans: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    --ap-font-serif: 'Playfair Display', Georgia, serif;
    --ap-radius: 14px;
    --ap-radius-sm: 8px;
    --ap-shadow: 0 1px 0 rgba(255,255,255,0.02) inset, 0 10px 30px rgba(0,0,0,0.35);
}

/* Lienzo base */
[data-testid="stAppViewContainer"], .stApp { font-family: var(--ap-font-sans) !important; color: var(--ap-text);
    background: radial-gradient(1100px 700px at 18% 12%, rgba(255,255,255,0.03), transparent 62%),
                radial-gradient(900px 600px at 88% 96%, rgba(201,162,74,0.04), transparent 60%), var(--ap-bg) !important;
    background-attachment: fixed !important; }
[data-testid="stSidebar"] { background-color: #07080b !important; border-right: 1px solid var(--ap-border) !important; }
.block-container { padding-top: 2.2rem !important; }

/* Limpieza del cromo nativo de Streamlit */
header[data-testid="stHeader"] { background: transparent !important; height: 2.6rem; }
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
#MainMenu { visibility: hidden; } footer { visibility: hidden; height: 0; }
hr { border-color: var(--ap-border) !important; }

/* Tooltips ⓘ (táctiles y con foco de teclado) */
.tooltip-container { position: relative; display: inline-block; cursor: pointer; margin-left: 6px; color: var(--ap-gold); font-weight: 500; font-family: var(--ap-font-sans); font-size: 0.8rem; opacity: 0.85; }
.tooltip-text {
    visibility: hidden; background-color: var(--ap-surface-2); color: var(--ap-text); text-align: left;
    padding: 10px 12px; border-radius: var(--ap-radius-sm); border: 1px solid var(--ap-border-strong);
    position: absolute; z-index: 100; bottom: 130%; left: 50%; transform: translateX(-50%);
    font-size: 0.78rem; width: 230px; box-shadow: 0 12px 28px rgba(0,0,0,0.55);
    opacity: 0; transition: opacity 0.2s; text-transform: none; letter-spacing: normal; font-weight: 400; line-height: 1.45;
}
.tooltip-container:hover .tooltip-text, .tooltip-container:focus .tooltip-text, .tooltip-container:active .tooltip-text { visibility: visible; opacity: 1; }

/* Pestañas: subrayado sobrio en lugar de píldoras */
div[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--ap-border); gap: 4px; }
div[data-testid="stTabs"] button { background: transparent !important; border: none !important; border-radius: 0 !important; color: var(--ap-text-muted) !important; padding: 10px 16px !important; font-family: var(--ap-font-sans) !important; font-weight: 500 !important; font-size: 0.9rem !important; letter-spacing: 0.3px; transition: color 0.2s ease; }
div[data-testid="stTabs"] button:hover { color: var(--ap-text) !important; }
div[data-testid="stTabs"] button[aria-selected="true"] { color: var(--ap-gold) !important; }
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--ap-gold) !important; height: 2px !important; }

/* Tarjetas de métricas y cajas de detalle (sobrias, sin glassmorphism) */
.metric-card, .pos-box { background: var(--ap-surface) !important; border-radius: var(--ap-radius) !important; border: 1px solid var(--ap-border) !important; padding: 22px 24px !important; margin-bottom: 16px !important; box-shadow: var(--ap-shadow) !important; transition: border-color 0.2s ease; }
.metric-card:hover { border-color: var(--ap-border-strong) !important; }
.metric-card--primary { background: linear-gradient(180deg, var(--ap-surface-2) 0%, var(--ap-surface) 100%) !important; border-color: var(--ap-gold-line) !important; position: relative; overflow: hidden; }
.metric-card--primary::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--ap-gold); }
.metric-card--primary .metric-value { font-size: 3.1rem !important; }
.metric-card--primary:hover { border-color: var(--ap-gold) !important; }

.metric-title { color: var(--ap-text-muted) !important; font-size: 0.7rem !important; font-weight: 500 !important; text-transform: uppercase !important; letter-spacing: 1.8px !important; margin-bottom: 6px !important; font-family: var(--ap-font-sans) !important; display: flex; align-items: center; }
.metric-value { font-family: var(--ap-font-serif) !important; font-size: 2.4rem !important; font-weight: 400 !important; color: #ffffff !important; letter-spacing: -0.5px !important; line-height: 1.1 !important; margin: 8px 0 !important; font-variant-numeric: tabular-nums; }
.metric-subtext { font-size: 0.85rem !important; margin-top: 6px !important; font-weight: 400 !important; color: var(--ap-text-faint) !important; font-family: var(--ap-font-sans) !important; }

/* KPI del home: borde dorado (mismo tono que la onda de la portada) y una luz que lo recorre cada 12 s, en cascada */
@property --ap-ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes ap-borde-luz { 0% { --ap-ang: 0deg; opacity: 0; } 4% { opacity: 1; } 34% { opacity: 1; }
    38% { --ap-ang: 360deg; opacity: 0; } 100% { --ap-ang: 360deg; opacity: 0; } }
.metric-card.kpi { position: relative; border-color: rgba(201, 162, 74, 0.38) !important; }
.metric-card.kpi:hover { border-color: rgba(233, 211, 154, 0.6) !important; }
.metric-card.kpi::after { content: ""; position: absolute; inset: 0; border-radius: inherit; padding: 1.2px; pointer-events: none; opacity: 0;
    background: conic-gradient(from var(--ap-ang), transparent 0deg, transparent 290deg, rgba(233,211,154,0) 312deg, rgba(255,244,214,0.9) 338deg, rgba(233,211,154,0) 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ap-borde-luz 12s linear 2s infinite; }
.metric-card.kpi.kpi-2::after { animation-delay: 3.4s; }
.metric-card.kpi.kpi-3::after { animation-delay: 4.8s; }
.metric-card.kpi.kpi-4::after { animation-delay: 6.2s; }
@media (prefers-reduced-motion: reduce) { .metric-card.kpi::after { animation: none !important; } }

/* ===== Rediseño 2026-10 · piel "Marco de luz" para el modo sencillo ===== */
/* Filo dorado con luz (tarjetas HTML y contenedores con key) */
.ap-filo, .st-key-bola_card, .st-key-sol_card, .st-key-carta_card { position: relative; border: 1px solid rgba(201,162,74,0.38) !important; border-radius: 14px; }
.st-key-bola_card, .st-key-sol_card, .st-key-carta_card { background: var(--ap-surface); padding: 18px 20px 10px; box-shadow: var(--ap-shadow); }
.ap-filo::after, .st-key-bola_card::after, .st-key-sol_card::after, .st-key-carta_card::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; padding: 1.2px; pointer-events: none; opacity: 0; z-index: 2;
    background: conic-gradient(from var(--ap-ang), transparent 0deg, transparent 290deg, rgba(233,211,154,0) 312deg, rgba(255,244,214,0.9) 338deg, rgba(233,211,154,0) 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ap-borde-luz 12s linear 2s infinite; }
.st-key-bola_card::after { animation-delay: 4s; } .ap-franja.ap-filo::after { animation-delay: 6s; }
.st-key-sol_card::after { animation-delay: 8s; } .st-key-carta_card::after { animation-delay: 3s; }
.ap-t { color: var(--ap-text-muted); font-size: 0.66rem; font-weight: 500; letter-spacing: 1.8px; text-transform: uppercase; margin: 0 0 6px; display: flex; align-items: center; }
.ap-v { font-family: var(--ap-font-serif); font-weight: 400; color: #ffffff; line-height: 1.1; margin: 0; font-variant-numeric: tabular-nums; }
.ap-s { color: var(--ap-text-faint); font-size: 0.82rem; margin: 8px 0 0; }
.ap-pos { color: #5fbf9a !important; } .ap-neg { color: var(--ap-negative) !important; } .ap-oro { color: #e2c575 !important; }

/* Indicadores · Patrimonio protagonista */
.ap-hero { display: grid; grid-template-columns: 1.3fr 1fr; background: var(--ap-surface); box-shadow: var(--ap-shadow); margin-bottom: 18px; }
.ap-hero .izq { padding: 28px 30px; border-right: 1px solid var(--ap-border); min-width: 0; }
.ap-hero .izq .ap-v { font-size: clamp(2.3rem, 4.2vw, 3.3rem); margin-top: 6px; }
.ap-hero .der { display: grid; grid-template-rows: repeat(3, 1fr); min-width: 0; }
.ap-hero .der > div { padding: 14px 24px; border-bottom: 1px solid var(--ap-border); display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.ap-hero .der > div:last-child { border-bottom: 0; }
.ap-hero .der .ap-t { margin: 0; }
.ap-hero .der .ap-v { font-size: 1.45rem; text-align: right; }

/* Progreso · franja única */
.ap-franja { display: grid; grid-template-columns: repeat(3, 1fr); background: var(--ap-surface); box-shadow: var(--ap-shadow); margin-bottom: 18px; }
.ap-franja > div { padding: 20px 24px; border-left: 1px solid var(--ap-border); min-width: 0; }
.ap-franja > div:first-child { border-left: 0; }
.ap-franja .ap-v { font-size: 2rem; }
@keyframes ap-barre { 0% { transform: translateX(-120%); } 30%, 100% { transform: translateX(560%); } }
.ap-barra { position: relative; height: 8px; border-radius: 6px; background: var(--ap-surface-2); border: 1px solid var(--ap-border); overflow: hidden; margin-top: 14px; }
.ap-barra b { position: relative; overflow: hidden; display: block; height: 100%; background: linear-gradient(90deg, #a8883f, #e2c575); }
.ap-barra b::after { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 18%; background: linear-gradient(90deg, transparent, rgba(255,244,214,0.75), transparent); animation: ap-barre 8s ease-in-out 1.5s infinite; }

/* Tablas HTML (posiciones agrupadas e historial) */
.ap-tw { overflow: auto; border: 1px solid var(--ap-border); border-radius: 12px; background: var(--ap-surface); margin-bottom: 8px; }
.ap-tw table { width: 100%; border-collapse: collapse; font-size: 0.86rem; min-width: 560px; font-variant-numeric: tabular-nums; }
.ap-tw th { position: sticky; top: 0; background: var(--ap-surface); text-align: left; font-size: 0.64rem; font-weight: 500; letter-spacing: 1.6px; text-transform: uppercase; color: var(--ap-text-faint); padding: 12px 14px; border-bottom: 1px solid var(--ap-border); white-space: nowrap; z-index: 1; }
.ap-tw td { padding: 11px 14px; border-bottom: 1px solid var(--ap-border); white-space: nowrap; color: var(--ap-text); }
.ap-tw tr:last-child td { border-bottom: 0; }
.ap-tw .n { text-align: right; }
.ap-tw .tk { font-weight: 600; letter-spacing: 0.02em; }
.ap-tw .grupo td { background: var(--ap-surface-2); color: #e2c575; font-size: 0.82rem; font-weight: 500; }
.ap-tw .grupo td:first-child { font-size: 0.7rem; letter-spacing: 1.6px; text-transform: uppercase; }
.ap-pill { display: inline-block; font-size: 0.62rem; font-weight: 600; letter-spacing: 1.2px; padding: 3px 8px; border-radius: 999px; border: 1px solid rgba(201,162,74,0.38); color: #e2c575; }
.ap-pill.gris { color: var(--ap-negative); border-color: var(--ap-border-strong); }

/* Composición · lista de pesos */
.ap-lista { background: var(--ap-surface); padding: 14px 20px; color: var(--ap-text); }
.ap-lista .fila { display: grid; grid-template-columns: 62px 1fr 92px 54px; gap: 12px; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--ap-border); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
.ap-lista .fila:last-child { border-bottom: 0; }
.ap-lista .track { height: 9px; background: var(--ap-surface-2); border-radius: 3px; overflow: hidden; }
.ap-lista .track b { display: block; height: 100%; background: linear-gradient(90deg, #8a6f33, #e2c575); }

/* Gráfica Bola de Nieve: luz que recorre la línea del valor (última traza = copia solo para la luz) */
@keyframes ap-hilo { 0% { stroke-dashoffset: 90; opacity: 0; } 3% { opacity: 1; } 34% { opacity: 1; } 38% { stroke-dashoffset: -2600; opacity: 0; } 100% { stroke-dashoffset: -2600; opacity: 0; } }
.st-key-bola_nieve .scatterlayer .trace:last-child .js-line { stroke-dasharray: 90 6000 !important; opacity: 0;
    filter: drop-shadow(0 0 4px rgba(233,211,154,0.95)); animation: ap-hilo 9s cubic-bezier(.45,.05,.35,1) 1.5s infinite; }

/* Carta protagonista */
.ap-carta { display: flex; gap: 18px; align-items: center; }
.ap-carta h3 { margin: 0 0 4px !important; padding: 0 !important; font-family: var(--ap-font-serif) !important; font-style: italic; font-weight: 400; color: #f3e2b0 !important; font-size: 1.3rem !important; }
.ap-carta p { margin: 0; color: var(--ap-text-muted); font-size: 0.85rem; }
.st-key-carta_card [data-testid="stDownloadButton"] button { background: linear-gradient(135deg, #b9913f 0%, #d9bb72 55%, #c9a24a 100%) !important; color: #15120b !important; border: 0 !important; font-weight: 600 !important; }
.st-key-carta_card [data-testid="stDownloadButton"] button p { color: #15120b !important; font-weight: 600 !important; }

@media (max-width: 760px) {
    .ap-hero, .ap-franja { grid-template-columns: 1fr; }
    .ap-hero .izq { border-right: 0; border-bottom: 1px solid var(--ap-border); padding: 22px; }
    .ap-franja > div { border-left: 0; border-top: 1px solid var(--ap-border); }
    .ap-franja > div:first-child { border-top: 0; }
    .ap-carta { flex-wrap: wrap; }
    .ap-lista .fila { grid-template-columns: 54px 1fr 84px; } .ap-lista .fila > :last-child { display: none; }
}
@media (prefers-reduced-motion: reduce) {
    .ap-filo::after, .st-key-bola_card::after, .st-key-sol_card::after, .st-key-carta_card::after, .ap-barra b::after,
    .st-key-bola_nieve .scatterlayer .trace:last-child .js-line, .st-key-sol path.surface { animation: none !important; }
}

/* Colores semánticos (se conservan los nombres de clase heredados) */
.text-neon-green, .pos-green { color: var(--ap-positive) !important; }
.text-neon-red, .pos-red { color: var(--ap-negative) !important; }
.text-neon-cyan { color: var(--ap-cyan) !important; }
.text-neon-purple { color: var(--ap-info) !important; }
.text-neon-gold { color: var(--ap-gold) !important; }

.pos-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; }
.pos-label { color: var(--ap-text-muted); font-weight: 400; }
.pos-val { color: #ffffff; font-weight: 500; font-family: var(--ap-font-sans); font-variant-numeric: tabular-nums; }

/* Cabecera editorial del home */
.ap-masthead { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 10px 24px; padding-bottom: 14px; margin-bottom: 18px; border-bottom: 1px solid var(--ap-border); }
.ap-eyebrow { font-family: var(--ap-font-sans); font-size: 0.68rem !important; font-weight: 600; letter-spacing: 2.6px; text-transform: uppercase; color: var(--ap-gold); margin: 0 0 6px 0; }
.ap-masthead h3 { font-family: var(--ap-font-serif); font-style: italic; font-weight: 400; color: #ffffff; margin: 0; padding: 0; font-size: 1.75rem; line-height: 1.15; }
.ap-meta { display: flex; gap: 22px; flex-wrap: wrap; }
.ap-meta-item { display: flex; flex-direction: column; align-items: flex-end; }
.ap-meta-label { font-size: 0.64rem; letter-spacing: 1.8px; text-transform: uppercase; color: var(--ap-text-faint); }
.ap-meta-value { font-size: 0.95rem; color: var(--ap-text); font-weight: 500; font-variant-numeric: tabular-nums; }

/* Widgets nativos */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button { font-family: var(--ap-font-sans) !important; font-weight: 500 !important; letter-spacing: 0.3px; }
[data-testid="stExpander"] details { border-color: var(--ap-border) !important; border-radius: var(--ap-radius-sm) !important; background: var(--ap-surface); }

@media (max-width: 800px) {
    .metric-value { font-size: 2rem !important; }
    .metric-card--primary .metric-value { font-size: 2.4rem !important; }
    .ap-meta-item { align-items: flex-start; }
}
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

# --- Sprint 0 · FX: moneda REAL de cotización ---------------------------------
# Evita multiplicar por USD/MXN algo que ya cotiza en pesos (ej. AMXB.MX, WALMEX.MX, BTC-MXN).
# Camino rápido sin red: .MX / -MXN -> MXN; -USD o sin sufijo (listado de EE.UU.) -> USD.
# Solo los sufijos ambiguos (.L, .DE, .AS...) consultan fast_info.currency, cacheado 1 día.
@st.cache_data(ttl=86400, max_entries=500, show_spinner=False)
def moneda_cotizacion(yf_symbol):
    s = str(yf_symbol or "").upper().strip()
    if not s:
        return "USD"
    if s.endswith(".MX") or s.endswith("-MXN"):
        return "MXN"
    if s.endswith("-USD") or ("." not in s and "=" not in s and not s.startswith("^")):
        return "USD"
    try:
        moneda = yf.Ticker(s).fast_info.currency
        return str(moneda).strip() if moneda else "USD"   # se respeta "GBp" (peniques) vs "GBP"
    except Exception:
        return "USD"   # sin dato: mismo supuesto que antes (USD)

def _factor_a_mxn(moneda, fx_mxn, usd):
    """Pesos por 1 unidad de la moneda de cotización. Moneda desconocida -> USD (comportamiento previo)."""
    return fx_mxn.get(moneda, usd)

# --- POOL DE CONEXIONES (PostgreSQL / Neon) ---------------------------------
# Un solo pool por proceso, compartido por todas las sesiones. Una conexión rota se descarta
# individualmente (el pool abre otra bajo demanda); nunca se cierra el pool completo.
POOL_MIN_CONEXIONES = 2
POOL_MAX_CONEXIONES = 10
POOL_ESPERA_S = 15   # tiempo máximo que una sesión espera un cupo libre antes de rendirse

@st.cache_resource
def get_pool():
    return pg_pool.ThreadedConnectionPool(
        POOL_MIN_CONEXIONES, POOL_MAX_CONEXIONES, dsn=st.secrets["DATABASE_URL"],
        connect_timeout=10, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5
    )

@st.cache_resource
def _cupos_pool():
    """ThreadedConnectionPool lanza PoolError al agotarse en vez de esperar; el semáforo hace que
    las sesiones hagan fila (con tope de tiempo) en lugar de fallar al instante."""
    return threading.BoundedSemaphore(POOL_MAX_CONEXIONES)

# --- CACHÉ DE LECTURAS + INVALIDACIÓN AUTOMÁTICA ------------------------------
# Las lecturas por cliente se cachean (st.cache_data, siempre con uid en la clave). Cualquier escritura
# confirmada por db_conn() (INSERT/UPDATE/DELETE/DDL o funciones fp_* que escriben) limpia esas cachés,
# venga de app.py o de los módulos fp_*. Lo que registre el bot por Telegram aparece al vencer el TTL.
_ESCRITURA_RE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|MERGE|ALTER|CREATE|DROP|TRUNCATE)\b"
    r"|^\s*WITH\b[\s\S]*\b(INSERT|UPDATE|DELETE)\b"
    r"|\bfp_(generar_codigo_vinculacion|revocar_vinculo_telegram)\s*\(", re.IGNORECASE)
_hilo_db = threading.local()   # cada sesión de Streamlit corre en su propio hilo
_CACHES_LECTURA = []

class _CursorRastreador(psycopg2.extensions.cursor):
    """Cursor normal que anota si la transacción en curso escribió algo."""
    def _anotar(self, query):
        if getattr(_hilo_db, "escritura", False): return
        try:
            texto = query.decode() if isinstance(query, bytes) else (query if isinstance(query, str) else query.as_string(self.connection))
        except Exception:
            texto = "INSERT"   # consulta no legible: se asume escritura (invalidar de más es seguro)
        if _ESCRITURA_RE.search(texto): _hilo_db.escritura = True
    def execute(self, query, vars=None):
        self._anotar(query)
        return super().execute(query, vars)
    def executemany(self, query, vars_list):
        self._anotar(query)
        return super().executemany(query, vars_list)

def lectura_cacheada(ttl):
    """st.cache_data para lecturas de Neon. La función decorada DEBE recibir el uid si lee datos de un cliente."""
    def deco(fn):
        cacheada = st.cache_data(ttl=ttl, show_spinner=False)(fn)
        _CACHES_LECTURA.append(cacheada)
        return cacheada
    return deco

def invalidar_lecturas():
    for fn in _CACHES_LECTURA: fn.clear()
    limpiar_cache_inteligencia()

def _conexion_valida(conn):
    try:
        if conn.closed: return False
        conn.rollback()
        with conn.cursor() as cur: cur.execute("SELECT 1")
        conn.rollback()
        return True
    except Exception:
        return False

def _descartar_conexion(pool, conn):
    """Cierra SOLO esta conexión y libera su lugar en el pool; las de otras sesiones no se tocan."""
    try: pool.putconn(conn, close=True)
    except Exception:
        try: conn.close()
        except Exception: pass

@contextmanager
def db_conn(autocommit=False):
    cupos = _cupos_pool()
    if not cupos.acquire(timeout=POOL_ESPERA_S):
        raise RuntimeError("La base de datos está saturada: no hubo una conexión libre a tiempo.")
    try:
        pool = get_pool()
        conn = None
        for _ in range(3):
            try:
                candidata = pool.getconn()
            except pg_pool.PoolError:
                time.sleep(0.2)
                continue
            if _conexion_valida(candidata):
                conn = candidata
                break
            _descartar_conexion(pool, candidata)   # rota: se cierra solo esta y se pide otra
        if conn is None:
            raise RuntimeError("No fue posible obtener una conexión válida a la base de datos.")
        rota = False
        _hilo_db.escritura = False
        try:
            conn.autocommit = autocommit
            conn.cursor_factory = _CursorRastreador
            yield conn
            if not autocommit: conn.commit()
            if _hilo_db.escritura: invalidar_lecturas()
        except Exception as e:
            rota = isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))
            try: conn.rollback()
            except Exception: rota = True
            raise
        finally:
            _hilo_db.escritura = False
            try: conn.autocommit = False; conn.cursor_factory = None
            except Exception: rota = True
            if rota or conn.closed:
                _descartar_conexion(pool, conn)
            else:
                try: pool.putconn(conn)
                except Exception: pass
    finally:
        cupos.release()

def read_df(sql, params=None):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columnas = [d[0] for d in cur.description]
            filas = cur.fetchall()
    return pd.DataFrame(filas, columns=columnas)

@lectura_cacheada(ttl=300)
def get_user_profile(uid):
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT dca_frequency, goal_name FROM users WHERE user_id=%s", (uid,))
            fila = cur.fetchone()
        return (fila[0] or "MENSUAL", fila[1] or "Libertad Financiera")
    except Exception:
        return ("MENSUAL", "Libertad Financiera")

def hash_password(password: str) -> str: return hashlib.sha256(password.encode()).hexdigest()

def dinero_exacto(valor, decimales=2):
    """float/str/Decimal -> Decimal redondeado (half-up). str() evita arrastrar el error binario del float."""
    return Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)

@st.cache_resource
def init_db():
    # Sprint 0 · Seguridad: sin secreto de admin la app se detiene (antes caía en "clave_temporal_local").
    try: admin_pwd = str(st.secrets["admin_password"]).strip()
    except Exception: admin_pwd = os.environ.get("CMA_ADMIN_PASSWORD", "").strip()
    if not admin_pwd or admin_pwd == "clave_temporal_local":
        st.error("Configuración incompleta: define `admin_password` en .streamlit/secrets.toml "
                 "(o la variable de entorno CMA_ADMIN_PASSWORD). La app no arranca sin ella.")
        st.stop()
    if not bcrypt_disponible():
        st.error("Configuración incompleta: falta el paquete `bcrypt` (requirements.txt). "
                 "La app no arranca sin hashing seguro de contraseñas.")
        st.stop()
    with db_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            # Precisión financiera: NUMERIC exacto (nunca REAL/float4). Escalas: títulos 8 (cripto fraccional),
            # precios 6, comisiones/IVA 4 (moneda de cotización), tipo de cambio 6, montos MXN 2 (centavos).
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);
                CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, user_id TEXT, timestamp TEXT, fecha TEXT, tipo_operacion TEXT, ticker TEXT, clase TEXT, plataforma TEXT, moneda TEXT, titulos NUMERIC(24,8), precio_unitario NUMERIC(20,6), comision NUMERIC(18,4), iva NUMERIC(18,4), tipo_cambio NUMERIC(12,6), total_mxn NUMERIC(18,2));
                CREATE TABLE IF NOT EXISTS cash_movements (id TEXT PRIMARY KEY, user_id TEXT, fecha TEXT, tipo TEXT, concepto TEXT, monto_mxn NUMERIC(18,2));
            """)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dca_frequency TEXT DEFAULT 'MENSUAL'")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_name TEXT DEFAULT 'Libertad Financiera'")
            cur.execute("INSERT INTO users (user_id, username, password_hash, dca_frequency, goal_name) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING", ("USR-001", "alex_admin", hash_password_seguro(admin_pwd), "MENSUAL", "Fondo Institucional"))   # Sprint 0: bcrypt
            # P0-B · Roles: CLIENTE por omisión; el gestor original (USR-001) siempre es ADMIN.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rol TEXT DEFAULT 'CLIENTE'")
            cur.execute("UPDATE users SET rol = 'ADMIN' WHERE user_id = 'USR-001' AND rol IS DISTINCT FROM 'ADMIN'")
    return True

@lectura_cacheada(ttl=60)
def es_admin(uid):
    """P0-B · El rol se lee de la base en cada rerun (nunca de session_state, que el cliente no controla pero sí persiste)."""
    if not uid: return False
    if uid == "USR-001": return True
    try:
        df = read_df("SELECT rol FROM users WHERE user_id=%s", (uid,))
        return (not df.empty) and str(df["rol"].iloc[0] or "").upper() == "ADMIN"
    except Exception:
        return False

init_db()

PROMPT_MAESTRO = """
ROL
Eres el "Motor Algorítmico V5" de APortafolio: analista senior de un Multi-Family Office con doble especialidad en análisis cuantitativo-técnico y análisis fundamental. Tu mandato es emitir una LECTURA ANALÍTICA E INFORMATIVA de las señales observadas: describes escenarios y parámetros cuantitativos, nunca instruyes al inversionista a comprar, vender o mantener. El inversionista es mexicano y su moneda base es MXN.

FECHA DE ANÁLISIS: {fecha_hoy}

1) FICHA DEL ACTIVO
- Ticker: {ticker} | Clase: {clase} | Sector: {sector}
- Precio actual: {current_price} (moneda de cotización) | Tipo de cambio USD/MXN: {usd_mxn}

2) BLOQUE TÉCNICO (precalculado y verificado en Python; NO lo recalcules ni lo contradigas)
- Rango 52 semanas: {low_52w} a {high_52w} | Posición en el rango: {pos_52w} (0% = mínimo, 100% = máximo) | Distancia al máximo: {dist_max_52w}
- MA50: {ma50} (precio vs MA50: {dist_ma50}) | MA200: {ma200} (precio vs MA200: {dist_ma200})
- Variación 12 meses: {cambio_1y} | RSI(14): {rsi14}
- Volatilidad anualizada: {vol_anual} | Drawdown máximo 12 meses: {max_dd}

3) BLOQUE FUNDAMENTAL
- P/E (trailing): {pe_ratio} | EPS (trailing): {eps}
- Si P/E o EPS aparecen como N/A, el activo es probablemente un ETF, un criptoactivo o una empresa sin utilidades: NO inventes múltiplos; sustituye la lectura de valuación por tendencia, posición en rango y riesgo.

4) CONTEXTO DE CARTERA (moneda base MXN)
- Estado: {estado_posicion}
- Costo promedio: {avg_cost_mxn} MXN (equivalente aproximado en moneda de cotización: {avg_cost_equiv})
- Retorno neto de la posición: {net_return_pct} ({pnl_mxn} MXN). Dato autoritativo: ya incluye efecto cambiario y comisiones.
- Peso en el portafolio: {portfolio_weight}

5) FLUJO DE NOTICIAS (titulares recientes)
{macro_news_context}

6) AGENDA MACRO
{fed_cpi_events}

MARCO DE DECISIÓN (aplícalo en este orden)
A. Tendencia: Precio > MA50 > MA200 = alcista; Precio < MA50 < MA200 = bajista; cualquier otra combinación = transición.
B. Timing: RSI(14) > 70 = sobrecompra (no perseguir el precio); RSI(14) < 30 = sobreventa (oportunidad solo si la tendencia primaria no está rota o la valuación lo respalda). Posición en rango < 25% = zona de descuento; > 85% = margen de seguridad reducido.
C. Valuación: P/E < 20 atractivo; 20 a 40 razonable si existe crecimiento; > 40 exigente y requiere un catalizador visible en las noticias. EPS negativo o nulo penaliza.
D. Riesgo de cartera: peso > 20% = riesgo de concentración (el veredicto máximo es DCA FUERTE salvo descuento extremo); peso > 30% = sesgo hacia REDUCIR POSICIÓN. Volatilidad > 45% o drawdown peor que -30% obligan a escalonar entradas.
E. Costo promedio: con pérdida y tesis intacta, promediar a la baja es válido; con tesis rota, no lo es. Con ganancia amplia (> 40%) y sobrecompra, evalúa tomar utilidades parciales.
F. Noticias: úsalas solo como catalizador o riesgo. No inventes hechos, cifras, fechas de reporte ni eventos que no estén en los titulares o en los datos.

CATEGORÍA DE SEÑAL (elige EXACTAMENTE una y que sea coherente con el rating; son etiquetas internas de clasificación cuantitativa, no instrucciones al inversionista)
- "COMPRA AGRESIVA" (rating 9 o 10): confluencia técnica, de valuación y de catalizador; asimetría clara al alza.
- "DCA FUERTE" (rating 7 u 8): tesis sólida con timing o valuación imperfectos; acumular de forma escalonada.
- "HOLD ESTRATÉGICO" (rating 4 a 6): relación riesgo-beneficio neutral; mantener y esperar un mejor punto de entrada.
- "REDUCIR POSICIÓN" (rating 1 a 3): deterioro técnico o fundamental, sobrevaluación o sobreconcentración. Si el activo NO está en cartera, significa "no abrir posición".

REGLAS DE REDACCIÓN
- Español profesional con tono de comité de inversión: directo, cuantitativo, sin relleno ni frases genéricas.
- Cada argumento debe citar al menos una cifra del bloque de datos (porcentajes, múltiplos o niveles de precio).
- bull_points y bear_points: de 2 a 4 elementos cada uno, máximo 20 palabras por elemento.
- macro_synthesis: un solo párrafo de 4 a 6 oraciones (máximo 120 palabras) que (1) describa la estructura técnica, (2) la contraste con la valuación, (3) integre noticias y agenda macro, (4) pondere la posición en cartera y (5) cierre con escenarios condicionales ("si el precio..., se observaría...") y niveles de referencia cuantitativos (MA50, MA200 o extremos del rango).
- Lenguaje informativo y condicional: "se observa", "el escenario sugiere", "los parámetros indican". Prohibido el imperativo y las instrucciones de inversión ("compra", "vende", "acumula", "mantén", "recorta").
- Prohibido: markdown, asteriscos, emojis, mencionar que eres una IA o señalar que faltan datos. El aviso legal lo agrega la aplicación.

FORMATO DE SALIDA
Responde ÚNICA Y EXCLUSIVAMENTE con un objeto JSON válido (sin texto antes ni después y sin bloques de código) con exactamente estas claves:
{{"verdict": "DCA FUERTE", "rating": 7, "bull_points": ["...", "..."], "bear_points": ["...", "..."], "macro_synthesis": "..."}}
"""

# P0-B · Blindaje legal. Las categorías internas del Motor V5 se muestran como escenarios, no como órdenes.
ETIQUETA_LECTURA_V5 = {
    "COMPRA AGRESIVA": "Señales favorables con alta confluencia",
    "DCA FUERTE": "Señales favorables moderadas",
    "HOLD ESTRATÉGICO": "Señales mixtas / neutrales",
    "REDUCIR POSICIÓN": "Señales desfavorables o de concentración",
}

AVISO_LECTURA_V5 = (
    "Aviso legal · Lectura cuantitativa con fines exclusivamente informativos y educativos. No constituye una "
    "recomendación personalizada, asesoría en inversiones ni una oferta o invitación a comprar, vender o mantener "
    "valores. Las señales se calculan de forma automatizada con datos públicos de mercado que pueden contener errores "
    "o retrasos, y no consideran su perfil de riesgo, horizonte ni situación financiera. Los rendimientos pasados no "
    "garantizan resultados futuros; invertir implica riesgo, incluida la pérdida del capital. Toda decisión de "
    "inversión es responsabilidad exclusiva del inversionista, quien puede consultar a un asesor en inversiones autorizado."
)

AVISO_BOLETIN_CIO = (
    "Aviso legal · Boletín generado automáticamente con apoyo de modelos de inteligencia artificial a partir de "
    "información pública. Es de carácter general e informativo: no evalúa la situación financiera, fiscal ni el perfil "
    "de riesgo de ninguna persona y no constituye recomendación de inversión, asesoría fiscal ni contable. Las fechas "
    "de reportes trimestrales, dividendos y eventos macroeconómicos deben verificarse en fuentes oficiales antes de "
    "tomar cualquier decisión. Invertir implica riesgo, incluida la pérdida del capital."
)

def html_aviso_legal(texto, margen_sup=12):
    return (f"<div class='notranslate' translate='no' style='margin-top:{margen_sup}px; padding:10px 14px; "
            f"border-left:2px solid rgba(212,175,55,0.45); background:rgba(8,11,19,0.45); border-radius:6px; "
            f"color:#8b949e; font-size:0.72rem; line-height:1.5;'>{_html.escape(texto)}</div>")

ASSET_CLASS = {"ISAC": "ETF", "XNAS": "ETF", "XDWH": "ETF", "EIMI": "ETF", "NUCL": "ETF", "GOOGL": "Acción", "MELI": "Acción", "NOW": "Acción", "ASML": "Acción", "NVO": "Acción", "MA": "Acción", "V": "Acción", "BTC": "Cripto"}
# Clase capturada en "Registrar Operación" -> clase de asignación (la que usan Smart DCA, sunburst y Carta CMA).
CLASE_FORMULARIO_A_ASIGNACION = {"ACCION": "Acción", "ACCIÓN": "Acción", "ETF": "ETF", "CRIPTO": "Cripto", "FIBRA/REIT": "FIBRA/REIT"}
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

# Códigos que indican saturación o fallo transitorio del proveedor: se salta al siguiente
# modelo de la cadena en silencio. 400/401/403 son permanentes (llave, payload) y cortan el ciclo.
GEMINI_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}

def _espera_backoff(resp, intento):
    """Pausa corta antes del siguiente modelo: respeta Retry-After (tope 2s) o usa backoff con jitter."""
    try:
        ra = float(resp.headers.get("Retry-After", "") or 0) if resp is not None else 0.0
    except (TypeError, ValueError):
        ra = 0.0
    if ra > 0: return min(ra, 2.0)
    return min(0.4 * (intento + 1), 1.5) + random.uniform(0, 0.25)

def llamar_gemini(prompt, api_key, temperature=0.2, json_mode=False, timeout=45, presupuesto_s=None):
    """Devuelve (texto, error). Firma compatible con la versión anterior (presupuesto_s es opcional).
    - 404 / 429 / 5xx / timeout / red / respuesta vacía o ilegible  -> se prueba el siguiente modelo.
    - 400 / 401 / 403 (errores permanentes)                            -> se corta el ciclo.
    - presupuesto_s limita el tiempo TOTAL de la cadena para no congelar la UI.
    El error se registra en logs del servidor; nunca debe mostrarse crudo al cliente."""
    import requests
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': str(api_key).strip()}
    gen_cfg = {"temperature": temperature}
    if json_mode: gen_cfg["responseMimeType"] = "application/json"
    # Alternativa más estricta (desactivada por seguridad: si el modelo no soporta el esquema responde 400
    # y todo caería al Plan B). Activar solo tras probarla con los modelos de la cadena:
    # if json_mode: gen_cfg["responseSchema"] = {"type": "OBJECT", "properties": {
    #     "verdict": {"type": "STRING", "enum": list(VEREDICTOS_V5)}, "rating": {"type": "INTEGER"},
    #     "bull_points": {"type": "ARRAY", "items": {"type": "STRING"}},
    #     "bear_points": {"type": "ARRAY", "items": {"type": "STRING"}},
    #     "macro_synthesis": {"type": "STRING"}}, "required": ["verdict", "rating", "macro_synthesis"]}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg}
    cadena = _cadena_modelos_gemini()
    limite = time.monotonic() + (presupuesto_s if presupuesto_s else timeout * max(1, len(cadena)))
    ultimo_error = "Sin respuesta de la API."
    for intento, modelo in enumerate(cadena):
        restante = limite - time.monotonic()
        if restante < 3:
            ultimo_error = f"Presupuesto de tiempo agotado antes de {modelo}. Último error: {ultimo_error}"
            log_app.warning("Gemini · %s", ultimo_error)
            break
        url = f"{GEMINI_API_BASE}/{modelo}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=(5, max(3.0, min(float(timeout), restante))))
        except requests.exceptions.RequestException as e:
            ultimo_error = f"{modelo}: fallo de red/timeout ({type(e).__name__})."
            log_app.warning("Gemini · %s -> siguiente modelo", ultimo_error)
            continue
        codigo = resp.status_code
        if codigo == 200:
            try:
                partes = resp.json()["candidates"][0]["content"]["parts"]
                texto = "".join(p.get("text", "") for p in partes if isinstance(p, dict) and not p.get("thought"))
                if texto.strip():
                    if intento > 0: log_app.info("Gemini · respondió %s tras %d fallo(s) previo(s).", modelo, intento)
                    return texto, ""
                ultimo_error = f"{modelo}: respuesta vacía (posible bloqueo de seguridad)."
            except Exception as e:
                ultimo_error = f"{modelo}: estructura de respuesta inesperada ({str(e)})."
            log_app.warning("Gemini · %s -> siguiente modelo", ultimo_error)
            continue
        if codigo == 404:
            ultimo_error = f"Error 404: el modelo '{modelo}' no está disponible."
            log_app.warning("Gemini · %s -> siguiente modelo", ultimo_error)
            continue
        if codigo in GEMINI_CODIGOS_TRANSITORIOS:
            ultimo_error = f"Error {codigo} en {modelo}: {resp.text[:200]}"
            log_app.warning("Gemini · %s -> siguiente modelo", ultimo_error)
            if intento < len(cadena) - 1:
                espera = _espera_backoff(resp, intento)
                if time.monotonic() + espera < limite - 3: time.sleep(espera)
            continue
        ultimo_error = f"Error {codigo}: {resp.text[:300]}"
        log_app.error("Gemini · error permanente, se corta la cadena: %s", ultimo_error)
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
# 3.1.1 MOTOR V5: MÉTRICAS TÉCNICAS, VEREDICTOS Y PLAN B LOCAL
# ==========================================
VEREDICTOS_V5 = ("COMPRA AGRESIVA", "DCA FUERTE", "HOLD ESTRATÉGICO", "REDUCIR POSICIÓN")
V5_TTL_PLAN_B_S = 120   # tras un fallo real de la API, el Plan B se reutiliza 2 min para no re-saturar ni frenar cada rerun

def _num_finito(valor):
    try:
        f = float(valor)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None

def _fmt_num(valor, patron="{:,.2f}", na="N/A"):
    v = _num_finito(valor)
    return patron.format(v) if v is not None else na

def html_seguro(texto):
    """Escapa HTML y neutraliza '$' (Streamlit interpreta $...$ como LaTeX dentro de st.markdown)."""
    return _html.escape(str(texto), quote=True).replace("$", "&#36;")

def calcular_tecnicos_v5(hist, precio, low_52, high_52):
    """Métricas técnicas deterministas del último año. Nunca lanza excepción: devuelve None en lo no calculable."""
    t = {"precio": _num_finito(precio) or 0.0, "ma50": None, "ma200": None, "dist_ma50": None, "dist_ma200": None,
         "cambio_1y": None, "rsi14": None, "vol_anual": None, "max_dd": None,
         "low_52": _num_finito(low_52), "high_52": _num_finito(high_52), "pos_52w": None, "dist_max_52w": None}
    try:
        cierre = pd.to_numeric(hist["Close"], errors="coerce").dropna().astype(float)
        if cierre.empty: return t
        p = t["precio"] or float(cierre.iloc[-1])
        t["precio"] = p
        t["ma50"] = float(cierre.tail(50).mean())
        t["ma200"] = float(cierre.tail(200).mean())
        if t["ma50"]: t["dist_ma50"] = (p / t["ma50"] - 1) * 100
        if t["ma200"]: t["dist_ma200"] = (p / t["ma200"] - 1) * 100
        if float(cierre.iloc[0]) != 0: t["cambio_1y"] = (float(cierre.iloc[-1]) / float(cierre.iloc[0]) - 1) * 100
        if len(cierre) > 15:
            delta = cierre.diff()
            ganancia = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
            perdida = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
            g, pe = _num_finito(ganancia.iloc[-1]), _num_finito(perdida.iloc[-1])
            if g is not None and pe is not None:
                t["rsi14"] = 100.0 if pe == 0 else 100 - 100 / (1 + g / pe)
        rets = cierre.pct_change().dropna()
        if len(rets) > 2:
            periodos = 365 if len(cierre) > 300 else 252   # cripto cotiza 7 días/semana
            t["vol_anual"] = float(rets.std() * np.sqrt(periodos) * 100)
        t["max_dd"] = float((cierre / cierre.cummax() - 1).min() * 100)
        lo, hi = t["low_52"], t["high_52"]
        if lo is not None and hi is not None and hi > lo:
            t["pos_52w"] = max(0.0, min(100.0, (p - lo) / (hi - lo) * 100))
            t["dist_max_52w"] = (p / hi - 1) * 100
    except Exception as e:
        log_app.warning("Motor V5 · métricas técnicas incompletas: %s", e)
    return t

def veredicto_por_rating(rating):
    r = _rating_seguro(rating)
    if r >= 9: return "COMPRA AGRESIVA"
    if r >= 7: return "DCA FUERTE"
    if r >= 4: return "HOLD ESTRATÉGICO"
    return "REDUCIR POSICIÓN"

def normalizar_veredicto(valor, rating):
    """Lleva cualquier texto del modelo a uno de los 4 veredictos canónicos; si es ambiguo, decide el rating."""
    s = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode().upper()
    if "AGRESIV" in s: return "COMPRA AGRESIVA"
    if "DCA" in s or "ACUMUL" in s: return "DCA FUERTE"
    if any(k in s for k in ("REDUC", "VEND", "VENTA", "EVITAR", "RECORT", "SALIR")): return "REDUCIR POSICIÓN"
    if any(k in s for k in ("HOLD", "MANTEN", "ESPERA", "NEUTRAL")): return "HOLD ESTRATÉGICO"
    if "COMPRA" in s: return "COMPRA AGRESIVA" if _rating_seguro(rating) >= 9 else "DCA FUERTE"
    return veredicto_por_rating(rating)

def _sintesis_local_v5(ticker, t, pe, eps, veredicto, is_owned, peso, ret_pct):
    """Síntesis en lenguaje natural construida solo con datos verificados (Plan B, indistinguible para el cliente)."""
    p, frases = t["precio"], []
    s = f"{ticker} cotiza en ${p:,.2f}"
    if t["dist_ma50"] is not None and t["dist_ma200"] is not None:
        s += f", {t['dist_ma50']:+.1f}% respecto a su MA50 y {t['dist_ma200']:+.1f}% frente a su MA200"
    if t["pos_52w"] is not None:
        s += f", en el {t['pos_52w']:.0f}% de su rango de 52 semanas (${t['low_52']:,.2f} a ${t['high_52']:,.2f})"
    frases.append(s + ".")

    ma50, ma200 = t["ma50"], t["ma200"]
    cambio = f", con un desempeño de {t['cambio_1y']:+.1f}% en 12 meses" if t["cambio_1y"] is not None else ""
    if ma50 and ma200:
        if p > ma50 > ma200: frases.append(f"La estructura de medias es alcista (precio sobre MA50 y MA200){cambio}.")
        elif p < ma50 < ma200: frases.append(f"La estructura de medias es bajista (precio bajo MA50 y MA200){cambio}; en este escenario aún no se observa confirmación de piso.")
        else: frases.append(f"Las medias móviles describen una fase de transición{cambio}, sin una tendencia primaria dominante.")

    rsi, vol = t["rsi14"], t["vol_anual"]
    if rsi is not None:
        if rsi >= 70: s = f"El RSI(14) en {rsi:.0f} advierte sobrecompra de corto plazo"
        elif rsi <= 30: s = f"El RSI(14) en {rsi:.0f} refleja sobreventa, típicamente zona de rebote táctico"
        else: s = f"El RSI(14) en {rsi:.0f} se mantiene en zona neutral"
        frases.append(s + (f", con una volatilidad anualizada de {vol:.1f}%." if vol is not None else "."))

    pe_n, eps_n = _num_finito(pe), _num_finito(eps)
    eps_txt = f" y un EPS de ${eps_n:,.2f}" if eps_n is not None else ""
    if pe_n is not None and pe_n > 0:
        if pe_n < 20: frases.append(f"Con un P/E de {pe_n:.1f}x{eps_txt}, la valuación luce atractiva en términos relativos y aporta margen de seguridad.")
        elif pe_n <= 40: frases.append(f"Con un P/E de {pe_n:.1f}x{eps_txt}, la valuación se ubica en un rango razonable para su perfil de crecimiento.")
        else: frases.append(f"Con un P/E de {pe_n:.1f}x{eps_txt}, la valuación es exigente y descuenta un crecimiento sostenido, lo que reduce el margen de seguridad.")
    else:
        frases.append("Al no reportar un múltiplo de utilidades aplicable (vehículo indexado, criptoactivo o utilidades negativas), la lectura descansa en la tendencia, la posición en rango y el riesgo.")

    if is_owned:
        s = f"La posición representa {peso:.1f}% del portafolio con un retorno acumulado de {ret_pct:+.1f}%"
        frases.append(s + (", nivel que ya implica riesgo de concentración." if peso > 20 else "."))
    else:
        frases.append("El activo no forma parte de la cartera y se analiza únicamente como referencia de observación.")

    # P0-B · Cierres informativos y condicionales (sin instrucciones de compra/venta).
    cierres = {
        "COMPRA AGRESIVA": "En conjunto, se observa una confluencia técnica y de valuación favorable; históricamente, escenarios así conviven con volatilidad, por lo que la MA50 funciona como nivel de referencia.",
        "DCA FUERTE": ("En conjunto, los parámetros muestran señales favorables moderadas; si el precio retrocediera hacia la MA50, el escenario se mantendría dentro de su tendencia vigente."
                       if (ma50 and p >= ma50) else "En conjunto, los parámetros muestran señales favorables moderadas mientras el precio consolida por debajo de la MA50, nivel que marcaría un cambio de escenario si se recupera."),
        "HOLD ESTRATÉGICO": "En conjunto, las señales son mixtas: la relación riesgo-beneficio observada es neutral y el escenario dependerá de la ruptura de la MA50 o de los extremos del rango.",
        "REDUCIR POSICIÓN": ("En conjunto, el balance técnico-fundamental es desfavorable" + (" y la concentración en cartera eleva la sensibilidad del portafolio a este activo." if is_owned else ".")
                             + " Una mejora de la estructura de medias modificaría este escenario."),
    }
    frases.append(cierres.get(veredicto, cierres["HOLD ESTRATÉGICO"]))
    return " ".join(frases)

def plan_b_local_v5(ticker, t, pe_ratio, eps, is_owned, p_peso, p_retorno_pct):
    """Scoring local. Conserva EXACTAMENTE las reglas de puntuación originales (score base 5, MA50/MA200,
    P/E, concentración); añade la guardia de tendencia bajista, viñetas descriptivas y la síntesis. Devuelve (veredicto, rating, bulls, bears, macro)."""
    score, bulls, bears = 5.0, [], []
    p, ma50, ma200 = t["precio"], t["ma50"], t["ma200"]
    if ma50 and ma200:
        if p < ma50 and p > ma200: score += 2.0; bulls.append("Corrección saludable a corto plazo.")
        elif p < ma200: score += 3.0; bulls.append("Cotiza bajo su MA200. Descuento profundo.")
        elif p > ma50 * 1.15: score -= 2.0; bears.append("Sobrecomprado (>15% arriba de la MA50).")
    if isinstance(pe_ratio, float):
        if pe_ratio < 20: score += 2.0; bulls.append(f"Valuación atractiva (P/E: {pe_ratio:.1f}).")
        elif pe_ratio > 40: score -= 1.5; bears.append(f"Valuación exigente/Premium (P/E: {pe_ratio:.1f}).")
    if is_owned and p_peso > 20.0: score -= 2.0; bears.append(f"Riesgo de Concentración ({p_peso:.1f}% del portafolio).")
    rating = max(1, min(10, int(score)))
    # Guardia anti "cuchillo cayendo" (misma regla que el PROMPT_MAESTRO, punto B): con tendencia primaria
    # bajista (precio < MA50 < MA200) el descuento no basta para COMPRA AGRESIVA; el techo es DCA FUERTE.
    if ma50 and ma200 and p < ma50 < ma200 and rating > 8: rating = 8
    veredicto = veredicto_por_rating(rating)

    # Viñetas descriptivas (no alteran el score)
    rsi, pos, vol, dd, c1y = t["rsi14"], t["pos_52w"], t["vol_anual"], t["max_dd"], t["cambio_1y"]
    if rsi is not None and rsi <= 30: bulls.append(f"RSI(14) en {rsi:.0f}: sobreventa técnica.")
    if rsi is not None and rsi >= 70: bears.append(f"RSI(14) en {rsi:.0f}: sobrecompra técnica.")
    if pos is not None and pos <= 25: bulls.append(f"Cotiza en el cuartil inferior de su rango de 52 semanas ({pos:.0f}%).")
    if pos is not None and pos >= 85: bears.append(f"Cerca de máximos de 52 semanas ({pos:.0f}% del rango): menor margen de seguridad.")
    if c1y is not None and c1y > 0: bulls.append(f"Tendencia de 12 meses positiva ({c1y:+.1f}%).")
    if vol is not None and vol > 45: bears.append(f"Volatilidad anualizada elevada ({vol:.1f}%).")
    if dd is not None and dd < -25: bears.append(f"Drawdown máximo de 12 meses de {dd:.1f}%.")
    if not bulls: bulls.append("Cotización líquida y continua que permite ajustar la exposición con precisión.")
    if not bears: bears.append("Sensibilidad a cambios en tasas de interés y en el apetito global por riesgo.")

    macro = _sintesis_local_v5(ticker, t, pe_ratio, eps, veredicto, is_owned, p_peso, p_retorno_pct)
    return veredicto, rating, bulls[:4], bears[:4], macro

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


@lectura_cacheada(ttl=30)
def fp_dinero_libre(uid, hoy):
    filas = _fp_consulta("SELECT * FROM fp_dinero_libre(%s, %s)", (uid, hoy))
    if not filas:
        return None
    dl = filas[0]
    for clave in _FP_TEXTO_MONTOS:
        dl[clave] = float(dl.get(clave) or 0)
    return dl


@lectura_cacheada(ttl=60)
def fp_bolsas(uid):
    return _fp_consulta(
        "SELECT nombre, tipo, aporte_periodo, saldo_acumulado, monto_objetivo FROM fp_bolsas "
        "WHERE user_id = %s AND activa ORDER BY prioridad, nombre", (uid,))


@lectura_cacheada(ttl=60)
def fp_proximos(uid, desde, hasta):
    return _fp_consulta(
        "SELECT fecha, nombre, tipo_movimiento, monto FROM fp_ocurrencias(%s, %s, %s) "
        "ORDER BY fecha, tipo_movimiento, nombre LIMIT 8", (uid, desde, hasta))


@lectura_cacheada(ttl=30)
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


@lectura_cacheada(ttl=300)
def fp_categorias(uid):
    return _fp_consulta(
        "SELECT categoria_id, nombre FROM fp_categorias WHERE user_id = %s OR user_id IS NULL ORDER BY nombre", (uid,))


@lectura_cacheada(ttl=300)
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


@lectura_cacheada(ttl=30)
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
        usuario_tg = f"@{html_seguro(vinculo['telegram_username'])}" if vinculo.get("telegram_username") else "tu Telegram"
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
        st.markdown(f"<div class='fp-codigo notranslate' translate='no'>{html_seguro(guardado['codigo'])}</div>"
                    f"<p class='fp-nota' style='text-align:center;'>Vence a las {hora} ({minutos} min). "
                    f"Envía este mensaje al bot:</p>", unsafe_allow_html=True)
        st.code(f"/vincular {guardado['codigo']}", language=None)
        _codigo_dl = str(guardado['codigo']).strip().upper()
        render_boton_telegram(_codigo_dl if _codigo_dl.startswith("CMA-") else f"CMA-{_codigo_dl}")
        try:
            bot = str(st.secrets["TELEGRAM_BOT_USERNAME"]).strip().lstrip("@")
        except Exception:
            bot = ""
        if bot:
            st.markdown(f"<p class='fp-nota' style='text-align:center;'><a href='https://t.me/{bot}' target='_blank' "
                        f"style='color:#d4af37; text-decoration:none;'>Abrir @{bot} en Telegram</a></p>",
                        unsafe_allow_html=True)


FP_ESTILOS_TELEGRAM = """
<style>
.fp-tg-banner { background: linear-gradient(135deg, rgba(212,175,55,0.10) 0%, rgba(8,11,19,0.95) 60%); border: 1px solid rgba(212,175,55,0.45); border-radius: 24px; padding: 26px 28px; margin: 4px 0 18px 0; box-shadow: 0 10px 28px rgba(0,0,0,0.45); }
.fp-tg-kicker { color: #d4af37; font-size: 0.72rem; letter-spacing: 3px; text-transform: uppercase; margin: 0 0 6px 0; font-family: 'Inter', sans-serif; }
.fp-tg-titulo { font-family: 'Playfair Display', serif; font-style: italic; color: #ffffff; font-size: 1.55rem; font-weight: 400; margin: 0 0 8px 0; line-height: 1.2; }
.fp-tg-texto { color: #cbd5e1; font-size: 0.9rem; line-height: 1.6; margin: 0 0 12px 0; }
.fp-tg-pasos { color: #8b949e; font-size: 0.85rem; line-height: 1.8; margin: 0; padding-left: 18px; }
.fp-tg-pasos b { color: #e5e7eb; font-weight: 500; }
.fp-tg-escudo { color: #64748b; font-size: 0.75rem; margin: 12px 0 0 0; }
</style>
"""


def fp_estado_telegram(uid):
    """'SIN_ESQUEMA' | 'VINCULADO' | 'PENDIENTE' | 'ERROR'. Una sola consulta por recarga."""
    try:
        if not fp_esquema_listo():
            return "SIN_ESQUEMA"
        return "VINCULADO" if fp_vinculo_activo(uid) else "PENDIENTE"
    except Exception:
        return "ERROR"


def _fp_ir_a_telegram():
    """Callback del botón lateral: lleva a 'Tu dinero hoy', donde vive el banner de vinculación."""
    st.session_state["seccion_app"] = SECCION_FP


def render_fp_telegram_banner(uid):
    """Vinculación como elemento protagonista (solo mientras NO esté vinculado)."""
    st.markdown(FP_ESTILOS_TELEGRAM, unsafe_allow_html=True)
    col_txt, col_accion = st.columns([1.35, 1], gap="large")
    with col_txt:
        st.markdown(
            "<div class='fp-tg-banner notranslate' translate='no'>"
            "<p class='fp-tg-kicker'>Paso 1 · 30 segundos</p>"
            "<p class='fp-tg-titulo'>Conecta tu Telegram y olvídate de capturar gastos</p>"
            "<p class='fp-tg-texto'>Escribes \"42 pasaje\" en el chat y tu mayordomo lo clasifica, lo suma a tu "
            "presupuesto y te dice cuánto te queda libre. Sin formularios.</p>"
            "<ol class='fp-tg-pasos'>"
            "<li>Toca <b>Generar código de vinculación</b>.</li>"
            "<li>Toca <b>Abrir en Telegram</b> (o envía <b>/vincular CMA-XXXXXX</b> al bot).</li>"
            "<li>Vuelve aquí y toca <b>Ya lo conecté</b>.</li></ol>"
            "<p class='fp-tg-escudo'>Nunca te pediremos contraseñas del banco ni NIPs.</p>"
            "</div>", unsafe_allow_html=True)
    with col_accion:
        st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
        render_fp_telegram(uid)          # mismo componente de siempre (claves de widget intactas)
        if st.session_state.get("fp_codigo_tg"):
            if st.button("Ya lo conecté · actualizar", key="fp_tg_refrescar", use_container_width=True):
                st.rerun()               # si ya quedó vinculado, el banner se convierte en la línea compacta


def render_fp_telegram_compacto(uid):
    """Ya vinculado: una línea discreta con opción de desconectar."""
    with st.expander("Telegram · conexión activa", expanded=False):
        render_fp_telegram(uid)


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


# --- Sprint 1 · Re-renders parciales -----------------------------------------
# Con @st.fragment, "Registrar", "Deshacer" y "Quitar" solo vuelven a ejecutar este bloque, no las ~2,300 líneas.
# Compatible con versiones viejas: st.experimental_fragment o, si no existe, función normal (rerun completo).
# Alternativa más amplia (descartada por seguridad): envolver también la tarjeta de Dinero Libre y la columna
# derecha; ahí viven ui_boton_compromisos/ui_boton_bolsas, que abren diálogos propios de otros módulos.
_fp_fragmento = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None) or (lambda f: f)

def _fp_rerun_parcial():
    """Rerun solo del fragmento; si la versión de Streamlit no lo soporta, rerun completo (comportamiento previo).
    La señal interna de rerun de Streamlit es BaseException, así que el except no la intercepta."""
    try:
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()


def _fp_render_registro(uid, hoy):
    _fp_titulo("Registro rápido", "spark")
    ui_boton_importacion(db_conn, uid)   # fuera del fragmento: abre su propio diálogo
    _fp_render_captura(uid, hoy)         # Sprint 1 · fragmento: formulario + últimos movimientos


@_fp_fragmento
def _fp_render_captura(uid, hoy):
    ultimo = st.session_state.get("fp_ultimo_registro")
    if ultimo and ultimo.get("uid") == uid:
        c1, c2 = st.columns([3, 1])
        libre_txt = ""
        try:   # la tarjeta de arriba se refresca en la siguiente carga completa; aquí va el dato al instante
            dl_post = fp_dinero_libre(uid, hoy)
            if dl_post and dl_post.get("estado") != "SIN_BASE":
                libre_txt = f" · Dinero libre ahora: {fp_dinero(dl_post['dinero_libre'])}"
        except Exception:
            pass
        c1.markdown(f"<p class='fp-nota' style='margin-top:8px;'>Registrado: {html_seguro(ultimo['texto'])}{libre_txt}</p>", unsafe_allow_html=True)
        if c2.button("Deshacer", key="fp_deshacer_ultimo", use_container_width=True):
            fp_descartar(uid, ultimo["movimiento_id"])
            st.session_state.pop("fp_ultimo_registro", None)
            _fp_rerun_parcial()

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
                    _fp_rerun_parcial()   # Sprint 1

    _fp_render_ultimos(uid)   # Sprint 1 · dentro del fragmento: se actualiza junto con el registro


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
        sub = html_seguro(" · ".join(x for x in (f"{m['fecha']:%d/%m}", m["categoria"] if m["tipo"] != "AJUSTE" else "",
                                                 _FP_FUENTES.get(m["fuente"], m["fuente"])) if x))
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"<div class='fp-fila notranslate' translate='no'><div><div style='color:#e5e7eb;'>{html_seguro(titulo)}</div>"
                    f"<div class='fp-fila-sub'>{sub}</div></div><div>{monto_html}</div></div>", unsafe_allow_html=True)
        if c2.button("Quitar", key=f"fp_quitar_{m['movimiento_id']}", help="Lo descarta de tus números (no se borra del historial)."):
            fp_descartar(uid, m["movimiento_id"])
            _fp_rerun_parcial()   # Sprint 1


def _fp_render_proximos(uid, dl, hoy):
    c_tit, c_btn = st.columns([10, 1])
    with c_tit: _fp_titulo("Lo que viene", "trend")
    with c_btn: ui_boton_compromisos(db_conn, uid)
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
        filas += (f"<div class='fp-fila'><div><div style='color:#e5e7eb;'>{html_seguro(e['nombre'])}</div>"
                  f"<div class='fp-fila-sub'>{_FP_DIAS[e['fecha'].weekday()][:3]} {e['fecha']:%d/%m}</div></div>"
                  f"<div style='color:{color};'>{signo}{fp_dinero(e['monto'])}</div></div>")
    st.markdown(f"<div class='pos-box notranslate' translate='no'>{filas}</div>", unsafe_allow_html=True)


def _fp_render_bolsas(uid):
    c_tit, c_btn = st.columns([10, 1])
    with c_tit: _fp_titulo("Tus bolsas", "shield")
    with c_btn: ui_boton_bolsas(db_conn, uid)
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
                 f"<span style='color:#e5e7eb;'>{html_seguro(b['nombre'])}</span><span style='color:#d4af37;'>{fp_dinero(aporte)}</span></div>"
                 f"<div class='fp-fila-sub'>{detalle}</div>{barra}</div>")
    st.markdown(f"<div class='pos-box notranslate' translate='no'>{html}</div>", unsafe_allow_html=True)


def _fp_ir_a_terminal():
    """Callback del atajo «Ver mis inversiones»: cambia la sección antes de que se dibuje la barra lateral."""
    st.session_state["seccion_app"] = SECCION_TERMINAL


def _fp_render_nuevo(uid, nombre_cliente, viendo_otro_cliente, hoy):
    """Rediseño de «Tu dinero hoy» (fp_ui.py). Reusa las mismas lecturas y escrituras de esta sección.
    Devuelve False si algo falla antes de dibujar, para que se use la versión anterior."""
    from fp_fase5_inteligencia import evaluar_inteligencia
    ctx = {
        "uid": uid, "nombre": nombre_cliente, "viendo_otro": viendo_otro_cliente, "hoy": hoy, "db_conn": db_conn,
        "dinero_libre": fp_dinero_libre, "bolsas": fp_bolsas, "proximos": fp_proximos, "ultimos": fp_ultimos,
        "categorias": fp_categorias, "cuentas": fp_cuentas, "registrar": fp_registrar, "descartar": fp_descartar,
        "actividad": fp_actividad_registro, "anillos": calcular_anillos_salud,
        "inteligencia": lambda u, h: evaluar_inteligencia(db_conn, u, h),
        "sin_base": _fp_render_sin_base,
        "boton_compromisos": lambda u: ui_boton_compromisos(db_conn, u),
        "boton_bolsas": lambda u: ui_boton_bolsas(db_conn, u),
        "boton_importacion": lambda u: ui_boton_importacion(db_conn, u),
        "ir_terminal": _fp_ir_a_terminal,
    }
    try:
        fp_ui.render(ctx)
        return True
    except Exception as ex:
        log_app.warning("fp_ui · se usa la versión anterior: %s", ex)
        return False


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

    if fp_ui is not None and _fp_render_nuevo(uid, nombre_cliente, viendo_otro_cliente, hoy):
        return   # Rediseño 2026-10; si devuelve False, sigue la versión anterior (intacta abajo)

    ui_panel_inteligencia(db_conn, uid)
    
    try:
        dl = fp_dinero_libre(uid, hoy)
    except Exception:
        st.warning("No pude calcular tu dinero libre en este momento. Recarga la página en un minuto.")
        return

    if not dl or dl["estado"] == "SIN_BASE":
        _fp_render_sin_base(uid, dl, hoy)
    else:
        _fp_render_estado(dl)
        render_anillos_salud(uid, dl, hoy)   # Sprint 2 · anillos Registro / Presupuesto / Ahorro + Health Score

    col_izq, col_der = st.columns([1.35, 1], gap="large")
    with col_izq:
        _fp_render_registro(uid, hoy)   # Sprint 1: incluye "Últimos movimientos" dentro de su fragmento
    with col_der:
        _fp_render_proximos(uid, dl, hoy)
        _fp_render_bolsas(uid)


# ==========================================
# 3.3 SPRINT 2 · ESTEROIDES VISUALES Y GAMIFICACIÓN SANA  |  SPRINT 3 · PREMIUM WEALTH
# Capa aditiva (Norma 2): funciones nuevas que la UI invoca. Si cualquiera falla, la UI
# regresa exactamente al comportamiento previo (gráficas y tarjetas originales intactas).
# ==========================================
MODO_LECTURA_OPCIONES = ["Junior", "Senior"]   # Junior = experiencia actual (default)

ESTILOS_SENIOR = """
<style>
/* Modo Senior: letra grande, números claros, sin ruido de mercado */
.metric-value { font-size: clamp(2.2rem, 3.2vw, 3.1rem) !important; overflow-wrap: anywhere; }
.metric-title { font-size: 0.95rem !important; letter-spacing: 1px !important; }
.metric-subtext { font-size: 1.1rem !important; line-height: 1.5 !important; }
.fp-hero-valor { font-size: 4.2rem !important; }
.fp-fila, .fp-nota, .fp-leyenda, .pos-label, .pos-val, .pos-row { font-size: 1.1rem !important; }
.fp-fila-sub { font-size: 0.95rem !important; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-size: 1.08rem; }
.marquee-wrapper { display: none !important; }
.senior-card-valor { font-family: 'Playfair Display', serif; font-size: 2.6rem; color: #ffffff; line-height: 1.1; margin: 10px 0; }
</style>
"""


class _ContenedorSilencioso:
    """Adaptador: absorbe .markdown() de columnas que en Modo Senior no deben pintarse."""
    def markdown(self, *args, **kwargs):
        return None


_CONTENEDOR_SILENCIOSO = _ContenedorSilencioso()


def tasa_libre_riesgo(default=0.05):
    """RISK_FREE_RATE_MXN como fracción. Acepta 0.105 o 10.5 (se interpreta como %)."""
    try:
        v = float(st.secrets["RISK_FREE_RATE_MXN"])
    except Exception:
        return default
    if not np.isfinite(v) or v <= 0:
        return default
    return v / 100.0 if v > 1 else v


def xirr_portafolio(cash_df, total_portafolio):
    """Misma lógica que calc_xirr() de la Terminal, pero devuelve float (o None) para comparar contra CETES."""
    try:
        if cash_df is None or cash_df.empty:
            return None
        cfs = []
        for _, r in cash_df.iterrows():
            monto = abs(float(r["monto_mxn"]))
            if r["tipo"] == "DEPOSITO": cfs.append((pd.to_datetime(r["fecha"]), -monto))
            elif r["tipo"] == "RETIRO": cfs.append((pd.to_datetime(r["fecha"]), monto))
        if not cfs:
            return None
        cfs.append((pd.to_datetime(datetime.today().date()), float(total_portafolio)))
        return resolver_xirr(cfs)
    except Exception:
        return None


# --- 1. BOLA DE NIEVE 2.0 ---------------------------------------------------
@st.cache_data(ttl=3600, max_entries=20, show_spinner=False)
def _cierres_historicos_mxn(simbolos, inicio_iso):
    """Cierres diarios en MXN (cada día con su propio tipo de cambio). simbolos: tuple de símbolos de Yahoo."""
    fx_syms = ["USDMXN=X", "GBPMXN=X", "EURMXN=X"]
    data = yf.download(list(dict.fromkeys(list(simbolos) + fx_syms)), start=inicio_iso, progress=False)
    if data is None or data.empty:
        raise ValueError("Yahoo Finance no devolvió históricos.")
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=simbolos[0])
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    close.index = pd.to_datetime(close.index).normalize()
    close = close.sort_index().ffill()
    if "USDMXN=X" not in close.columns or close["USDMXN=X"].dropna().empty:
        raise ValueError("Sin tipo de cambio histórico.")
    usd = close["USDMXN=X"].bfill()
    gbp = close["GBPMXN=X"].bfill() if "GBPMXN=X" in close.columns else None
    eur = close["EURMXN=X"].bfill() if "EURMXN=X" in close.columns else None
    fx = {"MXN": 1.0, "USD": usd}
    if gbp is not None and not gbp.dropna().empty:
        fx.update({"GBP": gbp, "GBp": gbp / 100.0, "GBX": gbp / 100.0})   # LSE a veces cotiza en peniques
    if eur is not None and not eur.dropna().empty:
        fx["EUR"] = eur
    salida = {}
    for s in simbolos:
        if s in close.columns and not close[s].dropna().empty:
            salida[s] = close[s] * fx.get(moneda_cotizacion(s), usd)   # moneda desconocida -> USD (criterio Sprint 0)
    return pd.DataFrame(salida)


def series_bola_nieve(cash_df, tx_df, total_portafolio, rf, cierres_fn=None):
    """DataFrame diario con: capital (aportado neto), cetes (benchmark libre de riesgo) y valor (mercado + efectivo).
    'valor' queda en NaN si no hay históricos de precios; el llamador decide cómo degradar."""
    flujos = cash_df[cash_df["tipo"].isin(["DEPOSITO", "RETIRO"])].copy()
    if flujos.empty:
        return None
    hoy = pd.Timestamp(datetime.today().date())
    flujos["fecha"] = pd.to_datetime(flujos["fecha"]).dt.normalize()
    flujos = flujos[flujos["fecha"] <= hoy]
    if flujos.empty:
        return None
    flujos["flujo"] = np.where(flujos["tipo"] == "DEPOSITO", 1.0, -1.0) * flujos["monto_mxn"].astype(float).abs()
    idx = pd.date_range(flujos["fecha"].min(), hoy, freq="D")

    # 1) Capital invertido (lo que salió de tu bolsillo)
    flujo_diario = flujos.groupby("fecha")["flujo"].sum().reindex(idx, fill_value=0.0)
    capital = flujo_diario.cumsum()

    # 2) Benchmark: cada aportación/retiro capitalizado a la tasa libre de riesgo desde su fecha
    dias_idx = np.asarray((idx - idx[0]).days, dtype=float)
    cetes = np.zeros(len(idx))
    for fecha, monto in flujo_diario[flujo_diario != 0].items():
        d = float((fecha - idx[0]).days)
        t = np.clip(dias_idx - d, 0.0, None) / 365.0
        cetes += np.where(dias_idx >= d, monto * np.power(1.0 + rf, t), 0.0)

    # 3) Valor del portafolio: posiciones x precio histórico en MXN + efectivo (misma lógica que calc_liquidez_real)
    valor = pd.Series(np.nan, index=idx)
    try:
        caja = cash_df.copy()
        caja["fecha"] = pd.to_datetime(caja["fecha"]).dt.normalize()
        entradas, salidas = {"DEPOSITO", "VENTA", "DIVIDENDO"}, {"COMPRA", "RETIRO", "COMISION", "IMPUESTO"}
        monto_abs = caja["monto_mxn"].astype(float).abs()
        caja["delta"] = np.where(caja["tipo"].isin(entradas), monto_abs, np.where(caja["tipo"].isin(salidas), -monto_abs, 0.0))
        acumulado = caja.groupby("fecha")["delta"].sum().sort_index().cumsum()
        efectivo = acumulado.reindex(acumulado.index.union(idx)).ffill().reindex(idx).fillna(0.0).clip(lower=0.0)

        valor_posiciones = pd.Series(0.0, index=idx)
        if tx_df is not None and not tx_df.empty:
            tx = tx_df.copy()
            tx["fecha"] = pd.to_datetime(tx["fecha"]).dt.normalize()
            tx["titulos"] = tx["titulos"].astype(float)
            pos = tx.pivot_table(index="fecha", columns="ticker", values="titulos", aggfunc="sum").sort_index().cumsum()
            pos = pos.reindex(pos.index.union(idx)).ffill().reindex(idx).fillna(0.0).clip(lower=0.0)
            tickers = [t for t in pos.columns if pos[t].abs().sum() > 0]
            if tickers:
                simbolos = tuple(_yf_symbol(t) for t in tickers)
                inicio = (min(idx[0], tx["fecha"].min()) - timedelta(days=10)).strftime("%Y-%m-%d")
                precios = (cierres_fn or _cierres_historicos_mxn)(simbolos, inicio)
                precios = precios.reindex(precios.index.union(idx)).ffill().bfill().reindex(idx)
                compras = tx[tx["tipo_operacion"] == "COMPRA"]
                for t, s in zip(tickers, simbolos):
                    if s in precios.columns and not precios[s].dropna().empty:
                        valor_posiciones += pos[t] * precios[s].fillna(0.0)
                    else:   # sin histórico: se valúa a costo promedio (no inventa plusvalía)
                        c = compras[compras["ticker"] == t]
                        tit = float(c["titulos"].sum())
                        costo = float(c["total_mxn"].astype(float).sum()) / tit if tit > 0 else 0.0
                        valor_posiciones += pos[t] * costo
        valor = valor_posiciones + efectivo
        valor.iloc[-1] = float(total_portafolio)   # el último punto cuadra al centavo con la tarjeta "Patrimonio Total"
    except Exception as e:
        log_app.warning("Bola de Nieve 2.0 · sin histórico de valor: %s", e)
        valor = pd.Series(np.nan, index=idx)

    return pd.DataFrame({"capital": capital.values, "cetes": cetes, "valor": valor.values}, index=idx)


def construir_bola_nieve_v2(cash_df, tx_df, total_portafolio, rf, senior=False):
    """Devuelve (figura, resumen_html) o None. None = la Terminal pinta la gráfica original."""
    try:
        df = series_bola_nieve(cash_df, tx_df, total_portafolio, rf)
        if df is None or df.empty:
            return None
        capital_hoy, cetes_hoy = float(df["capital"].iloc[-1]), float(df["cetes"].iloc[-1])
        valor_hoy = float(total_portafolio)
        hay_historia = df["valor"].notna().sum() > 1

        # Rediseño · opción C "Lo que generó cada peso": a todo se le resta lo aportado. El capital queda como la línea
        # cero y se compara solo la ganancia: tu portafolio contra lo que habría generado CETES. Así no se enciman.
        ORO_LINEA, VERDE_AREA, MARFIL, PIZARRA, LUZ = "#e2c575", "rgba(95, 191, 154, 0.16)", "#d9d4c7", "#7fa3c9", "#fff4d6"
        gan_cetes = df["cetes"] - df["capital"]
        gan_valor = df["valor"] - df["capital"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=[0.0] * len(df), mode="lines", name=f"Aportado (${capital_hoy:,.0f})",
            line=dict(color=MARFIL, width=1.3), customdata=df["capital"],
            hovertemplate="<b>Aportado:</b> $%{customdata:,.2f} MXN<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=df.index, y=gan_cetes, mode="lines", name=f"CETES {rf * 100:.2f}%",
            line=dict(color=PIZARRA, width=1.8), customdata=df["cetes"],
            hovertemplate="<b>CETES:</b> %{y:+,.2f} sobre lo aportado (valdría $%{customdata:,.2f})<extra></extra>"))
        if hay_historia:
            fig.add_trace(go.Scatter(
                x=df.index, y=gan_valor, mode="lines", name="Tu portafolio", fill="tozeroy",
                line=dict(color=ORO_LINEA, width=2.4), fillcolor=VERDE_AREA, customdata=df["valor"],
                hovertemplate="<b>Tu portafolio:</b> %{y:+,.2f} sobre lo aportado (vale $%{customdata:,.2f})<extra></extra>"))
        else:   # sin precios históricos: solo el punto de hoy
            fig.add_trace(go.Scatter(
                x=[df.index[-1]], y=[valor_hoy - capital_hoy], mode="markers", name="Tu portafolio hoy",
                marker=dict(color=ORO_LINEA, size=9), hovertemplate="<b>Tu portafolio hoy:</b> %{y:+,.2f}<extra></extra>"))
        # Última traza: copia de la línea que solo existe para la luz animada por CSS (.st-key-bola_nieve).
        fig.add_trace(go.Scatter(x=df.index, y=gan_valor if hay_historia else gan_cetes, mode="lines",
                                 line=dict(color=LUZ, width=2.2), hoverinfo="skip", showlegend=False, name="luz"))

        g_tu, g_ce = valor_hoy - capital_hoy, cetes_hoy - capital_hoy
        sig = lambda v: f"{'+' if v >= 0 else '-'}${abs(v):,.0f}"
        # Móvil primero: sin rótulos a la derecha (aplastaban la gráfica en pantallas angostas). Las cifras finales van
        # en la leyenda, abajo y en horizontal, y solo se marca el punto de hoy de cada línea.
        for tr in fig.data:
            if tr.name == "Tu portafolio" or tr.name == "Tu portafolio hoy": tr.name = f"Tú {sig(g_tu)}"
            elif str(tr.name).startswith("CETES"): tr.name = f"CETES {sig(g_ce)}"
            elif str(tr.name).startswith("Aportado"): tr.name = f"Aportado ${capital_hoy:,.0f}"
        fig.add_trace(go.Scatter(x=[df.index[-1], df.index[-1]], y=[g_tu, g_ce], mode="markers", hoverinfo="skip", showlegend=False,
                                 marker=dict(size=7, color=[ORO_LINEA, PIZARRA], line=dict(color="#050608", width=1.5)), name="hoy"))
        fig.data = fig.data[:-2] + (fig.data[-1], fig.data[-2])   # la luz sigue siendo la última traza (CSS)

        style_financial_figure(fig, height=400 if senior else 360, senior=senior, showlegend=True,
                               margin=dict(t=10, b=10, l=6, r=12))
        fig.update_layout(hovermode="x unified",
                          legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="left", x=0, font=dict(size=12)))
        fig.update_xaxes(range=[df.index[0], df.index[-1]], nticks=5, tickformat="%d %b", tickangle=0, automargin=True)
        fig.update_yaxes(tickformat="+$,.0f", zeroline=False, nticks=6, automargin=True)   # +$150 / -$150

        dif = valor_hoy - cetes_hoy
        veredicto = (f"<b style='color:#5fbf9a;'>le ganas a CETES por ${dif:,.0f}</b>" if dif >= 0
                     else f"<b style='color:#94a3b8;'>CETES iría ${-dif:,.0f} arriba</b>")
        tam = "1.1rem" if senior else "0.88rem"
        resumen = (f"<p class='notranslate' translate='no' style='color:#8b949e; font-size:{tam}; margin:-4px 0 6px 0;'>"
                   f"Aportaste <b style='color:#e2c575;'>${capital_hoy:,.0f}</b> · hoy vale "
                   f"<b style='color:#ffffff;'>${valor_hoy:,.0f}</b> · en CETES tendrías "
                   f"<b style='color:#8f9bb3;'>${cetes_hoy:,.0f}</b> → {veredicto}.</p>")
        return fig, resumen
    except Exception as e:
        log_app.warning("Bola de Nieve 2.0 · se usa la gráfica original: %s", e)
        return None


# --- 2. TABLA DE POSICIONES PREMIUM ------------------------------------------
def _spark_limpio(valores):
    try:
        limpio = [float(x) for x in (valores or []) if x is not None and np.isfinite(float(x))]
        return limpio if len(limpio) >= 2 else []
    except Exception:
        return []


def mxn_signo(v):
    """+$1,234.56 / -$1,234.56 (en lugar de $+1,234.56)."""
    v = float(v or 0)
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


ORDEN_CLASES = ["ETF", "Acción", "Cripto"]
NOMBRE_GRUPO = {"Acción": "Acciones"}


def render_tabla_posiciones(summary, senior=False):
    """Rediseño · "Agrupada por clase": ETF, Acciones y Cripto con subtotal por grupo. Si algo falla, se usa la tabla anterior."""
    st.markdown(f"<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; "
                f"margin-bottom:15px; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' translate='no'>"
                f"{svg_icon('eye', color='#d4af37', size=18)}Tus Posiciones</h4>", unsafe_allow_html=True)
    if summary is None or summary.empty:
        st.caption("Aún no tienes posiciones abiertas.")
        return
    try:
        df = summary.copy()
        for c in ("valor_actual", "pnl", "retorno_pct", "ponderacion_pct"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        clases = [c for c in ORDEN_CLASES if c in df["Clase"].values] + sorted(set(df["Clase"]) - set(ORDEN_CLASES))
        cls = lambda v: "ap-pos" if v >= 0 else "ap-neg"
        filas = ""
        for c in clases:
            g = df[df["Clase"] == c].sort_values("valor_actual", ascending=False)
            filas += (f"<tr class='grupo'><td>{html_seguro(NOMBRE_GRUPO.get(c, c))}</td><td class='n'>${g['valor_actual'].sum():,.2f}</td>"
                      f"<td class='n {cls(g['pnl'].sum())}'>{mxn_signo(g['pnl'].sum())}</td><td></td><td class='n'>{g['ponderacion_pct'].sum():.1f}%</td></tr>")
            for _, r in g.iterrows():
                filas += (f"<tr><td class='tk'>{html_seguro(r['ticker'])}</td><td class='n'>${r['valor_actual']:,.2f}</td>"
                          f"<td class='n {cls(r['pnl'])}'>{mxn_signo(r['pnl'])}</td><td class='n {cls(r['retorno_pct'])}'>{r['retorno_pct']:+.2f}%</td>"
                          f"<td class='n'>{r['ponderacion_pct']:.1f}%</td></tr>")
        st.markdown("<div class='ap-tw notranslate' translate='no'><table><tr><th>Activo</th><th class='n'>Valor MXN</th>"
                    "<th class='n'>Ganancia</th><th class='n'>Rendimiento</th><th class='n'>Peso</th></tr>"
                    f"{filas}</table></div>", unsafe_allow_html=True)
    except Exception as e:
        log_app.warning("Tabla agrupada · se usa la tabla anterior: %s", e)
        _render_tabla_posiciones_dataframe(summary, senior, con_titulo=False)


def _render_tabla_posiciones_dataframe(summary, senior=False, con_titulo=True):
    """Tabla anterior (st.dataframe con tendencia de 30 días). Se conserva como respaldo."""
    if con_titulo: st.markdown(f"<h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; "
                f"margin-bottom:15px; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' translate='no'>"
                f"{svg_icon('eye', color='#d4af37', size=18)}Tus Posiciones</h4>", unsafe_allow_html=True)
    if summary is None or summary.empty:
        st.caption("Aún no tienes posiciones abiertas.")
        return
    try:
        tabla = pd.DataFrame({
            "Activo": summary["ticker"].astype(str),
            "Clase": summary["Clase"].astype(str),
            "Títulos": summary["titulos"].astype(float),
            "Precio": summary["precio_mercado"].astype(float),
            "Valor": summary["valor_actual"].astype(float),
            "Ganancia": summary["pnl"].astype(float),
            "Rendimiento": summary["retorno_pct"].astype(float),
            "Peso": summary["ponderacion_pct"].astype(float),
            "Tendencia (30D)": summary["Tendencia (30D)"].apply(_spark_limpio),
        }).sort_values("Valor", ascending=False)
        if senior:   # números grandes y claros: sin títulos, precio unitario ni clase
            tabla = tabla[["Activo", "Valor", "Ganancia", "Peso", "Tendencia (30D)"]]

        cc = getattr(st, "column_config", None)
        if cc is None or not hasattr(cc, "LineChartColumn") or not hasattr(cc, "ProgressColumn"):
            st.dataframe(tabla.drop(columns=["Tendencia (30D)"]), hide_index=True, use_container_width=True)   # Streamlit < 1.23
            return
        config = {
            "Activo": cc.TextColumn("Activo"),
            "Clase": cc.TextColumn("Clase"),
            "Títulos": cc.NumberColumn("Títulos", format="%.4f"),
            "Precio": cc.NumberColumn("Precio MXN", format="$%.2f"),
            "Valor": cc.NumberColumn("Valor MXN", format="$%.2f"),
            "Ganancia": cc.NumberColumn("Ganancia MXN", format="$%.2f"),
            "Rendimiento": cc.NumberColumn("Rendimiento", format="%+.2f%%"),
            # Peso sobre 100 % (honesto). Alternativa: max_value=float(tabla["Peso"].max()) para barras más largas.
            "Peso": cc.ProgressColumn("Peso en portafolio", format="%.1f%%", min_value=0.0, max_value=100.0),
            "Tendencia (30D)": cc.LineChartColumn("Tendencia 30D (MXN)"),
        }
        # Alternativa Streamlit >= 1.40: format="dollar" o "localized" para separador de miles.
        st.dataframe(tabla, column_config={k: v for k, v in config.items() if k in tabla.columns},
                     hide_index=True, use_container_width=True)
    except Exception as e:
        log_app.warning("Tabla de posiciones premium · %s", e)
        st.caption("No pude armar la tabla de posiciones en este momento.")


# --- 3. ¿LE GANASTE A CETES? + ADAPTADORES SENIOR DE RIESGO ------------------
def html_le_ganaste_a_cetes(xirr, rf, senior=False):
    titulo = "¿Le ganaste a CETES?"
    tt = ("Compara tu rendimiento real anualizado (XIRR, con las fechas exactas de tus depósitos y retiros) "
          f"contra la tasa libre de riesgo configurada ({rf * 100:.2f}% anual).")
    if xirr is None:
        cuerpo = ("<p style='color:#8b949e;font-size:0.95rem;margin:0;'>Aún no hay historia suficiente "
                  "(mínimo 30 días con depósitos) para compararte.</p>")
    else:
        dif_pp = (xirr - rf) * 100
        gano = dif_pp >= 0
        color = "#34d399" if gano else "#94a3b8"
        veredicto = "Sí" if gano else "Todavía no"
        detalle = (f"Tu dinero rindió {xirr * 100:+.2f}% al año contra {rf * 100:.2f}% de CETES "
                   f"({dif_pp:+.2f} puntos).")
        cuerpo = (f"<p style='color:{color};font-size:{'2rem' if senior else '1.35rem'};font-weight:600;"
                  f"font-family:\"Inter\", sans-serif;margin:0;'>{veredicto}</p>"
                  f"<p style='color:#8b949e;font-size:{'1.05rem' if senior else '0.85rem'};margin:6px 0 0 0;'>{detalle}</p>")
    return (f"<div class='pos-box notranslate' translate='no'><p class='metric-title'>{titulo} "
            f"<span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt}</span></span></p>{cuerpo}</div>")


def render_riesgo_senior(var_95_mxn, max_dd, port_beta):
    """Mismos números del Módulo de Riesgo, sin Beta/Sharpe/VaR: solo lenguaje llano y cifras grandes."""
    if port_beta > 1.2: mov, mov_txt = "Más movido", "Tu portafolio sube y baja más que la bolsa de EE.UU."
    elif port_beta < 0.8: mov, mov_txt = "Más tranquilo", "Tu portafolio se mueve menos que la bolsa de EE.UU."
    else: mov, mov_txt = "Parejo", "Tu portafolio se mueve parecido a la bolsa de EE.UU."
    tarjetas = [
        ("En un día malo", f"-${var_95_mxn:,.0f}", "Así de grande puede ser una baja en 1 de cada 20 días. Es normal y temporal."),
        ("Tu peor tropiezo del año", f"{max_dd:.1f}%", "La mayor caída desde un punto alto en los últimos 12 meses."),
        ("Comparado con la bolsa", mov, mov_txt),
    ]
    for col, (t, v, s) in zip(st.columns(3), tarjetas):
        col.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>{t}</div>"
                     f"<div class='senior-card-valor'>{v}</div><div class='metric-subtext'>{s}</div></div>",
                     unsafe_allow_html=True)


def render_diversificacion_senior(corr_matrix):
    try:
        c = corr_matrix.values.astype(float)
        n = c.shape[0]
        promedio = (np.nansum(c) - np.nansum(np.diag(c))) / (n * (n - 1)) if n > 1 else 1.0
    except Exception:
        promedio = np.nan
    if not np.isfinite(promedio):
        st.caption("No pude medir tu diversificación en este momento.")
        return
    if promedio < 0.3: nivel, color, texto = "Buena", "#34d399", "Tus inversiones no se mueven todas igual: cuando una baja, otras aguantan."
    elif promedio < 0.6: nivel, color, texto = "Media", "#d4af37", "Parte de tus inversiones se mueve en bloque. Sumar algo distinto te protegería más."
    else: nivel, color, texto = "Baja", "#94a3b8", "Casi todas tus inversiones suben y bajan juntas. Conviene diversificar."
    st.markdown(f"<div class='metric-card notranslate' translate='no'><div class='metric-title'>¿Qué tan repartido está tu dinero?</div>"
                f"<div class='senior-card-valor' style='color:{color};'>{nivel}</div><div class='metric-subtext'>{texto}</div></div>",
                unsafe_allow_html=True)


# --- 4. ANILLOS DIARIOS & HEALTH SCORE (Tu dinero hoy) ------------------------
@lectura_cacheada(ttl=60)
def fp_actividad_registro(uid, hoy):
    """(días con al menos un registro en los últimos 7, ¿registró hoy?). Lee fp_financial_ledger (mismo esquema del bot)."""
    filas = _fp_consulta(
        """
        SELECT COUNT(DISTINCT fecha) AS dias, COALESCE(BOOL_OR(fecha = %s::date), FALSE) AS hoy
          FROM fp_financial_ledger
         WHERE user_id = %s AND estado <> 'DESCARTADO'
           AND fecha > %s::date - 7 AND fecha <= %s::date
        """, (hoy, uid, hoy, hoy))
    if not filas:
        return 0, False
    return int(filas[0]["dias"] or 0), bool(filas[0]["hoy"])


def calcular_anillos_salud(dl, dias_registro_7d):
    """Tres anillos (0 a 1) y un Health Score explicable (0 a 100). Sin datos -> 0, nunca inventa."""
    def _f(clave):
        try: return float(dl.get(clave) or 0)
        except Exception: return 0.0

    registro = max(0.0, min(1.0, dias_registro_7d / 7.0))

    # Presupuesto "al ritmo": fracción que te queda del dinero variable vs fracción del periodo que falta
    libre_real = _f("dinero_libre")
    libre, gastado = max(libre_real, 0.0), _f("gastado_periodo")
    bolsa_variable = gastado + libre
    frac_restante = (libre / bolsa_variable) if bolsa_variable > 0 else (1.0 if libre_real >= 0 else 0.0)
    try:
        dias_total = max((dl["proximo_ingreso"] - dl["periodo_inicio"]).days, 1)
    except Exception:
        dias_total = 30
    frac_tiempo = max(0.0, min(1.0, _f("dias_restantes") / dias_total))
    if libre_real < 0: presupuesto = 0.0
    elif frac_tiempo <= 0: presupuesto = 1.0
    else: presupuesto = min(1.0, frac_restante / frac_tiempo)

    # Ahorro: lo apartado (bolsas + ahorro programado) vs meta sugerida del 10 % de lo que entró en el periodo
    entradas = _f("base") + _f("ingresos_periodo") + _f("ingresos_extra")
    apartado = _f("reservado_bolsas") + _f("ahorro_programado")
    meta_ahorro = 0.10 * entradas
    ahorro = min(1.0, apartado / meta_ahorro) if meta_ahorro > 0 else (1.0 if apartado > 0 else 0.0)

    score = int(round(100 * (0.35 * presupuesto + 0.35 * ahorro + 0.30 * registro)))
    if score >= 80: nivel, color = "Sólido", "#34d399"
    elif score >= 60: nivel, color = "En construcción", "#d4af37"
    else: nivel, color = "Prioridad", "#94a3b8"
    return {"registro": registro, "presupuesto": presupuesto, "ahorro": ahorro, "score": score, "nivel": nivel,
            "color": color, "dias_registro": dias_registro_7d, "frac_restante": frac_restante,
            "frac_tiempo": frac_tiempo, "apartado": apartado, "meta_ahorro": meta_ahorro}


def _svg_anillos(valores, colores, tam=132):
    radios, grosor, centro = (54, 41, 28), 10, 66
    capas = ""
    for r, v, c in zip(radios, valores, colores):
        circ = 2 * np.pi * r
        capas += (f"<circle cx='{centro}' cy='{centro}' r='{r}' fill='none' stroke='rgba(255,255,255,0.06)' stroke-width='{grosor}'/>"
                  f"<circle cx='{centro}' cy='{centro}' r='{r}' fill='none' stroke='{c}' stroke-width='{grosor}' "
                  f"stroke-linecap='round' stroke-dasharray='{circ * max(v, 0.001):.2f} {circ:.2f}' "
                  f"transform='rotate(-90 {centro} {centro})'/>")
    return f"<svg width='{tam}' height='{tam}' viewBox='0 0 132 132' style='flex-shrink:0;'>{capas}</svg>"


def render_anillos_salud(uid, dl, hoy):
    try:
        dias, registro_hoy = fp_actividad_registro(uid, hoy)
        a = calcular_anillos_salud(dl, dias)
    except Exception as e:
        log_app.warning("Anillos de salud · %s", e)
        return
    colores = ("#d4af37", "#34d399", "#c084fc")
    tt = ("Health Score = 35% Presupuesto al ritmo + 35% Ahorro (meta sugerida: 10% de lo que entró) "
          "+ 30% Registro (días con movimientos en los últimos 7). Se compara contra ti mismo, no es un buró de crédito.")
    filas = [
        (colores[0], "Registro", f"{a['dias_registro']} de 7 días" + (" · hoy registrado" if registro_hoy else " · falta hoy")),
        (colores[1], "Presupuesto", "Sobregirado" if a["presupuesto"] == 0 and float(dl.get("dinero_libre") or 0) < 0
         else f"{a['presupuesto'] * 100:.0f}% al ritmo · te queda {a['frac_restante'] * 100:.0f}% con {a['frac_tiempo'] * 100:.0f}% del periodo"),
        (colores[2], "Ahorro", f"{fp_dinero(a['apartado'])} de {fp_dinero(a['meta_ahorro'])} sugeridos"),
    ]
    filas_html = "".join(
        f"<div style='display:flex; align-items:baseline; gap:8px; margin:5px 0;'>"
        f"<i style='width:9px; height:9px; border-radius:50%; background:{c}; display:inline-block;'></i>"
        f"<span style='color:#e5e7eb; min-width:92px;'>{n}</span><span class='fp-fila-sub' style='margin:0;'>{d}</span></div>"
        for c, n, d in filas)
    st.markdown(
        f"<div class='metric-card notranslate' translate='no' style='display:flex; align-items:center; gap:26px; flex-wrap:wrap;'>"
        f"{_svg_anillos((a['registro'], a['presupuesto'], a['ahorro']), colores)}"
        f"<div style='flex:1; min-width:220px;'><div class='metric-title'>Salud financiera {_fp_tooltip(tt)}</div>"
        f"<div style='display:flex; align-items:baseline; gap:12px;'>"
        f"<span style='font-family:\"Playfair Display\", serif; font-size:2.6rem; color:{a['color']};'>{a['score']}</span>"
        f"<span style='color:#8b949e;'>/ 100 · {a['nivel']}</span></div>{filas_html}</div></div>",
        unsafe_allow_html=True)


# --- 6. CMA FINANCIAL LETTER (entregable imprimible a PDF) --------------------
def _siguientes_acciones_carta(ctx):
    """P0-B · Escenarios observados: describe parámetros cuantitativos del portafolio, sin prescribir acciones."""
    escenarios = []
    patrimonio = ctx["patrimonio"] or 0
    for p in ctx["posiciones"]:
        if p["peso"] > 20:
            escenarios.append(f"Concentración: {_html.escape(p['ticker'])} representa {p['peso']:.1f}% del patrimonio, "
                              f"por encima del umbral de referencia de 20%. En este escenario, la variación de un solo "
                              f"activo tiene un peso relevante en el resultado total.")
            break
    for a in ctx.get("asignacion") or []:
        if a.get("parametro") is not None and abs(a.get("desviacion", 0)) >= 5:
            lado = "por encima" if a["desviacion"] > 0 else "por debajo"
            escenarios.append(f"Asignación: la clase {_html.escape(a['clase'])} pesa {a['peso_invertido']:.1f}% de lo invertido, "
                              f"{abs(a['desviacion']):.1f} puntos {lado} de su parámetro de {a['parametro']:.0f}%.")
            break
    if patrimonio > 0 and ctx["liquidez"] / patrimonio > 0.20:
        escenarios.append(f"Liquidez: {ctx['liquidez'] / patrimonio * 100:.0f}% del patrimonio se mantiene en efectivo. "
                          f"Este parámetro reduce la volatilidad del conjunto y, a la vez, la parte expuesta a rendimientos de mercado.")
    if ctx["xirr"] is not None and ctx["xirr"] < ctx["rf"]:
        escenarios.append(f"Rendimiento: la tasa real anualizada observada ({ctx['xirr'] * 100:+.2f}%) se ubica por debajo de "
                          f"la tasa libre de riesgo de referencia ({ctx['rf'] * 100:.2f}%). Costos, concentración y horizonte "
                          f"son los parámetros que explican habitualmente esta brecha.")
    if ctx["racha"] == 0:
        escenarios.append("Disciplina: no se registran aportaciones en el periodo actual. En la proyección a 5 años, "
                          "el supuesto de aportación periódica es el parámetro de mayor sensibilidad.")
    if not escenarios:
        escenarios.append("Sin alertas cuantitativas: la concentración, la asignación, la liquidez y la disciplina de "
                          "aportación se ubican dentro de los umbrales de referencia utilizados en este reporte.")
    return escenarios[:4]


SELLO_SVG = ('<svg width="54" height="54" viewBox="0 0 54 54" aria-hidden="true" style="flex-shrink:0;">'
             '<circle cx="27" cy="27" r="25.5" fill="none" stroke="#b8962e" stroke-width="1"/>'
             '<circle cx="27" cy="27" r="21.5" fill="none" stroke="#b8962e" stroke-width="0.6"/>'
             '<text x="27" y="31.5" text-anchor="middle" font-family="Playfair Display, Georgia, serif" '
             'font-size="12.5" letter-spacing="1.5" fill="#8a6d1f">CMA</text></svg>')


def generar_carta_cma(ctx):
    """Carta de banca privada en HTML autocontenido. Se imprime a PDF desde el navegador (Ctrl+P > Guardar como PDF).
    Alternativa (requiere agregar 'weasyprint' a requirements.txt): weasyprint.HTML(string=html).write_pdf().
    Las claves nuevas del ctx son opcionales (ctx.get): si faltan, su sección simplemente no se imprime."""
    e = lambda x: _html.escape(str(x if x is not None else ""))
    m = lambda v: f"${float(v or 0):,.2f}"
    ms = lambda v: f"{'+' if float(v or 0) >= 0 else '-'}${abs(float(v or 0)):,.2f}"
    cls = lambda v: "pos" if float(v or 0) >= 0 else "neg"
    hoy = hoy_mx()
    fecha_txt = f"Ciudad de México, {fp_fecha_larga(hoy).lower()} de {hoy.year}"
    xirr, rf = ctx["xirr"], ctx["rf"]
    if xirr is None:
        cetes_txt = "Aún no contamos con historia suficiente (mínimo 30 días) para comparar su rendimiento contra CETES."
    elif xirr >= rf:
        cetes_txt = (f"Su rendimiento real anualizado (XIRR) es de {xirr * 100:+.2f}%, por encima de la tasa libre de "
                     f"riesgo de {rf * 100:.2f}% ({(xirr - rf) * 100:+.2f} puntos). Su capital está siendo mejor remunerado que en CETES.")
    else:
        cetes_txt = (f"Su rendimiento real anualizado (XIRR) es de {xirr * 100:+.2f}%, por debajo de la tasa libre de "
                     f"riesgo de {rf * 100:.2f}% ({(xirr - rf) * 100:+.2f} puntos).")

    # --- Composición detallada ---
    def _tit(v):
        return f"{float(v or 0):.8f}".rstrip("0").rstrip(".") or "0"
    filas_pos = "".join(
        f"<tr><td><b>{e(p['ticker'])}</b></td><td>{e(p['clase'])}</td><td class='n'>{_tit(p.get('titulos'))}</td>"
        f"<td class='n'>{m(p.get('costo_promedio'))}</td><td class='n'>{m(p['valor'])}</td>"
        f"<td class='n {cls(p.get('pnl'))}'>{ms(p.get('pnl'))}</td>"
        f"<td class='n {cls(p['retorno'])}'>{p['retorno']:+.2f}%</td><td class='n'>{p['peso']:.1f}%</td></tr>"
        for p in ctx["posiciones"]) or "<tr><td colspan='8'>Sin posiciones abiertas.</td></tr>"

    # --- Asignación por clase vs parámetros ---
    bloque_asig = ""
    asig = ctx.get("asignacion") or []
    if asig:
        filas_asig = ""
        for a in asig:
            tiene_param = a.get("parametro") is not None
            txt_param = f"{a['parametro']:.0f}%" if tiene_param else "—"
            txt_desv = f"{a['desviacion']:+.1f} pp" if tiene_param else "—"
            filas_asig += (f"<tr><td>{e(a['clase'])}</td><td class='n'>{m(a['valor'])}</td><td class='n'>{a['peso_patrimonio']:.1f}%</td>"
                           f"<td class='n'>{a['peso_invertido']:.1f}%</td><td class='n'>{txt_param}</td><td class='n'>{txt_desv}</td></tr>")
        filas_asig += (f"<tr><td>Liquidez (efectivo)</td><td class='n'>{m(ctx['liquidez'])}</td>"
                       f"<td class='n'>{(ctx['liquidez'] / ctx['patrimonio'] * 100) if ctx['patrimonio'] else 0:.1f}%</td>"
                       f"<td class='n'>—</td><td class='n'>—</td><td class='n'>—</td></tr>")
        bloque_asig = ("<h2>Asignación por clase de activo</h2>"
                       "<table><tr><th>Clase</th><th class='n'>Valor MXN</th><th class='n'>% patrimonio</th>"
                       "<th class='n'>% invertido</th><th class='n'>Parámetro</th><th class='n'>Desviación</th></tr>"
                       f"{filas_asig}</table><p class='nota'>Los parámetros son los definidos en el Simulador de Rebalanceo de la "
                       "Terminal. La desviación compara el peso sobre lo invertido contra el parámetro, en puntos porcentuales.</p>")

    # --- Contribución ---
    bloque_contrib = ""
    if len(ctx["posiciones"]) >= 2:
        ordenadas = sorted(ctx["posiciones"], key=lambda p: p.get("pnl", 0))
        peor, mejor = ordenadas[0], ordenadas[-1]
        bloque_contrib = (
            "<h2>Contribución al resultado</h2><table class='kpi'>"
            f"<tr><td>Mayor contribución</td><td class='n'><b>{e(mejor['ticker'])}</b> · "
            f"<span class='{cls(mejor.get('pnl'))}'>{ms(mejor.get('pnl'))} ({mejor['retorno']:+.2f}%)</span></td></tr>"
            f"<tr><td>Menor contribución</td><td class='n'><b>{e(peor['ticker'])}</b> · "
            f"<span class='{cls(peor.get('pnl'))}'>{ms(peor.get('pnl'))} ({peor['retorno']:+.2f}%)</span></td></tr></table>")

    # --- Riesgo ---
    r = ctx.get("riesgo") or {}
    bloque_riesgo = ""
    if r:
        beta = float(r.get("beta", 0) or 0)
        estres = ctx["patrimonio"] * (-0.20 * beta)
        bloque_riesgo = (
            "<h2>Perfil de riesgo (últimos 12 meses)</h2><table class='kpi'>"
            f"<tr><td>Sensibilidad al mercado (beta vs S&amp;P 500)</td><td class='n'>{beta:.2f}</td></tr>"
            f"<tr><td>Rendimiento ajustado por riesgo (Sharpe)</td><td class='n'>{r.get('sharpe', 0):.2f}</td></tr>"
            f"<tr><td>Volatilidad anualizada</td><td class='n'>{r.get('vol_anual', 0) * 100:.1f}%</td></tr>"
            f"<tr><td>Caída máxima desde un punto alto</td><td class='n'>{r.get('max_dd', 0):.1f}%</td></tr>"
            f"<tr><td>Pérdida diaria que solo se supera 1 de cada 20 días (VaR 95%)</td><td class='n'>{m(r.get('var_95_mxn', 0))}</td></tr>"
            f"<tr><td>Escenario de estrés: S&amp;P 500 −20% (impacto estimado por beta)</td><td class='n neg'>{ms(estres)}</td></tr>"
            "</table>")

    # --- Flujo de caja acumulado ---
    bloque_flujos = ""
    f = ctx.get("flujos") or {}
    if f:
        filas_f = "".join(f"<tr><td>{e(k)}</td><td class='n'>{m(v)}</td></tr>" for k, v in f.items() if v)
        if filas_f:
            bloque_flujos = f"<h2>Flujo de caja acumulado</h2><table class='kpi'>{filas_f}</table>"

    # --- Actividad reciente ---
    bloque_actividad = ""
    act = ctx.get("actividad") or []
    if act:
        filas_act = "".join(
            f"<tr><td>{e(a['fecha'])}</td><td>{e(a['tipo'])}</td><td><b>{e(a['ticker'])}</b></td>"
            f"<td class='n'>{_tit(a['titulos'])}</td><td class='n'>{a['tc']:.4f}</td><td class='n'>{m(a['total'])}</td></tr>"
            for a in act)
        bloque_actividad = ("<h2>Operaciones recientes</h2><table><tr><th>Fecha</th><th>Tipo</th><th>Activo</th>"
                            "<th class='n'>Títulos</th><th class='n'>T.C.</th><th class='n'>Total MXN</th></tr>"
                            f"{filas_act}</table>")

    bloque_cio = (f"<h2>Boletín del CIO Virtual (informativo)</h2><div class='cio'>{e(ctx['cio'])}</div>"
                  f"<p class='legal' style='margin-top:8px;'>{e(AVISO_BOLETIN_CIO)}</p>" if ctx.get("cio") else "")
    acciones = "".join(f"<li>{a}</li>" for a in _siguientes_acciones_carta(ctx))
    color_pnl = cls(ctx["pnl"])
    capital = float(ctx["capital"] or 0)
    costo_pos = ctx.get("costo_posiciones")
    valor_pos = ctx.get("valor_posiciones")
    fila_opt = lambda etiqueta, valor: (f"<tr><td>{etiqueta}</td><td class='n'>{m(valor)}</td></tr>" if valor is not None else "")
    tc_ref = ctx.get("usd_mxn")
    # Folio: huella corta del estado reportado (cliente, fecha y cifras). Si cambia un número, cambia el folio.
    folio = folio_carta(ctx)
    tc_txt = f" (USD/MXN de referencia al corte: {float(tc_ref):.4f})" if tc_ref else ""
    html_carta = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CMA Financial Letter · {e(ctx['nombre'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;1,400&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
body {{ background:#fbf9f4; color:#1f2937; font-family:'Inter', Helvetica, Arial, sans-serif; font-size:10.5pt; line-height:1.6; margin:0; }}
.hoja {{ max-width:780px; margin:0 auto; padding:48px 56px; background:#fffdf8; border:1px solid #e8e1cf; }}
.marca {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom:1px solid #b8962e; padding-bottom:14px; }}
.marca h1 {{ font-family:'Playfair Display', Georgia, serif; font-weight:400; letter-spacing:4px; font-size:18pt; margin:0; color:#1f2937; }}
.marca span {{ color:#8a7a4a; font-size:8.5pt; letter-spacing:3px; text-transform:uppercase; }}
.fecha {{ text-align:right; color:#6b7280; margin:18px 0 26px 0; font-size:9.5pt; }}
h2 {{ font-family:'Playfair Display', Georgia, serif; font-style:italic; font-weight:400; color:#8a6d1f; font-size:13pt; margin:26px 0 8px 0; }}
table {{ width:100%; border-collapse:collapse; margin:6px 0; }}
td, th {{ padding:7px 6px; border-bottom:1px solid #eee6d3; text-align:left; }}
th {{ font-size:8pt; letter-spacing:2px; text-transform:uppercase; color:#8a7a4a; font-weight:600; }}
.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pos {{ color:#047857; }} .neg {{ color:#6b7280; }}
.kpi td:first-child {{ color:#4b5563; }}
.nota {{ color:#6b7280; font-size:9pt; }}
.sello {{ margin:34px 0 0 0; padding:22px 24px; background:#f7f3e8; border:1px solid #e3d7b5; border-top:2px solid #b8962e; page-break-inside:avoid; }}
.sello-cab {{ display:flex; align-items:center; gap:14px; }}
.sello-ojo {{ margin:0; color:#8a7a4a; font-size:8pt; letter-spacing:3px; text-transform:uppercase; }}
.sello-tit {{ margin:2px 0 0 0; font-family:'Playfair Display', Georgia, serif; font-style:italic; color:#8a6d1f; font-size:14pt; }}
.sello-lead {{ margin:14px 0 6px 0; color:#4b5563; font-size:10pt; }}
.sello-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:4px 26px; }}
.sello-grid div {{ padding:9px 0; border-bottom:1px solid #eadfc4; font-size:9pt; color:#4b5563; line-height:1.5; }}
.sello-grid b {{ display:block; color:#1f2937; font-weight:600; font-size:9.5pt; margin-bottom:2px; }}
.sello-folio {{ margin:14px 0 0 0; text-align:right; color:#8a7a4a; font-size:8pt; letter-spacing:1.5px; }}
@media (max-width:640px) {{ .sello-grid {{ grid-template-columns:1fr; }} }}
.cio {{ white-space:pre-wrap; background:#f7f3e8; padding:14px 16px; border-left:2px solid #b8962e; font-size:9.5pt; }}
ul {{ padding-left:18px; }} li {{ margin-bottom:6px; }}
.firma {{ margin-top:34px; }} .firma b {{ font-family:'Playfair Display', Georgia, serif; font-weight:400; font-size:12pt; }}
.legal {{ margin-top:30px; font-size:7.5pt; color:#9ca3af; border-top:1px solid #eee6d3; padding-top:10px; }}
@media print {{ body {{ background:#ffffff; }} .hoja {{ border:none; padding:0; max-width:none; }} tr {{ page-break-inside:avoid; }} }}
.tw {{ width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }}
@media (max-width:640px) {{
  body {{ font-size:9.6pt; }} .hoja {{ padding:24px 16px; border:none; }}
  .marca h1 {{ font-size:15pt; letter-spacing:3px; }} .marca span {{ font-size:6.8pt; letter-spacing:1.6px; text-align:right; }}
  h2 {{ font-size:12pt; margin-top:22px; }}
  td, th {{ padding:6px 5px; }} th {{ font-size:7pt; letter-spacing:1px; white-space:nowrap; }}
  .tw table:not(.kpi) {{ min-width:520px; }} .tw table:not(.kpi) td {{ white-space:nowrap; }}
  .kpi td.n {{ white-space:nowrap; }}
  .sello {{ padding:18px 16px; }} .sello-grid {{ grid-template-columns:1fr; }}
}}
</style></head><body><div class="hoja">
<div class="marca"><h1>CMA</h1><span>Private Wealth · Financial Letter</span></div>
<p class="fecha">{e(fecha_txt)}</p>
<p>Estimado(a) {e(ctx['nombre'])}:</p>
<p>Le compartimos el estado de su patrimonio al día de hoy. Su patrimonio total asciende a <b>{m(ctx['patrimonio'])}</b>,
construido con <b>{m(capital)}</b> de capital aportado. El resultado no realizado de sus inversiones es de
<b class="{color_pnl}">{ms(ctx['pnl'])} ({ctx['retorno_pct']:+.2f}%)</b>.</p>
<h2>Resumen patrimonial</h2>
<table class="kpi">
<tr><td>Patrimonio total</td><td class="n"><b>{m(ctx['patrimonio'])}</b></td></tr>
{fila_opt("Valor de mercado de las posiciones", valor_pos)}
<tr><td>Liquidez disponible</td><td class="n">{m(ctx['liquidez'])}</td></tr>
<tr><td>Capital aportado (depósitos − retiros)</td><td class="n">{m(capital)}</td></tr>
{fila_opt("Costo de las posiciones abiertas", costo_pos)}
<tr><td>Resultado no realizado</td><td class="n {color_pnl}">{ms(ctx['pnl'])} ({ctx['retorno_pct']:+.2f}%)</td></tr>
{fila_opt("Fricción acumulada (comisiones e IVA)", ctx.get('friccion'))}
<tr><td>Ingreso pasivo estimado por dividendos (anual)</td><td class="n">{m(ctx['salario_invisible'])}</td></tr>
<tr><td>Proyección a 5 años (supuesto de 10% anual)</td><td class="n">{m(ctx['proyeccion_5a'])}</td></tr>
</table>
<h2>¿Le ganamos a CETES?</h2>
<p>{e(cetes_txt)}</p>
{bloque_asig}
<h2>Composición del portafolio</h2>
<table><tr><th>Activo</th><th>Clase</th><th class="n">Títulos</th><th class="n">Costo prom.</th><th class="n">Valor MXN</th>
<th class="n">Resultado</th><th class="n">Rend.</th><th class="n">Peso</th></tr>{filas_pos}</table>
{bloque_contrib}
{bloque_riesgo}
{bloque_flujos}
{bloque_actividad}
<h2>Disciplina y metas</h2>
<p>Aportaciones consecutivas: <b>{ctx['racha']}</b> periodo(s) con frecuencia {e(str(ctx['frecuencia']).lower())}.
Meta «{e(ctx['meta_nombre'])}»: hito de {m(ctx['meta_monto'])}, avance de {ctx['progreso_meta']:.1f}%; faltan {m(ctx['faltante'])}.</p>
<h2>Escenarios observados</h2>
<ul>{acciones}</ul>
{bloque_cio}
<div class="sello">
<div class="sello-cab">{SELLO_SVG}<div><p class="sello-ojo">Estándar CMA</p>
<p class="sello-tit">Nuestro compromiso con su patrimonio</p></div></div>
<p class="sello-lead">Cada cifra de esta carta se construye con el mismo cuidado con el que usted construyó su patrimonio.
Estos son los principios que respaldan cada número que lee.</p>
<div class="sello-grid">
<div><b>Precisión al centavo</b>Su costo se calcula con el tipo de cambio que usted realmente pagó en cada operación, con comisiones e impuestos incluidos.</div>
<div><b>Valuación transparente</b>Cada posición se valúa con precios de cierre de mercado y el tipo de cambio del día{tc_txt}. Las ganancias se presentan como no realizadas hasta la venta.</div>
<div><b>Rendimiento real</b>Su tasa anual (XIRR) considera la fecha exacta de cada depósito y retiro, y se contrasta contra CETES como referencia libre de riesgo.</div>
<div><b>Riesgo medido, no supuesto</b>Doce meses de datos diarios: sensibilidad al mercado, caída máxima y pérdida diaria de referencia (VaR 95%).</div>
<div><b>Confidencialidad</b>Su información se resguarda en una base de datos privada con acceso protegido por credenciales cifradas. Solo usted y su gestor la consultan.</div>
<div><b>Información, no promesas</b>Este documento es un registro fiel de su patrimonio. Toda proyección declara sus supuestos y ninguna cifra se presenta como garantía.</div>
</div>
<p class="sello-folio">Emitido el {hoy:%d/%m/%Y} · Folio {folio}</p>
</div>
<div class="firma"><p>Quedamos a sus órdenes para revisar cualquier punto.</p><p><b>CMA · Private Wealth</b><br>
<span style="color:#6b7280;">Terminal APPortafolio</span></p></div>
<p class="legal">Documento informativo generado automáticamente con datos registrados por el cliente y cotizaciones de mercado
(Yahoo Finance). Los rendimientos son no realizados y no garantizan resultados futuros. Las proyecciones usan supuestos explícitos
y no constituyen una recomendación personalizada de inversión.<br><br>{e(AVISO_LECTURA_V5)}</p>
</div></body></html>"""
    # Vista previa en celular: cada tabla en su propio contenedor con scroll horizontal (el PDF no cambia).
    return html_carta.replace("<table", "<div class='tw'><table").replace("</table>", "</table></div>")


def posiciones_para_carta(summary, limite=15):
    """Top de posiciones por valor, con números limpios (sin NaN) para la carta."""
    salida = []
    if summary is None or summary.empty:
        return salida
    def _n(v):
        try:
            f = float(v)
            return f if np.isfinite(f) else 0.0
        except Exception:
            return 0.0
    for _, r in summary.sort_values("valor_actual", ascending=False).head(limite).iterrows():
        salida.append({"ticker": str(r["ticker"]), "clase": str(r.get("Clase", "") or ""), "valor": _n(r["valor_actual"]),
                       "peso": _n(r.get("ponderacion_pct", 0)), "retorno": _n(r.get("retorno_pct", 0)),
                       "titulos": _n(r.get("titulos", 0)), "costo_promedio": _n(r.get("costo_promedio", 0)),
                       "pnl": _n(r.get("pnl", 0))})
    return salida


def asignacion_para_carta(summary, patrimonio, parametros):
    """Valor y peso por clase (sobre patrimonio y sobre lo invertido) contra los parámetros del simulador."""
    if summary is None or summary.empty:
        return []
    invertido = float(summary["valor_actual"].sum())
    salida = []
    for clase, valor in summary.groupby("Clase")["valor_actual"].sum().sort_values(ascending=False).items():
        valor = float(valor)
        peso_inv = valor / invertido * 100 if invertido > 0 else 0.0
        param = parametros.get(clase)
        salida.append({"clase": str(clase), "valor": valor,
                       "peso_patrimonio": valor / patrimonio * 100 if patrimonio > 0 else 0.0,
                       "peso_invertido": peso_inv, "parametro": param,
                       "desviacion": (peso_inv - param) if param is not None else 0.0})
    return salida


def flujos_para_carta(cash_df):
    """Totales acumulados por tipo de movimiento de caja (valores absolutos, en MXN)."""
    if cash_df is None or cash_df.empty:
        return {}
    tot = cash_df.assign(m=cash_df["monto_mxn"].astype(float).abs()).groupby("tipo")["m"].sum()
    etiquetas = [("DEPOSITO", "Depósitos"), ("RETIRO", "Retiros"), ("COMPRA", "Compras de activos"),
                 ("VENTA", "Ventas de activos"), ("DIVIDENDO", "Dividendos cobrados")]
    return {txt: float(tot.get(k, 0.0)) for k, txt in etiquetas}


def actividad_para_carta(tx_df, limite=10):
    if tx_df is None or tx_df.empty:
        return []
    recientes = tx_df.sort_values(["fecha", "timestamp"], ascending=False).head(limite)
    return [{"fecha": str(r["fecha"]), "tipo": str(r["tipo_operacion"]), "ticker": str(r["ticker"]),
             "titulos": abs(float(r["titulos"] or 0)), "tc": float(r["tipo_cambio"] or 1),
             "total": float(r["total_mxn"] or 0)} for _, r in recientes.iterrows()]


def metricas_riesgo_carta(summary, total_portafolio, rf):
    """Mismas fórmulas del Módulo de Riesgo (Modo Pro), para que la carta incluya el perfil de riesgo aunque el Modo Pro
    esté apagado. Los cierres de 1 año vienen de una caché de 24 h compartida. Si algo falla, devuelve {}."""
    try:
        if summary is None or summary.empty or total_portafolio <= 0:
            return {}
        returns_df, returns_mxn_df, betas = get_advanced_risk_metrics(summary["ticker"].tolist())
        if returns_mxn_df.empty:
            return {}
        pesos = (summary.set_index("ticker")["ponderacion_pct"] / 100).to_dict()
        beta = float(sum(pesos.get(t, 0) * betas.get(t, 1.0) for t in summary["ticker"]))
        port = pd.Series(0.0, index=returns_mxn_df.index)
        for t in returns_mxn_df.columns:
            if t in pesos: port += returns_mxn_df[t] * pesos[t]
        vol = float(port.std() * np.sqrt(252))
        sharpe = (float(port.mean() * 252) - rf) / vol if vol > 0 else 0.0
        var_95 = total_portafolio * abs(float(np.percentile(port, 5)))
        acumulado = (1 + port).cumprod()
        max_dd = float(((acumulado - acumulado.cummax()) / acumulado.cummax()).min() * 100)
        return {"beta": beta, "sharpe": sharpe, "max_dd": max_dd, "var_95_mxn": var_95, "vol_anual": vol}
    except Exception as ex:
        log_app.warning("Carta CMA · riesgo no disponible: %s", ex)
        return {}


def folio_carta(ctx):
    """Folio verificable de la carta: huella corta del estado reportado. Si cambia un número, cambia el folio."""
    hoy = hoy_mx()
    capital = float(ctx["capital"] or 0)
    huella = f"{ctx['nombre']}|{hoy}|{ctx['patrimonio']:.2f}|{capital:.2f}|{ctx['pnl']:.2f}|{len(ctx['posiciones'])}"
    return f"CMA-{hoy:%Y%m%d}-{hashlib.sha256(huella.encode()).hexdigest()[:6].upper()}"


def generar_carta_pdf(ctx, version="completa"):
    """CMA Financial Letter en PDF real (texto seleccionable), con ReportLab. Misma estructura y paleta que la versión HTML.
    version="esencial" (modo sencillo, 2026-10): resumen al grano; omite tablas técnicas (riesgo detallado, flujos, operaciones).
    Fuentes base de PDF (Times / Helvetica): no requiere archivos de fuente en el servidor. Requiere `reportlab`."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Flowable)

    C_TX, C_MUTED, C_SOFT = colors.HexColor("#1f2937"), colors.HexColor("#6b7280"), colors.HexColor("#4b5563")
    C_ORO, C_ORO_OSC, C_ORO_TXT = colors.HexColor("#b8962e"), colors.HexColor("#8a6d1f"), colors.HexColor("#8a7a4a")
    C_LINEA, C_PAPEL, C_SELLO, C_SELLO_BORDE = colors.HexColor("#eee6d3"), colors.HexColor("#fffdf8"), colors.HexColor("#f7f3e8"), colors.HexColor("#e3d7b5")
    C_POS, C_NEG = colors.HexColor("#047857"), colors.HexColor("#6b7280")
    e = lambda x: _html.escape(str(x if x is not None else ""))
    m = lambda v: f"${float(v or 0):,.2f}"
    ms = lambda v: f"{'+' if float(v or 0) >= 0 else '-'}${abs(float(v or 0)):,.2f}"
    col = lambda v: "#047857" if float(v or 0) >= 0 else "#6b7280"
    tit = lambda v: (f"{float(v or 0):.8f}".rstrip("0").rstrip(".") or "0")

    st_body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.4, leading=14, textColor=C_TX)
    st_soft = ParagraphStyle("soft", parent=st_body, textColor=C_SOFT)
    st_nota = ParagraphStyle("nota", parent=st_body, fontSize=8, leading=11.5, textColor=C_MUTED)
    st_h2 = ParagraphStyle("h2", fontName="Times-Italic", fontSize=13.5, leading=17, textColor=C_ORO_OSC, spaceBefore=16, spaceAfter=6)
    st_th = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=6.6, leading=9, textColor=C_ORO_TXT)
    st_th_r = ParagraphStyle("thr", parent=st_th, alignment=TA_RIGHT)
    st_td = ParagraphStyle("td", parent=st_body, fontSize=8.8, leading=12)
    st_td_r = ParagraphStyle("tdr", parent=st_td, alignment=TA_RIGHT)
    st_fecha = ParagraphStyle("fecha", parent=st_body, fontSize=8.8, textColor=C_MUTED, alignment=TA_RIGHT)
    st_legal = ParagraphStyle("legal", parent=st_body, fontSize=6.6, leading=9.2, textColor=colors.HexColor("#9ca3af"))

    def tabla(filas, anchos, encabezado=True, alinear_der=()):
        datos = []
        for k, fila in enumerate(filas):
            celdas = []
            for j, c in enumerate(fila):
                if isinstance(c, Flowable):
                    celdas.append(c); continue
                if encabezado and k == 0:
                    celdas.append(Paragraph(str(c).upper(), st_th_r if j in alinear_der else st_th))
                else:
                    celdas.append(Paragraph(str(c), st_td_r if j in alinear_der else st_td))
            datos.append(celdas)
        t = Table(datos, colWidths=anchos, repeatRows=1 if encabezado else 0)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, C_LINEA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        return t

    class Sello(Flowable):
        def __init__(self, d=15 * mm):
            super().__init__(); self.width = self.height = d
        def draw(self):
            c, r = self.canv, self.width / 2
            c.setStrokeColor(C_ORO); c.setLineWidth(0.8); c.circle(r, r, r - 0.5, stroke=1, fill=0)
            c.setLineWidth(0.45); c.circle(r, r, r - 2.6, stroke=1, fill=0)
            c.setFillColor(C_ORO_OSC); c.setFont("Times-Roman", 10.5); c.drawCentredString(r, r - 3.6, "CMA")

    hoy = hoy_mx()
    folio = folio_carta(ctx)
    ancho_util = A4[0] - 32 * mm
    xirr, rf = ctx["xirr"], ctx["rf"]
    capital = float(ctx["capital"] or 0)
    tc_ref = ctx.get("usd_mxn")
    tc_txt = f" (USD/MXN de referencia al corte: {float(tc_ref):.4f})" if tc_ref else ""
    esencial = version == "esencial"
    h = []

    # Encabezado
    cab = Table([[Paragraph("C M A", ParagraphStyle("marca", fontName="Times-Roman", fontSize=19, leading=22, textColor=C_TX)),
                  Paragraph("PRIVATE WEALTH &middot; FINANCIAL LETTER", ParagraphStyle("mr", fontName="Helvetica", fontSize=7.2, textColor=C_ORO_TXT, alignment=TA_RIGHT))]],
                colWidths=[ancho_util * 0.4, ancho_util * 0.6])
    cab.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.9, C_ORO), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    h += [cab, Spacer(1, 10), Paragraph(e(f"Ciudad de México, {fp_fecha_larga(hoy).lower()} de {hoy.year}"), st_fecha), Spacer(1, 12)]
    h.append(Paragraph(f"Estimado(a) {e(ctx['nombre'])}:", st_body)); h.append(Spacer(1, 6))
    h.append(Paragraph(f"Le compartimos el estado de su patrimonio al día de hoy. Su patrimonio total asciende a <b>{m(ctx['patrimonio'])}</b>, "
                       f"construido con <b>{m(capital)}</b> de capital aportado. El resultado no realizado de sus inversiones es de "
                       f"<font color='{col(ctx['pnl'])}'><b>{ms(ctx['pnl'])} ({ctx['retorno_pct']:+.2f}%)</b></font>.", st_body))

    # Resumen patrimonial
    filas = [["Patrimonio total", f"<b>{m(ctx['patrimonio'])}</b>"]]
    if esencial:
        filas += [["Capital aportado (depósitos - retiros)", m(capital)], ["Efectivo disponible", m(ctx["liquidez"])],
                  ["Ganancia en sus inversiones", f"<font color='{col(ctx['pnl'])}'>{ms(ctx['pnl'])} ({ctx['retorno_pct']:+.2f}%)</font>"],
                  ["Ingreso estimado por dividendos (anual)", m(ctx["salario_invisible"])]]
    if not esencial and ctx.get("valor_posiciones") is not None: filas.append(["Valor de mercado de las posiciones", m(ctx["valor_posiciones"])])
    if not esencial:
        filas += [["Liquidez disponible", m(ctx["liquidez"])], ["Capital aportado (depósitos - retiros)", m(capital)]]
        if ctx.get("costo_posiciones") is not None: filas.append(["Costo de las posiciones abiertas", m(ctx["costo_posiciones"])])
        filas.append(["Resultado no realizado", f"<font color='{col(ctx['pnl'])}'>{ms(ctx['pnl'])} ({ctx['retorno_pct']:+.2f}%)</font>"])
        if ctx.get("friccion") is not None: filas.append(["Fricción acumulada (comisiones e IVA)", m(ctx["friccion"])])
        filas += [["Ingreso pasivo estimado por dividendos (anual)", m(ctx["salario_invisible"])], ["Proyección a 5 años (supuesto de 10% anual)", m(ctx["proyeccion_5a"])]]
    h += [Paragraph("Resumen patrimonial", st_h2), tabla(filas, [ancho_util * 0.68, ancho_util * 0.32], encabezado=False, alinear_der=(1,))]

    # CETES
    if xirr is None: cetes_txt = "Aún no contamos con historia suficiente (mínimo 30 días) para comparar su rendimiento contra CETES."
    elif xirr >= rf: cetes_txt = (f"Su rendimiento real anualizado (XIRR) es de {xirr * 100:+.2f}%, por encima de la tasa libre de riesgo de "
                                  f"{rf * 100:.2f}% ({(xirr - rf) * 100:+.2f} puntos). Su capital está siendo mejor remunerado que en CETES.")
    else: cetes_txt = (f"Su rendimiento real anualizado (XIRR) es de {xirr * 100:+.2f}%, por debajo de la tasa libre de riesgo de "
                       f"{rf * 100:.2f}% ({(xirr - rf) * 100:+.2f} puntos).")
    h += [Paragraph("¿Le ganamos a CETES?", st_h2), Paragraph(e(cetes_txt), st_body)]

    # Asignación
    asig = ctx.get("asignacion") or []
    if asig and esencial:
        pat = float(ctx["patrimonio"] or 0)
        filas = [["Dónde está", "Valor MXN", "% del patrimonio"]] + [[e(a["clase"]), m(a["valor"]), f"{a['peso_patrimonio']:.1f}%"] for a in asig]
        filas.append(["Efectivo", m(ctx["liquidez"]), f"{(ctx['liquidez'] / pat * 100) if pat else 0:.1f}%"])
        h += [Paragraph("¿Dónde está su dinero?", st_h2), tabla(filas, [ancho_util * 0.5, ancho_util * 0.25, ancho_util * 0.25], alinear_der=(1, 2))]
    elif asig:
        filas = [["Clase", "Valor MXN", "% patrimonio", "% invertido", "Parámetro", "Desviación"]]
        for a in asig:
            tp = a.get("parametro") is not None
            filas.append([e(a["clase"]), m(a["valor"]), f"{a['peso_patrimonio']:.1f}%", f"{a['peso_invertido']:.1f}%",
                          f"{a['parametro']:.0f}%" if tp else "-", f"{a['desviacion']:+.1f} pp" if tp else "-"])
        pat = float(ctx["patrimonio"] or 0)
        filas.append(["Liquidez (efectivo)", m(ctx["liquidez"]), f"{(ctx['liquidez'] / pat * 100) if pat else 0:.1f}%", "-", "-", "-"])
        w = ancho_util / 6
        h += [Paragraph("Asignación por clase de activo", st_h2), tabla(filas, [w * 1.3, w * 1.1, w * 0.9, w * 0.9, w * 0.9, w * 0.9], alinear_der=(1, 2, 3, 4, 5)),
              Spacer(1, 4), Paragraph("Los parámetros son los definidos en el Simulador de Rebalanceo de la Terminal. La desviación compara el peso "
                                      "sobre lo invertido contra el parámetro, en puntos porcentuales.", st_nota)]

    # Composición
    if esencial:
        filas = [["Activo", "Valor MXN", "Ganancia", "Rend."]] + [
            [f"<b>{e(p['ticker'])}</b>", m(p["valor"]), f"<font color='{col(p.get('pnl'))}'>{ms(p.get('pnl'))}</font>",
             f"<font color='{col(p['retorno'])}'>{p['retorno']:+.2f}%</font>"] for p in ctx["posiciones"][:6]]
        if len(filas) == 1: filas.append(["Sin posiciones abiertas.", "", "", ""])
        h += [Paragraph("Sus principales posiciones", st_h2), tabla(filas, [ancho_util * 0.3, ancho_util * 0.25, ancho_util * 0.25, ancho_util * 0.2], alinear_der=(1, 2, 3))]
        if len(ctx["posiciones"]) > 6:
            h.append(Paragraph(f"Y {len(ctx['posiciones']) - 6} posición(es) más. La edición Pro de la carta incluye el detalle completo.", st_nota))
    filas = [["Activo", "Clase", "Títulos", "Costo prom.", "Valor MXN", "Resultado", "Rend.", "Peso"]]
    for p in ctx["posiciones"]:
        filas.append([f"<b>{e(p['ticker'])}</b>", e(p["clase"]), tit(p.get("titulos")), m(p.get("costo_promedio")), m(p["valor"]),
                      f"<font color='{col(p.get('pnl'))}'>{ms(p.get('pnl'))}</font>", f"<font color='{col(p['retorno'])}'>{p['retorno']:+.2f}%</font>", f"{p['peso']:.1f}%"])
    if len(filas) == 1: filas.append(["Sin posiciones abiertas.", "", "", "", "", "", "", ""])
    w = ancho_util / 8
    if not esencial: h += [Paragraph("Composición del portafolio", st_h2),
          tabla(filas, [w * 0.95, w * 0.85, w * 1.0, w * 1.05, w * 1.1, w * 1.1, w * 0.95, w * 0.75], alinear_der=(2, 3, 4, 5, 6, 7))]


    # Contribución
    if len(ctx["posiciones"]) >= 2 and not esencial:
        orden = sorted(ctx["posiciones"], key=lambda p: p.get("pnl", 0))
        peor, mejor = orden[0], orden[-1]
        fila = lambda p: f"<b>{e(p['ticker'])}</b> &middot; <font color='{col(p.get('pnl'))}'>{ms(p.get('pnl'))} ({p['retorno']:+.2f}%)</font>"
        h += [Paragraph("Contribución al resultado", st_h2),
              tabla([["Mayor contribución", fila(mejor)], ["Menor contribución", fila(peor)]], [ancho_util * 0.5, ancho_util * 0.5], encabezado=False, alinear_der=(1,))]

    # Riesgo
    r = ctx.get("riesgo") or {}
    if r and esencial:
        beta = float(r.get("beta", 0) or 0)
        mov = (f"se mueve {abs(1 - beta) * 100:.0f}% {'menos' if beta < 1 else 'más'} que la bolsa de EE.UU." if abs(1 - beta) >= 0.03
               else "se mueve prácticamente igual que la bolsa de EE.UU.")
        h += [Paragraph("Su nivel de riesgo", st_h2),
              Paragraph(f"Su portafolio {mov} En los últimos 12 meses su peor caída fue de {abs(float(r.get('max_dd', 0) or 0)):.1f}%. "
                        f"Si la bolsa de EE.UU. cayera 20%, el impacto estimado sería de {ms(ctx['patrimonio'] * -0.20 * beta)}.", st_body)]
    elif r:
        beta = float(r.get("beta", 0) or 0)
        filas = [["Sensibilidad al mercado (beta vs S&amp;P 500)", f"{beta:.2f}"], ["Rendimiento ajustado por riesgo (Sharpe)", f"{r.get('sharpe', 0):.2f}"],
                 ["Volatilidad anualizada", f"{r.get('vol_anual', 0) * 100:.1f}%"], ["Caída máxima desde un punto alto", f"{r.get('max_dd', 0):.1f}%"],
                 ["Pérdida diaria que solo se supera 1 de cada 20 días (VaR 95%)", m(r.get("var_95_mxn", 0))],
                 ["Escenario de estrés: S&amp;P 500 -20% (impacto estimado por beta)", f"<font color='#6b7280'>{ms(ctx['patrimonio'] * -0.20 * beta)}</font>"]]
        h += [KeepTogether([Paragraph("Perfil de riesgo (últimos 12 meses)", st_h2), tabla(filas, [ancho_util * 0.72, ancho_util * 0.28], encabezado=False, alinear_der=(1,))])]

    # Flujos
    f = {k: v for k, v in (ctx.get("flujos") or {}).items() if v} if not esencial else {}
    if f:
        h += [KeepTogether([Paragraph("Flujo de caja acumulado", st_h2), tabla([[e(k), m(v)] for k, v in f.items()], [ancho_util * 0.68, ancho_util * 0.32], encabezado=False, alinear_der=(1,))])]

    # Operaciones recientes
    act = (ctx.get("actividad") or []) if not esencial else []
    if act:
        filas = [["Fecha", "Tipo", "Activo", "Títulos", "T.C.", "Total MXN"]] + [
            [e(a["fecha"]), e(a["tipo"]), f"<b>{e(a['ticker'])}</b>", tit(a["titulos"]), f"{a['tc']:.4f}", m(a["total"])] for a in act]
        w = ancho_util / 6
        h += [Paragraph("Operaciones recientes", st_h2), tabla(filas, [w * 1.1, w * 0.95, w * 0.9, w, w * 0.9, w * 1.15], alinear_der=(3, 4, 5))]

    # Disciplina y escenarios
    h += [Paragraph("Disciplina y metas", st_h2),
          Paragraph(f"Aportaciones consecutivas: <b>{ctx['racha']}</b> periodo(s) con frecuencia {e(str(ctx['frecuencia']).lower())}. "
                    f"Meta «{e(ctx['meta_nombre'])}»: hito de {m(ctx['meta_monto'])}, avance de {ctx['progreso_meta']:.1f}%; faltan {m(ctx['faltante'])}.", st_body),
          Paragraph("Escenarios observados", st_h2)]
    for esc in _siguientes_acciones_carta(ctx):
        h.append(Paragraph(esc, ParagraphStyle("li", parent=st_body, leftIndent=12, bulletIndent=2, spaceAfter=4), bulletText="•"))

    if ctx.get("cio") and not esencial:
        caja = Table([[Paragraph(e(ctx["cio"]).replace("\n", "<br/>"), ParagraphStyle("cio", parent=st_body, fontSize=8.6, leading=12.5))]], colWidths=[ancho_util])
        caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_SELLO), ("LINEBEFORE", (0, 0), (0, -1), 1.5, C_ORO),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        h += [Paragraph("Boletín del CIO Virtual (informativo)", st_h2), caja, Spacer(1, 4), Paragraph(e(AVISO_BOLETIN_CIO), st_legal)]

    # Sello · Estándar CMA
    principios = [
        ("Precisión al centavo", "Su costo se calcula con el tipo de cambio que usted realmente pagó en cada operación, con comisiones e impuestos incluidos."),
        ("Valuación transparente", f"Cada posición se valúa con precios de cierre de mercado y el tipo de cambio del día{tc_txt}. Las ganancias se presentan como no realizadas hasta la venta."),
        ("Rendimiento real", "Su tasa anual (XIRR) considera la fecha exacta de cada depósito y retiro, y se contrasta contra CETES como referencia libre de riesgo."),
        ("Riesgo medido, no supuesto", "Doce meses de datos diarios: sensibilidad al mercado, caída máxima y pérdida diaria de referencia (VaR 95%)."),
        ("Confidencialidad", "Su información se resguarda en una base de datos privada con acceso protegido por credenciales cifradas. Solo usted y su gestor la consultan."),
        ("Información, no promesas", "Este documento es un registro fiel de su patrimonio. Toda proyección declara sus supuestos y ninguna cifra se presenta como garantía."),
    ]
    st_pt = ParagraphStyle("pt", parent=st_body, fontSize=8.2, leading=11.6, textColor=C_SOFT)
    celda = lambda t, d: Paragraph(f"<font name='Helvetica-Bold' color='#1f2937' size='8.8'>{t}</font><br/>{e(d)}", st_pt)
    ancho_in = ancho_util - 28
    grid = Table([[celda(*principios[i]), celda(*principios[i + 1])] for i in (0, 2, 4)], colWidths=[ancho_in / 2, ancho_in / 2])
    grid.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, C_SELLO_BORDE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    enc = Table([[Sello(), Paragraph("<font name='Helvetica' size='7' color='#8a7a4a'>E S T Á N D A R &nbsp; C M A</font><br/>"
                                     "<font name='Times-Italic' size='14' color='#8a6d1f'>Nuestro compromiso con su patrimonio</font>",
                                     ParagraphStyle("st", parent=st_body, leading=17))]], colWidths=[18 * mm, ancho_in - 18 * mm])
    enc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    interior = [enc, Spacer(1, 8), Paragraph("Cada cifra de esta carta se construye con el mismo cuidado con el que usted construyó su patrimonio. "
                                              "Estos son los principios que respaldan cada número que lee.", st_soft), Spacer(1, 4), grid, Spacer(1, 8),
                Paragraph(f"Emitido el {hoy:%d/%m/%Y} &middot; Folio {folio}", ParagraphStyle("fo", parent=st_body, fontSize=7.4, textColor=C_ORO_TXT, alignment=TA_RIGHT))]
    sello = Table([[interior]], colWidths=[ancho_util])
    sello.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_SELLO), ("BOX", (0, 0), (-1, -1), 0.6, C_SELLO_BORDE), ("LINEABOVE", (0, 0), (-1, 0), 1.6, C_ORO),
                               ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 14), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
    h += [Spacer(1, 22), KeepTogether([sello])]

    # Firma y aviso legal
    h += [Spacer(1, 20), Paragraph("Quedamos a sus órdenes para revisar cualquier punto.", st_body), Spacer(1, 6),
          Paragraph("<font name='Times-Roman' size='12'>CMA &middot; Private Wealth</font><br/><font color='#6b7280'>Terminal APPortafolio</font>", st_body),
          Spacer(1, 18), Table([[""]], colWidths=[ancho_util], style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, C_LINEA)]),
          Paragraph("Documento informativo generado automáticamente con datos registrados por el cliente y cotizaciones de mercado (Yahoo Finance). "
                    "Los rendimientos son no realizados y no garantizan resultados futuros. Las proyecciones usan supuestos explícitos y no constituyen "
                    "una recomendación personalizada de inversión." + ("" if esencial else "<br/><br/>" + e(AVISO_LECTURA_V5)), st_legal)]

    def fondo(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_PAPEL); canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setFont("Helvetica", 6.8); canvas.setFillColor(C_ORO_TXT)
        canvas.drawString(16 * mm, 10 * mm, f"CMA · Private Wealth · Folio {folio}")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"CMA Financial Letter · {ctx['nombre']}", author="CMA · Private Wealth", subject=f"Folio {folio}")
    doc.build(h, onFirstPage=fondo, onLaterPages=fondo)
    return buf.getvalue()


def render_carta_cma(ctx, pro=False, xp=None):
    """Carta CMA en dos ediciones: esencial (modo sencillo, al grano) y Pro (detallada, con gráficas).
    La vista previa muestra las páginas reales del PDF; si no se puede, se muestra la versión HTML como antes."""
    st.markdown("<br>", unsafe_allow_html=True)
    nombre_archivo = f"Carta_CMA{'_Pro' if pro else ''}_{re.sub(r'[^A-Za-z0-9_-]', '_', str(ctx['nombre']))}_{hoy_mx():%Y%m%d}"
    # Fluidez: el PDF (y sus páginas de vista previa) se rehace solo cuando cambia su contenido, no en cada clic.
    huella = hashlib.sha256(json.dumps([ctx, xp, pro, str(hoy_mx())], default=str, sort_keys=True).encode()).hexdigest()
    cache = st.session_state.get("_carta_cache") or {}
    if cache.get("huella") == huella:
        pdf, edicion_pro, carta_html = cache["pdf"], cache["edicion_pro"], cache.get("html")
    else:
        pdf, edicion_pro, carta_html = _construir_carta(ctx, pro, xp)
        if pdf is None and carta_html is None:
            st.caption("No pude generar la carta en este momento.")
            return
        st.session_state["_carta_cache"] = cache = {"huella": huella, "pdf": pdf, "edicion_pro": edicion_pro, "html": carta_html}
    _pintar_carta(ctx, pro, pdf, edicion_pro, carta_html, nombre_archivo, cache)


def _construir_carta(ctx, pro, xp):
    pdf, edicion_pro = None, False
    if pro and carta_pro is not None and xp is not None:
        try:
            pdf = carta_pro.generar_carta_pro_pdf(ctx, xp, folio_carta(ctx), f"Ciudad de México, {fp_fecha_larga(hoy_mx()).lower()} de {hoy_mx().year}",
                                                  _siguientes_acciones_carta(ctx), AVISO_LECTURA_V5, AVISO_BOLETIN_CIO)
            edicion_pro = True
        except Exception as ex:
            log_app.warning("Carta CMA Pro · se entrega la carta base: %s", ex)
    if pdf is None:
        try:
            pdf = generar_carta_pdf(ctx, version="completa" if pro else "esencial")
        except Exception as ex:   # sin reportlab o error de maquetación: se ofrece el HTML como antes
            log_app.warning("Carta CMA · PDF no disponible, se ofrece HTML: %s", ex)
    carta_html = None
    if pdf is None:
        try:
            carta_html = generar_carta_cma(ctx)
        except Exception as ex:
            log_app.warning("Carta CMA · %s", ex)
    return pdf, edicion_pro, carta_html


def _pintar_carta(ctx, pro, pdf, edicion_pro, carta_html, nombre_archivo, cache):
    descripcion = ("Edición Pro: evolución contra S&amp;P 500 y CETES, de dónde viene tu resultado, riesgo, escenarios de estrés, "
                   "dividendos, agenda y proyección, con gráficas y folio verificable." if pro else
                   "Tu resumen al corte de hoy: cuánto tienes, cuánto has ganado, dónde está tu dinero y cómo vas con tu meta.")
    with st.container(key="carta_card"):
        c_txt, c_btn = st.columns([2.2, 1], vertical_alignment="center")
        c_txt.markdown(f"<div class='ap-carta notranslate' translate='no'>{SELLO_SVG.replace('#8a6d1f', '#e2c575')}"
                       f"<div><h3>CMA Financial Letter{' · Pro' if pro else ''}</h3><p>{descripcion}</p></div></div>", unsafe_allow_html=True)
        if pdf is not None:
            c_btn.download_button("Descargar carta (PDF)", data=pdf, file_name=f"{nombre_archivo}.pdf", mime="application/pdf",
                                  use_container_width=True, key="carta_pdf")
        else:
            c_btn.download_button("Descargar carta (HTML)", data=carta_html.encode("utf-8"), file_name=f"{nombre_archivo}.html",
                                  mime="text/html", use_container_width=True, key="carta_html")
        if pro and not ctx.get("cio"):
            st.caption("El Boletín del CIO Virtual se agrega a la carta cuando lo actualizas en esta sesión.")
        with st.expander("Vista previa", expanded=False):   # fuera del acordeón: mismo desplegable en ambas ediciones
            paginas = cache.get("paginas")
            if paginas is None:
                paginas = []
                if pdf is not None and carta_pro is not None:
                    try:
                        paginas = carta_pro.paginas_png(pdf)
                    except Exception as ex:
                        log_app.warning("Carta CMA · vista previa: %s", ex)
                cache["paginas"] = paginas
            if paginas:
                st.caption(f"{len(paginas)} página(s) · {'edición Pro' if edicion_pro else 'edición esencial' if not pro else 'carta completa'}")
                for img in paginas:
                    st.image(img, use_container_width=True)
            else:
                import streamlit.components.v1 as components
                components.html(carta_html or generar_carta_cma(ctx), height=1100, scrolling=True)


if "user_id" not in st.session_state: st.session_state["user_id"] = None

# Leyenda de la portada (informativa, sin prometer asesoría ni rendimientos: Norma 2).
# Anteriores: "Exclusivo y personalizado para ti." · "Su patrimonio, analizado con rigor institucional."
LEYENDA_PORTADA = "Claridad para decidir. Rigor para construir patrimonio."

# ==========================================
# 4. PORTADA · ACCESO DE CLIENTES (DOS COLUMNAS, RESPONSIVA)
# ==========================================
# --- Portada de acceso: 4 variantes animadas (mismo diseño que la vista previa "Portadas APPortafolio") ---
# LOGIN_VARIANTE es la definitiva. Para comparar en localhost sin tocar código: http://localhost:8501/?portada=3
LOGIN_VARIANTES = {1: "Hilo de oro", 2: "Doble trazo", 3: "Trazo vivo", 4: "Marco de luz"}
LOGIN_VARIANTE = 4   # definitiva: Marco de luz con dos ondas


def variante_portada():
    try:
        v = int(st.query_params.get("portada", LOGIN_VARIANTE))
    except Exception:
        v = LOGIN_VARIANTE
    return v if v in LOGIN_VARIANTES else LOGIN_VARIANTE


_ONDA_A = "M 60 940 C 150 700, 330 600, 520 500 S 840 300, 990 -40"
_ONDA_B = "M 150 960 C 250 720, 430 630, 620 530 S 950 330, 1110 -40"
_ONDA_B_INV = "M 1110 -40 C 950 330, 810 430, 620 530 C 430 630, 250 720, 150 960"   # misma curva, sentido opuesto
SVG_ONDA_PORTADA = (
    '<svg class="ap-onda" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
    '<defs><linearGradient id="apOro" gradientUnits="userSpaceOnUse" x1="0" y1="900" x2="1000" y2="0">'
    '<stop offset="0" stop-color="#c9a24a" stop-opacity="0"/><stop offset=".35" stop-color="#c9a24a" stop-opacity=".38"/>'
    '<stop offset=".7" stop-color="#e9d39a" stop-opacity=".32"/><stop offset="1" stop-color="#c9a24a" stop-opacity="0"/>'
    '</linearGradient><filter id="apHalo" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter></defs>'
    f'<path class="base b1" pathLength="100" d="{_ONDA_A}"/>'
    f'<path class="base b2" pathLength="100" d="{_ONDA_B}"/>'
    f'<path class="halo l1" pathLength="100" d="{_ONDA_A}"/><path class="luz l1" pathLength="100" d="{_ONDA_A}"/>'
    f'<path class="halo l2" pathLength="100" d="{_ONDA_B}"/><path class="luz l2" pathLength="100" d="{_ONDA_B}"/>'   # ambas luces suben
    '</svg>')

_ICONO_USUARIO = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
                  "stroke='%237d8494' stroke-width='1.6'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7'/%3E%3C/svg%3E\")")
_ICONO_CANDADO = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
                  "stroke='%237d8494' stroke-width='1.6'%3E%3Crect x='5' y='11' width='14' height='10' rx='2'/%3E%3Cpath d='M8 11V8a4 4 0 0 1 8 0v3'/%3E%3C/svg%3E\")")

_CSS_PORTADA_BASE = """
<style>
:root { --pt-ob: #050608; --pt-card: rgba(11,13,18,0.94); --pt-campo: #10131a; --pt-linea: rgba(255,255,255,0.08);
        --pt-linea-2: #232833; --pt-tx: #eef0f4; --pt-tx-2: #a3a9b6; --pt-tx-3: #6b7280;
        --pt-oro: #c9a24a; --pt-oro-claro: #e9d39a; --pt-oro-luz: #fff4d6; }
[data-testid="stAppViewContainer"], .stApp {
    background: radial-gradient(1100px 700px at 18% 28%, rgba(255,255,255,0.035), transparent 62%),
                radial-gradient(900px 600px at 88% 90%, rgba(201,162,74,0.05), transparent 60%), var(--pt-ob) !important; }

/* Onda dorada fija detrás de todo; el contenido queda por encima */
.ap-onda { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 0; pointer-events: none; }
.ap-onda .base { fill: none; stroke: url(#apOro); stroke-width: 1.1; }
.ap-onda .luz, .ap-onda .halo { fill: none; stroke-linecap: round; stroke-dasharray: 7 100; stroke-dashoffset: 7; opacity: 0; }
.ap-onda .luz { stroke: var(--pt-oro-luz); stroke-width: 1.8; }
.ap-onda .halo { stroke: var(--pt-oro); stroke-width: 7; filter: url(#apHalo); }
.ap-onda .b2, .ap-onda .l2 { display: none; }
[data-testid="stHorizontalBlock"] { position: relative; z-index: 1; min-height: calc(100vh - 7rem); }

/* Marca */
.ap-marca { container-type: inline-size; width: 100%; }
.portada-title { font-family: 'Montserrat', 'Segoe UI', sans-serif !important; font-weight: 400; color: var(--pt-tx);
    font-size: clamp(1.2rem, 7.4cqi, 3.4rem); letter-spacing: 0.32em; line-height: 1.25; white-space: nowrap; margin: 0; }
.portada-title span { display: block; }
.portada-title .regla { display: block; width: 76px; height: 2px; margin: 0.3em 0 0.4em;
    background: linear-gradient(90deg, var(--pt-oro), var(--pt-oro-claro)); transform-origin: left; }
.portada-subtitle { margin: 26px 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-weight: 400;
    font-size: clamp(0.82rem, 1.25vw, 1rem); letter-spacing: 0.08em; color: var(--pt-tx-2); }

/* Tarjeta de acceso = el formulario de Streamlit */
[data-testid="stForm"] { position: relative; max-width: 440px; margin-left: auto; background: var(--pt-card) !important;
    border: 1px solid var(--pt-linea) !important; border-radius: 14px !important; padding: 34px 32px 26px !important; }
.ap-ojo { margin: 0 0 6px !important; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 0.72rem !important;
    letter-spacing: 0.28em; text-transform: uppercase; color: var(--pt-tx-2) !important; }
[data-testid="stForm"] [data-testid="stWidgetLabel"] p { font-family: 'Inter', sans-serif; font-size: 0.8rem !important;
    font-weight: 500; color: #c9ced8 !important; }
[data-testid="stForm"] [data-baseweb="input"] { min-height: 46px; border-radius: 8px !important; background-color: var(--pt-campo) !important;
    border: 1px solid var(--pt-linea-2) !important; transition: border-color .3s ease, box-shadow .3s ease; }
[data-testid="stForm"] [data-baseweb="input"]:focus-within { border-color: rgba(201,162,74,0.55) !important;
    box-shadow: 0 0 0 3px rgba(201,162,74,0.10) !important; }
[data-testid="stForm"] [data-baseweb="base-input"], [data-testid="stForm"] input { background: transparent !important; }
[data-testid="stForm"] input { color: var(--pt-tx) !important; font-family: 'Inter', sans-serif !important; font-size: 0.88rem !important; }
[data-testid="stForm"] input::placeholder { color: #5f6675 !important; }
.st-key-login_usr [data-baseweb="input"] { background: var(--pt-campo) __ICONO_USUARIO__ no-repeat 14px center / 17px !important; }
.st-key-login_pwd [data-baseweb="input"] { background: var(--pt-campo) __ICONO_CANDADO__ no-repeat 14px center / 17px !important; }
.st-key-login_usr input, .st-key-login_pwd input { padding-left: 42px !important; }
[data-testid="stForm"] [data-baseweb="input"] button svg { fill: #7d8494 !important; }
[data-testid="InputInstructions"] { display: none !important; }
[data-testid="stFormSubmitButton"] button { min-height: 46px; margin-top: 8px; border: 0 !important; border-radius: 8px !important;
    background: linear-gradient(135deg, #b9913f 0%, #d9bb72 55%, #c9a24a 100%) !important; color: #15120b !important;
    transition: transform .25s ease, box-shadow .25s ease, filter .25s ease !important; }
[data-testid="stFormSubmitButton"] button p { font-family: 'Inter', sans-serif !important; font-weight: 600 !important; font-size: 0.92rem !important; letter-spacing: 0.02em; }
[data-testid="stFormSubmitButton"] button:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(201,162,74,0.22) !important; filter: brightness(1.04); }
.ap-pie { margin: 6px 0 0 !important; text-align: center; font-size: 0.68rem !important; color: var(--pt-tx-3) !important; letter-spacing: 0.04em; }

/* Animaciones comunes */
@keyframes ptIzq { from { opacity: 0; transform: translateX(-28px); } to { opacity: 1; transform: none; } }
@keyframes ptDer { from { opacity: 0; transform: translateX(32px); } to { opacity: 1; transform: none; } }
@keyframes ptAbajo { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: none; } }
@keyframes ptAparece { from { opacity: 0; } to { opacity: 1; } }
@keyframes ptCrece { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes ptRecorrido { 0% { stroke-dashoffset: 7; opacity: 0; } 4% { opacity: 1; } 34% { opacity: 1; }
    38% { stroke-dashoffset: -100; opacity: 0; } 100% { stroke-dashoffset: -100; opacity: 0; } }
@keyframes ptDibuja { from { stroke-dashoffset: 100; } to { stroke-dashoffset: 0; } }
@keyframes ptDestello { 0% { background-position: 100% 0; } 22% { background-position: 0% 0; } 100% { background-position: 0% 0; } }
@property --pt-ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
@keyframes ptGiro { to { --pt-ang: 360deg; } }

/* Teléfono: Streamlit apila las columnas; todo entra desde abajo */
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] { min-height: auto; padding-top: 18px; }
    .ap-marca { text-align: center; }
    .portada-title { font-size: clamp(1.1rem, 8.2cqi, 2.2rem); letter-spacing: 0.22em; padding-left: 0.22em; }
    .portada-title .regla { margin-left: auto; margin-right: auto; transform-origin: center; }
    .portada-subtitle { margin-top: 18px; margin-bottom: 18px; }
    [data-testid="stForm"] { margin: 0 auto; padding: 28px 22px 22px !important; animation-name: ptAbajo !important; }
}
@media (prefers-reduced-motion: reduce) {
    .ap-onda *, .ap-marca *, .ap-marca, [data-testid="stForm"], [data-testid="stForm"]::before { animation: none !important; }
}
__VARIANTE__
</style>
"""

_CSS_PORTADA_VARIANTE = {
    # 1 · Hilo de oro: fiel a la referencia. Marca desde la izquierda, tarjeta desde la derecha, luz cada 9 s.
    1: """
.portada-title span:first-child { animation: ptIzq .9s cubic-bezier(.2,.7,.2,1) .1s both; }
.portada-title span:last-child { animation: ptIzq .9s cubic-bezier(.2,.7,.2,1) .25s both; }
.portada-title .regla { animation: ptCrece .8s cubic-bezier(.2,.7,.2,1) .55s both; }
.portada-subtitle { animation: ptAparece 1s ease .8s both; }
[data-testid="stForm"] { animation: ptDer 1s cubic-bezier(.2,.7,.2,1) .35s both; }
.ap-onda .base { animation: ptAparece 1.6s ease .2s both; }
.ap-onda .l1 { animation: ptRecorrido 9s cubic-bezier(.45,.05,.35,1) 1.8s infinite; }
""",
    # 2 · Doble trazo: dos ondas, luces en sentidos opuestos y desfasadas. La tarjeta sube.
    2: """
.ap-onda .b2, .ap-onda .l2 { display: inline; }
.ap-marca { animation: ptAparece 1.1s ease .1s both; }
.portada-title .regla { animation: ptCrece .8s cubic-bezier(.2,.7,.2,1) .6s both; }
.portada-subtitle { animation: ptAbajo .9s ease .7s both; }
[data-testid="stForm"] { animation: ptAbajo 1s cubic-bezier(.2,.7,.2,1) .4s both; }
.ap-onda .base { animation: ptAparece 1.6s ease both; }
.ap-onda .b2 { opacity: .55; }
.ap-onda .l1 { animation: ptRecorrido 11s cubic-bezier(.45,.05,.35,1) 1.6s infinite; }
.ap-onda .l2 { animation: ptRecorrido 11s cubic-bezier(.45,.05,.35,1) 7.1s infinite; }
""",
    # 3 · Trazo vivo: la onda se dibuja al abrir; destello champaña sobre el título cada ~10 s.
    3: """
.ap-onda .base { stroke-dasharray: 100; animation: ptDibuja 2.6s cubic-bezier(.6,0,.2,1) .2s both; }
.ap-onda .l1 { animation: ptRecorrido 10s cubic-bezier(.45,.05,.35,1) 3s infinite; }
.ap-marca { animation: ptIzq 1s cubic-bezier(.2,.7,.2,1) .3s both; }
.portada-title .regla { animation: ptCrece .8s cubic-bezier(.2,.7,.2,1) 1s both; }
.portada-subtitle { animation: ptAparece 1s ease 1.2s both; }
[data-testid="stForm"] { animation: ptDer 1s cubic-bezier(.2,.7,.2,1) .7s both; }
.portada-title { background: linear-gradient(100deg, var(--pt-tx) 0%, var(--pt-tx) 42%, var(--pt-oro-claro) 50%, var(--pt-tx) 58%, var(--pt-tx) 100%);
    background-size: 280% 100%; background-position: 100% 0; -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; animation: ptDestello 10s ease-in-out 3.4s infinite; }
@media (prefers-reduced-motion: reduce) { .ap-onda .base { stroke-dasharray: none; } }
""",
    # 4 · Marco de luz (definitiva): dos ondas como en la 2 + luz que recorre el borde de la tarjeta.
    4: """
.ap-onda .b2, .ap-onda .l2 { display: inline; }
.ap-onda .b2 { opacity: .55; }
.ap-onda .l2 { animation: ptRecorrido 14s cubic-bezier(.45,.05,.35,1) 13s infinite; }
.portada-title span:first-child { animation: ptIzq .9s cubic-bezier(.2,.7,.2,1) .1s both; }
.portada-title span:last-child { animation: ptIzq .9s cubic-bezier(.2,.7,.2,1) .25s both; }
.portada-title .regla { animation: ptCrece .8s cubic-bezier(.2,.7,.2,1) .55s both; }
.portada-subtitle { animation: ptAparece 1s ease .8s both; }
[data-testid="stForm"] { animation: ptDer 1s cubic-bezier(.2,.7,.2,1) .35s both; }
.ap-onda .base { animation: ptAparece 1.6s ease .2s both; }
.ap-onda .l1 { animation: ptRecorrido 14s cubic-bezier(.45,.05,.35,1) 6s infinite; }
[data-testid="stForm"]::before { content: ""; position: absolute; inset: -1px; border-radius: 15px; padding: 1px; pointer-events: none;
    background: conic-gradient(from var(--pt-ang), transparent 0deg, transparent 300deg, rgba(233,211,154,0) 318deg, rgba(255,244,214,.85) 340deg, rgba(233,211,154,0) 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ptGiro 7s linear 1.4s infinite; }
""",
}


def css_portada(variante):
    return (_CSS_PORTADA_BASE.replace("__ICONO_USUARIO__", _ICONO_USUARIO).replace("__ICONO_CANDADO__", _ICONO_CANDADO)
            .replace("__VARIANTE__", _CSS_PORTADA_VARIANTE.get(variante, _CSS_PORTADA_VARIANTE[1])))


if st.session_state["user_id"] is None:
    _variante = variante_portada()
    st.markdown(css_portada(_variante), unsafe_allow_html=True)
    st.markdown(SVG_ONDA_PORTADA, unsafe_allow_html=True)

    c_izq, c_der = st.columns([1.25, 1], gap="large", vertical_alignment="center")
    with c_izq:
        st.markdown("<div class='ap-marca notranslate' translate='no'>"
                    "<div class='portada-title' role='heading' aria-level='1'>"
                    "<span>TERMINAL</span><i class='regla'></i><span>APPORTAFOLIO</span></div>"
                    f"<p class='portada-subtitle'>{html_seguro(LEYENDA_PORTADA)}</p></div>", unsafe_allow_html=True)
    with c_der:
        with st.form("login_form"):
            st.markdown("<p class='ap-ojo'>Acceso privado</p>", unsafe_allow_html=True)
            usr = st.text_input("Identificador", placeholder="Ingresa tu identificador", key="login_usr")
            pwd = st.text_input("Clave de acceso", type="password", placeholder="Ingresa tu clave de acceso", key="login_pwd")
            enviar = st.form_submit_button("Acceder", use_container_width=True)
            st.markdown("<p class='ap-pie'>Entorno privado · Acceso protegido</p>", unsafe_allow_html=True)
            if enviar:
                uid_ok = autenticar(db_conn, usr, pwd)
                if uid_ok:
                    st.session_state.pop("login_pwd", None)   # la clave no se queda en la sesión
                    st.session_state["user_id"] = uid_ok
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")
    st.stop()

# ==========================================
# 4.1 PUERTA LEGAL · TÉRMINOS Y CONDICIONES (post-login)
# ==========================================
# Concentra en un solo punto de aceptación los avisos que antes vivían debajo de cada componente
# (lectura V5, Boletín CIO, rebalanceo, ganancias no realizadas y estimaciones de "Tu dinero hoy").
# Se acepta una vez por sesión; "Cerrar Sesión" limpia el estado y la vuelve a pedir en el siguiente acceso.
TERMINOS_Y_CONDICIONES = [
    ("Naturaleza de la plataforma",
     "APortafolio es una herramienta de visualización, registro y análisis cuantitativo de su patrimonio. No es una "
     "casa de bolsa, no custodia valores ni ejecuta órdenes: las operaciones que usted captura son registros de "
     "control interno."),
    ("Lecturas de inteligencia artificial",
     "La Lectura Cuantitativa V5, el Boletín del CIO Virtual y los diagnósticos automáticos se generan con modelos "
     "de inteligencia artificial y datos públicos de mercado. Son de carácter general, informativo y educativo: no "
     "constituyen asesoría en inversiones, recomendación personalizada ni oferta o invitación a comprar, vender o "
     "mantener valores, y no evalúan su perfil de riesgo, horizonte, situación financiera ni fiscal."),
    ("Escenarios y simulaciones",
     "Las categorías de señal, el simulador de rebalanceo, las proyecciones y los escenarios de estrés son cálculos "
     "aritméticos con supuestos explícitos; no consideran costos, impuestos ni su perfil de inversionista y no "
     "garantizan resultados."),
    ("Datos y valuaciones",
     "Las cotizaciones provienen de fuentes públicas (Yahoo Finance) y pueden contener errores o retrasos. Las "
     "ganancias y pérdidas mostradas son no realizadas hasta que se vende la posición. Los montos de finanzas "
     "personales son estimaciones con base en lo que usted registra y no sustituyen el saldo de su banco. Las fechas "
     "de reportes, dividendos y eventos macroeconómicos deben verificarse en fuentes oficiales."),
    ("Riesgo",
     "Invertir implica riesgo, incluida la pérdida total del capital. Los rendimientos pasados no garantizan "
     "resultados futuros. Toda decisión de inversión es responsabilidad exclusiva del usuario, quien puede consultar "
     "a un asesor en inversiones autorizado."),
]

TYC_VERSION = "2026-10"   # cambiar al modificar los términos: obliga a todos a aceptarlos de nuevo

@st.cache_resource
def _asegurar_tabla_tyc():
    """Bitácora de aceptaciones (una fila por usuario y versión). Idempotente; corre una vez por proceso."""
    with db_conn(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tyc_aceptaciones (
                user_id     TEXT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                version     TEXT        NOT NULL,
                aceptado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, version)
            )""")
    return True

@lectura_cacheada(ttl=300)
def tyc_aceptados_en_bd(uid, version):
    _asegurar_tabla_tyc()
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM tyc_aceptaciones WHERE user_id = %s AND version = %s", (uid, version))
        return cur.fetchone() is not None

def registrar_aceptacion_tyc(uid, version):
    """Guarda la aceptación con la hora del servidor de Neon (CURRENT_TIMESTAMP). Si ya existía, conserva la original."""
    _asegurar_tabla_tyc()
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO tyc_aceptaciones (user_id, version, aceptado_en) VALUES (%s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (user_id, version) DO NOTHING", (uid, version))
    tyc_aceptados_en_bd.clear()   # explícito: el próximo acceso lee la aceptación recién guardada

# Quien ya aceptó esta versión en Neon entra directo al dashboard (se consulta una vez por sesión).
if not st.session_state.get("tyc_aceptados", False):
    try:
        st.session_state["tyc_aceptados"] = tyc_aceptados_en_bd(st.session_state["user_id"], TYC_VERSION)
    except Exception:
        log_app.exception("T&C · no se pudo consultar la bitácora de aceptación")

if not st.session_state.get("tyc_aceptados", False):
    st.markdown("""
    <style>
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    .block-container { max-width: 860px !important; padding-top: 6vh !important; }
    .tyc-eyebrow { font-size: 0.7rem; letter-spacing: 2.6px; text-transform: uppercase; color: var(--ap-gold); margin: 0 0 6px 0; }
    .tyc-titulo { font-family: var(--ap-font-serif); font-style: italic; font-size: 2rem; color: #ffffff; margin: 0 0 18px 0; }
    .tyc-seccion { color: var(--ap-text); font-weight: 600; font-size: 0.9rem; margin: 16px 0 4px 0; }
    .tyc-texto { color: var(--ap-text-muted); font-size: 0.88rem; line-height: 1.65; margin: 0; }
    </style>
    """, unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<p class='tyc-eyebrow notranslate' translate='no'>CMA Wealth · Aviso legal</p>"
                    "<p class='tyc-titulo notranslate' translate='no'>Términos y condiciones de uso</p>"
                    + "".join(f"<p class='tyc-seccion'>{html_seguro(t)}</p><p class='tyc-texto'>{html_seguro(d)}</p>"
                              for t, d in TERMINOS_Y_CONDICIONES)
                    + "<p class='tyc-texto' style='margin-top:18px;'>Al continuar, usted declara haber leído y aceptado "
                      "estos términos.</p>", unsafe_allow_html=True)
        if st.button("Aceptar y Entrar a la Terminal", type="primary", use_container_width=True, key="tyc_aceptar"):
            try:
                registrar_aceptacion_tyc(st.session_state["user_id"], TYC_VERSION)
            except Exception:
                log_app.exception("T&C · no se pudo registrar la aceptación")
                st.error("No pudimos registrar tu aceptación. Intenta de nuevo en un momento.")   # sin registro no se entra
            else:
                st.session_state["tyc_aceptados"] = True
                st.rerun()
    st.stop()

# ==========================================
# 5. GESTIÓN MULTI-CLIENTE Y SIDEBAR
# ==========================================
user_id = st.session_state["user_id"]
@lectura_cacheada(ttl=300)
def listar_usuarios():
    return read_df("SELECT user_id, username FROM users ORDER BY username")

all_users = listar_usuarios()
ES_ADMIN = es_admin(user_id)   # P0-B · rol leído de la base en cada rerun

# Rediseño 2026-10 · Barra lateral estilo banca móvil. Los huecos se crean en el orden visual y cada bloque escribe en el
# suyo, así el orden de la barra no depende del orden del código. Los permisos (gestor vs cliente) no cambian.
SB = {k: st.sidebar.container(key=f"sb_{k}") for k in ("top", "ficha", "inv", "pref", "cuenta", "pie")}
if pro_ui is not None:
    st.markdown(pro_ui.CSS_SIDEBAR, unsafe_allow_html=True)
_grp = (lambda t: pro_ui.html_grupo(t)) if pro_ui is not None else (lambda t: f"<p style='font-size:0.7rem;color:#6b7385;'>{t.upper()}</p>")
SB["pref"].markdown(_grp("Preferencias"), unsafe_allow_html=True)
SB["cuenta"].markdown(_grp("Cuenta"), unsafe_allow_html=True)


def _exp(cont, etiqueta, icono=None, abierto=False):
    """Renglón desplegable de la barra (con ícono si la versión de Streamlit lo admite)."""
    try:
        return cont.expander(etiqueta, expanded=abierto, icon=icono)
    except TypeError:
        return cont.expander(etiqueta, expanded=abierto)


def _btn(cont, etiqueta, icono=None, **kw):
    try:
        return cont.button(etiqueta, icon=icono, **kw)
    except TypeError:
        return cont.button(etiqueta, **kw)


def _ficha(nombre, rol, detalle):
    if pro_ui is not None:
        return pro_ui.html_ficha_cliente(nombre, rol, detalle)
    return f"<h3 style='color:#d4af37; font-family:\"Playfair Display\"; font-style:italic;'>{html_seguro(nombre)}</h3>"

if ES_ADMIN:
    _ficha_ph = SB["ficha"].empty()   # se llena con el cliente elegido (abajo)
    client_dict = dict(zip(all_users["username"], all_users["user_id"]))
    # Al iniciar sesión se abre la cartera propia del gestor (antes: el primer usuario en orden alfabético).
    _nombres_clientes = list(client_dict.keys())
    _ids_clientes = list(client_dict.values())
    _idx_propio = _ids_clientes.index(user_id) if user_id in _ids_clientes else 0
    selected_client_name = SB["ficha"].selectbox("Viendo la cartera de", _nombres_clientes, index=_idx_propio,
                                                 key=f"cliente_activo_{user_id}")
    active_client_id = client_dict[selected_client_name]
    active_username = selected_client_name 
    _ficha_ph.markdown(_ficha(active_username, "Gestor", f"Panel de gestor · {len(_nombres_clientes)} perfiles"), unsafe_allow_html=True)
    ui_boton_perfil(db_conn, user_id, active_client_id, contenedor=SB["cuenta"])   # renglón en Cuenta
    
    with _exp(SB["cuenta"], "Registrar nuevo cliente", ":material/person_add:"):
        with st.form("new_client_form"):
            new_usr = st.text_input("Nombre de Usuario")
            new_pwd = st.text_input("Contraseña Temporal", type="password")
            if st.form_submit_button("Crear Perfil"):
                if new_usr and new_pwd:
                    try:
                        with db_conn() as conn, conn.cursor() as cur:
                            cur.execute("INSERT INTO users (user_id, username, password_hash) VALUES (%s, %s, %s)", (f"USR-{uuid.uuid4().hex}", new_usr.strip(), hash_password_seguro(new_pwd)))   # Sprint 0
                        st.success("Creado con éxito. Recarga la página.")
                    except psycopg2.IntegrityError: st.error("El usuario ya existe.")
                    except Exception: st.error("No se pudo crear el perfil. Intenta de nuevo.")
else:
    active_client_id = user_id
    active_username = all_users.loc[all_users["user_id"] == user_id, "username"].values[0]
    SB["ficha"].markdown(_ficha(active_username, "Cliente", "Cartera privada"), unsafe_allow_html=True)
    ui_boton_perfil(db_conn, user_id, active_client_id, contenedor=SB["cuenta"])   # renglón en Cuenta

# Privacidad · Aislamiento de IA: las lecturas V5 y el Boletín CIO pertenecen a UN cliente. Si el gestor cambia
# de cliente se descartan en esta misma ejecución, antes de pintar nada (no pueden filtrarse a otro perfil).
if st.session_state.get("ia_cliente") != active_client_id:
    for _clave_ia in ("ai_memory", "cio_report"):
        st.session_state.pop(_clave_ia, None)
    st.session_state["ia_cliente"] = active_client_id

# 5.1 NAVEGACIÓN PRINCIPAL (Fase 3): "Tu dinero hoy" es el home; la Terminal sigue intacta.
if "modo_pro_toggle" in st.session_state:
    st.session_state["modo_pro_toggle"] = st.session_state["modo_pro_toggle"]   # conserva el Modo Pro al cambiar de sección
seccion = SB["top"].radio("Sección", [SECCION_FP, SECCION_TERMINAL], key="seccion_app", label_visibility="collapsed", horizontal=True,
                          format_func=lambda x: "Tu dinero hoy" if x == SECCION_FP else "Inversiones")

if _btn(SB["pie"], "Cerrar sesión", ":material/logout:", use_container_width=True, key="btn_cerrar_sesion"):
    st.session_state.clear()   # nada del usuario anterior (código de Telegram, reportes de IA) queda en pantalla
    st.session_state["user_id"] = None; st.rerun()

if seccion == SECCION_TERMINAL:
    SB["top"].toggle("Modo Pro", key="modo_pro_toggle", help="Muestra herramientas institucionales (XIRR, riesgo, CIO, carta Pro).")

# Sprint 2 · Modo de Lectura: se pinta en ambas secciones para que el tamaño de letra acompañe al usuario.
SB["pref"].radio("Modo de lectura", MODO_LECTURA_OPCIONES, key="modo_lectura", horizontal=True,
                 help="Senior: letra más grande, números claros y sin tecnicismos (Beta, VaR, Sharpe).")
MODO_SENIOR = st.session_state.get("modo_lectura", "Junior") == "Senior"
if MODO_SENIOR:
    st.markdown(ESTILOS_SENIOR, unsafe_allow_html=True)

with _exp(SB["pref"], "Estrategia y perfil", ":material/track_changes:"):
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
                # La clave se verifica ANTES de abrir la conexión de escritura: nunca se retienen dos conexiones a la vez.
                perfil_ok = verificar_usuario(db_conn, user_id, old_pwd)
                if perfil_ok:
                    with db_conn() as conn, conn.cursor() as cur:
                        if new_pwd and len(new_pwd) >= 6:
                            cur.execute("UPDATE users SET password_hash=%s, dca_frequency=%s, goal_name=%s WHERE user_id=%s", (hash_password_seguro(new_pwd), f_dca, f_goal, user_id))
                        else:
                            cur.execute("UPDATE users SET dca_frequency=%s, goal_name=%s WHERE user_id=%s", (f_dca, f_goal, user_id))
                        perfil_ok = True
                if perfil_ok: st.success("Perfil actualizado.")
                else: st.error("Clave incorrecta.")

    # render_fp_telegram(user_id)   # UX Beta: movido al área central (banner / línea compacta)

# Vinculación de Telegram: protagonista en el área central (siempre del usuario que inició sesión)
estado_tg = fp_estado_telegram(user_id)
if estado_tg == "PENDIENTE" and seccion == SECCION_TERMINAL:
    _btn(SB["cuenta"], "Conectar Telegram", ":material/send:", key="fp_tg_ir", on_click=_fp_ir_a_telegram, use_container_width=True,
         help="Registra tus gastos por chat en segundos.")

if seccion == SECCION_FP:
    if estado_tg == "PENDIENTE":
        render_fp_telegram_banner(user_id)          # hasta arriba, antes de "Tu dinero hoy" y "Registro rápido"
    render_fp_dashboard(active_client_id, active_username, viendo_otro_cliente=(active_client_id != user_id))
    if estado_tg in ("VINCULADO", "ERROR"):
        render_fp_telegram_compacto(user_id)        # línea discreta al final del dashboard
    if fp_esquema_listo():
        st.markdown("---")
        if fp_ui is not None and hasattr(fp_ui, "ui_planificacion"):
            fp_ui.ui_planificacion(db_conn, active_client_id)   # Reparto nuevo; Deudas y Metas como antes
        else:
            ui_planificacion(db_conn, active_client_id)
    st.stop()   # la Terminal (cotizaciones, riesgo, IA) no se calcula mientras no se abra

SB["inv"].markdown(_grp("Inversiones"), unsafe_allow_html=True)
SB_OP, SB_DEP, SB_REP = SB["inv"].container(), SB["inv"].container(), SB["inv"].container()
# P0-B · Lectura única y explícita de las tablas de la Terminal, siempre filtrada por el cliente activo
# (cliente = su propio user_id; admin = el cliente elegido en el Panel de Gestor). La reutilizan reportes, home e historial.
_TX_COLS = ("id, user_id, timestamp, fecha, tipo_operacion, ticker, clase, plataforma, moneda, "
            "titulos, precio_unitario, comision, iva, tipo_cambio, total_mxn")

@lectura_cacheada(ttl=60)
def cargar_tablas_terminal(uid):
    tx = read_df(f"SELECT {_TX_COLS} FROM transactions WHERE user_id=%s ORDER BY fecha, timestamp", (uid,))
    caja = read_df("SELECT id, user_id, fecha, tipo, concepto, monto_mxn FROM cash_movements WHERE user_id=%s ORDER BY fecha, id", (uid,))
    for col in ("titulos", "precio_unitario", "comision", "iva", "total_mxn"):
        tx[col] = pd.to_numeric(tx[col], errors="coerce").fillna(0.0)
    tx["tipo_cambio"] = pd.to_numeric(tx["tipo_cambio"], errors="coerce").fillna(1.0)
    caja["monto_mxn"] = pd.to_numeric(caja["monto_mxn"], errors="coerce").fillna(0.0)
    caja["tipo"] = caja["tipo"].fillna("").astype(str).str.upper().str.strip()
    caja["concepto"] = caja["concepto"].fillna("")
    return tx, caja

tx_df, cash_df = cargar_tablas_terminal(active_client_id)
export_df = tx_df

if not export_df.empty:
    clean_df = export_df.drop(columns=["id", "user_id", "timestamp"], errors="ignore")
    clean_df.rename(columns={"fecha": "Fecha", "tipo_operacion": "Tipo", "ticker": "Activo", "clase": "Clase", "plataforma": "Plataforma", "moneda": "Moneda", "titulos": "Títulos", "precio_unitario": "Precio Unitario", "comision": "Comisión", "iva": "IVA", "tipo_cambio": "Tipo de Cambio", "total_mxn": "Total MXN"}, inplace=True)
    col_dl1, col_dl2 = _exp(SB_REP, "Reportes `CSV · Excel`", ":material/download:").columns(2)
    with col_dl1: st.download_button("CSV", data=clean_df.to_csv(index=False).encode('utf-8'), file_name=f"Portafolio_{active_username}.csv", mime="text/csv", use_container_width=True)
    with col_dl2:
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: clean_df.to_excel(writer, index=False, sheet_name='Terminal')
            st.download_button("Excel", data=buffer.getvalue(), file_name=f"Portafolio_{active_username}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        except: st.download_button("Excel", data=clean_df.to_csv(index=False, sep=";").encode('latin1'), file_name=f"Portafolio_{active_username}_EXCEL.csv", mime="text/csv", use_container_width=True)
else: _exp(SB_REP, "Reportes `sin datos`", ":material/download:").caption("Aún no hay operaciones para exportar.")

# Modo Dios: el gestor registra operaciones en la cartera del cliente activo (antes solo en USR-001).
# Alternativa (comportamiento previo): `if active_client_id == "USR-001":`
if ES_ADMIN:
    _exp_op = _exp(SB_OP, f"Registrar operación `{len(tx_df)} ops`", ":material/swap_vert:")
    _exp_op.caption("1. Buscar activo y cotización")
    col_b1, col_b2 = _exp_op.columns([2, 1])
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
                            st.session_state["val_moneda"] = moneda_cotizacion(tk_sym)   # Sprint 0 · FX
                            _exp_op.success(f"${p:.2f} {st.session_state['val_moneda']}")
                        else: _exp_op.error("Sin datos.")
                    except: _exp_op.error("Inválido.")
            else: _exp_op.warning("Escribe un ticker.")

    val_t = st.session_state.get("val_ticker", "")
    val_p = float(st.session_state.get("val_price", 0.0))
    val_m = st.session_state.get("val_moneda", "")   # Sprint 0 · FX

    # Tipo de cambio: se congela UNA vez por sesión. Antes el campo usaba value=live_usd_rate, que se refresca
    # cada 5 min (ttl=300); al cambiar, Streamlit recreaba el widget y borraba el TC escrito a mano.
    if "f_tc" not in st.session_state:
        st.session_state["f_tc"] = round(float(live_usd_rate), 4)

    def _tc_a_mercado():
        st.session_state["f_tc"] = round(float(get_live_usd()), 4)

    with _exp_op:
        st.caption(f"2. Se registrará en la cartera de: {active_username}")
        st.button(f"Usar TC de mercado ({float(live_usd_rate):.4f})", on_click=_tc_a_mercado,
                  key="btn_tc_mercado", use_container_width=True,
                  help="Carga el USD/MXN de Yahoo Finance. Para que tu costo cuadre, escribe el TC real de tu conversión.")
        with st.form("form_nueva_compra"):
            f_tipo_op = st.selectbox("Tipo de Operación", ["COMPRA", "VENTA"])
            f_ticker = st.text_input("Activo (Ticker)", value=val_t)
            f_clase = st.selectbox("Clase de Activo", ["ACCION", "ETF", "FIBRA/REIT", "CRIPTO"])
            f_plat = st.selectbox("Plataforma", ["GBM_SIC", "GBM_USA", "BINANCE", "BINGX", "BITSO"])
            f_moneda = st.selectbox("Moneda", ["MXN", "USD"], index=1 if val_m == "USD" else 0,
                                    help="Se detecta sola al validar el ticker. En MXN no se aplica tipo de cambio.")
            # Escalas alineadas con las columnas NUMERIC: títulos 8 (cripto fraccional), precio 6, comisión/IVA 4.
            f_titulos = st.number_input("Títulos / Fracción", min_value=0.0, format="%.8f", step=0.0001)
            f_precio = st.number_input("Precio Unitario", min_value=0.0, value=val_p, format="%.4f", step=1.0)
            f_comision = st.number_input("Comisión", min_value=0.0, format="%.4f", step=0.01,
                                         help="En la moneda de la operación. Incluye comisiones de conversión si quieres verlas en Fricción Financiera.")
            f_iva = st.number_input("IVA", min_value=0.0, format="%.4f", step=0.01)
            f_tc = st.number_input("Tipo de Cambio", min_value=1.0, format="%.4f", step=0.0001, key="f_tc",
                                   help="Pesos por dólar que realmente pagaste en tu conversión (no se reemplaza solo).")
            f_fecha = st.date_input("Fecha", value=hoy_mx(), max_value=hoy_mx())   # fecha de CDMX, no la del servidor (UTC)
            
            if st.form_submit_button("Ejecutar Operación", use_container_width=True):
                f_ticker_clean = sanitize_ticker(f_ticker)
                if f_ticker_clean and f_titulos > 0 and f_precio > 0:
                    # Precisión financiera: aritmética en Decimal con las mismas escalas que las columnas NUMERIC.
                    d_titulos, d_precio = dinero_exacto(f_titulos, 8), dinero_exacto(f_precio, 6)
                    d_comision, d_iva = dinero_exacto(f_comision, 4), dinero_exacto(f_iva, 4)
                    tc_efectivo = Decimal(1) if f_moneda == "MXN" else dinero_exacto(f_tc, 6)   # Sprint 0 · FX: lo que ya está en MXN no se reconvierte
                    valor_bruto_mxn = d_titulos * d_precio * tc_efectivo
                    costos_mxn = (d_comision + d_iva) * tc_efectivo
                    if f_tipo_op == "COMPRA": total_mxn = dinero_exacto(valor_bruto_mxn + costos_mxn); imp_caja = -total_mxn; t_fin = d_titulos
                    else: total_mxn = dinero_exacto(valor_bruto_mxn - costos_mxn); imp_caja = total_mxn; t_fin = -d_titulos

                    ts_id = datetime.now().timestamp()
                    with db_conn() as conn, conn.cursor() as cur:
                        cur.execute("INSERT INTO transactions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (f"TXN-{ts_id}", active_client_id, datetime.now().isoformat(), str(f_fecha), f_tipo_op, f_ticker_clean, f_clase, f_plat, f_moneda, t_fin, d_precio, d_comision, d_iva, tc_efectivo, total_mxn))
                        cur.execute("INSERT INTO cash_movements VALUES (%s,%s,%s,%s,%s,%s)", (f"CMV-{ts_id}", active_client_id, str(f_fecha), f_tipo_op, f"{f_tipo_op} {f_ticker_clean}", imp_caja))
                    st.session_state["val_ticker"] = ""; st.session_state["val_price"] = 0.0; st.session_state["val_moneda"] = ""
                    st.success(f"{f_tipo_op} de {f_ticker_clean} registrada exitosamente."); st.rerun()
                else: st.error("Verifica el Ticker, Títulos y Precio.")

# 5.2 P0-B · REGISTRO DE MOVIMIENTOS (depósitos y retiros) para todos los perfiles.
#   · Cliente: el destino es SIEMPRE su propio user_id de sesión (no hay selector que manipular).
#   · Admin: elige el cliente destino; la elección se revalida contra la tabla users al guardar.
def destino_registro_caja(es_admin_flag, uid_sesion, uid_elegido, usuarios_validos):
    if not es_admin_flag:
        return uid_sesion
    return uid_elegido if uid_elegido in usuarios_validos else None

def registrar_movimiento_caja(uid_destino, tipo, concepto, monto, fecha):
    """DEPOSITO positivo / RETIRO negativo: misma convención de signo que el resto de la Terminal."""
    monto_abs = abs(dinero_exacto(monto))   # NUMERIC(18,2): centavos exactos
    monto_final = monto_abs if tipo == "DEPOSITO" else -monto_abs
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO cash_movements (id, user_id, fecha, tipo, concepto, monto_mxn) VALUES (%s, %s, %s, %s, %s, %s)",
                    (f"CMV-TES-{uuid.uuid4().hex}", uid_destino, str(fecha), tipo, concepto, monto_final))

_ultimo_caja = str(cash_df["fecha"].max()) if not cash_df.empty else "sin movimientos"
with _exp(SB_DEP, f"Depósito o retiro `{_ultimo_caja}`", ":material/account_balance_wallet:"):
    if st.session_state.get("flash_caja"):
        st.success(st.session_state.pop("flash_caja"))
    usuarios_validos = dict(zip(all_users["user_id"], all_users["username"]))
    with st.form("form_nuevo_deposito", clear_on_submit=True):
        if ES_ADMIN:
            opciones_destino = list(usuarios_validos.keys())
            c_destino = st.selectbox("Registrar a nombre de", opciones_destino,
                                     index=opciones_destino.index(active_client_id) if active_client_id in opciones_destino else 0,
                                     format_func=lambda u: usuarios_validos.get(u, u),
                                     help="Modo Admin: elige el cliente al que se le registra el movimiento.")
        else:
            c_destino = user_id
            st.caption(f"Se registrará en tu cuenta: {active_username}")
        c_tipo_op = st.selectbox("Tipo de Movimiento", ["DEPOSITO", "RETIRO"])
        f_concepto = st.text_input("Concepto", placeholder="Ej: Fondeo DCA", max_chars=120)
        f_monto = st.number_input("Monto (MXN)", min_value=1.0, step=500.0)
        f_dep_fecha = st.date_input("Fecha de Registro", value=hoy_mx(), max_value=hoy_mx())   # fecha de CDMX
        if st.form_submit_button("Registrar Movimiento", use_container_width=True):
            uid_destino = destino_registro_caja(ES_ADMIN, user_id, c_destino, usuarios_validos)
            if not uid_destino:
                st.error("El cliente elegido ya no existe. Recarga la página.")
            else:
                try:
                    registrar_movimiento_caja(uid_destino, c_tipo_op, (f_concepto or "").strip() or c_tipo_op.title(), f_monto, f_dep_fecha)
                    quien = "" if uid_destino == user_id else f" a {usuarios_validos.get(uid_destino, uid_destino)}"
                    st.session_state["flash_caja"] = f"{c_tipo_op.title()} de ${f_monto:,.2f} registrado{quien}."
                    st.rerun()
                except psycopg2.Error:
                    log_app.exception("Registro de caja · no se pudo guardar")
                    st.error("No se pudo registrar el movimiento. Intenta de nuevo.")

# ==========================================
# 6. CARGA DE DATOS Y MATEMÁTICAS
# ==========================================
# tx_df y cash_df ya se cargaron una sola vez en la sección 5 (cargar_tablas_terminal); todo escritura hace st.rerun().

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

_MACRO_TICKERS = ("USDMXN=X", "EURMXN=X", "GBPMXN=X", "^GSPC", "^NDX", "^DJI", "GC=F", "BTC-USD")

@st.cache_data(ttl=300, max_entries=200, show_spinner=False)
def _cierres_30d(simbolos):
    """Cierres de 1 mes por símbolo de Yahoo (+ macro/FX). Solo datos de mercado: la caché se comparte entre
    clientes sin exponer nada personal (el costo promedio de respaldo se aplica fuera, en get_prices_and_sparklines)."""
    todos = list(dict.fromkeys(tuple(simbolos) + _MACRO_TICKERS))
    try:
        data = yf.download(todos, period="1mo", progress=False)
    except Exception:
        data = pd.DataFrame()
    return {sym: _serie_cierre(data, sym) for sym in todos}

def get_prices_and_sparklines(tickers, fallback):
    cierres = _cierres_30d(tuple(sorted({_yf_symbol(t) for t in (tickers or [])})))
    vacia = pd.Series(dtype=float)

    def get_latest(symbol):
        s = cierres.get(symbol, vacia)
        try: return float(s.iloc[-1]) if not s.empty else 0.0
        except Exception: return 0.0

    usd = get_latest("USDMXN=X") or 18.50
    # Sprint 0 · FX: pesos por unidad de cada moneda de cotización
    fx_mxn = {"MXN": 1.0, "USD": usd}
    _gbp, _eur = get_latest("GBPMXN=X"), get_latest("EURMXN=X")
    if _gbp: fx_mxn.update({"GBP": _gbp, "GBp": _gbp / 100.0, "GBX": _gbp / 100.0})   # LSE cotiza a veces en peniques
    if _eur: fx_mxn["EUR"] = _eur
    pxs_mxn, pxs_usd, spark_data = {}, {}, {}
    for t in (tickers or []):
        try:
            yf_symbol = _yf_symbol(t)
            raw_usd_series = cierres.get(yf_symbol, vacia)
            if raw_usd_series.empty:
                pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark_data[t] = [fallback.get(t, 0.0)] * 10
                continue
            factor_mxn = _factor_a_mxn(moneda_cotizacion(yf_symbol), fx_mxn, usd)   # Sprint 0 · FX
            hist_prices_mxn = (raw_usd_series * factor_mxn).tolist()
            spark_data[t] = hist_prices_mxn
            pxs_usd[t] = float(raw_usd_series.iloc[-1]) * factor_mxn / usd
            pxs_mxn[t] = hist_prices_mxn[-1] if hist_prices_mxn else fallback.get(t, 0.0)
        except Exception:
            pxs_mxn[t] = fallback.get(t, 0.0); pxs_usd[t] = 0.0; spark_data[t] = [fallback.get(t, 0.0)] * 10

    macro_data = {}
    for m in _MACRO_TICKERS:
        macro_data[m] = {"price": 0.0, "p": 0.0, "pct": 0.0}
        try:
            s = cierres.get(m, vacia)
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

_YIELD_MAXIMO = 0.25   # >25 % anual se descarta como dato corrupto (no infla el Salario Invisible)

def _yield_fraccion(inf):
    """Rendimiento anual por dividendo como FRACCIÓN (0.035 = 3.5 %), con fuentes en orden de confiabilidad."""
    def _pos(v):
        try:
            f = float(v)
            return f if np.isfinite(f) and f > 0 else None
        except (TypeError, ValueError):
            return None
    precio = _pos(inf.get("regularMarketPrice")) or _pos(inf.get("previousClose")) or _pos(inf.get("currentPrice"))
    tasa = _pos(inf.get("dividendRate")) or _pos(inf.get("trailingAnnualDividendRate"))
    candidatos = [
        (tasa / precio) if (tasa and precio) else None,   # $ por acción / precio: misma moneda, fracción pura
        _pos(inf.get("trailingAnnualDividendYield")),       # yfinance: fracción
        _pos(inf.get("yield")),                             # ETFs (fund yield): fracción
        (_pos(inf.get("dividendYield")) or 0) / 100 or None,  # yfinance >= 0.2.54: PORCENTAJE -> se divide entre 100
    ]
    return next((c for c in candidatos if c and c <= _YIELD_MAXIMO), 0.0)

@st.cache_data(ttl=86400, max_entries=50)
def get_asset_yields(tickers):
    """{ticker: fracción anual}. Sprint 0: ya no mezcla porcentajes con fracciones."""
    yields = {}
    for t in tickers:
        if t == "BTC":
            yields[t] = 0.0   # cripto no paga dividendos: sin llamada de red
            continue
        try:
            yf_sym = f"{t}.L" if t in ["ISAC", "EIMI", "XDWH", "XNAS", "NUCL"] else t
            yields[t] = float(_yield_fraccion(yf.Ticker(yf_sym).info or {}))
        except Exception:
            yields[t] = 0.0
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
    # Clase: primero el mapa curado; si el ticker no está, la clase capturada en la operación (antes caía en "Otro"
    # y el Smart DCA no lo contaba). El mapa sigue mandando para no alterar la clasificación actual.
    _clase_capturada = (tx_df.sort_values("timestamp").groupby("ticker")["clase"].last()
                        .map(lambda c: CLASE_FORMULARIO_A_ASIGNACION.get(str(c or "").upper().strip(), "Otro")).to_dict())
    summary["Clase"] = summary["ticker"].map(lambda t: ASSET_CLASS.get(t, _clase_capturada.get(t, "Otro")))
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

# Capital aportado = depósitos − retiros (lo que de verdad salió de tu bolsillo). Antes la tarjeta "Dinero de tu
# Bolsillo" mostraba total_invertido, que es el COSTO de las posiciones abiertas (sin efectivo): no cuadraba con el banco.
def aportaciones_netas(df_caja):
    if df_caja is None or df_caja.empty: return 0.0, False
    flujos = df_caja[df_caja["tipo"].isin(["DEPOSITO", "RETIRO"])]
    if flujos.empty: return 0.0, False
    monto = flujos["monto_mxn"].astype(float).abs()
    return float(np.where(flujos["tipo"] == "DEPOSITO", monto, -monto).sum()), True

capital_aportado, hay_aportaciones = aportaciones_netas(cash_df)
if not hay_aportaciones:
    capital_aportado = total_invertido   # cliente sin depósitos registrados: se muestra el costo de sus posiciones
retorno_global = (pnl_global / total_invertido) * 100 if total_invertido > 0 else 0.0
summary["ponderacion_pct"] = (summary["valor_actual"] / total_portafolio) * 100 if not summary.empty else 0.0
xirr_valor = xirr_portafolio(cash_df, total_portafolio)   # una sola vez: Modo Pro, "¿Le ganaste a CETES?" y Carta CMA

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
tt_cap = ("Depósitos menos retiros: el dinero que ha salido de tu bolsillo hacia el portafolio. "
          "Debajo se muestra cuánto costaron las posiciones que tienes hoy (sin contar el efectivo).")
tt_liq = "Dinero en efectivo listo para aprovechar oportunidades en el mercado."
tt_pnl = "Profit & Loss (Pérdidas o Ganancias Totales de tus inversiones)."

# P0-B · Jerarquía del home: (1) contexto + métricas clave, (2) gráficas, (3) detalle de movimientos al final.
# Rediseño 2026-10 · encabezado con saludo y estado de mercados (EE.UU. y México); el conteo de operaciones/movimientos
# se mudó junto a las pestañas del historial.
_MODO_PRO = st.session_state.get("modo_pro_toggle", False)
_ultimo_mov = max([str(x) for x in list(tx_df["fecha"]) + list(cash_df["fecha"]) if x] or ["—"])


def _clave_gemini():
    try: return st.secrets["GEMINI_API_KEY"]
    except Exception: return None


H_PRO = SimpleNamespace(style=style_financial_figure, cfg=plotly_config, yf_symbol=_yf_symbol, moneda=moneda_cotizacion,
                        cierres_mxn=_cierres_historicos_mxn, cierres_riesgo=_descargar_cierres_riesgo, riesgo=get_advanced_risk_metrics,
                        series_bola_nieve=series_bola_nieve, gemini=llamar_gemini, json=extraer_json_robusto, gemini_key=_clave_gemini,
                        log=log_app, asset_class=ASSET_CLASS, usd_mxn=float(usd_mxn or 18.5))


def prefs_leer(uid):
    """Preferencias de interfaz del usuario (tablero del Modo Pro). Tabla user_prefs(user_id, prefs TEXT JSON)."""
    _asegurar_tabla_prefs()
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT prefs FROM user_prefs WHERE user_id=%s", (uid,))
        fila = cur.fetchone()
    return json.loads(fila[0]) if fila and fila[0] else None


def prefs_guardar(uid, prefs):
    _asegurar_tabla_prefs()
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO user_prefs (user_id, prefs, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (user_id) DO UPDATE SET prefs = EXCLUDED.prefs, updated_at = CURRENT_TIMESTAMP", (uid, json.dumps(prefs)))


def _asegurar_tabla_prefs():
    if st.session_state.get("_tabla_prefs_ok"):
        return
    with db_conn() as conn, conn.cursor() as cur:   # tabla nueva y aislada: no toca transactions / cash_movements
        cur.execute("CREATE TABLE IF NOT EXISTS user_prefs (user_id TEXT PRIMARY KEY, prefs TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    st.session_state["_tabla_prefs_ok"] = True


H_PRO.prefs_leer, H_PRO.prefs_guardar = prefs_leer, prefs_guardar


@st.cache_data(ttl=300, max_entries=30, show_spinner=False)
def _serie_cacheada(cash_df, tx_df, total_portafolio, rf):
    """Fluidez: la serie diaria del patrimonio la usan el cuadro, la gráfica y la carta; se calcula una vez cada 5 min."""
    return series_bola_nieve(cash_df, tx_df, total_portafolio, rf)


H_PRO.series_bola_nieve = _serie_cacheada


def _sec(sid):
    """Modo Pro: el bloque se pinta dentro de su barra del acordeón. Modo sencillo: sin cambios."""
    return pro_ui.seccion(sid) if (_MODO_PRO and pro_ui is not None) else nullcontext()


def _seccion_pro(nombre, fn, *args, **kwargs):
    """Ejecuta un componente de pro_ui; si falla, la sección se omite con un aviso y el resto de la Terminal sigue."""
    if pro_ui is None:
        st.caption(f"«{nombre}» no está disponible: falta el módulo pro_ui.py.")
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as ex:
        log_app.exception("Modo Pro · %s: %s", nombre, ex)
        st.caption(f"La sección «{nombre}» no está disponible en este momento.")
        return None


if pro_ui is not None:
    st.markdown(pro_ui.CSS_PRO, unsafe_allow_html=True)
    st.markdown(pro_ui.html_encabezado(active_username, pro=_MODO_PRO), unsafe_allow_html=True)
else:   # respaldo: encabezado previo
    st.markdown(f"<div class='ap-masthead notranslate' translate='no'><div><p class='ap-eyebrow'>CMA Wealth · Private Client Terminal</p>"
                f"<h3>{html_seguro(active_username)}</h3></div></div>", unsafe_allow_html=True)

# Rediseño 2026-10 · Indicadores Pro: un solo cuadro (patrimonio + composición, gráfica con periodo y P&L / liquidez / XIRR abajo).
# Si el componente falla, se pintan las 4 tarjetas anteriores.
_kpi_pro_ok = bool(_MODO_PRO and pro_ui is not None and _seccion_pro(
    "Indicadores", pro_ui.render_kpis_pro, H_PRO, cash_df, tx_df, float(total_portafolio), float(pnl_global), float(retorno_global),
    float(capital_aportado), float(total_invertido), float(liquidez_mxn), xirr_valor, tasa_libre_riesgo(), summary))
k1, k2, k3, k4 = st.columns([1.45, 1, 1, 1]) if (_MODO_PRO and not _kpi_pro_ok) else (_CONTENEDOR_SILENCIOSO,) * 4
k1.markdown(f"<div class='metric-card metric-card--primary kpi kpi-1 notranslate' translate='no'><div class='metric-title'>Patrimonio Total <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_pat}</span></span></div><div class='metric-value'>${total_portafolio:,.2f}</div></div>", unsafe_allow_html=True)
_sub_cap = (f"Costo de posiciones: ${total_invertido:,.2f}" if hay_aportaciones
            else "Sin depósitos registrados: se muestra el costo de tus posiciones")
k2.markdown(f"<div class='metric-card kpi kpi-2 notranslate' translate='no'><div class='metric-title'>Capital Aportado <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_cap}</span></span></div><div class='metric-value'>${capital_aportado:,.2f}</div><div class='metric-subtext'>{_sub_cap}</div></div>", unsafe_allow_html=True)

if st.session_state.get("modo_pro_toggle", False):
    k3.markdown(f"<div class='metric-card kpi kpi-3 notranslate' translate='no'><div class='metric-title'>Liquidez Disponible <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_liq}</span></span></div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    c_pnl = "text-neon-green" if pnl_global >= 0 else "text-neon-red"
    k4.markdown(f"<div class='metric-card kpi kpi-4 notranslate' translate='no'><div class='metric-title'>P&L Neto Acumulado <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_pnl}</span></span></div><div class='metric-value {c_pnl}'>${pnl_global:+,.2f}</div><div class='metric-subtext {c_pnl}'>{retorno_global:+.2f}%</div></div>", unsafe_allow_html=True)
else:
    # Rediseño · "Patrimonio protagonista": un solo bloque; el patrimonio grande y un libro mayor a la derecha.
    ganancia_neta = pnl_global
    c_gan = "ap-pos" if ganancia_neta >= 0 else "ap-neg"
    texto_simple = "ganancia generada" if ganancia_neta >= 0 else "pérdida temporal"
    _tt = lambda t: f"<span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{t}</span></span>"
    st.markdown(
        f"<div class='ap-hero ap-filo notranslate' translate='no'>"
        f"<div class='izq'><p class='ap-t'>Patrimonio total {_tt(tt_pat)}</p><p class='ap-v'>${total_portafolio:,.2f}</p>"
        f"<p class='ap-s'><span class='{c_gan}'>{mxn_signo(ganancia_neta)} · {retorno_global:+.2f}%</span> {texto_simple} en tus posiciones</p></div>"
        f"<div class='der'>"
        f"<div><p class='ap-t'>Capital aportado {_tt(tt_cap)}</p><p class='ap-v'>${capital_aportado:,.2f}</p></div>"
        f"<div><p class='ap-t'>Efectivo libre {_tt(tt_liq)}</p><p class='ap-v ap-oro'>${liquidez_mxn:,.2f}</p></div>"
        f"<div><p class='ap-t'>Costo de posiciones {_tt('Lo que pagaste por las posiciones que tienes hoy, con comisiones y tipo de cambio.')}</p>"
        f"<p class='ap-v'>${total_invertido:,.2f}</p></div>"
        f"</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-card kpi kpi-3 notranslate' translate='no'><div class='metric-title'>Efectivo Libre <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>{tt_liq}</span></span></div><div class='metric-value text-neon-purple'>${liquidez_mxn:,.2f}</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-card kpi kpi-4 notranslate' translate='no'><div class='metric-title'>{texto_simple} <span class='tooltip-container' tabindex='0'>ⓘ<span class='tooltip-text'>Lo que tus inversiones han producido para ti.</span></span></div><div class='metric-value {c_gan}'>${ganancia_neta:+,.2f}</div><div class='metric-subtext {c_gan}'>{retorno_global:+.2f}% de rendimiento</div></div>", unsafe_allow_html=True)

# Rediseño 2026-10 · Modo Pro en acordeón + «Mi tablero»: los huecos se crean aquí, en el orden del usuario.
st.session_state["_acc_activo"] = False   # se vuelve True solo si esta ejecución pinta el acordeón
st.session_state["_acc_slots"] = {}
if _MODO_PRO and pro_ui is not None:
    try:
        pro_ui.preparar_acordeon(H_PRO, user_id)   # preferencias del usuario que inició sesión
    except Exception as _ex_acc:
        log_app.warning("Acordeón · se muestra sin barras: %s", _ex_acc)

# 8.1 LA BOLA DE NIEVE Y GAMIFICACIÓN
if _MODO_PRO and pro_ui is not None:   # Rediseño 2026-10 · gráfica Pro (vs índices / por activo) + calendario de dividendos
    with _sec("rend"):
        _seccion_pro("Rendimiento del portafolio", pro_ui.render_grafica_pro, H_PRO, cash_df, tx_df, total_portafolio, tasa_libre_riesgo())
    with _sec("div"):
        if not tx_df.empty:
            _seccion_pro("Calendario de dividendos", pro_ui.render_dividendos, H_PRO, tx_df, active_username)
        else:
            st.caption("Aún no hay operaciones para calcular dividendos.")
else:
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

          _bola_v2 = construir_bola_nieve_v2(cash_df, tx_df, total_portafolio, tasa_libre_riesgo(), senior=MODO_SENIOR)   # Sprint 2
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

          style_financial_figure(fig_snow, height=320, showlegend=True)
          fig_snow.update_layout(hovermode="x unified")
          fig_snow.update_yaxes(tickprefix="$")
          with st.container(key="bola_card"):   # tarjeta con filo dorado y luz (CSS .st-key-bola_card)
              if _bola_v2 is not None:   # Sprint 2 · Capital vs Valor vs CETES; si falla, se pinta la gráfica original intacta
                  fig_snow_v2, resumen_bola = _bola_v2
                  st.markdown(resumen_bola, unsafe_allow_html=True)
                  st.plotly_chart(fig_snow_v2, use_container_width=True, config=plotly_config, key="bola_nieve")
              else:
                  st.plotly_chart(fig_snow, use_container_width=True, config=plotly_config)
      else: st.info("Registra tu primer depósito en «Registro de Movimientos» (menú lateral) para ver crecer tu Bola de Nieve.")
  else: st.info("Registra tu primer depósito en «Registro de Movimientos» (menú lateral) para ver crecer tu Bola de Nieve.")

if not (_MODO_PRO and pro_ui is not None):   # en Pro el título lo pone la escalera
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

# Paleta de la racha: misma familia dorada de la portada (antes amarillo/naranja/cian)
if racha_actual == 0: color_racha, icon_racha, rango_txt = "#64748b", "circle", "Inactivo"
elif racha_actual <= 2: color_racha, icon_racha, rango_txt = "#a8883f", "spark", "Iniciador"
elif racha_actual <= 5: color_racha, icon_racha, rango_txt = "#c9a24a", "flame", "Constante"
elif racha_actual <= 11: color_racha, icon_racha, rango_txt = "#e2c575", "bolt", "Pro"
else: color_racha, icon_racha, rango_txt = "#f3e2b0", "award", "Leyenda"

hitos = [10000, 50000, 100000, 250000, 500000, 1000000, 2500000, 5000000, 10000000]
meta_actual = next((h for h in hitos if h > total_portafolio), hitos[-1])
progreso_meta = min((total_portafolio / meta_actual) * 100, 100)
faltante = max(0, meta_actual - total_portafolio)
tasa_anual = 0.10
aportacion_promedio = (ahorro_racha / racha_actual) if racha_actual > 0 else 0
if user_freq == "SEMANAL": pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 52, tasa_anual / 52
elif user_freq == "QUINCENAL": pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 24, tasa_anual / 24
else: pmt, n_periodos, r_periodo = aportacion_promedio, 5 * 12, tasa_anual / 12

# Sprint 0 · Proyección honesta (continua en la aportación):
#   · lo invertido capitaliza a tasa_anual; el efectivo (liquidez) NO rinde 10 % por estar parado;
#   · las aportaciones solo existen si hay racha activa (pmt > 0).
# Alternativa conservadora: sin racha, no proyectar rendimiento alguno -> proyeccion_5a = total_portafolio
factor_5a = (1 + r_periodo) ** n_periodos
aportes_5a = pmt * ((factor_5a - 1) / r_periodo) if (pmt > 0 and r_periodo > 0) else 0.0
proyeccion_5a = (total_activos * factor_5a) + liquidez_mxn + aportes_5a
if pmt > 0:
    txt_proyeccion = (f"Si mantienes tu racha {txt_frecuencia.lower()} de <b>${aportacion_promedio:,.0f}</b> "
                      f"y lo invertido rinde 10% anual. Tu efectivo no se capitaliza.")
else:
    txt_proyeccion = ("Sin racha activa: solo tu capital ya invertido crece al 10% anual. "
                      "No sumo aportaciones ni rendimiento a tu efectivo.")

# Rediseño · "Franja única": racha, hito y proyección en una sola franja con filo dorado.
# Modo Pro (2026-10): escalera de aportaciones; la base son tus depósitos y el rendimiento es un supuesto opcional.
if _MODO_PRO and pro_ui is not None:
    with _sec("prog"):
        _seccion_pro("Progreso y futuro", pro_ui.render_progreso_pro, cash_df, total_portafolio, capital_aportado, pmt, user_freq,
                     xirr_valor, tasa_libre_riesgo(), active_client_id)
else:
    st.markdown(
        f"<div class='ap-franja ap-filo notranslate' translate='no'>"
        f"<div><p class='ap-t'>Racha de aportación · <span style='color:{color_racha};margin-left:4px;'>{rango_txt}</span></p>"
        f"<p class='ap-v' style='color:{color_racha};'>{racha_actual}</p>"
        f"<p class='ap-s'>{txt_frecuencia.lower()} seguidas · récord {max(racha_actual, racha_maxima)} · ahorro en racha ${ahorro_racha:,.2f}</p></div>"
        f"<div><p class='ap-t'>{html_seguro(meta_nombre)} · hito ${meta_actual:,.0f}</p>"
        f"<p class='ap-v'>{progreso_meta:.1f}%</p>"
        f"<div class='ap-barra'><b style='width:{min(max(progreso_meta, 0), 100):.1f}%'></b></div>"
        f"<p class='ap-s'>Faltan <b style='color:#e6e9ef;'>${faltante:,.2f} MXN</b></p></div>"
        f"<div><p class='ap-t'>Proyección a 5 años</p><p class='ap-v'>${proyeccion_5a:,.2f}</p>"
        f"<p class='ap-s'>{txt_proyeccion}</p></div>"
        f"</div>", unsafe_allow_html=True)
if not _MODO_PRO:
    st.markdown("---")

# ==========================================
# 8.2 SPRINT 2 · TABLA DE POSICIONES PREMIUM (visible en Modo Fácil y en Modo Pro)
# ==========================================
metricas_riesgo = {}   # Sprint 3 · la llena el Módulo de Riesgo (Modo Pro) y la consume la Carta CMA
R_PRO = None          # Modo Pro · métricas de riesgo calculadas una sola vez (posiciones, riesgo, estrés y carta)
if _MODO_PRO and pro_ui is not None and not summary.empty:
    try:
        R_PRO = pro_ui.metricas_riesgo_pro(H_PRO, summary, float(total_portafolio), tasa_libre_riesgo())
    except Exception as _ex_r:
        log_app.warning("Modo Pro · métricas de riesgo: %s", _ex_r)
    if R_PRO:
        metricas_riesgo.update({"beta": R_PRO["beta"], "sharpe": R_PRO["sharpe"], "max_dd": R_PRO["max_dd"] * 100,
                                "var_95_mxn": R_PRO["var95"], "vol_anual": R_PRO["vol"]})
if _MODO_PRO and pro_ui is not None:
    with _sec("posi"):
        _seccion_pro("Tus posiciones", pro_ui.render_posiciones_pro, H_PRO, summary, (R_PRO or {}).get("vols", {}), (R_PRO or {}).get("betas", {}))
else:
    render_tabla_posiciones(summary, senior=MODO_SENIOR)
if not _MODO_PRO:
    st.markdown("---")

# ==========================================
# RAMIFICACIÓN MODO PRO vs MODO FÁCIL
# ==========================================
if st.session_state.get("modo_pro_toggle", False):
    # Rediseño 2026-10 · Modo Pro. Cada sección vive en pro_ui.py y se ejecuta aislada (_seccion_pro).
    rf_pro = tasa_libre_riesgo()
    total_friccion = float((tx_df["comision"] + tx_df["iva"]).mul(tx_df["tipo_cambio"]).sum()) if not tx_df.empty else 0.0
    with _sec("atri"):
        _seccion_pro("Rendimiento y atribución", pro_ui.render_rendimiento_pro if pro_ui else None, H_PRO, summary, tx_df, xirr_valor, rf_pro,
                     total_friccion, float(usd_mxn or 18.5))

    with _sec("radio"):
        if "ai_memory" not in st.session_state: st.session_state["ai_memory"] = {}

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

                    tec_v5 = calcular_tecnicos_v5(hist_data, current_price, low_52, high_52)
                    mem_data = st.session_state["ai_memory"].get(target_asset)
                    if mem_data and mem_data.get("src") == "local" and (time.time() - mem_data.get("ts", 0)) > V5_TTL_PLAN_B_S:
                        mem_data = None   # el Plan B cacheado expiró: se reintenta Gemini en este rerun
                    if mem_data:
                        ai_verdict = mem_data.get("v", "HOLD ESTRATÉGICO")
                        ai_rating = mem_data.get("r", 5)
                        ai_bulls = mem_data.get("bl", [])
                        ai_bears = mem_data.get("br", [])
                        ai_macro = mem_data.get("m", "")
                    else:
                        ai_verdict, ai_rating, ai_bulls, ai_bears, ai_macro = "N/A", 5, [], [], ""
                        error_api = ""
                        gemini_intentado = False
                        backend_api_key = None
                        try: backend_api_key = st.secrets["GEMINI_API_KEY"]
                        except Exception: pass

                        if backend_api_key:
                            current_time = time.time()
                            last_call = st.session_state.get("last_gemini_call", 0)
                            time_left = 10.0 - (current_time - last_call)
                            if time_left > 0:
                                # Escudo anti-baneo: se resuelve en silencio con el Plan B (no se cachea; el próximo rerun reintenta Gemini).
                                error_api = f"Escudo anti-baneo local: faltan {int(time_left)}s"
                                ai_verdict = "ERROR API"
                                # Alternativa visible (desactivada por diseño stealth):
                                # st.toast(f"Escudo Anti-Baneo activo. Espera {int(time_left)}s para un nuevo análisis.")
                            else:
                                st.session_state["last_gemini_call"] = current_time
                                gemini_intentado = True
                                try:
                                    es_accion = isinstance(pe_ratio, (int, float)) and not isinstance(pe_ratio, bool)
                                    prompt_filled = PROMPT_MAESTRO.format(
                                        fecha_hoy=datetime.now(ZONA_MX).strftime("%Y-%m-%d"),
                                        ticker=target_asset,
                                        clase=ASSET_CLASS.get(target_asset, "Acción" if es_accion else "No clasificado"),
                                        sector=ASSET_SECTOR.get(target_asset, asset_info.get("sector") or "No especificado"),
                                        current_price=_fmt_num(current_price),
                                        usd_mxn=_fmt_num(usd_mxn, "{:,.4f}"),
                                        low_52w=_fmt_num(low_52), high_52w=_fmt_num(high_52),
                                        pos_52w=_fmt_num(tec_v5["pos_52w"], "{:.0f}%"),
                                        dist_max_52w=_fmt_num(tec_v5["dist_max_52w"], "{:+.1f}%"),
                                        ma50=_fmt_num(tec_v5["ma50"]), dist_ma50=_fmt_num(tec_v5["dist_ma50"], "{:+.1f}%"),
                                        ma200=_fmt_num(tec_v5["ma200"]), dist_ma200=_fmt_num(tec_v5["dist_ma200"], "{:+.1f}%"),
                                        cambio_1y=_fmt_num(tec_v5["cambio_1y"], "{:+.1f}%"),
                                        rsi14=_fmt_num(tec_v5["rsi14"], "{:.0f}"),
                                        vol_anual=_fmt_num(tec_v5["vol_anual"], "{:.1f}%"),
                                        max_dd=_fmt_num(tec_v5["max_dd"], "{:.1f}%"),
                                        pe_ratio=_fmt_num(pe_ratio, "{:.2f}x"), eps=_fmt_num(eps, "{:.2f}"),
                                        estado_posicion=("EN CARTERA" if is_owned else "SIN POSICIÓN (candidato de observación)"),
                                        avg_cost_mxn=(_fmt_num(p_costo_prom) if is_owned else "N/A"),
                                        avg_cost_equiv=(_fmt_num(p_costo_prom / usd_mxn) if is_owned and _num_finito(usd_mxn) else "N/A"),
                                        net_return_pct=(_fmt_num(p_retorno_total_pct, "{:+.2f}%") if is_owned else "N/A"),
                                        pnl_mxn=(_fmt_num(p_retorno_total_mxn, "{:+,.2f}") if is_owned else "N/A"),
                                        portfolio_weight=_fmt_num(p_peso, "{:.2f}%"),
                                        macro_news_context=noticias_texto,
                                        fed_cpi_events="Decisiones de tasas FED y Banxico, datos de IPC/inflación global y tipo de cambio USD/MXN en seguimiento continuo.",
                                    )
                                    with st.spinner(f"Corriendo motor de Scoring V5 para {target_asset}..."):
                                        texto_ia, err_ia = llamar_gemini(prompt_filled, backend_api_key, temperature=0.2, json_mode=True, timeout=20, presupuesto_s=45)
                                    if texto_ia:
                                        parsed_response = extraer_json_robusto(texto_ia)
                                        if parsed_response and parsed_response.get("macro_synthesis"):
                                            ai_rating = _rating_seguro(parsed_response.get("rating", 5))
                                            ai_verdict = normalizar_veredicto(parsed_response.get("verdict"), ai_rating)
                                            ai_bulls = _como_lista(parsed_response.get("bull_points"), ["Puntos fuertes en evaluación."])[:4]
                                            ai_bears = _como_lista(parsed_response.get("bear_points"), ["Riesgos en evaluación."])[:4]
                                            ai_macro = str(parsed_response.get("macro_synthesis")).strip()
                                            st.session_state["ai_memory"][target_asset] = {"v": ai_verdict, "r": ai_rating, "bl": ai_bulls, "br": ai_bears, "m": ai_macro, "src": "gemini", "ts": time.time()}
                                        else:
                                            ai_verdict, error_api = "ERROR PARSEO", f"La IA no devolvió un JSON legible: {str(texto_ia)[:200]}"
                                    else:
                                        ai_verdict, error_api = "ERROR API", err_ia
                                except Exception as e:
                                    ai_verdict, error_api = "ERROR API", f"Error interno: {str(e)}"

                        if not backend_api_key or ai_verdict in ["N/A", "ERROR API", "ERROR PARSEO"]:
                            # PLAN B (stealth): el cliente ve una síntesis normal; el motivo real solo queda en los logs.
                            if error_api: log_app.warning("Motor V5 · %s -> Plan B local. Motivo: %s", target_asset, error_api)
                            elif not backend_api_key: log_app.warning("Motor V5 · GEMINI_API_KEY no configurada -> Plan B local.")
                            ai_verdict, ai_rating, ai_bulls, ai_bears, ai_macro = plan_b_local_v5(
                                target_asset, tec_v5, pe_ratio, eps, is_owned, p_peso, p_retorno_total_pct)
                            if gemini_intentado:
                                st.session_state["ai_memory"][target_asset] = {"v": ai_verdict, "r": ai_rating, "bl": ai_bulls, "br": ai_bears, "m": ai_macro, "src": "local", "ts": time.time()}

                    score_color = "#34d399" if ai_rating >= 7 else ("#d4af37" if ai_rating >= 4 else "#94a3b8")

                    # Rediseño 2026-10 · pestañas; la gráfica marca tus compras (punto dorado) sobre MA50/MA200.
                    tab_g, tab_f, tab_v, tab_n = st.tabs(["Gráfica", "Fundamentales", "Lectura V5", "Noticias"])
                    with tab_g:
                        _ficha_ok = False
                        if pro_ui is not None:
                            try:
                                _mon_graf = moneda_cotizacion(_yf_symbol(target_asset))
                                fig_ficha, _compras = pro_ui.figura_ficha_tecnica(H_PRO, hist_data, target_asset, tx_df, usd_mxn, _mon_graf)
                                with st.container(key="ficha_card"):
                                    st.plotly_chart(fig_ficha, use_container_width=True, config=plotly_config, key="ficha_graf")
                                    st.markdown("<div class='notranslate' translate='no'>" + pro_ui.html_compras_caro_barato(
                                        _compras, float(current_price), float(low_52), float(high_52)) + "</div>", unsafe_allow_html=True)
                                    st.caption(f"Precios en {_mon_graf}. «≈» = compra registrada en otra moneda, convertida con el tipo de cambio. "
                                               "Rango 52 s: dónde quedó el precio de tu compra entre el mínimo (0 %) y el máximo (100 %) de las últimas 52 semanas, medido con el rango actual.")
                                _ficha_ok = True
                            except Exception as _ex_ficha:
                                log_app.warning("Radiografía · ficha técnica %s: %s", target_asset, _ex_ficha)
                        if not _ficha_ok:   # respaldo: gráfica previa (precio + volumen)
                            fig_deep = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
                            fig_deep.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'], fill='tozeroy', mode='lines', name='Precio', line=dict(color=color_line, width=2), fillcolor=f"rgba({52 if pct_change_1y>=0 else 148}, {211 if pct_change_1y>=0 else 163}, {153 if pct_change_1y>=0 else 184}, 0.15)"), row=1, col=1)
                            fig_deep.add_trace(go.Bar(x=hist_data.index, y=hist_data['Volume'], name='Volumen', marker_color='rgba(212, 175, 55, 0.4)'), row=2, col=1)
                            style_financial_figure(fig_deep, title=f"{target_asset} | Análisis de 1 Año", showlegend=False)
                            fig_deep.update_layout(yaxis2=dict(showgrid=False, showticklabels=False))
                            st.plotly_chart(fig_deep, use_container_width=True, config=plotly_config)
                    
                    with tab_v:
                        bulls_html = "".join([f"<li style='margin-bottom:4px;'>{html_seguro(r)}</li>" for r in ai_bulls])
                        bears_html = "".join([f"<li style='margin-bottom:4px;'>{html_seguro(r)}</li>" for r in ai_bears])
                        st.markdown(
                            (
                                f"<div class='pos-box notranslate' translate='no' style='border-top: 2px solid {score_color};'>"
                                f"<div style='display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid rgba(212, 175, 55, 0.15);padding-bottom:15px;margin-bottom:15px;'>"
                                f"<div><p class='metric-title'>Lectura Cuantitativa V5 · Escenario observado</p>"
                                f"<h3 style='color:{score_color};margin:0;font-size:1.6rem;font-weight:400;font-family:\"Playfair Display\", serif;font-style:italic;'>{html_seguro(ETIQUETA_LECTURA_V5.get(ai_verdict, ai_verdict))}</h3></div>"
                                f"<div title='Puntaje de confluencia de señales (no es una calificación de compra)' style='background:transparent;color:{score_color};border:1px solid {score_color};font-weight:600;font-size:1.4rem;padding:5px 15px;border-radius:20px;display:flex;align-items:center;'>"
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
                                f"<p style='color:#e5e7eb;font-size:0.9rem;margin:0;line-height:1.6;'><i>\"{html_seguro(ai_macro)}\"</i></p></div></div>"
                            ),
                            unsafe_allow_html=True
                        )
                    with tab_n:
                        if asset_news:
                            news_html = "".join([f"<li style='margin-bottom:6px;'><a href='{html_seguro(n['link'])}' target='_blank' rel='noopener noreferrer' style='color:#d4af37; text-decoration:none;'>{html_seguro(n['title'])}</a></li>" for n in asset_news if str(n['link']).startswith(('https://', 'http://'))])
                            st.markdown(f"<div style='margin-top:15px;' class='notranslate' translate='no'><p class='metric-title'>Data Feed Inyectada al Modelo (Live News)</p><div class='pos-box'><ul style='color:#9ca3af;font-size:0.85rem;margin:0;padding-left:15px;'>{news_html}</ul></div></div>", unsafe_allow_html=True)
                        else: st.caption("Yahoo Finance no tiene noticias recientes de este activo.")
                    
                    with tab_f:
                        if is_owned:
                            ret_color_class = "pos-green" if p_retorno_total_mxn >= 0 else "pos-red"
                            st.markdown(
                                (
                                    f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'>"
                                    f"<h3 style='color:#d4af37;font-family:\"Playfair Display\", serif;font-style:italic;margin-top:0;margin-bottom:20px;font-size:1.3rem;font-weight:400;'>Tu Posición (MXN)</h3>"
                                    f"<div class='pos-row'><div><span class='pos-label'>Acciones / Títulos</span><br><span class='pos-val'>{f'{float(p_titulos):.8f}'.rstrip('0').rstrip('.')}</span></div>"
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
                            st.markdown(f"<div class='pos-box notranslate' translate='no' style='margin-top:0;'><h3 style='color:#d4af37;font-family:\"Playfair Display\", serif;font-style:italic;margin-top:0;margin-bottom:20px;font-size:1.3rem;font-weight:400;'>Estado de Cartera</h3><p style='color:#8b949e;font-size:0.85rem;'>Actualmente no posees {html_seguro(target_asset)} en tu portafolio. La lectura se muestra solo como referencia de observación.</p></div>", unsafe_allow_html=True)

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


    with _sec("riesgo"):
        if MODO_SENIOR and R_PRO:   # Sprint 2 · lectura en lenguaje llano para el modo de lectura Senior
            render_riesgo_senior(R_PRO["var95"], R_PRO["max_dd"] * 100, R_PRO["beta"])
        _seccion_pro("Riesgo", pro_ui.render_riesgo_pro if pro_ui else None, H_PRO, R_PRO, summary, float(total_portafolio))
    with _sec("estres"):
        _seccion_pro("Simulador de estrés", pro_ui.render_estres_pro if pro_ui else None, summary, (R_PRO or {}).get("betas", {}),
                     float(liquidez_mxn), float(total_portafolio))
    with _sec("cio"):
        _seccion_pro("Boletín del CIO", pro_ui.render_cio_pro if pro_ui else None, H_PRO, summary, active_client_id, tx_df, active_username)

    with _sec("dca"):
     if not summary.empty:
         # El capital se precarga con el efectivo disponible (una vez por cliente y sesión, para que el refresco de
         # cotizaciones no borre lo que escribas). Los parámetros conservan su default 60/25/15 y ahora tienen key
         # para que la Carta CMA use los mismos.
         _k_cap = f"dca_capital_{active_client_id}"
         if _k_cap not in st.session_state:
             st.session_state[_k_cap] = float(round(max(liquidez_mxn, 0.0), 2))
         c_tgt1, c_tgt2, c_tgt3, c_dca = st.columns(4)
         with c_tgt1: tgt_etf = st.number_input("Parámetro ETF (%)", min_value=0.0, max_value=100.0, value=60.0, step=1.0, key="dca_tgt_etf")
         with c_tgt2: tgt_acc = st.number_input("Parámetro Acción (%)", min_value=0.0, max_value=100.0, value=25.0, step=1.0, key="dca_tgt_acc")
         with c_tgt3: tgt_cripto = st.number_input("Parámetro Cripto (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0, key="dca_tgt_cripto")
         with c_dca: new_capital = st.number_input("Capital a distribuir (MXN)", min_value=0.0, step=500.0, key=_k_cap,
                                                   help=f"Precargado con tu efectivo disponible (${liquidez_mxn:,.2f}). "
                                                        "Cámbialo para simular otra aportación.")

         if abs((tgt_etf + tgt_acc + tgt_cripto) - 100.0) < 1e-6:
             tgt_dict = {"ETF": tgt_etf, "Acción": tgt_acc, "Cripto": tgt_cripto}
             new_tot = total_activos + new_capital
             deficits, comp_sug, actual_cls = {}, {}, {}
             for cls, tgt in tgt_dict.items():
                 c_val = float(summary.loc[summary["Clase"] == cls, "valor_actual"].sum()) if cls in summary["Clase"].values else 0.0
                 actual_cls[cls] = c_val
                 deficits[cls] = max(0, (new_tot * (tgt / 100.0)) - c_val)

             tot_def = sum(deficits.values())
             for cls in tgt_dict: comp_sug[cls] = new_capital * (deficits[cls] / tot_def) if tot_def > 0 else new_capital * (tgt_dict[cls]/100)

             # P0-B · Escenario aritmético (no es una instrucción de inversión). Tabla: hoy vs parámetro vs después.
             filas_dca = ""
             for cls, tgt in tgt_dict.items():
                 pct_hoy = (actual_cls[cls] / total_activos * 100) if total_activos > 0 else 0.0
                 pct_desp = ((actual_cls[cls] + comp_sug[cls]) / new_tot * 100) if new_tot > 0 else 0.0
                 desv = pct_hoy - tgt
                 color_desv = "#d4af37" if abs(desv) < 2 else ("#c084fc" if desv > 0 else "#94a3b8")
                 filas_dca += (f"<tr><td style='padding:8px 6px;color:#e6e9ef;'>{cls}</td>"
                               f"<td style='padding:8px 6px;text-align:right;'>${actual_cls[cls]:,.2f}</td>"
                               f"<td style='padding:8px 6px;text-align:right;'>{pct_hoy:.1f}%</td>"
                               f"<td style='padding:8px 6px;text-align:right;'>{tgt:.0f}%</td>"
                               f"<td style='padding:8px 6px;text-align:right;color:{color_desv};'>{desv:+.1f} pp</td>"
                               f"<td style='padding:8px 6px;text-align:right;color:#ffffff;font-weight:500;'>${comp_sug[cls]:,.2f}</td>"
                               f"<td style='padding:8px 6px;text-align:right;'>{pct_desp:.1f}%</td></tr>")
             fuera = summary.loc[~summary["Clase"].isin(list(tgt_dict)), "ticker"].tolist()
             nota_fuera = (f"<p class='metric-subtext' style='margin-top:10px;'>Fuera de los parámetros (clase sin asignar): "
                           f"{html_seguro(', '.join(fuera))}.</p>" if fuera else "")
             if pro_ui is not None:   # Rediseño 2026-10 · hoy / objetivo / después en barras de 100 %
                 st.markdown(pro_ui.html_dca_barras(actual_cls, tgt_dict, {c: actual_cls[c] + comp_sug[c] for c in tgt_dict}, comp_sug, new_capital),
                             unsafe_allow_html=True)
             with (pro_ui.desplegable("Tabla detallada del escenario", key="dca_tabla") if pro_ui is not None else st.expander("Tabla detallada del escenario", expanded=True)):
                 th = "padding:6px;text-align:right;font-size:0.68rem;letter-spacing:1.4px;text-transform:uppercase;color:#8b94a7;font-weight:500;"
                 st.markdown(
                     f"<div class='pos-box notranslate' translate='no' style='overflow-x:auto;'>"
                     f"<p class='metric-title'>Escenario de Distribución · Parámetros Cuantitativos</p>"
                     f"<table style='width:100%;border-collapse:collapse;font-size:0.88rem;color:#8b94a7;font-variant-numeric:tabular-nums;'>"
                     f"<tr style='border-bottom:1px solid #1c2331;'><th style='{th}text-align:left;'>Clase</th><th style='{th}'>Valor hoy</th>"
                     f"<th style='{th}'>Peso hoy</th><th style='{th}'>Parámetro</th><th style='{th}'>Desviación</th>"
                     f"<th style='{th}'>Distribución del capital</th><th style='{th}'>Peso después</th></tr>{filas_dca}</table>"
                     f"<p class='metric-subtext' style='margin-top:10px;'>Pesos calculados sobre tus posiciones invertidas "
                     f"(${total_activos:,.2f}); el efectivo entra solo a través del capital a distribuir (${new_capital:,.2f}). "
                     f"Desviación positiva = clase por encima de su parámetro.</p>{nota_fuera}</div>",
                     unsafe_allow_html=True)
         else: st.warning("Los objetivos deben sumar 100%.")

else:
    st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px;' class='notranslate' translate='no'>Tu Portafolio Simplificado</h4>", unsafe_allow_html=True)
    
    if not summary.empty:
        best_idx = summary['pnl'].idxmax()
        worst_idx = summary['pnl'].idxmin()
        best_row = summary.loc[best_idx]
        worst_row = summary.loc[worst_idx]
        
        # Rediseño · tarjetas con nombres sobrios (antes "Salario Invisible", "Empleado del Mes" y "En Recuperación")
        col_easy1, col_easy2, col_easy3 = st.columns(3)
        with col_easy1:
            st.markdown(
                f"<div class='metric-card notranslate' translate='no'><p class='ap-t'>Ingreso pasivo estimado</p>"
                f"<p class='ap-v' style='font-size:1.9rem;'>${salario_invisible:,.2f} <span style='font-size:0.95rem;color:#8b949e;font-family:Inter, sans-serif;'>MXN / año</span></p>"
                f"<p class='ap-s'>Dividendos estimados de tus posiciones actuales. Cripto no paga dividendos.</p></div>", unsafe_allow_html=True)
        with col_easy2:
            st.markdown(
                f"<div class='metric-card notranslate' translate='no'><p class='ap-t'>Mayor contribución</p>"
                f"<p class='ap-v' style='font-size:1.9rem;'>{html_seguro(best_row['ticker'])} <span class='{'ap-pos' if best_row['pnl'] >= 0 else 'ap-neg'}' style='font-size:1.05rem;font-family:Inter, sans-serif;'>{mxn_signo(best_row['pnl'])} MXN</span></p>"
                f"<p class='ap-s'>Activo con la mayor ganancia no realizada.</p></div>", unsafe_allow_html=True)
        with col_easy3:
            st.markdown(
                f"<div class='metric-card notranslate' translate='no'><p class='ap-t'>Menor contribución</p>"
                f"<p class='ap-v' style='font-size:1.9rem;'>{html_seguro(worst_row['ticker'])} <span class='{'ap-pos' if worst_row['pnl'] >= 0 else 'ap-neg'}' style='font-size:1.05rem;font-family:Inter, sans-serif;'>{mxn_signo(worst_row['pnl'])} MXN</span></p>"
                f"<p class='ap-s'>Activo con el menor resultado no realizado.</p></div>", unsafe_allow_html=True)

        st.markdown("<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; text-align:center;' class='notranslate' translate='no'>Radiografía Visual de tu Dinero</h4>", unsafe_allow_html=True)
        st.markdown("<p style='color:#64748b;font-size:0.8rem;text-align:center;'>Haz clic en el centro o en las categorías para navegar por tu portafolio.</p>", unsafe_allow_html=True)

        summary_plot = summary.copy()
        summary_plot['Clase'] = summary_plot['Clase'].fillna('Otro')
        summary_plot['Sector'] = summary_plot['Sector'].fillna('Desconocido')

        # Misma colorimetría (gris → oro → verde, sin rojo) pero en tonos sólidos, no aqua.
        ESCALA_SOL = [[0.0, "#5f6879"], [0.25, "#959dad"], [0.5, "#e2a91f"], [0.72, "#7cb82f"], [1.0, "#12a150"]]
        fig_sun = px.sunburst(summary_plot, path=['Clase', 'Sector', 'ticker'], values='valor_actual',
                              color='retorno_pct', color_continuous_scale=ESCALA_SOL, color_continuous_midpoint=0)
        style_financial_figure(fig_sun, height=520, margin=dict(t=10, b=10, l=10, r=10))
        fig_sun.update_traces(marker=dict(line=dict(color=AP_COLORS["bg"], width=1.6)),
                              insidetextfont=dict(family=AP_FONT_SANS, size=13),
                              hovertemplate="<b>%{label}</b><br>Valor: $%{value:,.2f} MXN<br>Rendimiento: %{color:+.2f}%<extra></extra>")
        fig_sun.update_coloraxes(colorbar=dict(title=dict(text="Rend. %", font=dict(color=AP_COLORS["text_muted"], size=11)), len=0.7))

        # Filo con luz en patrón: los bordes negros se encienden en orden (anillo interior → medio → exterior,
        # rebanada por rebanada). Plotly dibuja las rebanadas en ese orden, así que al hacer clic y navegar
        # el mismo patrón se aplica solo a las formas nuevas.
        _retrasos = "".join(f".st-key-sol g.slice:nth-of-type({k}) path.surface {{ animation-delay: {1.2 + k * 0.16:.2f}s; }}" for k in range(1, 61))
        st.markdown("<style>@keyframes ap-sol-filo { 0% { stroke: #050608; stroke-width: 1.6px; filter: none; } "
                    "3% { stroke: #fff4d6; stroke-width: 2.6px; filter: drop-shadow(0 0 5px rgba(233,211,154,0.95)); } "
                    "9% { stroke: #050608; stroke-width: 1.6px; filter: none; } 100% { stroke: #050608; stroke-width: 1.6px; filter: none; } } "
                    ".st-key-sol path.surface { animation: ap-sol-filo 14s ease-in-out infinite; } " + _retrasos + "</style>",
                    unsafe_allow_html=True)

        c_sol, c_lista = st.columns([1.35, 1], gap="medium", vertical_alignment="center")
        with c_sol:
            with st.container(key="sol_card"):
                st.plotly_chart(fig_sun, use_container_width=True, config=plotly_config, key="sol")
        with c_lista:
            _top = summary.sort_values("valor_actual", ascending=False)
            _max = float(_top["valor_actual"].max() or 1)
            filas_lista = "".join(
                f"<div class='fila'><span style='font-weight:600;'>{html_seguro(r['ticker'])}</span>"
                f"<span class='track'><b style='width:{float(r['valor_actual']) / _max * 100:.1f}%'></b></span>"
                f"<span style='text-align:right;'>${float(r['valor_actual']):,.2f}</span>"
                f"<span style='text-align:right;color:#8b94a7;'>{float(r['ponderacion_pct']):.1f}%</span></div>"
                for _, r in _top.iterrows())
            st.markdown(f"<div class='ap-lista ap-filo notranslate' translate='no'><p class='ap-t' style='margin-bottom:4px;'>Peso por activo</p>{filas_lista}</div>",
                        unsafe_allow_html=True)
        
    else:
        st.info("**Modo Simple Activo:** Aún no tienes activos en tu portafolio. Registra tus primeras compras en el panel lateral para ver tu Salario Invisible y tu Radiografía de inversiones.")
    st.markdown("---")

# ==========================================
# 10. HISTORIAL CONTABLE Y CAJA
# ==========================================
with _sec("hist"):
    if not _MODO_PRO:
        st.markdown(f"<br><h4 style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; font-style:italic; margin-bottom:15px; letter-spacing:1px; display:flex; align-items:center;' class='notranslate' translate='no'>{svg_icon('book', color='#d4af37', size=18)}Historial de Movimientos y Caja</h4>", unsafe_allow_html=True)
    if pro_ui is not None:   # Rediseño 2026-10 · el resumen que antes iba en el encabezado, a la derecha de las pestañas
        st.markdown(pro_ui.html_meta_historial(len(tx_df), len(cash_df), _ultimo_mov), unsafe_allow_html=True)
    tab_ops, tab_caja = st.tabs(["Historial de Transacciones", "Flujo de Caja"])

    with tab_ops:
        if not tx_df.empty and _MODO_PRO and pro_ui is not None:   # Pro: estado de cuenta agrupado por mes + buscador
            _seccion_pro("Historial", pro_ui.render_historial_pro_tx, tx_df)
        elif not tx_df.empty:
            col_f1, col_f2 = st.columns([1, 3])
            with col_f1:
                tickers_disp = ["Todos"] + sorted(tx_df["ticker"].unique().tolist())
                filtro_t = st.selectbox("Filtrar por Activo", tickers_disp, key="filtro_ticker_hist")
        
            df_mostrar_tx = tx_df[tx_df["ticker"] == filtro_t] if filtro_t != "Todos" else tx_df.copy()
            df_mostrar_tx = df_mostrar_tx.iloc[::-1]   # P0-B · lo más reciente arriba

            _tit = lambda v: (f"{abs(float(v)):.8f}".rstrip("0").rstrip(".") or "0")
            filas_tx = "".join(
                f"<tr><td>{html_seguro(r['fecha'])}</td><td><span class='ap-pill{'' if r['tipo_operacion'] == 'COMPRA' else ' gris'}'>{html_seguro(r['tipo_operacion'])}</span></td>"
                f"<td class='tk'>{html_seguro(r['ticker'])}</td><td style='color:#8b94a7;font-size:0.78rem;'>{html_seguro(r['clase'])}</td>"
                f"<td class='n'>{_tit(r['titulos'])}</td><td class='n'>${float(r['precio_unitario']):,.4f}</td>"
                f"<td class='n'>{float(r['tipo_cambio']):,.4f}</td><td class='n' style='color:#ffffff;font-weight:500;'>${float(r['total_mxn']):,.2f}</td></tr>"
                for _, r in df_mostrar_tx.iterrows())
            st.markdown("<div class='ap-tw notranslate' translate='no' style='max-height:360px;'><table><tr><th>Fecha</th><th>Tipo</th><th>Activo</th><th>Clase</th>"
                        "<th class='n'>Títulos</th><th class='n'>Precio U.</th><th class='n'>T.C.</th><th class='n'>Total MXN</th></tr>"
                        f"{filas_tx}</table></div>", unsafe_allow_html=True)
        else: 
            st.caption("Aún no tienes transacciones registradas.")

    with tab_caja:
        if not cash_df.empty and _MODO_PRO and pro_ui is not None:
            _seccion_pro("Flujo de caja", pro_ui.render_historial_pro_caja, cash_df)
        elif not cash_df.empty:
            col_c1, col_c2 = st.columns([1, 3])
            with col_c1:
                tipos_disp = ["Todos"] + sorted(cash_df["tipo"].unique().tolist())
                filtro_c = st.selectbox("Filtrar por Tipo", tipos_disp, key="filtro_tipo_caja")
            
            df_mostrar_cash = cash_df[cash_df["tipo"] == filtro_c] if filtro_c != "Todos" else cash_df.copy()
            df_mostrar_cash = df_mostrar_cash.iloc[::-1]   # P0-B · lo más reciente arriba

            filas_caja = "".join(
                f"<tr><td>{html_seguro(r['fecha'])}</td><td><span class='ap-pill{'' if float(r['monto_mxn']) >= 0 else ' gris'}'>{html_seguro(r['tipo'])}</span></td>"
                f"<td>{html_seguro(r['concepto'])}</td><td class='n {'ap-pos' if float(r['monto_mxn']) >= 0 else 'ap-neg'}'>{mxn_signo(r['monto_mxn'])}</td></tr>"
                for _, r in df_mostrar_cash.iterrows())
            st.markdown("<div class='ap-tw notranslate' translate='no' style='max-height:360px;'><table><tr><th>Fecha</th><th>Tipo</th><th>Concepto</th>"
                        f"<th class='n'>Monto MXN</th></tr>{filas_caja}</table></div>", unsafe_allow_html=True)
        else: 
            st.caption("Aún no tienes movimientos de caja registrados.")


# ==========================================
# 11. SPRINT 3 · CMA FINANCIAL LETTER (carta de banca privada, imprimible a PDF)
# ==========================================
# Antes la carta solo traía "Perfil de riesgo" con el Modo Pro encendido (metricas_riesgo lo llena ese módulo) y el
# Boletín CIO solo si se había generado: por eso a veces salía más corta. Ahora el riesgo se calcula aunque el Modo Pro
# esté apagado, y la carta suma asignación vs parámetros, detalle por posición, flujos, operaciones recientes y metodología.
_parametros_carta = {"ETF": float(st.session_state.get("dca_tgt_etf", 60.0)),
                     "Acción": float(st.session_state.get("dca_tgt_acc", 25.0)),
                     "Cripto": float(st.session_state.get("dca_tgt_cripto", 15.0))}
_friccion_carta = float((tx_df["comision"] + tx_df["iva"]).mul(tx_df["tipo_cambio"]).sum()) if not tx_df.empty else 0.0
_ctx_carta = {
    "nombre": active_username, "patrimonio": float(total_portafolio), "capital": float(capital_aportado),
    "costo_posiciones": float(total_invertido), "valor_posiciones": float(total_activos),
    "pnl": float(pnl_global), "retorno_pct": float(retorno_global), "liquidez": float(liquidez_mxn),
    "salario_invisible": float(salario_invisible), "proyeccion_5a": float(proyeccion_5a),
    "xirr": xirr_valor, "rf": tasa_libre_riesgo(), "usd_mxn": float(usd_mxn) if usd_mxn else None,
    "friccion": _friccion_carta,
    "posiciones": posiciones_para_carta(summary),
    "riesgo": metricas_riesgo or metricas_riesgo_carta(summary, float(total_portafolio), tasa_libre_riesgo()),
    "asignacion": asignacion_para_carta(summary, float(total_portafolio), _parametros_carta),
    "flujos": flujos_para_carta(cash_df), "actividad": actividad_para_carta(tx_df),
    "racha": racha_actual, "rango": rango_txt, "frecuencia": user_freq,
    "meta_nombre": meta_nombre, "meta_monto": float(meta_actual), "progreso_meta": float(progreso_meta),
    "faltante": float(faltante), "cio": st.session_state.get("cio_report"),
}
_xp_carta = None
_huella_xp = hashlib.sha256(json.dumps([round(float(total_portafolio), 0), len(tx_df), len(cash_df), str(hoy_mx()),
                                        st.session_state.get(f"cio_json_{active_client_id}"), st.session_state.get(f"pro_aporte_{active_client_id}"),
                                        st.session_state.get(f"dca_capital_{active_client_id}"), _parametros_carta, xirr_valor],
                                       default=str, sort_keys=True).encode()).hexdigest()
if _MODO_PRO and pro_ui is not None and not summary.empty and st.session_state.get("_xp_huella") == _huella_xp:
    _xp_carta = st.session_state.get("_xp_carta")   # fluidez: nada relevante cambió, se reutiliza
elif _MODO_PRO and pro_ui is not None and not summary.empty:   # datos extra de la edición Pro (gráficas, riesgo, agenda…)
    try:
        _xp_carta = pro_ui.contexto_carta_pro(H_PRO, summary, tx_df, cash_df, R_PRO, float(total_portafolio), tasa_libre_riesgo(),
                                              float(usd_mxn or 18.5), active_client_id, float(liquidez_mxn), _parametros_carta,
                                              st.session_state.get(f"cio_json_{active_client_id}"), xirr_valor)
        st.session_state["_xp_carta"], st.session_state["_xp_huella"] = _xp_carta, _huella_xp
    except Exception as _ex_xp:
        log_app.warning("Carta CMA Pro · contexto: %s", _ex_xp)
render_carta_cma(_ctx_carta, pro=_MODO_PRO, xp=_xp_carta)   # fija al final, fuera del acordeón   # dos ediciones: esencial (sencillo) y Pro

