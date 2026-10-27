# Revisión del repositorio y de la propuesta · 27 de octubre de 2026

Referencia revisada: `a138878`, motor **0.24.0**, captura
`2026-10-27T22:05:04.366914+00:00`, precios al **27 de octubre**.
La captura con TLT 35%, AMZN 20% y HPQ 15% corresponde al motor 0.20.0 y a
precios del 26 de octubre; ya no describe esta versión.

## Resultado reproducido

`referenceRequest` con `maxPositions: 6`, `maxCorrelation: 0.85`, semilla
20261024, capital USD 100.000 y los demás parámetros predeterminados:

| Activo | Peso |
|---|---:|
| IGSB | 35% |
| NVDA | 20% |
| PGR | 20% |
| SHV | 10% |
| CI | 10% |
| CASH | 5% |

Media simulada 7,08%; mediana 5,87%; CVaR95 12,91%; probabilidad de pérdida
29,03%; equivalente cierto USD 106.443,52. Se cumplen los límites del caso.
El efectivo coincide con la reserva mínima. Son resultados condicionales al
modelo, no retornos realizados ni validación económica.

## Hallazgos abiertos

### 1. La búsqueda omite una sustitución factible que mejora su propio objetivo

Se enumeraron intercambios de 5 puntos y sustituciones completas de una
posición hacia otro instrumento de la misma muestra de 40. Se comprobaron
pesos, composición, costes, tamaño mínimo de operación, CVaR, probabilidad de
pérdida, drawdown y liquidez. El caso no tiene suelo de capital ni retiros.
Entre 88 vecinas factibles, sustituir CI 10% por NFLX 10% mejora el objetivo
sobre los mismos 3.000 escenarios finales, sin cambiar los otros pesos:

| Métrica | Seleccionada | Sustitución CI → NFLX |
|---|---:|---:|
| Equivalente cierto | USD 106.443,52 | USD 106.668,49 |
| Mediana | 5,87% | 6,25% |
| CVaR95 | 12,91% | 12,81% |
| Probabilidad de pérdida | 29,03% | 27,70% |

Las carteras se fijaron antes de comprobarlas en dos muestras nuevas de
3.000 trayectorias cada una:

| Semilla nueva | Mejora equivalente | CVaR seleccionada | CVaR sustitución |
|---|---:|---:|---:|
| 20261028 | USD 259,96 | 13,00% | 12,36% |
| 20261029 | USD 275,07 | 13,11% | 12,42% |

Diferencias pareadas de utilidad logarítmica: 0,002442 y 0,002581; errores
estándar 0,000741 y 0,000731. Los intervalos normales del 95% quedan por
encima de cero en ambas muestras. Esto mide error de Monte Carlo con el
**mismo modelo y datos**, no error de parámetros ni capacidad predictiva
histórica. La sustitución es un contraejemplo a la optimalidad de la
búsqueda, no una recomendación de compra ni un óptimo global. La revisión
desde CASH no cubre sustituciones cuando CASH ya está en su mínimo.
Permanece abierto el pendiente 20.

### 2. El centrado macro solo conserva la media terminal a un año

`centeredRegimeConditions` resta `log(sum(p * exp(c)))` a la condición
anual. La simulación acumula esa condición durante `H` años. Centrar
`exp(c)` no centra `exp(H*c)` cuando `H` difiere de uno.

Con los escenarios predeterminados y crecimiento de BPA del 12%, el
multiplicador esperado de patrimonio atribuible **solo** a escenarios es
0,991240 a tres meses, 1 a un año, 1,003844 a dos años y 1,016724 a cinco
años. Se excluyen difusión e incertidumbre del ancla en esta identidad;
la desviación no procede del muestreo. A un año, 0.23.0 sí cumple su
objetivo. Para preservar la media al horizonte se necesita normalizar con
`log(sum(p * exp(H*c))) / H` y verificar todos los horizontes admitidos.
El motor revisado aún utiliza la otra expresión.

### 3. La nueva ancla de holdings no exige primera observación al corte

`holdingsAnchor` comprueba fecha económica, antigüedad y cobertura, pero no
`observed_at`, duplicados ni los mismos controles que `actualHoldings`.
Un caso con cartera fechada el 23-oct, observada por primera vez el 28-oct,
recibe ancla al solicitar información al 26-oct; el módulo de exposición
rechaza correctamente la misma cartera. También se admite ausencia de
primera observación. Hay que compartir un validador temporal y estructural.

Esto demuestra una vía de filtración en reconstrucciones o importaciones;
no demuestra que la propuesta corriente haya utilizado información futura.
Se mantiene además el pendiente de gastos de ETF: no se descuentan de sus
nuevas anclas de renta variable.

## Estado general

0.21.0 incorpora reversión de varianza a horizonte; 0.22.0 habilita anclas
compuestas para 15 ETF; 0.23.0 centra incertidumbre y escenarios a un año e
incorpora AGG, LQD e IGSB; 0.24.0 concilia la ficha de bonos con la función
de escenarios de la simulación. Son avances reales frente a la captura.

Permanecen sin calibrar crecimiento, múltiplos, confianza y probabilidades
macro. Las nuevas anclas de ETF heredan esa incertidumbre, y las pérdidas
esperadas de crédito son convenciones. La validación prospectiva de retorno
y del CVaR exacto sigue pendiente. El estado adecuado continúa siendo
**investigación experimental**, con defectos concretos de búsqueda y
consistencia todavía abiertos.

Comprobaciones locales: **193 pruebas JavaScript**, **126 Python** y
`npm run check` aprobados. En `a138878`, validación, navegador y despliegue
de GitHub Actions también finalizaron correctamente. Los casos adversariales
anteriores no estaban cubiertos por esas pruebas. Esta revisión documenta
hallazgos; no modifica el motor.

## Seguimiento

Los hallazgos 2 y 3 se cierran en 0.26.0 (véase el
[estado consolidado](estado-validacion.md)). El hallazgo 1 sigue abierto en
el pendiente 20. Desde 0.25.0 las anclas de acciones cambian, así que la
cartera reproducida arriba describe solo 0.24.0.
