# Spec: fix-template-pg-corrupto

> Estado: APPROVED — bugfix SDD (MOTOR NO DISPONIBLE por template purgado por limpiador de Temp).

## Objetivo
Que SQLab arranque siempre con PostgreSQL: si el cluster template cacheado
aparece **parcial** (sin `PG_VERSION` y no vacío — típico tras una limpieza de
`%TEMP%` por Storage Sense/CCleaner) se repara solo, y el template se guarda
en una carpeta **estable fuera de `%TEMP%`** para que los limpiadores no lo
vuelvan a corromper.

## Causa raíz (reproducida)
`%TEMP%/sqllab-pgdata-17` perdió `PG_VERSION`, `postgresql.conf`, `pg_hba.conf`,
`base/1` y las relation files: solo sobrevivieron archivos con fecha ≥ a 3 días
antes de la purga (patrón de borrado por antigüedad + borrado de carpetas
vacías). `_asegurar_cluster()` solo miraba `PG_VERSION` y ejecutaba `initdb`
sobre un directorio no vacío → `initdb: error: directory ... exists but is not
empty` → diálogo **MOTOR NO DISPONIBLE**.

## Acceptance criteria (Given/When/Then)
- **CR-01**: Given el directorio del template existe sin `PG_VERSION` y con
  restos (p. ej. `pg_wal/`, `postmaster.pid` rancio) y **no hay servidor vivo**,
  When `PGServer(...)`, Then se vacía el directorio y se ejecuta `initdb` de
  nuevo; el objeto queda usable (no lanza) y el directorio termina con
  `PG_VERSION`. Ningún resto del template viejo persiste.
- **CR-02**: Given un template sano (`PG_VERSION` presente),
  When `PGServer(...)`, Then **no** se ejecuta `initdb` ni se borra nada
  (ruta rápida intacta: cero escrituras).
- **CR-03**: Given un servidor **vivo** sirviendo ese data-dir con
  `postmaster.pid` (aunque le hayan borrado `PG_VERSION` en caliente),
  When se crea otro `PGServer` sobre la misma base, Then lo **adopta**
  (puerto del ajeno) y **no borra ni un archivo** (el servidor sigue
  respondiendo consultas).
- **CR-04**: Given `initdb` falla porque otra instancia acaba de llenar el
  directorio (carrera de primer arranque doble), When el reintento, Then se
  **adopta** ese cluster en vez de propagar el error.
- **CR-05**: Given que no se pasa `base_dir`, Then el template vive en
  `%LOCALAPPDATA%\SQLab\sqllab-pgdata-17` (carpeta estable, fuera de Temp).
  Si `LOCALAPPDATA` no existe/no es escribible → fallback a
  `%TEMP%\sqllab-pgdata-17` (comportamiento previo).
- **CR-06**: Given el directorio **no se puede vaciar** (archivo bloqueado por
  antivirus u otro proceso tras 3 intentos), When la reparación, Then
  `RuntimeError` en español con **la ruta completa** y la instrucción de borrar
  esa carpeta a mano (el diálogo MOTOR NO DISPONIBLE muestra ese texto).
- **CR-07**: Given la app arranca con el cluster ya reparado o sano, Then el
  resto del ciclo (arranque, `sqllab_<pid>`, cierre) es idéntico al de la spec
  `pg-engine`.

## Edge cases
- `postmaster.pid` rancio (servidor caído, PID muerto) + sin `PG_VERSION` →
  la espera de adopción no encuentra nada → se limpia y se re-inicializa.
- `postmaster.pid` con PID reutilizado por otro proceso → la adopción no
  conecta → se limpia (ver límites).
- Template inexistente (primer arranque) → sin carpeta que vaciar → `initdb`
  directo (caso actual).
- Dos instancias a la vez sobre el mismo template → la perdedora adopta
  (CR-04) o, si el `initdb` paralelo aún corre, espera la aparición de
  `PG_VERSION` antes de reintentar la adopción.
- Fallo de permisos al crear `%LOCALAPPDATA%\SQLab` → fallback a Temp.

## Límites conocidos
- El template **viejo** en `%TEMP%\sqllab-pgdata-17` queda huérfano (no se
  borra desde la app); el propio limpiador de Temp lo eliminará.
