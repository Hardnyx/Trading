# Pronósticos históricos ampliados a ocho cierres

**2-nov-2026. Capacidad predictiva y ventaja económica: sin acreditar.**

Se reconstruyeron pronósticos para todos los cierres con al menos 70% del
peso de SPY cubierto por historias de investigación. Se mantuvo el umbral
original: ocho de los 48 cierres cumplen la regla. Los otros cuarenta
permanecen en el calendario con su motivo de exclusión, sin relajar cobertura
ni elegir fechas según resultados o vencimientos disponibles.

El [protocolo](protocolo-validacion-ampliada-v1.json) y las distribuciones
por fecha se publicaron en `c323b81` antes de puntuarlas. Se conservan las
dos fechas originales y se añaden seis. El periodo y sus precios ya se
habían estudiado; no es una muestra independiente ni prospectiva. Las dos
primeras distribuciones y sus puntuaciones reproducen el piloto anterior;
no se suman otra vez como evidencia nueva.

## Entradas y alcance

| Cierre | Cobertura de historias antes de BPA | Acciones con BPA e historia | Acciones preseleccionadas para pronóstico |
|---|---:|---:|---:|
| 31-dic-2024 | 70,26% | 127 | 38 |
| 30-abr-2025 | 71,55% | 134 | 38 |
| 30-jun-2025 | 70,16% | 131 | 38 |
| 30-sep-2025 | 71,44% | 135 | 38 |
| 31-dic-2025 | 72,04% | 134 | 38 |
| 30-abr-2026 | 72,77% | 139 | 38 |
| 30-jun-2026 | 71,62% | 141 | 38 |
| 30-sep-2026 | 71,17% | 139 | 38 |

Se reutiliza el compilador del piloto: macro ALFRED verificada, holdings y
tickers documentados, BPA TTM presentado antes del día del corte y dividendos
pasados reexpresados bajo la hipótesis de unidades del proveedor. Se
reverifican los originales. Calidad contable ausente, perfiles de bonos/ETF,
estimaciones de analistas y GJR actuales no se introducen como sustitutos.
El reloj real de descarga se conserva; el reloj fijo de reconstrucción
identifica esta revisión de 2026 y permite reproducir los archivos.

Se ejecutan `referenceRequest`, `prepareComposition` y `generatePaths` de
producción: anclas, preselección, dependencia y EWMA dinámico. No se ejecuta
el optimizador ni se generan órdenes o una cuenta continua en los seis
orígenes nuevos. Son ocho cortes de **pronósticos de investigación**, no
ocho nuevos backtests integrales. Se conservan semilla, 2.000 trayectorias,
ley de precios, referencias y horizontes del diagnóstico previo.

El objetivo sigue siendo retorno total bruto antes de separar dividendos en
efectivo, contrastado con extremos ajustados exactos. SPY se puntúa aparte.
Los pronósticos completos, anclas y covarianzas se archivan por fecha, con
hashes en el [manifiesto](../data/historical/expanded-stock-validation-v1/manifest.json).
Las entradas completas se reconstruyen desde el corpus original y se
conservan también como artefacto CI. El kernel y los pesos publicados no cambian.

## Resultados frente a EWMA de retorno cero

La referencia mantiene la covarianza al origen, pero usa GBM gaussiano con
varianza fija, media aritmética cero, sin regímenes ni incertidumbre de anclas.
La comparación cambia varios componentes conjuntamente. No identifica alfa
incremental ni demuestra ventaja frente a un ancla económica común.

| Horizonte | Orígenes vencidos / previstos | Adicionales al piloto | Filas acción/horizonte puntuadas | Intervalos sin solapamiento temporal | CRPS menor | Brier menor | RMSE menor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 21 sesiones | 8/8 | 6 | 304 | 8 | 7/8 | 7/8 | 8/8 |
| 63 sesiones | 7/8 | 5 | 266 | 5 | 6/7 | 5/7 | 6/7 |
| 252 sesiones | 4/8 | 2 | 152 | 1 | 4/4 | 4/4 | 4/4 |

