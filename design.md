# design.md

## Decisión: SQLite en memoria (:memory:)

Toda la sesión vive en `sqlite3.connect(":memory:")`. Cargar un ejercicio recrea la BD. La ejecución es instantánea y 100% offline.

## Trade-offs aceptados
- Sin persistencia automática: al cerrar la app se pierde el estado, salvo que el usuario use *Guardar sesión* (exporta un `.json` con tablas + enunciado + historial).
- Sin merge de esquemas: cada carga reemplaza por completo las tablas anteriores.
- Límite práctico: el render se topa (`VISOR_MAX_FILAS=2000`,
  `RESULTADO_MAX_FILAS=5000`, conteos siempre con el total); el parseo sigue
  en memoria (sin streaming): ficheros >50 MB piden confirmación previa.

## Alternativas descartadas
- SQLite en archivo: complica permisos y empaquetado del .exe.
- DuckDB / Postgres embebido: dependencias nativas adicionales, overkill para ejercicios de principiante.

## UI: solo oscuro, pista colapsada, autocompletado OFF
- `dark.qss` único, sin toggle de tema. Paleta cyber fósforo (v5, esquinas rectas,
  scrollbars 4px): black `#040707` · obsidian `#080d0d` · panel `#0a1212` ·
  card `#0f1b1b` · borde `#153330` · verde `#00ffaa` · dim `#00aa70` ·
  ámbar `#ffb300` · cian `#00e5ff` · rojo `#ff3366` · texto `#d7ffec` · muted `#4d7c6d`.
  Solo monoespaciadas del sistema (sin Google Fonts/FontAwesome CDN).
- `QToolButton` para la pista (`checked=False` por defecto) para no distraer.
- `QSettings` guarda el toggle de autocompletado (`false` por defecto, checkbox `AC`
  en la consola). Cuando está activo, `QCompleter` sugiere tablas/columnas/keywords.

## UI SQLab (v8 — diseño vigente sep-2026; app 100 % en español)
La app se llama **SQLab**. HUD minimalista: logo (chip 26px renderizado desde
`resources/logo_sqllab.svg`) + marca `SQLab` + botones (`FORMATO JSON IA`,
`CARGAR EJERCICIO`, CSV/SAV/SES). Sin textos de versión/motor/heap,
sin reloj/ticks, sin testigos T1/T2/IO, sin tarjeta IA Link, sin ASCII-art.
- **Banner de misión**: `[NIVEL]: PRINCIPIANTE ★☆☆` (dificultad tal cual, en mayúsculas) +
  `[MISIÓN]: título` + `VER_PISTA/OCULTAR_PISTA` + `EJEMPLO: TIENDA/BIBLIOTECA`.
- **Hint drawer** oculto por defecto: `[IA_DESCIFRADO] PROTOCOLO DE SUGERENCIA:` + `[CERRAR]`.
- **Matriz de esquema 288px**: nodos `> tabla [NF]`, inspector `NODO: / COLUMNAS` con filas
  `# col [TIPO→[PK]]` (clic inyecta columna), `INSERTAR SELECT *`, `REGISTRO DE
  TRANSACCIONES` (20, `> query`, clic recarga+ejecuta, `[LIMPIAR]`) y barra
  `CACHÉ_TX: SINCRONIZADA / PRAGMA: DESACTIVADO`.
