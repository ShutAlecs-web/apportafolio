"""
fp_edicion_ui.py — Edición visual sin fricción (Ronda 2 · Puntos 5 y 6).

Módulo aislado (Norma 2): no toca app.py ni ninguna función existente. Solo se importa y se llama.

Qué hace:
  * Editar / eliminar bolsas (fp_bolsas).
  * Editar / eliminar próximos pagos (la tabla que alimenta fp_ocurrencias: fp_reglas_recurrentes o
    fp_compromisos_programados, detectada sola).
  * Cambiar el `username` del usuario (independencia de cuentas compartidas).

API pública (botones contextuales, se colocan junto a cada sección de la Terminal):
  * ui_boton_bolsas(db_conn, uid, contenedor=None)
  * ui_boton_compromisos(db_conn, uid, contenedor=None)
  * ui_boton_perfil(db_conn, actor_uid, target_uid, contenedor=None)
  `contenedor` (p. ej. st.sidebar) pinta ahí el botón; la ventana siempre se abre en el área principal.

Diseño "schema-adaptive":
  El editor NO asume nombres de columnas. Lee el esquema real desde pg_catalog (legible por cualquier rol
  en Neon, sin depender de to_regclass) y construye el formulario con lo que encuentra. Si algo no cuadra,
  cae a modo seguro (solo lectura o aviso), nunca rompe la Terminal.

Suposiciones (Norma 3, documentadas):
  - fp_bolsas y fp_reglas_recurrentes tienen columna `user_id` (sin ella no se edita nada).
  - Llave primaria simple. Si pg_catalog no la reporta, se usa la convención bolsa_id / regla_id / id.

Requisitos: streamlit >= 1.37 recomendado (st.dialog). Con versiones anteriores usa st.experimental_dialog
y, si tampoco existe, cae automáticamente a un st.expander debajo del botón.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

import pandas as pd
import psycopg2
import streamlit as st
from psycopg2 import sql

try:
    from seguridad_auth import verificar_usuario   # módulo de la Ronda 1
except Exception:
    verificar_usuario = None                        # sin él, el cambio de username se bloquea por seguridad


# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
ADMIN_UID = "USR-001"
COLUMNA_USUARIO = "user_id"
LIMITE_FILAS = 500

TABLA_BOLSAS_CANDIDATAS = ("fp_bolsas",)
TABLA_COMPROMISOS_CANDIDATAS = ("fp_reglas_recurrentes", "fp_compromisos_programados")
# Se elige la que lea la función fp_ocurrencias (la misma que pinta "Lo que viene"), para que lo que
# edites se vea de inmediato. Si no se puede saber, la primera cuyo esquema sea legible.
# Forzar una tabla: st.secrets["FP_TABLA_COMPROMISOS"] = "nombre_tabla".
FUNCION_OCURRENCIAS = "fp_ocurrencias"

# Columnas que jamás se editan desde la UI.
COLUMNAS_SIEMPRE_BLOQUEADAS = {
    COLUMNA_USUARIO, "creado_en", "created_at", "actualizado_en", "updated_at",
    "timestamp", "mensaje_origen_id", "fuente", "vinculado_en",
}
# Tipos que ni siquiera se muestran (listas, JSON): ilegibles para el usuario.
TIPOS_NO_VISIBLES = {"ARRAY", "json", "jsonb", "bytea", "tsvector"}
# Columnas técnicas que no se MUESTRAN (siguen en el DataFrame interno para el UPDATE).
COLUMNAS_OCULTAS = {
    COLUMNA_USUARIO, "bolsa_id", "regla_id", "compromiso_id", "meta_id", "prioridad",
    "creado_en", "actualizado_en", "created_at", "updated_at", "timestamp", "mensaje_origen_id", "vinculado_en",
    "fuente",
}
OCULTAR_SUFIJO_ID = True   # oculta también cualquier otra columna *_id (cuenta_id, categoria_id...). ALTERNATIVA: False

# Campos probablemente derivados por el motor de Dinero Libre: solo lectura para no desincronizar saldos.
# ALTERNATIVA: vaciar esta tupla si quieres permitir ajustes manuales de saldo.
PATRONES_DERIVADOS = ("saldo", "consumido", "gastado", "acumulado", "disponible")

# Si existe alguna de estas columnas booleanas, "Eliminar" = desactivar (reversible).
BANDERAS_SOFT_DELETE = ("activa", "activo", "vigente")
# ALTERNATIVA (borrado físico siempre): cambiar a  BANDERAS_SOFT_DELETE = ()

# Baja lógica por columna `estado` (reversible y respeta el historial del ledger):
COLUMNA_ESTADO = "estado"
ESTADO_BAJA_POR_TABLA = {"fp_compromisos_programados": "FINALIZADO"}   # mismo valor que usa el bot
ESTADOS_BAJA_CANDIDATOS = ("FINALIZADO", "CANCELADO", "INACTIVO", "ELIMINADO")

# Convención de llaves primarias si el catálogo no reporta la PK.
PK_CONVENCIONALES = ("bolsa_id", "regla_id", "compromiso_id", "meta_id", "id")

TIPOS_ENTEROS = {"integer", "bigint", "smallint"}
TIPOS_DECIMALES = {"numeric", "real", "double precision", "decimal"}
TIPOS_NUMERICOS = TIPOS_ENTEROS | TIPOS_DECIMALES
TIPOS_TEXTO = {"text", "character varying", "character", "varchar", "char"}
TIPOS_TIMESTAMP = {"timestamp with time zone", "timestamp without time zone"}
# Tipos que la tabla editable no maneja con seguridad → solo lectura.
# (Timestamps bloqueados para evitar corrimientos de zona horaria; ALTERNATIVA: quitarlos de aquí.)
TIPOS_NO_EDITABLES = {
    "json", "jsonb", "bytea", "ARRAY", "USER-DEFINED", "tsvector", "uuid", "money",
    "time without time zone", "time with time zone", "interval",
} | TIPOS_TIMESTAMP

ORDEN_PREFERIDO = ("proxima_fecha", "fecha_proxima", "fecha_vencimiento", "fecha_pago", "dia_pago", "fecha", "nombre")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._\-]{3,30}$")

COL_ELIMINAR = "Eliminar"


# ==========================================
# 2. DIÁLOGOS (st.dialog → experimental_dialog → expander)
# ==========================================
_DIALOG = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)


def _como_dialogo(titulo):
    def deco(fn):
        if _DIALOG is None:
            return fn
        try:
            return _DIALOG(titulo, width="large")(fn)
        except TypeError:
            return _DIALOG(titulo)(fn)
    return deco


# ==========================================
# 3. UTILIDADES
# ==========================================
def _secret(clave, default=None):
    try:
        return st.secrets[clave]
    except Exception:
        return default


def _es_nulo(v) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, tuple, dict, set)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _py(v, tipo=None):
    """Convierte valores de pandas/numpy a tipos nativos que psycopg2 sabe adaptar."""
    if _es_nulo(v):
        return None
    if isinstance(v, pd.Timestamp):
        v = v.to_pydatetime()
    elif hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()          # numpy.int64 / float64 / bool_
        except Exception:
            pass
    if tipo == "date" and isinstance(v, _dt.datetime):
        v = v.date()
    if tipo in TIPOS_ENTEROS and isinstance(v, float) and v.is_integer():
        v = int(v)
    if tipo in TIPOS_TEXTO and isinstance(v, str):
        v = v.strip()
    return v


def _iguales(a, b) -> bool:
    na, nb = _es_nulo(a), _es_nulo(b)
    if na or nb:
        return na and nb
    a, b = _py(a), _py(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)
    if isinstance(a, _dt.datetime) and not isinstance(b, _dt.datetime):
        a = a.date()
    if isinstance(b, _dt.datetime) and not isinstance(a, _dt.datetime):
        b = b.date()
    return a == b


def _etiqueta(col: str) -> str:
    return col.replace("_", " ").strip().capitalize()


def _flash(mensaje: str):
    st.session_state["fpedit_flash"] = mensaje


def _mostrar_flash():
    """Muestra una sola vez el mensaje pendiente de la última acción (lo consume el primer botón que se pinte)."""
    flash = st.session_state.pop("fpedit_flash", None)
    if flash:
        try:
            st.toast(flash)
        except Exception:
            st.success(flash)


def _normalizar_tipo(tipo_pg: str) -> str:
    """'numeric(12,2)' -> 'numeric'; 'character varying(120)' -> 'character varying'; 'text[]' -> 'ARRAY'."""
    t = str(tipo_pg or "").strip()
    if t.endswith("[]"):
        return "ARRAY"
    t = re.sub(r"\(.*?\)", "", t).strip()
    return {"timestamptz": "timestamp with time zone", "timestamp": "timestamp without time zone"}.get(t, t)


# ==========================================
# 4. RESOLUCIÓN DE TABLAS E INTROSPECCIÓN DEL ESQUEMA
# ==========================================
def _resolver_tabla(_db_conn, candidatas: tuple):
    # Simplificado: to_regclass devolvía NULL por permisos en Neon. Se toma la primera candidata.
    return candidatas[0] if candidatas else None


def _leer_esquema(db_conn, tabla: str):
    """Lee columnas y PK desde pg_catalog. Lanza excepción si no hay columnas (así no se cachea un fallo)."""
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname,
                   CASE WHEN ty.typtype = 'd' THEN format_type(ty.typbasetype, ty.typtypmod)
                        ELSE format_type(a.atttypid, a.atttypmod) END,
                   NOT a.attnotnull,
                   ty.typtype::text,
                   CASE WHEN ty.typtype = 'e' THEN
                        ARRAY(SELECT e.enumlabel::text FROM pg_enum e
                               WHERE e.enumtypid = a.atttypid ORDER BY e.enumsortorder) END,
                   (a.attgenerated <> '')
              FROM pg_attribute a
              JOIN pg_class t     ON t.oid = a.attrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
              JOIN pg_type ty     ON ty.oid = a.atttypid
             WHERE t.relname = %s
               AND n.nspname = ANY(current_schemas(false))
               AND a.attnum > 0 AND NOT a.attisdropped
             ORDER BY a.attnum
            """,
            (tabla,),
        )
        filas = cur.fetchall()
        if not filas:
            # Respaldo: information_schema (por si el rol no ve pg_attribute de esa tabla).
            cur.execute(
                """
                SELECT column_name, data_type, (is_nullable = 'YES')
                  FROM information_schema.columns
                 WHERE table_schema = current_schema() AND table_name = %s
                 ORDER BY ordinal_position
                """,
                (tabla,),
            )
            filas = [(c, t, n, "b", None, False) for c, t, n in cur.fetchall()]
        cur.execute(
            """
            SELECT a.attname
              FROM pg_constraint c
              JOIN pg_class t     ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
              JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
             WHERE c.contype = 'p'
               AND t.relname = %s
               AND n.nspname = ANY(current_schemas(false))
            """,
            (tabla,),
        )
        pks = [r[0] for r in cur.fetchall()]

    if not filas:
        raise LookupError(f"Sin columnas visibles para {tabla}")

    tipos, opciones, generadas = {}, {}, set()
    for c, t, _, typtype, etiquetas, generada in filas:
        if typtype == "e":
            tipos[c] = "enum"
            opciones[c] = list(etiquetas or [])
        else:
            tipos[c] = _normalizar_tipo(t)
        if generada:
            generadas.add(c)
    pk = pks[0] if len(pks) == 1 else None
    if pk is None and not pks:
        pk = next((c for c in PK_CONVENCIONALES if c in tipos), None)
    return {
        "tipos": tipos,
        "nulos": {f[0]: bool(f[2]) for f in filas},
        "orden": [f[0] for f in filas],
        "pk": pk,
        "opciones": opciones,     # valores permitidos de columnas ENUM (se editan con lista desplegable)
        "generadas": generadas,   # columnas GENERATED: Postgres no permite escribirlas
        "tabla": tabla,
    }


