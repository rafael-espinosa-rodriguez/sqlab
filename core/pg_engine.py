"""Motor PostgreSQL embebido (spec pg-engine, F1 migración).

Servidor local efímero: cluster template cacheado (initdb una sola vez),
`postgres.exe` directo vía Popen + poll TCP (pg_ctl se cuelga: ver spec
postgres-embebido-spike), BD de sesión `sqllab_<pid>` con DROP al cerrar.

Paridad de API con `SQLEngine`: `execute()` multi-sentencia, `load_tables()`
que devuelve omitidas, `table_names()`/`column_names()`, `exportar_db`.

Autoreparación del template (spec fix-template-pg-corrupto): si un limpiador
de `%TEMP%` deja el cluster a medias (sin `PG_VERSION`) se vacía y vuelve a
inicializar; el template vive fuera de Temp (`%LOCALAPPDATA%\\SQLab`) para que
no vuelva a ser purgado.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

from core.error_friendly import friendly_pg_error
from core.sqlite_engine import QueryResult, Table, _partir_sentencias

PG_VERSION = "17"
_TEMPLATE_DIR = f"sqllab-pgdata-{PG_VERSION}"

_TIPOS_PG = {
    "INTEGER", "BIGINT", "SMALLINT", "REAL", "DOUBLE PRECISION",
    "TEXT", "NUMERIC", "DECIMAL", "BOOLEAN", "DATE", "TIMESTAMP",
    "TIME", "BYTEA", "VARCHAR", "CHAR",
}


def _pg_bin_dir() -> str | None:
    """Carpeta con initdb/postgres: vendor en dev, _MEIPASS en exe frozen."""
    dev = r"D:\pg-bin\vendor\pgsql\bin"
    if os.path.isfile(os.path.join(dev, "initdb.exe")):
        return dev
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen = os.path.join(meipass, "pgsql", "bin")
        if os.path.isfile(os.path.join(frozen, "initdb.exe")):
            return frozen
    return None


PG_BIN_DIR = _pg_bin_dir()


def _dir_base_default() -> str:
    """Carpeta estable para el template, fuera de `%TEMP%` (spec
    fix-template-pg-corrupto): los limpiadores de Temp (Storage Sense y
    similares) purgan archivos antiguos y dejan el cluster a medias.

    Prefiere `%LOCALAPPDATA%\\SQLab`; sin `LOCALAPPDATA` (o no definida)
    cae en `%TEMP%`, como antes.
    """
    appdata = (os.environ.get("LOCALAPPDATA") or "").strip()
    if not appdata:
        return tempfile.gettempdir()
    return os.path.join(appdata, "SQLab")


def _resolver_base(base_dir: str | None) -> str:
    """Directorio del template: siempre creado como carpeta propia.

    Con `base_dir` explícito se usa tal cual (tests/arranque compartido);
    sin él se prefiere `%LOCALAPPDATA%\\SQLab` y, si no es creable, se cae a
    `%TEMP%`. Si ni una ni otra se pueden crear, error claro (CR-06).
    """
    if base_dir:
        candidatos = [os.path.join(base_dir, _TEMPLATE_DIR)]
    else:
        candidatos = [
            os.path.join(_dir_base_default(), _TEMPLATE_DIR),
            os.path.join(tempfile.gettempdir(), _TEMPLATE_DIR),
        ]
    vistos: set[str] = set()
    ultimo_error: OSError | None = None
    for ruta in candidatos:
        if ruta in vistos:
            continue
        vistos.add(ruta)
        try:
            os.makedirs(ruta, exist_ok=True)
            return ruta
        except OSError as exc:
            ultimo_error = exc
    raise RuntimeError(
        f"No se pudo crear la carpeta del motor: {ultimo_error}. "
        "Revisa los permisos de tu usuario y vuelve a intentarlo.")


def _tipo_pg(tipo: str) -> str:
    """Mapea tipo declarado a tipo PG válido (resto → TEXT).

    Acepta sufijos del formato de ejercicios (`INTEGER PRIMARY KEY`) y
    parámetros (`VARCHAR(255)`): si la palabra base es conocida se conserva
    la declaración original (PG la parsea).
    """
    u = (tipo or "").strip().upper()
    if not u:
        return "TEXT"
    if u.startswith("DOUBLE PRECISION"):
        return "DOUBLE PRECISION"
    base = re.split(r"[\s(]", u, maxsplit=1)[0]
    if base in _TIPOS_PG or base in ("VARCHAR", "CHAR", "CHARACTER"):
        return u
    return "TEXT"


def _valor_pg(value: Any) -> Any:
    """Normaliza un valor para psycopg: escalares tal cual (None intacto)."""
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    return str(value)


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PGServer:
    """Cluster template + proceso postgres compartible entre sesiones (F4).

    El template se inicializa una sola vez (initdb ~9 s); `start()`/`stop()`
    son idempotentes. Sin `pg_ctl` (se cuelga): `Popen(postgres)` + poll TCP.
    """

    def __init__(self, base_dir: str | None = None, usuario: str = "postgres") -> None:
        import psycopg  # dependencia declarada (requirements.txt)

        if PG_BIN_DIR is None:
            raise RuntimeError("Sin binarios PostgreSQL vendoreados.")
        self._psycopg = psycopg
        # El template vive en subdir propio (initdb exige directorio vacío)
        # y fuera de %TEMP% para sobrevivir a los limpiadores de Temp.
        self.base = _resolver_base(base_dir)
        self.usuario = usuario
        self._proc: subprocess.Popen | None = None
        self.puerto: int | None = None
        self._env = dict(os.environ)
        self._env["LC_ALL"] = "C"
        self._env["LANG"] = "C"
        self._asegurar_cluster()

    @property
    def vivo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def adoptado(self) -> bool:
        """True si usa un servidor ajeno vivo (segunda app / otro proceso)."""
        return self._proc is None and self.puerto is not None

    def _exe(self, nombre: str) -> str:
        assert PG_BIN_DIR is not None
        return os.path.join(PG_BIN_DIR, nombre)

    def _asegurar_cluster(self) -> None:
        """initdb solo si el template no existe (9 s la primera vez).

        Si `PG_VERSION` desapareció (limpiador de Temp dejó el cluster a
        medias) se vacía y se vuelve a inicializar; si otro proceso sirve ya
        este data-dir, se adopta sin tocar nada (spec fix-template-pg-corrupto).
        """
        if os.path.isfile(os.path.join(self.base, "PG_VERSION")):
            return
        estado = self._recuperar_servidor()
        if estado == "adoptado":
            return
        if estado == "servidor_vivo":
            # Regla de seguridad: jamás vaciar un data-dir con un servidor vivo.
            raise RuntimeError(
                f"Hay un servidor PostgreSQL activo sobre esta carpeta y no "
                f"responde: {self.base}. Cierra todas las ventanas de SQLab, "
                "borra esa carpeta y vuelve a abrir la app.")
        if os.path.isdir(self.base) and os.listdir(self.base):
            self._vaciar_template()
        os.makedirs(self.base, exist_ok=True)
        r = subprocess.run(
            [self._exe("initdb.exe"), "-D", self.base, "-E", "UTF8",
             "-U", self.usuario, "--auth=trust"],
            capture_output=True, text=True, env=self._env,
            cwd=PG_BIN_DIR, timeout=300,
        )
        if r.returncode != 0:
            # Otra instancia ganó la carrera de primer arranque doble: si
            # acaba de llenar el directorio, su servidor terminará de subir.
            if self._adoptar_tras_carrera(r.stdout + r.stderr):
                return
            raise RuntimeError(f"initdb falló:\n{(r.stdout + r.stderr)[-1500:]}")

    def _recuperar_servidor(self) -> str:
        """Decide entre adoptar, esperar o reparar cuando falta `PG_VERSION`.

        Devuelve `"adoptado"` (otro proceso ya sirve este data-dir),
        `"servidor_vivo"` (hay servidor escuchando pero no responde: no se
        puede tocar el directorio) o `"nada"` (pid rancio/ausente → reparar).

        Si el limpiador borró `PG_VERSION` **en caliente**, el postmaster sigue
        vivo pero rechaza las conexiones: se restaura ese marcador (era el
        archivo purgado, `17\\n`) para poder adoptarlo. Si aun así no responde,
        la marca se deshace para no enmascarar la corrupción (E-01, CR-03).
        """
        if self._adoptar_ajeno():
            return "adoptado"
        puerto = self._puerto_pid()
        if puerto is None:
            return "nada"
        for intento in range(10):  # ~5 s: cubre arranques/adopciones lentas
            if intento:
                time.sleep(0.5)
            if not self._puerto_vivo(puerto):
                continue
            self._restaurar_pg_version()
            if self._adoptar_ajeno():
                return "adoptado"
            self._deshacer_pg_version()
            return "servidor_vivo"
        return "nada"

    @staticmethod
    def _puerto_vivo(puerto: int) -> bool:
        """¿Escucha algo en el puerto del data-dir? (sondeo TCP, sin SQL)."""
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=1):
                return True
        except OSError:
            return False

    def _puerto_pid(self) -> int | None:
        """Puerto declarado en el postmaster.pid del data-dir (None si no hay).

        postmaster.pid va en el encoding del SO (p. ej. cp1252): se leen bytes
        y se tolera lo no ASCII (el puerto es ASCII).
        """
        try:
            with open(os.path.join(self.base, "postmaster.pid"), "rb") as fh:
                lineas = fh.read().decode("ascii", errors="ignore").splitlines()
            return int(lineas[3].strip())
        except Exception:
            return None

    def _restaurar_pg_version(self) -> None:
        """Reescribe la marca de versión que borró el limpiador (bytes originales)."""
        with open(os.path.join(self.base, "PG_VERSION"), "wb") as fh:
            fh.write(f"{PG_VERSION}\n".encode("ascii"))

    def _deshacer_pg_version(self) -> None:
        """Quita la marca recién escrita si sigue igual: no enmascarar (E-01)."""
        ruta = os.path.join(self.base, "PG_VERSION")
        try:
            with open(ruta, "rb") as fh:
                contenido = fh.read()
        except OSError:
            return
        if contenido == f"{PG_VERSION}\n".encode("ascii"):
            try:
                os.remove(ruta)
            except OSError:
                pass

    def _vaciar_template(self) -> None:
        """Borra un template parcial/corrupto: initdb exige directorio vacío (CR-01).

        Tres intentos con pausa por si un proceso suelto lo tiene bloqueado
        (Windows no permite borrar ficheros en uso); si persiste, error
        accionable para el usuario (CR-06).
        """
        for _ in range(3):
            shutil.rmtree(self.base, ignore_errors=True)
            if not os.path.isdir(self.base) or not os.listdir(self.base):
                return
            time.sleep(0.5)
        raise RuntimeError(
            f"No se pudo reparar el motor: la carpeta {self.base} está "
            "bloqueada. Cierra SQLab, borra esa carpeta a mano y vuelve a "
            "abrir la app.")

    def _adoptar_tras_carrera(self, salida: str) -> bool:
        """Tras un initdb fallido por 'no vacío', adopta al par que ganó (CR-04).

        Solo cuando el mensaje indica directorio no vacío (EN/ES): initdb del
        gemelo puede estar en marcha (~9 s) y su servidor arranca después, así
        que se sondea ~20 s antes de rendirse.
        """
        bajo = salida.lower()
        if "not empty" not in bajo and "no está vacío" not in bajo and "no esta vacio" not in bajo:
            return False
        if self._adoptar_ajeno():
            return True
        for _ in range(40):
            time.sleep(0.5)
            if self._adoptar_ajeno():
                return True
        return False

    def _adoptar_ajeno(self) -> bool:
        """Si otro proceso ya sirve este data-dir, adoptarlo (puerto de postmaster.pid).

        Permite N apps/tests sobre el mismo template sin lock de postmaster.
        Un postmaster.pid rancio (crash) no conecta → se arranca propio.
        """
        puerto = self._puerto_pid()
        if puerto is None:
            return False
        try:
            conn = self._psycopg.connect(
                f"host=127.0.0.1 port={puerto} user={self.usuario} dbname=postgres",
                autocommit=True, connect_timeout=2,
            )
            conn.close()
        except Exception:
            return False
        self.puerto = puerto
        return True

    def dsn(self, db: str = "postgres") -> str:
        return f"host=127.0.0.1 port={self.puerto} user={self.usuario} dbname={db}"
        return f"host=127.0.0.1 port={self.puerto} user={self.usuario} dbname={db}"

    def start(self) -> None:
        """Arranca el servidor (idempotente) o adopta uno ajeno vivo."""
        if self.vivo:
            return
        if self._adoptar_ajeno():
            return
        self.puerto = _puerto_libre()
        self._proc = subprocess.Popen(
            [self._exe("postgres.exe"), "-D", self.base, "-p", str(self.puerto),
             "-c", "listen_addresses=127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=self._env, cwd=PG_BIN_DIR,
        )
        t0 = time.time()
        ultimo_error: Exception | None = None
        while time.time() - t0 < 60:
            assert self._proc is not None
            if self._proc.poll() is not None:
                raise RuntimeError("postgres terminó durante el arranque.")
            try:
                conn = self._psycopg.connect(self.dsn(), autocommit=True, connect_timeout=2)
                conn.close()
                return
            except Exception as exc:
                ultimo_error = exc
                time.sleep(0.5)
        raise RuntimeError(f"postgres no aceptó conexiones: {ultimo_error}")

    def stop(self) -> None:
        """Detiene el servidor (tolerante)."""
        try:
            if self.vivo:
                assert self._proc is not None
                self._proc.terminate()
                self._proc.wait(timeout=30)
        except Exception:
            pass
        self._proc = None

    def crear_bd(self, nombre: str) -> None:
        conn = self._psycopg.connect(self.dsn(), autocommit=True)
        try:
            conn.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
            conn.execute(f'CREATE DATABASE "{nombre}"')
        finally:
            conn.close()

    def borrar_bd(self, nombre: str) -> None:
        if not self.vivo:
            return
        try:
            conn = self._psycopg.connect(self.dsn(), autocommit=True, connect_timeout=5)
        except Exception:
            return
        try:
            conn.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


class PGEngine:
    """Sesión PostgreSQL embebida con la API de SQLEngine."""

    dialect = "POSTGRESQL"
    etiqueta_db = "PG LOCAL"

    def __init__(self, base_dir: str | None = None, server: PGServer | None = None,
                 dbname: str | None = None, usuario: str = "postgres") -> None:
        import psycopg  # dependencia declarada (requirements.txt)

        self.server = server if server is not None else PGServer(base_dir, usuario)
        self.server.start()
        # Propio solo si este engine levantó el proceso (no adoptado ni inyectado).
        self._propio = server is None and not self.server.adoptado
        self.dbname = dbname or f"sqllab_{os.getpid()}"
        self.tables: dict[str, Table] = {}
        self._conn = None
        self.server.crear_bd(self.dbname)
        self._conn = psycopg.connect(self.server.dsn(self.dbname), autocommit=True)

    # ---------------------------------------------------------- ciclo de vida

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def dsn(self, db: str | None = None) -> str:
        return self.server.dsn(db or self.dbname)

    def close(self) -> None:
        """DROP de la BD de sesión; detiene el servidor solo si es propio."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self.tables = {}
        try:
            self.server.borrar_bd(self.dbname)
        except Exception:
            pass
        if self._propio:
            self.server.stop()

    # ------------------------------------------------------------------ datos

    def _limpiar_bd(self) -> None:
        assert self._conn is not None
        for name in list(self.tables):
            try:
                self._conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            except Exception:
                pass
        self.tables = {}

    def load_tables(self, tables: list[Table]) -> list[str]:
        """Sustituye las tablas de la sesión (paridad con SQLEngine)."""
        assert self._conn is not None
        self._limpiar_bd()
        omitidas: list[str] = []
        if not tables:
            return omitidas
        for t in tables:
            if not t.columns:
                omitidas.append(t.name)
                continue
            cols = ", ".join(f'"{c.name}" {_tipo_pg(c.type)}' for c in t.columns)
            try:
                self._conn.execute(f'CREATE TABLE "{t.name}" ({cols})')
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                omitidas.append(t.name)
                continue
            ncols = len(t.columns)
            vals = ", ".join(["%s"] * ncols)
            lote = []
            for row in t.rows:
                reg = [None] * ncols
                for i, v in enumerate(row[:ncols]):
                    reg[i] = _valor_pg(v)
                lote.append(tuple(reg))
            try:
                cur = self._conn.cursor()
                try:
                    cur.executemany(f'INSERT INTO "{t.name}" VALUES ({vals})', lote)
                finally:
                    cur.close()
            except Exception:
                for reg in lote:  # fallback fila por fila (paridad RG-06)
                    try:
                        self._conn.execute(f'INSERT INTO "{t.name}" VALUES ({vals})', reg)
                    except Exception:
                        continue
            self.tables[t.name] = t
        return omitidas

    def execute(self, query: str) -> QueryResult:
        """Ejecuta una o varias sentencias; devuelve el último resultado con filas."""
        if self._conn is None:
            return QueryResult(ok=False, error="Todavía no hay tablas cargadas. Carga un archivo de ejercicio primero.")
        query = query.strip().strip(";")
        if not query:
            return QueryResult(ok=True, message="Escribe una consulta y pulsa Ejecutar.")
        sentencias = _partir_sentencias(query)
        ultimo: QueryResult | None = None
        for s in sentencias:
            ultimo = self._ejecutar_una(s)
            if ultimo.error:
                return ultimo
        assert ultimo is not None
        if len(sentencias) > 1 and not ultimo.columns:
            ultimo.message = f"{len(sentencias)} sentencias ejecutadas correctamente."
        return ultimo

    def _ejecutar_una(self, query: str) -> QueryResult:
        assert self._conn is not None
        try:
            cur = self._conn.execute(query)
            try:
                rows = [list(r) for r in cur.fetchall()]
            except Exception:
                rows = []
            columns = [d[0] for d in (cur.description or [])]
            n = len(rows)
            return QueryResult(ok=True, columns=columns, rows=rows, row_count=n,
                               message=f"Consulta ejecutada correctamente. {n} fila(s)")
        except Exception as exc:
            try:
                self._conn.rollback()
            except Exception:
                pass
            return QueryResult(ok=False, error=friendly_pg_error(
                str(exc), self.tables.keys(), query, sqlstate=getattr(exc, "sqlstate", None)))

    def exportar_db(self, path: str) -> None:
        """Vuelca la BD de sesión a SQL restorable (vía pg_dump del bundle)."""
        if self._conn is None:
            raise ValueError("No hay tablas cargadas.")
        r = subprocess.run(
            [self.server._exe("pg_dump.exe"), "-h", "127.0.0.1", "-p", str(self.server.puerto),
             "-U", self.server.usuario, "-d", self.dbname, "-f", path],
            capture_output=True, text=True, env=self.server._env, timeout=300,
        )
        if r.returncode != 0:
            raise OSError(f"pg_dump falló:\n{(r.stdout + r.stderr)[-1000:]}")

    def table_names(self) -> list[str]:
        return list(self.tables.keys())

    def column_names(self, table: str) -> list[str]:
        t = self.tables.get(table)
        return [c.name for c in t.columns] if t else []


__all__ = [
    "PGEngine", "PGServer", "PG_BIN_DIR", "PG_VERSION", "_tipo_pg",
    "_dir_base_default", "_resolver_base",
]
