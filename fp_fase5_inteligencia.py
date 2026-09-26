"""
fp_fase5_inteligencia.py — APortafolio FP · Fase 5 · Inteligencia accionable y puente a Terminal

Módulo AISLADO (Norma 2): no importa nada de app.py ni de main.py. Recibe `db_conn` (context manager de app.py).
Exporta:
  • siguiente_mejor_accion(db_conn, uid)   · Punto 18 · UNA acción principal, determinista y justificada
  • semaforo_preparacion(db_conn, uid)     · Punto 17 · LISTO / EN CONSTRUCCIÓN / PRIORIDAD + checklist
  • evaluar_inteligencia(db_conn, uid)     · ambas con una sola lectura de datos (lo que usa la UI)
  • ui_panel_inteligencia(db_conn, uid)    · panel Streamlit Quiet Luxury
Solo LEE datos: no crea tablas ni mueve dinero. Nunca inventa cifras: si falta un dato, la regla que lo
necesita no se evalúa y el checklist lo marca como pendiente.

Fuentes (todas ya existentes): fp_dinero_libre(), fp_ocurrencias(), fp_bolsas, fp_deudas (Fase 4),
fp_compromisos_programados (respaldo), fp_financial_ledger, users.dca_frequency, transactions (Terminal).
"""
from __future__ import annotations

import html
import logging
import math
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import streamlit as st

log = logging.getLogger("apportafolio_fp.fase5")

ZONA_MX = timezone(timedelta(hours=-6))

# ---- Umbrales del modelo (ajustables sin tocar la lógica) ----
TASA_CARA = 10.0          # % anual: por encima, la deuda compite con cualquier inversión
TASA_TOXICA = 30.0        # % anual: bloquea el semáforo
COLCHON_MINIMO = 1.0      # meses de compromisos para abrir la Terminal
COLCHON_IDEAL = 3.0       # meses recomendados
MINIMO_ACCION = 500.0     # MXN: por debajo, no vale la pena mover dinero
DIAS_HISTORIAL = 30       # días de registros para un diagnóstico confiable
DEFICIT_CRITICO = 0.10    # déficit > 10% del ingreso mensual = crítico

ORO, VERDE, GRIS, TERRACOTA, TENUE = "#d4af37", "#34d399", "#94a3b8", "#e07a5f", "#64748b"
_PERIODO_TXT = {"SEMANAL": ("semana", "semanas"), "QUINCENAL": ("quincena", "quincenas"), "MENSUAL": ("mes", "meses")}
_PERIODOS_EN_6_MESES = {"SEMANAL": 26, "QUINCENAL": 12, "MENSUAL": 6}
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

_ESTADOS_SEMAFORO = {
    "LISTO":           {"icono": "🟢", "etiqueta": "Listo para invertir", "color": VERDE},
    "EN_CONSTRUCCION": {"icono": "🟡", "etiqueta": "En construcción",     "color": ORO},
    "PRIORIDAD":       {"icono": "🔴", "etiqueta": "Prioridad: cimientos", "color": TERRACOTA},
}
_NIVELES = {  # alertas de 4 niveles del Blueprint (punto 15)
    "RIESGO": ("Riesgo", TERRACOTA), "ATENCION": ("Atención", ORO),
    "OPORTUNIDAD": ("Oportunidad", VERDE), "NORMAL": ("En orden", GRIS),
}

__all__ = ["siguiente_mejor_accion", "semaforo_preparacion", "evaluar_inteligencia", "ui_panel_inteligencia",
           "recolectar_contexto"]


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


def _opcional(conn, nombre, fn, default):
    """Cada fuente se lee aislada en un SAVEPOINT: si falla, se omite sin tumbar el resto."""
    usar_sp = not getattr(conn, "autocommit", False)
    with conn.cursor() as cur:
        try:
            if usar_sp:
                cur.execute("SAVEPOINT fp_f5")
            resultado = fn(cur)
            if usar_sp:
                cur.execute("RELEASE SAVEPOINT fp_f5")
            return resultado
        except Exception:
            log.warning("Fuente '%s' no disponible; se omite.", nombre, exc_info=True)
            if usar_sp:
                try:
                    cur.execute("ROLLBACK TO SAVEPOINT fp_f5")
                except Exception:
                    pass
            return default


def _columnas(cur, tabla):
    cur.execute("SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = ANY(current_schemas(false))", (tabla,))
    return {n: t for n, t in cur.fetchall()}


def _elegir(cols, candidatos):
    return next((c for c in candidatos if c in cols), None)


def _hoy():
    return datetime.now(ZONA_MX).date()


def _f(valor, default=0.0):
    try:
        if valor is None:
            return default
        v = float(valor)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def _dinero(valor):
    v = round(_f(valor), 2)
    signo, v = ("-" if v < 0 else ""), abs(v)
    return f"{signo}${v:,.0f}" if v == int(v) else f"{signo}${v:,.2f}"


def _fecha_corta(d):
    return f"{d.day} {_MESES[d.month - 1]}"


def _abajo(valor, paso=100.0):
    return math.floor(max(0.0, valor) / paso) * paso


def _arriba(valor, paso=50.0):
    return math.ceil(max(0.0, valor) / paso) * paso


def _es_colchon(tipo, nombre):
    t = _norm(f"{tipo} {nombre}")
    return "colchon" in t or "emergencia" in t


def _es_meta(tipo):
    return _norm(tipo).startswith("meta")


