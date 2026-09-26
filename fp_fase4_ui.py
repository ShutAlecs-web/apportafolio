"""
fp_fase4_ui.py — APortafolio FP · Fase 4 · Bloque 2 (UI de Planificación)

Módulo AISLADO (Norma 2): no importa nada de app.py. Recibe `db_conn` (context manager de app.py).
Exporta:
  • ui_cascada_ingresos(db_conn, uid)    · Punto 12 · reparto en cascada del próximo ingreso
  • ui_control_deudas(db_conn, uid)      · Punto 13 · pasivos + Estrategia Avalancha
  • ui_metas_aportaciones(db_conn, uid)  · Punto 14 · metas con aportación calculada
  Atajos: ui_planificacion(db_conn, uid) (las 3 en tabs) y ui_boton_cascada / ui_boton_deudas / ui_boton_metas (diálogos).

Cambios de esquema (solo ADITIVOS, IF NOT EXISTS):
  - CREATE fp_reglas_cascada, fp_repartos_cascada, fp_deudas.
  - ALTER fp_bolsas ADD COLUMN fecha_objetivo DATE (nullable; no altera fp_dinero_libre).
Suposiciones: fp_bolsas tiene user_id, nombre, tipo, aporte_periodo, saldo_acumulado, monto_objetivo, activa
(las mismas que ya lee app.py); su id se detecta entre {bolsa_id, id} y, si no hay, se usa nombre.
La frecuencia por defecto para metas es users.dca_frequency (editable en pantalla).
"""
from __future__ import annotations

import json
import logging
import math
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from psycopg2 import sql

log = logging.getLogger("apportafolio_fp.fase4_ui")

ZONA_MX = timezone(timedelta(hours=-6))  # CDMX sin horario de verano (mismo criterio que app.py)
ORO, VERDE, GRIS, TENUE = "#d4af37", "#34d399", "#94a3b8", "#64748b"

__all__ = [
    "ui_cascada_ingresos", "ui_control_deudas", "ui_metas_aportaciones",
    "ui_planificacion", "ui_boton_cascada", "ui_boton_deudas", "ui_boton_metas",
]

_FRECUENCIAS = ("SEMANAL", "QUINCENAL", "MENSUAL")
_DIAS_FRECUENCIA = {"SEMANAL": 7, "QUINCENAL": 15, "MENSUAL": 30}
_TXT_PERIODO = {"SEMANAL": "semana", "QUINCENAL": "quincena", "MENSUAL": "mes"}
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

# Orden de la cascada (fijo, Blueprint punto 12): Compromisos -> Colchón -> Metas -> Inversión -> Libre
_DESTINOS = (
    ("COMPROMISOS", "Compromisos", "#475569"),
    ("COLCHON",     "Colchón",     "#64748b"),
    ("METAS",       "Metas",       "rgba(212,175,55,0.65)"),
    ("INVERSION",   "Inversión",   ORO),
    ("LIBRE",       "Libre",       VERDE),
)
_MODOS = {"AUTO": "Automático", "PORCENTAJE": "% del ingreso", "MONTO_FIJO": "Monto fijo", "RESTO": "Lo que sobre"}
_MODOS_INV = {v: k for k, v in _MODOS.items()}
_REGLAS_DEFAULT = {
    "COMPROMISOS": ("AUTO", 0.0), "COLCHON": ("AUTO", 0.0), "METAS": ("AUTO", 0.0),
    "INVERSION": ("PORCENTAJE", 10.0), "LIBRE": ("RESTO", 0.0),
}

_DDL = """
CREATE TABLE IF NOT EXISTS fp_reglas_cascada (
    regla_id       TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    orden          SMALLINT NOT NULL,
    destino        TEXT NOT NULL CHECK (destino IN ('COMPROMISOS','COLCHON','METAS','INVERSION','LIBRE')),
    modo           TEXT NOT NULL CHECK (modo IN ('AUTO','PORCENTAJE','MONTO_FIJO','RESTO')),
    valor          NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (valor >= 0),
    activa         BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, destino)
);
CREATE TABLE IF NOT EXISTS fp_repartos_cascada (
    reparto_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    fecha      DATE NOT NULL,
    ingreso    NUMERIC(14,2) NOT NULL,
    detalle    JSONB NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_fp_repartos_cascada_user ON fp_repartos_cascada (user_id, creado_en DESC);
CREATE TABLE IF NOT EXISTS fp_deudas (
    deuda_id       TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    nombre         TEXT NOT NULL,
    saldo_actual   NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (saldo_actual >= 0),
    tasa_anual     NUMERIC(7,3)  NOT NULL DEFAULT 0 CHECK (tasa_anual >= 0),
    pago_minimo    NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (pago_minimo >= 0),
    dia_pago       SMALLINT CHECK (dia_pago BETWEEN 1 AND 31),
    activa         BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Si fp_deudas ya existía (migraciones del bot), solo se completan columnas faltantes.
ALTER TABLE fp_deudas
    ADD COLUMN IF NOT EXISTS saldo_actual   NUMERIC(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tasa_anual     NUMERIC(7,3)  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pago_minimo    NUMERIC(14,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dia_pago       SMALLINT,
    ADD COLUMN IF NOT EXISTS activa         BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ix_fp_deudas_user ON fp_deudas (user_id);
DO $$ BEGIN
    IF to_regclass('public.fp_bolsas') IS NOT NULL THEN
        ALTER TABLE fp_bolsas ADD COLUMN IF NOT EXISTS fecha_objetivo DATE;
    END IF;
END $$;
"""

