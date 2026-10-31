# Precios históricos: contraste de unidades y entradas de investigación

## Medición del 31-oct-2026

El [reporte por cierre](../data/historical/price-reconciliation-v1/coverage.md)
contrasta el mercado congelado del estudio con las posiciones originales de
SPY y los identificadores históricos ya recuperados.

| Medida | Resultado | Alcance |
|---|---:|---|
| Cierres programados | 48 | Se conservan los bloqueados y sus exclusiones |
| Cierres con contraste puntual compatible | 10 | Dos de los doce cortes con tickers no tienen una fila de precios en la fecha exacta de cartera |
| Comparaciones puntuales compatibles | 1.442 | Combinaciones activo/cierre, con fechas de referencia repetidas; no son pruebas independientes |
| Historias reconstruidas para investigación | 1.424 en 10 cierres | Entre 252 y 500 intervalos de retorno por historia; no son 1.424 predicciones |
| Peso de SPY con historia reconstruida | 66,35%–72,77% en los diez cierres | El resto permanece excluido, sin renormalizar |
| Casos bloqueados por ajustes posteriores distintos de splits | 60 | Clasificaciones del proveedor pendientes de contrastar con originales del emisor |
| Cierres certificados para el motor completo | 0 | Faltan identidad continua, eventos, flujos, fundamentales, perfiles y parámetros causales |

El [JSON compacto](../data/historical/price-reconciliation-v1/coverage.json)
incluye hashes, inventario de eventos pendientes y conteos por causa. Las
comparaciones por posición están en `points.json.gz` en ese directorio.
Los archivos `out/historical-common-unit-histories-v1.json.gz`, generados por
el comando y conservados como artefacto CI, contienen las historias por fecha.

## Contraste antes de interpretar un precio histórico

El [protocolo v1](protocolo-precios-historicos-v1.json) fija el mercado exacto,
el enlace de símbolos y la tolerancia antes de utilizar resultados del modelo.
Se usa el ticker literal del documento. No se convierten signos ni se empatan
nombres. Si un ticker apunta a varios CUSIP en el mismo cierre, queda bloqueado.

La referencia es el valor razonable USD dividido por acciones de una posición
larga, común, con unidades NS y nivel 1 del N-PORT de SPY. Esa marca por acción
es una referencia contable del fondo, **no una cotización de cierre certificada**.
La [instrucción oficial del formulario](https://www.sec.gov/investment/new-form-n-port)
describe la cantidad, su unidad y la valoración declarada para la cartera.

La columna `close` de Yahoo ya incorpora splits; `adj_close` incorpora además
distribuciones, según la [página histórica del proveedor](https://finance.yahoo.com/quote/NVDA/history/).
Por eso el contraste de nivel utiliza `close` y revierte mecánicamente los
splits declarados posteriores a la fecha de referencia. No suma dividendos
ni trata `adj_close` como precio de compra. La tolerancia fija es el mayor
entre USD 0,01 y un punto básico de la marca por acción; no se ajusta para
aceptar casos individuales.

Se exige la fecha exacta. Un N-PORT con fecha de fin de semana no se compara
automáticamente con el viernes anterior. Tampoco se promedian posiciones
duplicadas o se interpreta un contrato, deuda, moneda distinta de USD o una
valoración de nivel 2/3 como una cotización ordinaria de acciones.

## Base común de acciones al origen

Para una historia terminada en un cierre, se multiplica toda la serie previa
por el mismo producto de ratios de splits posteriores a ese cierre. Esto
restaura niveles en unidades de acciones de ese origen y conserva los cocientes
de precios y retornos. Se comprueba tanto para splits como reverse splits y
su composición. No se incluyen filas de precios posteriores al cierre.
La columna `adj_close` conserva un índice de retorno total del proveedor;
su nivel puede incluir ajustes posteriores por distribuciones. Se utiliza
como índice para cocientes, no como un precio o una versión original del dato.

Esta inversión es **ex post**: utiliza metadatos de eventos posteriores para
retirar ajustes que el proveedor incorporó después. No significa que Trading
hubiera capturado esa serie entonces. Las clasificaciones del proveedor siguen
siendo hipótesis hasta reconciliar eventos originales del emisor. Una marca
compatible en un día no acredita toda la historia ni continuidad del símbolo.

Los ajustes identificados como distintos de un split bloquean la inversión
de niveles si son posteriores a la referencia; también bloquean la historia
de entrenamiento si afectan su ventana o su base posterior. El inventario
conserva las fechas y ratios declarados sin certificarlos como eventos reales.

## Uso y límites

```sh
python -m unittest tests.test_historical_price_audit
python scripts/historical_price_audit.py
python scripts/historical_replay_plan.py
```

La ejecución automática de `Historical provider inputs (research)` ahora
encadena recuperación, identificadores y contraste de precios en un único
trabajo. Esto evita que varias publicaciones automáticas compitan por la
matriz. Conserva el artefacto `historical-share-unit-research` por 90 días.
Los workflows de identificadores y de precios también admiten ejecución manual.

La muestra de precios sigue siendo el catálogo congelado actual, con sesgo
de selección y supervivencia. Se excluyen instrumentos históricos ausentes;
no se cambian por supervivientes. Las historias resultantes están marcadas
como investigación y no certifican precios ejecutables, dividendos cobrados,
escisiones, deslistados, parámetros causales ni validez predictiva. La matriz
del replay completo mantiene todas sus barreras y pronósticos/órdenes nulos.
