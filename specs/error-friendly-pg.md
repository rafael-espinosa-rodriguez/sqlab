# SPEC: error-friendly-pg (F2)

## Meta
- **Feature**: error-friendly-pg
- **Autor**: opencode (Muse Spark)
- **Fecha**: 2026-09-27 (enmienda 2026-10-07, v36)
- **Estado**: `APPROVED`

## Objetivo
`friendly_pg_error()` traduce errores PostgreSQL a español principiante
(igual tono que `friendly_error` de SQLite): por SQLSTATE cuando viene del
servidor real, con fallback a regex del mensaje (testeable sin servidor).
Los hints de dialecto SQLite (`::`→CAST, `date_part`→STRFTIME) NO aplican
en PG y no deben dispararse.

## Acceptance Criteria

### FE-01 — tabla/columna inexistente
- **Given** `42P01 relation "x" does not exist` / `42703 column "y" does not exist`
- **When** traducir
- **Then** `No existe la tabla «x». ...` / `No existe la columna «y». ...` en español.

### FE-02 — sintaxis y función
- **Given** `42601 syntax error at or near "SEL"` / `42883 function date_part(unknown, integer) does not exist`
- **When** traducir
- **Then** mensaje de sintaxis con el token + sugerencia SQLite→PG invertida cuando aplique (p. ej. nada que sugerir: `date_part` existe; el problema son los tipos → hint de tipos).

### FE-03 — sin SQLSTATE (fallback texto)
- **Given** solo texto de error PG (sin conexión)
- **When** traducir
- **Then** mismos mensajes vía regex; desconocido → genérico con texto recortado.

### FE-04 — cableado
- **Given** `PGEngine._ejecutar_una` con error real
- **When** falla
- **Then** usa `friendly_pg_error` con `sqlstate` de la excepción (los tests e2e lo verifican contra servidor; unitarios sin servidor).

## Enmienda v36 (2026-10-07) — 42803 GROUP BY + sintaxis ES ampliada

Hallazgo de campo: ejercicios escritos pensando en SQLite (columnas "suelas"
junto a `MAX()/MIN()` en un `GROUP BY`) son válidos en SQLite pero PostgreSQL
los rechaza con **42803**. El servidor local (initdb con locale ES) responde:
`la columna «products.product_name» debe aparecer en la cláusula GROUP BY o
ser usada en una función de agregación`. Sin patrón dedicado, el bucle
completo matcheaba antes `funci[óo]n (...)\(` y producía un mensaje
**incorrecto** ("No existe la función «de agregación…»"). Se añade par
dedicado ANTES de los patrones de función y se registra en `_SQLSTATE_PG`.

Además, la variante ES real de 42601 es `error de sintaxis en o cerca de
«FROM»` (con "en o "), que el patrón previo (`cerca de|cercano a`) no
cubría → fallback crudo. Se amplía el alternador.

### FE-05 — 42803 columna fuera de GROUP BY
- **Given** sqlstate `42803` con mensaje EN (`column "x" must appear in the GROUP BY clause…`) o ES (`la columna «x» debe aparecer en la cláusula GROUP BY…`)
- **When** traducir
- **Then** mensaje en español con el nombre de la columna, la regla
  (GROUP BY o función de agregación) y el hint de arreglo (agregarla al
  GROUP BY o envolverla en MAX/MIN/AVG/SUM/COUNT). Nunca el mensaje
  incorrecto de "función inexistente".
- **And** sin `sqlstate` (solo texto), el bucle de patrones llega al
  dedicado ANTES de los de función → mismo resultado.

### FE-06 — sintaxis ES "en o cerca de"
- **Given** `42601` con variante ES real del servidor local: `error de sintaxis en o cerca de «FROM»`
- **When** traducir
- **Then** `Error de sintaxis cerca de «from»…` (misma plantilla que la
  variante previa `cerca de`); sin caer al fallback crudo.

## Edge Cases
- [x] `friendly_error` de SQLite intacto (14 tests existentes).
- [x] Excepción sin `sqlstate` (corte de conexión `08006`, etc.): genérico + texto.
- [x] Nombres entrecomillados con espacios: regex tolerante.

## Límites Conocidos
- Cubre los SQLSTATE comunes (42P01, 42703, 42701, 42601, 42883, 42803, 22P02, 23505, 23503, 23502, 22012); el resto va al genérico.
- 42803 se traduce pero NO se reescribe la consulta (sin modo compatibilidad SQLite: decisión explícita, enseña el SQL estándar).
- UI (F4) mostrará estos mensajes sin cambios de widgets.

## Archivos a tocar
- `core/error_friendly.py` (`friendly_pg_error` + `_PATRONES_PG` + `_SQLSTATE_PG`)
- `core/pg_engine.py` (usar `friendly_pg_error` con sqlstate)
- `tests/test_error_friendly_pg.py` (FE-01..FE-06)

## Tests requeridos
- **Unit**: strings PG reales → español (sin servidor).
- **E2E**: errores reales contra servidor (skip sin binarios).
- **Nombre de archivos de test**: `tests/test_error_friendly_pg.py`

## Notas de diseño
- Firma: `friendly_pg_error(raw, table_names=(), query="", sqlstate=None)`.
- `psycopg` expone `exc.sqlstate`; el engine lo pasa explícito (testeable).
