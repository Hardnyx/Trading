# Intersección local Bloomberg v4–SEC del primer corte

**Hito:** H1.2, identidad histórica y cierres originales. **Corte:** 31-dic-2024, 16:00 Nueva York. **Alcance:** investigación retrospectiva, sin datos nuevos incorporados y sin elegibilidad de replay integral.

El colector independiente `BloombergExcelCollector_v4.0` puede generar un archivo `stage/2024-12-31/stage.json` a partir de su almacén versionado local. El archivo `market.partial.json` contiene solo el snapshot; **no** contiene los recibos por registro necesarios para esta conciliación. Los históricos recuperados hoy mediante Excel/BDH quedan clasificados como capturas actuales, no como versiones verificadas en 2024.

El auditor [`historical_bloomberg_stage_audit.py`](../scripts/historical_bloomberg_stage_audit.py) confronta **exclusivamente en la estación local autorizada** los registros normalizados de ese `stage.json` con las posiciones originales del N-PORT SPY reconstruidas por `historical_identity_requests.build_requests()`. No consulta rentabilidades posteriores, resultados de modelos, universo actual ni ajusta umbrales para conseguir más coincidencias.

## Contrato requerido

Por cada posible enlace, deben existir en el almacén v4 registros de **fuente versionada con disponibilidad declarada anterior al corte**, comprobaciones de integridad, documento y versión original, semántica verificada y evidencia de identidad vigente. Se exigen:

| Dataset v4 | Campos y restricciones |
|---|---|
| `identifier_history` | `cusip` original exacto y `ticker` histórico, sin ambigüedad, con inicio y fin de validez explícitos |
| `security_master` | `currency=USD`, `type=stock` y `exchange_mic` de cuatro caracteres, provenientes de registros versionados |
| `daily_prices` | `close` positivo sin ajuste (`unadjusted-causal`), divisa USD y sesión del 31-dic-2024; sin anticipar su primera disponibilidad |

Las posiciones cuyo CUSIP original es inválido —26 posiciones extranjeras identificadas previamente por ISIN— se conservan como `invalid-original-cusip-requires-foreign-isin-route`, **sin imputar una correspondencia estadounidense**. Para estas posiciones corresponde el importador ISIN separado, sujeto a su propia prueba de identidad y mercado.

`stage` debe preservar el límite de las 16:00 de Nueva York, su huella de snapshot y los indicadores de inelegibilidad. Es indispensable una observación explícita del ticker en los N-PORT de comparación
anteriores al corte; si falta, no se acepta como cruce ni siquiera de
investigación. El auditor no se limita a una coincidencia de ticker: detecta CUSIP con múltiples claves, claves del almacén reutilizadas por varios CUSIP, conflictos de ticker, datos sin intervalo histórico, precios ajustados, cierres discrepantes y valores cuya disponibilidad declarada excede el corte.

`source_hashes` del colector enumera los originales utilizados **en los activos construidos en el stage**, no todos los originales de `normalized_asof_records`. Por ello se comprueba el formato de la huella individual y el recibo de cada registro, pero no se presume que la ausencia en `source_hashes` invalide una identidad aún no incorporada al snapshot. La autenticación contra bytes originales y credenciales de Bloomberg **no se repite aquí**: continúa siendo responsabilidad verificable de la custodia local y una auditoría independiente posterior. Los sellos autodeclarados tampoco prueban publicación efectiva en la fecha histórica.

## Ejecución local

Para generar una solicitud **solo de esquema, sin identificadores privados**:

```bat
python scripts\historical_bloomberg_stage_audit.py --template out\historical-bloomberg-first-cut-request.json
```

Tras importar originales auténticos y verificar localmente los registros históricos en el almacén Bloomberg v4, generar el `stage.json` de investigación:

```bat
.venv\Scripts\python.exe collector.py stage --cutoff 2024-12-31T16:00:00-05:00 --output "%LOCALAPPDATA%\BloombergDatos"
```

El colector puede terminar con código 2 por bloqueos y aun así escribir el `stage.json`. Desde la carpeta de Trading, ejecutar la conciliación **sin mover los originales a Git ni a CI**:

```bat
python scripts\historical_bloomberg_stage_audit.py --stage "%LOCALAPPDATA%\BloombergDatos\stage\2024-12-31\stage.json" --warehouse-root "%LOCALAPPDATA%\BloombergDatos\warehouse" --report out\historical-bloomberg-first-cut-receipt-v1.json
```

El informe bajo `out/` es **privado**: puede contener IDs nativos de proveedor, CUSIP y huellas originales. No debe publicarse en el repositorio ni adjuntarse a los workflows públicos si la licencia restringe su difusión. La consola solo informa conteos y no expone esos identificadores.

## Criterio de aceptación y límites

La aceptación técnica consiste en reproducir la matriz de posiciones desde N-PORT SEC, cargar el `stage.json` original, comprobar el sello de snapshot, rechazar versiones fuera de fecha/ambiguas y conservar un recibo privado con **el denominador completo**. Una coincidencia permanece etiquetada `research-only-v4-sec-source-intersection`, **no** `certified`, aunque presente cierre y MIC.

La promoción a H1 requiere además identificación jurídica continua y deslistados, fuentes independientes de primeras disponibilidades, sesiones y operaciones corporativas completas, precios ejecutables, perfiles y fundamentos del resto del universo, y procedencia causal de parámetros. El resultado de la auditoría mantiene `full_engine_eligible_cuts_added=0`, `production_eligible=false` y `predictive_validation=not-established`; no se altera H0.3 ni se emite ningún pronóstico u orden.

La batería `python -m unittest tests.test_historical_bloomberg_stage_audit` prueba el contrato con registros **sintéticos**. No hay prueba de ejecución real contra Bloomberg Terminal en esta entrega.

## Segregación de identificadores no estadounidenses y prueba con originales SEC

El N-PORT completo conserva **504 posiciones positivas**, de las cuales **478
incluyen un CUSIP que pasa el dígito de control** y **26 tienen el CUSIP original
inválido o no utilizable**. La ruta Bloomberg/CUSIP descarta estas últimas
incluso si un extracto del proveedor repite su identificador placeholder:
la coincidencia literal no crea un instrumento estadounidense.

Para distinguir una excepción sin resolver de una posición extranjera realmente
identificada, la ejecución local vuelve a abrir el N-PORT original mediante
`historical_sec_alternate_identity.audit()`, comprueba el SHA-256 del mismo
original, las 26 posiciones y sus pesos, y exige exactamente un ISIN extranjero
válido **expreso en el SEC** por excepción. Solo tras ese contraste las etiqueta
`original-foreign-isin-separate-vendor-route`. La ruta de consulta del
proveedor por ISIN ya existe separadamente; este puente no realiza esa
consulta ni transforma un ISIN en CUSIP. Un informe invocado en pruebas sin
el cotejo original conserva el estado `invalid-original-cusip-requires-isin-source-review`.

Las cuentas de 478 y 26 son **fuentes identificadoras**, no identidades
permanentes verificadas ni cierres de precio; ninguna se incorpora al replay.

## Control de cronología de los cierres originales

La confrontación con el código de `bbg.pit.Record` y `bbg.adapter.stage` del colector v4.0 mostró que el puente inicialmente aceptaba, en su fixture sintético, un cierre de **31-dic-2024** declarado como publicado el **1-oct-2024**. Es una secuencia imposible y no constituye un dato Bloomberg real. La auditoría ahora descarta cierres cuya publicación antecede a la propia fecha observada y, para el cierre de la sesión de decisión **31-dic-2024**, exige publicación no anterior a las **16:00 de Nueva York**, sin permitir una disponibilidad posterior a esa decisión. Las pruebas adversariales cubren publicación adelantada varios meses, un segundo antes de las 16:00, y difusión posterior al corte.