# ==========================================
# 2. LECTURA DE DATOS (solo lectura)
# ==========================================
def _q_dinero_libre(cur, uid, hoy):
    cur.execute("SELECT * FROM fp_dinero_libre(%s, %s)", (uid, hoy))
    fila = cur.fetchone()
    if not fila:
        return None
    dl = dict(zip([d[0] for d in cur.description], fila))
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in dl.items()}


def _q_ocurrencias(cur, uid, hoy, hasta):
    cur.execute("SELECT fecha, nombre, tipo_movimiento, monto FROM fp_ocurrencias(%s, %s, %s) ORDER BY fecha",
                (uid, hoy, hasta + timedelta(days=1)))
    return [{"fecha": f, "nombre": n or "Compromiso", "tipo": (t or "").upper(), "monto": _f(m)}
            for f, n, t, m in cur.fetchall() if f and hoy <= f <= hasta]


def _q_compromisos_tabla(cur, uid):
    """Respaldo si fp_ocurrencias no existe: suma mensual aproximada de compromisos activos."""
    cols = _columnas(cur, "fp_compromisos_programados")
    monto = _elegir(cols, ("monto", "monto_estimado", "importe", "monto_mxn"))
    if not cols or "user_id" not in cols or not monto:
        return None
    where, params = ["user_id::text = %s"], [str(uid)]
    tipo = _elegir(cols, ("tipo", "tipo_compromiso", "tipo_movimiento"))
    if tipo:
        where.append(f"UPPER(COALESCE({tipo}::text, '')) NOT IN ('INGRESO', 'INGRESO_RECURRENTE', 'NOMINA', 'SALARIO')")
    activo = _elegir(cols, ("activo", "activa"))
    if activo and cols[activo] == "boolean":
        where.append(f"COALESCE({activo}, TRUE)")
    estado = _elegir(cols, ("estado", "status"))
    if estado:
        where.append(f"UPPER(COALESCE({estado}::text, '')) NOT IN ('CANCELADO', 'INACTIVO', 'PAUSADO', 'LIQUIDADO', 'ARCHIVADO')")
    # Identificadores provienen de information_schema (lista blanca de candidatos), no del usuario.
    cur.execute(f"SELECT COALESCE(SUM({monto}), 0) FROM fp_compromisos_programados WHERE {' AND '.join(where)}", params)
    return _f(cur.fetchone()[0])


def _q_bolsas(cur, uid):
    cols = _columnas(cur, "fp_bolsas")
    fecha = "fecha_objetivo" if "fecha_objetivo" in cols else "NULL::date"
    cur.execute(f"SELECT nombre, tipo, aporte_periodo, saldo_acumulado, monto_objetivo, {fecha} "
                "FROM fp_bolsas WHERE user_id = %s AND activa ORDER BY prioridad, nombre", (uid,))
    return [{"nombre": n or "Bolsa", "tipo": t or "", "aporte": _f(a), "saldo": _f(s),
             "objetivo": _f(o), "fecha_objetivo": fo} for n, t, a, s, o, fo in cur.fetchall()]


def _q_deudas(cur, uid):
    cur.execute("SELECT nombre, saldo_actual, tasa_anual, pago_minimo FROM fp_deudas "
                "WHERE user_id = %s AND COALESCE(activa, TRUE) AND saldo_actual > 0", (uid,))
    return [{"nombre": n or "Deuda", "saldo": _f(s), "tasa": _f(t), "minimo": _f(m)} for n, s, t, m in cur.fetchall()]


def _q_flujo(cur, uid, hoy):
    cols = _columnas(cur, "fp_financial_ledger")
    filtro_var = "compromiso_id IS NULL" if "compromiso_id" in cols else "TRUE"
    base = ("FROM fp_financial_ledger WHERE user_id = %s AND COALESCE(estado, '') <> 'DESCARTADO' "
            "AND tipo_movimiento IN ('GASTO', 'INGRESO')")
    cur.execute(f"SELECT MIN(fecha::date) {base}", (uid,))
    primera = cur.fetchone()[0]
    d90, d30 = hoy - timedelta(days=89), hoy - timedelta(days=29)
    cur.execute(
        f"""
        SELECT COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'INGRESO' AND fecha::date >= %s), 0),
               COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'GASTO'   AND fecha::date >= %s), 0),
               COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'GASTO' AND {filtro_var} AND fecha::date >= %s), 0)
        {base} AND COALESCE(moneda, 'MXN') = 'MXN' AND fecha::date <= %s
        """,
        (d90, d90, d30, uid, hoy))
    ing90, gas90, var30 = (_f(x) for x in cur.fetchone())
    dias = (hoy - primera).days + 1 if primera else 0
    meses_eq = max(1.0, min(90, dias) / 30.44) if dias else 1.0
    return {
        "dias_historial": dias,
        "ingreso_mensual": ing90 / meses_eq,
        "gasto_mensual": gas90 / meses_eq,
        "gasto_variable_diario": var30 / max(1, min(30, dias)) if dias else 0.0,
    }


def _q_frecuencia(cur, uid):
    cur.execute("SELECT dca_frequency FROM users WHERE user_id = %s", (uid,))
    fila = cur.fetchone()
    f = str((fila[0] if fila else "") or "").upper()
    return f if f in _PERIODO_TXT else "QUINCENAL"


def _q_terminal(cur, uid):
    cur.execute("SELECT to_regclass('public.transactions') IS NOT NULL")
    if not cur.fetchone()[0]:
        return 0
    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (uid,))
    return int(cur.fetchone()[0] or 0)


