"""
seguridad_auth.py — Adapter de credenciales (SHA-256 legado -> bcrypt).
Todo hash NUEVO es bcrypt con sal aleatoria (cost 12); si `bcrypt` no está instalado se lanza
error en lugar de degradar a SHA-256. Los hashes SHA-256 heredados solo se aceptan para iniciar
sesión y se reescriben a bcrypt en ese mismo login.
"""
import hashlib
import hmac
import re

try:
    import bcrypt as _bcrypt
except Exception:
    _bcrypt = None

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_BCRYPT_PREFIJOS = ("$2a$", "$2b$", "$2y$")
BCRYPT_ROUNDS = 12


def _sha256(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _bytes72(password: str) -> bytes:
    # bcrypt ignora lo que pase de 72 bytes; se trunca explícitamente para evitar excepciones.
    return password.encode("utf-8")[:72]


def bcrypt_disponible() -> bool:
    return _bcrypt is not None


def hash_password_seguro(password: str) -> str:
    """Único hashing permitido: bcrypt con sal. Nunca degrada a un hash débil."""
    if _bcrypt is None:
        raise RuntimeError("bcrypt no está instalado: agrega `bcrypt` a requirements.txt. "
                           "No se generan hashes débiles.")
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")
    return _bcrypt.hashpw(_bytes72(password), _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def es_bcrypt(h) -> bool:
    return isinstance(h, str) and h.startswith(_BCRYPT_PREFIJOS)


def verificar_password(password: str, stored_hash) -> tuple:
    """(autenticado, necesita_migracion). Detecta el algoritmo por el propio hash almacenado."""
    if not password or not stored_hash:
        return False, False
    stored = str(stored_hash).strip()

    if es_bcrypt(stored):
        if _bcrypt is None:
            return False, False          # nunca se valida un hash bcrypt a ciegas
        try:
            return bool(_bcrypt.checkpw(_bytes72(password), stored.encode("utf-8"))), False
        except Exception:
            return False, False

    if _SHA256_RE.match(stored):
        ok = hmac.compare_digest(_sha256(password), stored.lower())   # comparación en tiempo constante
        return ok, bool(ok and _bcrypt is not None)

    return False, False


def _migrar(db_conn, user_id, password, hash_anterior):
    """Reescritura silenciosa. El filtro por hash_anterior evita pisar un cambio concurrente."""
    if _bcrypt is None:
        return False
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE user_id=%s AND password_hash=%s",
                (hash_password_seguro(password), user_id, hash_anterior),
            )
        return True
    except Exception:
        return False                     # la migración jamás interrumpe el acceso


def autenticar(db_conn, username: str, password: str):
    """Login completo. Devuelve user_id o None. Migra SHA-256 -> bcrypt en silencio."""
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT user_id, password_hash FROM users WHERE username=%s", (username,))
            fila = cur.fetchone()
    except Exception:
        return None
    if not fila:
        return None
    ok, migrar = verificar_password(password, fila[1])
    if not ok:
        return None
    if migrar:
        _migrar(db_conn, fila[0], password, fila[1])
    return fila[0]


def verificar_usuario(db_conn, user_id: str, password: str) -> bool:
    """Confirma la clave actual de un usuario ya logueado (formulario de perfil). También migra."""
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,))
            fila = cur.fetchone()
    except Exception:
        return False
    if not fila:
        return False
    ok, migrar = verificar_password(password, fila[0])
    if ok and migrar:
        _migrar(db_conn, user_id, password, fila[0])
    return ok