@st.cache_data(ttl=600, show_spinner=False)
def _esquema_cacheado(_db_conn, tabla: str):
    return _leer_esquema(_db_conn, tabla)   # si lanza excepción, Streamlit NO la guarda en caché


def _esquema(db_conn, tabla: str):
    """{'tipos': {col: tipo}, 'nulos': {col: bool}, 'orden': [cols], 'pk': col|None} o None."""
    if not tabla:
        return None
    try:
        return _esquema_cacheado(db_conn, tabla)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _fuente_funcion(_db_conn, nombre_funcion: str) -> str:
    """Código fuente de una función SQL (pg_proc es legible por cualquier rol)."""
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(string_agg(prosrc, ' '), '') FROM pg_proc WHERE proname = %s", (nombre_funcion,))
        fila = cur.fetchone()
    return (fila[0] if fila else "") or ""


def _tabla_compromisos(db_conn):
    """Tabla de próximos pagos: forzada por secrets > la que usa fp_ocurrencias > la primera legible."""
    override = _secret("FP_TABLA_COMPROMISOS")
    if override:
        return _resolver_tabla(db_conn, (str(override).strip(),))
    try:
        fuente = _fuente_funcion(db_conn, FUNCION_OCURRENCIAS).lower()
    except Exception:
        fuente = ""
    usada = next((t for t in TABLA_COMPROMISOS_CANDIDATAS if re.search(rf"\b{re.escape(t)}\b", fuente)), None)
    if usada:
        return usada
    legible = next((t for t in TABLA_COMPROMISOS_CANDIDATAS if _esquema(db_conn, t)), None)
    return legible or _resolver_tabla(db_conn, TABLA_COMPROMISOS_CANDIDATAS)


