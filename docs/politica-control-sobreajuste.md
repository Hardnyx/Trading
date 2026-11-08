# Política de control de sobreajuste

**Hito:** H0.3, gobierno de investigación del motor integral. **Adoptada:** 8 de noviembre de 2026 (UTC). **Estado:** controles de diseño, no evidencia de ausencia de sobreajuste.

## Criterio obligatorio

Ninguna calibración, búsqueda de parámetros, selección de activos, horizonte, semilla, benchmark, exclusión, estrategia o versión del motor puede elegirse por el resultado de la misma muestra cuyo rendimiento luego se presenta como confirmación independiente. **No se puede garantizar que no exista sobreajuste**; se puede limitar, auditar y detectar parte de sus mecanismos, y demostrar o no su generalización con evidencia futura independiente.

El criterio es de aceptación en H0, H1, H3, H4, H5 y H6, no solo una recomendación para el backtest.

## Qué ya estaba incluido

- El protocolo v1 es **desarrollo retrospectivo**, con 48 cortes ya examinados y sin holdout histórico intacto. El registro v2 comienza después de su creación y no reclasifica ese pasado.
- Las entradas, ajustes, semillas y búsqueda deben congelarse por versión y fecha; los resultados de acciones y Monte Carlo no cuentan como meses independientes.
- Los siete contrastes primarios y sus benchmarks están definidos antes de puntuar confirmación; Holm controla su multiplicidad **dentro del modelo registrado**, no el número de versiones que se probaron antes.
- Las pruebas de fuente point-in-time y primera publicación impiden formas concretas de *look-ahead*. Ninguna de ellas demuestra por sí sola habilidad predictiva.

## Controles añadidos

**1. Separación por función de los datos.** Todo el periodo retrospectivo ya visto sirve para investigación, reparación y diseño, jamás para afirmar una prueba independiente. Los pronósticos integrales prospectivos se mantienen por cohorte y no se escogen meses según aciertos. No se convierten ausencias en efectivo ni se eliminan meses negativos.

**2. Selección temporal interna.** Si el motor introduce aprendizaje, selección de características, búsqueda de hiperparámetros o pesos ajustados sobre resultados, cada origen externo debe disponer de una búsqueda **interna** realizada en el pasado. La selección, la imputación, normalización, filtros estadísticos y calibración de probabilidades se vuelven a ajustar únicamente en el entrenamiento del pliegue. En una validación interna cronológica *expanding* o *rolling*, las etiquetas que aún no han madurado no son conocidas. Se purgan las etiquetas del entrenamiento que solapan la ventana de validación; se registra y justifica si procede un embargo temporal según horizonte y ventanas de características, sin inventar un número universal. No utilizar `KFold` aleatorio. Si no se realiza selección de hiperparámetros, no es obligatorio fingir una búsqueda anidada, pero sigue siendo obligatorio un pronóstico causal.

**3. Inventario de intentos y de decisiones.** Registrar todas las variantes efectivamente probadas, incluso rechazadas, con versión de fuentes/código, espacio de búsqueda, semillas, periodo usado, criterios de selección y momento de inspección. Las pruebas anteriores a esta política no se consideran exhaustivamente inventariadas. La selección de la mejor rentabilidad simulada entre decenas de variantes no es una prueba de ventaja. Informar sensibilidad, estabilidad por régimen y comparaciones económicas con el coste de búsqueda, sin escoger después el único benchmark favorable.

**4. Inmutabilidad de la confirmación.** No inspeccionar contrastes primarios confirmatorios antes de los hitos de análisis previamente registrados. Si se desea un análisis interino, registrar de antemano la regla de error secuencial; el contrato v2 no la incluye. Se permiten verificaciones operativas de integridad, procedencia y maduración sin usar su rentabilidad para afinar el modelo.

**5. Cambios del motor.** Una corrección matemática real puede ser necesaria aunque los resultados empeoren. Debe quedar registrada con razón independiente de los rendimientos, entradas y pruebas. Si altera retornos, filtros, calibración, núcleo, costos, prioridades o decisión, crea una cohorte nueva. Si se examinó confirmación antes de decidir el cambio, ese periodo pasa a desarrollo para la nueva versión; hay que obtener una **nueva muestra futura independiente**. Los resultados de versiones incompatibles no se suman.

**6. Inferencia y criterio de cierre.** Mantener el conjunto fijo de siete pruebas, Holm a 0,05, muestra madura mínima de 96 orígenes y bloques establecidos. Es un mínimo operativo, **no una garantía de potencia**; faltan magnitudes económicas mínimas justificadas y análisis de potencia. Si se prueban numerosos modelos, aplicar un diseño que también tome en cuenta esa búsqueda: no reinterpretar Holm dentro de una versión como protección contra *data snooping* entre versiones. Los procedimientos como DSR/PBO son diagnósticos secundarios solo cuando hay un registro de ensayos suficientemente completo y compatible, no un requisito automático que sustituya la validación prospectiva.

## Verificación y alcance

`docs/politica-control-sobreajuste-v1.json` fija las condiciones de gobierno de investigación; `data/validation/model-trials-v1.json` es un registro inicialmente vacío de **nuevos** intentos, no un inventario exhaustivo de experimentos antiguos. `scripts/overfit_policy_guard.py --verify` rechaza la debilitación de criterios registrados, la promoción indebida de la historia usada, ejemplos de ventanas temporales contaminadas y registros de nuevas versiones que reutilicen una cohorte anterior. Las pruebas adversariales se ejecutan en CI.

**Límite:** el verificador puede revisar archivos declarados y decisiones codificadas, no demostrar que se documentó cada ensayo realizado fuera del repositorio. El control también exige revisión humana del historial de cambios y de la trazabilidad de los datos y resultados. Los protocolos v1 y v2 anteriores **no se editan**; cualquier cambio a hipótesis, familia de pruebas, efectos o regla confirmatoria requiere una versión explícita y una nueva ventana futura, nunca una reescritura.

**Aceptación:** no declarar «modelo libre de overfitting». Declarar, según evidencia independiente, que el resultado es *respaldado*, *no respaldado* o *inconcluso*, con resultados adversos y todas las variantes relevantes expuestas.

**Integridad del registro:** la CI revisa el historial completo de Git del archivo de ensayos y rechaza borrados, reordenamientos o cambios retrospectivos de entradas ya publicadas. Esta garantía cubre los ensayos *registrados* después de adoptar la política, no experimentos ejecutados fuera del repositorio ni intentos anteriores cuyo inventario no es exhaustivo.
