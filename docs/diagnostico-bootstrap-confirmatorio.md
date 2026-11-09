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