- **Centro 40/60**: tabs `[DIRECTIVA DE MISIÓN]` (spec + OBJETIVO N.º, COLUMNAS OBJETIVO
  en chips verde/cian, ORDEN) y `VOLCADO DE TABLA` (cabeceras `col ::tipo`,
  `N REGISTRO(S)`, `MEMORIA: OK`); consola con `FORMATO` (toggle checkable que
  queda marcado al activarse, `#FormatBtn:checked`), `AC`, `COPIAR PARA IA`
  (`CyberBtn` borde verde), `EJECUTAR_SQL` (F5/Ctrl+Enter), editor + tira
  (punto parpadeante, `LÍN/COL`, `DIALECTO: SQLITE3`, `UTF-8 // CRLF`); matriz
  `>> MATRIZ DE RESULTADOS` con badge `N FILAS`, `T_EJEC: ms // ESTADO: 200 OK` /
  `EN ESPERA` / `FALLO_EJEC // ERROR`, standby limpio y
  `EXCEPCIÓN_SINTAXIS_SQLITE CÓD_ERROR: 0x22` + `CONSEJO DE RECUPERACIÓN` vía
  `error_friendly`.
- **Tooltips** en botones, listas, editor, tabs y grillas (atributo `toolTip` en cada widget).
- **Esquina de grilla**: el botón de esquina de `QTableWidget` se pinta oscuro
  (`QTableCornerButton::section` en `dark.qss`); sin él Qt lo deja blanco (ver bug imagen).
- **Diálogos custom**: `_show_custom_dialog(parent, title, msg, kind)` reemplaza a
  `QMessageBox` (diálogo modal dark con `ACEPTAR`); regla `QMessageBox` eliminada del QSS.
- **Modal JSON**: `ESPECIFICACIÓN DE PROTOCOLO JSON PARA IA` con `COPIAR PLANTILLA`;
  al copiar el botón pasa a `✓ COPIADA` (deshabilitado) y muestra toast `ToastLabel` in-dialog ~2,4 s.
- `COPIAR PARA IA` usa la plantilla misión + query + mejora (en español).
- **Logo**: `resources/logo_sqllab.svg` (SVG Matrix verde, 1200×1200) → ícono de ventana
  (`QIcon`) en `app.py`/`MainWindow` y chip HUD; con Qt se renderiza vía `QIcon`, sin CDN.
  El icono del archivo `.exe` en Windows se genera con `bin/make_icon.py`
  (SVG → `logo_sqllab.ico` multi-tamaño 16–256) y se referencia con `icon=` en `run.spec`.
- **Crono por ejercicio** (v13, v14 verdoso): frame compacto `CronoFrame` en el HUD (`TitleBar`) con
  display `CronoTime` (`HH:MM:SS`), toggle de modo `CronoMode` (`CRONO` cuenta arriba /
  `TEMPO` cuenta regresiva desde `CronoSpin` 5–3600 s), `INICIAR`/`PAUSA` y `REINICIAR`.
  Reset automático (detenido, sin alerta) al aplicar un ejercicio nuevo. Fin de cuenta
  regresiva → toast `TIEMPO AGOTADO` + alerta roja (`#ff3366`). Granularidad 1 s con base
  `time.monotonic`. Sin persistencia del crono. v14: `CronoMode:checked` pasa de ámbar
  (`#ffb300`) a verde (`#00ffaa`/`rgba(0,255,170,0.15)`, como `FormatBtn:checked`) para estética
  verdosa uniforme del HUD.
- **Splitter matriz/editor** (v14): `work_splitter` (`QSplitter` horizontal editor|matriz) con
  `setChildrenCollapsible(False)`, `setCollapsible(0/1,False)`, `editor_pane` 220 / `output_pane`
  240 mínimos, `handleWidth` 6 (QSS `QSplitter::handle:horizontal` 1px visual + `margin:0 2px`
  para hit-area), método `_reset_work_splitter` por doble-clic en el handle.

## Carga de tablas Excel/CSV (v14)
- Fuente: carpeta con `*.csv` (UTF-8 o UTF-8-BOM, `,` o `;` auto-detectado vía `csv.Sniffer`),
  `*.xlsx` (`openpyxl` `read_only` + `data_only`) y `*.xls` (`xlrd` 2.0.1). Solo 1ª hoja.
  `core/session_loader.load_tablas_folder` (alias `load_csv_folder`) case-insensitive,
  `load_file` dispatch por extensión, cabeceras vacías→`colN`, duplicadas→`_2`, inferencia
  `INTEGER`/`REAL`/`TEXT`. Botón HUD `CSV`→`TABLAS` con tooltip formato completo; `run.spec`
  `hiddenimports=['openpyxl','xlrd']`; `requirements-dev.txt` añade `openpyxl`/`xlrd`/`xlwt`
  (xlwt solo para generar fixtures `.xls` en tests).

