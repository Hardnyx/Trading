# Trading: modelo estocástico de riesgo, noticias y decisiones de inversión

**Documento técnico de diseño · versión 1.0 (propuesta de investigación) · 25 de octubre de 2026**

> **Alcance:** especificación **teórica y metodológica**. No es una descripción de un modelo ya validado ni una autorización para utilizarlo en decisiones reales. Este documento no modifica la interfaz, el optimizador ni las recomendaciones de Trading. Las implementaciones experimentales que puedan existir deben tratarse por separado.

## Resumen

Se propone un sistema predictivo para carteras multiactivo que distingue entre (i) rentabilidad esperada, (ii) volatilidad condicional, (iii) dependencias de mercado y residuales, (iv) saltos y eventos informativos, y (v) decisión de invertir bajo restricciones. La propuesta evita dos errores: considerar que una misma rentabilidad supuesta sirve para todos los instrumentos y etiquetar retrospectivamente toda desviación como «noticia» para absolver al pronóstico. La validación será estrictamente *ex ante*: cada predicción y cada dato empleado conservarán su fecha de conocimiento. La primera implementación será un candidato de volatilidad **GJR-GARCH(1,1) con innovaciones Student-t estandarizadas**, contrastado con EWMA en modo experimental, sin modificar aún las recomendaciones. La atribución de noticias, los saltos informativos y las correlaciones dinámicas se incorporarán únicamente después de acreditar mejoras fuera de muestra.

**Palabras clave:** cálculo estocástico, GJR-GARCH, efectos asimétricos, regímenes, datos *point-in-time*, eventos, riesgo de cartera, CVaR.

### Estado de implementación (25 de octubre de 2026)

La versión 0.7.0 descompone una única matriz EWMA común en factor SPY y residuo PSD, actualiza GJR y EWMA diariamente, y elimina un factor radial Student-t universal no calibrado. **No** equivale aún al modelo factorial-GARCH completo: GJR se estima sobre retornos totales y la estimación de residuos por régimen/sector sigue siendo diagnóstica. La dependencia de cola, GARCH residual, GARCH-X, DCC y saltos informativos continúan pendientes de validación.

## 1. Problema y pregunta de investigación

Trading dispone de valoración fundamental, un universo multiactivo, simulaciones Monte Carlo y una matriz de covarianza EWMA. Sin embargo, la expectativa anual genérica de ciertos ETF —por ejemplo, 6 % para oro— no representa una tesis económica calibrada, y los saltos añadidos a una covarianza histórica que ya incluye crisis pueden contar el mismo riesgo dos veces.

**Pregunta central:** ¿la volatilidad asimétrica y la evidencia informativa disponible al corte mejoran la predicción probabilística y las decisiones de cartera respecto de una referencia parsimoniosa, sin utilizar información futura ni ocultar fallos del modelo?

Tres hipótesis refutables:
- **H1:** GJR-GARCH-t reduce la pérdida predictiva de volatilidad respecto de EWMA, de forma estable fuera de muestra.
- **H2:** eventos identificados con sellos temporales y sorpresas frente al consenso explican variación incremental, no ya capturada por factores o GARCH.
- **H3:** utilizar distribuciones y riesgos calibrados mejora utilidad neta o adecuación al mandato frente a mantener la cartera o un benchmark sencillo.

El incumplimiento de H1, H2 o H3 implica **no promover** el componente correspondiente a producción.

## 2. Información y prevención del sesgo retrospectivo

La filtración de información se evita imponiendo un conjunto de información disponible $`\mathcal F_t`$. Un cálculo realizado al cierre de $`t`$ puede usar únicamente precios, datos, revisiones y publicaciones conocidos hasta ese momento; predice $`t+1`$ o el horizonte definido.

Cada observación guarda como mínimo: identificador, fecha económica, fecha y hora de publicación, primera fecha de disponibilidad, proveedor, fecha de descarga, revisión/vintage, moneda, transformación y calidad. Los datos publicados después del cierre no se utilizan como si hubieran sido conocidos durante la sesión. Los eventos intradía requieren distinguir su hora exacta y la ventana de precios analizada. Eventos sin timestamp verificable quedan **sin atribuir**.

Se emplean retornos logarítmicos ajustados por dividendos y splits, con calendarios compatibles. No se inventan valores ausentes ni se utilizan revisiones futuras de series macroeconómicas. Los retornos realizados y los índices de precios no sustituyen la tasa de crecimiento de beneficios ni las primas económicas en las expectativas *ex ante*.

## 3. Modelo probabilístico conjunto: retorno, factores, residuo y saltos

