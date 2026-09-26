"""
telegram_deeplink.py — Botón de vinculación con Deep Link (fricción cero).
Norma 2: es aditivo. No reemplaza la visualización actual del código en la sección 3.2;
se llama justo después de ella con el código devuelto por fp_generar_codigo(uid).
"""
import html
import os
import re

import streamlit as st

_CODIGO_RE = re.compile(r"^CMA-[A-Z0-9]{6}$")
_DEFAULT_BOT = "ApportafolioFP_bot"


def bot_username() -> str:
    try:
        valor = st.secrets["TELEGRAM_BOT_USERNAME"]
    except Exception:
        valor = os.environ.get("TELEGRAM_BOT_USERNAME", _DEFAULT_BOT)
    return str(valor or _DEFAULT_BOT).strip().lstrip("@")


def construir_links(codigo: str) -> tuple:
    """(deep_link tg://, respaldo https://t.me). Devuelve (None, None) si el código no es válido."""
    codigo = str(codigo or "").strip().upper()
    if not _CODIGO_RE.match(codigo):
        return None, None
    bot = bot_username()
    return f"tg://resolve?domain={bot}&start={codigo}", f"https://t.me/{bot}?start={codigo}"


def render_boton_telegram(codigo, contenedor=None) -> bool:
    """Pinta el botón dorado (tg://) y el enlace de respaldo (t.me). Devuelve False si el código es inválido."""
    destino = contenedor if contenedor is not None else st
    deep_link, web_link = construir_links(codigo)
    if not deep_link:
        return False
    deep_link, web_link = html.escape(deep_link, quote=True), html.escape(web_link, quote=True)
    destino.markdown(
        f"""
        <style>
        .tg-deep-link {{ display:flex; align-items:center; justify-content:center; width:100%; box-sizing:border-box;
            background:linear-gradient(135deg,#bf953f 0%,#e2c575 100%); color:#02050a !important;
            font-family:'Montserrat',sans-serif; font-weight:600; letter-spacing:2px; text-transform:uppercase;
            font-size:0.75rem; text-decoration:none !important; padding:12px 10px; border-radius:8px;
            margin-top:8px; transition:all 0.3s ease; box-shadow:0 6px 14px rgba(0,0,0,0.5); }}
        .tg-deep-link:hover {{ transform:translateY(-2px); box-shadow:0 10px 20px rgba(191,149,63,0.4); }}
        .tg-fallback {{ display:block; text-align:center; font-size:0.72rem; color:#8b949e; margin-top:8px; }}
        .tg-fallback a {{ color:#d4af37; text-decoration:none; }}
        </style>
        <a class="tg-deep-link notranslate" translate="no" href="{deep_link}" target="_blank" rel="noopener">Abrir Telegram y vincular</a>
        <span class="tg-fallback">¿No abrió? Usa el <a href="{web_link}" target="_blank" rel="noopener">enlace web de respaldo</a>.</span>
        """,
        unsafe_allow_html=True,
    )
    return True