def recolectar_contexto(db_conn, uid, hoy=None):
    """Una sola conexión; cada fuente es opcional. Devuelve el contexto crudo."""
    hoy = hoy or _hoy()
    ctx = {"hoy": hoy}
    with _abrir(db_conn) as conn:
        ctx["dl"] = _opcional(conn, "fp_dinero_libre", lambda c: _q_dinero_libre(c, uid, hoy), None)
        ctx["ocurrencias"] = _opcional(conn, "fp_ocurrencias", lambda c: _q_ocurrencias(c, uid, hoy, hoy + timedelta(days=30)), None)
        ctx["compromisos_tabla"] = (_opcional(conn, "fp_compromisos_programados", lambda c: _q_compromisos_tabla(c, uid), None)
                                    if ctx["ocurrencias"] is None else None)
        ctx["bolsas"] = _opcional(conn, "fp_bolsas", lambda c: _q_bolsas(c, uid), [])
        ctx["deudas"] = _opcional(conn, "fp_deudas", lambda c: _q_deudas(c, uid), [])
        ctx["flujo"] = _opcional(conn, "fp_financial_ledger", lambda c: _q_flujo(c, uid, hoy), None)
        ctx["frecuencia"] = _opcional(conn, "users", lambda c: _q_frecuencia(c, uid), "QUINCENAL")
        ctx["operaciones_terminal"] = _opcional(conn, "transactions", lambda c: _q_terminal(c, uid), 0)
    return ctx


# ==========================================
# 3. MÉTRICAS (puras, sin BD)
# ==========================================
def _periodos_hasta(hoy, objetivo, frecuencia):
    dias = (objetivo - hoy).days
    if dias <= 0:
        return 0
    if frecuencia == "SEMANAL":
        return max(1, math.ceil(dias / 7))
    if frecuencia == "QUINCENAL":
        return max(1, math.ceil(dias / 15.2))
    meses = (objetivo.year - hoy.year) * 12 + objetivo.month - hoy.month - (1 if objetivo.day < hoy.day else 0)
    return max(1, meses)


def calcular_metricas(ctx):
    hoy, dl, flujo = ctx["hoy"], ctx.get("dl"), ctx.get("flujo") or {}
    ocurr = ctx.get("ocurrencias")
    deudas = sorted(ctx.get("deudas") or [], key=lambda d: (-d["tasa"], d["saldo"]))  # orden Avalancha
    bolsas = ctx.get("bolsas") or []
    frecuencia = ctx.get("frecuencia") or "QUINCENAL"

    compromisos_30 = (sum(o["monto"] for o in ocurr if o["tipo"] != "INGRESO") if ocurr is not None
                      else ctx.get("compromisos_tabla"))
    minimos = sum(d["minimo"] for d in deudas)
    compromiso_mensual = compromisos_30 if compromisos_30 and compromisos_30 > 0 else minimos
    proximos_7 = [o for o in (ocurr or []) if o["tipo"] != "INGRESO" and o["fecha"] <= hoy + timedelta(days=7)]

    colchones = [b for b in bolsas if _es_colchon(b["tipo"], b["nombre"])]
    colchon = sum(b["saldo"] for b in colchones)
    cobertura = colchon / compromiso_mensual if compromiso_mensual > 0 else None

    con_base = bool(dl) and dl.get("estado") != "SIN_BASE"
    dinero_libre = _f(dl.get("dinero_libre")) if con_base else None
    dias_restantes = int(_f(dl.get("dias_restantes"), 0)) if con_base else 0
    reserva_gasto = flujo.get("gasto_variable_diario", 0.0) * dias_restantes
    excedente = max(0.0, dinero_libre) if dinero_libre is not None else 0.0
    transferible = _abajo(excedente - reserva_gasto)

    dias_hist = flujo.get("dias_historial", 0)
    ingreso_m, gasto_m = flujo.get("ingreso_mensual", 0.0), flujo.get("gasto_mensual", 0.0)
    superavit = (ingreso_m - gasto_m) if dias_hist >= DIAS_HISTORIAL and ingreso_m > 0 else None

    metas_atrasadas = []
    for b in bolsas:
        if not _es_meta(b["tipo"]) or b["objetivo"] <= 0 or b["saldo"] >= b["objetivo"]:
            continue
        fo = b["fecha_objetivo"]
        if not isinstance(fo, date):
            continue
        faltante = b["objetivo"] - b["saldo"]
        n = _periodos_hasta(hoy, fo, frecuencia)
        if n == 0:
            metas_atrasadas.append({**b, "vencida": True, "faltante": faltante, "requerido": faltante, "periodos": 0, "brecha": faltante})
            continue
        requerido = _arriba(faltante / n, 10)
        if b["aporte"] + 0.5 < requerido:
            metas_atrasadas.append({**b, "vencida": False, "faltante": faltante, "requerido": requerido,
                                    "periodos": n, "brecha": requerido - b["aporte"]})
    metas_atrasadas.sort(key=lambda m: (not m["vencida"], -m["brecha"]))

    return {
        "hoy": hoy, "frecuencia": frecuencia, "dl": dl, "con_base": con_base,
        "dinero_libre": dinero_libre, "dias_restantes": dias_restantes, "proximo_ingreso": (dl or {}).get("proximo_ingreso"),
        "excedente": excedente, "reserva_gasto": reserva_gasto, "transferible": transferible,
        "compromiso_mensual": compromiso_mensual, "compromisos_medidos": compromiso_mensual > 0, "proximos_7": proximos_7,
        "colchon": colchon, "tiene_bolsa_colchon": bool(colchones), "cobertura": cobertura,
        "deudas": deudas, "deudas_caras": [d for d in deudas if d["tasa"] > TASA_CARA],
        "deudas_toxicas": [d for d in deudas if d["tasa"] >= TASA_TOXICA],
        "deudas_sin_avance": [d for d in deudas if d["tasa"] > 0 and d["minimo"] <= d["saldo"] * d["tasa"] / 1200.0],
        "dias_historial": dias_hist, "ingreso_mensual": ingreso_m, "gasto_mensual": gasto_m, "superavit": superavit,
        "metas_atrasadas": metas_atrasadas, "operaciones_terminal": ctx.get("operaciones_terminal") or 0,
    }