Este control no demuestra que un cierre pudiera **ejecutarse** exactamente a las 16:00 ni verifica un calendario bursátil completo, la latencia del proveedor, la publicación independiente de la fuente o precios de sesiones previas. Los datos de cierre difundidos después de las 16:00 no están disponibles para la decisión registrada exactamente a esa hora y permanecen excluidos; cualquier política de decisión poscierre requiere fijar otra hora antes de iniciar una cohorte, no desplazarla retrospectivamente. El dataset no se usa para entrenar o optimizar rendimientos confirmatorios.

## Conciliación de bytes originales y almacén local (11-nov-2026)

Para el uso real de `--stage` se exige también `--warehouse-root`: la carpeta `warehouse` creada por `BloombergExcelCollector_v4.0` bajo la raíz de salida (`warehouse.sqlite3` y `raw/<SHA256>.json`). El auditor abre SQLite **en modo solo lectura**, obtiene cada `record_id` a partir del JSON canónico de los registros seleccionados de `stage.json`, comprueba que corresponda a una fila inalterada del almacén y vuelve a abrir **los archivos originales de procedencia** por sus SHA-256. También confronta los punteros del documento intermediario `pit-source-document-v1` con el valor y las fechas que aparecen en el original de proveedor. Una discrepancia de bytes, reloj, identificador, fuente, puntero o cita del stage interrumpe toda la ejecución, sin emitir un informe afirmativo.

La comprobación no escribe sobre la base de datos ni copia originales a GitHub. Los recibos del informe privado separan el número de registros del stage, archivos reabiertos y documentos de proveedor reexaminados; conservan explícitamente `original_vendor_publication_independently_authenticated=false` y `full_engine_eligible_cuts_added=0`. La integridad **local** de un archivo no acredita una respuesta Bloomberg auténtica ni que el dato estuviera publicado en la fecha declarada. Sin un almacén original válido, la CLI no admite la reconciliación de fuentes privadas; el modo `--template` sigue funcionando sin Bloomberg.

Los tests `tests/test_historical_bloomberg_warehouse_receipt.py` manipulan identificadores de fila, originales, valores, relojes, punteros, citas y rutas en una base SQLite sintética. Se comprobó además la compatibilidad local con `bbg.pit.Warehouse.import_document()` y `Warehouse.as_of()` de la versión 4.0, usando un documento sintético no acreditativo; no se han recibido datos licenciados del mercado.

## Selección temporal del stage reconstruida desde el almacén (11-nov-2026)

El comprobador de originales ahora realiza una **segunda conciliación del conjunto completo de filas** mediante [`historical_bloomberg_asof_replay.py`](../scripts/historical_bloomberg_asof_replay.py). Lee todas las filas serializadas de `pit_records` en SQLite bajo la misma transacción de solo lectura, verifica su digest canónico y reconstruye, sin importar el código del colector ni confiar en sus columnas de índices, las reglas `as_of` registradas: calidad PIT, primera disponibilidad, fechas de observación y efecto, vigencia de identidades y revisión más reciente por clave lógica. Ante discrepancia con `normalized_asof_records`, incluso **por omisión de una fila vigente o por conservación de una revisión anterior**, se rechaza el stage.

La reproducción controla expresamente las 8 dimensiones que forman la clave lógica de observación y la precedencia por `first_available_at`, `vintage_id` y `revision_id`; rechaza valores contradictorios bajo un mismo orden de versión. El informe **privado** registra `warehouse_asof_rows_independently_reselected`, `warehouse_records_examined_for_asof` y `stage_asof_selection_independently_recomputed=true`. La comprobación del contenido SHA-256 de los archivos originales continúa siendo obligatoria. La selección temporal reproducida es una **verificación de consistencia interna** del algoritmo y del archivo, no una autenticación independiente de la disponibilidad real de Bloomberg, ni un calendario de sesiones, ni un sello de modelo históricamente preregistrado. La ruta de evidencia histórica del motor y sus 0/48 cortes completos no cambian.

Las pruebas de casos positivos y adversariales son sintéticas. Además de 13 pruebas unitarias locales se contrastó la selección con `Warehouse.as_of` del colector v4.0 real, incluida una revisión más reciente que reemplaza el valor anterior. Esa comprobación no constituye un dato de proveedor.

