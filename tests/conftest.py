"""Fixtures compartidos para la suite E2E/SMOKE de SQLab.

Aísla QSettings en un directorio temporal y crea MainWindow en modo offscreen.
Vincula cada test a su spec en specs/ via pytest marks (ver AGENTS.md Metodología).
"""
from __future__ import annotations

import os
import sys

# Asegurar que los imports de la app son accesibles
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Forzar offscreen antes de que Qt arranque
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings


# ── Vinculación tests → specs ──────────────────────────────────────────────

# Módulo de test → spec ID (coincide con specs/<id>.md)
_SPEC_MAP: dict[str, str] = {
    "test_sqlite_engine": "sqlite-engine",
    "test_error_friendly": "error-friendly",
    "test_session_loader": "session-loader",
    "test_e2e_smoke": "ui-main-window",
    "test_cronometro": "cronometro-ejercicio",
    "test_icono": "icono-ejecutable",
    "test_fix_matriz": "fix-matriz-resultados",
    "test_carga_tablas": "carga-tablas-excel-csv",
    "test_ejemplos_empaquetados": "fix-ejemplos-empaquetados",
    "test_carga_archivos": "carga-tablas-archivos",
    "test_formato_sql": "formato-sql-real",
    "test_ui_nombres": "ui-nombres-estado",
    "test_visor_tablas": "visor-tablas-anchas",
    "test_rendimiento": "rendimiento-tablas-grandes",
    "test_fix_carga_robusta": "fix-carga-robusta",
    "test_multi_sentencia": "fix-multi-sentencia",
    "test_exportar_csv": "exportar-resultado-csv",
    "test_mostrar_null": "mostrar-null-en-grillas",
    "test_normalizar_nulos": "normalizar-nulos-csv-excel",
    "test_scrollbars": "scrollbars-visibles",
    "test_abrir_db": "abrir-db-existente",
    "test_autocompletar_enter": "autocompletar-con-enter",
    "test_consola_vacia": "consola-vacia-inicial",
    "test_exportar_excel": "exportar-excel",
    "test_autocompletar_parentesis": "autocompletar-parentesis",
    "test_compat_postgres": "compat-postgres",
    "test_copiar_especificacion": "copiar-especificacion",
    "test_historial_contraido": "historial-contraido",
    "test_auto_espaciado": "auto-espaciado-columnas",
    "test_exportar_db": "exportar-db",
    "test_comparar_consultas": "comparar-consultas",
    "test_graficos": "graficos-basicos",
    "test_pg_engine": "pg-engine",
    "test_error_friendly_pg": "error-friendly-pg",
    "test_carga_tipos_pg": "carga-tipos-pg",
    "test_fix_template_pg": "fix-template-pg-corrupto",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Agrega pytest.mark.spec('...') automáticamente a cada test según su módulo."""
    for item in items:
        module_name = item.module.__name__.rsplit(".", 1)[-1]
        spec_id = _SPEC_MAP.get(module_name)
        if spec_id:
            item.add_marker(pytest.mark.spec(spec_id))


# ── QSettings aislado (evita contaminar el registry/INI real) ──────────

@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Cada test obtiene un QSettings IniFormat apuntando a tmp_path."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    # Forzar organización/app nuevas para aislamiento
    s = QSettings("SQLTestOrg", "SQLTestSuite")
    s.clear()
    # MainWindow usa QSettings(org, app) implícito → formato NATIVO (registro
    # en Windows); setDefaultFormat no lo redirige. Aislarlo también con
    # snapshot + clear + restore para no leer/escribir el registro real.
    native = QSettings("SQLPractica", "SQLPractica")
    snapshot = {k: native.value(k) for k in native.allKeys()}
    native.clear()
    native.sync()
    yield s
    s.clear()
    native.clear()
    for k, v in snapshot.items():
        native.setValue(k, v)
    native.sync()


# ── MainWindow fixture ─────────────────────────────────────────────────

def _pg_bin() -> str | None:
    from core.pg_engine import PG_BIN_DIR
    import os
    if PG_BIN_DIR and os.path.isfile(os.path.join(PG_BIN_DIR, "initdb.exe")):
        return PG_BIN_DIR
    return None


@pytest.fixture(scope="session")
def _servidor_pg(tmp_path_factory):
    """Un servidor PG por sesión en template propio (o None → fallback SQLite).

    Template dedicado (no el de la app) para no pelear el lock postmaster
    con instancias reales abiertas.
    """
    from core.pg_engine import PGServer
    if _pg_bin() is None:
        yield None
        return
    base = str(tmp_path_factory.mktemp("pgtests"))
    srv = PGServer(base_dir=base)
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture
def app(qtbot, _servidor_pg, tmp_path):
    """MainWindow en offscreen con motor PG compartido (o SQLite sin binarios)."""
    from ui.main_window import MainWindow
    if _servidor_pg is None:
        from core.sqlite_engine import SQLEngine
        eng = SQLEngine()
    else:
        from core.pg_engine import PGEngine
        _servidor_pg.contador = getattr(_servidor_pg, "contador", 0) + 1
        eng = PGEngine(server=_servidor_pg, dbname=f"sqllab_t{_servidor_pg.contador}")
    w = MainWindow(engine=eng)
    qtbot.addWidget(w)
    w.show()
    yield w
    try:
        eng.close()
    except Exception:
        pass
