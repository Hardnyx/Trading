# Resolución y sensibilidad del diseño confirmatorio

**Hito:** H0.3. **Revisión:** 8 de noviembre de 2026 UTC. **Alcance:** diagnóstico prospectivo del tamaño muestral, sin usar realizaciones ni alterar hipótesis.

La inscripción v2 conserva siete contrastes primarios y Holm unilateral al 5 %. El umbral de 96 meses admisibles y maduros proviene de cuatro bloques de 24 meses; es un mínimo de operación del bootstrap circular declarado, **no una garantía de potencia ni de tamaño correcto de prueba en muestra pequeña**.

## Dos diagnósticos deliberadamente distintos

1. **Normal optimista:** diferencia detectable estandarizada = (cuantil normal de 1 - 0,05/7 + cuantil normal de 0,80) / raíz del número de bloques no solapados. Supone varianza conocida e independencia; no hay varianza causal empírica del motor.
2. **Signos exactos de bloques:** bajo bloques independientes, simétricos y no solapados, el menor valor p unilateral posible con todos los bloques a favor es 2 elevado a menos el número de bloques. Es una **prueba diagnóstica alternativa**, no el bootstrap circular registrado; no permite declarar inválido ese bootstrap ni trasladar su potencia a la prueba registrada. Sirve para mostrar la resolución limitada que persiste al contar meses solapados como observaciones.

| Meses elegibles y maduros | Bloques 24 m | MDE normal optimista (SD de bloques) | Mejor p unilateral de signos | ¿Supera el primer paso de Holm? |
|---|---:|---:|---:|---|
| 48 | 2 | 2,328 | 0,25 | No |
| 96 | 4 | 1,646 | 0,0625 | No |
| 120 | 5 | 1,472 | 0,03125 | No |
| 192 | 8 | 1,164 | 0,00390625 | Sí, solo si los ocho bloques son favorables |

El primer umbral de Holm es 0,05/7 = 0,00714286. Con ocho bloques independientes y una probabilidad **hipotética**, no estimada, del 80 % de signo favorable en cada uno, la potencia de esa prueba exacta es apenas 0,8^8 = **16,8 %** para rechazar en el primer paso. Esto **no** es potencia calculada para Trading: no se ha estimado la distribución de efectos, su dependencia, su varianza causal ni la potencia del bootstrap registrado. Tampoco se propone elevar silenciosamente el requisito a 192 meses ni sustituir la prueba preinscrita por otra.

## Implicaciones y aceptación

- H0.3 sigue **parcial**. El mínimo de 96 meses no debe anunciarse como muestra suficiente para demostrar ventaja. No ejecutar contrastes confirmatorios antes de justificar magnitud mínima económicamente relevante por prueba, varianza de diferencias pareadas y potencia del procedimiento efectivamente registrado.
- Para estimar varianzas usar únicamente una muestra de desarrollo explícitamente identificada, con efectos y datos congruentes. Los ocho orígenes marginales reconstruidos y los dos pilotos no constituyen una estimación causal del motor integral. No observar resultados futuros de confirmación para elegir un efecto, una variante o el número de meses.
- Una revisión del método inferencial, el número de pruebas o el criterio de aceptación requiere **nuevo protocolo y nueva cohorte prospectiva**, sin modificar v1/v2 ni reaprovechar meses observados.
- Los bootstrap con 10 000 remuestreos no crean 10 000 observaciones independientes. Sus valores p y cobertura necesitan un diagnóstico de tamaño finito ante horizontes solapados, dependencia temporal, pérdidas asimétricas y apenas cuatro bloques de 24 meses.

**Reproducción:** ejecutar `python scripts/confirmatory_design_sensitivity.py --verify` y `python -m unittest tests.test_confirmatory_design_sensitivity`. El programa solo lee el contrato v2; produce JSON en stdout, no escribe datos ni mira retornos, posiciones o resultados confirmatorios.

**Resultado de esta entrega:** queda documentada la limitación de resolución y automatizado su cálculo. No existe nueva evidencia predictiva, no se activa la inferencia formal ni se acredita ausencia de sobreajuste.