# ==========================================
# 4. SEMÁFORO DE PREPARACIÓN + CHECKLIST (Punto 17)
# ==========================================
def _item(clave, titulo, estado, detalle, bloqueante=True):
    return {"clave": clave, "titulo": titulo, "estado": estado, "detalle": detalle, "bloqueante": bloqueante}


def _semaforo(m):
    items = []

    dias = m["dias_historial"]
    items.append(_item("HISTORIAL", f"Al menos {DIAS_HISTORIAL} días de registros",
                       "OK" if dias >= DIAS_HISTORIAL else "PENDIENTE",
                       f"Llevas {dias} día{'s' if dias != 1 else ''} registrando." if dias < DIAS_HISTORIAL
                       else "Hay historial suficiente para medir tus hábitos."))

    if m["dinero_libre"] is None:
        items.append(_item("LIQUIDEZ", "Sin sobregiro en el periodo", "PENDIENTE",
                           "Declara tu saldo o registra tu ingreso para medirlo."))
    elif m["dinero_libre"] < 0:
        items.append(_item("LIQUIDEZ", "Sin sobregiro en el periodo", "CRITICO",
                           f"Vas {_dinero(-m['dinero_libre'])} por encima de lo que te alcanza."))
    else:
        items.append(_item("LIQUIDEZ", "Sin sobregiro en el periodo", "OK",
                           f"{_dinero(m['dinero_libre'])} libres hasta tu próximo ingreso."))

    caras = m["deudas_caras"]
    if not caras:
        items.append(_item("DEUDA", f"Sin deudas con tasa mayor a {TASA_CARA:.0f}%", "OK",
                           "Ninguna deuda cara." if m["deudas"] else "No tienes deudas registradas."))
    else:
        total = sum(d["saldo"] for d in caras)
        critico = bool(m["deudas_toxicas"] or m["deudas_sin_avance"])
        items.append(_item("DEUDA", f"Sin deudas con tasa mayor a {TASA_CARA:.0f}%", "CRITICO" if critico else "PENDIENTE",
                           f"{len(caras)} deuda{'s' if len(caras) != 1 else ''} cara{'s' if len(caras) != 1 else ''} "
                           f"por {_dinero(total)}; la más alta cobra {caras[0]['tasa']:.1f}% anual."))

    if not m["compromisos_medidos"]:
        items.append(_item("COLCHON", "Colchón de al menos 1 mes de compromisos", "PENDIENTE",
                           "Programa tus pagos fijos para poder medir tu cobertura."))
    else:
        cob = m["cobertura"] or 0.0
        estado = "OK" if cob >= COLCHON_MINIMO else ("PENDIENTE" if cob > 0 else "CRITICO")
        items.append(_item("COLCHON", "Colchón de al menos 1 mes de compromisos", estado,
                           f"Tu colchón de {_dinero(m['colchon'])} cubre {cob:.1f} meses de "
                           f"{_dinero(m['compromiso_mensual'])} mensuales."))

    sup = m["superavit"]
    if sup is None:
        items.append(_item("SUPERAVIT", "Superávit mensual", "PENDIENTE",
                           "Se mide con 30 días de ingresos y gastos registrados."))
    else:
        critico = sup < 0 and abs(sup) > m["ingreso_mensual"] * DEFICIT_CRITICO
        items.append(_item("SUPERAVIT", "Superávit mensual", "OK" if sup > 0 else ("CRITICO" if critico else "PENDIENTE"),
                           f"En promedio entran {_dinero(m['ingreso_mensual'])} y salen {_dinero(m['gasto_mensual'])} "
                           f"al mes ({'+' if sup >= 0 else ''}{_dinero(sup)})."))

    # --- Recomendaciones (no bloquean la Terminal) ---
    atrasadas = m["metas_atrasadas"]
    items.append(_item("METAS", "Metas al día", "OK" if not atrasadas else "PENDIENTE",
                       "Tus metas van en ruta." if not atrasadas
                       else f"{len(atrasadas)} meta{'s' if len(atrasadas) != 1 else ''} por debajo del aporte necesario.",
                       bloqueante=False))
    if m["compromisos_medidos"]:
        cob = m["cobertura"] or 0.0
        items.append(_item("COLCHON_IDEAL", f"Colchón ideal de {COLCHON_IDEAL:.0f} meses",
                           "OK" if cob >= COLCHON_IDEAL else "PENDIENTE",
                           f"Meta: {_dinero(m['compromiso_mensual'] * COLCHON_IDEAL)}.", bloqueante=False))
    items.append(_item("TERMINAL", "Terminal activada", "OK" if m["operaciones_terminal"] else "PENDIENTE",
                       f"{m['operaciones_terminal']} operaciones registradas." if m["operaciones_terminal"]
                       else "Aún sin operaciones de inversión.", bloqueante=False))

    bloqueantes = [i for i in items if i["bloqueante"]]
    if any(i["estado"] == "CRITICO" for i in bloqueantes):
        estado = "PRIORIDAD"
        primero = next(i for i in bloqueantes if i["estado"] == "CRITICO")
        resumen = f"Antes de invertir, atiende: {primero['titulo'].lower()}."
    elif all(i["estado"] == "OK" for i in bloqueantes):
        estado = "LISTO"
        resumen = "Tus cimientos sostienen una inversión constante. La Terminal está abierta para ti."
    else:
        estado = "EN_CONSTRUCCION"
        faltan = sum(1 for i in bloqueantes if i["estado"] != "OK")
        resumen = f"Vas bien. Falta{'n' if faltan != 1 else ''} {faltan} criterio{'s' if faltan != 1 else ''} para abrir la Terminal con seguridad."
    return {"estado": estado, **_ESTADOS_SEMAFORO[estado], "resumen": resumen,
            "cumplidos": sum(1 for i in bloqueantes if i["estado"] == "OK"), "total": len(bloqueantes),
            "checklist": items}


