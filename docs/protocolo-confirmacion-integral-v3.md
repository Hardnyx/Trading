# Protocolo confirmatorio v3 del motor integral

**Registro:** 15-nov-2026 UTC. Contrato: [protocolo-confirmacion-integral-v3.json](protocolo-confirmacion-integral-v3.json). **Estado:** metodología registrada; recolección e inferencia cerradas.

**Por qué existe.** La familia de siete pruebas de [v2](protocolo-confirmacion-integral-v2.json), que no se modifica, no pudo calibrarse: sus horizontes de 63 y 252 sesiones se solapan entre orígenes mensuales. Con solo 21 sesiones, el método KVB no mostró exceso de error hasta AR(1) 0,6 ([calibración](registro-calibracion-familia-21.md)). Los umbrales y meses salen de [potencia y materialidad](potencia-v3-familia-21.md).

**Qué afirma y cómo.**

- **Prueba confirmatoria única, `ranking_ic:21`:** ¿el motor ordena acciones mejor que BPA/precio? Prueba KVB unilateral con α = 0,05 tras 120 meses maduros elegibles. «Respaldada y material» exige p < 0,05 y mejora media ≥ 0,03 de IC.
- **Vigilancia de daño, `net_economic_value:21`:** cada 12 meses, prueba unilateral de que la cuenta neta del motor no pierde frente a SPY más efectivo con igual beta, con α = 0,005 por revisión (10 revisiones). Si detecta daño, se deja de usar cualquier apuesta del motor en carteras publicadas. Nunca afirma ventaja.
- **Descriptivo:** el error de pronóstico (`return_mse:21`) y los informes anuales, sin valores p.

**Qué hereda de v2 sin cambios:** cortes mensuales, referencias, objetivo de pronóstico, ejecución al cierre siguiente, costos, cohorte de código y reglas de admisión.

**Por qué sigue cerrado.** Ya se resolvieron la inferencia calibrada y los umbrales económicos. Faltan los bloqueos operativos de v2: publicar los pronósticos originales con primera captura verificable de forma independiente y verificar las vintages originales de fuentes, ajustes, holdings y flujos. El primer origen elegible será el primer corte mensual posterior a un commit fechado que registre ambos verificados.

**Lo que no promete.** Con 120 meses, la potencia del 80 % solo se alcanza en escenarios de dispersión favorables. Ninguna regla permite alargar la muestra, cambiar umbrales o mirar resultados intermedios de la prueba confirmatoria.
