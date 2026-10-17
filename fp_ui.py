"""
fp_ui.py — «Tu dinero hoy» · rediseño Institutional Dark (tier gratuito).

Capa ADITIVA (Norma 3): no importa app.py ni cambia ninguna consulta. app.py le pasa sus propias funciones
de lectura/escritura en un dict `ctx`; si algo aquí falla, app.py vuelve a dibujar la versión anterior.

Secciones (elecciones del catálogo «Tu dinero hoy · opciones»):
  1 · Nota del día (memo con sello CMA)                    ← evaluar_inteligencia()["accion"]
  2 · Camino a la Terminal: Etapas + vista previa con candado ← evaluar_inteligencia()["semaforo"]
  3 · Hoy puedes gastar: barra de la quincena + estado de cuenta ← fp_dinero_libre
  4 · Salud financiera en tres barras + bolsas como sobres  ← calcular_anillos_salud / fp_bolsas
  5 · Registro rápido: botón flotante + hoja inferior, una línea al estilo del bot («150 tacos comida»)
  6 · Lo que viene en tarjetas horizontales + últimos movimientos
  7 · Reparto del ingreso: barra 100 % con control por destino (reusa la cascada de fp_fase4_ui)

Lenguaje (Norma 2): descriptivo y cuantitativo, sin imperativos de inversión.
"""
from __future__ import annotations

import html
import logging
import re
import unicodedata
import uuid
from datetime import timedelta

import streamlit as st

log = logging.getLogger("apportafolio.fp_ui")

ORO, ORO2, ORO3 = "#c9a24a", "#e2c575", "#f3e2b0"
POS, NEG, ACERO, GRIS = "#5fbf9a", "#b8777c", "#7fa3c9", "#9aa3b2"
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_FUENTES = {"TELEGRAM_TEXTO": "Telegram", "REGLA_AUTOMATICA": "Telegram · regla", "WEB_MANUAL": "Web",
            "WHATSAPP_TEXTO": "WhatsApp"}

_fragmento = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None) or (lambda f: f)


def _rerun_seccion():
    """Rerun solo del fragmento (la pestaña activa no se reinicia); si no hay soporte, rerun completo."""
    try:
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()


# ==========================================
# 0. ESTILOS
# ==========================================
CSS = f"""
<style>
@property --fpx-ang {{ syntax: '<angle>'; initial-value: 0deg; inherits: false; }}
@keyframes fpx-giro {{ to {{ --fpx-ang: 360deg; }} }}
@keyframes fpx-sube {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes fpx-crece {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@keyframes fpx-sello {{ to {{ transform: rotate(360deg); }} }}
@keyframes fpx-respira {{ 0%, 100% {{ box-shadow: 0 0 0 0 rgba(226,197,117,.45); }} 50% {{ box-shadow: 0 0 0 10px rgba(226,197,117,0); }} }}

.fpx {{ font-family: 'Inter', system-ui, sans-serif; color: #e6e9ef; }}
.fpx .m {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.fpx-card {{ position: relative; isolation: isolate; background: linear-gradient(180deg, #111723, #0b0f17);
  border: 1px solid #1c2331; border-radius: 16px; padding: 18px 20px; margin: 0 0 16px 0;
  animation: fpx-sube .55s cubic-bezier(.2,.7,.2,1) both; }}
.fpx-card::before {{ content: ""; position: absolute; inset: -1px; border-radius: inherit; padding: 1px; z-index: -1;
  background: conic-gradient(from var(--fpx-ang), transparent 0 68%, rgba(226,197,117,.75) 80%, rgba(255,244,214,.9) 83%, transparent 95%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
  animation: fpx-giro 7s linear infinite; pointer-events: none; }}
.fpx-card.lento::before {{ animation-duration: 11s; }}
.fpx-card:hover {{ border-color: #2a3344; }}
.fpx-t {{ color: #6b7385; font-size: .64rem; font-weight: 500; letter-spacing: 1.8px; text-transform: uppercase; margin: 0 0 6px; }}
.fpx-s {{ color: #a3a9b6; font-size: .8rem; line-height: 1.5; margin: 0; }}
.fpx-row {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
.fpx-ser {{ font-family: 'Playfair Display', Georgia, serif; font-style: italic; font-weight: 400; color: #fff; }}
.fpx-chip {{ display: inline-block; font-size: .6rem; font-weight: 500; letter-spacing: 1.3px; text-transform: uppercase;
  border: 1px solid rgba(201,162,74,.45); color: {ORO2}; border-radius: 999px; padding: 2px 9px; white-space: nowrap; }}
.fpx-chip.neg {{ border-color: rgba(184,119,124,.55); color: {NEG}; }}
.fpx-chip.pos {{ border-color: rgba(95,191,154,.5); color: {POS}; }}
.fpx-chip.ten {{ border-color: #2a3344; color: #6b7385; }}
.fpx-trk {{ height: 7px; border-radius: 4px; background: #161d2b; overflow: hidden; position: relative; }}
.fpx-trk b {{ position: absolute; inset: 0 auto 0 0; border-radius: 4px; background: linear-gradient(90deg, #8a6f33, {ORO2});
  transform-origin: left; animation: fpx-crece 1.1s cubic-bezier(.2,.7,.2,1) both; }}
.fpx-enc {{ font-family: 'Playfair Display', serif; font-style: italic; color: #fff; font-size: 2rem; margin: 0; }}
.fpx-fecha {{ color: #8b949e; font-size: .9rem; margin: 4px 0 20px; }}
.fpx-sec {{ font-family: 'Playfair Display', serif; font-style: italic; color: {ORO3}; font-size: 1.15rem; margin: 6px 0 10px; }}

/* 1 · Nota del día */
.fpx-nota-cab {{ display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {ORO};
  padding-bottom: 9px; margin-bottom: 12px; }}
.fpx-nota-tit {{ font-size: 1.45rem; line-height: 1.25; margin: 0 0 8px; text-wrap: balance; }}
.fpx-nota-txt {{ color: #cfd3db; font-size: .9rem; line-height: 1.65; margin: 0; }}
.fpx-evid {{ display: flex; flex-wrap: wrap; gap: 8px 22px; margin-top: 12px; }}
.fpx-evid div {{ display: flex; flex-direction: column; gap: 2px; }}
.fpx-evid span:first-child {{ color: #6b7385; font-size: .6rem; letter-spacing: 1.4px; text-transform: uppercase; }}
.fpx-evid span:last-child {{ color: #e6e9ef; font-size: .9rem; }}
.fpx-pie {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 14px;
  padding-top: 10px; border-top: 1px solid #1c2331; }}
.fpx-sello {{ flex-shrink: 0; }}
.fpx-sello .giro {{ transform-origin: 30px 30px; animation: fpx-sello 26s linear infinite; }}

/* 2 · Camino a la Terminal */
.fpx-etapas {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: 10px 0 8px; }}
.fpx-etapa p {{ margin: 7px 0 0; font-size: .74rem; color: #6b7385; }}
.fpx-etapa.on p {{ color: {ORO2}; }} .fpx-etapa.ok p {{ color: {POS}; }}
.fpx-etapa .fpx-trk {{ height: 6px; }}
.fpx-prev {{ position: relative; overflow: hidden; border-radius: 12px; border: 1px solid #1c2331; margin-top: 12px; background: #07090d; }}
.fpx-prev-in {{ filter: blur(3.5px) saturate(.9); opacity: .6; padding: 12px 14px; pointer-events: none; user-select: none; }}
.fpx-prev.abierta .fpx-prev-in {{ filter: none; opacity: .9; }}
.fpx-candado {{ position: absolute; inset: 0; display: grid; place-items: center; text-align: center;
  background: linear-gradient(180deg, rgba(5,6,8,.15), rgba(5,6,8,.82)); }}
.fpx-candado svg {{ margin: 0 auto 4px; display: block; }}
.fpx-crit summary {{ color: {ORO2}; font-size: .76rem; cursor: pointer; list-style: none; margin-top: 10px; }}
.fpx-crit summary::-webkit-details-marker {{ display: none; }}
.fpx-crit summary::after {{ content: ' +'; }} .fpx-crit[open] summary::after {{ content: ' −'; }}
.fpx-it {{ display: grid; grid-template-columns: 16px 1fr; gap: 8px; padding: 7px 0; border-bottom: 1px solid #161d2b; font-size: .78rem; }}
.fpx-it:last-child {{ border-bottom: 0; }}

.st-key-fpx_ir_terminal button {{ border: 1px solid rgba(201,162,74,.55) !important; background: rgba(201,162,74,.08) !important;
  color: {ORO2} !important; border-radius: 11px !important; }}
.st-key-fpx_ir_terminal button:hover {{ background: rgba(201,162,74,.16) !important; border-color: {ORO2} !important; }}

/* 3 · Hoy puedes gastar */
.fpx-stack {{ display: flex; gap: 2px; height: 16px; margin: 10px 0 9px; transform-origin: left; animation: fpx-crece 1.1s cubic-bezier(.2,.7,.2,1) both; }}
.fpx-stack div {{ height: 100%; min-width: 3px; }}
.fpx-stack div:first-child {{ border-radius: 4px 0 0 4px; }} .fpx-stack div:last-child {{ border-radius: 0 4px 4px 0; }}
.fpx-ley {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: .74rem; color: #a3a9b6; }}
.fpx-ley i {{ display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; }}
.fpx-edo {{ display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid #1c2331; font-size: .86rem; }}
.fpx-edo span:last-child {{ font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }}
.fpx-final {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-top: 12px;
  padding-top: 10px; border-top: 1px solid {ORO}; }}
.fpx-hoy {{ font-family: 'IBM Plex Mono', monospace; font-size: 2.3rem; line-height: 1; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }}

/* 4 · Salud y sobres */
.fpx-sal {{ margin-top: 11px; }}
.fpx-sobres {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; }}
.fpx-sobre {{ border: 1px solid #1c2331; border-radius: 11px; padding: 10px 12px; background: rgba(5,6,8,.35); }}

/* 6 · Lo que viene */
.fpx-carril {{ display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; padding: 2px 2px 10px; margin-bottom: 8px;
  scrollbar-width: thin; scrollbar-color: #2a3344 transparent; }}
.fpx-prox {{ flex: 0 0 158px; scroll-snap-align: start; border: 1px solid #1c2331; border-radius: 13px; padding: 11px 13px;
  background: linear-gradient(180deg, #111723, #0b0f17); animation: fpx-sube .5s ease both; }}
.fpx-prox.ing {{ border-color: rgba(95,191,154,.35); }}
.fpx-prox .d {{ color: {ORO2}; font-size: .6rem; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; }}
.fpx-prox .n {{ color: #e6e9ef; font-size: .84rem; margin: 6px 0 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.fpx-mov {{ display: grid; grid-template-columns: 1fr auto; gap: 1px 12px; padding: 9px 0; border-bottom: 1px solid #1c2331; font-size: .86rem; }}
.fpx-mov:last-child {{ border-bottom: 0; }}
.fpx-mov .c {{ color: #6b7385; font-size: .7rem; }}

/* 5 · Botón flotante + hoja inferior */
.st-key-fp_fab {{ position: fixed !important; right: max(20px, env(safe-area-inset-right)); bottom: max(22px, env(safe-area-inset-bottom));
  z-index: 1000; width: auto !important; }}
.st-key-fp_fab button {{ width: 60px; height: 60px; min-height: 60px; border-radius: 50% !important; border: 0 !important; padding: 0 !important;
  background: linear-gradient(135deg, #b9913f, #e2c575 55%, #c9a24a) !important; color: #15120b !important;
  box-shadow: 0 10px 30px rgba(0,0,0,.55), 0 0 0 1px rgba(255,244,214,.25) inset; animation: fpx-respira 3.2s ease-in-out infinite; }}
.st-key-fp_fab button p {{ font-size: 1.9rem !important; line-height: 1 !important; font-weight: 300; margin: 0; }}
.st-key-fp_fab button [data-testid="stIconMaterial"], .st-key-fp_fab button svg {{ display: none; }}
div[data-baseweb="popover"]:has(.st-key-fp_hoja) {{ position: fixed !important; inset: auto 0 0 0 !important; transform: none !important;
  display: flex; justify-content: center; z-index: 1001; }}
div[data-baseweb="popover"]:has(.st-key-fp_hoja) > div {{ width: min(620px, 100vw) !important; max-width: 100vw !important;
  border-radius: 20px 20px 0 0 !important; border: 1px solid rgba(201,162,74,.4) !important; border-bottom: 0 !important;
  background: linear-gradient(180deg, #111723, #07090d) !important; box-shadow: 0 -18px 50px rgba(0,0,0,.6) !important;
  animation: fpx-sube .35s cubic-bezier(.2,.7,.2,1) both; }}
[data-testid="stPopoverBody"]:has(.st-key-fp_hoja) {{ max-height: 82vh; overflow-y: auto; padding: 10px 18px 22px !important; }}
.fpx-asa {{ width: 44px; height: 4px; border-radius: 2px; background: #2a3344; margin: 2px auto 12px; }}
.fpx-prev-mov {{ border: 1px dashed rgba(201,162,74,.45); border-radius: 10px; padding: 9px 12px; margin: 4px 0 10px; font-size: .84rem; }}

@media (max-width: 640px) {{
  .fpx-card {{ padding: 15px 15px; border-radius: 14px; }}
  .fpx-hoy {{ font-size: 2rem; }} .fpx-nota-tit {{ font-size: 1.25rem; }}
  .fpx-enc {{ font-size: 1.6rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .fpx-card, .fpx-card::before, .fpx-trk b, .fpx-stack, .fpx-prox, .fpx-sello .giro, .st-key-fp_fab button {{ animation: none !important; }}
}}
</style>
"""