- Si un limpiador actúa **con la app abierta** y purga el data-dir en caliente,
  el servidor en ejecución puede fallar; la ruta nueva hace que eso no ocurra
  en Temp. No se monitoriza la salud del cluster en caliente.
- Un `postmaster.pid` con PID reutilizado puede hacer que `postgres` se niegue
  a arrancar ("lock file exists"): caso distinto, fuera de este alcance.
- No se usa lock cross-proceso: la carrera de initdb se resuelve por
  adopción/reintento (CR-04), no por exclusión mutua.

## Archivos a tocar
- `core/pg_engine.py`: `_dir_base_default()`, `_resolver_base()`,
  `PGServer.__init__`, `_asegurar_cluster()`, nuevos `_vaciar_template()` /
  `_recuperar_servidor()` / `_puerto_pid()` / `_puerto_vivo()` (ver E-01).
- `specs/pg-engine.md` (enmienda de la ruta del template),
  `specs/INDEX.md` (registro), `AGENTS.md` (changelog).

## Requisitos de testing
- **Unit** (sin binarios PG, corren en CI): CR-01, CR-02, CR-03 (marca
  restaurada + adopción simulada y servidor vivo ilegible), CR-04, CR-05,
  CR-06 con `subprocess.run` / adopción simulados.
- **Integración** (con binarios, `skip` si faltan): CR-01 con `initdb` real y
  CR-03 con servidor vivo real.
- **Nombre de archivo**: `tests/test_fix_template_pg.py`
  (spec id `fix-template-pg-corrupto` en `_SPEC_MAP`).
- **Verificación**: `python -m pytest -q` 100 % + `ruff check .`.

## Notas de diseño
- Orden en `_asegurar_cluster`: `PG_VERSION` → recuperación del servidor en
  caliente (CR-03) → vaciar → `makedirs` + `initdb` → si `initdb` falla,
  reintentar adopción (carrera) → error claro.
- **Adoptar antes de borrar** es la regla de seguridad: nunca se vacía un
  data-dir del que se pudo confirmar que hay un servidor respondiendo.
- La espera de adopción es ~5 s (10 × 0.5 s) y solo se activa cuando falta
  `PG_VERSION` **y** existe `postmaster.pid` (estado ya anormal), por lo que no
  penaliza el arranque normal.
- La ubicación nueva usa `LOCALAPPDATA` sin dependencias extra; se crea con
  `os.makedirs(..., exist_ok=True)` y su fallo cae a `tempfile.gettempdir()`.

## Enmienda E-01 (2026-10-07 — verificación de CR-03 con PG real)

**Hallazgo**: un servidor vivo con `PG_VERSION` borrado **no admite nuevas
conexiones** (cada backend nuevo hace `CheckDataVersion()` y muere con
`server closed the connection unexpectedly`); la adopción por SQL sola era
imposible. Comprobado además que `PG_VERSION` original es exactamente `b'17\n'`
y que **restaurarlo hace que el servidor vuelva a atender al instante** (sin
reinicio, conexión existente incluida).

Adaptación de CR-03 (mismo criterio de aceptación: adopción + cero borrado +
el servidor sigue respondiendo):

- `_recuperar_servidor()` sustituye a `_esperar_adopcion()` y devuelve un
  estado: `"adoptado"` (SQL ok) / `"servidor_vivo"` / `"nada"` (pid rancio o
  ausente → se repara, CR-01).
- Si hay `postmaster.pid` y **el puerto TCP responde**, la purga en caliente se
  repara restaurando el marcador `PG_VERSION` (`17\n`, bytes originales) y
  reintentando la adopción: ese archivo es justo el que borró el limpiador.
- Si el servidor sigue **vivo pero ilegible** (catálogo dañado, puerto
  ajeno): se **deshace** la marca escrita (para no enmascarar la corrupción:
  el próximo arranque, con el servidor caído, reparará solo) y se lanza
  `RuntimeError` en español con la ruta e instrucciones (CR-06). **Nunca** se
  vacía un data-dir con un servidor vivo escuchando.
- Un `postmaster.pid` rancio (puerto cerrado) sigue acabando en vaciar +
  `initdb` (CR-01); la sonda TCP es la que distingue rancio de vivo.

