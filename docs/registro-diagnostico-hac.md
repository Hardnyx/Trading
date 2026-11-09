# Registro del diagnóstico independiente HAC v1

**Hito:** H0.3. **Fecha de registro:** 9-nov-2026 UTC. **Código base:** `ef0899c93519`.

Este documento fija **antes de ejecutar sus nuevas simulaciones** el método, la rejilla de 64 escenarios, la semilla, la muestra por escenario y el criterio de incertidumbre del diagnóstico. El contrato legible por máquina es [estudio-calibracion-hac-v1.json](estudio-calibracion-hac-v1.json). El periodo de desarrollo ya examinado, las simulaciones bootstrap anteriores y todos los retornos de Trading quedan excluidos de esta evaluación.

## Método bajo examen

La única variante candidata es el estadístico unilateral de la media con varianza de largo plazo Bartlett/Newey-West, `lag=12` meses **fijo para todos los escenarios** y cola normal asintótica. Se de-mean cada columna para calcular las covarianzas por rezago con divisor `n`; `gamma_0 + 2*sum[(1-k/13)*gamma_k]` es el estimador de la varianza de largo plazo. Valores degenerados o no finitos producen `p=1`, no un rechazo. Se aplica Holm sobre las siete hipótesis ya fijadas en v2.

Se examinan 96/192 meses, autocorrelación AR(1) 0/0,3/0,6/0,85, factor de correlación transversal 0/0,75, innovaciones gaussianas o Student-t de cinco grados de libertad estandarizadas a varianza unitaria, y dos configuraciones: siete nulos verdaderos o cuatro nulos verdaderos y tres desplazados en +0,5 desviaciones típicas incondicionales. Total: **64 escenarios, 512 réplicas independientes por escenario**, con 256 meses de calentamiento del AR(1). Semilla independiente `20261112`, sin reutilizar la de experimentos anteriores.

## Evaluación sin selección posterior

Se calculará la frecuencia de al menos un falso rechazo **familiar**, no la tasa media por hipótesis. La incertidumbre simultánea de los 64 escenarios utilizará Clopper-Pearson exacto bilateral, con Bonferroni a 95 %; el presupuesto por cola es `0,05/(2*64)`. Al menos una cota inferior superior al 5 % equivale a evidencia de exceso en esta rejilla. Incluso si todas las cotas superiores fueran menores al 5 %, ello no certificaría control universal ni aplicación válida a rendimientos reales.

Ningún resultado autoriza cambiar a `lag=24`, seleccionar una familia de innovaciones favorable, modificar alfa, reducir la familia de siete pruebas ni declarar que HAC es el procedimiento confirmado. Es una alternativa **exploratoria**, no v3, y tampoco reemplaza la inferencia congelada en v2.

## Fundamento y límites

- Diebold y Mariano (1995), *Comparing Predictive Accuracy*, estudian diferencias de pérdidas con dependencia temporal: https://doi.org/10.1080/07350015.1995.10524599
- Newey y West (1994), *Automatic Lag Selection in Covariance Matrix Estimation*, documentan distorsiones de tamaño en muestras finitas incluso con enfoques HAC: https://www.nber.org/papers/t0144
- Datta y Du (2012), *Nonparametric HAC Estimation for Time Series Data with Missing Observations*, advierten que tratar observaciones faltantes como una serie equiespaciada sin regla validada puede alterar la inferencia: https://www.federalreserve.gov/econres/ifdp/nonparametric-hac-estimation-for-time-series-data-with-missing-observations.htm

La rejilla no cubre cambios estructurales, volatilidad condicional, dependencia adversarial, pérdidas con colas sin varianza, meses no disponibles o coherencia de la cuenta de Trading. Holm necesita valores p marginales válidos y no repara un estimador HAC mal calibrado. Para usar un método nuevo habría que justificar sus supuestos, potencia, valor económico y publicar **otro registro antes de la nueva cohorte de observaciones**, sin alterar ni reinterpretar v2.