**Convención temporal:** $`t`$ es el cierre de una sesión y $`\mathcal{F}_t`$ es toda la información verificablemente disponible entonces. Se define el retorno logarítmico del día siguiente como

```math
r_{i,t+1}=\ln\!\left(\frac{P^{\mathrm{aj}}_{i,t+1}}{P^{\mathrm{aj}}_{i,t}}\right).
```

El **modelo discreto de un día** será:

```math
\boxed{
r_{i,t+1}
=\mu_{i,t}
+\boldsymbol{\beta}_{i,t}^{\mathsf T}\mathbf f_{t+1}
+u_{i,t+1}
+j^{c}_{i,t+1}
}
```

con las condiciones de centrado

```math
\begin{aligned}
\mu_{i,t}&=\mathbb E[r_{i,t+1}\mid\mathcal F_t],\\
\mathbb E[\mathbf f_{t+1}\mid\mathcal F_t]&=\mathbf 0,\\
\mathbb E[u_{i,t+1}\mid\mathcal F_t]&=0,\\
\mathbb E[j^c_{i,t+1}\mid\mathcal F_t]&=0.
\end{aligned}
```

Aquí $`P^{\mathrm{aj}}`$ es un precio total-return ajustado; $`\mu_{i,t}`$ es la previsión condicionada **conocida antes del resultado**; $`\boldsymbol{\beta}_{i,t}`$ recoge exposiciones a factores; $`\mathbf f_{t+1}`$ representa sus sorpresas (mercado, curva de tasas, crédito, USD, sectores); $`u_{i,t+1}`$ representa una innovación residual; $`j^c_{i,t+1}`$ es un salto *centrado*, **solo si más adelante se justifica estadísticamente**.

**No se sumará un salto realizado sin compensar su expectativa**, porque de lo contrario la ecuación dejaría de identificar a $`\mu_{i,t}`$ como media condicionada. Si se omite el módulo de saltos, se fija $`j^c=0`$ y sus eventos permanecen en los residuos observados.

La previsión de retorno $`\mu`$ se obtiene de modelos económicos por clase de instrumento, no del GARCH:
- Acciones: flujos, crecimiento por acción, rentabilidad distribuida, dilución, márgenes y valoración relativa, con incertidumbre explícita.
- Bonos/ETF de bonos: TIR, carry neto, rolldown, duración, convexidad cuando esté medida, spreads y riesgo de crédito.
- Oro: escenarios de tasas reales, USD y demanda de refugio, sin atribuirle automáticamente una prima positiva constante.
- Efectivo: rendimiento efectivo neto de la cuenta; cero solo si el efectivo se considera explícitamente no remunerado.

Las expectativas deben ser coherentes en horizonte y unidades: **un retorno diario logarítmico no es intercambiable con un retorno simple anual**, y una varianza diaria no se compara directamente con un CVaR anual. La transformación de horizonte depende de la dinámica condicional y no de multiplicar mecánicamente los parámetros de un proceso con regímenes y saltos.

### 3.1. ¿Dónde entra el cálculo estocástico?

La ecuación anterior define un sistema **discreto** de pronóstico y control de volatilidad. GARCH también es discreto: no es, por sí mismo, una ecuación diferencial de Itô. Si se necesitan trayectorias continuas o simulación intradía, una **aproximación alternativa** puede escribirse como

```math
\frac{\mathrm dS_{i,t}}{S_{i,t^-}}
=\bigl(a_{i,t}-\lambda_{i,t}\kappa_{i,t}\bigr)\,\mathrm dt
+\boldsymbol{\sigma}_{i,t}^{\mathsf T}\,\mathrm d\mathbf W_t
+(J_{i,t}-1)\,\mathrm dN_{i,t},
```

donde $`\kappa_{i,t}=\mathbb E[J_{i,t}-1\mid\mathcal F_{t^-}]`$. Esta representación **no debe sumarse encima** de la simulación discreta previa: es otra especificación que necesitaría una correspondencia documentada de derivas, volatilidades, saltos y frecuencias.

## 4. Volatilidad asimétrica: GJR-GARCH-t

El punto de partida preferente es el residuo $`u_{i,t}`$ obtenido **después** de controlar los factores disponibles. Si todavía no existe una descomposición factorial confiable, puede modelarse temporalmente un retorno centrado, pero no sumarse más adelante esa varianza a una matriz factorial que ya contenga el mismo movimiento común.

```math
\begin{aligned}
u_{i,t}&=\sqrt{h_{i,t\mid t-1}}\,z_{i,t},\\
z_{i,t}&\sim\sqrt{\frac{\nu_i-2}{\nu_i}}\,t_{\nu_i},
\qquad \nu_i>2,\\
\mathbb E[z_{i,t}]&=0,\qquad
\mathrm{Var}(z_{i,t})=1.
\end{aligned}
```