def _columnas_bloqueadas(esq) -> set:
    bloqueadas = set()
    for col, tipo in esq["tipos"].items():
        if (col in COLUMNAS_SIEMPRE_BLOQUEADAS or col == esq["pk"] or tipo in TIPOS_NO_EDITABLES
                or col in esq.get("generadas", ()) or any(p in col.lower() for p in PATRONES_DERIVADOS)):
            bloqueadas.add(col)
    return bloqueadas


def _columnas_visibles(esq, columnas_df) -> list:
    """Orden de columnas para la vista: COL_ELIMINAR + solo columnas legibles para el usuario."""
    visibles = []
    for col in columnas_df:
        if col == COL_ELIMINAR:
            continue
        tipo = esq["tipos"].get(col, "")
        if col in COLUMNAS_OCULTAS or col == esq["pk"] or tipo in TIPOS_TIMESTAMP or tipo in TIPOS_NO_VISIBLES:
            continue
        if OCULTAR_SUFIJO_ID and col.lower().endswith("_id"):
            continue
        visibles.append(col)
    return [COL_ELIMINAR] + visibles


def _bandera_soft_delete(esq):
    return next((b for b in BANDERAS_SOFT_DELETE if esq["tipos"].get(b) == "boolean"), None)


def _baja_logica(esq):
    """(columna, valor_de_baja, valores_ocultos) o None si solo cabe borrado físico."""
    bandera = _bandera_soft_delete(esq)
    if bandera:
        return bandera, False, None
    if COLUMNA_ESTADO in esq["tipos"]:
        if esq["tipos"][COLUMNA_ESTADO] == "enum":
            posibles = [v for v in ESTADOS_BAJA_CANDIDATOS if v in esq.get("opciones", {}).get(COLUMNA_ESTADO, [])]
            if posibles:
                return COLUMNA_ESTADO, posibles[0], posibles
        valor = ESTADO_BAJA_POR_TABLA.get(esq.get("tabla"))
        if valor:
            return COLUMNA_ESTADO, valor, [valor]
    return None


