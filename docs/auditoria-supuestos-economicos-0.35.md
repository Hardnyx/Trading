# Qué sostiene la composición · 29-oct-2026

La propuesta canónica vigente con precios del 28-oct es SPY 35%, LQD 35%,
TIP 25%, CASH 5%, desde USD 100.000 en efectivo. Se comprobó en el registro
Node/Chrome del commit `5667d48`, job `123416012077`. No es una cuenta real
ni se ejecutaron operaciones. Este diagnóstico no cambia la producción.

## Separación de causas

Se mantienen fijos los datos completos del commit `17f5fda`, las 19 cestas
ex post de las auditorías anteriores, el horizonte anual y el mandato de
crecimiento USD sin retiros. La semilla `0x71e4a9c3` se fijó antes del
experimento. Se evalúan 1.500 parejas antitéticas por caso (3.000
trayectorias), con medias por pareja para medir error. No se vuelve a buscar
una cartera ni se cambian semillas para mejorar el resultado.

Se declaran 17 casos: base, sin re-rating, baja convicción ya existente,
prima CAPM 0/2/4%, IC 0/0,10, crecimiento del catálogo ×0,5/×1,5, pérdida
esperada de crédito ×2/×3, exposición al spread ×1,5/×3, magnitudes de tasas
nominales ×0/×2 y un estrés conjunto adicional. Son sensibilidades elegidas,
**no intervalos estimados de parámetros ni escenarios con probabilidades**.

La prima CAPM cambia la referencia de equilibrio y limita las anclas ETF
según la regla existente; no suma ese porcentaje directamente al retorno
final del fondo. El crecimiento se cambia también en constituyentes fuera
de los 40 activos simulados. Las cifras contables, precios, TIR, fechas y
covarianza no se sobrescriben. Se conserva el no re-rating al reconstruir
anclas de un estrés combinado.

La familia de 6.800 contrastes cubre selección entre candidatas y cambios
pareados frente al caso base. Las bandas son aproximaciones de Monte Carlo
con conversión monetaria estimada. **No contienen el error económico del
modelo**. Para cambios firmemente negativos, también se conserva una cota
superior negativa: no se recorta el signo como si fuese pérdida de oportunidad.

## Efecto sobre la misma cartera publicada

Las cifras son cambios en su equivalente cierto condicional, respecto del
caso base, para USD 100.000. No son retornos observados ni ganancias por operar.

| Cambio aislado | Cambio estimado | Banda aproximada de simulación |
|---|---:|---:|
| Prima CAPM 0% | USD −668,72 | [−671,95; −665,49] |
| Prima CAPM 2% | USD −27,98 | [−28,11; −27,84] |
| Prima CAPM 4% | USD +468,16 | [+465,90; +470,42] |
| Crecimiento del catálogo ×0,5 | USD −517,84 | [−520,52; −515,15] |
| Crecimiento del catálogo ×1,5 | USD +518,28 | [+515,60; +520,96] |
| IC 0 o IC 0,10 | USD 0 | [0; 0] |
| Sin re-rating | USD −73,10 | [−89,84; −56,36] |
| Pérdida de crédito ×2 | USD −85,11 | [−85,34; −84,88] |
| Pérdida de crédito ×3 | USD −170,22 | [−170,68; −169,77] |
| Exposición al spread ×1,5 | USD −29,77 | [−91,13; +31,63] |
| Exposición al spread ×3 | USD −140,02 | [−370,89; +91,36] |
| Magnitud de tasas nominales ×0 | USD −4,96 | [−342,93; +334,11] |
| Magnitud de tasas nominales ×2 | USD −106,35 | [−443,20; +231,59] |

Las sensibilidades de prima y crecimiento superan ampliamente USD 100 en
esta configuración. Simular más podría estrechar su error numérico, pero
no decidiría qué prima o crecimiento son correctos.

El cambio de tasas mantiene probabilidades, inflación y shocks de beneficios;
solo escala `rateShift` y `rateJumpBps`. Para TIP, la inflación sigue afectando
el rendimiento real y el principal. El ancla media del bono se conserva por
el centrado del modelo; cambian los escenarios y la utilidad. Las bandas de
tasas y spread abarcan cero: con este presupuesto no se resuelve su efecto
sobre utilidad. No es evidencia de que esos riesgos sean pequeños.

## El IC afecta la selección aunque no mueva esta cesta

La neutralización frente al benchmark hace que variar el IC no cambie el
retorno central de esta cesta de SPY y bonos. Eso no valida el IC ni significa
que el parámetro no importe. Con IC cero, la propia cesta publicada es líder
puntual del conjunto en el caso aislado. Con IC 0,10, el líder incluye 45%
de renta variable y reasigna el 65% del capital respecto de la publicada;
la mejora equivalente puntual es USD 764,65 y su cota inferior USD 293,91.
Es una diferencia dentro del modelo obtenida duplicando una convención,
no evidencia para duplicarla o comprar esas acciones.

Baja convicción combina varios cambios: prima e IC cero, crédito estresado,
menor confianza y no re-rating. Su líder puntual tiene 0% de acciones y
reasigna el 95% del capital respecto de la publicada; el déficit de esta
última frente a su propio caso base es USD 782,58. No puede atribuirse ese
giro exclusivamente a la prima cero: en el caso aislado de prima cero el
líder aún tiene 35% de acciones, gracias al resto de supuestos.