# ==========================================
# 5. SIGUIENTE MEJOR ACCIÓN (Punto 18) · escalera determinista
# ==========================================
def _accion(codigo, nivel, titulo, detalle, monto=None, evidencia=None, destino=None):
    return {"codigo": codigo, "nivel": nivel, "titulo": titulo, "detalle": detalle, "monto": monto,
            "evidencia": evidencia or [], "destino": destino}


def _r_sobregiro(m, s):
    if m["dinero_libre"] is None or m["dinero_libre"] >= 0:
        return None
    exceso = -m["dinero_libre"]
    hasta = f"el {_fecha_corta(m['proximo_ingreso'])}" if isinstance(m["proximo_ingreso"], date) else "tu próximo ingreso"
    detalle = (f"Hasta {hasta} ya gastaste {_dinero(exceso)} más de lo que te alcanza después de pagos fijos y apartados.")
    if m["proximos_7"]:
        p = m["proximos_7"][0]
        detalle += f" Además vence {p['nombre']} ({_dinero(p['monto'])}) el {_fecha_corta(p['fecha'])}."
    detalle += " Mantén el gasto variable al mínimo los días que faltan para equilibrarlo."
    return _accion("SOBREGIRO", "RIESGO", f"Frena el gasto variable: vas {_dinero(exceso)} arriba", detalle, exceso,
                   [("Dinero libre", _dinero(m["dinero_libre"])), ("Días restantes", str(m["dias_restantes"]))])


def _r_deuda_sin_avance(m, s):
    if not m["deudas_sin_avance"]:
        return None
    d = max(m["deudas_sin_avance"], key=lambda x: x["tasa"])
    interes = d["saldo"] * d["tasa"] / 1200.0
    pago = _arriba(interes + d["saldo"] * 0.01, 50)  # interés + 1% del saldo: empieza a amortizar
    return _accion("DEUDA_SIN_AVANCE", "RIESGO", f"Sube el pago de {d['nombre']} a {_dinero(pago)} al mes",
                   f"Con el mínimo de {_dinero(d['minimo'])} no cubres los {_dinero(interes)} de interés mensual "
                   f"({d['tasa']:.1f}% anual): la deuda crece aunque pagues. Con {_dinero(pago)} el saldo empieza a bajar.",
                   pago, [("Saldo", _dinero(d["saldo"])), ("Tasa anual", f"{d['tasa']:.1f}%"), ("Interés/mes", _dinero(interes))])


def _r_sin_base(m, s):
    if m["con_base"]:
        return None
    return _accion("SIN_BASE", "ATENCION", "Declara tu saldo de hoy",
                   "Sin un punto de partida no puedo calcular cuánto puedes gastar ni cuánto te sobra. "
                   "Escribe tu saldo en 'Tu dinero hoy' o registra tu próximo ingreso y el diagnóstico se completa solo.")


def _r_colchon_minimo(m, s):
    if not m["compromisos_medidos"] or (m["cobertura"] or 0) >= COLCHON_MINIMO:
        return None
    faltante = m["compromiso_mensual"] * COLCHON_MINIMO - m["colchon"]
    evid = [("Colchón", _dinero(m["colchon"])), ("1 mes de compromisos", _dinero(m["compromiso_mensual"]))]
    base = (f"Tu colchón cubre {(m['cobertura'] or 0) * 100:.0f}% de un mes de compromisos. "
            "Un mes completo evita que un imprevisto termine en la tarjeta de crédito.")
    crear = "" if m["tiene_bolsa_colchon"] else " Crea la bolsa desde Telegram: /apartar 500 colchón."
    monto = _abajo(min(faltante, m["transferible"]))
    if monto >= 100:
        return _accion("COLCHON_MINIMO", "ATENCION", f"Fondea tu Colchón con {_dinero(monto)}",
                       f"{base} Después de reservar {_dinero(m['reserva_gasto'])} para tu gasto habitual, "
                       f"te sobran {_dinero(m['transferible'])} en este periodo.{crear}", monto, evid)
    n = _PERIODOS_EN_6_MESES[m["frecuencia"]]
    aporte = _arriba(faltante / n, 50)
    singular = _PERIODO_TXT[m["frecuencia"]][0]
    return _accion("COLCHON_MINIMO", "ATENCION", f"Aparta {_dinero(aporte)} por {singular} para tu Colchón",
                   f"{base} Con ese aporte lo completas en 6 meses sin apretar tu gasto diario.{crear}", aporte, evid)