# ==========================================
# 5. LECTURA Y ESCRITURA
# ==========================================
def _cargar(db_conn, tabla, esq, uid) -> pd.DataFrame:
    baja = _baja_logica(esq)
    orden = next((c for c in ORDEN_PREFERIDO if c in esq["tipos"]), esq["pk"] or esq["orden"][0])
    if baja and baja[2] is None:
        filtro = sql.SQL(" AND {} IS NOT FALSE").format(sql.Identifier(baja[0]))
    elif baja:
        filtro = sql.SQL(" AND ({c} IS NULL OR {c}::text NOT IN ({v}))").format(
            c=sql.Identifier(baja[0]), v=sql.SQL(", ").join(sql.Literal(x) for x in baja[2]))
    else:
        filtro = sql.SQL("")
    consulta = sql.SQL("SELECT * FROM {t} WHERE {u} = %s{f} ORDER BY {o} NULLS LAST LIMIT {lim}").format(
        t=sql.Identifier(tabla), u=sql.Identifier(COLUMNA_USUARIO), f=filtro,
        o=sql.Identifier(orden), lim=sql.Literal(LIMITE_FILAS),
    )
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(consulta, (uid,))
        columnas = [d[0] for d in cur.description]
        filas = cur.fetchall()
    df = pd.DataFrame(filas, columns=columnas)
    for col, tipo in esq["tipos"].items():
        if col not in df.columns:
            continue
        if tipo in TIPOS_NUMERICOS:
            df[col] = pd.to_numeric(df[col], errors="coerce")          # Decimal → float para el editor
        elif tipo == "date":
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def _column_config(esq, bloqueadas):
    cfg = {COL_ELIMINAR: st.column_config.CheckboxColumn(
        COL_ELIMINAR, help="Marca y guarda para eliminar (o desactivar) el registro.", default=False)}
    for col, tipo in esq["tipos"].items():
        requerido = (not esq["nulos"].get(col, True)) and col not in bloqueadas
        if tipo in TIPOS_ENTEROS:
            cfg[col] = st.column_config.NumberColumn(_etiqueta(col), format="%d", step=1, required=requerido)
        elif tipo in TIPOS_DECIMALES:
            cfg[col] = st.column_config.NumberColumn(_etiqueta(col), format="%.2f", required=requerido)
        elif tipo == "date":
            cfg[col] = st.column_config.DateColumn(_etiqueta(col), format="DD/MM/YYYY", required=requerido)
        elif tipo == "boolean":
            cfg[col] = st.column_config.CheckboxColumn(_etiqueta(col))
        elif tipo == "enum":
            cfg[col] = st.column_config.SelectboxColumn(
                _etiqueta(col), options=esq.get("opciones", {}).get(col, []), required=requerido)
        else:
            cfg[col] = st.column_config.TextColumn(_etiqueta(col), required=requerido)
    return cfg


