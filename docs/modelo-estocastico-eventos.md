# Trading: modelo estocástico de riesgo, noticias y decisiones de inversión

**Documento técnico de diseño · versión 1.0 (propuesta de investigación) · 25 de octubre de 2026**

## Resumen

Se propone un sistema predictivo para carteras multiactivo que distingue entre (i) rentabilidad esperada, (ii) volatilidad condicional, (iii) dependencias de mercado y residuales, (iv) saltos y eventos informativos, y (v) decisión de invertir bajo restricciones. La propuesta evita dos errores: considerar que una misma rentabilidad supuesta sirve para todos los instrumentos y etiquetar retrospectivamente toda desviación como «noticia» para absolver al pronóstico. La validación será estrictamente *ex ante*: cada predicción y cada dato empleado conservarán su fecha de conocimiento. La primera implementación será un candidato de volatilidad **GJR-GARCH(1,1) con innovaciones Student-t estandarizadas**, contrastado con EWMA en modo experimental, sin modificar aún las recomendaciones. La atribución de noticias, los saltos informativos y las correlaciones dinámicas se incorporarán únicamente después de acreditar mejoras fuera de muestra.

**Palabras clave:** cálculo estocástico, GJR-GARCH, efectos asimétricos, regímenes, datos *point-in-time*, eventos, riesgo de cartera, CVaR.

## 1. Problema y pregunta de investigación

Trading dispone de valoración fundamental, un universo multiactivo, simulaciones Monte Carlo y una matriz de covarianza EWMA. Sin embargo, la expectativa anual genérica de ciertos ETF —por ejemplo, 6 % para oro— no representa una tesis económica calibrada, y los saltos añadidos a una covarianza histórica que ya incluye crisis pueden contar el mismo riesgo dos veces.

**Pregunta central:** ¿la volatilidad asimétrica y la evidencia informativa disponible al corte mejoran la predicción probabilística y las decisiones de cartera respecto de una referencia parsimoniosa, sin utilizar información futura ni ocultar fallos del modelo?

Tres hipótesis refutables:
- **H1:** GJR-GARCH-t reduce la pérdida predictiva de volatilidad respecto de EWMA, de forma estable fuera de muestra.
- **H2:** eventos identificados con sellos temporales y sorpresas frente al consenso explican variación incremental, no ya capturada por factores o GARCH.
- **H3:** utilizar distribuciones y riesgos calibrados mejora utilidad neta o adecuación al mandato frente a mantener la cartera o un benchmark sencillo.

El incumplimiento de H1, H2 o H3 implica **no promover** el componente correspondiente a producción.

## 2. Información y prevención del sesgo retrospectivo

La filtración de información se evita imponiendo un conjunto de información disponible \(\mathcal F_t\). Un cálculo realizado al cierre de \(t\) puede usar únicamente precios, datos, revisiones y publicaciones conocidos hasta ese momento; predice \(t+1\) o el horizonte definido.

Cada observación guarda como mínimo: identificador, fecha económica, fecha y hora de publicación, primera fecha de disponibilidad, proveedor, fecha de descarga, revisión/vintage, moneda, transformación y calidad. Los datos publicados después del cierre no se utilizan como si hubieran sido conocidos durante la sesión. Los eventos intradía requieren distinguir su hora exacta y la ventana de precios analizada. Eventos sin timestamp verificable quedan **sin atribuir**.

Se emplean retornos logarítmicos ajustados por dividendos y splits, con calendarios compatibles. No se inventan valores ausentes ni se utilizan revisiones futuras de series macroeconómicas. Los retornos realizados y los índices de precios no sustituyen la tasa de crecimiento de beneficios ni las primas económicas en las expectativas *ex ante*.

## 3. Separación de media, riesgo y shocks

Para el activo \(i\), en frecuencia diaria:

\[
r_{i,t}=\mu_{i,t|t-1}+b_{i,t-1}^{\top}f_t+u_{i,t}+j_{i,t}.
\]