La varianza **pronosticada al cierre $`t`$ para la próxima sesión** es:

```math
\boxed{
h_{i,t+1\mid t}
=\omega_i
+\alpha_i u_{i,t}^{\,2}
+\gamma_i\mathbf 1_{\lbrace u_{i,t}<0\rbrace}u_{i,t}^{\,2}
+\beta_i h_{i,t\mid t-1}.
}
```

Una innovación negativa puede elevar más la volatilidad futura que otra positiva de igual magnitud. Si $`\gamma_i>0`$, el modelo representa un **efecto asimétrico de malas noticias financieras**; *no* demuestra que una noticia periodística específica haya causado el retorno.

Para la versión no exógena, con innovaciones simétricas de varianza unitaria, se consideran las restricciones:

```math
\omega_i>0,\qquad
\alpha_i,\beta_i,\gamma_i\ge 0,\qquad
\alpha_i+\beta_i+\frac{\gamma_i}{2}<1.
```

Estas condiciones son suficientes para el caso básico de persistencia de segundo momento aquí definido; no se extrapolan automáticamente a GARCH-X, cambios de régimen o distribuciones asimétricas. Tampoco se fuerza $`\gamma_i>0`$ para oro, divisas o renta fija: una versión simétrica debe permanecer entre los candidatos.

Se preferirá estimación por verosimilitud con Student-t **estandarizada**, múltiples inicializaciones, chequeos de convergencia y controles de estabilidad. Una varianza casi no estacionaria, un parámetro en el borde o historia insuficiente activará la reserva EWMA en lugar de producir certeza artificial.

**Referencia comparable:**

```math
h^{\mathrm{EWMA}}_{i,t+1\mid t}
=\lambda h^{\mathrm{EWMA}}_{i,t\mid t-1}
+(1-\lambda)u_{i,t}^{\,2},
\qquad 0<\lambda<1.
```

En toda comparación, ambos candidatos deben recibir la misma información y definición de innovación. Student-t permite colas más pesadas, pero no acredita por sí sola una dinámica de saltos causados por noticias.

## 5. Noticias verificadas, sorpresas y variables exógenas

Se distinguen **tres conceptos distintos**:

1. **Signo del retorno inesperado:** determina el término asimétrico de GJR-GARCH, incluso si no se conoce una noticia.
2. **Evento identificado:** existe una publicación con fecha, hora y fuente verificable, independiente del movimiento observado.
3. **Vinculación estadística o causal:** requiere un procedimiento de identificación; una coincidencia temporal no basta.

Una extensión investigable, **GJR-GARCH-X**, sería:

```math
h_{i,t+1\mid t}
=\omega_i+\alpha_i u_{i,t}^{\,2}
+\gamma_i\mathbf1_{\lbrace u_{i,t}<0\rbrace}u_{i,t}^{\,2}
+\beta_i h_{i,t\mid t-1}
+\boldsymbol{\delta}_i^{\mathsf T}\mathbf x_t.
```

El vector $`\mathbf x_t`$ contiene únicamente características **conocidas al cierre $`t`$**. Podría incluir intensidad de sorpresa ya publicada, indicadores de acontecimientos programados para el día siguiente e incertidumbre observable. Esta forma aditiva requiere restricciones de positividad (por ejemplo, $`\mathbf x_t\ge 0`$ y $`\boldsymbol{\delta}_i\ge 0`$). Con covariables firmadas se consideraría una formulación de **log-varianza**, en vez de dejar que la varianza se haga negativa.

La sorpresa de un indicador macroeconómico debe definirse antes de observar su reacción de precio:

```math
\mathrm{Sorpresa}_{k,t}
=\mathrm{Dato}_{k,t}
-\mathrm{Consenso}_{k,t^-}.
```

El consenso debe corresponder a la información disponible **antes de publicar el dato**, no a una revisión posterior. Por ejemplo, IPC observado de 3,2 % frente a consenso previo de 3,4 % implica sorpresa de $`-0{,}2`$ puntos porcentuales. Esto no determina universalmente el signo de su impacto en acciones o bonos.

Las noticias del día $`t+1`$ desconocidas en $`t`$ no se pueden introducir como regresores realizados para el pronóstico $`t+1`$. Sí cabe modelar la **probabilidad de que ocurra un evento** a partir de un calendario publicado o una intensidad condicionada.

