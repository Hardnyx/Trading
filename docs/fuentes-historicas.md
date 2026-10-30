# Datos fechados para reconstruir el motor completo

Protocolo `historical-provider-inputs-v1`. Recuperación de datos públicos
para los 48 cierres mensuales del estudio congelado, octubre de 2022 a
septiembre de 2026. No ejecuta el optimizador ni cambia el modelo publicado.

## Medición del 30-oct-2026

La colección se descargó, publicó y volvió a verificar desde los originales:

| Requisito | Resultado medido | Implicación |
|---|---|---|
| Macro | 768/768 combinaciones serie/corte; 16 series en los 48 cortes | Cerrada la recuperación del periodo real ALFRED para este corpus |
| Documentos originales SPY | 30 documentos, de los que 20 son XML N-PORT verificados | Se conservan los originales, sin deducir fechas de publicación de la fecha de cartera |
| Holdings con disponibilidad previa y edad admisible | 26/48 cortes | Otros 22 superan el límite vigente de 120 días; no se amplía para llenar huecos |
| Peso con ticker explícito en los XML | 0% en los veinte documentos | Están los pesos y CUSIP; falta un enlace histórico verificable a instrumentos y precios |
| Motor completo apto para replay | 0/48 cortes | Siguen faltando identificadores, perfiles, calidad contable y universo históricos |

Los 768 registros son paquetes de **datos de entrada**, no 768 pruebas
predictivas ni observaciones independientes de acierto. Los distintos
formatos archivados del mismo raw no se cuentan como evidencia adicional.
La recuperación inicial de SPY detectó una ruta de presentación XSL; se
corrigió el acceso al XML original y se conservó el resultado completo.
La primera versión macro archivada se reutiliza en las pasadas posteriores.

La matriz verificable se encuentra en
[`readiness.json`](../data/historical/provider-inputs-v1/readiness.json), y el
inventario con hashes en [`manifest.json`](../data/historical/provider-inputs-v1/manifest.json).
El diagnóstico no cambia el estado `not-established` de la capacidad predictiva.

## Matriz del replay integral por componente

La [matriz de 48 cierres](../data/historical/replay-plan-v1/coverage.md)
detalla qué fuentes pueden verificarse y qué componentes siguen bloqueados.
Se publica también en [JSON](../data/historical/replay-plan-v1/coverage.json)
y [CSV](../data/historical/replay-plan-v1/coverage.csv), con una fila por
fecha y componente en el CSV. No se limita a un indicador global de aptitud.

```sh
python -m unittest tests.test_historical_replay_plan
python scripts/historical_replay_plan.py
python scripts/historical_replay_plan.py --require-full-engine
```

El último comando escribe la evidencia y termina con código 2: no hay
adaptadores causales completos ni un solo cierre elegible. La ejecución
normal comprueba fuentes, no ejecuta Monte Carlo ni el optimizador.
Los bloques de pronósticos y órdenes permanecen nulos. La macro verificada
y un N-PORT público no habilitan por sí solos ninguna etapa del modelo.

Cada regeneración reaudita los bytes originales; no confía en los booleanos
de `readiness.json`. Conserva todos los cierres, propaga dependencias, registra
hashes de fuentes, motor y [protocolo de evaluación](protocolo-replay-integral-v1.md).
Faltan también precios y flujos operables reconciliados y la procedencia
temporal de los parámetros: congelar el kernel actual no demuestra que se
hubiera calibrado con información anterior a cada corte. Este periodo ya
inspeccionado continúa clasificado como desarrollo, sin holdout independiente.

## Macro conocida en cada fecha

Se consultan las 16 series del motor mediante el API oficial FRED/ALFRED.
Cada petición fija `realtime_start = realtime_end = corte − un día` y
limita las observaciones a esa versión. Se usa un día anterior porque el
API identifica días, no la primera disponibilidad intradía en Nueva York.
No se sustituye una petición histórica fallida con el CSV actual.

Se conservan el cuerpo original, hash, petición sin credenciales, fecha
real de descarga y derivación normalizada. La fecha de descarga sigue siendo
actual: la evidencia histórica procede del periodo real declarado por el
proveedor, no de fingir que Trading lo había descargado antes.

