# Datos fechados para reconstruir el motor completo

Protocolo `historical-provider-inputs-v1`. Recuperación de datos públicos
para los 48 cierres mensuales del estudio congelado, octubre de 2022 a
septiembre de 2026. No ejecuta el optimizador ni cambia el modelo publicado.

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