En el caso base, el líder puntual reasigna el 65% y supera la cesta publicada
en USD 328,14, pero su cota inferior es USD 61,03, por debajo del umbral
USD 100. La búsqueda original además se decide con cinco modelos y una
confirmación independiente. Ninguno de estos líderes de un caso aislado
constituye una autorización de transición.

Los líderes se ordenan por utilidad puntual antes de exigir todos los límites
de riesgo; el de tasas ×2 falla el diagnóstico de CVaR. El resultado conserva
esas exclusiones por separado y no los presenta como carteras admisibles.

El estrés conjunto exploratorio (prima e IC cero, pérdida y spread ×3,
tasas ×2, sin re-rating) reduce el equivalente de la cesta publicada en
USD 1.016,01, banda [−1.221,41; −810,21]. Su diferencia frente al líder de
ese caso es USD 299,55, con cota inferior negativa. Tampoco acredita rotarla.

## Qué evidencia sostiene cada bloque

| Bloque | Evidencia disponible | Lo que falta para sostener su uso predictivo |
|---|---|---|
| TIR, duración y gastos | Perfil fechado del emisor. LQD: TIR 5,97%, duración 7,64037 y gastos 0,14%, datos 27-oct. IGSB: TIR 5,47%, duración 2,64051 y gastos 0,04% | Conciliación y prueba del retorno al horizonte, rolldown, curvas y costes; una TIR no es una predicción validada de retorno total anual |
| Pérdida esperada IG y beta de spread | Convenciones del código: 0,25% y beta 1; los perfiles sostienen TIR/duración, no estas calibraciones | Defaults, recuperaciones, ratings y vencimientos comparables; prueba de la sensibilidad a spreads fuera de muestra |
| Prima bursátil y crecimiento | Anclas por bloques/holdings y supuestos del catálogo; 0 instrumentos con `analyst_estimates` en la captura | Vintages originales, errores de anclas y primas comparados con referencias, información disponible en cada origen |
| IC 0,05 | Estructura de Grinold–Kahn y proxy anual reconstruido: IC 0,037, intervalo por bloques [−0,082; 0,082], según el estado de validación | Señal TTM exacta, universo al origen y retornos posteriores; el proxy no certifica IC 0,05 |
| Re-rating y escenarios macro | Convenciones registradas; curva al corte y probit para una parte de las probabilidades | Magnitudes, reversión y distribución conjunta calibradas y contrastadas fuera de muestra |

Los perfiles y hashes originales se conservan en el resultado. Se consultó
la [página oficial de LQD](https://www.ishares.com/us/products/239566/lqd-ishares-iboxx-investment-grade-corporate-bond-etf)
para contrastar identidad y definición de sus datos; el experimento sigue
usando la captura congelada, sin sustituirla por observaciones posteriores.
La [investigación de la Reserva Federal sobre spreads y exceso de prima de
bonos](https://www.federalreserve.gov/monetarypolicy/files/FOMC20160304memo05.pdf)
distingue compensación por defaults de otros componentes de la prima.
No se convierte el spread completo en pérdida esperada ni ese estudio de
2016 en una calibración para estos ETF en 2026.

## Consecuencia para la confianza y prioridad

El problema no se agota en Monte Carlo. La asignación puede cambiar mucho
porque el equilibrio de renta variable y la habilidad declarada modifican
la comparación entre acciones e índices. El crecimiento supuesto también
mueve materialmente la cesta de índice. La prioridad de validación queda:

1. Señal TTM e IC exactos y ancla de crecimiento/prima del benchmark con
   vintages; estas convenciones mueven retornos o selección significativamente.
2. Pérdidas de crédito y exposición a spreads con datos comparables y
   calibración conjunta. No se adopta una pérdida de 0,75% por haber probado ×3.
3. Tasas/re-rating y riesgo conjunto, con mayor precisión y episodios diversos.

No se cambian supuestos de producción ni se elige el caso que favorezca una
cartera deseada. Se identifican condiciones y carencias de evidencia. La
calibración predictiva, la cobertura de búsqueda y la operativa real siguen
abiertas. Una probabilidad de pérdida publicada continúa siendo condicional,
no una frecuencia de mercado certificada.

## Reproducción y controles

```sh
node --test tests/economic-sensitivity.test.mjs
node scripts/economic_sensitivity_research.mjs
```

El [resultado completo](auditorias/economic-sensitivity-2026-10-29.json)
conserva cada caso, candidata, ancla, perfil, banda firmada y hashes. Para
repetir la auditoría fechada se usan el código de esta revisión y los ficheros
completos de `dist/data/market.json` y `dist/data/volatility.json` del commit
`17f5fda9cfd88330194c2288e158b43ef1a8fcbd`, pasados con `--market` y
`--volatility`. Los archivos de metadatos sin históricos no los reemplazan.

Las pruebas cubren independencia de pérdidas y spread, conservación de
observaciones contables, efecto sobre constituyentes no simulados,
centrado de tasas y bandas negativas sin recorte artificial. CI ejecuta un
contraste acotado (`--quick`, 100 parejas) sobre la cesta fechada de referencia
y conserva el artefacto durante 90 días. No afirma evaluar cualquier cuenta
ni sustituye la propuesta vigente de futuras capturas.