Se define un registro reproducible: `event_id`, `published_at_utc`, `known_at_utc`, `actual`, `consensus_asof`, `surprise`, `unit`, `source_url`, `asset_ids`, `factor_ids`, `association_status`. Los estados incluyen evento verificado, asociación estadística, coincidencia insuficiente y sin atribución. El clasificador puede ayudar a **encontrar** eventos, no a declararlos causas ni a suprimir errores del modelo.

## 6. Saltos condicionales y riesgo de doble conteo

Un salto económico es una innovación discontinua que puede no quedar bien representada por una Student-t continua. En tiempo discreto, si $`N_{i,t+1}`$ es un indicador de salto y $`J_{i,t+1}`$ su magnitud logarítmica, el término centrado es:

```math
j^c_{i,t+1}
=N_{i,t+1}J_{i,t+1}
-\mathbb E[N_{i,t+1}J_{i,t+1}\mid\mathcal F_t].
```

Su probabilidad debe depender solo de información anterior: $`p_{i,t}=\Pr(N_{i,t+1}=1\mid\mathcal F_t)`$. Esta ecuación no convierte todo retorno extremo en un salto identificado; el módulo requiere una prueba de identificación y calibración independiente.

Si se opta por un modelo continuo de Merton, puede emplearse la ecuación de la sección 3.1 con intensidad $`\lambda_{i,t}`$ y multiplicador $`J_{i,t}`$. La compensación del drift y la dependencia conjunta entre saltos se especifican explícitamente.

**Riesgo principal:** ajustar GARCH con series que incluyen crashes y, luego, añadir un segundo proceso de saltos extraordinarios calibrado sobre esos mismos crashes puede **duplicar la varianza y el riesgo de cola**. Antes de habilitar ambos procesos habrá que:

- Estimar la separación de componentes de manera conjunta; o
- Identificar saltos con un método validado y recalibrar los residuos continuos con incertidumbre de clasificación.

La **primera especificación teórica utilizable** no obliga a incluir saltos explícitos; mantiene las pérdidas extremas en el historial y exige comprobar si Student-t y volatilidad condicional ya capturan su frecuencia.

## 7. Covarianzas, correlaciones residuales y estados del mercado

Bajo la **hipótesis explícita** de innovaciones factoriales y residuales condicionalmente ortogonales, la covarianza predictiva se descompone:

```math
\boxed{
\boldsymbol{\Sigma}_{t+1\mid t}
=\mathbf B_t\boldsymbol{\Sigma}_{f,t+1\mid t}\mathbf B_t^{\mathsf T}
+\mathbf D_{t+1\mid t}
 \mathbf R_{\varepsilon,t+1\mid t}
 \mathbf D_{t+1\mid t}
+\boldsymbol{\Sigma}_{J,t+1\mid t}.
}
```

Aquí $`\mathbf B_t`$ son cargas factoriales; $`\boldsymbol{\Sigma}_f`$ representa shocks comunes; $`\mathbf D`$ contiene desviaciones estándar residuales; $`\mathbf R_{\varepsilon}`$ sus correlaciones; $`\boldsymbol{\Sigma}_J`$ recoge saltos centrados **solo cuando se modelan separadamente sin doble conteo**. Si hay covarianzas cruzadas no nulas entre componentes, deben incluirse: la expresión no constituye una identidad incondicional.

Las fases bull/bear sirven para contrastar betas condicionales y dependencias en distintas circunstancias. Una clasificación operacional posible es:

```math
s_t=\mathbf1_{\left\lbrace
\sum_{k=0}^{62}r^{M}_{t-k}\ge 0
\right\rbrace},
```

usando únicamente retornos del índice de mercado disponibles en $`t`$. El umbral y la ventana son **hipótesis metodológicas**, no definiciones universales de ciclo económico.

Se distinguen:
- **Correlación total:** dependencia relevante para las pérdidas de cartera observadas.
- **Correlación residual:** asociación después de explicar componentes factoriales, útil para detectar exposiciones empresariales redundantes.
- **Dependencia de cola:** probabilidad de caídas simultáneas, potencialmente distinta de la correlación lineal.

Es válido ensayar **DCC-GARCH** en residuos estandarizados y por bloques o factores, comparándolo con matrices regulares más simples. No se asume que DCC sea mejor ni que sea viable aplicarlo sin regularización a todo el universo.

**El riesgo sistémico no desaparece al descontar SPY de una matriz residual.** En Monte Carlo se recomponen factores y residuos; la matriz final debe ser semidefinida positiva y documentar su calibración, regularización y estabilidad.

## 8. Aprendizaje secuencial y evaluación honesta de shocks

El aprendizaje no consiste en volver a escribir el pasado para que los pronósticos parezcan acertados. Para cada corte $`t`$:

1. **Pronóstico sellado:** registrar $`(\mu_{i,t},h_{i,t+1\mid t},p_{i,t})`$, parámetros, información y versión del modelo antes de conocer $`r_{i,t+1}`$.
2. **Resultado observado:** calcular $`u_{i,t+1}`$ y, cuando corresponda, el residuo estandarizado

```math
z_{i,t+1}=\frac{u_{i,t+1}}{\sqrt{h_{i,t+1\mid t}}}.
```

3. **Atribución tentativa:** asociar eventos con sello de tiempo y evidencia, pero mantener la pérdida de predicción original.
4. **Actualización de estado:** actualizar $`h_{i,t+2\mid t+1}`$ con el error realizado y **parámetros previamente entrenados**.
5. **Reestimación:** recalibrar coeficientes solamente en fechas predeterminadas, usando una ventana anterior y sin modificar pronósticos archivados.
6. **Promoción:** autorizar un cambio metodológico únicamente después de pruebas fuera de muestra independientes.

Una caída observada de cuatro desviaciones estándar puede estar relacionada con resultados empresariales y, simultáneamente, indicar que el modelo subestimó la probabilidad de eventos extremos. Son afirmaciones diferentes que no se cancelan.

### 8.1. ¿Cómo se distingue error de shock?

- **Innovación extrema aislada, cobertura adecuada a largo plazo:** riesgo realizado compatible con una distribución que admite colas.
- **Exceso persistente de excepciones:** colas o volatilidad condicional mal calibradas, aunque cada excepción tenga una noticia asociada.
- **Errores recurrentes de media o factor:** expectativas económicas o exposiciones mal especificadas.
- **Cambio estructural sustentado en evidencia:** analizar regímenes y necesidad de reentrenar, sin recalificar retrospectivamente el desempeño.

## 9. Validación empírica, decisión y criterio de aceptación

Se propone evaluación *walk-forward*: en cada fecha se entrenan modelos con información hasta $`t`$, se congelan parámetros y se puntúa el pronóstico de $`t+1`$. La ventana, frecuencia de reentrenamiento y filtros deben definirse **antes** de examinar resultados fuera de muestra.

### 9.1. Criterios de volatilidad

Un criterio principal es **QLIKE**, aplicado a la varianza pronosticada y un proxy de realización:

```math
L_{\mathrm{QLIKE}}\!\left(h_{t+1\mid t},u_{t+1}^{\,2}\right)
=\log h_{t+1\mid t}
+\frac{u_{t+1}^{\,2}}{h_{t+1\mid t}}.
```

Cuanto menor, mejor en promedio bajo las condiciones pertinentes. Los residuos cuadrados diarios son proxies muy ruidosos de la varianza latente; si se dispone de datos intradía limpios y legalmente utilizables, se puede evaluar contra varianza realizada.

También se compararán *log-scores* predictivos completos, cobertura y **agrupamiento de excepciones VaR** y medidas de Expected Shortfall. La estabilidad de coeficientes, diferencias por activo, subperiodo y régimen, y el riesgo de múltiples comparaciones serán parte del reporte, no notas marginales.

### 9.2. Separar pronóstico de riesgo y selección de cartera

Un mejor QLIKE **no garantiza** mejores inversiones. Las carteras se optimizarían posteriormente con pronósticos económicos de retorno, escenarios conjuntos, costos de transacción y restricciones de mandato. Para un enfoque estático condicionado, una formulación de investigación es:

```math
\max_{\mathbf w\in\mathcal W}
\inf_{\theta\in\Theta_t}
\left\lbrace
\mathbb E_{\theta}\!\left[U(W_T(\mathbf w))\mid\mathcal F_t\right]
-C(\mathbf w,\mathbf w_t)
\right\rbrace.
```

$`\mathcal W`$ es el conjunto de carteras permitidas; $`\Theta_t`$ representa parámetros razonablemente inciertos; $`U`$ es utilidad del patrimonio final y $`C`$ los costos de rebalanceo. En particular, **no se fuerza una distribución de pesos**. SHY o efectivo pueden dominar justificadamente si las demás opciones no compensan su riesgo.

### 9.3. Regla de promoción

Un candidato experimental no modifica composición ni señales. Su promoción exige, como mínimo, (a) trazabilidad temporal verificable, (b) mejor puntuación predictiva preespecificada en múltiples ventanas fuera de muestra, (c) colas y excepciones no peores de forma material, (d) parámetros estables y fallbacks identificables y (e) mejora económica neta en una **evaluación de decisiones separada**. Si no mejora suficientemente, se conserva el modelo de referencia sencillo.

## 10. Secuencia de investigación (sin cambios a la página)

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
