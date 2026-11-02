# Contraste de distribuciones del piloto histórico

**2-nov-2026. Capacidad predictiva y ventaja económica: sin acreditar.**

Se reconstruyeron las distribuciones de retorno total implícitas en el
núcleo del piloto con sus entradas originales y los mismos módulos de
producción. Se archivaron junto con el
[protocolo](protocolo-distribuciones-piloto-v1.json) en `d79d3e4`, antes de
ejecutar el puntuador. El periodo y los precios ya se habían examinado:
esto no constituye una prueba independiente ni un prerregistro prospectivo.

## Muestra y definición

Se conservan los dos orígenes, las 38 acciones preseleccionadas por fecha y
SPY por separado. Se evalúan 21, 63 y 252 sesiones desde el cierre original,
sin mover extremos por instrumento. Las 228 filas acción/horizonte tienen
extremos exactos, sin exclusiones. No son 228 experimentos independientes.
Los vencimientos son 3-feb/3-abr-2025 y 5-ene-2026 para diciembre, y
30-may/31-jul-2025 y 1-may-2026 para abril. Difieren de los aniversarios
calendario del primer diagnóstico de anclas.

Cada distribución utiliza 2.000 trayectorias diarias, semilla 20261102 y el
horizonte anual original; los horizontes cortos son prefijos de esas mismas
trayectorias. No son las trayectorias semanales originales de selección de
carteras ni pronósticos emitidos en 2024/2025. La variante conserva EWMA,
las anclas, la incertidumbre de parámetros y los regímenes del piloto;
no incorpora el GJR actual ni altera el kernel 1.0.0.

Se contrasta el proceso de retorno total bruto **antes de separar dividendos
en efectivo**, contra cocientes de cierres ajustados del mercado congelado
en `b2d1532`. Es compatible con un proxy de reinversión bruta; no realiza
flujos de efectivo, retenciones, costes ni precios ejecutables. La cartera
del piloto usaba dividendos en efectivo: este contraste no valida su riqueza
terminal ni sus decisiones. El resultado CASH no entra en las métricas de
acciones ni SPY se mezcla con ellas.

La referencia usa la misma covarianza EWMA al origen, retorno aritmético
esperado cero, varianza fija y GBM gaussiano, sin incertidumbre de anclas o
regímenes. Cambia varios componentes a la vez. Superarla no identifica qué
componente aporta valor ni demuestra ventaja frente a un pronóstico
económico común, como el ancla SPY del primer diagnóstico.

## Resultados descriptivos

CRPS mide el error de la distribución completa mediante una cuadrícula de
100 cuantiles. Brier mide el error de la probabilidad de retorno negativo.
En ambos, menor es mejor. RMSE y sesgo se refieren a la **media simulada**,
no al parámetro `annual` del ancla; sesgo = pronóstico menos realización.
La cobertura es la proporción de acciones dentro del intervalo central 90%.

| Origen | Sesiones | CRPS modelo / EWMA | Brier modelo / EWMA | RMSE modelo / EWMA | Cobertura 90% modelo / EWMA |
|---|---:|---:|---:|---:|---:|
| 31-dic-2024 | 21 | 0,0484 / 0,0502 | 0,2393 / 0,2527 | 8,72 / 8,94 pp | 78,9% / 78,9% |
| 31-dic-2024 | 63 | 0,0832 / 0,0819 | 0,2540 / 0,2468 | 15,01 / 14,51 pp | 84,2% / 76,3% |
| 31-dic-2024 | 252 | 0,1655 / 0,1826 | 0,2379 / 0,2753 | 29,86 / 33,11 pp | 89,5% / 73,7% |
| 30-abr-2025 | 21 | 0,0473 / 0,0486 | 0,2517 / 0,2559 | 8,32 / 8,57 pp | 100,0% / 100,0% |
| 30-abr-2025 | 63 | 0,1091 / 0,1153 | 0,2568 / 0,2775 | 20,35 / 21,21 pp | 94,7% / 97,4% |
| 30-abr-2025 | 252 | 0,3605 / 0,4050 | 0,2420 / 0,3292 | 65,94 / 71,51 pp | 86,8% / 86,8% |

El modelo mejora CRPS, Brier y RMSE en cinco de las seis combinaciones.
Empeora a 63 sesiones desde diciembre. Esa cuenta es descriptiva: no es
una tasa de éxito independiente ni una prueba estadística de superioridad.

Las medias anuales subestiman la realización en **11,50 y 38,93 pp**. La
asociación de rangos anual es aproximadamente −0,008 y 0,540: no hay una
capacidad de ordenación estable en ambos cortes. No contradice el primer
diagnóstico: aquí cambian predictor, extremos y referencia.

La probabilidad media de pérdida anual prevista es **45,73% y 48,37%**,
frente a frecuencias realizadas de **28,95% y 10,53%**. En los seis grupos
la probabilidad media prevista supera a la frecuencia observada. Esto
señala un desajuste en esta muestra, sin permitir concluir cómo se comporta
la calibración condicional en otros periodos. El informe conserva también
excepciones del cuantil inferior y residuos ES; dos orígenes y pocas
observaciones de cola no validan VaR, ES o CVaR anual de cartera.

## Alcance y continuación

Se avanza desde puntuar parámetros de anclaje a puntuar distribuciones,
probabilidades e intervalos con una referencia explícita y muestras iguales.
Persisten catálogo superviviente, reconstrucción posterior de precios/BPA,
parámetros retrospectivos y selección parcial. Las ventanas anuales se
solapan y las acciones están correlacionadas. No se agrupan para inferencia,
no se calculan p-valores y no se calibran parámetros con estos resultados.

Permanecen **0/48 cortes causales certificados**. Falta completar los datos
para más orígenes, conciliar los dividendos en efectivo y otras operaciones
corporativas y evaluar una cuenta continua neta de costes bajo el mismo
mandato. El seguimiento prospectivo debe madurar sin sustituir sellos.

## Reproducción

```sh
node scripts/scoped_pilot_distributions.mjs
node scripts/score_scoped_distributions.mjs --verify
node --test tests/scoped-pilot-distributions.test.mjs tests/scoped-distribution-scores.test.mjs
```

El generador verifica el código original, las anclas y la covarianza;
rechaza sustituir una distribución archivada diferente. El puntuador lee
pronósticos y protocolo desde el commit de congelación, sin recalcularlos,
y precios desde el commit de mercado fijado. El
[informe por acción](../data/historical/scoped-pilot-distribution-scores-v1/report.json)
guarda todos los extremos, exclusiones, métricas y hashes. La reproducción
entre versiones de V8 admite solo redondeo numérico de 1e-12; estructura,
decisiones y hashes deben coincidir exactamente.