def _persistir(db_conn, tabla, esq, uid, original, editado, marcados):
    """Aplica UPDATEs y eliminaciones en UNA transacción. Devuelve (n_actualizados, n_eliminados, modo)."""
    pk, tipos = esq["pk"], esq["tipos"]
    bloqueadas = _columnas_bloqueadas(esq)
    editables = [c for c in original.columns if c not in bloqueadas and c != pk]

    orig = original.set_index(pk)
    edit = editado.drop(columns=[COL_ELIMINAR]).set_index(pk)
    marcados_set = {_py(m) for m in marcados}

    actualizaciones = []
    for clave in edit.index:
        k = _py(clave)
        if k in marcados_set or clave not in orig.index:
            continue
        cambios = {}
        for col in editables:
            if col not in edit.columns:
                continue
            nuevo = edit.at[clave, col]
            if not _iguales(orig.at[clave, col], nuevo):
                valor = _py(nuevo, tipos.get(col))
                if valor is None and not esq["nulos"].get(col, True):
                    raise ValueError(f"El campo '{_etiqueta(col)}' no puede quedar vacío.")
                cambios[col] = valor
        if cambios:
            actualizaciones.append((k, cambios))

    baja = _baja_logica(esq)
    t, pk_id, u_id = sql.Identifier(tabla), sql.Identifier(pk), sql.Identifier(COLUMNA_USUARIO)

    with db_conn() as conn, conn.cursor() as cur:
        for k, cambios in actualizaciones:
            sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in cambios)
            cur.execute(
                sql.SQL("UPDATE {t} SET {s} WHERE {pk} = %s AND {u} = %s").format(t=t, s=sets, pk=pk_id, u=u_id),
                list(cambios.values()) + [k, uid],
            )
        for k in marcados_set:
            if baja:
                cur.execute(
                    sql.SQL("UPDATE {t} SET {b} = %s WHERE {pk} = %s AND {u} = %s").format(
                        t=t, b=sql.Identifier(baja[0]), pk=pk_id, u=u_id),
                    (baja[1], k, uid),
                )
            else:
                cur.execute(
                    sql.SQL("DELETE FROM {t} WHERE {pk} = %s AND {u} = %s").format(t=t, pk=pk_id, u=u_id),
                    (k, uid),
                )
    return len(actualizaciones), len(marcados_set), ("desactivado(s)" if baja else "eliminado(s)")