## Carga robusta + multi-sentencia + exportar (v20)
- JSON con BOM (`utf-8-sig` en `_parse_json` y `cargar_sesion`, como el CSV).
- `_normalize_headers`: dedup case-insensitive (SQLite no distingue
  `Nombre`/`nombre`) + elimina `"` (rompía el CREATE entrecomillado).
- `load_tables` devuelve omitidas; la UI avisa con toast (fin del descarte
  silencioso de tablas).
- `ver_select_all` entrecomilla (`SELECT * FROM "mis datos";`).
- `execute()` acepta scripts: `_partir_sentencias` (respeta literales y
  comentarios), corrección en orden, muestra el último resultado con filas;
  error amable si alguna falla (verificado: era `ProgrammingError`, no crash).
- `EXPORTAR CSV` en cabecera de resultados: vuelca el resultado COMPLETO
  (aunque la grilla esté topada) en `utf-8-sig` (Excel), `None`→vacío,
  `QUOTE_MINIMAL`; toast/cancel/vacío cubiertos.
- Estructura: repo aplanado a la raíz (`git mv` con historial); `LICENSE` MIT;
  CI en GitHub Actions (3.11 + 3.14); versión producto `1.0.0` en pyproject.

## NULL visible en grillas y CSV (v21)
- `_item_grilla` (`ui/tablas.py`): `None` → texto `NULL`, tooltip `NULL`,
  color tenue `#4d7c6d` (MutedLabel/StatusLabel del tema) + cursiva, sin
  alineación numérica; `""` sigue vacío (distinguible del nulo).
- `_ajustar_anchos`: mide el literal `"NULL"` en celdas `None` (no deja la
  columna estrecha).
- `EXPORTAR CSV`: enmienda a EX-03 — `None`→`NULL` (antes vacío), a pedido
  para analizar fuera de la app sin ambigüedad; BOM y `QUOTE_MINIMAL` intactos.
- Motor/carga/sesión intactos: los `None` siguen siendo nulos reales.

## Nulos CSV/Excel estilo pandas (v23)
- Reporte con foto: celdas "vacías" en CSV médico eran `" "` (espacios),
  que se conservaban y se veían vacías pese al render NULL de v21
  (el CSV ya convertía `""`→`None`, igual que Excel y JSON).
- Helper `_es_nulo` (`core/session_loader.py`): `None` o texto cuyo `strip()`
  está en `{"", "-", "NA", "NULL", "null", "NaN"}` (el `na_values` del
  usuario); se aplica en `_parse_csv` y `_parse_excel`, más relleno `None`
  en filas cortas. JSON excluido (respeta strings explícitos).
- Límite: `"NA"` legítimo → `NULL` (igual que pandas con `keep_default_na`).

## Scrollbars visibles (v25)
- El handle `#173834` sobre track `#060b0b` a 4 px era invisible sin hover.
  Ahora 12 px con handle `#00aa70` (dim del tema) + `border-radius` y hover
  `#00ffaa`; `add-line`/`sub-line` siguen en 0 y no hay colores claros.
- Tests por texto del QSS (patrón `test_crono_mode_checked_verde_en_qss`).

## Análisis profesional: SQLab como herramienta de análisis (v26)
- **Enter/Tab acepta autocompletado** (Fase 0): `eventFilter` en el editor +
  `_aceptar_autocompletado` + auto-resaltado; Ctrl+Enter/F5 y Escape intactos.
