# Registro prospectivo del motor integral v2

**Hito:** H0.3, registro metodológico parcial. **Registrado:** 8 de noviembre de 2026 UTC.

El contrato [protocolo-confirmacion-integral-v2.json](protocolo-confirmacion-integral-v2.json) conserva íntegro el protocolo de desarrollo v1. Excluye los 48 cierres históricos examinados, los ocho pronósticos retrospectivos y todos los sellos de señales bursátiles anteriores. Estos últimos evalúan señales de acciones, no órdenes ni una cuenta integral.

El primer origen posible es posterior al registro, a partir del 9 de noviembre de 2026. Un origen válido requiere el último cierre realmente observado de un mes de Nueva York, datos capturados entonces, una publicación original comprobable antes del periodo de rendimiento y una ejecución del motor con órdenes. No se presupone ningún sello futuro ni se considera elegible por tener hashes autodeclarados.

Se preservan las siete pruebas primarias de v1, sus referencias y el error familiar unilateral de 0,05 mediante Holm. Los bootstraps de 12/24 meses conservan cada corte transversal íntegro, con 10 000 remuestreos y mínimo cuatro bloques por tamaño. Se necesitan al menos 96 meses admisibles y maduros en una cohorte compatible, no 96 activos ni simulaciones. Las lagunas se conservan; no se sustituyen por 100% CASH ni se eliminan retrospectivamente.

**Registro incompleto para inferencia:** faltan umbrales de efectos económicamente relevantes y una evaluación de potencia justificable antes de examinar los resultados futuros. No existen todavía 96 orígenes, ni siquiera un corte completo causal. La versión del motor, el núcleo, la referencia y el esquema de datos deben permanecer comparables; si cambia la política, se crea otra cohorte, sin agrupar resultados incompatibles.

El comando `python scripts/prospective_study_registry.py --verify` valida el contrato, comprueba que el protocolo v1 no cambió, lee la contabilidad vigente de sellos de señales como evidencia excluida y, cuando existan futuros pronósticos integrales, examina `data/confirmatory/full-engine-v2/origins/` y su primer commit Git. CI no convierte una coincidencia de metadatos en certificación histórica.

**Próxima aceptación:** justificar efecto mínimo y potencia, implementar una captura original del motor integral con parámetros y entradas fechadas, y demostrar auditoría independiente de todos los insumos para comenzar a contar orígenes elegibles. No se declara cerrada H0.3 por registrar solo las reglas.

## Resultado posterior de calibración sintética

El diagnóstico [`confirmatory_bootstrap_diagnostic.py`](../scripts/confirmatory_bootstrap_diagnostic.py), comprobado por [CI 42642546232](https://github.com/Hardnyx/Trading/actions/runs/42642546232) el 9-nov-2026 UTC, encontró en simulaciones gaussianas AR(1) **rechazos nulos por encima del primer umbral nominal de Holm** con 96 meses y bloques de 12 o 24 meses. Por ejemplo, el caso AR(1) 0,6 con bloques de 24 meses rechazó 22 de 512 nulos (4,30 %) frente al umbral nominal de 0,714 %. Ver [resultados y límites](diagnostico-bootstrap-confirmatorio.md). Este primer diagnóstico individual no medía el error familiar conjunto de siete pruebas; tampoco estimaba potencia real.

**Consecuencia:** el protocolo v2 permanece íntegro como registro metodológico, pero **no tiene activación confirmatoria defendible** mientras esta preocupación de tamaño finito no se resuelva mediante una justificación estadística independiente y, de ser necesario, un nuevo protocolo versionado. No se cambian umbrales para conseguir resultados favorables ni se convierte el pasado examinado en holdout.

## Calibración de error familiar conjunto, 9-nov-2026 UTC

El [diagnóstico de siete nulos sintéticos](diagnostico-bootstrap-familiar.md), implementado en [`8f08908`](https://github.com/Hardnyx/Trading/commit/8f0890875b64610dcbb2f64197eb807df0522fc1) y comprobado por [CI 42647440162](https://github.com/Hardnyx/Trading/actions/runs/42647440162), mantiene siete remuestreos vinculados por **los mismos índices mensuales**. En 15 de 16 escenarios de muestra finita la frecuencia de al menos un rechazo bajo el nulo global fue mayor que el 5 % familiar nominal; en uno alcanzó 77/256 (30,08 %), con intervalo Wilson 24,79–35,96 %. Son resultados **hipotéticos**, sin medidas de Trading ni potencia real. A diferencia del diagnóstico individual anterior, aquí se contrasta el 5 % de error familiar, no el primer umbral 0,05/7. La conclusión de diseño es conservar el registro v2 congelado e **inactivo para inferencia** hasta justificar un procedimiento que supere las auditorías de tamaño finito sin revisar oportunistamente umbrales o cohortes.

## Diagnóstico de nulos parcialmente verdaderos, 9-nov-2026 UTC

La [auditoría de cuatro nulos verdaderos y tres desplazados](diagnostico-bootstrap-nulos-parciales.md), incorporada en el [commit `1a0a4dc`](https://github.com/Hardnyx/Trading/commit/1a0a4dca58b4abc3b84320fa26034d397683a6b5), quedó reproducida por [CI 42662188377](https://github.com/Hardnyx/Trading/actions/runs/42662188377), con **414 pruebas Python correctas** y el artefacto `confirmatory-partial-null-bootstrap`. Los ocho escenarios sintéticos de 128 réplicas conservaron siete valores p mensuales con remuestreo conjunto y el procedimiento Holm completo. El bootstrap rechazó alguna hipótesis nula verdadera entre **11/128 (8,59 %) y 25/128 (19,53 %)** de las veces, frente a un error familiar nominal de **5 %**. El control gaussiano con la distribución generadora conocida registró entre **3/128 (2,34 %) y 7/128 (5,47 %)**.

Este hallazgo se limita a la rejilla ensayada y no demuestra control fuerte para todas las configuraciones posibles, ni proporciona valores p válidos para efectos reales de Trading. **La inferencia v2 sigue inactiva.** Aun si se justificara un método nuevo, su incorporación exigiría un registro prospectivo independiente y una nueva cohorte, sin reinterpretar como confirmación los resultados ya examinados.