def _mensaje_error_pg(e) -> str:
    codigo = getattr(e, "pgcode", None) or ""
    if codigo == "23503":
        return "No se puede eliminar: el registro tiene movimientos asociados. Edítalo en lugar de borrarlo."
    if codigo == "23502":
        return "Hay un campo obligatorio vacío."
    if codigo == "23505":
        return "Ya existe otro registro con ese mismo valor."
    if codigo == "23514":
        return "Uno de los valores no cumple las reglas de la tabla (por ejemplo, montos negativos)."
    if codigo == "42501":
        return "Tu usuario de base de datos no tiene permiso para modificar esta tabla."
    if codigo.startswith("22"):
        return "Uno de los valores tiene un formato inválido."
    return "No se pudieron guardar los cambios. No se modificó nada."


# ==========================================
# 6. EDITOR GENÉRICO DE TABLA (bolsas / compromisos)
# ==========================================
def _editor_tabla(db_conn, clave, nombre_humano, tabla, uid):
    esq = _esquema(db_conn, tabla)
    if not esq:
        st.error(f"No pude leer la estructura de {nombre_humano}.")
        return
    if COLUMNA_USUARIO not in esq["tipos"]:
        st.error(f"La tabla de {nombre_humano} no tiene '{COLUMNA_USUARIO}'. Por seguridad no se edita.")
        return

    pk = esq["pk"]
    try:
        df = _cargar(db_conn, tabla, esq, uid)
    except Exception:
        st.error(f"No pude cargar tus {nombre_humano}. Inténtalo de nuevo.")
        return

    if df.empty:
        st.info(f"Todavía no tienes {nombre_humano} registradas.")
        return

    bloqueadas = _columnas_bloqueadas(esq)
    vista = df.copy()
    vista.insert(0, COL_ELIMINAR, False)
    orden_vista = _columnas_visibles(esq, vista.columns)   # IDs y fechas técnicas quedan fuera de la vista

    if not pk:
        st.warning("Esta tabla no tiene llave primaria simple: se muestra en solo lectura.")
        st.dataframe(vista, hide_index=True, use_container_width=True,
                     column_order=[c for c in orden_vista if c != COL_ELIMINAR])
        return

    version = st.session_state.get(f"fpedit_ver_{clave}", 0)
    st.caption("Toca una celda para editarla. Los campos en gris se calculan solos.")
    editado = st.data_editor(
        vista,                                   # conserva TODAS las columnas (IDs incluidos) para el UPDATE
        key=f"fpedit_editor_{clave}_{version}",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_order=orden_vista,                # solo se MUESTRAN Eliminar + columnas legibles
        column_config=_column_config(esq, bloqueadas),
        disabled=sorted(bloqueadas),
    )

    marcados = editado.loc[editado[COL_ELIMINAR] == True, pk].tolist()  # noqa: E712
    confirmado = True
    if marcados:
        accion = "quitar de tu lista" if _baja_logica(esq) else "eliminar definitivamente"
        confirmado = st.checkbox(f"Confirmo {accion} {len(marcados)} registro(s).", key=f"fpedit_conf_{clave}_{version}")

    c1, c2 = st.columns([1, 1])
    guardar = c1.button("Guardar cambios", type="primary", use_container_width=True, key=f"fpedit_save_{clave}_{version}")
    cancelar = c2.button("Cancelar", use_container_width=True, key=f"fpedit_cancel_{clave}_{version}")

    if cancelar:
        st.session_state[f"fpedit_abierto_{clave}"] = False
        st.session_state[f"fpedit_ver_{clave}"] = version + 1
        st.rerun()

    if guardar:
        if marcados and not confirmado:
            st.warning("Confirma la eliminación marcando la casilla.")
            return
        try:
            n_upd, n_del, modo = _persistir(db_conn, tabla, esq, uid, df, editado, marcados)
        except ValueError as e:
            st.error(str(e))
            return
        except psycopg2.Error as e:
            st.error(_mensaje_error_pg(e))
            return
        except Exception:
            st.error("No se pudieron guardar los cambios. No se modificó nada.")
            return

        if n_upd == 0 and n_del == 0:
            st.info("No hay cambios que guardar.")
            return
        partes = []
        if n_upd:
            partes.append(f"{n_upd} actualizado(s)")
        if n_del:
            partes.append(f"{n_del} {modo}")
        _flash(f"{nombre_humano.capitalize()}: " + ", ".join(partes) + ".")
        st.session_state[f"fpedit_ver_{clave}"] = version + 1
        st.session_state[f"fpedit_abierto_{clave}"] = False
        st.rerun()