# ==========================================
# 1. UTILIDADES
# ==========================================
def _e(t):
    return html.escape(str(t if t is not None else ""))


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def dinero(v, signo=False):
    v = round(_f(v), 2)
    s = "-" if v < 0 else ("+" if signo and v > 0 else "")
    v = abs(v)
    return f"{s}${v:,.0f}" if v == int(v) else f"{s}${v:,.2f}"


def _fc(fecha):
    """17 oct"""
    try:
        return f"{fecha.day} {_MESES[fecha.month - 1]}"
    except Exception:
        return ""


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t.lower()).strip()


def _md(contenido):
    st.markdown(f"<div class='fpx notranslate' translate='no'>{contenido}</div>", unsafe_allow_html=True)


def _sello(tam=40):
    return (f"<svg class='fpx-sello' width='{tam}' height='{tam}' viewBox='0 0 60 60' aria-hidden='true'>"
            f"<circle cx='30' cy='30' r='28' fill='none' stroke='{ORO}' stroke-width='1.2'/>"
            f"<circle class='giro' cx='30' cy='30' r='24.5' fill='none' stroke='#8a6f33' stroke-width='1' stroke-dasharray='1.4 2.6'/>"
            f"<circle cx='30' cy='30' r='20' fill='none' stroke='{ORO}' stroke-width='.6' opacity='.6'/>"
            f"<text x='30' y='34.5' text-anchor='middle' font-family='Playfair Display, serif' font-style='italic' "
            f"font-size='13' fill='{ORO2}'>CMA</text></svg>")


def _candado():
    return (f"<svg width='26' height='26' viewBox='0 0 24 24' fill='none' stroke='{ORO2}' stroke-width='1.5' aria-hidden='true'>"
            f"<rect x='5' y='11' width='14' height='10' rx='2'/><path d='M8 11V8a4 4 0 0 1 8 0v3'/></svg>")


def _barra(pct, color=None):
    pct = max(0.0, min(100.0, pct))
    estilo = f"width:{max(pct, 1.5):.1f}%;" + (f"background:{color};" if color else "")
    return f"<div class='fpx-trk'><b style='{estilo}'></b></div>"


# ==========================================
# 2. INTÉRPRETE DE UNA LÍNEA (mismo criterio que el lector local del bot)
# ==========================================
_PALABRAS_INGRESO = ("me pagaron", "me pago", "cobre", "recibi", "me depositaron", "deposito", "ingreso",
                     "me dieron", "me cayo", "gane", "vendi", "sueldo", "nomina", "quincena")
_PALABRAS_SALDO = ("saldo", "tengo", "me quedan", "traigo")
_DIAS_ATRAS = (("anteayer", 2), ("antier", 2), ("ayer", 1))
_RELLENO = {"de", "en", "el", "la", "los", "las", "un", "una", "unos", "y", "a", "al", "para", "por", "con", "mi", "mis",
            "me", "pesos", "peso", "mxn", "hoy", "ayer", "antier", "anteayer", "gaste", "pague", "compre", "fue", "del",
            "k", "mil", "que", "se", "lo", "le", "pagaron", "depositaron", "dieron", "cayo", "recibi", "cobre"}
_CLAVES_CATEGORIA = (   # copia del lector local del bot (_LOCAL_CATEGORIAS)
    (("comida", "tacos", "taco", "super", "supermercado", "despensa", "oxxo", "restaurante", "cafe", "desayuno", "comer",
      "cena", "almuerzo", "walmart", "soriana", "chedraui", "mercado", "tortillas", "pizza", "antojo", "antojos",
      "hamburguesa", "tienda", "botana", "refresco"), ("Comida", "Alimentos", "Alimentación", "Supermercado", "Despensa")),
    (("uber", "didi", "pasaje", "pasajes", "transporte", "metro", "metrobus", "gasolina", "camion", "taxi",
      "estacionamiento", "caseta", "casetas", "combi", "micro"), ("Transporte", "Movilidad", "Gasolina")),
    (("renta", "alquiler", "hipoteca", "predial", "mantenimiento"), ("Renta", "Vivienda", "Hogar")),
    (("luz", "agua", "gas", "internet", "telefono", "celular", "cfe", "izzi", "telmex", "totalplay", "megacable",
      "recarga"), ("Servicios", "Hogar", "Vivienda")),
    (("spotify", "netflix", "disney", "hbo", "prime", "youtube", "icloud", "gym", "gimnasio", "suscripcion", "chatgpt",
      "claude", "apple"), ("Suscripciones", "Entretenimiento", "Servicios")),
    (("farmacia", "doctor", "medico", "medicina", "medicinas", "consulta", "dentista", "hospital", "analisis"), ("Salud",)),
    (("tarjeta", "credito", "prestamo", "deuda", "mensualidad", "coppel", "abono", "infonavit", "fonacot"),
     ("Deudas", "Pago de deudas", "Tarjetas")),
    (("cine", "bar", "fiesta", "concierto", "antro", "videojuego", "juego", "salida", "chelas", "cerveza"),
     ("Entretenimiento", "Ocio", "Diversión")),
    (("ropa", "zapatos", "tenis", "playera", "pantalon"), ("Ropa", "Compras")),
    (("escuela", "colegiatura", "curso", "libro", "libros", "universidad", "inscripcion"), ("Educación", "Educacion", "Escuela")),
)
_RE_MONTO = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|mil)?\b")


