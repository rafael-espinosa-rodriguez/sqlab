"""Spec fix-template-pg-corrupto — template PG autocurable + ruta estable.

Los limpiadores de `%TEMP%` (Storage Sense/CCliner) purgan archivos viejos y
dejan el cluster template a medias (sin `PG_VERSION`): la app debe repararlo
sola y, además, guardarlo fuera de Temp para que no vuelva a pasar.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from core import pg_engine
from core.pg_engine import PG_BIN_DIR

REQUIERE_PG = not (PG_BIN_DIR and os.path.isfile(os.path.join(PG_BIN_DIR, "initdb.exe")))
salta_sin_pg = pytest.mark.skipif(REQUIERE_PG, reason="sin binarios PG vendoreados")


# ── dobles de test (sin binarios: corren también en CI) ─────────────────────

class _SubprocessFalso:
    """Sustituye `pg_engine.subprocess`: simula initdb sin ejecutar nada."""

    def __init__(self, exito: bool = True, salida: str = "", escribir_version: bool = True):
        self.exito = exito
        self.salida = salida
        self.escribir_version = escribir_version
        self.llamadas: list[list[str]] = []

    def run(self, cmd, **kw):  # noqa: ANN001 (firma compatible con subprocess.run)
        self.llamadas.append(list(cmd))
        if self.exito and self.escribir_version:
            destino = cmd[cmd.index("-D") + 1]
            os.makedirs(destino, exist_ok=True)
            with open(os.path.join(destino, "PG_VERSION"), "wb") as fh:
                fh.write(b"17\n")
        class _R:
            returncode = 0 if self.exito else 1
            stdout = ""
            stderr = ""
        _R.stderr = self.salida
        return _R()


def _preparar_unidad(tmp_path, monkeypatch, fake):
    """Binarios ficticios + subprocess falso + sleeps sin espera."""
    monkeypatch.setattr(pg_engine, "PG_BIN_DIR", str(tmp_path / "bin-falso"))
    monkeypatch.setattr(pg_engine, "subprocess", fake)
    monkeypatch.setattr(pg_engine.time, "sleep", lambda _s: None)


# ── unit: reparación del template ────────────────────────────────────────────

def test_fx01_template_corrupto_se_vacia_y_reinitdb(tmp_path, monkeypatch):
    """FX-01 (CR-01): restos sin PG_VERSION → se vacía y vuelve a correr initdb."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "resto.txt").write_text("viejo", encoding="utf-8")
    (base / "restos_junk").mkdir()
    (base / "postmaster.pid").write_text("18308\n", encoding="ascii")  # rancio
    fake = _SubprocessFalso()
    _preparar_unidad(tmp_path, monkeypatch, fake)

    srv = pg_engine.PGServer(base_dir=str(tmp_path))

    assert len(fake.llamadas) == 1
    assert fake.llamadas[0][fake.llamadas[0].index("-D") + 1] == srv.base
    assert os.path.isfile(os.path.join(srv.base, "PG_VERSION"))
    assert not (base / "resto.txt").exists()
    assert not (base / "restos_junk").exists()
    assert not (base / "postmaster.pid").exists()


