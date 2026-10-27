# Diagnóstico de la cartera con 15% de efectivo

## Origen reproducido

Captura de mercado del 27 de octubre de 2026 a las 18:05:03 UTC, precios al
26 de octubre, commit de datos `1c7963e`. Semilla 20261024, 40 activos
simulados, capital inicial USD 100.000, seis posiciones como máximo y
correlación máxima 0,85. Se emplean los cuatro escenarios y los límites
predeterminados restantes: Treasuries 60%, instrumento 35%, acción 20%,
CVaR 20%, efectivo mínimo 5%, sin retiros y efectivo sin remuneración.

La reproducción con `referenceRequest(snapshot)` y los cambios
`{maxPositions: 6, maxCorrelation: 0.85}` en los límites produce exactamente
los pesos y las cifras de la captura. La cuenta y los supuestos del usuario
no se restablecen para corregir la búsqueda.

## Por qué aparece esta mezcla

- TLT aporta una ancla de carry del 5,21% y exposición a los escenarios de
  tasas; alcanza el tope de 35% por instrumento.
- SGOV y SHV aportan carry del 3,94% y 4,02%, con menor duración. Los tres
  ETF agotan juntos el límite de Treasuries del 60%.
- AMZN y HPQ tienen anclas de 10,94% y 9,84%. Dependen de crecimiento de
  BPA supuesto del 12% y 6%, reversión parcial de múltiplos y, para HPQ,
  dividendos. No son previsiones calibradas.
- El máximo de seis posiciones incluye CASH. Con la reserva mínima quedan
  cinco posiciones para instrumentos; los topes y la correlación limitan las
  combinaciones. El universo publicado de 260 instrumentos no equivale a 260
  alternativas comprables: se simula una muestra de 40 y solo seis ETF tienen
  ancla de renta fija utilizable; el resto requiere más evidencia o supuestos
  explícitos.

Estas condiciones delimitan la selección, pero **no justificaban todo el
15% de efectivo**. La reserva exigida era 5%. La búsqueda aleatoria y sus
ajustes locales habían omitido transferencias factibles a posiciones ya
seleccionadas.

## Corrección de la búsqueda

La revisión sistemática añade 5 puntos a AMZN y luego 5 puntos a HPQ,
descontándolos de CASH. Respeta los mismos límites, posiciones máximas,
costes y escenarios. No cambia supuestos de retorno ni reduce restricciones.

| Activo | Antes | Tras la revisión local |
|---|---:|---:|
| TLT | 35% | 35% |
| SGOV | 10% | 10% |
| SHV | 15% | 15% |
| AMZN | 15% | 20% |
| HPQ | 10% | 15% |
| CASH | 15% | 5% |

| Métrica simulada | Antes | Tras la revisión local |
|---|---:|---:|
| Retorno medio | 3,94% | 4,26% |
| Retorno mediano | 3,82% | 3,58% |
| Probabilidad de pérdida | 33,57% | 36,40% |
| CVaR95 | 14,49% | 17,90% |
| Crecimiento logarítmico esperado | 3,442% | 3,522% |
| Equivalente cierto sobre USD 100.000 | USD 103.502,18 | USD 103.584,68 |

Se maximiza el crecimiento logarítmico esperado. La corrección mejora ese
criterio en esta simulación, aunque reduce la mediana y aumenta el riesgo.
La diferencia equivalente de USD 82,49 es pequeña y está sujeta al error de
Monte Carlo, la incertidumbre de parámetros y la selección de candidatas.
No demuestra que la cartera corregida obtenga mejores resultados reales.

La revisión usa los mismos escenarios finales que la selección. No es una
prueba independiente ni garantiza optimalidad global; la convergencia entre
muestras y semillas sigue pendiente. El algoritmo evalúa tramos de 5 y 10
puntos, hasta cuatro rondas, y registra si se detuvo por reserva mínima,
restricciones, falta de mejora local o presupuesto de búsqueda.