def interpretar(texto, categorias, hoy):
    """'150 tacos comida' -> {tipo, monto, categoria_id, categoria, concepto, fecha} o {'error': ...}.
    categorias: [{'categoria_id', 'nombre'}] (fp_categorias)."""
    t = _norm(texto).replace("$", " ")
    if not t:
        return {"error": "Escribe un monto y un concepto, por ejemplo «150 tacos comida»."}
    numeros = _RE_MONTO.findall(t)
    if not numeros:
        return {"error": "No encontré un monto. Ejemplo: «150 tacos comida»."}
    if len(numeros) > 1:
        return {"error": "Escribe un solo monto por registro."}
    n, mult = numeros[0]
    try:
        monto = round(float(n.replace(",", "")) * (1000 if mult else 1), 2)
    except ValueError:
        return {"error": "No pude leer el monto."}
    if not 0 < monto <= 10_000_000:
        return {"error": "El monto debe ser mayor a cero."}

    if t.startswith("+") or any(p in t for p in _PALABRAS_INGRESO):
        tipo = "INGRESO"
    elif t.startswith("=") or any(re.search(rf"\b{p}\b", t) for p in _PALABRAS_SALDO):
        tipo = "AJUSTE"
    else:
        tipo = "GASTO"
    dias_atras = next((d for w, d in _DIAS_ATRAS if re.search(rf"\b{w}\b", t)), 0)
    fecha = hoy - timedelta(days=dias_atras)
    if tipo == "AJUSTE":
        return {"tipo": tipo, "monto": monto, "categoria_id": None, "categoria": "Saldo de hoy",
                "concepto": "Saldo declarado (web)", "fecha": hoy}

    palabras = [p for p in re.sub(r"[^a-z\s]", " ", t).split() if len(p) > 1 and p not in _RELLENO]
    por_norma = {_norm(c["nombre"]): c for c in (categorias or [])}
    elegida, palabra_cat = None, None
    if tipo == "INGRESO":
        elegida = por_norma.get("ingresos")
    if not elegida:   # 1) una palabra que ES el nombre de una de tus categorías («comida»)
        for p in palabras:
            for nombre_n, c in por_norma.items():
                if nombre_n and (p == nombre_n or p == nombre_n.split()[0]) and (tipo == "INGRESO" or nombre_n != "ingresos"):
                    elegida, palabra_cat = c, p
                    break
            if elegida:
                break
    if not elegida and tipo == "GASTO":   # 2) palabras clave del bot («tacos» -> Comida)
        juntas = f" {' '.join(palabras)} "
        for claves, candidatas in _CLAVES_CATEGORIA:
            if any(f" {c} " in juntas for c in claves):
                elegida = next((por_norma[_norm(x)] for x in candidatas if _norm(x) in por_norma), None)
                if elegida:
                    break
    if not elegida:
        elegida = por_norma.get("sin clasificar") or next(
            (c for n_, c in por_norma.items() if n_ != "ingresos"), None)
    if not elegida:
        return {"error": "No tienes categorías configuradas. Configúralas en Telegram con /configurar."}
    concepto = " ".join(p for p in palabras if p != palabra_cat)[:120] or elegida["nombre"]
    return {"tipo": tipo, "monto": monto, "categoria_id": elegida["categoria_id"], "categoria": elegida["nombre"],
            "concepto": concepto, "fecha": fecha}


# ==========================================
# 3. SECCIONES
# ==========================================
def _html_nota(accion, dl, hoy):
    titulo = accion.get("titulo") or "Tu periodo, en orden"
    detalle = accion.get("detalle") or ""
    evid = "".join(f"<div><span>{_e(k)}</span><span class='m'>{_e(v)}</span></div>"
                   for k, v in (accion.get("evidencia") or [])[:3])
    pie = ""
    if dl and dl.get("proximo_ingreso"):
        pie = f"Próximo ingreso el <b class='m' style='color:{POS};'>{_fc(dl['proximo_ingreso'])}</b>"
        if dl.get("dias_restantes"):
            pie += f" · {int(dl['dias_restantes'])} días, hoy incluido"
    elif accion.get("despues"):
        pie = f"Después: {_e(accion['despues'])}"
    return (f"<div class='fpx-card'><div class='fpx-nota-cab'><span class='fpx-ser' style='font-size:1.15rem;color:{ORO3};'>"
            f"Nota del día</span><span class='m fpx-s' style='letter-spacing:1.5px;'>{hoy.day} {_MESES[hoy.month - 1].upper()}</span></div>"
            f"<p class='fpx-ser fpx-nota-tit'>{_e(titulo)}</p><p class='fpx-nota-txt'>{_e(detalle)}</p>"
            f"{f'<div class=fpx-evid>{evid}</div>' if evid else ''}"
            f"<div class='fpx-pie'><span class='fpx-s'>{pie}</span>{_sello(42)}</div></div>")


# Las 3 etapas agrupan los 5 requisitos del semáforo (fp_fase5_inteligencia). La Terminal se abre con 3 de 3,
# que equivale al estado LISTO del semáforo (todos los requisitos en OK).
_ETAPAS = (("Ordenar", ("HISTORIAL", "LIQUIDEZ")),
           ("Ahorrar", ("COLCHON", "SUPERAVIT")),
           ("Invertir", ("DEUDA",)))


def _etapas(sem):
    items = {i["clave"]: i for i in (sem or {}).get("checklist", [])}
    salida = []
    for nombre, claves in _ETAPAS:
        presentes = [items[c] for c in claves if c in items]
        ok = sum(1 for i in presentes if i["estado"] == "OK")
        salida.append({"nombre": nombre, "ok": ok, "total": len(presentes) or 1,
                       "completa": bool(presentes) and ok == len(presentes),
                       "pendientes": [i for i in presentes if i["estado"] != "OK"]})
    return salida


def _miniatura_terminal():
    """Estructura de la Terminal (sin datos reales): KPI, curva, distribución y posiciones."""
    curva = "M0 48 L40 44 L80 38 L120 40 L160 26 L200 30 L240 16 L280 18 L320 8"
    pos = "".join(f"<div class='fpx-row' style='padding:5px 0;border-top:1px solid #161d2b;font-size:.7rem;'>"
                  f"<span>{t}</span><span class='m' style='color:{c};'>{v}</span></div>"
                  for t, v, c in (("VOO", "+12.4%", POS), ("CETES", "+5.1%", POS), ("NVDA", "-2.3%", NEG)))
    return (f"<div class='fpx-prev-in'><div class='fpx-row'><div><p class='fpx-t'>Patrimonio total</p>"
            f"<p class='m' style='font-size:1.5rem;margin:0;color:#fff;'>$248,310</p></div>"
            f"<svg width='54' height='54' viewBox='0 0 42 42'><circle cx='21' cy='21' r='15' fill='none' stroke='#1c2331' stroke-width='6'/>"
            f"<circle cx='21' cy='21' r='15' fill='none' stroke='{ORO2}' stroke-width='6' stroke-dasharray='52 94' transform='rotate(-90 21 21)'/>"
            f"<circle cx='21' cy='21' r='15' fill='none' stroke='{ACERO}' stroke-width='6' stroke-dasharray='28 94' stroke-dashoffset='-52' transform='rotate(-90 21 21)'/></svg></div>"
            f"<svg viewBox='0 0 320 56' style='width:100%;height:56px;margin:6px 0;'><path d='{curva}' fill='none' stroke='{ORO2}' stroke-width='2'/>"
            f"<path d='{curva} L320 56 L0 56Z' fill='rgba(226,197,117,.12)'/></svg>{pos}</div>")


def _html_camino(sem):
    etapas = _etapas(sem)
    llevas = sum(1 for e in etapas if e["completa"])
    abierta = llevas == len(etapas)
    actual = next((e for e in etapas if not e["completa"]), None)
    barras, previas_ok = "", True
    for e in etapas:
        en_orden = e["completa"] and previas_ok   # verde solo si las etapas anteriores también están cubiertas
        previas_ok = previas_ok and e["completa"]
        clase = "ok" if en_orden else ("on" if e is actual else "")
        color = POS if en_orden else None
        barras += (f"<div class='fpx-etapa {clase}'>{_barra(100 * e['ok'] / e['total'], color)}"
                   f"<p>{'✓ ' if en_orden else ''}{e['nombre']}</p></div>")
    if abierta:
        lectura = "Las tres etapas están cubiertas. La Terminal está disponible desde la barra lateral."
    else:
        falta = actual["pendientes"][0] if actual and actual["pendientes"] else None
        lectura = (f"Etapa actual: <b style='color:{ORO2};'>{actual['nombre']}</b>"
                   + (f" · pendiente: {_e(falta['titulo'].lower())}." if falta else "."))
    texto_candado = ("<p class='fpx-ser' style='margin:0;color:%s;font-size:1.05rem;'>Private Wealth Terminal</p>" % ORO3
                     + (f"<p class='fpx-s'>Abierta · {llevas} de {len(etapas)} criterios</p>" if abierta else
                        f"<p class='fpx-s'>Se abre al cumplir {len(etapas)} de {len(etapas)} criterios · "
                        f"<b class='m' style='color:{ORO2};'>llevas {llevas}</b></p>"))
    criterios = ""
    marcas = {"OK": ("✓", POS), "PENDIENTE": ("○", ORO2), "CRITICO": ("!", NEG)}
    for e in etapas:
        criterios += f"<p class='fpx-t' style='margin:10px 0 2px;'>{e['nombre']}</p>"
        for clave in dict(_ETAPAS)[e["nombre"]]:
            it = next((i for i in sem.get("checklist", []) if i["clave"] == clave), None)
            if not it:
                continue
            mk, col = marcas.get(it["estado"], ("○", ORO2))
            criterios += (f"<div class='fpx-it'><span style='color:{col};'>{mk}</span><div><div>{_e(it['titulo'])}</div>"
                          f"<div class='fpx-s' style='font-size:.72rem;'>{_e(it['detalle'])}</div></div></div>")
    return (f"<div class='fpx-card lento'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Camino a la Terminal</p>"
            f"<span class='m fpx-s'>{llevas} de {len(etapas)}</span></div><div class='fpx-etapas'>{barras}</div>"
            f"<p class='fpx-s'>{lectura}</p>"
            f"<div class='fpx-prev{' abierta' if abierta else ''}'>{_miniatura_terminal()}"
            f"<div class='fpx-candado'><div>{'' if abierta else _candado()}{texto_candado}</div></div></div>"
            f"<details class='fpx-crit'><summary>Criterios</summary>{criterios}</details></div>")


