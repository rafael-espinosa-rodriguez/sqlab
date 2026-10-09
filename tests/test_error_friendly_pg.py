"""Spec error-friendly-pg — errores PostgreSQL en español (FE)."""
from __future__ import annotations

import os

import pytest

from core.error_friendly import friendly_pg_error
from core.pg_engine import PG_BIN_DIR

REQUIERE_PG = not (PG_BIN_DIR and os.path.isfile(os.path.join(PG_BIN_DIR, "initdb.exe")))
salta_sin_pg = pytest.mark.skipif(REQUIERE_PG, reason="sin binarios PG vendoreados")


def _tablas_demo():
    from core.sqlite_engine import Column, Table
    return [
        Table(name="clientes", columns=[Column("id", "INTEGER"), Column("nombre", "TEXT")],
              rows=[[1, "Ana"]]),
    ]


def test_fe01_tabla_inexistente():
    """FE-01: 42P01 → español con nombre."""
    msg = friendly_pg_error('relation "pedidos" does not exist', sqlstate="42P01")
    assert "pedidos" in msg and "No existe la tabla" in msg


def test_fe01_columna_inexistente():
    """FE-01: 42703 → español con nombre."""
    msg = friendly_pg_error('column "monto" does not exist', sqlstate="42703")
    assert "monto" in msg and "No existe la columna" in msg


def test_fe02_sintaxis_y_funcion():
    """FE-02: 42601 con token; 42883 con hint de tipos (idents en minúsculas)."""
    msg = friendly_pg_error('syntax error at or near "SEL"', sqlstate="42601")
    assert "sel" in msg.lower() and "sintaxis" in msg.lower()
    msg = friendly_pg_error(
        "function date_part(unknown, integer) does not exist", sqlstate="42883"
    )
    assert "date_part" in msg
    # Español real de servidor con locale ES:
    msg = friendly_pg_error("no existe la columna «monto» de la relación «t»")
    assert "No existe la columna" in msg and "monto" in msg
    msg = friendly_pg_error("error de sintaxis cerca de «SELEKT»")
    assert "sintaxis" in msg.lower() and "selekt" in msg.lower()


def test_fe03_fallback_y_generico():
    """FE-03: sin sqlstate por texto; desconocido → genérico recortado."""
    msg = friendly_pg_error('relation "x" does not exist')
    assert "No existe la tabla" in msg
    msg = friendly_pg_error("FATAL: lo que sea " + "z" * 500)
    assert len(msg) <= 300 and "z" in msg


@salta_sin_pg
def test_fe04_e2e_sqlstate_real(tmp_path):
    """FE-04: error real del servidor llega traducido (sqlstate de psycopg)."""
    from core.pg_engine import PGEngine
    eng = PGEngine(base_dir=str(tmp_path))
    try:
        r = eng.execute("SELECT * FROM noexiste_xyz")
        assert not r.ok
        assert "noexiste_xyz" in r.error and "No existe la tabla" in r.error
        r = eng.execute("SELEKT 1")
        assert not r.ok and "sintaxis" in r.error.lower()
        eng.load_tables(_tablas_demo()[:1])
        r = eng.execute("SELECT nosuchcol FROM clientes")
        assert not r.ok and "No existe la columna" in r.error
    finally:
        eng.close()


_EN_42803 = (
    'column "products.product_name" must appear in the GROUP BY clause '
    "or be used in an aggregate function"
)
_ES_42803 = (
    "la columna «products.product_name» debe aparecer en la cláusula GROUP BY "
    "o ser usada en una función de agregación"
)


def test_fe05a_42803_ingles():
    """FE-05: 42803 EN → español con columna + regla + hint de arreglo."""
    msg = friendly_pg_error(_EN_42803, sqlstate="42803")
    assert "product_name" in msg
    assert "GROUP BY" in msg
    assert "MAX()" in msg or "MAX(" in msg
    assert "No existe la función" not in msg


def test_fe05b_42803_espanol():
    """FE-05: variante ES real del servidor local (locale initdb) → mismo tono."""
    msg = friendly_pg_error(_ES_42803, sqlstate="42803")
    assert "product_name" in msg
    assert "GROUP BY" in msg
    assert "MAX(" in msg
    assert "No existe la función" not in msg


def test_fe05c_42803_sin_sqlstate_no_cae_en_funcion():
    """FE-05: solo texto (sin sqlstate) → el patrón dedicado va ANTES de función."""
    msg = friendly_pg_error(_ES_42803)
    assert "GROUP BY" in msg and "MAX(" in msg
    assert "No existe la función" not in msg
    msg = friendly_pg_error(_EN_42803)
    assert "GROUP BY" in msg and "MAX(" in msg
    assert "No existe la función" not in msg


def test_fe05d_42803_sqlstate_mensaje_inesperado():
    """FE-05: 42803 con texto no reconocible → genérico, nunca el de función."""
    msg = friendly_pg_error("grouping error inesperado zzz", sqlstate="42803")
    assert "No existe la función" not in msg
    assert "zzz" in msg


@salta_sin_pg
def test_fe05e_e2e_42803_real(tmp_path):
    """FE-05 e2e: consulta real con columna suelta en GROUP BY → error amigable."""
    from core.pg_engine import PGEngine
    from core.sqlite_engine import Column, Table
    eng = PGEngine(base_dir=str(tmp_path))
    try:
        eng.load_tables([Table(
            name="products",
            columns=[Column("product_id", "INTEGER"), Column("product_name", "TEXT"),
                     Column("category", "TEXT"), Column("price", "REAL")],
            rows=[[1, "Laptop", "Electronica", 1000.0], [2, "Mouse", "Electronica", 20.0],
                  [3, "Silla", "Muebles", 80.0]],
        )])
        r = eng.execute(
            "SELECT category, product_name, MAX(price) FROM products GROUP BY category"
        )
        assert not r.ok
        assert "product_name" in r.error
        assert "GROUP BY" in r.error
        assert "No existe la función" not in r.error
    finally:
        eng.close()


def test_fe06_sintaxis_es_en_o_cerca_de():
    """FE-06: variante ES real «en o cerca de» → misma plantilla que «cerca de»."""
    msg = friendly_pg_error(
        "error de sintaxis en o cerca de «FROM» LINE 1: SELECT(AVG(x) FROM t",
        sqlstate="42601",
    )
    assert "sintaxis" in msg.lower()
    assert "from" in msg.lower()
    assert "La base de datos respondió" not in msg
