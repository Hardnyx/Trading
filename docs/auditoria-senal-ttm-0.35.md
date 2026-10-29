# Señal TTM e IC · resultado al 29-oct-2026

Se reconstruyó la señal con el extractor TTM, la valoración y la exposición
al mercado del código actual, sobre el mercado congelado del commit
`8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5`, precios al 28-oct.
El [protocolo](protocolo-senal-ttm-0.35.md) se fijó antes de leer los
resultados estadísticos. Se consultaron las 160 empresas: no hubo fallos de
descarga y se conservaron 10.538 versiones de observaciones de BPA.
La ausencia de conceptos estándar, como en V, no se rellena inventando BPA.

El resultado mejora la fidelidad del proxy anual anterior, pero **no valida
el IC de 0,05 ni la rentabilidad de la cartera**. Los datos siguen siendo
reconstruidos y la evidencia temporal anual es corta.

## Qué se midió

Solo se admiten informes con fecha anterior al origen. Se conserva la
reconstrucción anual + YTD − YTD comparable o anual directo y se rechaza
fallback FY, conflictos y componentes con bases de acciones mezcladas.
Es la fórmula TTM del código; no una certificación contable independiente
de esa aproximación por acción. Los dividendos se limitan a la ventana
histórica conocida por ex-fecha, sin usar el dividendo actual para rellenar.

Se vuelve a ejecutar `resolveAssumptions`, `valuation` y `marketExposure`.
El crecimiento y el múltiplo de referencia del catálogo permanecen fijos.
Se compara el ranking de la señal con el retorno posterior residual de SPY,
usando beta estimada solo con precios anteriores. La referencia simple
BPA/precio usa las mismas acciones y resultados posteriores.

También se mide Pearson entre el score limitado a ±3 y el residuo dividido
por la volatilidad estimada al origen. Esta medida se aproxima más al
concepto de habilidad que un ranking, pero no reproduce las confianzas y
la neutralización de holdings históricas del ancla final de producción.

## Resultados

Los intervalos son descriptivos por métrica, con bloques de 1/3/12 meses,
2.000 remuestreos y semilla fijada. No corrigen multiplicidad ni resuelven
los sesgos de selección. No se cuentan las acciones como orígenes
temporales independientes.

| Horizonte | Orígenes mensuales | Acciones por origen | IC de rangos TTM | Banda por bloques | IC BPA/precio | Diferencia TTM − referencia, banda |
|---|---:|---:|---:|---|---:|---|
| 21 sesiones | 47 | 135–148 | 0,0328 | [−0,0155; 0,0801] | 0,0189 | 0,0139 [−0,0176; 0,0466] |
| 63 sesiones | 45 | 135–148 | 0,0512 | [−0,0155; 0,0993] | 0,0321 | 0,0191 [−0,0243; 0,0623] |
| 252 sesiones | 36 | 135–142 | 0,0870 | [0,0265; 0,1337] | 0,0646 | 0,0224 [−0,0697; 0,1002] |

Pearson entre score y residuo estandarizado da 0,0412 a 21 sesiones,
0,0617 a 63 y 0,0922 a 252. Sus bandas son, respectivamente,
[−0,0037; 0,0873], [−0,0019; 0,1122] y [0,0330; 0,1466].

La muestra anual va del 31-oct-2022 al 30-sep-2025. Son 36 orígenes con
resultados posteriores solapados: el subconjunto sin solapamiento conserva
**solo tres**. Su IC de rangos medio es 0,0764; tres observaciones no bastan
para acreditar una habilidad estable en varios regímenes.

## Interpretación para la confianza

Hay una asociación anual positiva en esta reconstrucción. No debe
descartarse ni convertirse en una certificación predictiva. El crecimiento,
múltiplos y universo actuales se eligieron después de muchos de los
retornos observados; el filtro por fecha del informe no elimina ese sesgo.
Las respuestas actuales pueden incluir revisiones del proveedor y no
verifican la primera disponibilidad exacta de cada valor.

La mejora frente a BPA/precio **no queda resuelta en ninguno de los tres
horizontes**. Eso limita la justificación empírica para que los supuestos
individuales de crecimiento y re-rating determinen diferencias precisas de
peso. No demuestra que carezcan de valor; tampoco demuestra que lo añadan
frente a una regla mucho más simple.

El 0,0922 de Pearson no reemplaza el 0,05 declarado. La relación entre
score, confianza subjetiva, volatilidad y neutralización del benchmark
requiere su propia calibración. Menos aún autoriza duplicar el IC, cuya
[sensibilidad](auditoria-supuestos-economicos-0.35.md) cambia materialmente
los líderes del conjunto de carteras.

La producción permanece en 0.35.0 y el núcleo en 1.0.0, sin cambios de
parámetros o pesos promovidos desde este estudio. Siguen abiertos:

1. Sellar y evaluar la señal completa emitida con datos realmente observados,
   por versión y fecha, sin reescribir su cohorte al modificar el modelo.
2. Contrastar el valor incremental frente a BPA/precio y referencias simples
   con universo histórico, vintages verificables y mayor evidencia temporal.
3. Validar errores de las anclas de crecimiento y retorno del benchmark.
   Ordenar acciones y predecir rentabilidades absolutas son pruebas distintas.

## Trazabilidad y reproducción

El [resumen medido](auditorias/ttm-signal-summary-2026-10-29.json) conserva
estadísticas por origen, exclusiones y hashes. Los
[datos TTM congelados](auditorias/ttm-signal-inputs-2026-10-29.json.gz)
conservan componentes, todas las versiones SEC necesarias, fuentes y fechas
de observación. Las respuestas completas se identifican por hash; el paquete
incluye sus conceptos EPS necesarios, no el resto de conceptos ajenos al estudio.

```sh
mkdir -p out
git show 8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5:dist/data/market.json > out/ttm-market.json
gzip -dc docs/auditorias/ttm-signal-inputs-2026-10-29.json.gz > out/ttm-signal-facts.json
node scripts/ttm_signal_replay.mjs --market out/ttm-market.json
python scripts/ttm_signal_research.py summarize
```

Las exclusiones suman instancias acción-origen, no empresas distintas:
97 por bases mezcladas, 164 por falta de TTM/fallback FY, 332 por BPA no
positivo, 226 por ajustes futuros de precio distintos de splits sin
conciliación y 141 por señal o exposición no utilizables. Durante este
contraste no se filtraron candidatas por su retorno posterior; el universo
actual conserva su sesgo de selección ex post.

CI comprueba los invariantes y repite el diagnóstico en modo sombra,
conservando entradas y resultados durante 90 días. La captura fechada de
este estudio queda además en el repositorio. Una repetición con nuevos datos
no sustituye esa evidencia congelada ni autoriza operaciones.