La API documenta que el periodo real permite consultar lo conocido entonces:
[periodos reales](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
y [observaciones](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).
No son sellos prospectivos ni una firma criptográfica de la disponibilidad.
El proveedor puede tener errores: la respuesta original queda conservada.

Cada registro verifica versión, identidad de la petición, filas completas,
ausencia de fechas futuras/duplicadas y coincidencia entre datos normalizados
y cuerpo archivado. Los huecos originales no se rellenan con cero. Una
repetición reutiliza la primera respuesta archivada; no selecciona después
una revisión favorable del proveedor.

La descarga usa cuatro peticiones en vuelo como máximo y un único limitador
global, con al menos 0,65 segundos entre inicios. Se guarda un checkpoint
atómico después de cada registro: una interrupción conserva lo descargado
sin presentarlo como colección completa. El workflow reserva tiempo para
auditar y publicar la parte válida aunque la descarga alcance su límite.
Los registros nuevos fechan la finalización real de la descarga; los
reutilizados conservan su timestamp y su base temporal originales.

## Holdings originales de SPY

Se recuperan el inventario oficial de presentaciones del CIK 884394 y sus
documentos originales N-PORT públicos y estados N-30D/N-CSR/N-Q pertinentes.
Los documentos HTML se conservan sin inventar holdings al no disponer de
un extractor validado de sus tablas.

Los XML N-PORT conservan pesos e identificadores originales. Un CUSIP o
nombre no se convierte en ticker usando la lista actual de empresas. Si el
documento no aporta ticker explícito, su peso queda sin mapear. Tampoco se
normalizan a 100% los pesos desconocidos ni se inventa efectivo residual.

La disponibilidad conservadora empieza **después** del mayor entre el día
de presentación y sesenta días desde la fecha de composición. Es una regla
operativa cauta para este histórico, basada en la publicación diferida de
[N-PORT](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets);
no certifica la primera hora pública ni sustituye revisar cambios normativos
si se amplía el periodo. Una composición anterior al corte no demuestra que
ya estuviera publicada. Las enmiendas posteriores no se usan antes de su fecha.

Se conserva el límite vigente de antigüedad de 120 días. La publicación
trimestral diferida puede dejar cortes sin composición admisible. No se
relaja ese límite para completar el backtest. Disponibilidad del documento,
identificadores utilizables y cobertura de anclas válidas son requisitos distintos.

## Preparación reproducible de entradas macro (fase siguiente)

El adaptador `scripts/historical_replay_inputs.py` reconstruye, exclusivamente
desde el archivo verificable, un paquete por cada uno de los 48 cierres.
Revalida todos los hashes, el cuerpo ALFRED, la versión histórica solicitada,
el conjunto de series, las fechas de disponibilidad y los metadatos de cada
puntero. Una serie ausente, corrupta o reemplazada por datos actuales provoca
un fallo explícito: no se rellenan huecos ni se permite un backtest parcial
bajo la etiqueta de replay completo.

```sh
python -m unittest tests.test_historical_replay_inputs
python scripts/historical_replay_inputs.py --output out/historical-macro-inputs-v1.json.gz
```

El paquete comprimido conserva las historias, valores disponibles, versión,
fecha original del dato, hash de la fuente, primera descarga y el hash del
manifiesto. La compresión es reproducible (mtime fijo). El workflow
`Historical provider inputs (research)` comprueba las pruebas y guarda
`historical-macro-replay-inputs` como artefacto de investigación por 90 días;
no modifica los datos de producción.

**Esto prepara solo la capa macro.** El paquete señala explícitamente
`full_model_replay_ready=false` y `predictive_validation=not-established`.
Faltan todavía el universo histórico, correspondencia verificable de CUSIP,
perfiles originales de renta fija/ETF, calidad contable, precios operables y el
recorrido de decisiones del motor completo. No se atribuye rendimiento
predictivo al archivo generado.

## Archivos y operación

```sh
python -m unittest tests.test_historical_sources
python scripts/historical_sources.py
python scripts/audit_historical_inputs.py
```

Requiere `FRED_API_KEY` y `SEC_USER_AGENT` configurados en el entorno, ya
utilizados por el colector del proyecto. No se guardan ni imprimen las claves.
El workflow `Historical provider inputs (research)` usa esos secretos en
GitHub, conserva las respuestas comprimidas y publica solo datos públicos
de investigación mediante un commit normal a `main`.

- Archivo: `data/historical/provider-inputs-v1/`.
- Estado y huecos: `manifest.json` dentro del archivo.
- Verificación y matriz por corte: `readiness.json`, reconstruida desde los
  bytes archivados. Una macro completa no convierte el corte en apto para
  todo el motor si faltan perfiles, identificadores o anclas.
- Raw y normalizado: registros comprimidos e inmutables con hash.
- Una respuesta no disponible marca la colección parcial y CI lo advierte,
  conservando las fuentes válidas. No modifica `dist/data/market.json`.

Siguen siendo necesarios los perfiles históricos de bonos/ETF, calidad y
confianza contable completas, universo/identificadores/operaciones corporativas
históricos y el recorrido del motor completo. Recuperar estas fuentes no
acredita por sí mismo el IC, la calibración del riesgo o una ventaja económica.
