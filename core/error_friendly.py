"""Traduce errores de SQLite a mensajes entendibles para un principiante."""
from __future__ import annotations

import re
from collections.abc import Iterable

_PATTERNS: list[tuple[str, str]] = [
    (r"no such table:\s*([\w\"]+)", "No existe la tabla \u00ab{0}\u00bb. Revisa la lista de tablas del panel izquierdo."),
    (r"no such column:\s*([\w\"]+)", "No existe la columna \u00ab{0}\u00bb. Revisa los nombres de las columnas de la tabla que est\u00e1s usando."),
    (r"ambiguous column name:\s*([\w\"]+)", "La columna \u00ab{0}\u00bb existe en m\u00e1s de una tabla. Prefija el nombre con la tabla: tabla.{0}."),
    (r"near\s*\"?([\w]+)\"?:\s*syntax error", "Error de sintaxis cerca de \u00ab{0}\u00bb. Revisa la ortograf\u00eda del SQL, los espacios y las comas."),
    (r"syntax error (?:near \"?([\w\"',;)]*)\"?)?", "Error de sintaxis cerca de \u00ab{0}\u00bb. Revisa la ortograf\u00eda del SQL, los espacios y las comas."),
    (r"incomplete input", "La consulta est\u00e1 incompleta. Rev\u00edsala; suele faltar un valor, un par\u00e9ntesis o un cierre de cadena."),
    (r"no such function:\s*([\w\"]+)", "No existe la funci\u00f3n \u00ab{0}\u00bb. Ejemplos v\u00e1lidos: COUNT, SUM, AVG, MIN, MAX."),
    (r"unknown column(.{0,40})", "Referencia a una columna desconocida:{0}."),
    (r"table .* has (?:no column named|no such column)\s*([\w\"]+)", "La tabla no tiene una columna llamada \u00ab{0}\u00bb."),
    (r"datatype mismatch", "Los tipos de datos no coinciden. Probablemente est\u00e1s mezclando texto (TEXT) con n\u00fameros (INTEGER/REAL)."),
    (r"foreign key constraint failed", "La fila que intentas insertar viola una llave for\u00e1nea."),
    (r"constraint failed", "Se viol\u00f3 una restricci\u00f3n de la base de datos (campo \u00fanico o no nulo)."),
    (r"unable to open database file", "No se pudo abrir la base de datos."),
    (r"unsupported file format", "Formato de archivo no soportado."),
]

# Pistas cuando el error huele a sintaxis PostgreSQL (spec compat-postgres).
# Se evalúan contra la CONSULTA (no contra el error) y solo si hubo error.
_SUGERENCIAS_DIALECTO: list[tuple[str, str]] = [
    (r"date_part\s*\(", "DATE_PART es de PostgreSQL; en SQLite no existe. Usa STRFTIME('%Y', columna) para el año ('%m' mes, '%d' día)."),
    (r"extract\s*\(", "EXTRACT es de PostgreSQL; en SQLite usa STRFTIME('%Y', columna) (año), '%m' (mes), '%d' (día)."),
    (r"\bnow\s*\(\s*\)", "NOW() es de PostgreSQL; en SQLite usa DATE('now') o DATETIME('now')."),
    (r"\bilike\b", "SQLite no tiene ILIKE; usa LIKE (en SQLite ya es insensible a mayúsculas en ASCII)."),
    (r"using\s+[A-Za-z_][\w$]*\.", "USING lleva la columna SIN la tabla: USING (cliente_id), no USING c.cliente_id."),
    (r"::", "El operador :: es de PostgreSQL; en SQLite usa CAST(x AS TIPO). (La app reescribe `expr::TIPO` simple automáticamente.)"),
]


def _quote_error(raw: str) -> str:
    return raw.replace("\n", " ")[:220]