_CSS = f"""
<style>
.fp4-card {{ background: transparent; border: 1px solid rgba(212,175,55,0.16); border-radius: 18px;
            padding: 18px 20px; margin: 6px 0 14px 0; }}
.fp4-cab {{ font-family: 'Playfair Display', serif; font-style: italic; color: #ffffff; font-size: 1.25rem;
           font-weight: 400; margin: 4px 0 2px 0; letter-spacing: 0.5px; }}
.fp4-nota {{ color: #8b949e; font-size: 0.82rem; line-height: 1.5; margin: 0 0 12px 0; }}
.fp4-titulo {{ color: #8b949e; font-size: 0.72rem; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px; }}
.fp4-valor {{ font-family: 'Playfair Display', serif; font-size: 1.8rem; color: #ffffff; line-height: 1.1; }}
.fp4-sub {{ color: {TENUE}; font-size: 0.8rem; margin-top: 3px; }}
.fp4-barra {{ display: flex; width: 100%; height: 12px; border-radius: 6px; overflow: hidden; background: #111827;
             border: 1px solid #1f2937; margin: 12px 0; }}
.fp4-barra div {{ height: 100%; }}
.fp4-fila {{ display: flex; justify-content: space-between; align-items: baseline; padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.9rem; color: #e5e7eb; }}
.fp4-fila:last-child {{ border-bottom: none; }}
.fp4-chip {{ display: inline-block; padding: 1px 10px; border-radius: 12px; font-size: 0.7rem; border: 1px solid;
            letter-spacing: 1px; text-transform: uppercase; margin-left: 8px; }}
.fp4-mini {{ width: 100%; height: 6px; background: #111827; border-radius: 3px; margin-top: 8px; }}
.fp4-mini div {{ height: 100%; border-radius: 3px; background: rgba(212,175,55,0.75); }}
</style>
"""


# ==========================================
# 1. INFRAESTRUCTURA
# ==========================================
@contextmanager
def _abrir(db_conn):
    """Adapter: acepta fábrica de context manager (app.py) o fábrica/objeto de conexión cruda."""
    creada_aqui = callable(db_conn) and not hasattr(db_conn, "cursor")
    obj = db_conn() if creada_aqui else db_conn
    if hasattr(obj, "cursor"):
        try:
            yield obj
            if not getattr(obj, "autocommit", False):
                obj.commit()
        except Exception:
            try:
                obj.rollback()
            except Exception:
                pass
            raise
        finally:
            if creada_aqui:
                try:
                    obj.close()
                except Exception:
                    pass
    else:
        with obj as conn:
            yield conn


def _consulta(db_conn, q, params=None):
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        cur.execute(q, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, fila)) for fila in cur.fetchall()]


def _columnas(cur, tabla):
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = %s AND table_schema = ANY(current_schemas(false))", (tabla,))
    return {n: t for n, t in cur.fetchall()}


def _elegir(cols, candidatos):
    return next((c for c in candidatos if c in cols), None)


@st.cache_resource(show_spinner=False)
def _asegurar_esquema(_db_conn):
    with _abrir(_db_conn) as conn, conn.cursor() as cur:
        cur.execute(_DDL)
    return True


def _esquema_ok(db_conn):
    try:
        return _asegurar_esquema(db_conn)
    except Exception:
        log.exception("No se pudo preparar el esquema de planificación")
        st.error("No pude preparar las tablas de planificación. Revisa la conexión con la base de datos.")
        return False


def _hoy():
    return datetime.now(ZONA_MX).date()


def _f(valor, default=0.0):
    try:
        if valor is None or (isinstance(valor, float) and math.isnan(valor)):
            return default
        return float(valor)
    except (TypeError, ValueError):
        return default


def _vacio(valor):
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    try:
        return bool(pd.isna(valor))  # cubre NaN, NaT y pd.NA
    except (TypeError, ValueError):
        return False


