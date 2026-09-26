"""
fp_edicion_ui.py — Edición visual sin fricción (Ronda 2 · Puntos 5 y 6).

Módulo aislado (Norma 2): no toca app.py ni ninguna función existente. Solo se importa y se llama.

Qué hace:
  * Editar / eliminar bolsas (fp_bolsas).
  * Editar / eliminar próximos pagos o compromisos.
  * Cambiar el `username` del usuario activo (independencia de cuentas compartidas).

Diseño "schema-adaptive":
  El editor NO asume nombres de columnas. Lee el esquema real de Neon (information_schema + pg_index)
  y construye el formulario con lo que encuentra. Si algo no cuadra, cae a modo seguro (solo lectura
  o aviso), nunca rompe la Terminal.

Suposiciones (Norma 3, documentadas):
  - Asumí que fp_bolsas y la tabla de compromisos tienen columna `user_id` (sin ella no se edita nada).
  - Asumí que la tabla de compromisos es la primera que exista de TABLA_COMPROMISOS_CANDIDATAS
    (o la definida en st.secrets["FP_TABLA_COMPROMISOS"]).
  - Asumí llave primaria simple (una columna). Con PK compuesta o sin PK, el editor queda en solo lectura.

Requisitos: streamlit >= 1.37 recomendado (st.dialog). Con versiones anteriores usa st.experimental_dialog
y, si tampoco existe, cae automáticamente a un st.expander.
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
TABLA_COMPROMISOS_CANDIDATAS = ("fp_compromisos", "fp_proximos_pagos", "fp_pagos_programados", "fp_commitments")

# Columnas que jamás se editan desde la UI.
COLUMNAS_SIEMPRE_BLOQUEADAS = {
    COLUMNA_USUARIO, "creado_en", "created_at", "actualizado_en", "updated_at",
    "timestamp", "mensaje_origen_id", "fuente", "vinculado_en",
}
# Campos probablemente derivados por el motor de Dinero Libre: solo lectura para no desincronizar saldos.
# ALTERNATIVA: vaciar esta tupla si quieres permitir ajustes manuales de saldo.
PATRONES_DERIVADOS = ("saldo", "consumido", "gastado", "acumulado", "disponible")

# Si existe alguna de estas columnas booleanas, "Eliminar" = desactivar (reversible).
BANDERAS_SOFT_DELETE = ("activa", "activo", "vigente")
# ALTERNATIVA (borrado físico siempre): cambiar a  BANDERAS_SOFT_DELETE = ()

TIPOS_ENTEROS = {"integer", "bigint", "smallint"}
TIPOS_DECIMALES = {"numeric", "real", "double precision", "decimal"}
TIPOS_NUMERICOS = TIPOS_ENTEROS | TIPOS_DECIMALES
TIPOS_TEXTO = {"text", "character varying", "character", "varchar", "char"}
# Tipos que la tabla editable no maneja con seguridad → solo lectura.
# (Timestamps bloqueados para evitar corrimientos de zona horaria; ALTERNATIVA: quitarlos de aquí.)
TIPOS_NO_EDITABLES = {
    "json", "jsonb", "bytea", "ARRAY", "USER-DEFINED", "tsvector", "uuid", "money",
    "timestamp with time zone", "timestamp without time zone", "time without time zone",
    "time with time zone", "interval",
}

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


# ==========================================
# 4. INTROSPECCIÓN DEL ESQUEMA (cacheada)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def _resolver_tabla(_db_conn, candidatas: tuple):
    """Primera tabla existente de la lista, o None."""
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            for nombre in candidatas:
                if not nombre:
                    continue
                cur.execute("SELECT to_regclass(%s)", (str(nombre),))
                fila = cur.fetchone()
                if fila and fila[0]:
                    return str(nombre)
    except Exception:
        return None
    return None


@st.cache_data(ttl=600, show_spinner=False)
def _esquema(_db_conn, tabla: str):
    """{'tipos': {col: data_type}, 'nulos': {col: bool}, 'orden': [cols], 'pk': col|None}"""
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable
                  FROM information_schema.columns
                 WHERE table_schema = current_schema() AND table_name = %s
                 ORDER BY ordinal_position
                """,
                (tabla,),
            )
            filas = cur.fetchall()
            cur.execute(
                """
                SELECT a.attname
                  FROM pg_index i
                  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                 WHERE i.indrelid = to_regclass(%s) AND i.indisprimary
                """,
                (tabla,),
            )
            pks = [r[0] for r in cur.fetchall()]
    except Exception:
        return None
    if not filas:
        return None
    return {
        "tipos": {c: t for c, t, _ in filas},
        "nulos": {c: (n == "YES") for c, _, n in filas},
        "orden": [c for c, _, _ in filas],
        "pk": pks[0] if len(pks) == 1 else None,
    }


