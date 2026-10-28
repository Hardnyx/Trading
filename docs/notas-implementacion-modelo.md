# Notas de implementación conservadas

Estas notas describen fórmulas y versiones históricas; el [estado vigente](estado-validacion.md) identifica qué ejecuta el motor actual.

## 12. Integración y cambios de seguridad en la versión 0.7.0

La matriz de sensibilidad de correlación reconstruye el factor SPY y los residuos de la covarianza realmente estresada, evitando conservar una factorización obsoleta. El modo híbrido de volatilidad utiliza GJR solo con evidencia walk-forward más estricta; de no existir, permanece en EWMA diario. El modelo de saltos Merton anterior requiere una selección explícita, porque sus intensidades no proceden de noticias verificadas. La preselección de hasta 40 instrumentos usa señales financieras prospectivas ajustadas por incertidumbre y mantiene representación sectorial. La concentración de SHY se compara con alternativas de menor tope bajo el mismo conjunto de escenarios, sin imponer pesos arbitrarios. Las asociaciones informativas y GARCH-X siguen pendientes de validación científica.


## 13. Estado operativo posterior al parche 0.7.2

Se corrigió el error de exploración por el que un límite bajo de SHY podía arrojar «ninguna candidata verificada» aun existiendo efectivo factible. Cada frontera de concentración añade ahora CASH y escalones SHY/CASH, y no promueve carteras fuera de la verificación final.

Se introdujo un benchmark de SPY reservado **solo para investigación** cuando el retorno de ese ETF no está calibrado. Se especifica una prima accionaria hipotética de 3,5 pp respecto de DGS3MO con banda ±15 pp; no es una previsión respaldada por un backtest y, por diseño, no puede usarse como autorización de compra.

Para activos de renta fija se distingue carry anual del efecto de precio de un desplazamiento de tasas. La variación de precio se aproxima mediante duración modificada y convexidad proxy:


```math
\frac{P_T}{P_0} \approx 1 - D_{\mathrm{mod}}\,\Delta y
+ \frac{1}{2}\,C_{\mathrm{proxy}}\,(\Delta y)^2,
\qquad C_{\mathrm{proxy}} = D_{\mathrm{mod}}(D_{\mathrm{mod}}+1).
```

La rentabilidad anualizada de escenario se calcula con el carry observado neto de gastos, multiplicado por esa aproximación de precio. Los escenarios de rates se aplican una sola vez a cada trayectoria. Ello no modela una curva de rendimiento completa, reinversión de cupones ni opciones del bono; son pendientes de calibración, no funcionalidades terminadas.

**Advertencia vigente:** las colas conjuntas de Monte Carlo siguen siendo gaussianas, las hipótesis macro no son probabilidades empíricas verificadas y solo un subconjunto de 40 activos se optimiza por corrida. Los cálculos de GJR-t todavía no constituyen identificación semántica de noticias o un GARCH-X productivo. La previsión fundamental de retorno, costes de transacción, primas de riesgo y selección entre 93+ activos necesitan validación prospectiva/point-in-time antes de promover decisiones reales.


### Auditoría adicional: fronteras de SHY

En la versión 0.7.2 subsistía una inconsistencia: una cartera descubierta bajo un límite de 75 % podía seleccionarse con 50 % en SHY sin incluirse en la frontera de 50 %. El resultado mostraba una brecha de utilidad inexistente.

Ahora se reconcilian los finalistas verificados de las búsquedas global y condicionadas contra **cada conjunto anidado**, con los mismos escenarios y supuestos:

```math
\widehat V_{25}\leq\widehat V_{50}\leq\widehat V_{75}\leq\widehat V_{\mathrm{mandato}}.
```

Esta desigualdad se refiere a los máximos *entre candidatas efectivamente verificadas*, no a óptimos globales. La propuesta final entra en toda frontera cuyo tope cumpla, y su brecha es cero en esa frontera. El tope diagnóstico nunca amplía el mandato original. Las invariantes tienen pruebas automatizadas con diferentes semillas y restricciones.

**Límites pendientes:** la selección solo simula un subconjunto del universo, las hipótesis de retorno no están calibradas exhaustivamente con datos *point-in-time* y GARCH-X y colas multivariantes siguen siendo investigación, no características validadas.


## 14. Investigación reproducible posterior: versión 0.8.0

Los componentes de investigación se ejecutan **en paralelo**, mediante el workflow `Research evidence (shadow)`; sus parámetros no modifican automáticamente el motor que propone pesos.