def _dinero(valor):
    v = round(_f(valor), 2)
    signo, v = ("-" if v < 0 else ""), abs(v)
    return f"{signo}${v:,.0f}" if v == int(v) else f"{signo}${v:,.2f}"


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def _a_fecha(valor):
    if _vacio(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _sumar_meses(d, n):
    total = d.month - 1 + n
    anio, mes = d.year + total // 12, total % 12 + 1
    import calendar
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def _fecha_corta(d):
    return f"{d.day} {_MESES[d.month - 1]} {d.year}"


def _estilos():
    st.markdown(_CSS, unsafe_allow_html=True)


def _cabecera(titulo, nota):
    st.markdown(f"<p class='fp4-cab notranslate' translate='no'>{titulo}</p><p class='fp4-nota'>{nota}</p>",
                unsafe_allow_html=True)


def _version(nombre, uid):
    return st.session_state.setdefault(f"fp4_v_{nombre}_{uid}", 0)


def _reiniciar_editor(nombre, uid):
    st.session_state[f"fp4_v_{nombre}_{uid}"] = _version(nombre, uid) + 1


def _flash(mensaje):
    st.session_state["fp4_flash"] = mensaje


def _mostrar_flash():
    mensaje = st.session_state.pop("fp4_flash", None)
    if mensaje:
        st.toast(mensaje)


def _frecuencia_usuario(db_conn, uid):
    try:
        filas = _consulta(db_conn, "SELECT dca_frequency FROM users WHERE user_id = %s", (uid,))
        f = str((filas[0]["dca_frequency"] if filas else "") or "").upper()
        return f if f in _FRECUENCIAS else "QUINCENAL"
    except Exception:
        return "QUINCENAL"


# ==========================================
# 2. CASCADA DE INGRESOS (Punto 12)
# ==========================================
def _destino_de_tipo(tipo):
    n = _norm(tipo)
    if "colchon" in n or "emergencia" in n:
        return "COLCHON"
    if "meta" in n:
        return "METAS"
    if "inversion" in n or "invertir" in n:
        return "INVERSION"
    return None


def _montos_automaticos(db_conn, uid, hoy, frecuencia):
    """Lo que el modo 'Automático' toma de la configuración existente (fricción cero)."""
    autos, avisos = {d: 0.0 for d, _, _ in _DESTINOS}, []
    hasta = hoy + timedelta(days=_DIAS_FRECUENCIA[frecuencia] - 1)
    try:
        filas = _consulta(db_conn,
                          "SELECT COALESCE(SUM(monto), 0) AS total FROM fp_ocurrencias(%s, %s, %s) "
                          "WHERE tipo_movimiento <> 'INGRESO'", (uid, hoy, hasta))
        autos["COMPROMISOS"] = _f(filas[0]["total"]) if filas else 0.0
        # Alternativa (desactivada para no contar doble si tus deudas ya son compromisos):
        # autos["COMPROMISOS"] += SUM(pago_minimo) FROM fp_deudas WHERE user_id = uid AND activa
    except Exception:
        log.exception("fp_ocurrencias no disponible")
        avisos.append("No pude leer tus compromisos programados; 'Automático' en Compromisos cuenta $0.")
    try:
        for fila in _consulta(db_conn,
                              "SELECT tipo, COALESCE(SUM(aporte_periodo), 0) AS total FROM fp_bolsas "
                              "WHERE user_id = %s AND activa GROUP BY tipo", (uid,)):
            destino = _destino_de_tipo(fila["tipo"])
            if destino:
                autos[destino] += _f(fila["total"])
    except Exception:
        log.exception("fp_bolsas no disponible")
        avisos.append("No pude leer tus bolsas; 'Automático' en Colchón, Metas e Inversión cuenta $0.")
    return autos, avisos, hasta


def _ultimo_ingreso(db_conn, uid):
    try:
        filas = _consulta(db_conn,
                          "SELECT monto FROM fp_financial_ledger WHERE user_id = %s AND tipo_movimiento = 'INGRESO' "
                          "AND COALESCE(estado, '') <> 'DESCARTADO' ORDER BY fecha DESC LIMIT 1", (uid,))
        return _f(filas[0]["monto"]) if filas else 0.0
    except Exception:
        return 0.0


def _cargar_reglas(db_conn, uid):
    guardadas = {}
    try:
        for f in _consulta(db_conn, "SELECT destino, modo, valor, activa FROM fp_reglas_cascada WHERE user_id = %s", (uid,)):
            guardadas[f["destino"]] = (f["modo"], _f(f["valor"]), bool(f["activa"]))
    except Exception:
        log.exception("No se pudieron leer las reglas de cascada")
    reglas = []
    for destino, etiqueta, _ in _DESTINOS:
        modo, valor = _REGLAS_DEFAULT[destino]
        activa = True
        if destino in guardadas:
            modo, valor, activa = guardadas[destino]
        reglas.append({"destino": destino, "etiqueta": etiqueta, "modo": modo, "valor": valor, "activa": activa})
    return reglas, bool(guardadas)


def _reglas_desde_editor(editado):
    reglas = []
    for (destino, etiqueta, _), (_, fila) in zip(_DESTINOS, editado.iterrows()):
        modo = _MODOS_INV.get(fila.get("Modo"), "AUTO")
        if destino == "LIBRE":
            modo = "RESTO"
        elif modo == "RESTO":
            modo = "AUTO"  # "Lo que sobre" solo tiene sentido al final de la cascada
        activa = bool(fila.get("Activa")) if destino != "LIBRE" else True
        reglas.append({"destino": destino, "etiqueta": etiqueta, "modo": modo,
                       "valor": max(0.0, _f(fila.get("Valor"))), "activa": activa})
    return reglas


def _simular_cascada(ingreso, reglas, autos):
    restante, salida = max(0.0, _f(ingreso)), []
    for r in reglas:
        if r["destino"] == "LIBRE":
            salida.append({**r, "solicitado": restante, "asignado": restante, "faltante": 0.0})
            restante = 0.0
            continue
        if not r["activa"]:
            solicitado = 0.0
        elif r["modo"] == "AUTO":
            solicitado = autos.get(r["destino"], 0.0)
        elif r["modo"] == "PORCENTAJE":
            solicitado = _f(ingreso) * min(r["valor"], 100.0) / 100.0
        else:
            solicitado = r["valor"]
        asignado = min(restante, solicitado)
        restante -= asignado
        salida.append({**r, "solicitado": round(solicitado, 2), "asignado": round(asignado, 2),
                       "faltante": round(solicitado - asignado, 2)})
    return salida


def _render_reparto(sim, ingreso):
    total = max(_f(ingreso), 1.0)
    colores = {d: c for d, _, c in _DESTINOS}
    segmentos = "".join(f"<div style='width:{s['asignado'] / total * 100:.2f}%; background:{colores[s['destino']]};'></div>"
                        for s in sim if s["asignado"] > 0)
    filas = ""
    for s in sim:
        extra = (f"<div class='fp4-sub' style='color:{GRIS};'>faltan {_dinero(s['faltante'])} para cubrirlo</div>"
                 if s["faltante"] > 0.005 else "")
        pct = s["asignado"] / total * 100 if _f(ingreso) > 0 else 0
        filas += (f"<div class='fp4-fila'><div><span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
                  f"background:{colores[s['destino']]};margin-right:8px;'></span>{s['etiqueta']}{extra}</div>"
                  f"<div style='color:{VERDE if s['destino'] == 'LIBRE' else '#e5e7eb'};'>{_dinero(s['asignado'])}"
                  f"<span class='fp4-sub'> · {pct:.0f}%</span></div></div>")
    libre = sim[-1]["asignado"] if sim else 0.0
    st.markdown(
        f"<div class='fp4-card notranslate' translate='no'><div class='fp4-titulo'>Simulación del reparto</div>"
        f"<div class='fp4-valor' style='color:{VERDE if libre > 0 else GRIS};'>{_dinero(libre)} "
        f"<span class='fp4-sub'>quedan libres</span></div><div class='fp4-barra'>{segmentos}</div>{filas}</div>",
        unsafe_allow_html=True)


def _guardar_reglas(db_conn, uid, reglas):
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        for orden, r in enumerate(reglas, start=1):
            cur.execute(
                """
                INSERT INTO fp_reglas_cascada (regla_id, user_id, orden, destino, modo, valor, activa, actualizado_en)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id, destino) DO UPDATE
                   SET orden = EXCLUDED.orden, modo = EXCLUDED.modo, valor = EXCLUDED.valor,
                       activa = EXCLUDED.activa, actualizado_en = now()
                """,
                (f"CAS-{uid}-{r['destino']}", uid, orden, r["destino"], r["modo"], round(r["valor"], 2), r["activa"]))


def _registrar_reparto(db_conn, uid, ingreso, sim, hoy):
    detalle = [{"destino": s["destino"], "modo": s["modo"], "solicitado": s["solicitado"],
                "asignado": s["asignado"], "faltante": s["faltante"]} for s in sim]
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO fp_repartos_cascada (reparto_id, user_id, fecha, ingreso, detalle) VALUES (%s, %s, %s, %s, %s)",
                    (f"REP-{uuid.uuid4().hex[:16]}", uid, hoy, round(_f(ingreso), 2), json.dumps(detalle)))
    # Alternativa (desactivada, Norma 2): mover el reparto a saldo_acumulado de fp_bolsas. Se deja fuera porque
    # cambia el cálculo de fp_dinero_libre; activarla requiere validarla contra esa función primero.


