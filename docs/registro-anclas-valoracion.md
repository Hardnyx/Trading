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