1. **Control de información disponible:** `scripts/research_gate.py` rechaza datos obtenidos después de la emisión, capturas históricas sin vintage original y noticias con consenso posterior al anuncio. Se conservan los errores de pronóstico.
2. **Factor-GJR residual:** `scripts/multifactor_research.py` recalibra cargas conocidas previamente (SPY, renta fija, crédito y oro como candidatos) y compara GJR-t contra EWMA sobre residuales, exclusivamente fuera de muestra. Un mejor QLIKE individual no autoriza introducir ese modelo en la optimización.
3. **Pruebas de cola:** `scripts/tail_research.py` examina cobertura de VaR, independencia de excepciones, medias de cola y co-excedencias. `scripts/joint_tail_research.py` contrasta logscore de un modelo bivariante Student-t con uno gaussiano. La segunda prueba NO constituye un DCC-GARCH multivariante.
4. **Registro de eventos:** `scripts/build_event_registry.py` conserva la fecha oficial SEC y la primera fecha en que el sistema capturó la publicación. El ejemplo actual no contiene consenso numérico previo validado, por lo que `news_garchx_research.py` reporta información insuficiente en lugar de inventar un *bad news effect* semántico.
5. **Estabilidad y cobertura:** `scripts/portfolio_stability.mjs` contrasta semillas, presupuestos y muestras de activos; `portfolio_coverage.mjs` prueba admitir algunas candidatas excluidas sin permitir que entren directamente en producción. Diferentes universos no producen resultados pareados.
6. **Pronósticos prospectivos originales:** el refresh intenta guardar `data/forecasts/YYYY-MM-DD.json` con hash de mercado, emisión real, pesos y distribución. El puntaje futuro se archiva aparte al madurar y en la primera sesión disponible posterior al vencimiento. No se reescribe la predicción original.

No hay suficientes pronósticos maduros para afirmar que los retornos fundamentales, el CVaR anual, las estrategias de rebalanceo o una distribución Student-t superan modelos sencillos. La falta de vintages históricos de consenso, cambios en la composición del universo y delisted securities impide un backtest retrospectivo completo. La documentación detallada del nivel de evidencia está en [estado-validacion.md](estado-validacion.md).


## 15. Política de diversificación e ingresos por distribuciones

La versión 0.8.3 diferencia la exposición económica a deuda Treasury común, sector y emisor. La restricción de parejas con ETF utiliza correlación de rentabilidades **totales observadas**, no solamente residuales tras descontar el mercado. Las holdings se conservan con origen y fecha de primera observación, incluidas fuentes secundarias que reproducen al emisor o la SEC. La falta de composición no demuestra diversificación. Los fondos Treasury comparten presupuesto con independencia del gestor que los administra.

Los límites iniciales son 35% por instrumento (excluido efectivo) y 60% por conjunto Treasury, con posibilidad de superar el límite global hasta 50% **solamente** mediante evidencia prospectiva auditada que aún no está disponible. Su racionalidad es prudencial, no una predicción de pesos óptimos.

### 15.1 Identidad de precio, distribución y reinversión

Los precios ajustados usados por el modelo representan rendimiento total: añadir dividendos como retorno adicional produciría doble conteo. Sea $G_{i,k}$ el factor acumulado de rendimiento total bruto y $y_i$ el rendimiento efectivo anual supuesto para descomponer distribuciones. En pasos de duración $\Delta t$, se define $d_i=(1+y_i)^{\Delta t}-1$. La proxy de precio por participación y el dividendo bruto por participación inicial son:

```math
P_{i,k}=\frac{G_{i,k}}{(1+d_i)^k},\qquad
D_{i,k}=d_iP_{i,k},\qquad
\frac{P_{i,k}+D_{i,k}}{P_{i,k-1}}=
\frac{G_{i,k}}{G_{i,k-1}}.
```

La distribución se calcula sobre el precio del paso actual. Usar el precio anterior en esa misma descomposición rompe la identidad cuando cambia el rendimiento total del paso. Con capital neto inicial $V_0$, peso $w_i$ y retención supuesta $\tau$, el patrimonio sin reinversión es:

```math
V_k^{\mathrm{efectivo}}=
V_0\sum_iw_iP_{i,k}+
V_0\sum_iw_i\sum_{j=1}^{k}(1-\tau)D_{i,j}.
```

Con reinversión, solo la distribución neta compra nuevas participaciones. El valor de la posición y las participaciones acumuladas cumplen:

```math
q_{i,k}=q_{i,k-1}[1+(1-\tau)d_i],\quad q_{i,0}=1,
\qquad
V_k^{\mathrm{reinvertido}}=V_0\sum_iw_iG_{i,k}
\left[\frac{1+(1-\tau)d_i}{1+d_i}\right]^k.
```

Con retención cero se recupera exactamente el rendimiento total simulado. Con retención positiva se reduce el valor reinvertido; la reinversión no suministra efectivo para retiros. Valoración, liquidez y atribución utilizan los mismos coeficientes y se contrastan con un registro explícito de participaciones en pruebas deterministas.

La tasa $y_i$ procede del último año de distribuciones conocidas. Es una hipótesis de rendimiento distribuido sobre precio del final de cada paso; **no reproduce fechas efectivas de pago, cupones contractuales ni tasas fiscales por jurisdicción**. El efectivo cobrado no se remunera en esta aproximación. La retención supuesta de 0% no representa una exención. El registro prospectivo conserva la política de dividendos y no puntúa contra precios ajustados los casos con cobro en efectivo o retención sin realización conciliada.

