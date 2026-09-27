"""
fp_fase6_ui_importacion.py — APortafolio FP · Fase 6 · Bloque 2 · Importación y conciliación (Punto 23)

Módulo AISLADO (Norma 2): no importa nada de app.py ni de main.py y NO crea tablas ni altera esquemas.
Recibe `db_conn` (context manager de app.py) y `uid`.

Exporta:
  • ui_boton_importacion(db_conn, uid)    · botón "Importar estado de cuenta" → diálogo (lo que se inyecta en app.py)
  • ui_importacion(db_conn, uid)          · la misma interfaz, en línea (sin diálogo)
  • leer_csv(bytes) / normalizar_filas()   · parseo puro (sin BD), probado con formatos de bancos mexicanos
  • conciliar(db_conn, uid, filas)          · staging: NUEVO / DUPLICADO / CONFLICTO / INVÁLIDO (solo lectura)
  • importar_movimientos(db_conn, uid, ...) · escribe SOLO lo nuevo (re-verifica duplicados dentro de la transacción)
  • deshacer_importacion(db_conn, uid, ids) · marca como DESCARTADO lo importado (no borra)

Flujo: CSV → staging en memoria (session_state) → preview de conciliación → "Confirmar e importar".
Nada toca el ledger hasta el botón final.

Reglas de conciliación (orden de precedencia):
  DUPLICADO  mismo fingerprint (monto + fecha + comercio normalizado) y mismo tipo que un movimiento vivo del ledger.
             Emparejamiento 1 a 1: dos cafés iguales el mismo día en el CSV y uno en el ledger → 1 duplicado, 1 nuevo.
  CONFLICTO  sin huella exacta, pero hay un movimiento con el mismo monto a ±2 días (p. ej. "gasolina" por Telegram vs
             "OXXO GAS REFORMA" en el banco, o una transferencia ya registrada). No se importa salvo que el usuario lo marque.
  INVÁLIDO   fecha o monto ilegible (encabezados, totales, saldos). Nunca se importa.
  NUEVO      todo lo demás. Se importa marcado por defecto.

Suposiciones (auto-auditadas contra app.py / main.py):
  - Mismo esquema de fp_financial_ledger que usan fp_registrar() (app.py) y guardar_movimiento() (main.py);
    columnas opcionales (comercio, confianza_ia, compromiso_id, fingerprint) se detectan en information_schema.
  - `fuente` es ENUM: se usa 'IMPORTACION_CSV' si existe; si no, 'WEB_MANUAL' (valor que app.py ya escribe).
  - `estado` es ENUM: un conflicto aceptado se guarda como 'PENDIENTE_REVISION' (valor existente).
  - fp_buscar_compromiso() y fp_reglas_cma son opcionales: si no existen, se omiten sin romper la importación.
"""
from __future__ import annotations

import csv
import hashlib
import html
import logging
import re
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st

log = logging.getLogger("apportafolio_fp.fase6_ui")

# ==========================================
# 0. CONSTANTES
# ==========================================
ZONA_MX = timezone(timedelta(hours=-6))
TABLA_LEDGER = "fp_financial_ledger"
MAX_BYTES = 5 * 1024 * 1024
MAX_FILAS = 5000
TOLERANCIA_DIAS = 2
TOLERANCIA_MONTO = Decimal("0.01")

NUEVO, DUPLICADO, CONFLICTO, INVALIDO = "Nuevo", "Duplicado", "Conflicto", "Inválido"
_ORDEN_ESTADO = {CONFLICTO: 0, NUEVO: 1, DUPLICADO: 2, INVALIDO: 3}
_IMPORTABLES = {NUEVO, CONFLICTO}                 # CONFLICTO solo si el usuario lo marca a mano

_FUENTES_PREFERIDAS = ("IMPORTACION_CSV", "IMPORTACION", "ESTADO_CUENTA", "WEB_MANUAL")
_FUENTE_SEGURA = "WEB_MANUAL"
_ESTADO_REVISION = "PENDIENTE_REVISION"

ORO, VERDE, GRIS, TERRACOTA, TENUE = "#d4af37", "#34d399", "#94a3b8", "#e07a5f", "#64748b"
_COLOR_ESTADO = {NUEVO: VERDE, DUPLICADO: GRIS, CONFLICTO: ORO, INVALIDO: TERRACOTA}

MODO_SIGNO, MODO_CARGO_ABONO, MODO_TIPO = "Monto con signo", "Cargo y abono separados", "Monto + columna Tipo"
_MODOS = (MODO_SIGNO, MODO_CARGO_ABONO, MODO_TIPO)
FECHA_AUTO, FECHA_DMY, FECHA_MDY = "Automático", "Día/Mes/Año", "Mes/Día/Año"
_SIN_COLUMNA = "— sin columna —"

_SINONIMOS = {
    "fecha": ("fecha", "fecha operacion", "fecha de operacion", "fecha movimiento", "fecha de movimiento", "fecha valor",
              "fecha aplicacion", "fecha de aplicacion", "dia", "date", "transaction date", "posting date"),
    "concepto": ("concepto", "descripcion", "description", "detalle", "movimiento", "descripcion del movimiento",
                 "comercio", "establecimiento", "beneficiario", "referencia", "memo", "narrative"),
    "monto": ("monto", "importe", "amount", "cantidad", "valor", "monto mxn", "importe mxn"),
    "cargo": ("cargo", "cargos", "retiro", "retiros", "debito", "debitos", "egreso", "egresos", "salida", "salidas",
              "debit", "withdrawal"),
    "abono": ("abono", "abonos", "deposito", "depositos", "credito", "creditos", "ingreso", "ingresos", "entrada",
              "entradas", "credit"),
    "tipo": ("tipo", "tipo movimiento", "tipo de movimiento", "naturaleza", "cargo abono", "type"),
}
_PALABRAS_GASTO = ("cargo", "retiro", "gasto", "debito", "egreso", "salida", "compra", "pago", "debit", "withdrawal")
_PALABRAS_INGRESO = ("abono", "deposito", "ingreso", "credito", "entrada", "nomina", "credit", "deposit")
_MESES = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
          "aug": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}