# Patrones PostgreSQL (spec error-friendly-pg, F2 migración).
# El servidor puede hablar inglés o español según el locale de initdb:
# se cubren ambos. Los idents salen en minúsculas (se matchea en low).
_PATRONES_PG: list[tuple[str, str]] = [
    (r'relation "([^"]+)" does not exist', "No existe la tabla «{0}». Revisa la lista de tablas del panel izquierdo."),
    (r'no existe la relaci[óo]n «?([^»"\s]+)', "No existe la tabla «{0}». Revisa la lista de tablas del panel izquierdo."),
    (r'column "([^"]+)"(?: of relation "[^"]+")? does not exist', "No existe la columna «{0}». Revisa los nombres de las columnas de la tabla que estás usando."),
    (r'no existe la columna «?([^»"\s]+)', "No existe la columna «{0}». Revisa los nombres de las columnas de la tabla que estás usando."),
    (r'column "([^"]+)" .* specified more than once', "La columna «{0}» está repetida. Quita el duplicado."),
    (r'm[áa]s de una vez', "Hay una columna repetida. Quita el duplicado."),
    (r'syntax error at or near "([^"]*)"', "Error de sintaxis cerca de «{0}». Revisa la ortografía del SQL, los espacios y las comas."),
    (r'error de sintaxis (?:en o cerca de|cerca de|cercano a) «?([^»"]*)»?', "Error de sintaxis cerca de «{0}». Revisa la ortografía del SQL, los espacios y las comas."),
    (r'syntax error at end of input', "La consulta está incompleta. Revísala; suele faltar un valor, un paréntesis o un cierre de cadena."),
    (r'error de sintaxis al final de la entrada', "La consulta está incompleta. Revísala; suele faltar un valor, un paréntesis o un cierre de cadena."),
    (r'column "([^"]+)" must appear in the group by clause',
     "La columna «{0}» está en el SELECT pero no en el GROUP BY. Agrégala al GROUP BY o envuélvela en MAX(), MIN(), AVG(), SUM() o COUNT(). (SQLite la permite suelta; PostgreSQL exige agruparla.)"),
    (r'la columna «([^»]+)» debe aparecer en la cl[áa]usula group by',
     "La columna «{0}» está en el SELECT pero no en el GROUP BY. Agrégala al GROUP BY o envuélvela en MAX(), MIN(), AVG(), SUM() o COUNT(). (SQLite la permite suelta; PostgreSQL exige agruparla.)"),
    (r'function ([^(]+)\([^)]*\) does not exist', "No existe la función «{0}» con esos tipos de datos. Revisa los tipos de los argumentos (p. ej. date_part necesita texto + fecha)."),
    (r'funci[óo]n ([^(«]+?)\(', "No existe la función «{0}» con esos tipos de datos. Revisa los tipos de los argumentos (p. ej. date_part necesita texto + fecha)."),
    (r'invalid input syntax for type (\w+)', "El valor no encaja en el tipo {0}. Revisa el formato (p. ej. fechas 'AAAA-MM-DD', números con punto)."),
    (r'sintaxis de entrada no v[áa]lida', "El valor no encaja en el tipo esperado. Revisa el formato (p. ej. fechas 'AAAA-MM-DD', números con punto)."),
    (r'duplicate key value violates unique constraint', "Esa fila ya existe (valor duplicado en una columna única o llave primaria)."),
    (r'llave duplicada|viola.*unicidad', "Esa fila ya existe (valor duplicado en una columna única o llave primaria)."),
    (r'insert or update on table .* violates foreign key constraint', "La fila que intentas insertar viola una llave foránea."),
    (r'viola.*llave for[áa]nea', "La fila que intentas insertar viola una llave foránea."),
    (r'null value in column "([^"]+)" .* violates not-null constraint', "La columna «{0}» no acepta nulos: dale un valor."),
    (r'valor nulo.*columna «?([^»"\s]+)', "La columna «{0}» no acepta nulos: dale un valor."),
    (r'division by zero', "División por cero: revisa el divisor."),
    (r'divisi[óo]n por cero', "División por cero: revisa el divisor."),
]

# SQLSTATE → índice en _PATRONES_PG (variante inglesa; si no matchea se
# recorre la lista completa, cubriendo español).
_SQLSTATE_PG: dict[str, int | None] = {
    "42P01": 0, "42703": 2, "42701": 4, "42601": 6, "42803": 10,
    "42883": 12, "22P02": 14, "23505": 16, "23503": 18, "23502": 20, "22012": 22,
}


def friendly_pg_error(raw: str, table_names: Iterable[str] = (), query: str = "",
                      sqlstate: str | None = None) -> str:
    """Traduce un error PostgreSQL a español principiante (F2).

    Usa el SQLSTATE si viene (psycopg lo expone en `exc.sqlstate`); si no,
    cae a regex del mensaje. Sin coincidencia: genérico recortado.
    """
    low = raw.lower()
    if sqlstate in _SQLSTATE_PG:
        idx = _SQLSTATE_PG[sqlstate]
        if idx is None:
            return f"La base de datos respondió con un error:\n{_quote_error(raw)}"
        pattern, template = _PATRONES_PG[idx]
        m = re.search(pattern, low)
        if m:
            try:
                ident = m.group(1).strip().strip('"') if m.lastindex else raw.strip()
            except IndexError:
                ident = raw.strip()
            return template.format(ident)
    for pattern, template in _PATRONES_PG:
        m = re.search(pattern, low)
        if not m:
            continue
        try:
            ident = m.group(1).strip().strip('"') if m.lastindex else raw.strip()
        except IndexError:
            ident = raw.strip()
        return template.format(ident)
    return f"La base de datos respondió con un error:\n{_quote_error(raw)}"


def friendly_error(raw: str, table_names: Iterable[str] = (), query: str = "") -> str:
    low = raw.lower()
    if query:
        qlow = query.lower()
        for pattern, mensaje in _SUGERENCIAS_DIALECTO:
            if re.search(pattern, qlow):
                return mensaje
    for pattern, template in _PATTERNS:
        m = re.search(pattern, low)
        if not m:
            continue
        try:
            ident = m.group(1).strip().strip('"') if m.lastindex else raw.strip()
        except IndexError:
            ident = raw.strip()
        msg = template.format(ident)
        if "syntax error" in pattern and not m.lastindex:
            msg = "Error de sintaxis. Revisa la consulta."
        return msg
    return f"La base de datos respondi\u00f3 con un error:\n{_quote_error(raw)}"