La distinción entre índice de precio y rendimiento total sigue la [metodología matemática de S&P DJI](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-index-math.pdf). La existencia de impuestos aun con reinversión se explica en la [documentación de Vanguard](https://investor.vanguard.com/investor-resources-education/online-trading/reinvest-dividends); no se deduce de ella una tasa aplicable al usuario. Las ecuaciones anteriores son la aproximación propia de Trading.

### 15.2 Exposición observada y cotas de concentración

Las distintas clases reconocidas de un emisor se suman: por ejemplo, GOOG y GOOGL comparten exposición a Alphabet. El límite por acción del mandato se aplica a la suma directa e indirecta. Se distinguen los pesos conocidos de sus cotas conservadoras; no se publican las cotas como composición real.

Si $E_s$ es la exposición conocida al sector $s$ y $U$ la parte de renta variable sin clasificación sectorial, se exige $E_s+U\leq L_s$, además de $U\leq L_s$. Para un emisor $j$, solo se añade la parte no identificada de fondos donde ese emisor no figura entre las posiciones reconocidas. El total no identificado también debe respetar el límite por emisor. Son comprobaciones robustas frente a composición faltante, no probabilidades ni pesos estimados. Una cartera puede resultar conservadora por falta de datos.

Las holdings con antigüedad superior a 120 días no se utilizan como composición vigente. El plazo es un guardarraíl configurable en código, sin validación empírica de optimalidad. La descarga admite hasta 5.000 líneas por fondo y guarda revisiones con hash del original, sin sobrescribir otra respuesta del mismo día. La correlación de precios, el solapamiento conocido entre holdings y el riesgo sistémico total permanecen como medidas distintas.

## 16. Fechas de distribución, derechos de cobro y conciliación

La extensión distingue tres datos: un calendario publicado de fechas previstas, un importe por participación declarado y una distribución efectivamente conciliable. Una fecha prevista no confirma un importe. Cada captura conserva fuente, hash y primera observación; una publicación antigua descargada hoy no se convierte en información conocida entonces.

La referencia teórica empieza en el corte de precios. No recibe derechos cuyo exdividendo ya ocurrió antes de ese corte; los derechos anteriores de una cuenta existente requieren su historial de operaciones y abonos.

Para el calendario mensual de renta fija iShares se utiliza el [documento oficial del emisor](https://www.ishares.com/us/literature/shareholder-letters/isharesandblackrocketfsdistributionschedule.pdf). Las filas de posible distribución por motivos fiscales se excluyen del pronóstico de importes mientras no exista declaración. Si el calendario no cubre todo el horizonte, el sistema mantiene y rotula la aproximación uniforme; no extrapola fechas oficiales.

En la fecha exdividendo se reconoce el derecho al cobro, separado del efectivo. Con precio anterior a la distribución $P^-$, importe por participación $d$, participaciones $q$ y retención supuesta $\tau$:

```math
P^+=P^- - d,\qquad
A^+=A^-+qd(1-\tau),\qquad
W=qP+A+C.
```

$A$ es la cuenta por cobrar y $C$ el efectivo disponible. Antes de impuestos, la caída de precio y el derecho al cobro se compensan. El derecho no financia un retiro anterior al pago. En la fecha de pago se convierte en efectivo o se reinvierte según el mandato:

```math
\text{Cobro: }\quad C^+=C^-+a,\quad A^+=A^- - a;
\qquad
\text{Reinversión: }\quad q^+=q^-+a/P_{\mathrm{pago}},\quad A^+=A^- - a.
```

La trayectoria de rendimiento total continúa siendo la misma entrada estocástica. Se descompone en precio y distribuciones sin añadir un segundo retorno. Entre puntos de simulación se interpola logarítmicamente para valorar eventos fechados; esto no reconstruye precios intradía. La comprobación de liquidez respeta el orden real de pagos y retiros incluso cuando caen dentro del mismo intervalo semanal. Una distribución declarada que exceda el precio simulado no crea capital: el pago se limita al valor disponible y se identifica la incidencia.

Para importes todavía desconocidos se mantiene el rendimiento distribuido del último año como hipótesis; sus fechas pueden estar documentadas sin que el importe lo esté. El retraso de pago y la reinversión al pago pueden producir un resultado distinto de un índice que reinvierte en la fecha exdividendo. No se interpreta esa diferencia como alfa.

La conciliación realizada exige una ventana completa de eventos exdividendo, importes contrastables, fechas de pago y precios de la misma base. Los splits y ventanas incompletas bloquean la comparación hasta resolver su base. La retención sigue siendo una hipótesis configurada, no un impuesto individual comprobado. Un resultado bajo estas convenciones no concilia operaciones ni abonos reales del broker.