def _html_inversiones(sem, ops):
    """Para quien ya opera en la Terminal: atajo + estado de sus cimientos (informativo, sin el candado)."""
    etapas = _etapas(sem)
    llevas = sum(1 for e in etapas if e["completa"])
    chips = "".join(f"<span class='fpx-chip {'pos' if e['completa'] else 'ten'}' style='margin:0 5px 5px 0;'>"
                    f"{'✓ ' if e['completa'] else ''}{e['nombre']}</span>" for e in etapas)
    pend = next((i for e in etapas for i in e["pendientes"]), None)
    lectura = ("Cimientos completos: el flujo personal sostiene las aportaciones." if llevas == len(etapas) else
               f"Cimientos {llevas} de {len(etapas)}" + (f" · pendiente: {_e(pend['titulo'].lower())}." if pend else "."))
    return (f"<div class='fpx-card lento' style='margin-bottom:8px;'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Tus inversiones</p>"
            f"<span class='fpx-chip pos'>Terminal activa</span></div>"
            f"<div style='display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center;margin:12px 0 10px;'>"
            f"<svg width='46' height='46' viewBox='0 0 24 24' fill='none' stroke='{ORO2}' stroke-width='1.3' aria-hidden='true'>"
            f"<path d='M3 20h18'/><path d='M5 16l4-5 4 3 6-8'/><path d='M15 6h4v4'/></svg>"
            f"<div><p class='m' style='margin:0;font-size:1.6rem;color:#fff;line-height:1;'>{ops}</p>"
            f"<p class='fpx-s' style='font-size:.74rem;'>operaciones registradas en tu portafolio</p></div></div>"
            f"<div>{chips}</div><p class='fpx-s' style='font-size:.76rem;margin-top:4px;'>{lectura}</p></div>")


def _tarjeta_inversiones(ctx, sem, ops):
    _md(_html_inversiones(sem, ops))
    ir = ctx.get("ir_terminal")
    if ir:
        with st.container(key="fpx_ir_terminal"):
            st.button("Ver mis inversiones  →", key="fpx_btn_terminal", on_click=ir, use_container_width=True,
                      help="Abre la Terminal de inversiones de este perfil.")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


def _html_periodo(dl):
    disponible, libre = _f(dl.get("disponible_hoy")), _f(dl.get("dinero_libre"))
    comp, ahorro, apart, gast = (_f(dl.get(k)) for k in ("comprometido", "ahorro_programado", "reservado_bolsas", "gastado_periodo"))
    entradas = _f(dl.get("base")) + _f(dl.get("ingresos_periodo")) + _f(dl.get("ingresos_extra"))
    hasta = _fc(dl["proximo_ingreso"]) if dl.get("proximo_ingreso") else "tu próximo ingreso"
    desde = _fc(dl["periodo_inicio"]) if dl.get("periodo_inicio") else ""
    partes = [("Comprometido", comp, ACERO), ("Ahorro e inversión", ahorro, "#5d7a99"),
              ("Apartado", apart, ORO), ("Gastado", gast, GRIS), ("Libre", max(libre, 0), POS)]
    excedente = max(-libre, 0)
    total = max(entradas, sum(v for _, v, _ in partes), 1) + excedente
    seg = "".join(f"<div style='flex:{v / total:.5f};background:{c};' title='{n}'></div>" for n, v, c in partes if v > 0)
    if excedente:
        seg += (f"<div style='flex:{excedente / total:.5f};background:repeating-linear-gradient(45deg,{NEG} 0 4px,#6e4347 4px 8px);'"
                f" title='Excedente'></div>")
    ley = "".join(f"<span><i style='background:{c};'></i>{n} <span class='m'>{dinero(v)}</span></span>"
                  for n, v, c in partes if v > 0)
    if excedente:
        ley += f"<span style='color:{NEG};'><i style='background:{NEG};'></i>Excedente <span class='m'>{dinero(excedente)}</span></span>"
    origen = "saldo declarado" if dl.get("fuente_base") == "SALDO" else "ingresos"
    filas = [(f"Entradas desde el {desde} ({origen})" if desde else "Entradas del periodo", dinero(entradas), "#e6e9ef"),
             ("Pagos comprometidos", dinero(-comp) if comp else "$0", "#e6e9ef"),
             ("Ahorro e inversión programados", dinero(-ahorro) if ahorro else "$0", "#e6e9ef"),
             ("Apartado en bolsas", dinero(-apart) if apart else "$0", "#e6e9ef"),
             ("Gasto variable", dinero(-gast) if gast else "$0", "#e6e9ef"),
             (f"Libre al {hasta}", dinero(libre), POS if libre >= 0 else NEG)]
    edo = "".join(f"<div class='fpx-edo'><span>{_e(a)}</span><span style='color:{c};'>{b}</span></div>" for a, b, c in filas)
    if disponible >= 0:
        tit_hoy, val_hoy, col_hoy = "Hoy puedes gastar", dinero(disponible), ORO2
    else:
        tit_hoy, val_hoy, col_hoy = "Hoy, por encima del presupuesto", dinero(-disponible, signo=True), NEG
    sub = (f"Presupuesto de hoy <span class='m'>{dinero(dl.get('presupuesto_hoy'))}</span> · gastado hoy "
           f"<span class='m'>{dinero(dl.get('gastado_hoy'))}</span>")
    nota = ""
    if libre < 0:
        nota = (f"<p class='fpx-s' style='margin-top:10px;color:{NEG};'>El gasto del periodo está {dinero(-libre)} por encima "
                f"de lo que cubren las entradas hasta el {hasta}.</p>")
    return (f"<div class='fpx-card'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Tu periodo</p>"
            f"<span class='m fpx-s'>{dinero(entradas)}</span></div><div class='fpx-stack'>{seg}</div>"
            f"<div class='fpx-ley'>{ley}</div><div style='margin-top:12px;'>{edo}</div>"
            f"<div class='fpx-final'><div><p class='fpx-t' style='color:{ORO2};margin:0 0 4px;'>{tit_hoy}</p>"
            f"<p class='fpx-s' style='font-size:.74rem;'>{sub}</p></div>"
            f"<span class='fpx-hoy' style='color:{col_hoy};'>{val_hoy}</span></div>{nota}</div>")


def _html_salud(a, registro_hoy, dl, sobres_html=None):
    filas = [
        ("Registro", a["registro"], f"{a['dias_registro']} de 7 días" + (" · hoy registrado" if registro_hoy else "")),
        ("Presupuesto", a["presupuesto"],
         "por encima del periodo" if a["presupuesto"] == 0 and _f(dl.get("dinero_libre")) < 0
         else f"{a['presupuesto'] * 100:.0f}% al ritmo del calendario"),
        ("Ahorro", a["ahorro"], f"{dinero(a['apartado'])} de {dinero(a['meta_ahorro'])} de referencia"),
    ]
    barras = "".join(f"<div class='fpx-sal'><div class='fpx-row'><span style='font-size:.84rem;'>{n}</span>"
                     f"<span class='fpx-s' style='font-size:.72rem;'>{d}</span></div>"
                     f"<div style='margin-top:5px;'>{_barra(v * 100)}</div></div>" for n, v, d in filas)
    menor = min(filas, key=lambda x: x[1])
    nivel = {"Sólido": "pos", "En construcción": "", "Prioridad": "neg"}.get(a.get("nivel"), "")
    tt = ("Puntaje = 35% presupuesto al ritmo + 35% ahorro (referencia: 10% de las entradas del periodo) "
          "+ 30% registro (días con movimientos en los últimos 7). Se compara contra ti mismo; no es un buró de crédito.")
    return (f"<div class='fpx-card lento' title='{_e(tt)}'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Salud financiera</p>"
            f"<span class='fpx-chip {nivel}'>{_e(a.get('nivel', ''))}</span></div>"
            f"<p style='margin:6px 0 2px;'><span class='m' style='font-size:2.2rem;color:#fff;'>{a['score']}</span>"
            f"<span class='fpx-s'> / 100</span></p>{barras}"
            f"<p class='fpx-s' style='margin-top:12px;font-size:.74rem;'>Componente con más margen: "
            f"<b style='color:{ORO2};'>{menor[0].lower()}</b>.</p>"
            + ("" if sobres_html is None else
               f"<div style='border-top:1px solid rgba(201,162,74,.5);margin:14px 0 10px;'></div>"
               f"<p class='fpx-t'>Tus sobres</p>{sobres_html}")
            + "</div>")


def _html_sobres(bolsas):
    paleta = (ORO, ACERO, POS, "#5d7a99", ORO2)
    out = ""
    for k, b in enumerate(bolsas):
        aporte, saldo, objetivo = _f(b.get("aporte_periodo")), _f(b.get("saldo_acumulado")), _f(b.get("monto_objetivo"))
        c = paleta[k % len(paleta)]
        meta = (f"<p class='fpx-s' style='font-size:.7rem;'>meta <span class='m'>{dinero(objetivo)}</span></p>"
                f"<div style='margin-top:6px;'>{_barra(saldo / objetivo * 100 if objetivo else 0, c)}</div>"
                if objetivo else "<p class='fpx-s' style='font-size:.7rem;'>sin meta</p>")
        out += (f"<div class='fpx-sobre' style='border-top:2px solid {c};'><p class='fpx-t'>{_e(b.get('nombre'))}</p>"
                f"<p class='m' style='margin:0;font-size:1.05rem;'>{dinero(saldo)}</p>"
                f"<p class='fpx-s' style='font-size:.7rem;'><span class='m'>{dinero(aporte)}</span> por periodo</p>{meta}</div>")
    return f"<div class='fpx-sobres'>{out}</div>"