def _columnas_bloqueadas(esq) -> set:
    bloqueadas = set()
    for col, tipo in esq["tipos"].items():
        if (col in COLUMNAS_SIEMPRE_BLOQUEADAS or col == esq["pk"] or tipo in TIPOS_NO_EDITABLES
                or any(p in col.lower() for p in PATRONES_DERIVADOS)):
            bloqueadas.add(col)
    return bloqueadas


def _bandera_soft_delete(esq):
    return next((b for b in BANDERAS_SOFT_DELETE if esq["tipos"].get(b) == "boolean"), None)


# ==========================================
# 5. LECTURA Y ESCRITURA
# ==========================================
def _cargar(db_conn, tabla, esq, uid) -> pd.DataFrame:
    bandera = _bandera_soft_delete(esq)
    orden = next((c for c in ORDEN_PREFERIDO if c in esq["tipos"]), esq["pk"] or esq["orden"][0])
    filtro = sql.SQL(" AND {} IS NOT FALSE").format(sql.Identifier(bandera)) if bandera else sql.SQL("")
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
            nuevo = edit.at[clave, col]
            if not _iguales(orig.at[clave, col], nuevo):
                valor = _py(nuevo, tipos.get(col))
                if valor is None and not esq["nulos"].get(col, True):
                    raise ValueError(f"El campo '{_etiqueta(col)}' no puede quedar vacío.")
                cambios[col] = valor
        if cambios:
            actualizaciones.append((k, cambios))

    bandera = _bandera_soft_delete(esq)
    t, pk_id, u_id = sql.Identifier(tabla), sql.Identifier(pk), sql.Identifier(COLUMNA_USUARIO)

    with db_conn() as conn, conn.cursor() as cur:
        for k, cambios in actualizaciones:
            sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in cambios)
            cur.execute(
                sql.SQL("UPDATE {t} SET {s} WHERE {pk} = %s AND {u} = %s").format(t=t, s=sets, pk=pk_id, u=u_id),
                list(cambios.values()) + [k, uid],
            )
        for k in marcados_set:
            if bandera:
                cur.execute(
                    sql.SQL("UPDATE {t} SET {b} = FALSE WHERE {pk} = %s AND {u} = %s").format(
                        t=t, b=sql.Identifier(bandera), pk=pk_id, u=u_id),
                    (k, uid),
                )
            else:
                cur.execute(
                    sql.SQL("DELETE FROM {t} WHERE {pk} = %s AND {u} = %s").format(t=t, pk=pk_id, u=u_id),
                    (k, uid),
                )
    return len(actualizaciones), len(marcados_set), ("desactivado(s)" if bandera else "eliminado(s)")


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
    if not pk:
        st.warning("Esta tabla no tiene llave primaria simple: se muestra en solo lectura.")
        st.dataframe(df, hide_index=True, use_container_width=True)
        return

    bloqueadas = _columnas_bloqueadas(esq)
    vista = df.copy()
    vista.insert(0, COL_ELIMINAR, False)

    version = st.session_state.get(f"fpedit_ver_{clave}", 0)
    st.caption("Toca una celda para editarla. Los campos en gris se calculan solos.")
    editado = st.data_editor(
        vista,
        key=f"fpedit_editor_{clave}_{version}",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config=_column_config(esq, bloqueadas),
        disabled=sorted(bloqueadas),
    )

    marcados = editado.loc[editado[COL_ELIMINAR] == True, pk].tolist()  # noqa: E712
    confirmado = True
    if marcados:
        accion = "desactivar" if _bandera_soft_delete(esq) else "eliminar definitivamente"
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


