# Error familiar con cuatro hipótesis nulas verdaderas

**Hito:** H0.3. **Fecha:** 9 de noviembre de 2026 UTC. **Alcance:** diagnóstico sintético de control fuerte del error familiar, sin retornos bursátiles.

El diagnóstico anterior [bajo el nulo global](diagnostico-bootstrap-familiar.md) estudió únicamente siete hipótesis nulas verdaderas. Holm debe controlar el error familiar también cuando algunas hipótesis son falsas. Este estudio mantiene los siete contrastes, la corrección Holm, 10 000 remuestreos, los bloques de 12 y 24 meses y el protocolo v2 **sin cambios**.

## Diseño fijado

- Siete series mensuales Gaussianas AR(1) estacionarias con autocorrelación 0,6 y varianza marginal unitaria.
- Las series con índices 0, 1, 2 y 3 tienen media cero: son las **cuatro hipótesis verdaderas**. Las series 4, 5 y 6 reciben un desplazamiento fijo de +0,5 desviaciones típicas incondicionales al mes: son las **tres hipótesis falsas**.
- Longitudes de 96 y 192 meses; correlación contemporánea 0 y 0,75; bloques circulares de 12 y 24 meses.
- En cada una de las ocho combinaciones, 128 réplicas sintéticas, con semillas estables derivadas de 20261110. El remuestreo utiliza los mismos índices mensuales para los siete contrastes en cada réplica.
- Se calcula el escalonamiento Holm **completo**, no solo su primer umbral. Los valores p del control analítico se obtienen de la distribución gaussiana con el parámetro AR(1) verdadero del generador. Ese parámetro no es conocido para los resultados de Trading.

Se mide la frecuencia de rechazar **al menos una de las cuatro hipótesis nulas verdaderas**, que es la tasa de error familiar relevante bajo este nulo parcial. Los rechazos de las tres hipótesis desplazadas se registran aparte, sin interpretarlos como potencia económica.

## Resultado sintético reproducido localmente

| Meses | Correlación transversal | Bloque | Error familiar bootstrap | Error familiar analítico | Solo bootstrap / solo analítico | Alguna hipótesis desplazada rechazada |
|---|---:|---:|---:|---:|---:|---:|
| 96 | 0,00 | 12 | 18/128 (14,06 %) | 7/128 (5,47 %) | 11 / 0 | 120/128 |
| 96 | 0,00 | 24 | 25/128 (19,53 %) | 7/128 (5,47 %) | 18 / 0 | 121/128 |
| 96 | 0,75 | 12 | 12/128 (9,38 %) | 3/128 (2,34 %) | 9 / 0 | 105/128 |
| 96 | 0,75 | 24 | 21/128 (16,41 %) | 3/128 (2,34 %) | 18 / 0 | 111/128 |
| 192 | 0,00 | 12 | 14/128 (10,94 %) | 5/128 (3,91 %) | 9 / 0 | 128/128 |
| 192 | 0,00 | 24 | 20/128 (15,62 %) | 5/128 (3,91 %) | 15 / 0 | 128/128 |
| 192 | 0,75 | 12 | 11/128 (8,59 %) | 5/128 (3,91 %) | 6 / 0 | 124/128 |
| 192 | 0,75 | 24 | 12/128 (9,38 %) | 5/128 (3,91 %) | 8 / 1 | 126/128 |

El valor nominal a contrastar es **5 % de error familiar**, no 0,05/7 por hipótesis. Las frecuencias se basan en 128 réplicas independientes por escenario y tienen incertidumbre Monte Carlo significativa; el artefacto incluye intervalos Wilson del 95 %. Los dos bloques de un escenario comparten las mismas series originales y no constituyen réplicas independientes adicionales.

La prueba unitaria compara las decisiones vectorizadas con los valores p completos del remuestreo de referencia bajo exactamente los **mismos índices**, tanto para 96 como para 192 meses. La vectorización no cambia la definición del estadístico ni el umbral.

## Reproducción

Ejecutar desde la raíz del repositorio:

    python -m unittest tests.test_confirmatory_partial_null_bootstrap
    python scripts/confirmatory_partial_null_bootstrap.py --verify --output out/confirmatory-partial-null-bootstrap-v1.json

El segundo comando genera las ocho filas y conserva las discordancias pareadas de ambos procedimientos.

## Interpretación y límites

Este segundo diagnóstico detecta tasas simuladas de falso rechazo de hasta **25/128 = 19,53 %**, frente al 5 % nominal, aun con una parte de la familia bajo alternativas positivas. Refuerza el hallazgo de calibración insuficiente del bootstrap centrado para los procesos elegidos, mientras el control con parámetros conocidos se comporta de forma compatible con su nivel nominal y no es una alternativa aplicable al mercado real.

No se ha auditado toda posible configuración de nulos parciales, tampoco la distribución conjunta real de siete puntuaciones con horizontes distintos, observaciones faltantes y resultados económicos asimétricos. Los resultados no prueban control fuerte, no estiman potencia de Trading y no justifican modificar a posteriori las pruebas registradas. **H0.3 permanece abierto, v2 inactivo y la capacidad predictiva sin acreditar.** Un futuro procedimiento inferencial distinto requiere justificación independiente y registro prospectivo versionado, sin reutilizar resultados examinados para escogerlo.