## Integridad global del archivo y frontera exacta de decisión (11-nov-2026)

El contrato del colector v4 rechaza una ejecución `Warehouse.as_of()` si
**cualquier** fuente archivada tiene un SHA-256 incorrecto, incluso si esa fuente
no aparece en las filas seleccionadas. La verificación privada de Trading
reproduce ahora esa condición: recorre el inventario completo de `raw_sources`
bajo la transacción SQLite de solo lectura y vuelve a calcular cada huella
sobre los bytes de `raw/<sha256>.json`, por bloques. Una fuente omitida,
alterada o sustituida fuera de la carpeta archivada impide generar el recibo.
El conteo `warehouse_all_raw_source_files_verified` cubre tanto fuentes
incluidas como excluidas por `as_of`. La selección histórica de filas y la
reapertura de sus originales continúan como comprobaciones independientes.

La frontera del corte quedó cerrada **exactamente** a las
16:00:00.000000 de Nueva York: un sello de 16:00:00.000001 no es admisible.
Esto impide que un segundo fraccionario posterior amplíe inadvertidamente
el conjunto de datos; no prueba la ejecución de operaciones a ese precio
ni verifica una publicación histórica de Bloomberg. No se alteran la
clasificación de investigación, las cohortes ni los parámetros.

## Solicitudes operativas segregadas y estado real del catálogo v4

Para preparar una solicitud Bloomberg **sin proveedor consultado todavía**,
se conservan dos artefactos independientes derivados de la misma evidencia
N-PORT original. Desde Trading, generar la lista CUSIP válida:

```bat
python scripts\historical_vendor_identity.py --valid-cusip-template out\bloomberg-cusip-validos-2024-12-31.csv
```

El CSV prioriza por peso SPY descendente las **478 posiciones** con CUSIP
original verificable y conserva `source_position`, nombre y ticker observado
en SEC como pistas, **no** como identificaciones del proveedor. No modifica la
plantilla de auditoría `--template`, que sigue incluyendo las 504 posiciones
positivas originales, con las 26 excepciones conservadas en el denominador.

La ruta extranjera independiente se genera con:

```bat
python scripts\historical_foreign_isin_requests.py --csv out\bloomberg-isin-extranjero-2024-12-31.csv
```

La segunda lista incluye los **26 ISIN extranjeros explícitos del SEC**; no se
reinterpreta ninguno como CUSIP estadounidense ni se presume moneda USD.
Las dos listas son solicitudes de investigación, no exportaciones Bloomberg
ni autorizaciones para completar el motor.

El `field_registry.json` revisado del
`BloombergExcelCollector_v4.0` suministrado clasifica
`BDP ID_BB_GLOBAL` y `BDP CRNCY` como
`CURRENT_SNAPSHOT_ONLY`, `BDH PX_LAST` como `UNVERIFIED` y
`identifier_history/historical_FIGI_CUSIP_ISIN_ticker_intervals` como
`BLOCKED_NO_NATIVE_PIT_QUERY_VALIDATED`. Una consulta ejecutada hoy
puede aportar **candidatos retrospectivos** pero no demuestra que el
identificador, el precio o la revisión fueran conocidos al corte de 2024.
La incorporación a `pit-import` exige el documento original fechado,
huellas y punteros de valor/publicación/disponibilidad. La revisión
independiente de la primera publicación y los derechos de uso siguen pendientes.

En Windows, ejecutar el auditor con el mismo entorno Python que haya instalado
la dependencia `tzdata` del colector v4.0, especialmente cuando la
instalación de Python no dispone de zonas IANA del sistema.

## LEI original del emisor: evidencia SEC que sí está archivada