def _r_deuda_cara(m, s):
    if not m["deudas_caras"]:
        return None
    d = m["deudas_caras"][0]  # Avalancha: tasa más alta
    extra = _abajo(min(m["transferible"], d["saldo"]))
    evid = [("Saldo", _dinero(d["saldo"])), ("Tasa anual", f"{d['tasa']:.1f}%")]
    if extra >= 100:
        ahorro = extra * d["tasa"] / 1200.0
        return _accion("DEUDA_CARA", "ATENCION", f"Paga {_dinero(extra)} extra a {d['nombre']}",
                       f"Es tu deuda más cara ({d['tasa']:.1f}% anual). Abonarle equivale a un rendimiento sin riesgo "
                       f"de {d['tasa']:.1f}%, más de lo que ofrece una inversión conservadora. Este abono te ahorra "
                       f"{_dinero(ahorro)} de interés cada mes. Ya reservé {_dinero(m['reserva_gasto'])} para tu gasto habitual.",
                       extra, evid + [("Ahorro/mes", _dinero(ahorro))])
    sup = m["superavit"]
    detalle = f"Es tu deuda más cara ({d['tasa']:.1f}% anual). Estrategia Avalancha: mínimo a todas y cada peso extra aquí."
    if sup and sup > 0:
        detalle += f" Tu superávit promedio es {_dinero(sup)} al mes; ese es el monto ideal para abonarle."
    return _accion("DEUDA_CARA", "ATENCION", f"Concentra todo pago extra en {d['nombre']}", detalle, None, evid)


def _r_meta_atrasada(m, s):
    if not m["metas_atrasadas"]:
        return None
    mt = m["metas_atrasadas"][0]
    sing, plur = _PERIODO_TXT[m["frecuencia"]]
    evid = [("Ahorrado", _dinero(mt["saldo"])), ("Objetivo", _dinero(mt["objetivo"]))]
    if mt["vencida"]:
        return _accion("META_VENCIDA", "ATENCION", f"Reprograma tu meta {mt['nombre']}",
                       f"La fecha objetivo ya pasó y faltan {_dinero(mt['faltante'])}. Elige una fecha realista en "
                       "Planificación → Metas y el sistema recalcula tu aporte.", None, evid)
    return _accion("META_ATRASADA", "ATENCION", f"Sube tu aporte a {mt['nombre']} a {_dinero(mt['requerido'])} por {sing}",
                   f"Para juntar {_dinero(mt['objetivo'])} el {_fecha_corta(mt['fecha_objetivo'])} te faltan "
                   f"{_dinero(mt['faltante'])} en {mt['periodos']} {plur if mt['periodos'] != 1 else sing}. "
                   f"Hoy apartas {_dinero(mt['aporte'])}.", mt["requerido"], evid)


def _r_invertir(m, s):
    if s["estado"] != "LISTO" or m["transferible"] < MINIMO_ACCION:
        return None
    t = m["transferible"]
    return _accion("INVERTIR", "OPORTUNIDAD", f"Tienes {_dinero(t)} libres: transfiérelos a Terminal",
                   f"Ya descontados tus compromisos, tus apartados y {_dinero(m['reserva_gasto'])} para tu gasto habitual "
                   f"de los {m['dias_restantes']} días que faltan, sobran {_dinero(t)}. Tus cimientos están listos: "
                   "invertirlos de forma constante hace crecer tu patrimonio. Regístralo como transferencia, no como gasto.",
                   t, [("Dinero libre", _dinero(m["dinero_libre"])), ("Reserva de gasto", _dinero(m["reserva_gasto"]))],
                   destino="TERMINAL")


def _r_colchon_ideal(m, s):
    if not m["compromisos_medidos"] or (m["cobertura"] or 0) >= COLCHON_IDEAL or m["transferible"] < MINIMO_ACCION:
        return None
    monto = _abajo(min(m["transferible"], m["compromiso_mensual"] * COLCHON_IDEAL - m["colchon"]))
    if monto < 100:
        return None
    return _accion("COLCHON_IDEAL", "OPORTUNIDAD", f"Suma {_dinero(monto)} a tu Colchón",
                   f"Ya cubres {m['cobertura']:.1f} meses de compromisos. Llegar a {COLCHON_IDEAL:.0f} meses te da margen "
                   "para invertir sin tener que vender en un mal momento.", monto,
                   [("Colchón", _dinero(m["colchon"])), ("Meta 3 meses", _dinero(m["compromiso_mensual"] * COLCHON_IDEAL))])


def _r_historial(m, s):
    if m["dias_historial"] >= DIAS_HISTORIAL:
        return None
    faltan = DIAS_HISTORIAL - m["dias_historial"]
    return _accion("HISTORIAL", "NORMAL", "Sigue registrando tus movimientos",
                   f"Faltan {faltan} días para tu primer diagnóstico completo de ingresos y gastos. "
                   "Un mensaje por Telegram basta: \"42 pasaje\".")


