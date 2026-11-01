# Primer contraste de anclas del piloto con resultados posteriores

**1-nov-2026. Capacidad predictiva y ventaja económica: sin acreditar.**

Se puntuaron las anclas archivadas sin ejecutar de nuevo el compositor ni
cambiar sus supuestos. El [protocolo](protocolo-puntuacion-piloto-v1.json)
se publicó en `abd84b6` antes del cálculo. El periodo ya se había estudiado
y los precios estaban disponibles: no es un holdout independiente ni un
prerregistro prospectivo.

## Muestra y medición

Se conservaron ambos orígenes y las 38 acciones preseleccionadas en cada uno.
Los vencimientos comunes son 31-dic-2025 y 30-abr-2026: primera sesión de
SPY en o después del aniversario anual. Las 76 filas tienen extremos
exactos; no hubo exclusiones al puntuar. Se archivan también las reglas
para faltantes y ajustes corporativos, sin desplazar fechas por activo.

El predictor `annual` es la localización del ancla archivada, **no la media
ni la mediana incondicional de riqueza simulada**. Se contrasta con el
cociente de cierres ajustados menos uno: proxy bruto de retorno total con
reinversión. No concilia cobros, impuestos, ejecución ni dividendos en
efectivo. Es un diagnóstico de anclas, no una validación de la distribución
final del simulador.

Los comparadores usan las mismas filas: retorno cero y el ancla común de
SPY ya archivada (7,81% y 7,82%). Esta última es una convención económica;
no utiliza el retorno futuro de SPY.

| Origen | Acciones | MAE anclas | MAE cero | MAE ancla común SPY | Sesgo anclas | Spearman |
|---|---:|---:|---:|---:|---:|---:|
| 31-dic-2024 | 38 | 19,86 pp | 21,31 pp | 19,71 pp | −9,45 pp | 0,148 |
| 30-abr-2025 | 38 | 46,54 pp | 51,46 pp | 45,49 pp | −41,16 pp | 0,542 |

MAE: error absoluto medio. Sesgo: pronóstico menos realización. RMSE de
anclas frente al ancla común: 26,68/26,14 pp y 67,71/67,21 pp.

Las anclas específicas mejoran al comparador cero, pero **no mejoran el
MAE ni el RMSE del ancla común**. Subestiman los retornos en promedio.
El orden de las acciones tiene asociación positiva, especialmente en el
segundo corte; eso no acredita calibración del nivel ni habilidad estable.
No se ajustan los parámetros para encajar estas realizaciones.

## Efectivo y controles

En cada origen hay 23 finalistas: CASH y 22 alternativas. Solo CASH figura
como factible y hay cero transiciones admisibles. Las 22 alternativas
tienen cota inferior de ganancia superior al umbral de USD 100, pero no
son factibles. La falta de una mejora positiva no explica por sí sola el
efectivo; el archivo no guarda las causas por modelo de cada rechazo.

La confirmación final compara **CASH con CASH** después del retorno a la
cuenta inicial. Sus ganancias nulas no describen las inversiones rechazadas.
Queda pendiente reproducir y guardar la atribución de restricciones por
finalista. SPY era una referencia sin permiso de compra.

El efectivo al 0% declarado produce 0% por definición. Una referencia
hipotética mantenida de 35% SPY / 65% CASH produce aproximadamente 6,20%
y 10,88% bruto en los mismos extremos ajustados. No está conciliada con
costes y flujos, no certifica riesgo equivalente y SPY no era comprable por
el piloto. No demuestra que los rechazos fueran erróneos ni constituye un
backtest económico neto. Las cuentas de cada origen son independientes.

## Límites y continuación

Los dos años se solapan y las acciones están correlacionadas. No hay 76
experimentos independientes. No se agrupan para inferencia ni se calculan
p-valores o intervalos de confianza. La preselección tampoco representa
todas las 127/134 acciones disponibles. Persisten catálogo superviviente,
parámetros actuales, BPA y precios reconstruidos posteriormente y EWMA.

`low` y `high` son rangos de parámetros, **no P05/P95**. No se puntúan como
intervalos predictivos. No se validan probabilidad de pérdida, CVaR, GJR ni
calibración anual. Permanecen **0/48 cortes causales certificados**.

El siguiente cierre requiere realización de flujos compatible con la
distribución simulada, atribución de rechazos y más orígenes con datos
históricos suficientes. Después debe contrastarse una cuenta continua neta
de costes. Los registros prospectivos deben madurar conservando sus sellos.

## Reproducción

```sh
node scripts/score_scoped_pilot.mjs
node --test tests/scoped-pilot-outcomes.test.mjs
```

El ejecutor usa `git show b2d1532:dist/data/market.json`, independientemente
de actualizaciones posteriores del mercado. Requiere ese objeto en el clon.
Verifica los hashes publicados de entradas y resultados del piloto. El
[informe por acción](../data/historical/scoped-pilot-outcomes-v1/report.json)
conserva anclas, extremos, exclusiones y hashes de mercado, protocolo,
cohorte y ejecutor. No modifica los archivos del piloto original.