- \(\mu_{i,t|t-1}\) es la expectativa condicionada con información anterior al retorno.
- \(f_t\) son innovaciones factoriales comunes: mercado, tasas, crédito, moneda y sectores.
- \(u_{i,t}\) es el residual continuo, de media condicional cero.
- \(j_{i,t}\) es un salto adicional **solo si puede identificarse y calibrarse**, no un comodín para cualquier retorno inusual.

El motor actual ya contiene una estimación de correlaciones residuales por mercado bull/bear y sector. Es útil como diagnóstico de redundancia, pero **no equivale a dependencia causal ni elimina pérdidas conjuntas durante crisis**. Por ello, las simulaciones siguen reteniendo las exposiciones factoriales.

Para activos especializados se estimará \(\mu\) de manera diferenciada: acciones (beneficios, flujo de caja, dilución, valoración y prima factorial), bonos (carry, rolldown, cambios de curva, crédito, convexidad según disponibilidad), oro (tasas reales, USD y escenarios con incertidumbre explícita), y efectivo (rendimiento neto de la cuenta o cero si se asume no remunerado).

## 4. Volatilidad asimétrica: GJR-GARCH-t

Inicialmente, sobre residuos diarios adecuados (o retornos centrados, cuando todavía no existe una descomposición factorial válida):

\[
u_t=\sqrt{h_t}z_t,\quad z_t\sim t_{\nu}\ \text{estandarizada},\quad E[z_t]=0,\quad Var(z_t)=1,\quad \nu>2.
\]

\[
\boxed{h_{t+1}=\omega+\alpha u_t^2+\gamma\mathbf 1(u_t<0)u_t^2+\beta h_t.}
\]

La hipótesis económica para renta variable suele ser \(\gamma>0\): a igualdad de magnitud, un residuo negativo aumenta más la varianza futura que uno positivo. **Este es un efecto estadístico de noticias desfavorables, NO una clasificación automática de noticias periodísticas.**

Las restricciones del caso básico incluyen \(\omega>0\), \(\alpha,\beta,\gamma\ge0\) y \(\alpha+\beta+\gamma/2<1\), suponiendo innovaciones simétricas y sin covariables, para obtener varianza incondicional finita. No se impone \(\gamma>0\) universalmente: oro, deuda y divisas pueden no seguir la misma asimetría; se contrasta contra una versión simétrica.

En investigación se calibra por máxima verosimilitud con Student-t estandarizada, límites de parámetros, distintas inicializaciones y comprobación de convergencia. Se informan tamaño de muestra, parámetros, persistencia, errores y advertencias; si falla, se mantiene EWMA.

**Referencia:** \(\hat h_{t+1}^{EWMA}=\lambda\hat h_t+(1-\lambda)u_t^2\). La elección de \(\lambda\) y del periodo de entrenamiento también debe respetar las fechas de corte.

### ¿Por qué Student-t?

Los residuos financieros pueden presentar colas más pesadas que una normal. Student-t no elimina la necesidad de simular saltos extraordinarios, pero evita atribuir automáticamente cada valor extremo a una noticia extraordinaria.

## 5. Noticias reales y variables exógenas

Un evento debe identificarse **independientemente del movimiento de precio**: calendario de resultados, publicación de IPC o empleo, decisiones de bancos centrales, cambios regulatorios, hechos relevantes u otras noticias verificadas. Una noticia coincidente con una caída no prueba por sí sola causalidad.

La fase posterior propone GJR-GARCH-X:

\[
h_{t+1}=\omega+\alpha u_t^2+\gamma\mathbf1(u_t<0)u_t^2+\beta h_t
+\delta^\top X_t,
\]

donde \(X_t\) representa **variables conocidas antes de emitir la previsión de \(t+1\)**, como magnitudes absolutas de sorpresas publicadas durante \(t\), indicadores de calendario futuro ya anunciado y medidas escaladas de incertidumbre. No se permite insertar la sorpresa aún no conocida de \(t+1\). Para evitar negatividad, una parametrización alternativa usa componentes positivos de varianza o una función de enlace exponencial.

