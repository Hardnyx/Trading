# Primer piloto integrado histórico: desarrollo, no validación

El 31-oct-2026 se ejecutó el compositor de producción 0.35.0 en dos fechas
reconstruidas. En ambas conservó la cuenta inicial de USD 100.000 en efectivo.
Ninguna transición examinada resultó admisible bajo todos los controles.
Esto acredita una integración técnica acotada; no acredita acierto predictivo,
superioridad del efectivo, una cartera óptima ni rendimiento histórico.

| Corte | Peso con historia de precios reconstruida, antes del filtro BPA | Acciones con BPA e historia | Instrumentos simulados | Candidatas cribadas en revisión robusta | Transiciones admisibles | Decisión |
|---|---:|---:|---:|---:|---:|---|
| 31-dic-2024 | 70,26% | 127 | 40 | 797 | 0 | Mantener 100% CASH |
| 30-abr-2025 | 71,55% | 134 | 40 | 408 | 0 | Mantener 100% CASH |

Los 40 instrumentos incluyen 38 acciones, SPY de comparación y CASH. El
compositor mantiene su preselección habitual; las 127/134 acciones no se
optimizan simultáneamente. Excluye además O, PLD y AMT por falta de una base
de valoración comparable admitida. SPY queda como referencia hipotética
sin permiso de compra: sus holdings no producen un ancla fundamental con
cobertura suficiente. No se rellena ni normaliza el peso sin identificar.

La revisión conserva 23 finalistas por fecha y una única confirmación.
La búsqueda base usa 300 candidatas, 600 caminos de búsqueda, 3.000 de
verificación y tres arranques; el control robusto registra 1.000 caminos.
Los 797/408 conteos corresponden al conjunto reunido entre búsquedas,
no a observaciones históricas independientes. El resultado de mantener
efectivo es una salida de seguridad ante un conjunto sin transiciones
admisibles. El rango CASH [100%, 100%] y la etiqueta automática de estabilidad
no demuestran que una solución óptima sea estable. El efectivo conserva el
rendimiento supuesto por defecto, 0%; no se le imputa la tasa de Treasury.

## Qué se ejecutó

`referenceRequest → prepareComposition → composeMultiStart` utiliza los
módulos de producción sin modificarlos: pronósticos fundamentales,
correlaciones, volatilidad, Monte Carlo, búsqueda de pesos, revisión robusta,
costes y plan de operaciones. Los planes finales no contienen operaciones.
El [protocolo del piloto](protocolo-piloto-integrado-v1.json) fija la primera
pareja cronológica de cortes con al menos 70% de cobertura de precios,
semilla 20261024, cuenta independiente por fecha y horizonte de un año.
No se cambian fechas, semilla, límites o supuestos tras ver las salidas.
La regla se escribió localmente antes de ejecutar; su publicación es conjunta
con el resultado y no constituye un prerregistro independiente con sello
temporal externo.

Se eligió explícitamente la variante EWMA de producción. No se incorpora el
archivo actual de GJR ni se presenta este piloto como una reestimación
histórica de GJR o como la variante híbrida completa. No cambia el kernel
publicado. El catálogo, sectores y parámetros fijos de valoración son una
política retrospectiva actual, no parámetros acreditados en 2024/2025.

El adaptador revalida los originales de macro, N-PORT e identificadores;
reconstruye BPA TTM positivo con versiones contables presentadas antes del
día del corte. Utiliza el BPA reportado en las mismas unidades por acción
que el precio reconstruido. Excluye componentes incompatibles con splits.
Los dividendos pasados se reexpresan bajo la hipótesis declarada de unidades
del proveedor; no entran eventos posteriores. No acredita vintages originales
de esos precios, dividendos o EPS, ni calendarios de cobro ejecutables.

No se copian métricas financieras actuales, estimaciones de analistas,
perfiles actuales de bonos/ETF ni cuentas actuales. Las métricas de calidad
ausentes permanecen ausentes, con las penalizaciones de fiabilidad del motor.
La cobertura de submissions y la identidad continua siguen incompletas.
El reloj virtual de disponibilidad pública de holdings se etiqueta como
reconstrucción; conserva por separado la descarga real de 2026. No se finge
una captura de datos anterior.

## Evidencia conservada y reproducción

El [resumen verificable](../data/historical/scoped-engine-pilot-v1/report.json)
conserva los 48 cortes, las dos selecciones, pronósticos, volatilidades,
decisiones y hashes. Los archivos
[`inputs.json.gz`](../data/historical/scoped-engine-pilot-v1/inputs.json.gz) y
[`results.json.gz`](../data/historical/scoped-engine-pilot-v1/results.json.gz)
conservan exactamente las entradas usadas, las matrices de covarianza,
anclas y resultados completos, incluida la auditoría de decisiones. El
manifiesto de módulos de producción y el hash del ejecutor están dentro del
resultado completo. Los hashes de snapshot Python y `JSON.stringify` usan
serializaciones distintas y se identifican por separado.

Para repetir sobre las entradas exactas archivadas, sin reconstruirlas desde
un catálogo nuevo:

```sh
node scripts/scoped_engine_pilot.mjs data/historical/scoped-engine-pilot-v1/inputs.json.gz out/scoped-engine-pilot-repeat.json
python scripts/archive_scoped_pilot.py --inputs data/historical/scoped-engine-pilot-v1/inputs.json.gz --archive-dir out/scoped-engine-repeat --report out/scoped-engine-repeat-report.json
```

Para reconstruir las entradas desde los originales fijados:

```sh
git fetch origin 8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5
python scripts/scoped_engine_inputs.py
node scripts/scoped_engine_pilot.mjs out/scoped-engine-inputs-v1.json.gz out/scoped-engine-pilot-report.json
python scripts/archive_scoped_pilot.py --archive-dir out/scoped-engine-new-run --report out/scoped-engine-new-run-report.json
```

El tiempo real de compilación cambia el hash de unas entradas reconstruidas.
Otro código de producción puede cambiar el resultado y debe considerarse
otra versión. El empaquetador rechaza sustituir archivos de una cohorte
existente por bytes diferentes. El workflow separado conserva cada nueva
ejecución como artefacto identificado por commit, run y attempt; no reescribe
la cohorte publicada ni envía propuestas a producción.

## Qué sigue pendiente

El preflight causal completo permanece en **0/48 cortes elegibles**. Estos
**2 ensayos de desarrollo ejecutados** se cuentan por separado. Continúan
los sesgos del catálogo superviviente, exclusiones de eventos posteriores,
fechas no contiguas, cobertura parcial y parámetros retrospectivos.

No se calculan retornos realizados, errores, calibración, p-valores o
superioridad económica con este piloto. La siguiente ampliación requiere
completar los fundamentales y perfiles históricos y verificar los flujos
para puntuar pronósticos y carteras conforme al protocolo estadístico.
Las nuevas versiones necesitan datos no utilizados y seguimiento prospectivo.
El estado predictivo y económico continúa **no concluyente**.
