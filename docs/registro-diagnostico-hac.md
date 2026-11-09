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

## Reproducción del experimento congelado

El evaluador [confirmatory_hac_stress.py](../scripts/confirmatory_hac_stress.py) calcula el estadístico con covarianzas centradas, ejecuta el procedimiento Holm completo, cuenta falsos rechazos bajo nulo global y parcial y registra límites binomiales simultáneos para los 64 escenarios. Comprueba el **SHA-1 del objeto Git** del diseño registrado antes de ejecutarse: si se modifica el JSON, falla en lugar de aceptar nuevas variantes silenciosamente. Las pruebas comprueban aritmética HAC contra una implementación escalar, equivalencia de Holm, cambios adversariales del contrato, semilla estable y separación de medias desplazadas.

Para reproducir desde la raíz del repositorio:

```bash
python -m unittest tests.test_confirmatory_hac_stress
python scripts/confirmatory_hac_stress.py --verify --output out/confirmatory-hac-independent-stress-v1.json
```

CI publica la salida como artefacto `confirmatory-hac-independent-stress`, pero un resultado favorable en esta rejilla **no** permite aprobar inferencia financiera. No cambian las reglas de captura prospectiva ni los siete efectos económicos pendientes.

## Resultado observado y corte de evidencia: 9-nov-2026 UTC

El [commit `8eadbfb`](https://github.com/Hardnyx/Trading/commit/8eadbfb30d83499c2c9fdc1c7b287920653bfe71) superó [CI 42690190654](https://github.com/Hardnyx/Trading/actions/runs/42690190654) y [Pages 42690190610](https://github.com/Hardnyx/Trading/actions/runs/42690190610): **436 pruebas Python**, 62 pasos de CI correctos y artefacto `confirmatory-hac-independent-stress` con los 64 escenarios y sus intervalos exactos simultáneos. Se ejecutaron **512 réplicas por escenario** sin leer outcomes de Trading.

**Conclusión del experimento: evidencia de exceso de error familiar bajo los generadores sintéticos registrados.** **43/64** escenarios tienen una **cota inferior simultánea al 95 % superior al 5 % nominal**, tras Bonferroni sobre 64 intervalos. Las tasas puntuales por escenario oscilan entre **4,88 % y 41,21 %**. En el escenario más adverso previamente definido, **96 meses, AR(1) 0,85, correlación transversal 0, innovaciones Student-t5 y siete nulos verdaderos**, se obtuvieron **211/512 = 41,21 %** de falsos rechazos familiares (intervalo simultáneo **33,99 %–48,71 %**). Con los 192 meses previstos en la segunda longitud, tampoco se garantiza calibración: permanece evidencia de exceso en varios escenarios. El artefacto completo contiene el desglose, incluidos los nulos parcialmente verdaderos.

Pasar CI significa que el diagnóstico y sus invariantes se ejecutaron correctamente, **no** que la inferencia HAC haya aprobado. La evidencia sintética desfavorable impide proponer el HAC de rezago 12 como reparación de v2. No se prueba automáticamente otro rezago ni se elige un método según las frecuencias inspeccionadas: para nuevas propuestas será necesario explicitar la búsqueda, registrarla y evaluar en una cohorte de simulaciones no examinada. Los requisitos de datos reales, justificación económica, potencia y confirmación prospectiva permanecen inalterados.