- **Botón CARGAR único** (P1): `cargar_unificado` despacha a ejercicio/tablas-archivos/tablas-carpeta; presets y plantilla intactos.
- **Consola vacía inicial** (P2): `_aplicar_resultado`/`cargar_preset` aceptan `escribir_query=False`; el arranque ya no inyecta `defaultQuery`.
- **EXPORTAR EXCEL** (P3): `openpyxl` (ya dependencia), `None`→`NULL`, anchos auto topados; CSV intacto.
- **Cierre de paréntesis** (P4): funciones completan `FUNC()` con cursor dentro; `(` manual se autocierra (con popup visible, normal).
- **Compat Postgres** (P5): `_reescribir_cast_postgres` (máscara de literales/comentarios + scan balanceado, `expr::TIPO`→`CAST`, anidados ok) + hints de dialecto en `friendly_error` (query opcional); CAST/USING fijados por regresión.
- **COPIAR especificación** (P6), **REGLA DE ORO sin pistas** en `CLAUDE_PROMPT` (P11), **historial contraído** con toggle (P12).
- **Auto-espaciado** (P9): el tope 300 vive en la medición (el header no lo impone, pues Qt re-encoge al restaurar); reparto proporcional en resize + base actualizable por el usuario; VA-03/VA-04/RG-04 actualizados.
- Abrir `.db` en solo lectura (`mode=ro`, Fase A1) completa la paridad de ingesta.

## Split Fase 3: mixins de carga y workspace (v27)
- `ui/carga.py` (`CargaMixin`): presets, ejercicio, tablas, aviso 50 MB,
  `_aplicar_resultado`, status (usa crono/briefing/autocomplete vía MRO).
- `ui/workspace.py` (`WorkspaceMixin`): `_build_ui` + builders de misión,
  volcado, deck, editor y salida (usa `_sep` y `_configurar_grilla_ancha`
  vía MRO/import).
- `main_window.py` 1344→822: queda el núcleo (ejecución, historial, sesión,
  exports, comparador, gráficos). La ejecución NO se extrae a propósito:
  el coordinador se lee junto (recomendación auditoría).
- Métodos movidos verbatim; equivalencia por suite + ruff.

## Migración a PostgreSQL embebido (v30+, en curso)
- F0 (spec `postgres-embebido-spike`, veredicto GO): `pgserver` no existe en
  PyPI y `testing.postgresql` exige binarios locales; EDB bloquea descargas
  automáticas → el usuario aportó `postgresql-17.11-4` manual; vendoreado
  `pgsql/{bin,lib,share}` (134.5 MB, fuera de git). `initdb` 9 s (una vez),
  arranque 0.7 s. Hallazgo: `pg_ctl start` se cuelga; usar `Popen(postgres)`
  + poll TCP + `terminate`.
- F1 (`core/pg_engine.py`): `PGServer`-less — `PGEngine` gestiona cluster
  template cacheado + BD `sqllab_<pid>` con DROP al cerrar; paridad
  (`execute` multi, `load_tables` con omitidas, `%s`, tipos PG, `exportar_db`
  vía `pg_dump`); `sqlite_engine.py` congelado hasta F6.
- F2 (`friendly_pg_error`): SQLSTATE + regex bilingüe; los hints SQLite
  (`::`→CAST etc.) no aplican en PG. Hallazgo: initdb hereda el locale del
  SO (aquí ES: PG habla español) → parse EN+ES, SQLSTATE como ancla.
- F3 (tipos en carga): `_infer_type` suma `BOOLEAN` (true/false/yes/no, nunca
  "t"/"f"), `DATE` y `TIMESTAMP` ISO validadas; conversión a `bool` real en
  CSV/JSON/Excel (PG aborta INSERT con texto en BOOLEAN); JSON/TEXT intactos.