def _r_mantener(m, s):
    detalle = "Tus números están en orden y no hay nada urgente."
    if m["proximos_7"]:
        p = m["proximos_7"][0]
        detalle += f" Tu próximo pago fijo es {p['nombre']} ({_dinero(p['monto'])}) el {_fecha_corta(p['fecha'])}; ya está contemplado."
    return _accion("MANTENER", "NORMAL", "Mantén el rumbo", detalle)


# Orden de la escalera = prioridad financiera (liquidez → deuda que crece → base de datos → colchón mínimo
# → deuda cara → metas → inversión → colchón ideal → hábito → mantener).
_ESCALERA = (_r_sobregiro, _r_deuda_sin_avance, _r_sin_base, _r_colchon_minimo, _r_deuda_cara,
             _r_meta_atrasada, _r_invertir, _r_colchon_ideal, _r_historial, _r_mantener)


def _nba(m, s):
    candidatas = []
    for posicion, regla in enumerate(_ESCALERA, start=1):
        try:
            a = regla(m, s)
        except Exception:
            log.exception("Regla %s falló; se omite.", regla.__name__)
            a = None
        if a:
            a["prioridad"] = posicion  # 1 = más urgente
            candidatas.append(a)
    principal = candidatas[0] if candidatas else {**_r_mantener(m, s), "prioridad": len(_ESCALERA)}
    familia = principal["codigo"].split("_")[0]
    siguiente = next((c for c in candidatas[1:] if c["codigo"].split("_")[0] != familia and c["codigo"] != "MANTENER"), None)
    principal["despues"] = siguiente["titulo"] if siguiente else None
    return principal


# ==========================================
# 6. API PÚBLICA
# ==========================================
def evaluar_inteligencia(db_conn, uid, hoy=None):
    """Una sola lectura de datos → {'accion', 'semaforo', 'metricas'}."""
    m = calcular_metricas(recolectar_contexto(db_conn, uid, hoy))
    s = _semaforo(m)
    return {"accion": _nba(m, s), "semaforo": s, "metricas": m}


def siguiente_mejor_accion(db_conn, uid, hoy=None):
    """Punto 18 · devuelve UNA acción: {codigo, nivel, titulo, detalle, monto, evidencia, destino, despues}."""
    return evaluar_inteligencia(db_conn, uid, hoy)["accion"]


def semaforo_preparacion(db_conn, uid, hoy=None):
    """Punto 17 · {estado, icono, etiqueta, color, resumen, cumplidos, total, checklist[]}."""
    return evaluar_inteligencia(db_conn, uid, hoy)["semaforo"]


# ==========================================
# 7. UI · PANEL DE INTELIGENCIA (Quiet Luxury)
# ==========================================
_CSS = f"""
<style>
.fp5-card {{ background: linear-gradient(145deg, rgba(8,11,19,0.55) 0%, rgba(10,14,23,0.25) 100%);
            border: 1px solid rgba(212,175,55,0.14); border-radius: 22px; padding: 22px 24px; margin: 4px 0 18px 0;
            height: calc(100% - 22px); }}
.fp5-eyebrow {{ color: #8b949e; font-size: 0.7rem; letter-spacing: 2.4px; text-transform: uppercase;
               display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
.fp5-chip {{ font-size: 0.66rem; letter-spacing: 1.6px; padding: 2px 11px; border-radius: 12px; border: 1px solid; }}
.fp5-titulo {{ font-family: 'Playfair Display', serif; font-size: 1.75rem; font-weight: 400; color: #ffffff;
              line-height: 1.2; margin: 12px 0 10px 0; letter-spacing: -0.2px; }}
.fp5-texto {{ color: #aab4c3; font-size: 0.9rem; line-height: 1.65; font-weight: 300; }}
.fp5-evid {{ display: flex; flex-wrap: wrap; gap: 22px; margin-top: 16px; padding-top: 14px;
            border-top: 1px solid rgba(255,255,255,0.05); }}
.fp5-evid div {{ display: flex; flex-direction: column; gap: 3px; }}
.fp5-evid span:first-child {{ color: {TENUE}; font-size: 0.68rem; letter-spacing: 1.4px; text-transform: uppercase; }}
.fp5-evid span:last-child {{ color: #e5e7eb; font-size: 0.95rem; font-weight: 500; }}
.fp5-despues {{ color: {TENUE}; font-size: 0.8rem; margin-top: 14px; font-style: italic; }}
.fp5-luz {{ display: flex; align-items: center; gap: 14px; margin: 16px 0 10px 0; }}
.fp5-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; animation: fp5-respira 3.6s ease-in-out infinite; }}
@keyframes fp5-respira {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.55; }} }}
.fp5-estado {{ font-family: 'Playfair Display', serif; font-style: italic; font-size: 1.45rem; font-weight: 400; }}
.fp5-seg {{ display: flex; gap: 4px; margin: 16px 0 6px 0; }}
.fp5-seg div {{ flex: 1; height: 4px; border-radius: 2px; }}
.fp5-sub {{ color: {TENUE}; font-size: 0.78rem; }}
.fp5-check {{ margin-top: 14px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px; }}
.fp5-check summary {{ color: {ORO}; font-size: 0.8rem; letter-spacing: 1px; cursor: pointer; list-style: none; }}
.fp5-check summary::-webkit-details-marker {{ display: none; }}
.fp5-check summary::after {{ content: ' +'; }}
.fp5-check[open] summary::after {{ content: ' −'; }}
.fp5-item {{ display: flex; gap: 12px; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.035); }}
.fp5-item:last-child {{ border-bottom: none; }}
.fp5-marca {{ width: 18px; height: 18px; border-radius: 50%; border: 1px solid; font-size: 0.66rem; flex-shrink: 0;
             display: flex; align-items: center; justify-content: center; margin-top: 2px; }}
.fp5-item-t {{ color: #e5e7eb; font-size: 0.85rem; }}
.fp5-item-d {{ color: {TENUE}; font-size: 0.76rem; margin-top: 2px; line-height: 1.4; }}
.fp5-grupo {{ color: #4b5563; font-size: 0.66rem; letter-spacing: 1.8px; text-transform: uppercase; margin: 12px 0 2px 0; }}
.fp5-linea {{ color: #8b949e; font-size: 0.82rem; padding: 6px 0 14px 0; }}
</style>
"""

