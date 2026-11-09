# Diagnóstico de muestra finita del bootstrap confirmatorio

**Hito:** H0.3. **Fecha:** 9 de noviembre de 2026 (UTC). **Estado:** simulación de diseño, sin datos de rendimiento ni evidencia predictiva.

El [protocolo prospectivo v2](protocolo-confirmacion-integral-v2.json) exige una muestra mínima de 96 meses admisibles y maduros, bootstrap circular por bloques de 12 y 24 meses, 10 000 remuestreos y siete contrastes primarios bajo Holm unilateral al 5 %. Un mínimo operativo de cuatro bloques de 24 meses no garantiza que el procedimiento controle el error de tipo I o tenga potencia suficiente.

El script `scripts/confirmatory_bootstrap_diagnostic.py` ejecuta una **simulación puramente sintética** del contraste bootstrap centrado en cero. Cada serie representa efectos mensuales pareados de una **única prueba hipotética**. No abre cotizaciones, rendimientos, posiciones, resultados confirmatorios ni datos históricos de Trading.

## Escenarios definidos por anticipado

| Dimensión | Valores supuestos |
|---|---|
| Meses consecutivos elegibles | 96 y 192 |
| Bloques circulares del protocolo | 12 y 24 meses |
| Dependencia AR(1) estacionaria | 0,0 y 0,6 |
| Efecto sintético en desviaciones estándar incondicionales | 0 y +0,5 |
| Réplicas sintéticas por escenario | 512 |
| Remuestreos máximos por réplica | 10 000 |
| Umbral de rechazo examinado | Primer paso de Holm: 0,05 / 7 |

La desviación estándar es hipotética, no una magnitud económica mínima para Trading. La simulación de efecto cero describe frecuencia de rechazo bajo un modelo nulo particular; la de +0,5 describe potencia **solo bajo ese efecto AR(1) hipotético**. Cada tasa lleva un intervalo Wilson del 95 % que recoge incertidumbre de Monte Carlo, no incertidumbre sobre habilidad predictiva.

Para reproducir:

```bash
python scripts/confirmatory_bootstrap_diagnostic.py --verify \
  --output out/confirmatory-bootstrap-sensitivity-v1.json
```

El script comprueba el contrato registrado sin modificarlo. Para evaluar la decisión de rechazo, puede detener una réplica de manera exacta cuando ya ha contado demasiadas excedencias del bootstrap para superar el umbral. Esa optimización equivale a completar los 10 000 sorteos **para el veredicto binario de rechazo**, no es un análisis interino ni una búsqueda de semillas. Las demás cifras del simulador se calculan sobre la misma rejilla fija.

## Alcance y decisión pendiente

Este diagnóstico examina el **primer paso de Holm para una sola serie**; **no** simula siete pruebas simultáneas, sus correlaciones, el error familiar efectivo ni el bootstrap conjunto de horizontes e instrumentos. El proceso generador AR(1) gaussiano no representa regímenes, heterocedasticidad ni pérdidas extremas de mercado. No permite afirmar que 96 meses sean suficientes ni elegir una configuración por su tasa de rechazos después de observarla.

H0.3 seguirá abierto hasta justificar umbrales económicos por objetivo con una escala independiente de la muestra confirmatoria y analizar potencia/validez del contraste registrado frente a escenarios defendibles. Cualquier modificación al protocolo v2 necesitará nueva versión explícita y cohorte prospectiva nueva; las 48 fechas retrospectivas examinadas no pueden convertirse en un holdout independiente.

**Regla de aceptación:** las pruebas y los reportes generados son evidencias del comportamiento del algoritmo bajo supuestos sintéticos, no un resultado financiero. No cambian el motor, el conjunto de siete hipótesis, la semilla registrada, ni los umbrales y la activación del estudio.

## Resultados sintéticos verificados en CI

El [commit `7096d89`](https://github.com/Hardnyx/Trading/commit/7096d8963f4069ba872d461645ae733522eb3718) aprobó la [CI 42642546232](https://github.com/Hardnyx/Trading/actions/runs/42642546232), incluidas **400 pruebas Python**. El artefacto `confirmatory-bootstrap-sensitivity` conserva los 16 escenarios y sus intervalos Monte Carlo, producidos con la rejilla y semilla fijadas antes de inspeccionar resultados.

El **primer umbral nominal de Holm** es `0.05/7 = 0.00714286`, equivalente al 0,7143 % de los experimentos bajo el nulo si el test individual tuviera esa tasa de error.

| Meses | Correlación AR(1) supuesta | Bloque | Rechazos con efecto nulo | Frecuencia | Intervalo Wilson 95 % |
|---|---:|---:|---:|---:|---:|
| 96 | 0,0 | 12 | 10 / 512 | 1,95 % | 1,06–3,56 % |
| 96 | 0,0 | 24 | 16 / 512 | 3,13 % | 1,93–5,02 % |
| 96 | 0,6 | 12 | 13 / 512 | 2,54 % | 1,49–4,30 % |
| 96 | 0,6 | 24 | 22 / 512 | 4,30 % | 2,85–6,42 % |
| 192 | 0,6 | 12 | 9 / 512 | 1,76 % | 0,93–3,31 % |
| 192 | 0,6 | 24 | 16 / 512 | 3,13 % | 1,93–5,02 % |

Bajo un efecto **hipotético** de +0,5 desviaciones estándar incondicionales, el escenario AR(1) 0,6 y bloque 24 rechazó 359/512 (70,12 %) a 96 meses y 453/512 (88,48 %) a 192 meses. Estos porcentajes **no son potencia del motor** y, dado que el procedimiento exhibe rechazos nulos elevados en esta simulación, **no justifican** concluir que la potencia confirmatoria sea aceptable.

**Conclusión de diseño:** estos resultados ofrecen una advertencia cuantitativa de posible comportamiento anticonservador del bootstrap centrado con pocos bloques, bajo al menos un proceso generador de datos sintético. El contraste preinscrito **no debe activarse para afirmar ventaja estadística** hasta un análisis de calibración más amplio del tamaño finito y de la dependencia conjunta de la familia de siete pruebas. No se cambia v2, sus hipótesis, semillas, tamaños de bloque, umbrales o fechas de inicio después de observar la simulación; cualquier reemplazo necesitará nuevo protocolo prospectivo y confirmación independiente.