# ==========================================
# 7. EDITOR DE USERNAME (independencia de cuentas)
# ==========================================
def _editor_username(db_conn, actor_uid, target_uid):
    if verificar_usuario is None:
        st.error("Falta el módulo seguridad_auth.py; el cambio de usuario está bloqueado por seguridad.")
        return

    # Un cliente solo puede renombrarse a sí mismo; el gestor puede renombrar al cliente activo.
    if actor_uid != ADMIN_UID:
        target_uid = actor_uid

    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE user_id = %s", (target_uid,))
            fila = cur.fetchone()
    except Exception:
        st.error("No pude leer tu perfil en este momento.")
        return
    if not fila:
        st.error("Perfil no encontrado.")
        return
    actual = fila[0] or ""

    es_gestor_sobre_cliente = actor_uid == ADMIN_UID and target_uid != actor_uid
    st.caption(
        f"Usuario actual: **{actual}**. Tus datos, bolsas y vinculación de Telegram no cambian: "
        "solo cambia el nombre con el que inicias sesión."
    )
    version = st.session_state.get("fpedit_ver_username", 0)
    nuevo = st.text_input("Nuevo nombre de usuario", value=actual, max_chars=30, key=f"fpedit_usr_nuevo_{version}",
                          help="3 a 30 caracteres: letras, números, punto, guion o guion bajo.")
    etiqueta_clave = "Contraseña del gestor" if es_gestor_sobre_cliente else "Tu contraseña actual"
    clave = st.text_input(etiqueta_clave, type="password", key=f"fpedit_usr_clave_{version}")

    c1, c2 = st.columns([1, 1])
    guardar = c1.button("Guardar nombre", type="primary", use_container_width=True, key=f"fpedit_usr_save_{version}")
    cancelar = c2.button("Cancelar", use_container_width=True, key=f"fpedit_usr_cancel_{version}")

    if cancelar:
        st.session_state["fpedit_abierto_username"] = False
        st.session_state["fpedit_ver_username"] = version + 1
        st.rerun()
    if not guardar:
        return

    nuevo = (nuevo or "").strip()
    if nuevo == actual:
        st.info("Es el mismo nombre de usuario.")
        return
    if not USERNAME_RE.match(nuevo):
        st.error("Usa de 3 a 30 caracteres: letras, números, punto, guion o guion bajo (sin espacios).")
        return
    if not clave:
        st.error("Confirma con tu contraseña.")
        return
    if not verificar_usuario(db_conn, actor_uid, clave):
        st.error("Contraseña incorrecta.")
        return

    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE LOWER(username) = LOWER(%s) AND user_id <> %s", (nuevo, target_uid))
            if cur.fetchone():
                st.error("Ese nombre de usuario ya está en uso. Prueba con otro.")
                return
            # Bloqueo optimista: solo cambia si nadie lo modificó mientras tanto.
            cur.execute("UPDATE users SET username = %s WHERE user_id = %s AND username = %s", (nuevo, target_uid, actual))
            if cur.rowcount != 1:
                st.warning("El perfil cambió mientras editabas. Vuelve a abrir esta ventana.")
                return
    except psycopg2.Error as e:
        st.error(_mensaje_error_pg(e))
        return
    except Exception:
        st.error("No se pudo actualizar el nombre de usuario. No se modificó nada.")
        return

    _flash(f"Listo: tu nuevo usuario es {nuevo}. Úsalo en tu próximo inicio de sesión.")
    st.session_state["fpedit_ver_username"] = version + 1
    st.session_state["fpedit_abierto_username"] = False
    st.rerun()


