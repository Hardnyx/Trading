# Registro del diagnóstico independiente fixed-b v1

**Hito:** H0.3. **Fecha de registro:** 14-nov-2026 UTC. **Código base:** `b2e8faf31bd1`.

Este documento fija **antes de implementar y ejecutar el evaluador** el método, los dos brazos, la distribución de referencia, la rejilla de 64 escenarios, las semillas y el criterio de incertidumbre. El contrato legible por máquina es [estudio-calibracion-fixed-b-v1.json](estudio-calibracion-fixed-b-v1.json). Los retornos de Trading, el periodo de desarrollo ya examinado y las simulaciones anteriores quedan excluidos.

## Por qué este candidato

El [diagnóstico HAC registrado](registro-diagnostico-hac.md) mostró exceso de error familiar en 43/64 escenarios con el estadístico de Bartlett, rezago 12 y **cola normal asintótica**. Esa distorsión de tamaño en muestras finitas es el problema para el que se desarrollaron las asintóticas *fixed-b*. Mantienen fija la razón `b = M/n` entre ancho de banda y muestra y sustituyen la normal por el límite no estándar del mismo estadístico. La elección proviene de la literatura y se declara antes de evaluar; no se derivó de las frecuencias observadas en el estudio HAC, cuyo registro prohibía probar rezagos alternativos por inspección.

## Dos brazos, ambos informados

- **A · fixed-b con rezago 12:** el mismo estadístico que falló, con `b = 12/n` (0,125 a 96 meses; 0,0625 a 192). Solo cambia la distribución de referencia, de modo que aísla si el fallo provenía de la cola normal.
- **B · KVB, ancho de banda completo:** Bartlett con `M = n-1` y pesos `1-k/n`, es decir `b = 1` (Kiefer, Vogelsang y Bunzel). Es la variante más robusta a la persistencia y la de menor potencia esperada.

Ambos brazos se informan cualquiera sea su resultado. **No se selecciona un brazo, un ancho de banda ni una familia de innovaciones según los resultados**, y ninguno queda aprobado para inferencia con datos de mercado.

## Distribución de referencia

Para cada `b` se simula una vez el mismo estadístico sobre 100.000 series gaussianas independientes de 1.200 meses, con `M = 150`, `75` y `1.199` rezagos. La semilla de referencia, `20261115`, es independiente de la de evaluación. El valor p unilateral es `(1 + #{referencia ≥ estadístico}) / (1 + 100.000)`. Una varianza de largo plazo no positiva o no finita produce `p = 1`, nunca un rechazo.

## Evaluación sin selección posterior

Se reutiliza sin cambios el generador sintético del estudio HAC: 96/192 meses, AR(1) 0/0,3/0,6/0,85, correlación transversal 0/0,75, innovaciones gaussianas o Student-t5 estandarizadas, siete nulos verdaderos o cuatro verdaderos y tres desplazados en +0,5 DT. Son **512 réplicas por escenario**, con 256 meses de calentamiento y una **semilla nueva, `20261114`**. Ambos brazos se evalúan sobre las mismas series de cada escenario. Se aplica Holm completo sobre la familia de siete pruebas de v2.

La medida es la frecuencia de al menos un falso rechazo **familiar**. La incertidumbre se acota con Clopper-Pearson exacto bilateral y Bonferroni sobre **128 intervalos** (64 escenarios × 2 brazos); el presupuesto por cola es `0,05/(2·128)`. Una cota inferior superior al 5 % en un brazo equivale a evidencia de exceso en esa rejilla. Que todas las cotas superiores de un brazo queden por debajo del 5 % **no** certificaría control universal ni aplicación válida a rendimientos reales. Las réplicas con rechazo de alguna hipótesis desplazada se informan solo como diagnóstico descriptivo de potencia.

## Límites

La rejilla no cubre cambios estructurales, volatilidad condicional, dependencia adversarial, pérdidas sin varianza finita, meses faltantes ni la coherencia de la cuenta de Trading. Holm requiere valores p marginales válidos y no repara un estadístico mal calibrado. Cualquier uso posterior exige justificar supuestos, potencia y valor económico, y publicar **otro registro antes de la nueva cohorte de observaciones**, sin modificar ni reinterpretar v2.

## Referencias

- Kiefer, N. M., Vogelsang, T. J. y Bunzel, H. (2000), *Simple Robust Testing of Regression Hypotheses*, Econometrica 68(3), 695–714: https://doi.org/10.1111/1468-0262.00128
- Kiefer, N. M. y Vogelsang, T. J. (2005), *A New Asymptotic Theory for Heteroskedasticity-Autocorrelation Robust Tests*, Econometric Theory 21(6), 1130–1164: https://doi.org/10.1017/S0266466605050565
- Sun, Y., Phillips, P. C. B. y Jin, S. (2008), *Optimal Bandwidth Selection in Heteroskedasticity-Autocorrelation Robust Testing*, Econometrica 76(1), 175–194: https://doi.org/10.1111/j.0012-9682.2008.00822.x