_MARCAS = {"OK": ("✓", VERDE), "PENDIENTE": ("○", ORO), "CRITICO": ("!", TERRACOTA)}


def _e(texto):
    return html.escape(str(texto or ""))


def _html_accion(a):
    nivel_txt, color = _NIVELES.get(a["nivel"], _NIVELES["NORMAL"])
    evid = "".join(f"<div><span>{_e(k)}</span><span>{_e(v)}</span></div>" for k, v in a["evidencia"])
    despues = f"<div class='fp5-despues'>Después: {_e(a['despues'])}</div>" if a.get("despues") else ""
    return (f"<div class='fp5-card notranslate' translate='no' style='border-left:2px solid {color};'>"
            f"<div class='fp5-eyebrow'><span>Siguiente mejor acción</span>"
            f"<span class='fp5-chip' style='color:{color}; border-color:{color}55;'>{nivel_txt}</span></div>"
            f"<div class='fp5-titulo'>{_e(a['titulo'])}</div><div class='fp5-texto'>{_e(a['detalle'])}</div>"
            f"{f'<div class=fp5-evid>{evid}</div>' if evid else ''}{despues}</div>")


def _html_semaforo(s):
    c = s["color"]
    seg_color = {"OK": VERDE, "PENDIENTE": "rgba(212,175,55,0.45)", "CRITICO": TERRACOTA}
    segmentos = "".join(f"<div style='background:{seg_color[i['estado']]};'></div>"
                        for i in s["checklist"] if i["bloqueante"])

    def filas(bloq):
        out = ""
        for i in s["checklist"]:
            if i["bloqueante"] != bloq:
                continue
            marca, col = _MARCAS[i["estado"]]
            out += (f"<div class='fp5-item'><div class='fp5-marca' style='color:{col}; border-color:{col}66;'>{marca}</div>"
                    f"<div><div class='fp5-item-t'>{_e(i['titulo'])}</div><div class='fp5-item-d'>{_e(i['detalle'])}</div></div></div>")
        return out

    return (f"<div class='fp5-card notranslate' translate='no'>"
            f"<div class='fp5-eyebrow'><span>Preparación para Terminal</span></div>"
            f"<div class='fp5-luz'><span class='fp5-dot' style='background:{c}; box-shadow:0 0 16px {c}55;'></span>"
            f"<span class='fp5-estado' style='color:{c};'>{_e(s['etiqueta'])}</span></div>"
            f"<div class='fp5-texto'>{_e(s['resumen'])}</div>"
            f"<div class='fp5-seg'>{segmentos}</div><div class='fp5-sub'>{s['cumplidos']} de {s['total']} criterios</div>"
            f"<details class='fp5-check'><summary>Checklist de transición</summary>"
            f"<div class='fp5-grupo'>Requisitos</div>{filas(True)}"
            f"<div class='fp5-grupo'>Recomendado</div>{filas(False)}</details></div>")


def ui_panel_inteligencia(db_conn, uid):
    """Siguiente Mejor Acción (destacada) + Semáforo de preparación con checklist."""
    st.markdown(_CSS, unsafe_allow_html=True)
    hoy = _hoy()
    try:
        res = evaluar_inteligencia(db_conn, uid, hoy)
    except Exception:
        log.exception("Panel de inteligencia no disponible")
        st.caption("El diagnóstico no está disponible en este momento.")
        return
    accion, sem = res["accion"], res["semaforo"]

    clave_oculto = f"fp5_oculta_{uid}_{hoy.isoformat()}"  # ignorar = solo por hoy (Blueprint: verla/ignorarla)
    if st.session_state.get(clave_oculto):
        c1, c2 = st.columns([7, 1])
        c1.markdown(f"<div class='fp5-linea notranslate' translate='no'>Siguiente mejor acción oculta por hoy · "
                    f"<span style='color:{sem['color']};'>{_e(sem['etiqueta'])}</span></div>", unsafe_allow_html=True)
        if c2.button("Mostrar", key=f"fp5_mostrar_{uid}", use_container_width=True):
            st.session_state.pop(clave_oculto, None)
            st.rerun()
        return

    col_accion, col_sem = st.columns([1.65, 1], gap="large")
    with col_accion:
        st.markdown(_html_accion(accion), unsafe_allow_html=True)
    with col_sem:
        st.markdown(_html_semaforo(sem), unsafe_allow_html=True)
    _, c_btn = st.columns([7, 1])
    if c_btn.button("Ocultar hoy", key=f"fp5_ocultar_{uid}", use_container_width=True,
                    help="Oculta la recomendación hasta mañana. El diagnóstico sigue calculándose."):
        st.session_state[clave_oculto] = True
        st.rerun()