Ejemplo: si el IPC observado es 3,2 % y el consenso previo era 3,4 %, se utiliza la sorpresa \(-0,2\) puntos porcentuales y sus unidades; no se clasifica de manera automática «inflación alta = mala noticia».

Registro sugerido de evento: \`event_id\`, \`published_at_utc\`, \`known_at_utc\`, \`type\`, \`asset_ids\`, \`factor_ids\`, \`actual\`, \`consensus_asof\`, \`surprise\`, \`unit\`, \`source_url\`, \`quality\`, \`association_status\`. Las etiquetas deben admitir: confirmado como publicación; asociado estadísticamente; coincidencia débil; no atribuido.

## 6. Saltos, asimetría y no duplicación

Para incorporar saltos discontinuos, una extensión de Merton con intensidad condicional puede escribirse:

\[
\frac{dS_t}{S_{t^-}}=(\mu_t-\lambda_t E[J-1])dt+\sigma_t dW_t+(J-1)dN_t.
\]

La compensación evita sumar dos veces la deriva esperada por saltos. Sin embargo, **calibrar GARCH y además introducir saltos arbitrarios sobre retornos que ya contienen esos eventos puede duplicar riesgos**.

Se debe elegir una estrategia verificable:
1. Estimar conjuntamente difusión y saltos en un modelo identificable, o
2. Estimar primero saltos de forma robusta y calibrar la difusión sobre residuales coherentemente separados; conservar su incertidumbre de clasificación.

En la primera entrega **no se descomponen saltos**: los movimientos extremos cuentan como innovaciones y penalizan el ajuste. La atribución de noticias se registra por separado. Solo después de validar la separación se habilita un proceso de saltos.

## 7. Dependencia común, residual y dinámica

\[
\Sigma_t=B_t\Sigma_{f,t}B_t^\top+D_tR_{\varepsilon,t}D_t.
\]

La matriz factorial representa riesgo compartido; \(D_t\) contiene volatilidades condicionales y \(R_{\varepsilon,t}\) las correlaciones residuales. Un DCC-GARCH por factores y/o bloques sectoriales sería candidato posterior, no un ajuste simultáneo masivo sobre 177 activos sin suficiente historia.

Se mantienen explícitamente tres diagnósticos: correlación total, correlación residual tras controlar factores y dependencia de pérdidas extremas. **Solo las correlaciones residuales no bastan para decidir si la cartera puede resistir una crisis.**

Toda matriz aplicada a Monte Carlo debe ser simétrica y semidefinida positiva; se documentan regularización, shrinkage, pérdidas de observaciones y fallbacks.

## 8. Aprendizaje secuencial sin justificar errores

Para cada día:
1. Registrar la **distribución pronosticada** y la versión de parámetros antes de observar el retorno.
2. Observar el resultado y calcular \(z_t=u_t/\sqrt{h_t}\), probabilidad predictiva y métricas de calibración.
3. Registrar eventos con hora y fuente; la presencia de evento no borra ni mejora retrospectivamente el pronóstico archivado.
4. Actualizar el estado \(h_{t+1}\) con los coeficientes vigentes.
5. Reentrenar coeficientes solo en fechas predefinidas, con datos hasta el corte.
6. Promover un candidato nuevo únicamente si supera la validación fuera de muestra y controles de robustez.

Un movimiento de \(-4\sigma\) vinculado a resultados trimestrales sigue contando como excepción del modelo; puede ser un evento explicable económicamente y, simultáneamente, revelar subestimación de colas.

## 9. Validación empírica y criterio de promoción

Se evalúan varios cortes *walk-forward* (entrenamiento inicial, pronóstico fuera de muestra, reestimación periódica), usando idénticas fechas y universo para comparadores. Las métricas incluyen:
- **QLIKE:** \(L(h_t,u_t^2)=\log h_t+u_t^2/h_t\), reportando su diferencia contra EWMA. Si solo hay datos diarios, \(u_t^2\) es un proxy muy ruidoso de la varianza latente; con intradía validado se preferiría varianza realizada.
- Log-score predictivo Student-t / normal con parámetros **congelados** en cada corte.
- Cobertura, independencia y agrupación de excepciones VaR; CVaR/Expected Shortfall con evaluación pertinente, no mediante «aciertos» aislados.
- Estabilidad de \(\alpha,\beta,\gamma,\nu\), ganancias por sector y régimen, colas y estrés.
- En la etapa decisional: costos, turnover, utilidad neta, drawdown, probabilidad de pérdida y comparación con mantener, SHY y benchmarks apropiados.

**Regla de decisión:** la versión experimental no modifica la cartera. Un modelo nuevo se habilitará únicamente si (a) no usa información futura, (b) mejora de forma estable métricas predefinidas de pronóstico sobre EWMA, (c) no deteriora cobertura de riesgos extremos, y (d) demuestra beneficio económico incremental en evaluación separada. Sin mejora clara, se conserva la opción sencilla.

## 10. Plan de implementación en Trading

| Fase | Contenido | Estado del objetivo |
|---|---|---|
| 0 | Este artículo; contratos de datos, supuestos y pruebas de aceptación | Documento |
| 1 | GJR-GARCH-t en módulo aislado, referencia EWMA, validación *walk-forward*, reporte de calibración y anomalías | Primera implementación experimental |
| 2 | Registro de eventos point-in-time y prueba incremental de GARCH-X sin texto generativo como verdad | Pendiente |
| 3 | Modelo factorial dinámico; volatilidades por factor y correlaciones residuales regularizadas | Pendiente |
| 4 | Saltos y probabilidades condicionales con diagnóstico de doble conteo | Pendiente |
| 5 | Integración aprobada a simulación y optimización, pruebas de decisiones netas de costos | Pendiente |

Se almacenarán capturas **raw** y normalizadas, pronósticos inmutables, versión de código y parámetros. Los archivos públicos jamás contendrán claves, suscripciones privadas o contenido restringido de Bloomberg.

## 11. Limitaciones

El modelo no identifica causalidad de noticias por observar correlación temporal. Las etiquetas bull/bear no describen leyes económicas permanentes. Un GARCH diario puede servir para pronosticar volatilidad de corto plazo sin predecir la media a 12 meses. Toda elección de longitud de ventana, regularización o intensidad de shocks puede sobreajustarse. No se debe interpretar un incremento de QLIKE u otra métrica aislada como evidencia de rentabilidad de trading.

La investigación preserva la posibilidad de que la mejor decisión sea **mantener liquidez o una cartera pasiva**.

## Referencias

1. Bollerslev, T. (1986). *Generalized autoregressive conditional heteroskedasticity*. Journal of Econometrics, 31(3), 307–327. https://doi.org/10.1016/0304-4076(86)90063-1
2. Glosten, L. R., Jagannathan, R., & Runkle, D. E. (1993). *On the Relation between the Expected Value and the Volatility of the Nominal Excess Return on Stocks*. Journal of Finance, 48(5), 1779–1801. https://doi.org/10.1111/j.1540-6261.1993.tb05128.x
3. Engle, R. F., & Ng, V. K. (1993). *Measuring and Testing the Impact of News on Volatility*. Journal of Finance, 48(5), 1749–1778. https://doi.org/10.1111/j.1540-6261.1993.tb05127.x
4. Engle, R. F. (2002). *Dynamic Conditional Correlation: A Simple Class of Multivariate GARCH Models*. Journal of Business & Economic Statistics, 20(3), 339–350. https://doi.org/10.1198/073500102288618487
5. Hansen, P. R., & Lunde, A. (2005). *A Forecast Comparison of Volatility Models: Does Anything Beat a GARCH(1,1)?* Journal of Applied Econometrics, 20(7), 873–889. https://doi.org/10.1002/jae.800
6. Christoffersen, P. F. (1998). *Evaluating Interval Forecasts*. International Economic Review, 39(4), 841–862.
