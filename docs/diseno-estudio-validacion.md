# Diseño del estudio de validación: decisión de viabilidad

**Revisión:** 8 de noviembre de 2026 (UTC). **Hito:** H0.2. **Resultado:** diagnóstico completado; estudio confirmatorio integral no viable con las entradas y la muestra actualmente certificadas.

Este documento evalúa el [protocolo integral v1](protocolo-replay-integral-v1.json) sin sustituirlo ni reclasificar retrospectivamente resultados como independientes. Los contadores se reconstruyen a partir de [la auditoría legible por máquina](../data/historical/study-feasibility-v1/report.json), [las fuentes](../data/historical/provider-inputs-v1/readiness.json), [la matriz del motor](../data/historical/replay-plan-v1/coverage.json), [los identificadores](../data/historical/identifier-observations-v1/coverage.json) y [los precios](../data/historical/price-reconciliation-v1/coverage.json). Todos son cortes de información de investigación, no datos históricos certificados para órdenes.

## Universo y periodos de evidencia

| Muestra | Fechas / unidad de observación | Uso defendible hoy |
|---|---|---|
| Replay integral v1 | 48 cierres mensuales, 31-oct-2022 a 30-sep-2026; universo histórico de valores cotizados, ETF y efectivo pendiente de reconstrucción | Desarrollo retrospectivo y diagnóstico de ausencia de entradas; 0/48 cortes admisibles |
| Subconjunto histórico reconstruido | 8 orígenes archivados entre dic-2024 y sep-2026; 2 de ellos ejecutaron el compositor en modalidad EWMA | Contraste descriptivo sobre acciones supervivientes; ni el universo ni los vintages completos están certificados |
| Señales prospectivas selladas | Cohortes con modelo/código y publicación registrados; 21/63/252 sesiones requieren esperar realización | Confirmación potencial futura, únicamente dentro de cada cohorte causal compatible; no convertir activos de un sello en meses independientes |
| Historia ampliada hipotética | Al menos 96 orígenes mensuales **admisibles y maduros** para mantener el requisito v1 de cuatro bloques de 24 meses | No existe esta muestra certificada; requiere historia adicional, recuperación de acciones deslistadas y eventos, y maduración de horizontes |

La unidad de inferencia es el **origen temporal**, con el corte transversal conservado conjuntamente en cada remuestreo. Los horizontes anuales solapados, las simulaciones Monte Carlo y los activos de una misma fecha no multiplican el número efectivo de orígenes. La historia examinada antes de formular esta revisión no puede servir como muestra confirmatoria sin inspección previa.

## Viabilidad observada y decisión

- **Macro:** 768/768 respuestas históricas verificadas para 16 series y 48 cortes. Solo acredita esa capa.
- **SPY:** hay fuente pública dentro del límite de 120 días en 26/48 cortes; las observaciones documentales de ticker original cubren 12 cortes y no garantizan el emparejamiento operable de la cotización.
- **Precios:** hay historias de investigación para 10 cortes; se conserva el sesgo del catálogo actual y no se certifica identidad continua, precio ejecutable ni todos los flujos de dividendos.
- **Motor integral:** 0/48 cortes completos y 0 decisiones ejecutadas con preflight causal integral. Los dos pilotos que conservan CASH son ensayos acotados, no decisiones de una cuenta histórica continua.

**Dictamen H0.2:** con estas entradas no existe una muestra apta para probar las siete afirmaciones primarias bajo v1. La política actual permite completar ingeniería, descubrir faltantes y comunicar resultados descriptivos; no emitir una conclusión confirmatoria de ventaja predictiva o económica. Es un resultado de evaluación del diseño, no un porcentaje global de avance.

## Regla estadística y sensibilidad

El protocolo agrupa **siete contrastes primarios**: tres horizontes MSE, tres IC y una diferencia económica. Holm controla el error familiar unilateral en 0,05. Exige cuatro bloques para cada longitud de remuestreo, 12 y 24 meses; el segundo requisito supone **96 orígenes**, frente a solo 48 previstos. Aun con todos los 48 cortes admisibles, habría 4 bloques de 12 meses y **2 de 24 meses**, por lo que faltaría muestra y no bastaría ejecutar el replay.

Como cota pedagógica **optimista**, sin estimar potencia real, se supone normalidad de diferencias pareadas estandarizadas, bloques no solapados independientes, potencia nominal de 80% y el primer umbral de Holm (0,05/7). La diferencia detectable en desviaciones típicas de bloques sería aproximadamente:

| Orígenes disponibles | Bloques de 12 m | Diferencia mínima en SD | Bloques de 24 m | Diferencia mínima en SD |
|---|---:|---:|---:|---:|
| 48 | 4 | 1,646 | 2 | 2,328 |
| 96 | 8 | 1,164 | 4 | 1,646 |
| 120 | 10 | 1,041 | 5 | 1,472 |

La fórmula ilustrativa es `(z_(1-0,05/7) + z_0,8) / sqrt(floor(n/longitud_bloque))`. No es un cálculo de potencia empírica del motor: no hay varianza de diferencias pareadas causalmente verificadas, los bloques pueden depender entre sí y se requieren outcomes maduros. El requisito de cuatro bloques es un **mínimo operativo, no garantía de potencia**. El periodo 2022–2026 incluye resultados aún inmaduros a 252 sesiones y, por tanto, su muestra usable es menor que 48. Conseguir otros 48 cortes arbitrarios tampoco garantiza 96 cortes maduros.

## Efectos de interés y referencias

Se preservan las definiciones v1: retornos aritméticos totales compatibles con el outcome, MSE frente a media expansiva entrenada solo con pasado, IC Spearman frente a BPA TTM/precio en la misma intersección, y diferencial económico anualizado de retornos logarítmicos mensuales frente a SPY + CASH con beta ex ante. Las siete pruebas y sus referencias no se sustituyen por el contraste secundario EWMA de media cero.

Antes de registrar una cohorte confirmatoria deberá fijarse por afirmación un **mínimo efecto económicamente relevante**, expresado en unidades comparables (por ejemplo diferencia de MSE, mejora de IC, puntos porcentuales anuales de retorno neto) y estimarse la dispersión histórica de las diferencias sin seleccionar por el resultado. **No se fija ahora un umbral numérico arbitrario**: ninguna varianza causal integral está disponible para justificarlo. Sin estas dos magnitudes la potencia solo puede evaluarse por sensibilidad como arriba, no prometerse.

## Cuenta, costes y riesgo

El escenario base v1 conserva comisión fija y variable cero, spread 5 pb por operación, deslizamiento 2 pb, y tributación por ganancia de capital cero como supuesto explícito, más sensibilidad con triple spread/deslizamiento. Debe usar precios de ejecución de la **siguiente sesión observada**, cobros reales en efectivo y acciones consistentes con splits, sin contar dos veces dividendos de precios ajustados. El devengo de efectivo debe proceder de fuentes históricas y no de una tasa pronosticada.

El valor neto no se infiere solo del Sharpe o de comparaciones contra 100% efectivo: deben reportarse exposición bursátil, duración, crédito, beta y coste de rotación en el mismo mandato. VaR, ES y pérdidas extremas requieren suficientes eventos y su ausencia no se interpreta como riesgo nulo.

## Decisión de construcción y condiciones de salida

1. **Mantener v1 inmutable como diseño retrospectivo**, con 48 fechas, exclusiones explícitas y su estatus de desarrollo.
2. **Desbloquear H1:** inventariar un corte candidato sin mirar rendimientos posteriores, completar procedencia, licencias, universo deslistado, fundamentales y calibración por fecha. El [inventario del 31-dic-2024](../data/historical/full-engine-input-audit-v1/manifest.json) identifica 14 componentes; no acredita un snapshot admisible.
3. **Evaluar extensión histórica:** obtener al menos 96 decisiones mensuales admisibles **y resultados maduros** o publicar un contrato distinto, científicamente justificado, que limite las afirmaciones. Cambiar umbrales tras inspeccionar resultados no es solución.
4. **Registrar antes de evaluar la confirmación:** fecha de inicio, cohortes y versiones, universo, potencia, efectos de interés, siete contrastes, política de multiplicidad, costos, exclusiones, horizonte de maduración y revisiones sucesivas. No fusionar kernels ni fuentes reconstruidas con sellos prospectivos incompatibles.
5. **Condición de cierre del estudio:** cada afirmación tendrá resultado reproducible, intervalo, potencia, limitaciones y dictamen: respaldada, no respaldada o inconclusa. La capacidad predictiva no queda acreditada por la conclusión del diseño H0.2.

**Dependencia siguiente:** H0.3 solo puede registrar una nueva versión cuando se haya escogido y delimitado una muestra/alcance coherentes. En paralelo, H1.1 permite recuperar datos originales; se evita bloquear toda la ingeniería por el calendario prospectivo.
