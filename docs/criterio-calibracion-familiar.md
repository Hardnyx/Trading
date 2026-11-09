# Criterio de calibración de error familiar en las simulaciones

**Hito:** H0.3. **Fecha:** 9-nov-2026 UTC. **Alcance:** auditoría de diseño, no inferencia sobre retornos bursátiles.

El bootstrap circular centrado registrado en v2 mostró exceso de falsos positivos bajo siete nulos completos y bajo cuatro nulos verdaderos con tres desplazados. Un porcentaje observado cercano a 5 % tampoco basta para acreditar su calibración: las estimaciones Monte Carlo tienen incertidumbre y la rejilla contiene múltiples escenarios.

## Regla verificable

El script `scripts/confirmatory_calibration_gate.py` consume exclusivamente los dos JSON sintéticos ya definidos, valida sus esquemas, semillas, familia de siete pruebas, escenarios, repeticiones, remuestreos y consistencia de recuentos pareados. La rejilla conjunta contiene **24 escenarios**, sin selección según resultados: 16 de nulo global (256 réplicas cada uno) y ocho de nulo parcial (128 réplicas cada uno). Los dos tamaños de bloque dentro de una misma configuración comparten series; no se interpretan como replicaciones independientes entre escenarios.

Para cada proporción de falsos rechazos `k/n`, calcula límites exactos de Clopper-Pearson mediante cuantiles beta y distribuye un presupuesto de error de 5 % entre **24 intervalos bilaterales**, con probabilidad por cola `0.05/(2*24)`. La cota simultánea de 95 % sobre las 24 tasas bootstrap procede de Bonferroni y no necesita independencia entre escenarios; cada proporción binomial sí presupone réplicas independientes dentro de su escenario. Los intervalos del control gaussiano son descriptivos y **no** están incluidos en esa garantía simultánea conjunta.

Se distinguen tres resultados: (1) `excess-rejection-detected` si al menos un límite inferior del bootstrap supera el 5 % nominal; (2) `grid-upper-bounds-met` si todos los límites superiores están por debajo de 5 %, sin aprobar inferencia bursátil; (3) `inconclusive` en los demás casos. No se permite escoger un método candidato sobre estos resultados ya examinados.

Como comprobaciones aritméticas: 77/256 rechazos dan un límite inferior simultáneo aproximado de **21,67 %** y 25/128 dan **10,15 %**, ambos superiores a 5 %. Incluso **0/128** tendría un límite superior aproximado de **5,22 %**, de modo que una muestra favorable de 128 réplicas no puede certificar automáticamente la rejilla. La precisión y cobertura se refieren a este diseño sintético, no a la distribución desconocida de los siete objetivos reales.

## Reproducción en CI

El flujo `check.yml` produce los JSON con `confirmatory_familywise_bootstrap.py` y `confirmatory_partial_null_bootstrap.py` y luego ejecuta:

```bash
python scripts/confirmatory_calibration_gate.py --verify \
  --global-report out/confirmatory-familywise-bootstrap-v1.json \
  --partial-report out/confirmatory-partial-null-bootstrap-v1.json \
  --output out/confirmatory-calibration-gate-v1.json
```

El JSON de resultado se publica como artefacto `confirmatory-calibration-gate`. Los tests rechazan escenarios duplicados o incompletos, conteos incompatibles, cambios de semilla, de muestras y señales de activación indebida.

**Límite metodológico:** demostrar cobertura bajo una rejilla sintética nunca prueba control fuerte para todos los procesos posibles ni acredita datos point-in-time, potencia económica, ventaja predictiva o ausencia de sobreajuste. v2 permanece congelado e inactivo. Un eventual método v3 necesitaría supuestos justificables, evaluación prospectiva independiente y nuevo registro antes de observar confirmación. Esta auditoría formaliza la evaluación del método anterior, no elige su reemplazo.

**Referencia de cálculo:** [NIST, exact binomial confidence limits](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm).