@_como_dialogo("Cambiar nombre de usuario")
def _dialogo_username(db_conn, actor_uid, target_uid):
    _editor_username(db_conn, actor_uid, target_uid)


def _abrir(contenedor, clave, fn, *args):
    """Con st.dialog abre un modal. Sin él, renderiza dentro de un expander persistente."""
    if _DIALOG is not None:
        fn(*args)
    else:
        st.session_state[f"fpedit_abierto_{clave}"] = True


def _render_fallback(contenedor, clave, titulo, fn, *args):
    if _DIALOG is None and st.session_state.get(f"fpedit_abierto_{clave}"):
        with contenedor.expander(titulo, expanded=True):
            fn(*args)


# ==========================================
# 9. PUNTO DE ENTRADA PÚBLICO
# ==========================================
def render_panel_edicion_fp(db_conn, user_id, active_client_id=None, contenedor=None, titulo=True):
    """Pinta los 3 botones de edición. Llamar UNA sola vez por página (las keys de widgets son fijas).

    db_conn          : el context manager db_conn() de app.py.
    user_id          : quien inició sesión (se usa para verificar contraseñas).
    active_client_id : perfil sobre el que se trabaja (el gestor puede estar viendo a un cliente).
    contenedor       : st.sidebar, una columna, etc. Por defecto st.sidebar.
    """
    contenedor = contenedor if contenedor is not None else st.sidebar
    uid = active_client_id or user_id
    if not uid:
        return

    flash = st.session_state.pop("fpedit_flash", None)
    if flash:
        try:
            st.toast(flash)
        except Exception:
            contenedor.success(flash)

    tabla_bolsas = _resolver_tabla(db_conn, TABLA_BOLSAS_CANDIDATAS)
    override = _secret("FP_TABLA_COMPROMISOS")
    candidatas_comp = ((str(override).strip(),) if override else ()) + TABLA_COMPROMISOS_CANDIDATAS
    tabla_comp = _resolver_tabla(db_conn, candidatas_comp)

    if titulo:
        contenedor.markdown(
            "<h3 style='color:#e5e7eb; font-family:\"Inter\", sans-serif; font-size:0.95rem; font-weight:600;"
            " margin:0.6rem 0 0.3rem 0;'>Editar mis finanzas</h3>",
            unsafe_allow_html=True,
        )

    if contenedor.button("Bolsas", use_container_width=True, key="fpedit_btn_bolsas",
                         disabled=tabla_bolsas is None,
                         help=None if tabla_bolsas else "Aún no existen bolsas en tu cuenta."):
        _abrir(contenedor, "bolsas", _dialogo_bolsas, db_conn, uid, tabla_bolsas)

    if contenedor.button("Próximos pagos", use_container_width=True, key="fpedit_btn_compromisos",
                         disabled=tabla_comp is None,
                         help=None if tabla_comp else "No encontré la tabla de compromisos (define FP_TABLA_COMPROMISOS)."):
        _abrir(contenedor, "compromisos", _dialogo_compromisos, db_conn, uid, tabla_comp)

    if contenedor.button("Nombre de usuario", use_container_width=True, key="fpedit_btn_username"):
        _abrir(contenedor, "username", _dialogo_username, db_conn, user_id, uid)

    # Solo aplica cuando no hay st.dialog disponible.
    _render_fallback(contenedor, "bolsas", "Editar bolsas", _editor_tabla, db_conn, "bolsas", "bolsas", tabla_bolsas, uid)
    _render_fallback(contenedor, "compromisos", "Editar próximos pagos", _editor_tabla, db_conn, "compromisos",
                     "próximos pagos", tabla_comp, uid)
    _render_fallback(contenedor, "username", "Cambiar nombre de usuario", _editor_username, db_conn, user_id, uid)
