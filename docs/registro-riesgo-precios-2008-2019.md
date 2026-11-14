# Registro: núcleo de riesgo de precios fuera de muestra, 2008–2019

**Fecha de registro:** 14-nov-2026 UTC, **antes de construir los datos del periodo y de ejecutar.** Contrato: [estudio-riesgo-precios-2008-2019-v1.json](estudio-riesgo-precios-2008-2019-v1.json).

**Pregunta.** ¿El núcleo de precio y varianza desplegado da un VaR 95 % a 21 sesiones calibrado y un CRPS mejor que el EWMA plano en un periodo que nunca se usó para construirlo ni auditarlo? La auditoría anterior ([price-risk-reconstruction](auditorias/price-risk-reconstruction-2026-10-28.json)) solo cubrió desde nov-2021.

**Qué se ejecuta.** El mismo `price_risk_replay.mjs` y los mismos parámetros, sin cambios: tres modelos, 2.000 trayectorias, semilla fija. Cortes mensuales del 30-jun-2008 al 29-nov-2019, con 11 instrumentos que ya cotizaban (SGOV y la cesta actual se excluyen porque no existían o se eligieron después). Los precios provienen del archivo histórico del repositorio, ajustados por splits y dividendos.

**Afirmaciones primarias y regla de veredicto** (fijas antes de ver resultados):

- **A · Calibración.** SPY y las tres cestas de referencia, 21 sesiones, orígenes sin solapamiento. *No respaldada* si algún Kupiec ajustado por Holm da p < 0,05. *Respaldada* si no hay rechazo y la cota superior exacta al 95 % de cada tasa de excepciones es ≤ 12 %. *Inconclusa* en otro caso.
- **B · Mejora sobre EWMA plano.** Ganancia de CRPS emparejada en las tres cestas, intervalo bootstrap por bloques de 3 orígenes con α = 0,05/3. *Respaldada* si algún intervalo queda sobre cero y ninguno bajo cero. *No respaldada* si alguno queda bajo cero. *Inconclusa* en otro caso.

Todo lo demás (otros instrumentos y horizontes, independencia de Christoffersen, comparación con EWMA dinámico, años, ES) es descriptivo.

**Límites.** Solo responde por el componente de riesgo: no prueba pronósticos de retorno, fundamentales, el optimizador ni el valor económico neto. Son revisiones actuales de precios, no vintages originales. No rechazar no certifica. El resultado no cambia producción, y no se permite modificar el diseño después de ver resultados.