__all__ = ["ui_boton_importacion", "ui_importacion", "leer_csv", "detectar_mapeo", "normalizar_filas", "conciliar",
           "importar_movimientos", "deshacer_importacion", "generar_fingerprint"]


# ==========================================
# 1. FINGERPRINT · reutiliza fp_fase6_ingesta; copia idéntica como respaldo (el despliegue de la
#    Terminal puede no incluir los archivos del bot). La autoprueba verifica que ambas coincidan.
# ==========================================
_RUIDO_COMERCIO = {
    "de", "del", "la", "el", "los", "las", "en", "y", "a", "al", "por", "para", "con", "mi", "mis", "un", "una",
    "sa", "cv", "sapi", "srl", "sab", "rl", "s", "suc", "sucursal", "tienda", "mx", "mex", "mexico", "cdmx",
    "compra", "compras", "pago", "pagos", "cargo", "cargos", "abono", "tarjeta", "tdc", "tdd", "pos", "ref",
    "referencia", "folio", "aut", "autorizacion", "mxn", "pesos", "peso", "hoy", "ayer", "antier", "anteayer",
    "pague", "gaste", "compre", "fui",
}


def _sin_acentos(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()


def _norm(texto):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _sin_acentos(texto)).split())


def _a_decimal_local(monto):
    if isinstance(monto, Decimal):
        valor = monto
    elif isinstance(monto, (int, float)):
        valor = Decimal(str(monto))
    else:
        s = re.sub(r"[^\d,.\-]", "", str(monto or ""))
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
        try:
            valor = Decimal(s) if s else Decimal("0")
        except InvalidOperation:
            valor = Decimal("0")
    return abs(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _a_fecha_local(fecha):
    if isinstance(fecha, datetime):
        return fecha.date()
    if isinstance(fecha, date):
        return fecha
    s = str(fecha or "").strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {fecha!r}")


def _normalizar_comercio_local(texto):
    palabras = [p for p in _norm(texto).split() if len(p) > 1 and not p.isdigit()
                and not re.fullmatch(r"[a-z]*\d+[a-z\d]*", p) and p not in _RUIDO_COMERCIO]
    return " ".join(sorted(set(palabras))) or "sin comercio"


def _base_comercio_local(comercio, concepto):
    return (str(comercio).strip() if comercio and str(comercio).strip() else str(concepto or "")).strip()


def _generar_fingerprint_local(monto, fecha, comercio_normalizado):
    clave = (f"{_a_decimal_local(monto):.2f}|{_a_fecha_local(fecha).isoformat()}|"
             f"{_normalizar_comercio_local(comercio_normalizado)}")
    return f"v1:{hashlib.sha256(clave.encode('utf-8')).hexdigest()[:40]}"


try:  # Fuente única de verdad cuando está disponible (mismo repo que el bot)
    from fp_fase6_ingesta import generar_fingerprint, base_comercio  # type: ignore
    _FINGERPRINT_ORIGEN = "fp_fase6_ingesta"
except Exception:  # depende del despliegue
    generar_fingerprint, base_comercio = _generar_fingerprint_local, _base_comercio_local
    _FINGERPRINT_ORIGEN = "local"


# ==========================================
# 2. INFRAESTRUCTURA DE BD (adapter idéntico al de Fase 5 / Fase 6.1)
# ==========================================
@contextmanager
def _abrir(db_conn):
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


def _con_savepoint(cur, nombre, fn, default=None):
    """Ejecuta fn(cur) aislado: si falla, revierte solo ese paso y devuelve default."""
    try:
        cur.execute(f"SAVEPOINT {nombre}")
        resultado = fn(cur)
        cur.execute(f"RELEASE SAVEPOINT {nombre}")
        return resultado
    except Exception:
        log.warning("Paso '%s' omitido.", nombre, exc_info=True)
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {nombre}")
        except Exception:
            pass
        return default


def _meta_ledger(cur):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = ANY(current_schemas(false))", (TABLA_LEDGER,))
    columnas = {r[0] for r in cur.fetchall()}
    enums = {}
    for col in ("estado", "fuente"):
        cur.execute("""
            SELECT e.enumlabel FROM pg_attribute a JOIN pg_enum e ON e.enumtypid = a.atttypid
             WHERE a.attrelid = to_regclass(%s) AND a.attname = %s AND NOT a.attisdropped
            """, (TABLA_LEDGER, col))
        enums[col] = {r[0] for r in cur.fetchall()} or None
    cur.execute("SELECT to_regprocedure('fp_buscar_compromiso(text,text,text,numeric,date)') IS NOT NULL")
    tiene_compromisos = bool(cur.fetchone()[0])
    return {"columnas": columnas, "enums": enums, "compromisos": tiene_compromisos}


def _hoy():
    return datetime.now(ZONA_MX).date()


# ==========================================
# 3. PARSEO DEL CSV (puro, sin BD)
# ==========================================
def _decodificar(datos: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace")


def _delimitador(lineas):
    muestra = "\n".join(lineas[:40])
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        return max((",", ";", "\t", "|"), key=lambda d: sum(l.count(d) for l in lineas[:40]))


def _es_clave(celda, clave):
    n = _norm(celda)
    return any(n == s or n.startswith(s + " ") for s in _SINONIMOS[clave])


def leer_csv(datos: bytes) -> pd.DataFrame:
    """Lee un estado de cuenta: detecta codificación, delimitador y la fila real de encabezados
    (los bancos ponen nombre, cuenta y periodo arriba de la tabla). Todo se devuelve como texto."""
    if len(datos) > MAX_BYTES:
        raise ValueError(f"El archivo pesa {len(datos) / 1e6:.1f} MB; el máximo es {MAX_BYTES // 1_000_000} MB.")
    texto = _decodificar(datos)
    lineas = [l for l in texto.splitlines() if l.strip()]
    if not lineas:
        raise ValueError("El archivo está vacío.")
    delim = _delimitador(lineas)
    filas = list(csv.reader(lineas, delimiter=delim))

    inicio = next((i for i, f in enumerate(filas[:40])
                   if any(_es_clave(c, "fecha") for c in f)
                   and any(_es_clave(c, k) for c in f for k in ("monto", "cargo", "abono"))), None)
    if inicio is None:
        inicio = next((i for i, f in enumerate(filas[:40]) if sum(1 for c in f if c.strip()) >= 3), 0)

    encabezado, vistos = [], {}
    for j, c in enumerate(filas[inicio]):
        nombre = c.strip() or f"Columna {j + 1}"
        vistos[nombre] = vistos.get(nombre, 0) + 1
        encabezado.append(nombre if vistos[nombre] == 1 else f"{nombre} ({vistos[nombre]})")
    ancho = len(encabezado)
    cuerpo = [(f + [""] * ancho)[:ancho] for f in filas[inicio + 1:] if any(c.strip() for c in f)]
    if len(cuerpo) > MAX_FILAS:
        raise ValueError(f"El archivo tiene {len(cuerpo):,} filas; el máximo por importación es {MAX_FILAS:,}.")
    df = pd.DataFrame(cuerpo, columns=encabezado, dtype=str)
    return df.loc[:, [c for c in df.columns if df[c].str.strip().ne("").any()]].reset_index(drop=True)


def detectar_mapeo(columnas):
    """Sugerencia automática: {'fecha', 'concepto', 'monto', 'cargo', 'abono', 'tipo', 'modo'}."""
    mapeo = {}
    for clave in ("fecha", "cargo", "abono", "monto", "tipo", "concepto"):
        usadas = set(mapeo.values())
        exacta = next((c for c in columnas if c not in usadas and _norm(c) in _SINONIMOS[clave]), None)
        mapeo[clave] = exacta or next((c for c in columnas if c not in usadas and _es_clave(c, clave)), None)
    if mapeo["cargo"] and mapeo["abono"]:
        mapeo["modo"] = MODO_CARGO_ABONO
    elif mapeo["monto"] and mapeo["tipo"]:
        mapeo["modo"] = MODO_TIPO
    else:
        mapeo["modo"] = MODO_SIGNO
        if not mapeo["monto"]:
            mapeo["monto"] = mapeo["cargo"] or mapeo["abono"]
    return mapeo


def _parse_monto(valor):
    """Decimal con signo o None. '$1,234.56' · '-1,234.56' · '(1,234.56)' · '1.234,56' · '1234.56-'."""
    s = str(valor or "").strip()
    if not s or s in ("-", "--"):
        return None
    negativo = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d,.]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        decimal_sep = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal_sep == "," else ",", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3}){2,}", s):
        s = s.replace(".", "")
    try:
        v = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return -v if negativo else v