# ==========================================
# 8. DIÁLOGOS CONCRETOS
# ==========================================
@_como_dialogo("Editar bolsas")
def _dialogo_bolsas(db_conn, uid, tabla):
    _editor_tabla(db_conn, "bolsas", "bolsas", tabla, uid)


@_como_dialogo("Editar próximos pagos")
def _dialogo_compromisos(db_conn, uid, tabla):
    _editor_tabla(db_conn, "compromisos", "próximos pagos", tabla, uid)


@_como_dialogo("Perfil y usuario")
def _dialogo_username(db_conn, actor_uid, target_uid):
    _editor_username(db_conn, actor_uid, target_uid)


def _boton_contextual(etiqueta, key, clave, titulo_fallback, dialogo_fn, editor_fn, args_dialogo, args_editor,
                      ayuda=None, contenedor=None, ancho_completo=False):
    """Pinta el botón en `contenedor` (o donde se llame). Con st.dialog abre un modal: la llamada se hace
    FUERA del contenedor para que la ventana nunca quede atrapada en el sidebar. Sin st.dialog, abre un
    expander persistente justo debajo del botón."""
    _mostrar_flash()
    destino = contenedor if contenedor is not None else st
    if destino.button(etiqueta, key=key, help=ayuda, use_container_width=ancho_completo):
        if _DIALOG is not None:
            dialogo_fn(*args_dialogo)
        else:
            st.session_state[f"fpedit_abierto_{clave}"] = True
    if _DIALOG is None and st.session_state.get(f"fpedit_abierto_{clave}"):
        with destino.expander(titulo_fallback, expanded=True):
            editor_fn(*args_editor)


# ==========================================
# 9. API PÚBLICA — BOTONES CONTEXTUALES
# ==========================================
def ui_boton_bolsas(db_conn, uid, contenedor=None):
    """Botón ✏️ para editar/eliminar bolsas. Colócalo junto al encabezado de tus bolsas."""
    if not uid:
        return
    tabla = _resolver_tabla(db_conn, TABLA_BOLSAS_CANDIDATAS)
    _boton_contextual(
        "✏️", "btn_bolsas", "bolsas", "Editar bolsas",
        _dialogo_bolsas, _editor_tabla,
        (db_conn, uid, tabla), (db_conn, "bolsas", "bolsas", tabla, uid),
        ayuda="Editar o eliminar bolsas", contenedor=contenedor,
    )


def ui_boton_compromisos(db_conn, uid, contenedor=None):
    """Botón ✏️ para editar/eliminar próximos pagos. Colócalo junto al encabezado de tus compromisos."""
    if not uid:
        return
    tabla = _tabla_compromisos(db_conn)
    _boton_contextual(
        "✏️", "btn_comp", "compromisos", "Editar próximos pagos",
        _dialogo_compromisos, _editor_tabla,
        (db_conn, uid, tabla), (db_conn, "compromisos", "próximos pagos", tabla, uid),
        ayuda="Editar o eliminar próximos pagos", contenedor=contenedor,
    )


def ui_boton_perfil(db_conn, actor_uid, target_uid, contenedor=None):
    """Botón ⚙️ para cambiar el nombre de usuario.
    actor_uid  = quien inició sesión (su contraseña confirma el cambio).
    target_uid = perfil a renombrar (el gestor puede pasar el cliente activo; un cliente, su propio uid).
    contenedor = st.sidebar para pintarlo en el menú lateral (NO lo envuelvas en `with st.sidebar:`)."""
    if not actor_uid:
        return
    target_uid = target_uid or actor_uid
    _boton_contextual(
        "⚙️ Perfil y Usuario", "btn_perfil", "username", "Perfil y usuario",
        _dialogo_username, _editor_username,
        (db_conn, actor_uid, target_uid), (db_conn, actor_uid, target_uid),
        contenedor=contenedor, ancho_completo=True,
    )