Son 722 filas correlacionadas, no 722 experimentos independientes. Los
conteos de comparaciones favorables son descriptivos y no constituyen una
tasa de acierto con significación estadística. Ausencia de solapamiento
temporal tampoco garantiza independencia económica. El conjunto anual
solo permite seleccionar un intervalo sin solapamiento de forma cronológica;
no son cuatro años independientes.

Permanecen pendientes 63 sesiones desde 30-sep-2026 y 252 sesiones desde
31-dic-2025, 30-abr/30-jun/30-sep-2026. Esos pronósticos siguen archivados con
resultados nulos; no se eliminan para mejorar el informe. En los horizontes
vencidos no hay exclusiones por extremos ausentes o ajustes documentados.
Los vencimientos se miden contra el mercado congelado del 30-oct, no contra
la fecha de esta ejecución.

## Qué sigue fallando

| Origen anual | Sesgo de la media prevista | Probabilidad media de pérdida prevista | Frecuencia de pérdida realizada | Spearman de retornos |
|---|---:|---:|---:|---:|
| 31-dic-2024 | −11,50 pp | 45,73% | 28,95% | −0,008 |
| 30-abr-2025 | −38,93 pp | 48,37% | 10,53% | 0,540 |
| 30-jun-2025 | −36,44 pp | 46,33% | 18,42% | 0,147 |
| 30-sep-2025 | −23,08 pp | 46,71% | 26,32% | 0,296 |

Sesgo = media simulada menos retorno realizado. Las medias siguen
subestimando fuertemente el resultado anual y el orden de las acciones no
es estable. La cobertura anual del intervalo central 90% va de 76,32% a
89,47%. Estos desajustes requieren más periodos y datos, sin calibrar los
parámetros sobre esta misma muestra y presentarla después como validación.

La sobreestimación de pérdidas no es uniforme: a 21 sesiones desde
30-abr-2026 la previsión media es 49,33% frente a 63,16% observado; a 63
sesiones desde 30-jun-2026, 49,55% frente a 60,53%. CRPS empeora frente a
la referencia en el primer caso y a 63 sesiones desde 31-dic-2024. Brier
también empeora en esos dos casos y a 63 sesiones desde 30-jun-2026.

## Límites y continuación

Permanecen el catálogo superviviente, la cobertura parcial, los precios y
BPA reconstruidos posteriormente, los parámetros retrospectivos y la
falta de flujos operables reconciliados. No se publican inferencias agrupadas,
intervalos de confianza de habilidad, calibración de ES/CVaR ni rendimiento
de una cuenta neta de costes. El motor completo sigue en **0/48 cortes
causales certificados**. El siguiente bloqueo es ampliar las fuentes
históricas admisibles y conciliar la riqueza con dividendos en efectivo,
operaciones corporativas y ejecución, antes de evaluar decisiones continuas.

## Reproducción

```sh
python scripts/expanded_validation_inputs.py
node scripts/expanded_stock_forecasts.mjs
node scripts/score_expanded_stock_validation.mjs --verify
node --test tests/expanded-stock-validation.test.mjs tests/expanded-stock-scores.test.mjs
```

El generador rechaza cambios materiales en archivos ya archivados. El
contraste usa el contenido JSON serializado: los campos internos `undefined`
se omiten igual que al archivar, sin convertir cambios en campos nulos o
valores numéricos en equivalentes. Se conserva y verifica el hash del
generador original desde `c323b81`; una ejecución posterior de verificación
no lo reemplaza ni reescribe las distribuciones.
El
puntuador lee distribuciones desde el commit de congelación y resultados
desde el mercado fijado; no recalcula pronósticos. La comparación entre V8
tolera solo redondeo de 1e-12, manteniendo estructura y hashes exactos. El
[informe por acción](../data/historical/expanded-stock-validation-scores-v1/report.json)
conserva también todos los horizontes pendientes y el calendario sin solapamientos.