def _render_historial(db_conn, uid):
    try:
        filas = _consulta(db_conn, "SELECT fecha, ingreso, detalle FROM fp_repartos_cascada WHERE user_id = %s "
                                   "ORDER BY creado_en DESC LIMIT 5", (uid,))
    except Exception:
        return
    if not filas:
        return
    with st.expander("Repartos registrados", expanded=False):
        html = ""
        for f in filas:
            detalle = f["detalle"] if isinstance(f["detalle"], list) else json.loads(f["detalle"] or "[]")
            libre = next((d["asignado"] for d in detalle if d.get("destino") == "LIBRE"), 0)
            html += (f"<div class='fp4-fila'><div>{_fecha_corta(f['fecha'])}<div class='fp4-sub'>ingreso {_dinero(f['ingreso'])}</div></div>"
                     f"<div style='color:{VERDE};'>{_dinero(libre)} libre</div></div>")
        st.markdown(f"<div class='notranslate' translate='no'>{html}</div>", unsafe_allow_html=True)


def ui_cascada_ingresos(db_conn, uid):
    """Configura cómo se reparte el próximo ingreso y lo simula antes de guardarlo."""
    _estilos()
    _mostrar_flash()
    if not _esquema_ok(db_conn):
        return
    hoy = _hoy()
    frecuencia = _frecuencia_usuario(db_conn, uid)
    reglas, ya_guardadas = _cargar_reglas(db_conn, uid)
    autos, avisos, hasta = _montos_automaticos(db_conn, uid, hoy, frecuencia)

    _cabecera("Reparto de tu próximo ingreso",
              "El dinero baja en cascada: primero lo que ya debes, después tu colchón, tus metas y tu inversión. "
              "Lo que sobra es tuyo para gastar sin culpa.")
    ingreso = st.number_input("Monto del próximo ingreso (MXN)", min_value=0.0, step=500.0, format="%.2f",
                              value=_ultimo_ingreso(db_conn, uid), key=f"fp4_cas_ingreso_{uid}")

    df = pd.DataFrame([{
        "Destino": r["etiqueta"],
        "Modo": _MODOS[r["modo"]],
        "Valor": float(r["valor"]),
        "Automático": _dinero(autos.get(r["destino"], 0.0)) if r["destino"] != "LIBRE" else "—",
        "Activa": bool(r["activa"]),
    } for r in reglas])
    editado = st.data_editor(
        df, key=f"fp4_cas_editor_{uid}_{_version('cas', uid)}", hide_index=True, use_container_width=True,
        num_rows="fixed", disabled=["Destino", "Automático"],
        column_config={
            "Destino": st.column_config.TextColumn("Destino", width="small"),
            "Modo": st.column_config.SelectboxColumn("Cómo se calcula", options=list(_MODOS.values()), required=True),
            "Valor": st.column_config.NumberColumn("Valor (% o $)", min_value=0.0, step=1.0, format="%.2f",
                                                   help="Porcentaje si el modo es '% del ingreso'; pesos si es 'Monto fijo'."),
            "Automático": st.column_config.TextColumn(f"Automático (hasta {hasta:%d/%m})",
                                                      help="Tomado de tus compromisos programados y del aporte de tus bolsas."),
            "Activa": st.column_config.CheckboxColumn("Activa"),
        })
    for aviso in avisos:
        st.caption(aviso)

    reglas_ed = _reglas_desde_editor(editado)
    pct_total = sum(r["valor"] for r in reglas_ed if r["activa"] and r["modo"] == "PORCENTAJE")
    if pct_total > 100:
        st.warning(f"Tus porcentajes suman {pct_total:.0f}%. La cascada asigna en orden y lo último se quedará corto.")

    sim = _simular_cascada(ingreso, reglas_ed, autos)
    if ingreso > 0:
        _render_reparto(sim, ingreso)
        if sim[0]["faltante"] > 0.005:
            st.warning(f"Este ingreso no cubre tus compromisos: faltan {_dinero(sim[0]['faltante'])}.")
    else:
        st.caption("Escribe el monto de tu próximo ingreso para ver la simulación.")

    c1, c2 = st.columns(2)
    guardar = c1.button("Guardar reglas", key=f"fp4_cas_guardar_{uid}", use_container_width=True)
    registrar = c2.button("Guardar y registrar este reparto", key=f"fp4_cas_registrar_{uid}", type="primary",
                          use_container_width=True, disabled=ingreso <= 0)
    if guardar or registrar:
        try:
            _guardar_reglas(db_conn, uid, reglas_ed)
            if registrar:
                _registrar_reparto(db_conn, uid, ingreso, sim, hoy)
        except Exception:
            log.exception("Error guardando cascada")
            st.error("No pude guardar. Inténtalo de nuevo en un momento.")
            return
        _reiniciar_editor("cas", uid)
        _flash("Reparto registrado." if registrar else "Reglas de reparto guardadas.")
        st.rerun()
    if not ya_guardadas:
        st.caption("Estas son reglas sugeridas; se aplican cuando las guardes.")
    _render_historial(db_conn, uid)