def _html_proximos(eventos):
    tarjetas = ""
    for k, e in enumerate(eventos):
        ing = e["tipo_movimiento"] == "INGRESO"
        fecha = e["fecha"]
        tarjetas += (f"<div class='fpx-prox{' ing' if ing else ''}' style='animation-delay:{k * 60}ms;'>"
                     f"<div class='d'>{_DIAS[fecha.weekday()]} {_fc(fecha)}</div><div class='n'>{_e(e['nombre'])}</div>"
                     f"<div class='m' style='color:{POS if ing else '#e6e9ef'};'>{dinero(e['monto'] if ing else -_f(e['monto']), signo=ing)}</div></div>")
    return f"<div class='fpx-carril'>{tarjetas}</div>"


def _html_movs(movs):
    out = ""
    for m in movs:
        if m["tipo"] == "AJUSTE":
            titulo, monto, col = "Saldo declarado", f"= {dinero(m['monto'])}", ORO2
        elif m["tipo"] == "INGRESO":
            titulo, monto, col = m["concepto"] or m["categoria"] or "Ingreso", dinero(m["monto"], signo=True), POS
        else:
            titulo, monto, col = m["concepto"] or m["categoria"] or "Gasto", dinero(-_f(m["monto"])), "#e6e9ef"
        sub = " · ".join(x for x in (_fc(m["fecha"]), m["categoria"] if m["tipo"] != "AJUSTE" else "",
                                     _FUENTES.get(m["fuente"], m["fuente"] or "")) if x)
        out += (f"<div class='fpx-mov'><span>{_e(titulo)}</span><span class='m' style='color:{col};'>{monto}</span>"
                f"<span class='c'>{_e(sub)}</span><span></span></div>")
    return out


# ==========================================
# 4. REGISTRO RÁPIDO (botón flotante + hoja)
# ==========================================
def _registrar_linea(ctx, r):
    token = st.session_state.setdefault("fpx_token", uuid.uuid4().hex)
    mov_id = ctx["registrar"](ctx["uid"], r["tipo"], r["monto"], r["categoria_id"], None, r["concepto"], r["fecha"], token)
    st.session_state["fpx_token"] = uuid.uuid4().hex
    if mov_id:
        etiqueta = {"GASTO": "Gasto", "INGRESO": "Ingreso", "AJUSTE": "Saldo de hoy"}[r["tipo"]]
        detalle = "" if r["tipo"] == "AJUSTE" else f" · {r['categoria']} · {r['concepto']}"
        st.session_state["fpx_ultimo"] = {"uid": ctx["uid"], "movimiento_id": mov_id,
                                          "texto": f"{etiqueta} de {dinero(r['monto'])}{detalle}"}
    return mov_id


def _hoja_registro(ctx):
    uid, hoy = ctx["uid"], ctx["hoy"]
    st.markdown("<div class='fpx-asa'></div><p class='fpx-sec' style='margin-top:0;'>Registro rápido</p>", unsafe_allow_html=True)
    ultimo = st.session_state.get("fpx_ultimo")
    if ultimo and ultimo.get("uid") == uid:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"<p class='fpx-s' style='margin-top:8px;color:{POS};'>Registrado: {_e(ultimo['texto'])}</p>",
                    unsafe_allow_html=True)
        if c2.button("Deshacer", key="fpx_deshacer", use_container_width=True):
            ctx["descartar"](uid, ultimo["movimiento_id"])
            st.session_state.pop("fpx_ultimo", None)
            st.rerun()

    with st.form("fpx_form_linea", clear_on_submit=True, border=False):
        linea = st.text_input("Una línea, como en Telegram", placeholder="150 tacos comida",
                              help="Monto + concepto (+ categoría). «+5000 sueldo» es ingreso; «saldo 3200» declara "
                                   "tu saldo de hoy; «ayer 80 uber» lo fecha ayer.")
        enviar = st.form_submit_button("Registrar", type="primary", use_container_width=True)
    if enviar:
        r = interpretar(linea, ctx["categorias"](uid), hoy)
        if "error" in r:
            st.error(r["error"])
        else:
            try:
                ok = _registrar_linea(ctx, r)
            except Exception:
                log.exception("Registro rápido")
                ok = None
                st.error("No pude guardar el movimiento. Intenta de nuevo.")
            if ok:
                st.rerun()
    st.markdown("<p class='fpx-s' style='font-size:.72rem;margin:2px 0 10px;'>Ejemplos: «150 tacos comida» · "
                "«42 pasaje» · «+5000 sueldo» · «saldo 3200» · «ayer 80 uber»</p>", unsafe_allow_html=True)

    if st.toggle("Formulario completo", key="fpx_form_completo"):
        _formulario_completo(ctx)
    imp = ctx.get("boton_importacion")
    if imp:
        try:
            imp(uid)
        except Exception:
            log.exception("Importación")


def _formulario_completo(ctx):
    uid, hoy = ctx["uid"], ctx["hoy"]
    tipo_txt = st.radio("Tipo", ["Gasto", "Ingreso", "Saldo de hoy"], horizontal=True, key="fpx_tipo",
                        label_visibility="collapsed")
    tipo = {"Gasto": "GASTO", "Ingreso": "INGRESO", "Saldo de hoy": "AJUSTE"}[tipo_txt]
    categorias = list(ctx["categorias"](uid))
    if tipo == "GASTO":
        categorias = [c for c in categorias if c["nombre"].lower() != "ingresos"]
    elif tipo == "INGRESO":
        categorias.sort(key=lambda c: c["nombre"].lower() != "ingresos")
    cuentas = ctx["cuentas"](uid)
    with st.form("fpx_form_completo_f", clear_on_submit=True, border=False):
        c1, c2 = st.columns([1, 1.4])
        monto = c1.number_input("Monto (MXN)", min_value=0.0, step=10.0, format="%.2f")
        categoria_id, concepto, fecha, cuenta_id = None, "Saldo declarado (web)", hoy, None
        if tipo != "AJUSTE":
            nombres = [c["nombre"] for c in categorias]
            elegido = c2.selectbox("Categoría", nombres, index=0 if nombres else None)
            categoria_id = next((c["categoria_id"] for c in categorias if c["nombre"] == elegido), None)
            c3, c4 = st.columns([1.4, 1])
            concepto = c3.text_input("Concepto", placeholder="Ej. tacos, uber, renta", max_chars=120)
            fecha = c4.date_input("Fecha", value=hoy, max_value=hoy, format="DD/MM/YYYY")
            if cuentas:
                nombre_cta = st.selectbox("Cuenta", ["Sin especificar"] + [c["nombre"] for c in cuentas])
                cuenta_id = next((c["cuenta_id"] for c in cuentas if c["nombre"] == nombre_cta), None)
        else:
            c2.markdown("<p class='fpx-s' style='margin-top:30px;'>El total que tienes hoy; recalibra el cálculo al centavo.</p>",
                        unsafe_allow_html=True)
        if st.form_submit_button("Registrar", use_container_width=True):
            if monto <= 0:
                st.error("Escribe un monto mayor a cero.")
            elif tipo != "AJUSTE" and not categoria_id:
                st.error("Elige una categoría.")
            else:
                token = st.session_state.setdefault("fpx_token", uuid.uuid4().hex)
                try:
                    mov = ctx["registrar"](uid, tipo, round(monto, 2), categoria_id, cuenta_id, concepto, fecha, token)
                except Exception:
                    mov = None
                    st.error("No pude guardar el movimiento. Intenta de nuevo.")
                st.session_state["fpx_token"] = uuid.uuid4().hex
                if mov:
                    st.session_state["fpx_ultimo"] = {"uid": uid, "movimiento_id": mov,
                                                      "texto": f"{tipo_txt.lower()} de {dinero(monto)}"}
                    st.rerun()


def _boton_flotante(ctx):
    pop = getattr(st, "popover", None)
    if pop is None:   # Streamlit viejo: el registro queda en línea
        with st.expander("Registro rápido", expanded=False):
            with st.container(key="fp_hoja"):
                _hoja_registro(ctx)
        return
    with st.container(key="fp_fab"):
        with st.popover("+", help="Registrar un movimiento"):
            with st.container(key="fp_hoja"):
                _hoja_registro(ctx)


# ==========================================
# 5. PANTALLA COMPLETA
# ==========================================
def render(ctx):
    """ctx: uid, nombre, viendo_otro, hoy, db_conn, y las funciones de app.py:
       dinero_libre(uid, hoy), bolsas(uid), proximos(uid, desde, hasta), ultimos(uid), categorias(uid), cuentas(uid),
       registrar(...), descartar(uid, mov_id), actividad(uid, hoy), anillos(dl, dias), inteligencia(uid, hoy),
       sin_base(uid, dl, hoy), boton_compromisos(uid), boton_bolsas(uid), boton_importacion(uid)."""
    uid, hoy = ctx["uid"], ctx["hoy"]
    st.markdown(CSS, unsafe_allow_html=True)

    dl = ctx["dinero_libre"](uid, hoy)          # si falla, app.py captura y vuelve a la versión anterior
    try:
        intel = ctx["inteligencia"](uid, hoy)
    except Exception:
        log.exception("Inteligencia FP")
        intel = {"accion": {}, "semaforo": {"checklist": []}}

    sin_base = not dl or dl.get("estado") == "SIN_BASE"
    sem = intel.get("semaforo") or {"checklist": []}
    ops = int(((intel.get("metricas") or {}).get("operaciones_terminal")) or 0)
    invierte = ops > 0 or sem.get("estado") == "VIP"

    # Dos columnas continuas: cada lado apila sus tarjetas, así no queda hueco entre filas de alturas distintas.
    col_izq, col_der = st.columns([1.5, 1], gap="medium")
    with col_izq:
        _md(_html_nota(intel.get("accion") or {}, dl, hoy))
        if sin_base:
            ctx["sin_base"](uid, dl, hoy)
        else:
            _md(_html_periodo(dl))
            if dl.get("estado") == "SIN_PROXIMO_INGRESO":
                st.caption("Sin próximo ingreso configurado: el cálculo usa 30 días. Se ajusta en Telegram con /configurar.")
    with col_der:
        if invierte:
            _tarjeta_inversiones(ctx, sem, ops)
        else:
            _md(_html_camino(sem))
        _panel_salud_sobres(ctx, None if sin_base else dl)

    # Lo que viene
    c_t, c_b = st.columns([10, 1])
    c_t.markdown("<p class='fpx-sec notranslate' translate='no'>Lo que viene</p>", unsafe_allow_html=True)
    with c_b:
        if ctx.get("boton_compromisos"):
            ctx["boton_compromisos"](uid)
    hasta = (dl.get("proximo_ingreso") if dl else None) or (hoy + timedelta(days=30))
    eventos = ctx["proximos"](uid, hoy, hasta + timedelta(days=1))
    if eventos:
        _md(_html_proximos(eventos))
    else:
        st.caption("Sin pagos fijos ni ingresos programados. Se configuran en Telegram con /configurar.")

    _render_movimientos(ctx)
    _boton_flotante(ctx)


