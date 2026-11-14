# Registro: núcleo de riesgo de precios fuera de muestra, 2008–2019

**Fecha de registro:** 14-nov-2026 UTC, **antes de construir los datos del periodo y de ejecutar.** Contrato: [estudio-riesgo-precios-2008-2019-v1.json](estudio-riesgo-precios-2008-2019-v1.json).

**Pregunta.** ¿El núcleo de precio y varianza desplegado da un VaR 95 % a 21 sesiones calibrado y un CRPS mejor que el EWMA plano en un periodo que nunca se usó para construirlo ni auditarlo? La auditoría anterior ([price-risk-reconstruction](auditorias/price-risk-reconstruction-2026-10-28.json)) solo cubrió desde nov-2021.

**Qué se ejecuta.** El mismo `price_risk_replay.mjs` y los mismos parámetros, sin cambios: tres modelos, 2.000 trayectorias, semilla fija. Cortes mensuales del 30-jun-2008 al 29-nov-2019, con 11 instrumentos que ya cotizaban (SGOV y la cesta actual se excluyen porque no existían o se eligieron después). Los precios provienen del archivo histórico del repositorio, ajustados por splits y dividendos.

**Afirmaciones primarias y regla de veredicto** (fijas antes de ver resultados):

- **A · Calibración.** SPY y las tres cestas de referencia, 21 sesiones, orígenes sin solapamiento. *No respaldada* si algún Kupiec ajustado por Holm da p < 0,05. *Respaldada* si no hay rechazo y la cota superior exacta al 95 % de cada tasa de excepciones es ≤ 12 %. *Inconclusa* en otro caso.
- **B · Mejora sobre EWMA plano.** Ganancia de CRPS emparejada en las tres cestas, intervalo bootstrap por bloques de 3 orígenes con α = 0,05/3. *Respaldada* si algún intervalo queda sobre cero y ninguno bajo cero. *No respaldada* si alguno queda bajo cero. *Inconclusa* en otro caso.

Todo lo demás (otros instrumentos y horizontes, independencia de Christoffersen, comparación con EWMA dinámico, años, ES) es descriptivo.

**Límites.** Solo responde por el componente de riesgo: no prueba pronósticos de retorno, fundamentales, el optimizador ni el valor económico neto. Son revisiones actuales de precios, no vintages originales. No rechazar no certifica. El resultado no cambia producción, y no se permite modificar el diseño después de ver resultados.

## Resultado (14-nov-2026 UTC)

Registro publicado en [`329796e`](https://github.com/Hardnyx/Trading/commit/329796e3) antes de construir los datos y ejecutar. Se usó el núcleo sin cambios sobre 138 cortes mensuales (30-jun-2008 a 29-nov-2019); a 21 sesiones quedan **102 orígenes sin solapamiento** por objetivo. Ejecución reproducible: `python scripts/price_risk_oos_inputs.py`, `node scripts/price_risk_oos.mjs`, `python scripts/price_risk_oos_verdict.py`. Resumen en [auditorias/price-risk-oos-2008-2019.json](auditorias/price-risk-oos-2008-2019.json).

**A · Calibración del VaR 95 % a 21 sesiones: inconclusa.**

| Objetivo | Excepciones | Tasa | IC exacto 95 % | Kupiec p (Holm) |
|---|---:|---:|---|---:|
| SPY | 8/102 | 7,8 % | 3,4 %–14,9 % | 0,89 |
| Cesta equilibrada | 5/102 | 4,9 % | 1,6 %–11,1 % | 1,00 |
| Treasuries largos + acciones | 7/102 | 6,9 % | 2,8 %–13,6 % | 1,00 |
| Crédito + acciones | 7/102 | 6,9 % | 2,8 %–13,6 % | 1,00 |

Ninguna prueba rechaza la calibración, ni siquiera con la crisis de 2008 dentro de la muestra. Pero 102 meses no permiten descartar una tasa real de hasta 11–15 %, por encima del 12 % que exigía el registro para declararla respaldada.

**B · Mejora frente a EWMA plano: inconclusa.** El modelo desplegado mejora el CRPS de las tres cestas entre un 0,3 % y un 0,7 %, pero los tres intervalos incluyen cero.

**Descriptivo.** En los 42 instrumentos y horizontes, la tasa media de excepciones es **6,6 %** con el modelo desplegado frente a **7,2 %** con EWMA plano. Hay una ligera tendencia a subestimar el riesgo y ninguna celda se rechaza tras Holm. Las dos únicas celdas rechazadas son de los modelos de referencia (EMB a 5 sesiones).

**Qué significa.** El componente de riesgo no muestra fallas en 12 años que nunca había visto, pero esta muestra no basta para certificarlo ni para demostrar que supere a la alternativa simple. No dice nada sobre los pronósticos de retorno ni sobre el valor económico de las decisiones.
