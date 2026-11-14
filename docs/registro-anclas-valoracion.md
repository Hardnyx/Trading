# Registro: anclas de retorno de índices y bonos, 1900–2018

**Fecha de registro:** 14-nov-2026 UTC, **antes de calcular anclas o retornos.** Contrato: [estudio-anclas-valoracion-v1.json](estudio-anclas-valoracion-v1.json).

**Pregunta.** ¿Las anclas de retorno que usa el motor, calculadas solo con información de cada fecha, habrían pronosticado el retorno total de los 12 meses siguientes mejor que la media histórica? Es la base del sesgo del fondo hacia mercados más baratos.

**Qué se prueba.**

- **Acciones:** la fórmula del motor para índices, prior 6 % + 0,6 × (rendimiento de beneficios + inflación − 6 %). Se calcula sobre el S&P 500 de Shiller, con beneficios rezagados 3 meses y la inflación de los 12 meses previos (el breakeven a 10 años no existe antes de 2003).
- **Bonos:** el carry del motor, es decir, el rendimiento al vencimiento del Treasury a 10 años, contra el retorno de comprar ese bono y venderlo un año después.

**Comparación y regla.** Referencia: la media expansiva de todos los retornos de 12 meses ya conocidos en cada fecha, desde 1871. Muestra principal: 119 orígenes de enero, de 1900 a 2018, sin solapamiento. Métrica: R² fuera de muestra. Prueba: Clark-West unilateral.

- *Respaldada* si R² > 0 y p < 0,05.
- *No respaldada* si R² ≤ 0.
- *Inconclusa* en otro caso.

Los otros meses de origen, los subperiodos y la referencia constante de 6 % son descriptivos.

**Lo que no se prueba.** Los ETF internacionales (no hay historia gratuita de su P/E), las anclas por componentes de los ETF de EE. UU. y de las acciones (faltan fundamentales con fecha de publicación), el crédito y los escenarios. La idea del rendimiento de beneficios proviene de una literatura que estudió esta misma serie, así que la prueba no es independiente de ella. El resultado no cambia el motor ni el fondo.

## Resultado (14-nov-2026 UTC)

Registro publicado en [`6e643d8`](https://github.com/Hardnyx/Trading/commit/6e643d8a) antes de calcular. Ejecución: `python scripts/valuation_anchor_oos.py`. Resumen: [auditorias/valuation-anchor-oos-1900-2018.json](auditorias/valuation-anchor-oos-1900-2018.json).

| Ancla | R² fuera de muestra frente a la media histórica | Clark-West p | Veredicto |
|---|---:|---:|---|
| **Acciones** (rendimiento de beneficios + inflación, contraído al 6 %) | **−3,9 %** | 0,34 | **No respaldada** |
| **Bonos** (rendimiento al vencimiento del Treasury a 10 años) | **+27,9 %** | 0,006 | **Respaldada** |

**Acciones.** A 12 meses, el ancla pronostica peor que la media histórica en los 12 meses de origen (entre −2,5 % y −4,7 %), en 1900–1959 (−6,1 %) y en 1990–2018 (−5,6 %); solo mejora en 1960–1989 (+7,7 %, p = 0,10). En promedio **subestima el retorno en 2,6 puntos por año**. Supera por poco a un 6 % constante (+1,4 %). La literatura encuentra poder predictivo del rendimiento de beneficios a horizontes de 5 a 10 años, no a uno; el motor lo usa a un año.

**Bonos.** El carry predice bien en los 12 meses de origen (R² entre +27,6 % y +31,3 %) y en los tres subperiodos, con error medio casi nulo (+0,1 puntos).

**Implicación para el fondo.** El sesgo hacia acciones internacionales se apoya en diferencias de rendimiento de beneficios; en la serie de EE. UU. ese método no supera a la media histórica a un año y además subestima el retorno de las acciones, lo que empuja al motor hacia menos renta variable. La parte de bonos del fondo descansa en un ancla que sí está respaldada. Es una prueba sobre EE. UU.; los ETF internacionales no se pudieron probar.