def _panel_salud_sobres(ctx, dl):
    """Opción A del combo: salud (puntaje + 3 barras) y, bajo una línea dorada, los sobres; todo en un cuadro."""
    uid, hoy = ctx["uid"], ctx["hoy"]
    c_t, c_b = st.columns([6, 1])
    c_t.markdown("<p class='fpx-sec notranslate' translate='no' style='margin-top:0;'>Salud y sobres</p>", unsafe_allow_html=True)
    with c_b:
        if ctx.get("boton_bolsas"):
            ctx["boton_bolsas"](uid)
    try:
        bolsas = ctx["bolsas"](uid)
    except Exception:
        log.exception("Bolsas")
        bolsas = []
    sobres = (_html_sobres(bolsas) if bolsas else
              "<p class='fpx-s' style='font-size:.74rem;'>Aún no hay sobres. Desde Telegram: /apartar 500 colchón.</p>")
    if dl:
        try:
            dias, registro_hoy = ctx["actividad"](uid, hoy)
            _md(_html_salud(ctx["anillos"](dl, dias), registro_hoy, dl, sobres))
            return
        except Exception:
            log.exception("Salud financiera")
    _md(f"<div class='fpx-card lento'><p class='fpx-t'>Tus sobres</p>{sobres}</div>")


@_fragmento
def _render_movimientos(ctx):
    uid = ctx["uid"]
    st.markdown("<p class='fpx-sec notranslate' translate='no'>Últimos movimientos</p>", unsafe_allow_html=True)
    movs = ctx["ultimos"](uid)
    if not movs:
        st.caption("Aún no hay movimientos. El botón + registra uno en una línea («42 pasaje»), igual que el bot de Telegram.")
        return
    _md(f"<div class='fpx-card lento' style='padding:6px 18px;'>{_html_movs(movs)}</div>")
    pop = getattr(st, "popover", None)
    cont = pop("Quitar un movimiento", use_container_width=False) if pop else st.expander("Quitar un movimiento")
    with cont:
        opciones = {m["movimiento_id"]: f"{_fc(m['fecha'])} · {m['concepto'] or m['categoria'] or m['tipo'].title()} · {dinero(m['monto'])}"
                    for m in movs}
        elegido = st.selectbox("Movimiento", list(opciones), format_func=opciones.get, key="fpx_quitar_sel")
        if st.button("Quitar", key="fpx_quitar_btn", help="Lo descarta de tus números; no se borra del historial."):
            ctx["descartar"](uid, elegido)
            st.rerun()


# ==========================================
# 6. REPARTO DEL INGRESO · barra 100 % con control por destino
# Reusa la lógica de fp_fase4_ui (reglas, automáticos, simulación y guardado); solo cambia la interfaz.
# ==========================================
_COLORES_DESTINO = {"COMPROMISOS": ACERO, "COLCHON": "#5d7a99", "METAS": ORO, "INVERSION": ORO2, "LIBRE": POS}
_MODOS_UI = {"AUTO": "Automático", "PORCENTAJE": "%", "MONTO_FIJO": "Monto fijo", "OFF": "Sin asignar"}


@_fragmento
def ui_reparto(db_conn, uid):
    import fp_fase4_ui as f4   # módulo hermano; si no está, app.py usa la interfaz anterior
    f4._mostrar_flash()
    if not f4._esquema_ok(db_conn):
        return
    hoy = f4._hoy()
    frecuencia = f4._frecuencia_usuario(db_conn, uid)
    reglas, ya_guardadas = f4._cargar_reglas(db_conn, uid)
    autos, avisos, hasta = f4._montos_automaticos(db_conn, uid, hoy, frecuencia)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("<p class='fpx-sec notranslate' translate='no'>Reparto de tu próximo ingreso</p>"
                "<p class='fpx-s' style='margin:-4px 0 12px;'>El ingreso baja en cascada: compromisos, colchón, metas e "
                "inversión; lo que queda es libre.</p>", unsafe_allow_html=True)
    ingreso = st.number_input("Monto del próximo ingreso (MXN)", min_value=0.0, step=500.0, format="%.2f",
                              value=f4._ultimo_ingreso(db_conn, uid), key=f"fpx_rep_ing_{uid}")
    caja = st.empty()   # la barra se dibuja arriba de los controles, con los valores ya leídos

    nuevas = []
    seg = getattr(st, "segmented_control", None)
    for r in reglas:
        d = r["destino"]
        if d == "LIBRE":
            nuevas.append({**r, "modo": "RESTO", "activa": True})
            continue
        k_modo, k_val = f"fpx_rep_modo_{uid}_{d}", f"fpx_rep_val_{uid}_{d}"
        st.session_state.setdefault(k_modo, "OFF" if not r["activa"] else (r["modo"] if r["modo"] in _MODOS_UI else "AUTO"))
        st.session_state.setdefault(k_val, float(r["valor"]))
        c_n, c_m, c_v = st.columns([1.1, 2.3, 1.2], vertical_alignment="center")
        c_n.markdown(f"<div class='fpx' style='font-size:.88rem;'><i style='display:inline-block;width:9px;height:9px;"
                     f"border-radius:2px;background:{_COLORES_DESTINO[d]};margin-right:7px;'></i>{_e(r['etiqueta'])}</div>",
                     unsafe_allow_html=True)
        with c_m:
            if seg:
                modo = seg(r["etiqueta"], list(_MODOS_UI), format_func=_MODOS_UI.get, key=k_modo,
                           label_visibility="collapsed") or "AUTO"
            else:
                modo = st.selectbox(r["etiqueta"], list(_MODOS_UI), format_func=_MODOS_UI.get, key=k_modo,
                                    label_visibility="collapsed")
        with c_v:
            if modo == "AUTO":
                st.markdown(f"<div class='fpx m' style='color:#a3a9b6;font-size:.86rem;'>{dinero(autos.get(d, 0))}</div>",
                            unsafe_allow_html=True)
                valor = float(st.session_state.get(k_val) or 0)
            elif modo == "OFF":
                st.markdown("<div class='fpx fpx-s'>—</div>", unsafe_allow_html=True)
                valor = float(st.session_state.get(k_val) or 0)
            else:
                valor = st.number_input("Valor", min_value=0.0, step=1.0 if modo == "PORCENTAJE" else 100.0, format="%.2f",
                                        key=k_val, label_visibility="collapsed",
                                        help="Porcentaje del ingreso" if modo == "PORCENTAJE" else "Pesos por ingreso")
        nuevas.append({**r, "modo": "AUTO" if modo == "OFF" else modo, "valor": max(0.0, float(valor or 0)),
                       "activa": modo != "OFF"})

    pct_total = sum(r["valor"] for r in nuevas if r["activa"] and r["modo"] == "PORCENTAJE")
    sim = f4._simular_cascada(ingreso, nuevas, autos)
    with caja.container():
        _md(_html_reparto(sim, ingreso, hasta))
    for aviso in avisos:
        st.caption(aviso)
    if pct_total > 100:
        st.caption(f"Los porcentajes suman {pct_total:.0f}%: la cascada asigna en orden y el último destino queda corto.")
    if ingreso > 0 and sim and sim[0]["faltante"] > 0.005:
        st.caption(f"Este ingreso no cubre los compromisos del periodo: faltan {dinero(sim[0]['faltante'])}.")

    c1, c2 = st.columns(2)
    guardar = c1.button("Guardar reglas", key=f"fpx_rep_guardar_{uid}", use_container_width=True)
    registrar = c2.button("Guardar y registrar este reparto", key=f"fpx_rep_reg_{uid}", type="primary",
                          use_container_width=True, disabled=ingreso <= 0)
    if guardar or registrar:
        try:
            f4._guardar_reglas(db_conn, uid, nuevas)
            if registrar:
                f4._registrar_reparto(db_conn, uid, ingreso, sim, hoy)
        except Exception:
            log.exception("Reparto")
            st.error("No pude guardar. Intenta de nuevo en un momento.")
            return
        f4._flash("Reparto registrado." if registrar else "Reglas de reparto guardadas.")
        _rerun_seccion()
    if not ya_guardadas:
        st.caption("Reglas de referencia: se aplican cuando las guardas.")
    f4._render_historial(db_conn, uid)