def _partes_fecha(valor):
    s = _sin_acentos(valor).strip()
    s = re.split(r"[ t](?=\d{1,2}:\d{2})", s)[0].strip()               # quita la hora
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return ("YMD", int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", s)
    if m:
        return ("NUM", int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[-/ .]+([a-z]{3,})\.?[-/ .,]+(\d{2,4})\b", s)
    if m and m.group(2)[:3] in _MESES:
        return ("TXT", int(m.group(1)), _MESES[m.group(2)[:3]], int(m.group(3)))
    return None


def _orientacion(partes, preferencia):
    """Día primero salvo evidencia: si alguna fecha tiene el 2º número > 12 en la columna, es Mes/Día."""
    if preferencia == FECHA_DMY:
        return "DMY"
    if preferencia == FECHA_MDY:
        return "MDY"
    numericas = [p for p in partes if p and p[0] == "NUM"]
    if any(p[1] > 12 for p in numericas):
        return "DMY"
    if any(p[2] > 12 for p in numericas):
        return "MDY"
    return "DMY"                                                       # convención mexicana


def _a_fecha_parte(p, orientacion):
    if not p:
        return None
    clase, a, b, c = p
    if clase == "YMD":
        y, m, d = a, b, c
    elif clase == "TXT":
        d, m, y = a, b, c
    else:
        d, m, y = (a, b, c) if orientacion == "DMY" else (b, a, c)
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _tipo_por_texto(valor):
    n = _norm(valor)
    if not n:
        return None
    if any(p in n for p in _PALABRAS_INGRESO) or n in ("a", "abn", "cr"):
        return "INGRESO"
    if any(p in n for p in _PALABRAS_GASTO) or n in ("c", "cgo", "d", "dr"):
        return "GASTO"
    return None


def normalizar_filas(df, mapeo, cargos_negativos=True, formato_fecha=FECHA_AUTO, hoy=None):
    """DataFrame crudo + mapeo → filas canónicas {fila, fecha, concepto, tipo, monto(Decimal>0), error}. Pura."""
    hoy = hoy or _hoy()

    def col(k):
        return mapeo.get(k) if mapeo.get(k) in df.columns else None

    c_fecha, c_concepto = col("fecha"), col("concepto")
    partes = [_partes_fecha(v) for v in df[c_fecha]] if c_fecha else [None] * len(df)
    orient = _orientacion(partes, formato_fecha)
    modo = mapeo.get("modo") or MODO_SIGNO

    salida = []
    for i in range(len(df)):
        r = df.iloc[i]
        concepto = " ".join(str(r[c_concepto] if c_concepto else "").split())[:200]
        fecha = _a_fecha_parte(partes[i], orient)
        tipo, monto, error = None, None, ""

        if modo == MODO_CARGO_ABONO:
            cargo = _parse_monto(r[col("cargo")]) if col("cargo") else None
            abono = _parse_monto(r[col("abono")]) if col("abono") else None
            cargo, abono = (abs(cargo) if cargo else None), (abs(abono) if abono else None)
            if cargo and abono:
                neto = abono - cargo
                tipo, monto = ("INGRESO" if neto > 0 else "GASTO"), abs(neto)
            elif cargo:
                tipo, monto = "GASTO", cargo
            elif abono:
                tipo, monto = "INGRESO", abono
        else:
            v = _parse_monto(r[col("monto")]) if col("monto") else None
            if v is not None and v != 0:
                monto = abs(v)
                if modo == MODO_TIPO and col("tipo"):
                    tipo = _tipo_por_texto(r[col("tipo")])
                if tipo is None:
                    negativo = v < 0
                    tipo = (("GASTO" if negativo else "INGRESO") if cargos_negativos
                            else ("INGRESO" if negativo else "GASTO"))

        if fecha is None:
            error = "Fecha ilegible"
        elif fecha > hoy + timedelta(days=1):
            error = "Fecha futura"
        elif not monto:
            error = "Sin monto"
        elif not concepto:
            concepto = "Movimiento importado"
        salida.append({"fila": i + 1, "fecha": fecha, "concepto": concepto, "tipo": tipo, "monto": monto,
                       "error": error})
    return salida


# ==========================================
# 4. CONCILIACIÓN (staging · solo lectura)
# ==========================================
def _clave_origen(uid, huella, ordinal):
    """mensaje_origen_id determinista: re-importar el mismo estado nunca duplica (ON CONFLICT DO NOTHING)."""
    return f"IMP-{uid}-{huella.split(':')[-1][:24]}-{ordinal}"


def _etiqueta_fuente(fuente):
    return {"TELEGRAM_TEXTO": "Telegram", "REGLA_AUTOMATICA": "Telegram", "WEB_MANUAL": "Web",
            "WHATSAPP_TEXTO": "WhatsApp", "IMPORTACION_CSV": "importación"}.get(fuente, (fuente or "registro").lower())


def _ledger_ventana(cur, uid, desde, hasta):
    cur.execute(
        f"""
        SELECT l.movimiento_id, l.fecha::date, l.monto, l.tipo_movimiento::text, l.comercio, l.concepto, l.fuente::text
          FROM {TABLA_LEDGER} l
         WHERE l.user_id = %s AND COALESCE(l.estado::text, '') <> 'DESCARTADO'
           AND l.fecha::date BETWEEN %s AND %s
         LIMIT 20000
        """, (uid, desde, hasta))
    return [{"id": a, "fecha": b, "monto": _a_decimal_local(c), "tipo": d or "", "texto": base_comercio(e, f),
             "fuente": g or ""} for a, b, c, d, e, f, g in cur.fetchall()]


def _emparejar(filas, ledger, uid):
    """Asigna estado a cada fila (in place). Exactos primero (1 a 1), luego conflictos por monto ±2 días."""
    pool = {}
    for m in ledger:
        if m["tipo"] in ("GASTO", "INGRESO"):
            pool.setdefault((generar_fingerprint(m["monto"], m["fecha"], m["texto"]), m["tipo"]), []).append(m)
    usados, ordinales = set(), {}

    for f in filas:
        if f["error"]:
            f.update(estado=INVALIDO, detalle=f["error"], huella=None, mensaje_origen_id=None, movimiento_previo=None)
            continue
        f["huella"] = generar_fingerprint(f["monto"], f["fecha"], f["concepto"])
        k = (f["huella"], f["tipo"])
        ordinales[k] = ordinales.get(k, 0) + 1
        f["mensaje_origen_id"] = _clave_origen(uid, f["huella"], ordinales[k])
        m = next((m for m in pool.get(k, []) if m["id"] not in usados), None)
        if m:
            usados.add(m["id"])
            f.update(estado=DUPLICADO, movimiento_previo=m["id"],
                     detalle=f"Ya está en tu ledger ({_etiqueta_fuente(m['fuente'])}, {m['fecha']:%d/%m})")

    for f in filas:
        if f.get("estado"):
            continue
        cerca = sorted((m for m in ledger if m["id"] not in usados
                        and abs(m["monto"] - f["monto"]) <= TOLERANCIA_MONTO
                        and abs((m["fecha"] - f["fecha"]).days) <= TOLERANCIA_DIAS),
                       key=lambda m: (m["tipo"] != f["tipo"], abs((m["fecha"] - f["fecha"]).days)))
        if cerca:
            m = cerca[0]
            usados.add(m["id"])
            que = "una transferencia" if m["tipo"] == "TRANSFERENCIA" else f"«{(m['texto'] or 'sin concepto')[:40]}»"
            f.update(estado=CONFLICTO, movimiento_previo=m["id"],
                     detalle=f"Mismo monto el {m['fecha']:%d/%m}: {que} ({_etiqueta_fuente(m['fuente'])})")
        else:
            f.update(estado=NUEVO, movimiento_previo=None, detalle="")
    return filas


def conciliar(db_conn, uid, filas):
    """Clasifica cada fila contra fp_financial_ledger. No escribe nada."""
    validas = [f["fecha"] for f in filas if not f["error"]]
    if not validas:
        return _emparejar(filas, [], uid)
    desde = min(validas) - timedelta(days=TOLERANCIA_DIAS)
    hasta = max(validas) + timedelta(days=TOLERANCIA_DIAS)
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        ledger = _ledger_ventana(cur, uid, desde, hasta)
    return _emparejar(filas, ledger, uid)


# ==========================================
# 5. ESCRITURA (solo al confirmar)
# ==========================================
def importar_movimientos(db_conn, uid, filas, cuenta_id=None, duplicados_preview=None):
    """Escribe SOLO filas NUEVO (y CONFLICTO aceptadas por el usuario). En la misma transacción vuelve a leer el
    ledger por si el bot registró algo mientras se revisaba el preview. Cada fila va en su SAVEPOINT: una fila
    mala no tumba la importación. `duplicados_preview`: {(huella, tipo): n} que ya eran duplicado en el preview."""
    res = {"insertados": 0, "ya_existian": 0, "ahora_duplicados": 0, "fallidos": 0, "ids": []}
    candidatas = [f for f in filas if f.get("estado") in _IMPORTABLES and not f.get("error")]
    if not candidatas:
        return res

    with _abrir(db_conn) as conn, conn.cursor() as cur:
        meta = _meta_ledger(cur)
        cols, enums = meta["columnas"], meta["enums"]
        fuente = next((f for f in _FUENTES_PREFERIDAS if enums["fuente"] and f in enums["fuente"]), _FUENTE_SEGURA)
        revision = _ESTADO_REVISION if (enums["estado"] is None or _ESTADO_REVISION in enums["estado"]) else "CONFIRMADO"

        desde = min(f["fecha"] for f in candidatas) - timedelta(days=TOLERANCIA_DIAS)
        hasta = max(f["fecha"] for f in candidatas) + timedelta(days=TOLERANCIA_DIAS)
        vivos = {}
        for m in _ledger_ventana(cur, uid, desde, hasta):
            if m["tipo"] in ("GASTO", "INGRESO"):
                k = (generar_fingerprint(m["monto"], m["fecha"], m["texto"]), m["tipo"])
                vivos[k] = vivos.get(k, 0) + 1
        consumidos = dict(duplicados_preview or {})

        for n, f in enumerate(candidatas):
            k = (f["huella"], f["tipo"])
            if f["estado"] == NUEVO and vivos.get(k, 0) > consumidos.get(k, 0):
                consumidos[k] = consumidos.get(k, 0) + 1          # apareció después del preview: se descarta
                res["ahora_duplicados"] += 1
                continue

            def insertar(c, f=f):
                compromiso_id = None
                if meta["compromisos"] and "compromiso_id" in cols:
                    def buscar(c2):
                        c2.execute("SELECT fp_buscar_compromiso(%s, %s, %s, %s, %s)",
                                   (uid, f["tipo"], f.get("categoria_id"), f["monto"], f["fecha"]))
                        return c2.fetchone()[0]
                    compromiso_id = _con_savepoint(c, "fp6c", buscar)
                valores = {
                    "movimiento_id": f"MOV-{uuid.uuid4().hex[:16]}", "user_id": uid, "tipo_movimiento": f["tipo"],
                    "cuenta_origen_id": cuenta_id, "categoria_id": f.get("categoria_id"), "monto": f["monto"],
                    "moneda": "MXN", "concepto": f["concepto"], "fecha": f["fecha"], "fuente": fuente,
                    "estado": "CONFIRMADO" if f["estado"] == NUEVO else revision,
                    "mensaje_origen_id": f["mensaje_origen_id"],
                }
                opcionales = {"confianza_ia": 1.0 if f["estado"] == NUEVO else 0.5, "compromiso_id": compromiso_id,
                              "fingerprint": f["huella"]}
                valores.update({k2: v for k2, v in opcionales.items() if k2 in cols})
                columnas = list(valores)                 # lista blanca fija de este módulo, nunca del CSV
                c.execute(f"INSERT INTO {TABLA_LEDGER} ({', '.join(columnas)}) "
                          f"VALUES ({', '.join(['%s'] * len(columnas))}) "
                          "ON CONFLICT (mensaje_origen_id) DO NOTHING RETURNING movimiento_id",
                          [valores[c3] for c3 in columnas])
                fila = c.fetchone()
                return fila[0] if fila else ""

            resultado = _con_savepoint(cur, f"fp6i{n}", insertar, default=None)
            if resultado is None:
                res["fallidos"] += 1
            elif resultado == "":
                res["ya_existian"] += 1
            else:
                res["insertados"] += 1
                res["ids"].append(resultado)
    return res


def deshacer_importacion(db_conn, uid, ids):
    """Marca como DESCARTADO lo importado (mismo criterio que 'Quitar' en app.py: no se borra)."""
    if not ids:
        return 0
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE {TABLA_LEDGER} SET estado = 'DESCARTADO' WHERE user_id = %s AND movimiento_id = ANY(%s)",
                    (uid, list(ids)))
        return cur.rowcount


# ==========================================
# 6. CATÁLOGOS (categorías, cuentas, reglas CMA)
# ==========================================
def _catalogos(db_conn, uid):
    cat = {"categorias": {}, "cuentas": {}, "reglas": []}
    with _abrir(db_conn) as conn, conn.cursor() as cur:
        def q_cat(c):
            c.execute("SELECT categoria_id, nombre FROM fp_categorias WHERE user_id = %s OR user_id IS NULL "
                      "ORDER BY (user_id IS NOT NULL), nombre", (uid,))
            return {n: i for i, n in c.fetchall()}            # las del usuario pisan a las globales

        def q_cuentas(c):
            c.execute("SELECT cuenta_id, nombre FROM fp_cuentas WHERE user_id = %s AND activa ORDER BY nombre", (uid,))
            return {n: i for i, n in c.fetchall()}

        def q_reglas(c):
            c.execute("SELECT r.patron, r.categoria_id FROM fp_reglas_cma r WHERE r.activa "
                      "AND (r.user_id = %s OR r.user_id IS NULL) "
                      "ORDER BY (r.user_id IS NOT NULL) DESC, length(r.patron) DESC", (uid,))
            return [(_norm(p), ci) for p, ci in c.fetchall() if p]

        cat["categorias"] = _con_savepoint(cur, "fp6k", q_cat, {}) or {}
        cat["cuentas"] = _con_savepoint(cur, "fp6q", q_cuentas, {}) or {}
        cat["reglas"] = _con_savepoint(cur, "fp6r", q_reglas, []) or []
    return cat


def _categoria_sugerida(fila, catalogo):
    """CMA Memory primero (mismas reglas que el bot); si no, Ingresos / Sin clasificar."""
    nombres = {i: n for n, i in catalogo["categorias"].items()}
    texto = f" {_norm(fila['concepto'])} "
    if fila["tipo"] == "GASTO":
        regla = next((ci for p, ci in catalogo["reglas"] if f" {p} " in texto and ci in nombres), None)
        if regla:
            return nombres[regla]
    for preferida in (("Ingresos", "Sin clasificar") if fila["tipo"] == "INGRESO" else ("Sin clasificar",)):
        real = next((n for n in catalogo["categorias"] if _norm(n) == _norm(preferida)), None)
        if real:
            return real
    return None


# ==========================================
# 7. UI (Quiet Luxury)
# ==========================================
_CSS = f"""
<style>
.fp6-resumen {{ display:flex; flex-wrap:wrap; gap:10px; margin:6px 0 10px 0; }}
.fp6-chip {{ flex:1; min-width:110px; border:1px solid rgba(255,255,255,0.06); border-radius:16px; padding:12px 14px;
            background:linear-gradient(145deg, rgba(8,11,19,0.6), rgba(10,14,23,0.3)); }}
.fp6-chip span:first-child {{ display:block; font-size:0.66rem; letter-spacing:1.8px; text-transform:uppercase; color:{TENUE}; }}
.fp6-chip span:last-child {{ display:block; font-family:'Playfair Display', serif; font-size:1.6rem; margin-top:2px; }}
.fp6-nota {{ color:#8b949e; font-size:0.8rem; line-height:1.5; }}
</style>
"""


def _k(uid, sufijo):
    return f"fp6imp_{uid}_{sufijo}"


def _dinero(v):
    v = round(float(v or 0), 2)
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


def _html_resumen(conteos, total_nuevo):
    chips = "".join(f"<div class='fp6-chip'><span>{html.escape(e)}</span>"
                    f"<span style='color:{_COLOR_ESTADO[e]};'>{conteos.get(e, 0)}</span></div>"
                    for e in (NUEVO, CONFLICTO, DUPLICADO, INVALIDO))
    return (f"<div class='fp6-resumen notranslate' translate='no'>{chips}</div>"
            f"<p class='fp6-nota'>Nuevos: {_dinero(total_nuevo)} en total. Los duplicados e inválidos se descartan "
            "siempre; un conflicto solo se importa si lo marcas, y queda en revisión.</p>")


def _selector(contenedor, etiqueta, columnas, actual, clave):
    opciones = [_SIN_COLUMNA] + list(columnas)
    elegido = contenedor.selectbox(etiqueta, opciones, index=opciones.index(actual) if actual in opciones else 0,
                                   key=clave)
    return None if elegido == _SIN_COLUMNA else elegido


def _ui_mapeo(uid, df, sugerido, firma_archivo):
    """Mapeo rápido de columnas. Se abre solo si la detección automática no fue suficiente."""
    completo = bool(sugerido["fecha"]) and bool(sugerido["monto"] or (sugerido["cargo"] and sugerido["abono"]))
    k = lambda s: _k(uid, f"{s}_{firma_archivo}")      # un archivo nuevo reinicia el mapeo
    with st.expander("Columnas del archivo" + ("" if completo else " · revisa el mapeo"), expanded=not completo):
        c1, c2 = st.columns(2)
        mapeo = {"fecha": _selector(c1, "Fecha", df.columns, sugerido["fecha"], k("m_fecha")),
                 "concepto": _selector(c2, "Concepto", df.columns, sugerido["concepto"], k("m_concepto"))}
        mapeo["modo"] = st.radio("¿Cómo vienen los montos?", _MODOS, index=_MODOS.index(sugerido["modo"]),
                                 horizontal=True, key=k("m_modo"))
        c3, c4 = st.columns(2)
        negativos = True
        if mapeo["modo"] == MODO_CARGO_ABONO:
            mapeo["cargo"] = _selector(c3, "Cargo (sale dinero)", df.columns, sugerido["cargo"], k("m_cargo"))
            mapeo["abono"] = _selector(c4, "Abono (entra dinero)", df.columns, sugerido["abono"], k("m_abono"))
        else:
            mapeo["monto"] = _selector(c3, "Monto", df.columns, sugerido["monto"], k("m_monto"))
            if mapeo["modo"] == MODO_TIPO:
                mapeo["tipo"] = _selector(c4, "Tipo (cargo/abono)", df.columns, sugerido["tipo"], k("m_tipo"))
            negativos = st.radio("Los gastos vienen…", ["En negativo", "En positivo"], horizontal=True,
                                 key=k("m_signo"),
                                 help="Las tarjetas de crédito suelen listar los cargos en positivo.") == "En negativo"
        formato = st.radio("Formato de fecha", (FECHA_AUTO, FECHA_DMY, FECHA_MDY), horizontal=True, key=k("m_fmt"))
    return mapeo, negativos, formato


def _construir_staging(db_conn, uid, df, mapeo, negativos, formato, catalogo):
    filas = conciliar(db_conn, uid, normalizar_filas(df, mapeo, negativos, formato))
    for f in filas:
        f["categoria"] = _categoria_sugerida(f, catalogo) if f["estado"] != INVALIDO else None
    filas.sort(key=lambda f: (_ORDEN_ESTADO[f["estado"]], f["fecha"] or date.min, f["fila"]))
    tabla = pd.DataFrame([{
        "Importar": f["estado"] == NUEVO, "Estado": f["estado"], "Fecha": f["fecha"], "Concepto": f["concepto"],
        "Tipo": {"GASTO": "Gasto", "INGRESO": "Ingreso"}.get(f["tipo"], "—"),
        "Monto": float(f["monto"]) if f["monto"] else None, "Categoría": f["categoria"],
        "Detalle": f.get("detalle", ""), "Fila": f["fila"],
    } for f in filas])
    return filas, tabla


def ui_importacion(db_conn, uid):
    """Importación con staging, conciliación y confirmación. Nada se escribe hasta 'Confirmar e importar'."""
    st.markdown(_CSS, unsafe_allow_html=True)
    try:
        catalogo = _catalogos(db_conn, uid)
    except Exception:
        log.exception("Catálogos no disponibles")
        st.warning("No pude leer tus categorías y cuentas. Intenta de nuevo en un momento.")
        return

    nombres_cuentas = ["Sin especificar"] + list(catalogo["cuentas"])
    cuenta_txt = st.selectbox("¿De qué cuenta es este estado?", nombres_cuentas, key=_k(uid, "cuenta"),
                              help="Todos los movimientos del archivo quedan ligados a esta cuenta.")
    cuenta_id = catalogo["cuentas"].get(cuenta_txt)

    archivo = st.file_uploader("Estado de cuenta (CSV)", type=["csv", "txt"], key=_k(uid, "archivo"),
                               help="Descárgalo en formato CSV desde la banca en línea de tu banco.")
    if archivo is None:
        st.markdown("<p class='fp6-nota'>Comparo cada renglón contra lo que ya registraste por Telegram o la web "
                    "antes de guardar nada. Necesito fecha, concepto y monto (o cargo y abono).</p>",
                    unsafe_allow_html=True)
        return

    datos = archivo.getvalue()
    firma_archivo = hashlib.sha256(datos).hexdigest()[:12]
    try:
        df = leer_csv(datos)
    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")
        return
    if df.empty:
        st.warning("No encontré movimientos en el archivo.")
        return

    mapeo, negativos, formato = _ui_mapeo(uid, df, detectar_mapeo(list(df.columns)), firma_archivo)
    if not mapeo.get("fecha") or not (mapeo.get("monto") or mapeo.get("cargo") or mapeo.get("abono")):
        st.info("Elige al menos la columna de fecha y la de monto para continuar.")
        return

    # Staging: se recalcula solo si cambian archivo o mapeo (no consulta la BD en cada clic del editor)
    firma = hashlib.sha256(repr((firma_archivo, sorted((k, str(v)) for k, v in mapeo.items()),
                                 negativos, formato)).encode()).hexdigest()[:16]
    staging = st.session_state.get(_k(uid, "staging"))
    if not staging or staging["firma"] != firma:
        with st.spinner("Conciliando contra tu ledger…"):
            try:
                filas, tabla = _construir_staging(db_conn, uid, df, mapeo, negativos, formato, catalogo)
            except Exception:
                log.exception("Conciliación falló")
                st.error("No pude comparar contra tus movimientos. Intenta de nuevo en un momento.")
                return
        staging = {"firma": firma, "filas": filas, "tabla": tabla}
        st.session_state[_k(uid, "staging")] = staging

    filas, tabla = staging["filas"], staging["tabla"]
    conteos = {e: sum(1 for f in filas if f["estado"] == e) for e in (NUEVO, CONFLICTO, DUPLICADO, INVALIDO)}
    st.markdown(_html_resumen(conteos, sum(float(f["monto"]) for f in filas if f["estado"] == NUEVO)),
                unsafe_allow_html=True)

    editado = st.data_editor(
        tabla, key=_k(uid, f"editor_{firma}"), hide_index=True, use_container_width=True,
        height=min(460, 40 + 35 * max(len(tabla), 1)),
        disabled=["Estado", "Fecha", "Concepto", "Tipo", "Monto", "Detalle", "Fila"],
        column_config={
            "Importar": st.column_config.CheckboxColumn("Importar", help="Duplicados e inválidos se ignoran aunque los marques."),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Monto": st.column_config.NumberColumn("Monto", format="$%.2f"),
            "Categoría": st.column_config.SelectboxColumn("Categoría", options=list(catalogo["categorias"])),
            "Detalle": st.column_config.TextColumn("Detalle", width="large"),
            "Fila": st.column_config.NumberColumn("Fila", width="small", help="Renglón en el CSV original."),
        },
    )

    seleccion, marcados_invalidos = [], 0
    for pos, f in enumerate(filas):
        marcado = bool(editado.iloc[pos]["Importar"])
        if marcado and f["estado"] in _IMPORTABLES:
            seleccion.append({**f, "categoria_id": catalogo["categorias"].get(editado.iloc[pos]["Categoría"])})
        elif marcado:
            marcados_invalidos += 1
    if marcados_invalidos:
        st.caption(f"{marcados_invalidos} renglón(es) marcados son duplicados o inválidos: se descartarán.")

    c_info, c_btn = st.columns([2, 1])
    c_info.markdown(f"<p class='fp6-nota' style='margin-top:8px;'>{len(seleccion)} movimiento(s) · "
                    f"{_dinero(sum(float(f['monto']) for f in seleccion))} · cuenta: {html.escape(cuenta_txt)}</p>",
                    unsafe_allow_html=True)
    if c_btn.button("Confirmar e importar", type="primary", use_container_width=True, disabled=not seleccion,
                    key=_k(uid, "confirmar")):
        duplicados_preview = {}
        for f in filas:
            if f["estado"] == DUPLICADO:
                clave = (f["huella"], f["tipo"])
                duplicados_preview[clave] = duplicados_preview.get(clave, 0) + 1
        with st.spinner("Importando…"):
            try:
                res = importar_movimientos(db_conn, uid, seleccion, cuenta_id, duplicados_preview)
            except Exception:
                log.exception("Importación falló")
                st.error("No pude importar. No se guardó nada; intenta de nuevo.")
                return
        st.session_state.pop(_k(uid, "staging"), None)
        st.session_state[_k(uid, "ultima")] = {"ids": res["ids"], "n": res["insertados"], "ts": time.time()}
        partes = [f"{res['insertados']} importados"]
        if res["ya_existian"] or res["ahora_duplicados"]:
            partes.append(f"{res['ya_existian'] + res['ahora_duplicados']} ya estaban registrados")
        if res["fallidos"]:
            partes.append(f"{res['fallidos']} no se pudieron guardar")
        st.session_state[_k(uid, "aviso")] = " · ".join(partes)
        st.rerun()                                   # cierra el diálogo y refresca "Tu dinero hoy"


_DECORADOR_DIALOGO = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _DECORADOR_DIALOGO is not None:
    @_DECORADOR_DIALOGO("Importar estado de cuenta", width="large")
    def _dialogo_importacion(db_conn, uid):
        ui_importacion(db_conn, uid)
else:  # Streamlit < 1.34 no tiene diálogos: la UI se muestra en un expander
    _dialogo_importacion = None


def ui_boton_importacion(db_conn, uid, contenedor=None):
    """Botón 'Importar estado de cuenta' + aviso del resultado + 'Deshacer' de la última importación (1 hora)."""
    lugar = contenedor or st
    aviso = st.session_state.pop(_k(uid, "aviso"), None)
    if aviso:
        st.toast(f"Estado de cuenta: {aviso}")

    ultima = st.session_state.get(_k(uid, "ultima"))
    if ultima and ultima["n"] and time.time() - ultima["ts"] < 3600:
        c1, c2 = lugar.columns([3, 1])
        c1.markdown(f"<p class='fp6-nota' style='margin-top:8px;'>Importaste {ultima['n']} movimiento(s) "
                    "de tu estado de cuenta.</p>", unsafe_allow_html=True)
        if c2.button("Deshacer", key=_k(uid, "deshacer"), use_container_width=True,
                     help="Descarta lo importado (no se borra del historial)."):
            try:
                deshacer_importacion(db_conn, uid, ultima["ids"])
                st.session_state.pop(_k(uid, "ultima"), None)
                st.rerun()
            except Exception:
                log.exception("No se pudo deshacer la importación")
                st.error("No pude deshacer la importación. Intenta de nuevo.")

    if _dialogo_importacion is not None:
        if lugar.button("Importar estado de cuenta", key=_k(uid, "abrir"), use_container_width=True):
            _dialogo_importacion(db_conn, uid)
    else:
        with lugar.expander("Importar estado de cuenta"):
            ui_importacion(db_conn, uid)


# ==========================================
# 8. AUTOPRUEBA (pura: sin BD ni Streamlit en ejecución) · python fp_fase6_ui_importacion.py
# ==========================================
def _autoprueba():
    hoy = date(2026, 9, 26)
    # Coherencia de huellas con el bot (si el módulo del bot está en el mismo repo)
    try:
        import fp_fase6_ingesta as bot
        for args in ((1340, hoy, "OXXO SUC 1234"), ("42.5", "2026-09-01", "Tacos El Güero")):
            assert bot.generar_fingerprint(*args) == _generar_fingerprint_local(*args)
    except ImportError:
        pass

    assert _parse_monto("$1,234.56") == Decimal("1234.56") and _parse_monto("(1,234.56)") == Decimal("-1234.56")
    assert _parse_monto("1.234,56") == Decimal("1234.56") and _parse_monto("250.00-") == Decimal("-250.00")
    assert _parse_monto("") is None and _parse_monto("SALDO") is None

    bbva = ("BANCO XYZ\nCuenta: ****1234\n\nFecha;Descripción;Cargo;Abono;Saldo\n"
            "01/09/2026;OXXO SUC 1234 CDMX;85.50;;1000\n02/09/2026;NOMINA EMPRESA;;15,000.00;16000\n"
            "03/09/2026;UBER TRIP;180.00;;15820\n03/09/2026;UBER TRIP;180.00;;15640\n"
            "05/09/2026;OXXO GAS REFORMA;650.00;;14990\n;SALDO FINAL;;;14990\n").encode("cp1252")
    df = leer_csv(bbva)
    mapeo = detectar_mapeo(list(df.columns))
    assert mapeo["modo"] == MODO_CARGO_ABONO and mapeo["concepto"] == "Descripción", mapeo
    filas = normalizar_filas(df, mapeo, hoy=hoy)
    assert [f["tipo"] for f in filas[:2]] == ["GASTO", "INGRESO"] and filas[1]["monto"] == Decimal("15000.00")
    assert filas[-1]["error"]                                            # renglón de saldo final

    ledger = [
        {"id": "M1", "fecha": date(2026, 9, 1), "monto": Decimal("85.50"), "tipo": "GASTO", "texto": "oxxo", "fuente": "TELEGRAM_TEXTO"},
        {"id": "M2", "fecha": date(2026, 9, 3), "monto": Decimal("180.00"), "tipo": "GASTO", "texto": "Uber trip", "fuente": "WEB_MANUAL"},
        {"id": "M3", "fecha": date(2026, 9, 4), "monto": Decimal("650.00"), "tipo": "GASTO", "texto": "gasolina", "fuente": "TELEGRAM_TEXTO"},
    ]
    estados = [f["estado"] for f in _emparejar(filas, ledger, "USR-1")]
    assert estados == [DUPLICADO, NUEVO, DUPLICADO, NUEVO, CONFLICTO, INVALIDO], estados
    claves = [f["mensaje_origen_id"] for f in filas if f.get("mensaje_origen_id")]
    assert len(claves) == len(set(claves))                               # dos Uber iguales → claves distintas

    signo = leer_csv(b"Date,Description,Amount\n09/15/2026,Netflix,-199.00\n09/16/2026,Refund,50\n")
    fs = normalizar_filas(signo, detectar_mapeo(list(signo.columns)), hoy=hoy)
    assert fs[0]["fecha"] == date(2026, 9, 15) and fs[0]["tipo"] == "GASTO" and fs[1]["tipo"] == "INGRESO"
    print(f"fp_fase6_ui_importacion: autoprueba OK (fingerprint: {_FINGERPRINT_ORIGEN})")


if __name__ == "__main__":
    _autoprueba()
