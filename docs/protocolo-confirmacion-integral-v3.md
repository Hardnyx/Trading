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

## Estado de los bloqueos operativos (15-nov-2026)

- **Primera captura verificable de forma independiente:** mecanismo listo. Cada evidencia se sella con RFC 3161 ([sellado](sellado-tiempo-evidencia.md)), y [`v3_admission.py`](../scripts/v3_admission.py) admite una captura mensual solo si sus hashes se reproducen desde los archivos guardados y un sello firmado por al menos dos autoridades es anterior a la siguiente apertura posible. Se cumplirá con la primera captura mensual sellada (cierre de noviembre de 2026).
- **Vintages, ajustes, holdings y flujos:** para orígenes prospectivos, las entradas son las capturadas por el propio motor tras el cierre y selladas antes de la apertura, lo que acredita qué datos existían al decidir; no certifica que sean idénticos a la primera publicación de cada proveedor. Los flujos de la cuenta se reconstruyen con historias de distribuciones de los emisores observadas y selladas después del horizonte; el auditor lo comprueba al vencer las 21 sesiones.

El resultado de la auditoría se publica tras cada sellado en `data/timestamps/v3-admission.json`. La activación formal de la cohorte requiere un commit fechado que registre la primera captura admitida.