def _html_reparto(sim, ingreso, hasta):
    total = max(_f(ingreso), 1.0)
    seg = "".join(f"<div style='flex:{s['asignado'] / total:.5f};background:{_COLORES_DESTINO[s['destino']]};'></div>"
                  for s in sim if s["asignado"] > 0)
    filas = ""
    for s in sim:
        pct = s["asignado"] / total * 100 if _f(ingreso) > 0 else 0
        falta = (f"<span class='fpx-s' style='font-size:.7rem;color:{NEG};'> · faltan {dinero(s['faltante'])}</span>"
                 if s["faltante"] > 0.005 else "")
        filas += (f"<div class='fpx-edo'><span><i style='display:inline-block;width:8px;height:8px;border-radius:2px;"
                  f"background:{_COLORES_DESTINO[s['destino']]};margin-right:7px;'></i>{_e(s['etiqueta'])}{falta}</span>"
                  f"<span style='color:{POS if s['destino'] == 'LIBRE' else '#e6e9ef'};'>{dinero(s['asignado'])} "
                  f"<span style='color:#6b7385;font-size:.74rem;'>{pct:.0f}%</span></span></div>")
    libre = sim[-1]["asignado"] if sim else 0.0
    return (f"<div class='fpx-card'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Simulación · automáticos hasta el "
            f"{_fc(hasta)}</p><span class='m fpx-s'>{dinero(ingreso)}</span></div>"
            f"<div class='fpx-stack' style='height:18px;'>{seg or '<div style=flex:1;background:#161d2b></div>'}</div>{filas}"
            f"<div class='fpx-final'><p class='fpx-t' style='margin:0;color:{ORO2};'>Queda libre</p>"
            f"<span class='fpx-hoy' style='font-size:1.7rem;color:{POS if libre > 0 else GRIS};'>{dinero(libre)}</span></div></div>")


def ui_planificacion(db_conn, uid):
    """Reparto (barra 100 %), Deudas (Fecha de libertad) y Metas (Tarro); si alguna falla, se usa la de fp_fase4_ui."""
    import fp_fase4_ui as f4
    tab_rep, tab_deu, tab_met = st.tabs(["Reparto del ingreso", "Deudas", "Metas"])
    with tab_rep:
        try:
            ui_reparto(db_conn, uid)
        except Exception:
            log.exception("Reparto nuevo; se usa el anterior")
            f4.ui_cascada_ingresos(db_conn, uid)
    with tab_deu:
        try:
            ui_deudas(db_conn, uid)
        except Exception:
            log.exception("Deudas nuevo; se usa el anterior")
            f4.ui_control_deudas(db_conn, uid)
    with tab_met:
        try:
            ui_metas(db_conn, uid)
        except Exception:
            log.exception("Metas nuevo; se usa el anterior")
            f4.ui_metas_aportaciones(db_conn, uid)


# ==========================================
# 7. DEUDAS · opción A «Fecha de libertad» (simulación Avalancha de fp_fase4_ui)
# ==========================================
def _mes_corto(d):
    return f"{_MESES[d.month - 1]} {d.year}"


def _html_deudas(plan, base, con_saldo, hoy, f4, pendiente=False):
    total = sum(d["saldo"] for d in con_saldo)
    if plan["completo"]:
        fecha = _mes_corto(f4._sumar_meses(hoy, plan["meses"]))
        ahorro = (base["interes"] - plan["interes"]) if base["completo"] else None
        sub = (f"Total <span class='m'>{dinero(total)}</span> · intereses <span class='m'>{dinero(round(plan['interes']))}</span>"
               + (f" · <span style='color:{POS};'><span class='m'>{dinero(round(ahorro))}</span> menos</span> que pagando solo mínimos"
                  if ahorro and ahorro > 1 else ""))
        valor, color = fecha, ORO2
    else:
        valor, color = "Sin fecha de salida", NEG
        sub = (f"Total <span class='m'>{dinero(total)}</span> · con estos pagos el saldo no se liquida en 50 años "
               f"(escenario observado con el pago extra actual).")
    mayor = max((d["saldo"] for d in con_saldo), default=1) or 1
    filas = ""
    for k, d in enumerate(plan["orden"]):
        mes_liq = plan["liquidacion"].get(id(d))
        sale = f"sale en {_mes_corto(f4._sumar_meses(hoy, mes_liq))}" if mes_liq else "fuera de alcance"
        color_b = None if k == 0 else "#2a3344"
        sin_avance = d["minimo"] <= d["saldo"] * d["tasa"] / 1200.0
        aviso = (f"<p class='fpx-s' style='font-size:.7rem;color:{NEG};margin-top:3px;'>El mínimo no cubre los intereses del mes "
                 f"({dinero(round(d['saldo'] * d['tasa'] / 1200.0))}).</p>" if sin_avance else "")
        filas += (f"<div style='padding:8px 0;{'border-top:1px solid #161d2b;' if k else ''}'>"
                  f"<div class='fpx-row'><span style='font-size:.88rem;'><span class='m' style='color:{ORO2};margin-right:8px;'>{k + 1}</span>"
                  f"{_e(d['nombre'])}</span><span class='m' style='font-size:.88rem;'>{dinero(d['saldo'])}</span></div>"
                  f"<div class='fpx-row fpx-s' style='font-size:.72rem;margin:2px 0 5px;'><span>{d['tasa']:.2f}% anual · mínimo "
                  f"<span class='m'>{dinero(d['minimo'])}</span></span><span>{sale}</span></div>"
                  f"{_barra(d['saldo'] / mayor * 100, color_b)}{aviso}</div>")
    chip = "<span class='fpx-chip'>Sin guardar</span>" if pendiente else ""
    return (f"<div class='fpx-card'><div class='fpx-row'><p class='fpx-t' style='margin:0;'>Libre de deudas</p>{chip}</div>"
            f"<p class='m' style='font-size:1.9rem;line-height:1.1;margin:2px 0 6px;color:{color};'>{valor}</p>"
            f"<p class='fpx-s' style='font-size:.78rem;'>{sub}</p>"
            f"<div style='border-top:1px solid #1c2331;margin:12px 0 4px;'></div>{filas}</div>")


@_fragmento
def ui_deudas(db_conn, uid):
    import pandas as pd
    import fp_fase4_ui as f4
    f4._mostrar_flash()
    if not f4._esquema_ok(db_conn):
        return
    hoy = f4._hoy()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("<p class='fpx-sec notranslate' translate='no'>Tus deudas · Estrategia Avalancha</p>"
                "<p class='fpx-s' style='margin:-4px 0 12px;'>Orden por tasa: el pago mínimo va a todas y cada peso extra a la "
                "tasa más alta, que es la ruta con menos intereses en la simulación.</p>", unsafe_allow_html=True)
    try:
        filas = f4._cargar_deudas(db_conn, uid)
    except Exception:
        log.exception("Deudas")
        st.error("No pude leer tus deudas en este momento.")
        return
    ids_originales = {f[0] for f in filas}
    caja = st.empty()   # la tarjeta se dibuja arriba con lo que tenga la tabla, guardado o no
    with st.expander("Editar deudas", expanded=not filas):
        df = pd.DataFrame({
            "_id": pd.Series([f[0] for f in filas], dtype="object"),
            "Deuda": pd.Series([f[1] for f in filas], dtype="object"),
            "Saldo actual": pd.Series([f4._f(f[2]) for f in filas], dtype="float"),
            "Tasa anual %": pd.Series([f4._f(f[3]) for f in filas], dtype="float"),
            "Pago mínimo": pd.Series([f4._f(f[4]) for f in filas], dtype="float"),
            "Día de pago": pd.Series([f4._f(f[5], None) for f in filas], dtype="float"),
        })
        editado = st.data_editor(
            df, key=f"fpx_deu_editor_{uid}_{f4._version('deu', uid)}", hide_index=True, use_container_width=True,
            num_rows="dynamic",
            column_config={
                "_id": None,
                "Deuda": st.column_config.TextColumn("Deuda", required=True, max_chars=80),
                "Saldo actual": st.column_config.NumberColumn("Saldo actual", min_value=0.0, step=100.0, format="$%.2f"),
                "Tasa anual %": st.column_config.NumberColumn("Tasa anual", min_value=0.0, max_value=500.0, step=0.5,
                                                              format="%.2f%%", help="CAT o tasa anual de la deuda."),
                "Pago mínimo": st.column_config.NumberColumn("Pago mínimo mensual", min_value=0.0, step=50.0, format="$%.2f"),
                "Día de pago": st.column_config.NumberColumn("Día de pago", min_value=1, max_value=31, step=1, format="%d"),
            })
        nuevas, errores = f4._deudas_desde_editor(editado)
        for e in errores:
            st.caption(e)
        firma = lambda ds: sorted((d["nombre"], round(d["saldo"], 2), round(d["tasa"], 3), round(d["minimo"], 2), d["dia"]) for d in ds)
        guardadas = [{"nombre": f[1], "saldo": f4._f(f[2]), "tasa": f4._f(f[3]), "minimo": f4._f(f[4]),
                      "dia": None if f[5] is None else int(f4._f(f[5]))} for f in filas]
        pendiente = firma(nuevas) != firma(guardadas)
        if pendiente:
            st.markdown(f"<p class='fpx fpx-s' style='color:{ORO2};font-size:.76rem;'>Cambios sin guardar · la tarjeta de arriba "
                        f"ya los muestra; se conservan al presionar «Guardar deudas».</p>", unsafe_allow_html=True)
        if st.button("Guardar deudas", key=f"fpx_deu_guardar_{uid}", type="primary", use_container_width=True,
                     disabled=not pendiente):
            try:
                f4._guardar_deudas(db_conn, uid, nuevas, ids_originales)
            except Exception as ex:
                log.exception("Guardar deudas")
                st.error(f"No pude guardar tus deudas ({type(ex).__name__}). Intenta de nuevo en un momento.")
                return
            f4._reiniciar_editor("deu", uid)
            f4._flash("Deudas guardadas.")
            _rerun_seccion()

    con_saldo = [d for d in nuevas if d["saldo"] > 0]
    with caja.container():
        if con_saldo:
            extra = st.number_input("Pago extra al mes (MXN)", min_value=0.0, value=0.0, step=250.0, format="%.2f",
                                    key=f"fpx_deu_extra_{uid}",
                                    help="Monto adicional a los mínimos; en la Avalancha se asigna completo a la tasa más alta.")
            plan = f4._simular_pagos(con_saldo, extra, avalancha=True)
            base = f4._simular_pagos(con_saldo, 0.0, avalancha=False)
            _md(_html_deudas(plan, base, con_saldo, hoy, f4, pendiente))
        else:
            st.caption("Sin deudas registradas. Se agregan en «Editar deudas»: una fila por tarjeta, préstamo o crédito.")