# ==========================================
# 3. DEUDAS · ESTRATEGIA AVALANCHA (Punto 13)
# ==========================================
def _meta_deudas(cur):
    cols = _columnas(cur, "fp_deudas")
    id_col = _elegir(cols, ("deuda_id", "id"))
    return id_col, cols.get(id_col, "")


def _cargar_deudas(db_conn, uid):
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        id_col, _ = _meta_deudas(cur)
        cur.execute(
            sql.SQL("SELECT {}::text, nombre, saldo_actual, tasa_anual, pago_minimo, dia_pago FROM fp_deudas "
                    "WHERE user_id = %s AND COALESCE(activa, TRUE) ORDER BY tasa_anual DESC, saldo_actual ASC")
            .format(sql.Identifier(id_col)), (uid,))
        return cur.fetchall()


def _deudas_desde_editor(editado):
    deudas, errores = [], []
    for _, fila in editado.iterrows():
        nombre = "" if _vacio(fila.get("Deuda")) else str(fila.get("Deuda")).strip()
        if not nombre:
            continue
        dia = None if _vacio(fila.get("Día de pago")) else int(_f(fila.get("Día de pago")))
        if dia is not None and not 1 <= dia <= 31:
            errores.append(f"{nombre}: el día de pago debe estar entre 1 y 31.")
            dia = None
        deudas.append({
            "id": None if _vacio(fila.get("_id")) else str(fila.get("_id")),
            "nombre": nombre[:80],
            "saldo": max(0.0, round(_f(fila.get("Saldo actual")), 2)),
            "tasa": max(0.0, round(_f(fila.get("Tasa anual %")), 3)),
            "minimo": max(0.0, round(_f(fila.get("Pago mínimo")), 2)),
            "dia": dia,
        })
    return deudas, errores


def _simular_pagos(deudas, extra=0.0, avalancha=True, max_meses=600):
    """Simulación mensual. avalancha=True: mínimos + extra + mínimos liberados van a la tasa más alta."""
    orden = sorted(deudas, key=lambda d: (-d["tasa"], d["saldo"]))
    saldos = {id(d): d["saldo"] for d in orden}
    presupuesto_base = sum(d["minimo"] for d in orden) + max(0.0, extra)
    liquidacion, pagos_mes1, interes_total, mes = {}, {}, 0.0, 0
    while any(s > 0.005 for s in saldos.values()) and mes < max_meses:
        mes += 1
        for d in orden:
            if saldos[id(d)] > 0.005:
                i = saldos[id(d)] * d["tasa"] / 1200.0
                saldos[id(d)] += i
                interes_total += i
        disponible = presupuesto_base if avalancha else float("inf")
        pagos = {}
        for d in orden:
            if saldos[id(d)] > 0.005:
                p = min(saldos[id(d)], d["minimo"], disponible)
                saldos[id(d)] -= p
                disponible -= p
                pagos[id(d)] = p
        if avalancha:
            for d in orden:
                if disponible <= 0.005:
                    break
                if saldos[id(d)] > 0.005:
                    p = min(saldos[id(d)], disponible)
                    saldos[id(d)] -= p
                    disponible -= p
                    pagos[id(d)] = pagos.get(id(d), 0.0) + p
        if mes == 1:
            pagos_mes1 = pagos
        for d in orden:
            if saldos[id(d)] <= 0.005 and id(d) not in liquidacion and d["saldo"] > 0:
                liquidacion[id(d)] = mes
    completo = all(s <= 0.005 for s in saldos.values())
    return {"orden": orden, "meses": mes, "interes": interes_total, "liquidacion": liquidacion,
            "pagos_mes1": pagos_mes1, "completo": completo}


def _guardar_deudas(db_conn, uid, deudas, ids_originales):
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        id_col, id_tipo = _meta_deudas(cur)
        ident = sql.Identifier(id_col)
        vigentes = set()
        for d in deudas:
            if d["id"] and d["id"] in ids_originales:
                vigentes.add(d["id"])
                cur.execute(sql.SQL("UPDATE fp_deudas SET nombre=%s, saldo_actual=%s, tasa_anual=%s, pago_minimo=%s, "
                                    "dia_pago=%s, activa=TRUE, actualizado_en=now() WHERE user_id=%s AND {}::text=%s")
                            .format(ident), (d["nombre"], d["saldo"], d["tasa"], d["minimo"], d["dia"], uid, d["id"]))
            elif id_tipo in ("text", "character varying"):
                cur.execute(sql.SQL("INSERT INTO fp_deudas ({}, user_id, nombre, saldo_actual, tasa_anual, pago_minimo, dia_pago) "
                                    "VALUES (%s, %s, %s, %s, %s, %s, %s)").format(ident),
                            (f"DEU-{uuid.uuid4().hex[:16]}", uid, d["nombre"], d["saldo"], d["tasa"], d["minimo"], d["dia"]))
            else:  # id numérico/serial en una tabla preexistente: se deja al DEFAULT
                cur.execute("INSERT INTO fp_deudas (user_id, nombre, saldo_actual, tasa_anual, pago_minimo, dia_pago) "
                            "VALUES (%s, %s, %s, %s, %s, %s)", (uid, d["nombre"], d["saldo"], d["tasa"], d["minimo"], d["dia"]))
        for quitado in ids_originales - vigentes:  # baja lógica: nunca se borra el historial
            cur.execute(sql.SQL("UPDATE fp_deudas SET activa=FALSE, actualizado_en=now() WHERE user_id=%s AND {}::text=%s")
                        .format(ident), (uid, quitado))