def test_fx02_template_sano_no_se_toca(tmp_path, monkeypatch):
    """FX-02 (CR-02): con PG_VERSION no hay initdb ni borrados."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "PG_VERSION").write_bytes(b"17\n")
    (base / "marcador.txt").write_text("intacto", encoding="utf-8")
    fake = _SubprocessFalso()
    _preparar_unidad(tmp_path, monkeypatch, fake)

    pg_engine.PGServer(base_dir=str(tmp_path))

    assert fake.llamadas == []
    assert (base / "marcador.txt").read_text(encoding="utf-8") == "intacto"


def test_fx03_carrera_initdb_adopta_al_par(tmp_path, monkeypatch):
    """FX-03 (CR-04): initdb pierde la carrera → se adopta el cluster ganador."""
    fake = _SubprocessFalso(
        exito=False,
        salida='initdb: error: directory "x" exists but is not empty\n',
    )
    _preparar_unidad(tmp_path, monkeypatch, fake)
    estado = {"n": 0}

    def _adopta(self):
        estado["n"] += 1
        if estado["n"] == 1:  # antes de initdb: nadie sirviendo todavía
            return False
        self.puerto = 5555
        return True

    monkeypatch.setattr(pg_engine.PGServer, "_adoptar_ajeno", _adopta)
    srv = pg_engine.PGServer(base_dir=str(tmp_path))

    assert len(fake.llamadas) == 1
    assert srv.puerto == 5555


def test_fx04_directorio_bloqueado_error_en_espanol(tmp_path, monkeypatch):
    """FX-04 (CR-06): si no se puede vaciar, error con la ruta y qué borrar."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "resto.txt").write_text("bloqueado", encoding="utf-8")
    fake = _SubprocessFalso()
    _preparar_unidad(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(pg_engine.shutil, "rmtree", lambda *_a, **_k: None)

    with pytest.raises(RuntimeError) as exc:
        pg_engine.PGServer(base_dir=str(tmp_path))

    texto = str(exc.value)
    assert str(base) in texto
    assert "borra" in texto.lower()
    assert fake.llamadas == []  # no intenta initdb sobre un dir sucio


# ── unit: ubicación estable del template ─────────────────────────────────────

def test_fx05_ruta_por_defecto_fuera_de_temp(monkeypatch, tmp_path):
    """FX-05 (CR-05): por defecto %LOCALAPPDATA%\\SQLab; sin LOCALAPPDATA → Temp."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert pg_engine._dir_base_default() == os.path.join(
        str(tmp_path / "AppData" / "Local"), "SQLab")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert pg_engine._dir_base_default() == tempfile.gettempdir()


def test_fx06_base_explícita_y_preferencia_localappdata(tmp_path, monkeypatch):
    """FX-06 (CR-05): base_dir manda; sin él se prefiere LocalAppData."""
    appdata = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))

    explicita = pg_engine._resolver_base(str(tmp_path / "mibase"))
    assert explicita == str(tmp_path / "mibase" / "sqllab-pgdata-17")

    preferida = pg_engine._resolver_base(None)
    assert preferida == str(appdata / "SQLab" / "sqllab-pgdata-17")
    assert os.path.isdir(preferida)


def test_fx07_fallback_temp_si_localappdata_no_crecible(tmp_path, monkeypatch):
    """FX-07 (CR-05): LocalAppData inaccesible → se cae a %TEMP% (comportamiento viejo)."""
    archivo = tmp_path / "bloqueado"
    archivo.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(archivo))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    base = pg_engine._resolver_base(None)

    assert base == str(tmp_path / "sqllab-pgdata-17")
    assert os.path.isdir(base)


def test_fx08_sin_carpeta_disponible_error(tmp_path, monkeypatch):
    """FX-08 (CR-06): ni LocalAppData ni Temp creables → error claro."""
    archivo = tmp_path / "bloqueado"
    archivo.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(archivo))
    monkeypatch.setattr(tempfile, "tempdir", str(archivo))

    with pytest.raises(RuntimeError) as exc:
        pg_engine._resolver_base(None)

    assert "carpeta" in str(exc.value).lower()


def test_fx09_caliente_con_pgversion_purgado_adopta(tmp_path, monkeypatch):
    """FX-09 (CR-03/E-01): servidor vivo sin PG_VERSION → se restaura la marca y se adopta."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "marcador.txt").write_text("intacto", encoding="utf-8")
    (base / "postmaster.pid").write_text("1\n2\n3\n5555\n", encoding="ascii")
    fake = _SubprocessFalso()
    _preparar_unidad(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(
        pg_engine.PGServer, "_puerto_vivo", staticmethod(lambda _puerto: True))

    def _adopta(self):  # el PG real rechaza conexiones sin PG_VERSION (E-01)
        if os.path.isfile(os.path.join(self.base, "PG_VERSION")):
            self.puerto = 5555
            return True
        return False

    monkeypatch.setattr(pg_engine.PGServer, "_adoptar_ajeno", _adopta)
    srv = pg_engine.PGServer(base_dir=str(tmp_path))

    assert fake.llamadas == []  # ni initdb ni vaciado
    assert (base / "marcador.txt").read_text(encoding="utf-8") == "intacto"
    assert (base / "PG_VERSION").read_bytes() == b"17\n"
    assert srv.puerto == 5555


def test_fx12_servidor_vivo_ilegible_error_sin_borrar(tmp_path, monkeypatch):
    """FX-12 (CR-03/E-01): servidor escuchando pero ilegible → error y cero borrado."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "resto.txt").write_text("no me borres", encoding="utf-8")
    (base / "postmaster.pid").write_text("1\n2\n3\n5555\n", encoding="ascii")
    fake = _SubprocessFalso()
    _preparar_unidad(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(
        pg_engine.PGServer, "_puerto_vivo", staticmethod(lambda _puerto: True))
    monkeypatch.setattr(pg_engine.PGServer, "_adoptar_ajeno", lambda self: False)

    with pytest.raises(RuntimeError) as exc:
        pg_engine.PGServer(base_dir=str(tmp_path))

    texto = str(exc.value)
    assert str(base) in texto
    assert "servidor" in texto.lower()
    assert (base / "resto.txt").exists()  # nunca vaciar con servidor vivo
    assert not (base / "PG_VERSION").exists()  # marca deshecha (no enmascarar)
    assert fake.llamadas == []


# ── integración (initdb real; skip sin binarios) ─────────────────────────────

@salta_sin_pg
def test_fx10_initdb_real_repara_basura(tmp_path):
    """FX-10 (CR-01): initdb real sobre un template con restos lo repara."""
    base = tmp_path / "sqllab-pgdata-17"
    base.mkdir()
    (base / "basura.txt").write_text("purgado a medias", encoding="utf-8")
    (base / "restos_junk").mkdir()

    srv = pg_engine.PGServer(base_dir=str(tmp_path))
    try:
        assert os.path.isfile(str(base / "PG_VERSION"))
        assert not (base / "basura.txt").exists()
        assert not (base / "restos_junk").exists()
        srv.start()
        assert srv.vivo and srv.puerto
        with srv._psycopg.connect(srv.dsn(), autocommit=True) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        srv.stop()


@salta_sin_pg
def test_fx11_no_borra_servidor_vivo_sin_pgversion(tmp_path):
    """FX-11 (CR-03): servidor vivo con PG_VERSION borrado → adopción, cero borrado."""
    srv1 = pg_engine.PGServer(base_dir=str(tmp_path))
    srv1.start()
    try:
        os.remove(os.path.join(srv1.base, "PG_VERSION"))  # purga en caliente
        marcador = os.path.join(srv1.base, "marcador.txt")
        with open(marcador, "w", encoding="utf-8") as fh:
            fh.write("no me borres\n")

        srv2 = pg_engine.PGServer(base_dir=str(tmp_path))
        srv2.start()
        assert srv2.adoptado and srv2.puerto == srv1.puerto
        assert os.path.isfile(marcador)  # nada se vació
        assert os.path.isfile(os.path.join(srv1.base, "PG_VERSION"))  # marca restaurada (E-01)
        assert srv1.vivo
        with srv2._psycopg.connect(srv2.dsn(), autocommit=True) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
        srv2.stop()
        assert srv1.vivo  # adoptado: stop() no mata al servidor ajeno
    finally:
        srv1.stop()