## Template PG fuera de Temp + autoreparación (v35)
- Bug "MOTOR NO DISPONIBLE": el limpiador de Temp (Storage Sense) purgó
  `%TEMP%/sqllab-pgdata-17` (sin `PG_VERSION` ni conf) e `initdb` se negaba
  sobre el directorio no vacío.
- Ruta por defecto → `%LOCALAPPDATA%/SQLab/sqllab-pgdata-17` (fallback Temp);
  `base_dir` explícito manda (tests/fixture lo usan con template dedicado).
- Orden de reparación: `PG_VERSION` → sonda del servidor vivo → vaciar →
  `initdb` → adopción si otro proceso ganó la carrera → error accionable.
  Regla: **adoptar antes de borrar**; con servidor TCP escuchando jamás se
  vacía (error en español con la ruta).
- Hallazgo E-01: sin `PG_VERSION` el postmaster vivo rechaza conexiones
  (`CheckDataVersion`) → se restaura la marca (`17\n`, escritura en binario
  porque el modo texto Windows deja `\r\n`) para adoptar; si aun así no
  responde, la marca se deshace (no enmascarar) y se espera a que el servidor
  caiga para reparar solo.

## Corte de la UI a PostgreSQL (v33, F4)
- `MainWindow(engine=)` + arranque async en producción (`_HiloArranque` con
  señales listo/fallo; guards `MOTOR INICIANDO...` en entradas; `closeEvent`
  None-safe). Tests inyectan motor listo (sin hilos).
- `PGServer` compartido por sesión de tests + BD fresca por test
  (`sqllab_t<N>` con DROP al cerrar); conftest dual (PGSQLite fallback sin
  binarios; la suite corre en ambos motores).
- `engine.dialect`/`etiqueta_db`: `DIALECTO: POSTGRESQL`, `DB: PG LOCAL OK`,
  título `ERROR SQL` + `CÓD: {dialect}`; `sqlite_engine.py` solo suma los
  2 attrs (congelado en lo demás).
- Formateador con keywords PG (`RETURNING` como cláusula, `ILIKE`, `SERIAL`,
  `TIMESTAMP`, `BOOLEAN`...); `Decimal` alinea a derecha; `_build_ui`
  duplicado de Fase 3 eliminado (vale el del mixin).
- Hallazgos F4: `text = integer` estricto delató `_tipo_pg` sin sufijos
  (`INTEGER PRIMARY KEY`→TEXT; fix: conserva declaración si la base es
  conocida); `"a"`/`"A"` entrecomillados son distintos en PG (test CR-03 a
  tabla sin columnas, válida en ambos); EXPORTAR DB es `.sql` en PG.
- Cierre F4 (v34): adopción de servidor ajeno (2ª app o suite comparte el
  cluster leyendo el puerto de `postmaster.pid`; fix: el pid va en cp1252,
  leer bytes ASCII-tolerante); fixture de sesión en template dedicado;
  simulacro CI verde (327 tests, 0 fallos, 10 skips); CI con paso `ruff`.

## Split Fase 2: mixins de UI (v24)
- `ui/crono.py` (`CronoMixin`): `_build_crono` + formato/estado/handlers
  CRONO/TEMPO (solo toca attrs `crono_*`/`_crono_*`; usa `_toast` vía MRO).
- `ui/paneles.py` (`PanelesMixin`): `_build_hud`, `_sep`, `_build_banner`,
  `_build_hint_drawer`, `_build_matrix` + `_ruta_logo` (movida aquí para
  evitar import circular; `main_window` la re-importa).
- `MainWindow(CronoMixin, PanelesMixin, QMainWindow)`: 1429→1094 líneas.
  Métodos movidos verbatim; equivalencia verificada por suite + ruff.

## Rendimiento en tablas grandes (v18)
- Anchos por muestreo (`_ajustar_anchos`: primeras 100 filas + cabecera,
  `Interactive`, tope 300 px) en vez de `ResizeToContents` global: el ajuste
  no recorre las 221×200 celdas. El usuario puede reajustar a mano.
