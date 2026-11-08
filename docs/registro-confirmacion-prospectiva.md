# Registro prospectivo del motor integral v2

**Hito:** H0.3, registro metodológico parcial. **Registrado:** 8 de noviembre de 2026 UTC.

El contrato [protocolo-confirmacion-integral-v2.json](protocolo-confirmacion-integral-v2.json) conserva íntegro el protocolo de desarrollo v1. Excluye los 48 cierres históricos examinados, los ocho pronósticos retrospectivos y todos los sellos de señales bursátiles anteriores. Estos últimos evalúan señales de acciones, no órdenes ni una cuenta integral.

El primer origen posible es posterior al registro, a partir del 9 de noviembre de 2026. Un origen válido requiere el último cierre realmente observado de un mes de Nueva York, datos capturados entonces, una publicación original comprobable antes del periodo de rendimiento y una ejecución del motor con órdenes. No se presupone ningún sello futuro ni se considera elegible por tener hashes autodeclarados.

Se preservan las siete pruebas primarias de v1, sus referencias y el error familiar unilateral de 0,05 mediante Holm. Los bootstraps de 12/24 meses conservan cada corte transversal íntegro, con 10 000 remuestreos y mínimo cuatro bloques por tamaño. Se necesitan al menos 96 meses admisibles y maduros en una cohorte compatible, no 96 activos ni simulaciones. Las lagunas se conservan; no se sustituyen por 100% CASH ni se eliminan retrospectivamente.

**Registro incompleto para inferencia:** faltan umbrales de efectos económicamente relevantes y una evaluación de potencia justificable antes de examinar los resultados futuros. No existen todavía 96 orígenes, ni siquiera un corte completo causal. La versión del motor, el núcleo, la referencia y el esquema de datos deben permanecer comparables; si cambia la política, se crea otra cohorte, sin agrupar resultados incompatibles.

El comando `python scripts/prospective_study_registry.py --verify` valida el contrato, comprueba que el protocolo v1 no cambió, lee la contabilidad vigente de sellos de señales como evidencia excluida y, cuando existan futuros pronósticos integrales, examina `data/confirmatory/full-engine-v2/origins/` y su primer commit Git. CI no convierte una coincidencia de metadatos en certificación histórica.

**Próxima aceptación:** justificar efecto mínimo y potencia, implementar una captura original del motor integral con parámetros y entradas fechadas, y demostrar auditoría independiente de todos los insumos para comenzar a contar orígenes elegibles. No se declara cerrada H0.3 por registrar solo las reglas.