def ui_control_deudas(db_conn, uid):
    """Captura de pasivos y orden de pago por Estrategia Avalancha (tasa más alta primero)."""
    _estilos()
    _mostrar_flash()
    if not _esquema_ok(db_conn):
        return
    hoy = _hoy()
    _cabecera("Tus deudas · Estrategia Avalancha",
              "Pagas el mínimo de todas y cada peso extra va a la deuda con la tasa más alta. "
              "Es la ruta que menos intereses te cobra.")
    try:
        filas = _cargar_deudas(db_conn, uid)
    except Exception:
        log.exception("Error leyendo fp_deudas")
        st.error("No pude leer tus deudas en este momento.")
        return
    ids_originales = {f[0] for f in filas}
    df = pd.DataFrame({
        "_id": pd.Series([f[0] for f in filas], dtype="object"),
        "Deuda": pd.Series([f[1] for f in filas], dtype="object"),
        "Saldo actual": pd.Series([_f(f[2]) for f in filas], dtype="float"),
        "Tasa anual %": pd.Series([_f(f[3]) for f in filas], dtype="float"),
        "Pago mínimo": pd.Series([_f(f[4]) for f in filas], dtype="float"),
        "Día de pago": pd.Series([_f(f[5], None) for f in filas], dtype="float"),
    })
    editado = st.data_editor(
        df, key=f"fp4_deu_editor_{uid}_{_version('deu', uid)}", hide_index=True, use_container_width=True,
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
    deudas, errores = _deudas_desde_editor(editado)
    for e in errores:
        st.caption(e)

    if st.button("Guardar deudas", key=f"fp4_deu_guardar_{uid}", type="primary", use_container_width=True):
        try:
            _guardar_deudas(db_conn, uid, deudas, ids_originales)
        except Exception:
            log.exception("Error guardando fp_deudas")
            st.error("No pude guardar tus deudas. Inténtalo de nuevo en un momento.")
            return
        _reiniciar_editor("deu", uid)
        _flash("Deudas actualizadas.")
        st.rerun()

    con_saldo = [d for d in deudas if d["saldo"] > 0]
    if not con_saldo:
        st.caption("Agrega una fila por cada tarjeta, préstamo o crédito para ver tu orden de pago.")
        return

    extra = st.number_input("Pago extra que puedes destinar cada mes (MXN)", min_value=0.0, step=250.0,
                            format="%.2f", key=f"fp4_deu_extra_{uid}")
    plan = _simular_pagos(con_saldo, extra, avalancha=True)
    base = _simular_pagos(con_saldo, 0.0, avalancha=False)

    tabla = []
    for prioridad, d in enumerate(plan["orden"], start=1):
        mes_liq = plan["liquidacion"].get(id(d))
        tabla.append({
            "Prioridad": prioridad,
            "Deuda": d["nombre"],
            "Tasa anual": d["tasa"],
            "Saldo": d["saldo"],
            "Interés del mes": round(d["saldo"] * d["tasa"] / 1200.0, 2),
            "Pago sugerido": round(plan["pagos_mes1"].get(id(d), 0.0), 2),
            "Liquidada en": _fecha_corta(_sumar_meses(hoy, mes_liq)) if mes_liq else "Fuera de alcance",
        })
    st.dataframe(
        pd.DataFrame(tabla), hide_index=True, use_container_width=True,
        column_config={
            "Prioridad": st.column_config.NumberColumn("#", format="%d", width="small"),
            "Tasa anual": st.column_config.NumberColumn("Tasa anual", format="%.2f%%"),
            "Saldo": st.column_config.NumberColumn("Saldo", format="$%.2f"),
            "Interés del mes": st.column_config.NumberColumn("Interés del mes", format="$%.2f"),
            "Pago sugerido": st.column_config.NumberColumn("Pago sugerido este mes", format="$%.2f"),
        })

    sin_avance = [d["nombre"] for d in con_saldo if d["minimo"] <= d["saldo"] * d["tasa"] / 1200.0]
    if sin_avance:
        st.warning("Con el pago mínimo no bajan: " + ", ".join(sin_avance) + ". El mínimo apenas cubre los intereses.")

    total = sum(d["saldo"] for d in con_saldo)
    if plan["completo"]:
        libre_en = _fecha_corta(_sumar_meses(hoy, plan["meses"]))
        ahorro = (base["interes"] - plan["interes"]) if base["completo"] else None
        sub = (f"Pagas {_dinero(plan['interes'])} de intereses"
               + (f" · te ahorras {_dinero(ahorro)} frente a solo pagar mínimos" if ahorro and ahorro > 1 else ""))
        valor, color = libre_en, VERDE
    else:
        valor, color = "Sin fecha de salida", GRIS
        sub = "Con estos pagos la deuda no se liquida en 50 años. Sube el pago extra o renegocia la tasa más alta."
    st.markdown(
        f"<div class='fp4-card notranslate' translate='no'><div class='fp4-titulo'>Libre de deudas · total {_dinero(total)}</div>"
        f"<div class='fp4-valor' style='color:{color};'>{valor}</div><div class='fp4-sub'>{sub}</div></div>",
        unsafe_allow_html=True)


# ==========================================
# 4. METAS CON APORTACIÓN CALCULADA (Punto 14)
# ==========================================
def _meta_bolsas(cur):
    cols = _columnas(cur, "fp_bolsas")
    return cols, (_elegir(cols, ("bolsa_id", "id")) or "nombre")


def _cargar_metas(db_conn, uid):
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        cols, id_col = _meta_bolsas(cur)
        if not cols:
            return [], False
        tiene_fecha = "fecha_objetivo" in cols
        cur.execute(
            sql.SQL("SELECT {id}::text, nombre, saldo_acumulado, monto_objetivo, {fecha}, aporte_periodo FROM fp_bolsas "
                    "WHERE user_id = %s AND activa AND UPPER(tipo::text) LIKE 'META%%' ORDER BY prioridad, nombre")
            .format(id=sql.Identifier(id_col), fecha=sql.SQL("fecha_objetivo") if tiene_fecha else sql.SQL("NULL::date")),
            (uid,))
        return cur.fetchall(), tiene_fecha


def _periodos_restantes(hoy, objetivo, frecuencia):
    if not objetivo or objetivo <= hoy:
        return 0
    dias = (objetivo - hoy).days
    if frecuencia == "SEMANAL":
        return max(1, math.ceil(dias / 7))
    if frecuencia == "QUINCENAL":
        return max(1, math.ceil(dias / 15.2))
    meses = (objetivo.year - hoy.year) * 12 + objetivo.month - hoy.month - (1 if objetivo.day < hoy.day else 0)
    return max(1, meses)


def _evaluar_meta(saldo, objetivo, fecha, aporte_actual, hoy, frecuencia):
    faltante = max(0.0, objetivo - saldo) if objetivo > 0 else 0.0
    if objetivo <= 0:
        return {"estado": "Sin monto", "color": TENUE, "requerido": None, "periodos": None, "faltante": 0.0}
    if faltante <= 0.005:
        return {"estado": "Lograda", "color": VERDE, "requerido": 0.0, "periodos": 0, "faltante": 0.0}
    if not fecha:
        return {"estado": "Sin fecha", "color": TENUE, "requerido": None, "periodos": None, "faltante": faltante}
    if fecha <= hoy:
        return {"estado": "Vencida", "color": GRIS, "requerido": faltante, "periodos": 0, "faltante": faltante}
    n = _periodos_restantes(hoy, fecha, frecuencia)
    requerido = round(faltante / n, 2)
    en_ruta = aporte_actual + 0.005 >= requerido
    return {"estado": "En ruta" if en_ruta else "Ajustar", "color": VERDE if en_ruta else ORO,
            "requerido": requerido, "periodos": n, "faltante": faltante}


def ui_metas_aportaciones(db_conn, uid):
    """Metas (fp_bolsas tipo META): edita monto y fecha objetivo y calcula el aporte por periodo."""
    _estilos()
    _mostrar_flash()
    if not _esquema_ok(db_conn):
        return
    hoy = _hoy()
    _cabecera("Tus metas",
              "Define cuánto y para cuándo. El sistema calcula cuánto apartar cada periodo para llegar a tiempo.")
    try:
        filas, tiene_fecha = _cargar_metas(db_conn, uid)
    except Exception:
        log.exception("Error leyendo metas")
        st.error("No pude leer tus metas en este momento.")
        return
    if not filas:
        st.caption("Aún no tienes metas. Desde Telegram: /apartar 500 viaje (o el nombre de tu meta).")
        return
    if not tiene_fecha:
        st.caption("La fecha objetivo aún no está disponible en tu base de datos; se calculará cuando se active.")

    frec_default = _frecuencia_usuario(db_conn, uid)
    frecuencia = st.segmented_control(
        "Aportas cada", options=list(_FRECUENCIAS), default=frec_default, key=f"fp4_met_frec_{uid}",
        format_func=lambda f: _TXT_PERIODO[f].capitalize(),
    ) if hasattr(st, "segmented_control") else st.selectbox(
        "Aportas cada", list(_FRECUENCIAS), index=_FRECUENCIAS.index(frec_default), key=f"fp4_met_frec_{uid}",
        format_func=lambda f: _TXT_PERIODO[f].capitalize())
    frecuencia = frecuencia or frec_default

    df = pd.DataFrame({
        "_id": pd.Series([f[0] for f in filas], dtype="object"),
        "Meta": pd.Series([f[1] for f in filas], dtype="object"),
        "Ahorrado": pd.Series([_f(f[2]) for f in filas], dtype="float"),
        "Monto objetivo": pd.Series([_f(f[3]) for f in filas], dtype="float"),
        "Fecha objetivo": pd.Series([_a_fecha(f[4]) for f in filas], dtype="object"),
        "Aporte actual": pd.Series([_f(f[5]) for f in filas], dtype="float"),
    })
    editado = st.data_editor(
        df, key=f"fp4_met_editor_{uid}_{_version('met', uid)}", hide_index=True, use_container_width=True,
        num_rows="fixed", disabled=["Meta", "Ahorrado", "Aporte actual"] + ([] if tiene_fecha else ["Fecha objetivo"]),
        column_config={
            "_id": None,
            "Ahorrado": st.column_config.NumberColumn("Ahorrado", format="$%.2f"),
            "Monto objetivo": st.column_config.NumberColumn("Monto objetivo", min_value=0.0, step=500.0, format="$%.2f"),
            "Fecha objetivo": st.column_config.DateColumn("Fecha objetivo", min_value=hoy, format="DD/MM/YYYY"),
            "Aporte actual": st.column_config.NumberColumn(f"Aporte por {_TXT_PERIODO[frecuencia]}", format="$%.2f"),
        })

    resultados, html = [], ""
    for _, fila in editado.iterrows():
        saldo, objetivo = _f(fila["Ahorrado"]), max(0.0, _f(fila["Monto objetivo"]))
        fecha, aporte = _a_fecha(fila["Fecha objetivo"]), _f(fila["Aporte actual"])
        ev = _evaluar_meta(saldo, objetivo, fecha, aporte, hoy, frecuencia)
        resultados.append((fila, objetivo, fecha, ev))
        avance = min(saldo / objetivo * 100, 100) if objetivo > 0 else 0
        if ev["estado"] in ("En ruta", "Ajustar"):
            detalle = (f"Aparta <b style='color:#e5e7eb;'>{_dinero(ev['requerido'])}</b> por {_TXT_PERIODO[frecuencia]} "
                       f"durante {ev['periodos']} {_TXT_PERIODO[frecuencia]}{'s' if ev['periodos'] != 1 else ''} "
                       f"hasta el {_fecha_corta(fecha)}")
            if ev["estado"] == "Ajustar":
                detalle += f" · hoy apartas {_dinero(aporte)}"
        elif ev["estado"] == "Vencida":
            detalle = f"La fecha ya pasó y faltan {_dinero(ev['faltante'])}. Elige una nueva fecha."
        elif ev["estado"] == "Lograda":
            detalle = "Meta cumplida."
        elif ev["estado"] == "Sin fecha":
            detalle = f"Faltan {_dinero(ev['faltante'])}. Agrega una fecha para calcular tu aporte."
        else:
            detalle = "Agrega un monto objetivo."
        html += (f"<div class='fp4-fila' style='display:block;'><div style='display:flex;justify-content:space-between;'>"
                 f"<span>{fila['Meta']}<span class='fp4-chip' style='color:{ev['color']};border-color:{ev['color']}55;'>"
                 f"{ev['estado']}</span></span><span style='color:{ORO};'>{_dinero(saldo)}"
                 f"<span class='fp4-sub'> de {_dinero(objetivo) if objetivo else '—'}</span></span></div>"
                 f"<div class='fp4-sub'>{detalle}</div><div class='fp4-mini'><div style='width:{avance:.1f}%;'></div></div></div>")
    st.markdown(f"<div class='fp4-card notranslate' translate='no'>{html}</div>", unsafe_allow_html=True)

    aplicar = st.checkbox(f"Usar el aporte calculado como mi aporte por {_TXT_PERIODO[frecuencia]}",
                          key=f"fp4_met_aplicar_{uid}",
                          help="Actualiza el aporte de cada bolsa; tu Dinero Libre se recalcula con ese monto.")
    if st.button("Guardar metas", key=f"fp4_met_guardar_{uid}", type="primary", use_container_width=True):
        try:
            with _abrir(db_conn) as conn, conn.cursor() as cur:
                _, id_col = _meta_bolsas(cur)
                for fila, objetivo, fecha, ev in resultados:
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
            log.exception("Error guardando metas")
            st.error("No pude guardar tus metas. Inténtalo de nuevo en un momento.")
            return
        _reiniciar_editor("met", uid)
        _flash("Metas actualizadas.")
        st.rerun()


# ==========================================
# 5. ATAJOS DE INTEGRACIÓN (tabs y diálogos)
# ==========================================
def ui_planificacion(db_conn, uid):
    """Las 3 interfaces en tabs, listas para colocarse debajo de 'Tu dinero hoy'."""
    tab_rep, tab_deu, tab_met = st.tabs(["Reparto del ingreso", "Deudas", "Metas"])
    with tab_rep:
        ui_cascada_ingresos(db_conn, uid)
    with tab_deu:
        ui_control_deudas(db_conn, uid)
    with tab_met:
        ui_metas_aportaciones(db_conn, uid)


_DIALOGO = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)


