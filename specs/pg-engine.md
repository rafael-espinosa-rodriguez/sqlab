# SPEC: pg-engine (F1)

## Meta
- **Feature**: pg-engine
- **Autor**: opencode (Muse Spark)
- **Fecha**: 2026-09-27
- **Estado**: `APPROVED`

## Objetivo
`core/pg_engine.py`: motor PostgreSQL embebido con paridad de API respecto a
`SQLEngine` (para el corte futuro): servidor efímero local, `execute()`
multi-sentencia, `load_tables()`, tipos PG, booleanos/`None` reales y
`exportar_db` vía `pg_dump`.

## Acceptance Criteria

### PE-01 — ciclo de vida
- **Given** binarios PG 17.11 vendoreados
- **When** `PGEngine()` + `close()`
- **Then** cluster template en `%LOCALAPPDATA%/SQLab/sqllab-pgdata-17`
  (fallback `%TEMP%`; ver Enmienda PE-E01), initdb solo la primera vez,
  servidor en puerto libre, BD de sesión `sqllab_<pid>` creada; al cerrar:
  DROP + stop + sin procesos residuales. Sin `pg_ctl` (se cuelga:
  `Popen(postgres)` + poll TCP + `terminate`).

### PE-02 — execute paridad
- **Given** sesión con tablas
- **When** `execute()` con 1 o N sentencias (`;` fuera de literales/comentarios)
- **Then** `QueryResult` con el último resultado con filas; error → `friendly_error` (F2 lo traduce a PG; F1 acepta texto crudo).

### PE-03 — dialecto nativo
- **Given** `date_part`, `::`, `USING`, `ILIKE`, booleanos, `RETURNING`
- **When** ejecutar
- **Then** funciona sin reescritura (todo nativo PG; la reescritura `::` de sqlite se retira en F4).

### PE-04 — load_tables paridad
- **Given** lista de `Table` (tipos SQLite-ish o PG)
- **When** cargar
- **Then** CREATE con tipos PG (`INTEGER REAL TEXT NUMERIC BOOLEAN DATE` pasan; resto → `TEXT`), `executemany` con `%s`, filas truncadas/rellenas, tablas inválidas omitidas (devuelve nombres).

### PE-05 — exportar_db
- **Given** sesión con datos
- **When** `exportar_db(path)`
- **Then** dump SQL restorable con `psql` (vía `pg_dump` del bundle).

## Edge Cases
- [x] Sin binarios (CI/otra máquina): tests se saltan (`skip`), no fallan.
- [x] Puerto ocupado: puerto aleatorio libre por socket-bind previo.
- [x] Crash del servidor: `close()` tolera proceso muerto; `poll()` antes de `terminate`.
- [x] `None`/bytes/bool/fechas ISO como texto: pasan como en sqlite.

## Límites Conocidos
- `initdb` ~9 s solo la primera vez (cluster template cacheado); arranques siguientes <1 s.
- UI/startup UX y corte SQLite→PG son F4/F6, no F1.
- `requirements.txt` suma `psycopg[binary]` (cliente puro, ruedas Windows).

## Archivos a tocar
- `core/pg_engine.py` (nuevo: `PGServer` + `PGEngine`)
- `requirements.txt` (`psycopg[binary]`)
- `tests/test_pg_engine.py` (nuevo: PE-01..PE-05, skip sin binarios)

## Tests requeridos
- **Unit/E2E**: ciclo de vida, execute simple+multi+error, dialecto, load paridad + omitidas, export roundtrip.
- **Nombre de archivos de test**: `tests/test_pg_engine.py`

## Notas de diseño
- `sqlite_engine.py` congelado (no se toca) hasta F6.
- Reuso interno: `_partir_sentencias` importado de `core.sqlite_engine` (misma semántica `;`).
- Efímero por decisión: template cacheado + BD de sesión `sqllab_<pid>` con DROP al cerrar.

## Enmienda PE-E01 (2026-10-07) — ubicación y autoreparación del template
- **Por qué**: el limpiador de Temp (Storage Sense) purgaba
  `%TEMP%/sqllab-pgdata-17` dejándolo sin `PG_VERSION` → arranque con
  "MOTOR NO DISPONIBLE".
- **Qué cambia**: la ruta por defecto pasa a `%LOCALAPPDATA%/SQLab/…`
  (fallback Temp) y `_asegurar_cluster()` repara templates corruptos y
  adopta servidores vivos.
- **Detalle y AC**: spec `specs/fix-template-pg-corrupto.md`
  (CR-01..CR-07 + Enmienda E-01); tests `tests/test_fix_template_pg.py`.