La SEC distingue en el [Form N-PORT](https://www.sec.gov/about/forms/formn-port.pdf) el **LEI de la entidad emisora** de los identificadores del valor (CUSIP, ISIN, ticker). El repositorio ya conserva, bajo SHA-256, los bytes originales del N-PORT SPY anterior al corte 31-dic-2024. El módulo [`historical_spy_issuer_lei.py`](../scripts/historical_spy_issuer_lei.py) **reabre ese original**, verifica el mismo accession y huella utilizados para las 504 posiciones positivas, compara sus posiciones originales y extrae solamente el campo `lei` directo de cada inversión.

Se distingue LEI vacío, LEI indicado expresamente como no disponible, identificador inválido y LEI de 20 caracteres con dígitos de control **ISO 17442, módulo 97**. Se conserva el valor original sin corregirlo. Si el mismo CUSIP válido aparece con LEI válidos contradictorios en la fuente, esas pistas se ponen en cuarentena, sin elegir una entidad a partir del nombre o ticker. Ningún LEI se convierte en FIGI, CUSIP o prueba de titularidad de una acción.

Generar la nueva cola operativa **solo de CUSIP válidos**, con pista de LEI y procedencia del original:

```bat
python scripts\historical_spy_issuer_lei.py --verify
python scripts\historical_spy_issuer_lei.py --csv out\bloomberg-cusip-lei-sec-2024-12-31.csv --report out\sec-original-issuer-lei-review-v1.json
```

El CSV preserva `source_position`, CUSIP, nombre y ticker observados, peso, corte, `original_issuer_lei_as_filed`, `issuer_lei_hint`, estado de validación, accession original, SHA-256 y fecha de reporte/disponibilidad conservadora. Solo se ofrece `issuer_lei_hint` cuando pasa la validación. Las 26 posiciones de CUSIP inválido siguen fuera de esta cola y **permanecen íntegramente** en la ruta ISIN existente. Los datos son públicos de la SEC; no se envía documentación Bloomberg a GitHub.

**Limitación temporal:** el N-PORT refleja una fecha de tenencias histórica y su divulgación posterior. Que el LEI figure en el N-PORT no prueba la vigencia de un valor negociable, la correspondencia CIK/LEI, la disponibilidad de un identificador Bloomberg a las 16:00 del 31-dic-2024, la existencia de una cotización de ejecución ni la composición exacta del índice ese día. Esta evidencia complementa solicitudes manuales al proveedor, pero **no añade cortes admisibles**, calibra parámetros ni valida habilidad predictiva.

### Resultado real y artefacto reproducible

La primera ejecución verificada de [CI `43067002537`](https://github.com/Hardnyx/Trading/actions/runs/43067002537)
produjo desde el archivo SEC original los siguientes conteos:
**504 posiciones positivas, 478 CUSIP válidos, 26 excepciones**;
**486 LEI válidos de emisor** y **18 LEI declarados no disponibles**.
En la cola CUSIP son **463 de 478 posiciones con LEI válido**,
correspondientes a **460 LEI distintos** (otras 15 posiciones CUSIP
no tienen LEI). La prueba ahora congela estos conteos junto con la huella
y el accession del archivo original; ninguna identidad Bloomberg se deduce.

El workflow independiente [`SEC issuer LEI requests (research)`](https://github.com/Hardnyx/Trading/actions/workflows/issuer-lei-requests.yml), de ejecución selectiva y manual, genera y conserva durante 14 días un
artefacto denominado **`sec-original-issuer-lei-requests`**, formado por
`sec-issuer-lei-cusip-2024-12-31.csv` y
`sec-issuer-lei-source-summary-2024-12-31.json`, descargable desde su
página de GitHub Actions. Son solicitudes de investigación basadas en
datos públicos de la SEC, **no respuestas de proveedor**.

**Entrega comprobada.** [Workflow de fuente SEC `43068978317`](https://github.com/Hardnyx/Trading/actions/runs/43068978317) aprobado y artefacto `sec-original-issuer-lei-requests` publicado (ID GitHub `13876763494`, expiración 25-nov-2026 UTC). [CI general `43068978256`](https://github.com/Hardnyx/Trading/actions/runs/43068978256) aprobada: 597 Python, 382 JavaScript y guardias metodológicos. La publicación usa un flujo de investigación **separado**; la CI rápida conserva su prohibición de `actions/upload-artifact`.

## Contraste con otros N-PORT originales de fondos iShares (11-nov-2026)

La cola CUSIP/LEI del SPY se complementa mediante [`historical_crossfund_issuer_lei.py`](../scripts/historical_crossfund_issuer_lei.py). Se reabren los originales SEC de los **cinco fondos iShares** con últimas tenencias disponibles antes del corte: IVV e ITOT al 30-sep-2024 (disponibilidad conservadora desde 29-nov-2024), e IYY, ISCB e ILCB al 31-oct-2024 (desde 30-dic-2024). La antigüedad de las tenencias no excede **120 días**. No se consultan N-PORT publicados después de la fecha de decisión ni se reemplazan documentos con series actuales.

Para cada documento se vuelve a comprobar la fuente archivada, accession, hash SHA-256, fecha, identidad de la serie de fondos y digest de las observaciones originales de `historical_identifiers.parse_observations`. A continuación se extraen literalmente CUSIP y LEI de las inversiones de renta variable largas en USD, **incluyendo los fondos que no publicaron tickers**, y se contrastan con los 478 CUSIP válidos del SPY. Solo se registra un **acuerdo entre fuentes** si el LEI de emisor original del SPY pasa su dígito de control y es idéntico al único LEI válido observado por los otros fondos. Cualquier diferencia entre LEI válidos de fondos o entre estos y SPY queda en cuarentena; nunca se elige una correspondencia por parecido de nombre, por popularidad o por comportamiento posterior.

```bat
python scripts\historical_crossfund_issuer_lei.py --verify
python scripts\historical_crossfund_issuer_lei.py --csv out\sec-crossfund-issuer-lei-2024-12-31.csv --report out\sec-crossfund-issuer-lei-summary-2024-12-31.json
```

El workflow selectivo [`issuer-lei-requests.yml`](../.github/workflows/issuer-lei-requests.yml) añade ambos archivos al artefacto de investigación `sec-original-issuer-lei-requests`. **Importante:** la coincidencia en dos N-PORT prueba únicamente que dos fondos reportaron los mismos caracteres de CUSIP y LEI; no confirma de manera independiente la razón social, clase de acciones, CIK, vigencia jurídica, identificador Bloomberg, primera publicación real del proveedor o precio ejecutable. El emparejamiento sigue siendo una pista documental retrospectiva, sin promoción a un corte del motor completo. Los resultados de la CI y el número de acuerdos/contradicciones deben registrarse antes de cualquier interpretación de cobertura.

### Resultado de cinco originales disponibles al corte

El [workflow selectivo `43071557392`](https://github.com/Hardnyx/Trading/actions/runs/43071557392) reabrió los **cinco N-PORT** y seleccionó **6.033 posiciones** de renta variable larga en USD con CUSIP válido, aplicando los filtros de fuente indicados. De los **478 CUSIP válidos de SPY** resultaron **463 acuerdos de LEI de emisor**, **dos registros con LEI válido solamente en otro fondo**, **13 CUSIP observados en otros fondos sin LEI válido**, y **cero conflictos de LEI válidos**. El acuerdo representa una coincidencia de datos de tenencia en distintos reportes (los cinco de la misma familia iShares), no una constatación independiente del identificador jurídico ni del instrumento.

El CSV complementario conserva además `other_fund_valid_lei_values` para **revisión manual**. En los dos casos donde falta LEI en SPY y existe uno en otra fuente, este campo no pasa a `crossfund_corroborated_issuer_lei`; ante conflictos conserva los valores originales pero no elige uno. Los resultados se congelan mediante pruebas contra los originales SEC archivados. El artefacto actualizado sigue siendo `sec-original-issuer-lei-requests`, con dos CSV y dos resúmenes de procedencia, sin respuestas Bloomberg. Ninguna de estas coincidencias constituye una aprobación H1.2.

## Fuente SEC 13F de una gestora independiente (primer corte)

**Objetivo:** corroborar los CUSIP y la denominación de clase de las 478 posiciones SPY del 31-dic-2024 mediante un documento de un gestor ajeno a iShares/State Street. Se selecciona de antemano la [13F-HR original de Vanguard Group](https://www.sec.gov/Archives/edgar/data/102909/0001752724-24-248565-index.htm), accession `0001752724-24-248565`, de tenencias al **30-sep-2024**, presentada ante la SEC el **13-nov-2024 a las 11:58:36 ET**. La información estaba fechada antes del corte de investigación, pero **no** se certifica su primer instante histórico de divulgación mediante un proveedor independiente.

El [módulo `historical_independent_13f.py`](../scripts/historical_independent_13f.py) obtiene exclusivamente el **archivo completo original** `.txt` de esa presentación con un `SEC_USER_AGENT` real, valida el `SEC-HEADER` (CIK `102909`, accession, 13F-HR y aceptación exacta) y extrae la tabla XML `13F_0000102909_20240930.xml` que pertenece **al mismo archivo**. El XML se coteja literalmente: se consideran exclusivamente cantidades denominadas en `SH` sin opciones PUT/CALL; se preservan nombre y clase `nameOfIssuer/titleOfClass` declarados. Se prohíbe usar la cantidad o valoración declarada en 13F como cotización histórica, o equiparar su nombre con un CIK/LEI/FIGI. Si para un CUSIP figuran varias combinaciones de nombre/clase, se registra ambigüedad en lugar de escoger una.

Para reproducirlo en un ambiente autorizado, con el identificador y contacto real de la SEC configurado en `SEC_USER_AGENT`:

```bat
python scripts\historical_independent_13f.py --collect
python scripts\historical_independent_13f.py --verify
```

La primera orden conserva el archivo SEC original comprimido de modo reproducible y un recibo SHA-256 bajo `data/historical/independent-13f-v1/`, y produce un JSON y CSV de investigación bajo `out/`. El [workflow `independent-sec-13f.yml`](../.github/workflows/independent-sec-13f.yml) es selectivo (primera publicación o cambios del auditor, además de ejecución manual), conserva originales públicos como evidencia versionada y retiene temporalmente el CSV para consulta. No altera la CI rápida ni opera sobre fuentes Bloomberg con licencia.

La evidencia refuerza la lectura **CUSIP → título de clase declarado por otra gestora**, no la identidad legal de un instrumento permanente, su vigencia a cada fecha, dividendos/splits, precios originales ejecutables, naturaleza de acciones estadounidenses o completitud histórica del universo de inversión. **H1.2 y la validación predictiva continúan bloqueados** hasta verificar estos requisitos y demás entradas del motor; cero cortes de replay promovidos.

### Resultado real de la primera adquisición de Vanguard 13F

El [workflow de investigación `43075693783`](https://github.com/Hardnyx/Trading/actions/runs/43075693783) aprobó la adquisición oficial y depositó el original público en [`data/historical/independent-13f-v1/`](https://github.com/Hardnyx/Trading/tree/main/data/historical/independent-13f-v1) con el [commit `a23234c`](https://github.com/Hardnyx/Trading/commit/a23234c5ce1982dce04ad1745de3447014ba7985). El documento completo tiene **7.166.174 bytes**, SHA-256 original `9ad4a1d7fa286d96273cc57e95188a5392d7aae2f2358d0250fa8c3f3a2a0527`, y aceptación SEC original el **13-nov-2024 16:58:36 UTC**. La tabla original enumera **14.733 posiciones de acciones ordinarias o clases declaradas sin opción y en cantidad de títulos**; el auditor encontró **478 de 478 CUSIP válidos de SPY** con un único nombre y clase as-filed en el 13F. Se añade una prueba de regresión del contenido archivado para verificar exactamente ese resultado en CI. La extracción no añade los 26 CUSIP/ISIN extranjeros a la vía estadounidense. **Una coincidencia de clase de tenencia de un gestor independiente no certifica FIGI, CIK del emisor, LEI del instrumento, precio de ejecución, calendario ni datos PIT del proveedor Bloomberg.** La primera divulgación de esos bytes específicos no está autenticada por una segunda fuente: el original SEC contiene un sello de aceptación anterior al corte y el recibo registra descarga efectuada el 11-nov-2026.