- `load_tables` usa `executemany` por tabla con fallback fila por fila si el
  lote falla (misma semántica: tablas inválidas se omiten).
- `_confirmar_archivo_grande`: suma de tamaños >50 MB → diálogo
  `ARCHIVO GRANDE ... PUEDE TARDAR` con `[CARGAR]`/`[CANCELAR]`.

## Grillas anchas con scroll (v17)
- El `Stretch` global en `visor_tabla`/`resultado_tabla` dejaba ~6 px por
  columna con 200 columnas (texto recortado por el padding QSS → pinta
  "vacío"). `_configurar_grilla_ancha` (ambas grillas): `ResizeToContents` +
  `setMaximumSectionSize(300)` + `stretchLastSection(True)` (tablas angostas
  sin huecos) + elide derecha + `setWordWrap(False)`; `_item_grilla` pone
  tooltip con el valor completo y conserva alineación derecha numérica.
  Límite: `ResizeToContents` recorre todo (~1-2 s con 221×200, una vez por
  carga). Sin congelar 1ª columna (no nativo en QTableWidget).
- Tests: `conftest._isolated_settings` también aísla el `QSettings` nativo
  (`SQLPractica/SQLPractica` en registro Windows) con snapshot/clear/restore,
  porque `setDefaultFormat` no redirige el constructor implícito.

## Carga por archivos + formato real + nombres (v16)
- Botón `CARGAR TABLAS`: mini-diálogo custom `[ARCHIVOS]` (`getOpenFileNames`
  multi `*.csv/*.xlsx/*.xls`) / `[CARPETA]` (flujo anterior intacto) /
  `[CANCELAR]`. `core.session_loader.combinar_resultados` fusiona N
  `load_file` con last-wins por nombre de tabla (+ toast `REEMPLAZADA(S)` con
  aviso de último archivo) y conserva errores por fichero (válidos cargan
  igual, inválidos se listan en `ERROR DE DECODIFICACIÓN`).
- Formateador SQL real: `_tokenizar_sql` (word/str/lcom/bcom/sym, espacios
  reconstruidos) + `_formatear_sql` (mayúsculas, salto antes de cada cláusula,
  indent 2 espacios/nivel, subconsultas +1, `AND/OR/ON` indentados,
  operadores de comparación espaciados, `COUNT(*)` sin nivel extra,
  idempotente). Botón `FORMATO SQL` ya no es checkable; editor vacío = no-op.
- Nombres UI en español claro (14 renombres, ver spec `ui-nombres-estado`).
  Barra `status_db` (`TABLAS: N · FILAS: M · DB: MEMORIA OK`) actualizada en
  `_aplicar_resultado` y `ejecutar_consulta`; fuera etiquetas decorativas.
  `app.py` arranca con `showMaximized()`.

## Ejemplos empaquetados en el exe (v15)
- `run.spec` empaqueta `examples → examples` (incluye
  `examples/csv/`), así el onefile funciona en otro dispositivo sin archivos
  externos. `MainWindow._bundle_dir()` devuelve `sys._MEIPASS` en frozen
  (con fallback dev si falta) y la raíz del repo en desarrollo;
  `cargar_preset` resuelve `examples/<fichero>` desde ahí. Los ejemplos del
  bundle son de solo lectura (se cargan en memoria).

## Formato JSON dual (v2, vigente)
`session_loader._normalize_ia_format()` acepta el formato IA del diálogo
(`title/difficulty/statement/expected_hint/defaultQuery/tables[{name,schema{},data[]}]`) y lo
convierte al interno (`ejercicio{titulo,enunciado,pista,dificultad,default_query}/tablas`).
Tipos con sufijo (`INTEGER PRIMARY KEY`) conservan la definición completa; la base se valida contra
`INTEGER, REAL, TEXT, NUMERIC, DATE, BOOLEAN`. Claves extra (`icon`) se ignoran.
