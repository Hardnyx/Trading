# Primeras realizaciones históricas con dividendos en efectivo

**2-nov-2026. Capacidad predictiva y ventaja económica: sin acreditar.**

Se incorporan catorce eventos de Pfizer y Microsoft a una capa separada de
resultados realizados. No se introducen esos pagos posteriores en snapshots
históricos ni se modifican pronósticos, anclas, semillas o pesos. El objetivo
es reconstruir riqueza con dividendos en efectivo, que no equivale al
cociente de cierres ajustados con reinversión utilizado hasta ahora.

## Fuentes conservadas

| Emisor | Eventos en la ventana | Fuente | Evidencia preservada |
|---|---:|---|---|
| Pfizer, PFE | 7 | [Tabla oficial](https://investors.pfizer.com/Investors/stock-dividend/dividend-split-history/default.aspx) | Extracto factual de ex-date, record date, pago e importe obtenido mediante recuperación web; no son los bytes originales del HTML |
| Microsoft, MSFT | 7 | [Archivo enlazado por Relaciones con Inversionistas](https://www.microsoft.com/en-us/Investor/dividends-and-stock-history) | XLSX original descargado, con anuncio, ex-date, record date, pago e importe |

El [manifiesto](../data/historical/issuer-cashflows-v1/manifest.json) conserva
URLs, fecha de recuperación/archivo, tipo de representación y hashes. No se
equipara la evidencia de un extracto con la del archivo original. El contenido
normalizado se regenera desde esos archivos: encabezados cambiados, importes
no finitos, fechas imposibles, duplicados o hashes distintos provocan fallo.
El lector XLSX rechaza fechas con otra época de Excel y fórmulas en las celdas
de hechos. Solo se normaliza la ventana 2025 a 30-oct-2026; no se declara
soporte para combinar antiguos dividendos regulares/especiales con igual ex-date.

Los datos se recuperaron en noviembre de 2026 para medir resultados, no
como prueba de información conocida en el origen. `outcome_only=true` y
`forecast_input_eligible=false` impiden confundir ambos usos. La ausencia de
un importe o fecha de pago nunca se rellena con una periodicidad supuesta.

La prioridad de recuperación se calcula por filas bloqueadas y después por
ticker, sin usar retornos. La disponibilidad de fuentes puede cambiar el
orden de descarga. Pfizer encabezaba la lista y su tabla fue recuperable;
Microsoft ofrece un archivo original. PNC y Lowe's siguen pendientes: no se
reemplaza una tabla dinámica no recuperada con fechas inferidas de comunicados
que solo indican record date y pago. El informe publica la cola completa.

## Resultado medido

Se recorren las mismas ocho fechas y acciones del estudio ampliado. La
política conserva dividendos en efectivo, rendimiento del efectivo 0% y
retención supuesta 0%. No acredita que una cuenta real esté exenta de impuestos.
El origen y vencimiento son los cierres exactos registrados. Una distribución
exdividendo ya devengada, pero aún sin pagar al vencimiento, se mantiene como
cuenta por cobrar: no se trata como efectivo disponible para retirar.

| Horizonte | Filas vencidas | Reconstruibles antes | Reconstruibles después | Adicionales | Aún bloqueadas |
|---|---:|---:|---:|---:|---:|
| 21 sesiones | 304 | 226 | 234 | 8 | 70 |
| 63 sesiones | 266 | 21 | 35 | 14 | 231 |
| 252 sesiones | 152 | 6 | 14 | 8 | 138 |
| Total | 722 | 253 | 283 | 30 | 439 |

Otras 190 filas continúan pendientes de vencimiento en el mercado congelado;
no se excluyen del archivo. Las filas comparten acciones y eventos y no son
experimentos independientes. Muchas de las 253 filas anteriores no tenían
dividendos dentro del intervalo: se admiten solo con índice exdividendo
completo y cocientes ajustados/no ajustados compatibles. No se les atribuyen
pagos certificados de un emisor por tener cero eventos en el proveedor.

Los importes y ex-dates se comparan exactamente con el índice del proveedor,
sin desplazar eventos. Se conservan los controles existentes de splits y
otros ajustes corporativos posteriores: no se desbloquean instrumentos
con unidades o eventos pendientes de conciliación.

Para Pfizer, las diferencias anuales entre riqueza con efectivo y el proxy
ajustado son −0,38, −0,78, +0,21 y −0,99 pp en las cuatro fechas vencidas.
Para Microsoft son −0,02, +0,08, +0,10 y −0,11 pp. Estas diferencias muestran
por qué no deben intercambiarse las dos realizaciones; no prueban que una
política sea superior ni convierten el índice ajustado en un estado de cuenta.

## Alcance y continuación

No se puntúan los pronósticos brutos ya archivados contra estas nuevas
realizaciones de efectivo: sus objetivos son distintos. Faltan distribuciones
de riqueza compatibles con esa política y una cuenta continua con flujos,
costes y operaciones corporativas completas. No se certifican precios de
ejecución, identidad continua del instrumento, vintages originales ni la
integridad total de eventos por comparar dos fuentes parciales.

Las 439 filas bloqueadas conservan la causa y los ex-dates/importes pendientes,
sin inventar fechas de pago. La cola siguiente empieza por PNC (17 filas),
Lowe's (15), EOG (14), Duke y UPS (13 cada una). Permanecen **0/48 cortes
causales certificados** y la capacidad predictiva sigue sin acreditar.

## Reproducción

```sh
python scripts/issuer_cashflow_inputs.py
node scripts/audit_historical_cashflows.mjs --verify
python -m unittest tests.test_issuer_cashflow_inputs
node --test tests/historical-cashflows.test.mjs
```

La ejecución no descarga datos nuevos: usa las fuentes preservadas,
precios de `b2d1532` y filas del estudio congeladas en `39ff3b2`. Los
pronósticos previos permanecen intactos. El
[informe por fila y cola de recuperación](../data/historical/cashflow-reconciliation-v1/report.json)
incluye riqueza, efectivo, cuentas por cobrar, fuentes y hashes, sin afirmar
validez predictiva o rentabilidad de una estrategia.