# ==========================================
# 8. METAS · opción D «Tarro» (aporte calculado de fp_fase4_ui)
# ==========================================
_COL_ESTADO = {"En ruta": "pos", "Lograda": "pos", "Ajustar": "", "Vencida": "neg", "Sin fecha": "ten", "Sin monto": "ten"}


def _svg_tarro(pct, idx):
    pct = max(0.0, min(1.0, pct))
    forma = "M18 8 h34 v7 q10 5 10 17 v48 q0 9 -9 9 h-36 q-9 0 -9 -9 v-48 q0 -12 10 -17z"
    alto = 70 * pct
    return (f"<svg viewBox='0 0 70 92' width='76' height='100' aria-hidden='true'>"
            f"<defs><clipPath id='fpx-tarro-{idx}'><path d='{forma}'/></clipPath>"
            f"<linearGradient id='fpx-tg-{idx}' x1='0' y1='1' x2='0' y2='0'><stop offset='0' stop-color='#8a6f33'/>"
            f"<stop offset='1' stop-color='{ORO2}'/></linearGradient></defs>"
            f"<path d='{forma}' fill='#0b0f17'/>"
            f"<g clip-path='url(#fpx-tarro-{idx})'><rect x='0' y='{89 - alto:.1f}' width='70' height='{alto + 3:.1f}' "
            f"fill='url(#fpx-tg-{idx})'><animate attributeName='y' from='89' to='{89 - alto:.1f}' dur='1.2s' fill='freeze'/>"
            f"<animate attributeName='height' from='0' to='{alto + 3:.1f}' dur='1.2s' fill='freeze'/></rect></g>"
            f"<path d='{forma}' fill='none' stroke='#2a3344'/>"
            f"<rect x='16' y='3' width='38' height='6' rx='2' fill='#161d2b' stroke='#2a3344'/>"
            f"<line x1='9' x2='61' y1='20' y2='20' stroke='{ORO2}' stroke-dasharray='2 2' opacity='.8'/></svg>")


def _html_metas(resultados, frecuencia, f4):
    periodo = f4._TXT_PERIODO[frecuencia]
    tarros = ""
    for k, (nombre, saldo, objetivo, fecha, aporte, ev) in enumerate(resultados):
        pct = saldo / objetivo if objetivo > 0 else 0.0
        if ev["estado"] in ("En ruta", "Ajustar"):
            linea = f"<span class='m' style='color:{ORO2};'>{dinero(ev['requerido'])}</span> / {periodo}"
        elif ev["estado"] == "Lograda":
            linea = "meta cumplida"
        elif ev["estado"] == "Vencida":
            linea = f"faltan <span class='m'>{dinero(ev['faltante'])}</span>"
        elif ev["estado"] == "Sin fecha":
            linea = "sin fecha objetivo"
        else:
            linea = "sin monto objetivo"
        tarros += (f"<div style='text-align:center;min-width:0;'>{_svg_tarro(pct, k)}"
                   f"<p style='font-size:.84rem;margin:4px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{_e(nombre)}</p>"
                   f"<p class='m' style='margin:0;font-size:1rem;'>{pct * 100:.0f}%</p>"
                   f"<p class='fpx-s' style='font-size:.68rem;'><span class='m'>{dinero(saldo)}</span> de "
                   f"<span class='m'>{dinero(objetivo) if objetivo else '—'}</span></p>"
                   f"<p class='fpx-s' style='font-size:.68rem;margin-top:3px;'>{linea}</p>"
                   f"<span class='fpx-chip {_COL_ESTADO.get(ev['estado'], '')}' style='margin-top:6px;'>{ev['estado']}</span></div>")
    return (f"<div class='fpx-card'><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));"
            f"gap:16px 10px;'>{tarros}</div></div>")


@_fragmento
def ui_metas(db_conn, uid):
    import pandas as pd
    from psycopg2 import sql
    import fp_fase4_ui as f4
    f4._mostrar_flash()
    if not f4._esquema_ok(db_conn):
        return
    hoy = f4._hoy()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("<p class='fpx-sec notranslate' translate='no'>Tus metas</p>"
                "<p class='fpx-s' style='margin:-4px 0 12px;'>Cada tarro se llena con lo ahorrado; la línea punteada es el monto "
                "objetivo. El aporte por periodo se calcula con la fecha objetivo.</p>", unsafe_allow_html=True)
    try:
        filas, tiene_fecha = f4._cargar_metas(db_conn, uid)
    except Exception:
        log.exception("Metas")
        st.error("No pude leer tus metas en este momento.")
        return
    if not filas:
        st.caption("Aún no hay metas. Desde Telegram: /apartar 500 viaje (o el nombre de tu meta).")
        return
    frec_default = f4._frecuencia_usuario(db_conn, uid)
    seg = getattr(st, "segmented_control", None)
    if seg:
        frecuencia = seg("Aportas cada", options=list(f4._FRECUENCIAS), default=frec_default, key=f"fpx_met_frec_{uid}",
                         format_func=lambda f: f4._TXT_PERIODO[f].capitalize()) or frec_default
    else:
        frecuencia = st.selectbox("Aportas cada", list(f4._FRECUENCIAS), index=f4._FRECUENCIAS.index(frec_default),
                                  key=f"fpx_met_frec_{uid}", format_func=lambda f: f4._TXT_PERIODO[f].capitalize())
    caja = st.empty()

    with st.expander("Editar metas"):
        if not tiene_fecha:
            st.caption("La fecha objetivo aún no está disponible en tu base de datos; se calculará cuando se active.")
        df = pd.DataFrame({
            "_id": pd.Series([f[0] for f in filas], dtype="object"),
            "Meta": pd.Series([f[1] for f in filas], dtype="object"),
            "Ahorrado": pd.Series([f4._f(f[2]) for f in filas], dtype="float"),
            "Monto objetivo": pd.Series([f4._f(f[3]) for f in filas], dtype="float"),
            "Fecha objetivo": pd.Series([f4._a_fecha(f[4]) for f in filas], dtype="object"),
            "Aporte actual": pd.Series([f4._f(f[5]) for f in filas], dtype="float"),
        })
        editado = st.data_editor(
            df, key=f"fpx_met_editor_{uid}_{f4._version('met', uid)}", hide_index=True, use_container_width=True,
            num_rows="fixed", disabled=["Meta", "Ahorrado", "Aporte actual"] + ([] if tiene_fecha else ["Fecha objetivo"]),
            column_config={
                "_id": None,
                "Ahorrado": st.column_config.NumberColumn("Ahorrado", format="$%.2f"),
                "Monto objetivo": st.column_config.NumberColumn("Monto objetivo", min_value=0.0, step=500.0, format="$%.2f"),
                "Fecha objetivo": st.column_config.DateColumn("Fecha objetivo", min_value=hoy, format="DD/MM/YYYY"),
                "Aporte actual": st.column_config.NumberColumn(f"Aporte por {f4._TXT_PERIODO[frecuencia]}", format="$%.2f"),
            })
        resultados, para_guardar = [], []
        for _, fila in editado.iterrows():
            saldo, objetivo = f4._f(fila["Ahorrado"]), max(0.0, f4._f(fila["Monto objetivo"]))
            fecha, aporte = f4._a_fecha(fila["Fecha objetivo"]), f4._f(fila["Aporte actual"])
            ev = f4._evaluar_meta(saldo, objetivo, fecha, aporte, hoy, frecuencia)
            resultados.append((fila["Meta"], saldo, objetivo, fecha, aporte, ev))
            para_guardar.append((fila, objetivo, fecha, ev))
        aplicar = st.checkbox(f"Usar el aporte calculado como aporte por {f4._TXT_PERIODO[frecuencia]}",
                              key=f"fpx_met_aplicar_{uid}",
                              help="Actualiza el aporte de cada bolsa; el Dinero Libre se recalcula con ese monto.")
        if st.button("Guardar metas", key=f"fpx_met_guardar_{uid}", type="primary", use_container_width=True):
            try:
                with f4._abrir(db_conn) as conn, conn.cursor() as cur:
                    _, id_col = f4._meta_bolsas(cur)
                    for fila, objetivo, fecha, ev in para_guardar:
                        sets = [sql.SQL("monto_objetivo = %s")]
                        params = [round(objetivo, 2) if objetivo > 0 else None]
                        if tiene_fecha:
                            sets.append(sql.SQL("fecha_objetivo = %s"))
                            params.append(fecha)
                        if aplicar and ev["estado"] in ("En ruta", "Ajustar") and ev["requerido"] is not None:
                            sets.append(sql.SQL("aporte_periodo = %s"))
                            params.append(ev["requerido"])
                        params += [uid, str(fila["_id"])]
                        cur.execute(sql.SQL("UPDATE fp_bolsas SET {} WHERE user_id = %s AND {}::text = %s")
                                    .format(sql.SQL(", ").join(sets), sql.Identifier(id_col)), params)
            except Exception:
                log.exception("Guardar metas")
                st.error("No pude guardar tus metas. Intenta de nuevo en un momento.")
                return
            f4._reiniciar_editor("met", uid)
            f4._flash("Metas actualizadas.")
            _rerun_seccion()
    with caja.container():
        _md(_html_metas(resultados, frecuencia, f4))