def _como_dialogo(titulo):
    def deco(fn):
        if _DIALOGO is None:
            return fn
        try:
            return _DIALOGO(titulo, width="large")(fn)
        except TypeError:
            return _DIALOGO(titulo)(fn)
    return deco


@_como_dialogo("Reparto de tu ingreso")
def _dlg_cascada(db_conn, uid):
    ui_cascada_ingresos(db_conn, uid)


@_como_dialogo("Tus deudas")
def _dlg_deudas(db_conn, uid):
    ui_control_deudas(db_conn, uid)


@_como_dialogo("Tus metas")
def _dlg_metas(db_conn, uid):
    ui_metas_aportaciones(db_conn, uid)


def _boton(db_conn, uid, etiqueta, clave, dialogo, ayuda, contenedor):
    _mostrar_flash()
    destino = contenedor or st
    if destino.button(etiqueta, key=f"fp4_btn_{clave}_{uid}", help=ayuda, use_container_width=True):
        dialogo(db_conn, uid)


def ui_boton_cascada(db_conn, uid, etiqueta="Reparto", contenedor=None):
    _boton(db_conn, uid, etiqueta, "cas", _dlg_cascada, "Cómo se reparte tu próximo ingreso.", contenedor)


def ui_boton_deudas(db_conn, uid, etiqueta="Deudas", contenedor=None):
    _boton(db_conn, uid, etiqueta, "deu", _dlg_deudas, "Tus deudas en orden de Avalancha.", contenedor)


def ui_boton_metas(db_conn, uid, etiqueta="Metas", contenedor=None):
    _boton(db_conn, uid, etiqueta, "met", _dlg_metas, "Monto, fecha y aporte de tus metas.", contenedor)
