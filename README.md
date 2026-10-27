# Trading

Research, composición y seguimiento de una cartera personal de acciones y ETFs de Estados Unidos.

**Motor 0.19.0.** Historia anual de BPA diluido con presentaciones y fuentes, diagnóstico secuencial del crecimiento y procedencia explícita de los supuestos. El candidato de crecimiento permanece en investigación y no modifica las anclas. Se conservan las protecciones de splits, la valoración conciliada y el devengo de efectivo de 0.18.0. El modelo sigue siendo experimental. Véanse [el estado actual, las comprobaciones y los pendientes](docs/estado-validacion.md).

[Abrir aplicación](https://hardnyx.github.io/Trading/)

## Uso

1. **F8 · Mandato:** objetivo, horizonte, moneda, metas, retiros, drawdown tolerable y liquidez. Configura costos y, si corresponde, las cantidades que realmente tienes.
2. **F5 · Valoración:** revisa crecimiento, múltiplo, márgenes, dilución, confianza y tesis de cada empresa. Compara previsión propia, consenso comparable y crecimiento implícito en el precio.
3. **F1 · Componer:** pulsa **Proponer cartera**. Compara mantener, una alternativa con ETF/SHY/efectivo y candidatas activas, después de costos. Los pesos se pueden editar antes de registrar una referencia.
4. **F2 · Seguimiento:** revisa nueva evidencia, condiciones de tesis, desvíos y previsiones registradas. Reevaluar calcula cambios; registrar una composición no confirma operaciones en un broker.
5. **F3/F6:** trayectorias futuras, riesgo durante el horizonte, contribuciones marginales y correlaciones residuales después de mercado/sector. **F4/F7:** universo y contexto macro.

La cuenta, tesis, supuestos y pronósticos quedan en este navegador. **Exportar cartera** permite conservarlos y trasladarlos. Los avisos requieren permiso del navegador y la página abierta; no hay vigilancia de la cartera personal con la página cerrada.

## Validación y evidencia

El modelo de producción y sus pronósticos **siguen siendo experimentales**. La versión 0.8.0 añade investigaciones independientes sobre vintages/point-in-time, GJR multifactorial, coexcedencias y colas, Student-t bivariante, registros de eventos SEC y estabilidad de selección. Estas pruebas no se convierten automáticamente en nuevas reglas de inversión.

[**Estado de validación, resultados, límites y comandos reproducibles**](docs/estado-validacion.md)

[Pendientes priorizados y criterios de cierre](docs/pendientes.md)

Cada corte sella además, antes de la apertura siguiente, la varianza, el VaR95 y el ES95 a una sesión de referencias estadísticas por instrumento (`data/risk-forecasts/`). Su EWMA centrada y sus GJR sin límites de escalado difieren del simulador: no validan el motor exacto ni el CVaR de cartera. Los resultados ausentes se completan con registros nuevos e inmutables; Riesgo distingue sesiones completas y parciales. GitHub Actions conserva diagnósticos como artefactos en **Research evidence (shadow)**; la actualización de datos intenta sellar un pronóstico independiente una sola vez por corte de mercado en `data/forecasts/` y guardará su resultado al madurar. Eso **no incluye tu cartera personal**, que permanece en el navegador. No se ha demostrado todavía calidad predictiva a doce meses ni ventaja frente a portafolios sencillos netos de costos.

## Método

**Previsión.** Para acciones, BPA y múltiplo de salida propios; también ventas × margen neto / dilución, consenso comparable o mezcla 50/50. El múltiplo de salida por defecto es una referencia sectorial genérica: el valor justo la usa completa, pero el retorno esperado solo cierra la brecha entre el P/E observado y esa referencia con vida media de 10 años (≈19% de la brecha logarítmica en 3 años); convergencia total y ausencia de reversión delimitan la banda. Un múltiplo que fijes por empresa se respeta tal cual. El crecimiento implícito en precio usa la misma ecuación de dividendos descontados que la valoración. El retorno anual equivalente aproxima los dividendos al final; no se suman otra vez al simular. No es un DCF completo.

**Evidencia del crecimiento.** El recolector conserva hasta doce años de BPA anual diluido y todas sus versiones disponibles en la respuesta actual de SEC, con periodo, presentación, accession y enlace. El contraste usa pares anuales del mismo informe, sin mezclar bases por acción alrededor de splits. `python scripts/earnings_growth_research.py` evalúa un candidato con hasta cinco crecimientos conocidos, contraído hacia 6% con fuerza cinco, frente al prior común y al último crecimiento. Son convenciones fijas, no parámetros calibrados. Las bandas se calculan solo con errores ya publicados en cada origen; no se recortan pérdidas ni crecimientos extremos para mejorar métricas. La página identifica por separado la convención del catálogo, la edición manual y el consenso observado. La historia descargada hoy no acredita vintages originales y el diagnóstico no ajusta la propuesta automáticamente.

La confianza subjetiva se reduce por cobertura y antigüedad de fundamentos y contradicciones de tesis. Contrae la previsión hacia un retorno previo explícito y amplía sus rangos. Una contradicción no mejora el retorno previsto y bloquea nuevas compras hasta revisar las hipótesis. Confianza no equivale a precisión predictiva demostrada. Las observaciones faltantes aparecen como `—`, no como cero.

**Incertidumbre y escenarios.** Cópula normal de mercado, sector y empresa para las anclas triangulares. El valor central es el **modo**; la media triangular es `(mínimo + modo + máximo) / 3`. Las participaciones de incertidumbre y los escenarios macro son supuestos editables. Beneficios, múltiplos y tasas cambian de forma condicional a cada escenario; no se infiere automáticamente un régimen de los últimos datos macro.

Difusión correlacionada con covarianza EWMA de retornos logarítmicos, regularización fuera de diagonal del 5% y 252 sesiones/año. El retorno histórico no se utiliza como retorno esperado. En Merton, los eventos son comunes y las cargas difieren por activo: beta histórica de mercado para renta variable, duración/shock de tasas para bonos, carga asumida para oro y cero para efectivo. Cada activo utiliza su propio compensador `exp(media_i + varianza_i/2) - 1`. Los saltos y escenarios se añaden a una covarianza histórica que ya contiene shocks; es incertidumbre adicional del modelo, sin calibración estructural independiente.

**Bonos y efectivo.** SHY y TLT usan TIR bruta, gastos y duración de perfiles iShares fechados. Aproximación local: carry = TIR − gastos; respuesta a tasas = −duración × cambio de tasa. Con un perfil antiguo se puede usar la curva Treasury de plazo próximo como proxy de TIR, conservando duración y fecha del perfil. No se usa Treasury 3M como retorno de SHY. El escenario de precios utiliza una convexidad **proxy** (D(D+1)), no la convexidad efectiva publicada del fondo. No hay estimación completa del rolldown de la curva, cupones ni reinversión. CASH es efectivo sintético USD sin riesgo de precio; rinde la tasa neta que declares para tu cuenta (0% por defecto, es decir, efectivo no remunerado). Es una tasa contractual constante, no una previsión de la Fed ni de la curva.

**Mandato y decisión.** Objetivos: crecimiento logarítmico, preservación con utilidad CRRA o minimizar el faltante cuadrático frente a una meta final. Retiros/metas se expresan en moneda de referencia; cuenta y órdenes, en USD. Otras monedas requieren tipo de cambio, variación, volatilidad, correlación y confirmación explícitos. FX se compone multiplicativamente.

La búsqueda aproximada prueba carteras pasivas, una posición inicial de hasta 20% en cada activo elegible, combinaciones aleatorias y ajustes locales de 5 puntos porcentuales sobre las propuestas más prometedoras, hasta un presupuesto de aproximadamente 300 evaluaciones con 600 trayectorias mensuales comunes. Hasta diez finalistas se comprueban con 3,000 nuevas trayectorias semanales; sólo se propone una que pase esa verificación. El informe contrasta efectivo, SHY y benchmark en los mismos escenarios, identifica restricciones cercanas a su límite y señala los ETF que aún usan supuestos genéricos. No es optimización global ni prueba causal de por qué se eligió una concentración. Límites iniciales editables: 20% por emisor de acciones (directo + ETF), 35% global por instrumento, 60% Treasury agregado, 50% renta variable agregada, 35% por sector, ocho posiciones, correlación 0.95, CVaR máximo 20% y probabilidad de pérdida máxima 45%. El máximo específico de ETF de 80% y el de SHY de 100% están subordinados al global de 35%. Las holdings fechadas se suman por emisor; los sectores y emisores desconocidos consumen capacidad mediante cotas conservadoras.

El drawdown se calcula sobre un índice ajustado por retiros; la falta de efectivo y el piso de capital se comprueban aparte. Los retiros se prefundan en CASH. No se suponen ventas gratuitas durante las trayectorias. Se informa tiempo bajo máximos y falta de recuperación al final; los intervalos semanales pueden omitir mínimos entre observaciones.

Comisión por orden, comisión variable, medio spread completo por lado, deslizamiento e impuesto supuesto sobre ganancias realizadas se deducen una sola vez. Se resuelve el presupuesto con capital neto de costos. Impuesto 0 significa exclusión asumida; no representa una conclusión tributaria. Sin costo de compra, una venta gravada no es una propuesta completa. No se optimizan lotes fiscales. Mantener se prefiere si cumple el mandato y la mejora equivalente no supera el umbral en dólares y la relación beneficio/costo. Sensibilidades de crecimiento/margen, múltiplo, confianza y correlaciones vuelven a elegir entre una muestra limitada de candidatas.

**Referencia limpia y comparación en navegador.** El botón `Comparar base limpia` utiliza el mismo preset que la prueba reproducible (4 regímenes y semilla 20261024), independientemente de las posiciones y la configuración personal. Las propuestas no se aplican a las posiciones salvo mediante `Aplicar propuesta`. El flujo de CI ejecuta Chromium y verifica los pesos renderizados, así como la conservación del estado local. Enlace de versión: https://hardnyx.github.io/Trading/?build=0.7.0.

**Protección ante retornos de ETF sin evidencia.** El compositor no compra automáticamente ETF sin modelo de rentabilidad económica: solo permite nuevas posiciones si tienen una TIR/duración/gastos razonablemente identificados (ETF de bonos) o si el usuario ha consignado explícitamente tanto el retorno esperado como su rango de incertidumbre. Los ETF de acciones, oro y otras clases sin ese respaldo permanecen disponibles para investigación y pueden conservarse si ya estaban en la cartera, pero el 6 % genérico deja de servir como tesis de compra nueva. Este filtro es provisional y no equivale todavía a una valoración agregada ni a una prima de riesgo calibrada. El siguiente trabajo es modelar individualmente cada tipo de ETF en lugar de asumir un retorno igual para todos.

**Versión e integridad de propuestas (0.7.0).** El encabezado muestra la versión real del motor. Toda propuesta guardada se invalida si difiere la versión de cálculo, la fecha de precios o el identificador del corte; también se invalida al importar un snapshot distinto. Los pesos reales y supuestos del usuario se conservan, pero no se presentan métricas históricas como nuevas. Para cargar la versión vigente tras un despliegue, abrir `https://hardnyx.github.io/Trading/?build=0.7.0` y usar Proponer cartera.

**Riesgo estocástico (motor 0.7.0).** Las calibraciones GJR-GARCH-t públicas se ajustan todavía sobre retornos totales; por tanto, no son estimaciones de GARCH residual. En la simulación se descompone la covarianza EWMA conjunta con SPY en un factor común y el complemento residual PSD (identidad de Schur), con la misma historia y corte temporal. La recomposición conserva la matriz gaussiana latente. Las marginales Student-t cambian sus correlaciones lineales: se registra por separado una aproximación PSD de la covarianza inicial inducida y se utiliza para las porciones de varianza inicial. Sin 126 sesiones comunes o con una matriz inválida se usa la covarianza total. Los sectores/betas bull-bear siguen siendo diagnósticos, no factores estocásticos separados.

Cuando hay al menos un GJR validado, la varianza de **cada** activo se actualiza diariamente: GJR asimétrico para los aceptados y EWMA para los demás. Los shocks comunes y residuales se generan correlacionados con una cópula gaussiana; cada activo con GJR aceptado transforma su shock al cuantil de su Student-t estandarizada (la ley con que se estimó y aceptó), y los demás conservan innovaciones gaussianas. Se mantiene eliminada la Student-t radial global que imponía colas simultáneas sin calibración: la cópula gaussiana no añade dependencia de cola. Sin GJR aceptado, el modo híbrido aplica EWMA diario sin activar saltos Merton silenciosamente. Merton legado queda como comparador explícito con shocks no calibrados a noticias.

**Limitaciones y precaución.** El GJR publicado sigue calibrado con retornos totales, no con residuos de factores. La dependencia por cópula gaussiana puede subestimar caídas simultáneas extremas y necesita backtesting de coexcedencias, estrés y un modelo residual validado. Todavía no se han implementado DCC, GARCH-X, sectores simulados como factores específicos ni causalidad de noticias. No se interpreta una reducción del CVaR calculado como mejora demostrada del riesgo.

**Anomalías fuera de muestra.** Las sorpresas estandarizadas de tres o más desviaciones de los últimos 63 pronósticos se conservan con fecha, retorno y clasificación `unattributed_statistical_shock`. La vista F6 las muestra **sin atribución a una noticia**; ausencia de registros no implica causalidad ni descarta eventos. El seguimiento de esta calidad se integra a la actualización diaria de volatilidad.

**Noticias y eventos.** No existe todavía una fuente pública completa de eventos con consenso previo y timestamp validado; por tanto, Trading **no atribuye automáticamente noticias ni exonera errores de pronóstico**. El módulo experimental `scripts/analyze_volatility.py` acepta un registro JSON de eventos verificables y conserva íntegramente los errores realizados. GARCH-X, intensidades de salto por tipo de evento y modelos causales están definidos en [el artículo metodológico](docs/modelo-estocastico-eventos.md), pero no deben etiquetarse como activos hasta ser calibrados. Las hipótesis de retorno anual de ETF sin fundamento propio siguen siendo un límite del modelo; GARCH mejora una parte del riesgo, no su retorno esperado.

**Correlaciones por régimen.** En parejas de acciones, el filtro de similitud del compositor emplea correlaciones **residuales** de retornos logarítmicos después de estimar por separado la exposición a SPY en fases bull/bear clasificadas con 63 sesiones anteriores y, cuando se dispone de datos, descontar el proxy sectorial ortogonal. Se exige historia común de al menos 126 sesiones; en su ausencia se declara una sustitución por correlación total. Las correlaciones residuales no son causas ni relaciones económicas puras. **La matriz de covarianza total sigue siendo la usada para difusión Monte Carlo, CVaR y shocks**, para no eliminar artificialmente el riesgo de pérdidas conjuntas. En parejas con al menos un ETF, el filtro utiliza la correlación total. F6 muestra la matriz total y la residual. Las propuestas anteriores al motor 0.4.0 se invalidan, manteniendo posiciones y supuestos.

**Tesis y factores.** Condiciones sobre margen, deuda neta/FCF, BPA, conversión de caja y dilución generan revisiones con evidencia fechada. La tesis textual, invalidación y catalizadores son investigación propia. Una presentación nueva requiere lectura; no implica una operación automáticamente. Factores: SPY y sector ortogonal al mercado, betas OLS, correlaciones residuales y atribución aritmética desde el registro. El residual significa no explicado; no mide habilidad. La atribución usa betas fijadas al registro y una referencia teórica; no concilia operaciones reales posteriores.

## Validación predictiva

Cada cálculo registra un origen con corte de precios, corte de información, fecha de creación, fundamentos, hipótesis, versión, semillas, covarianza y huellas de entradas/historia. El registro local usa IndexedDB y conserva los orígenes sin desplazarlos al llegar nuevos cortes. Los resultados vencidos quedan fijados con su fecha de observación. Exporta copias para protegerlos frente a la limpieza del navegador. Los retrospectivos se excluyen y los inmaduros permanecen pendientes. Un origen sólo se considera prospectivo entre el cierre y la apertura del siguiente día de semana en Nueva York; este filtro conservador puede excluir registros durante feriados. Al vencer, se usa la primera sesión común disponible y ambos extremos de la misma serie ajustada actual, evitando mezclar escalas anteriores a splits/dividendos.

Se informa Brier de la probabilidad de pérdida, cobertura P05–P95 y error absoluto. Son resultados de referencias mantenidas, con el costo inicial supuesto; no concilian retiros/operaciones del broker. Sin historia FX, las previsiones en otra moneda quedan no evaluables. Las previsiones con retiros también quedan sin puntuar hasta conciliar la realización de sus flujos; no se comparan contra un retorno sin retiros. Ventanas solapadas no son muestras independientes. Aún no existe una muestra prospectiva madura que demuestre capacidad predictiva.

La comprobación walk forward de F3 evalúa únicamente bandas EWMA de riesgo: 126 sesiones pasadas y 21 futuras no solapadas, centro logarítmico cero. No valida el ancla fundamental, los saltos ni la selección de acciones. El universo actual no resuelve sesgo de supervivencia ni incluye todos los deslistados.

## Datos y actualización

```bash
python scripts/refresh_data.py
# Corte máximo; no convierte datos actuales en versiones históricas disponibles entonces:
python scripts/refresh_data.py --as-of 2026-10-24
```

El colector usa la biblioteca estándar de Python y `pypdf` para leer el calendario del emisor (`python -m pip install -r requirements-research.txt`). Respuestas en `.cache/`, límites de consultas SEC, escritura atómica. Se conserva el último dato válido y se informa la incidencia si una fuente falla. `market.json.gz` es una copia gzip determinista de `market.json` que la web intenta cargar primero; si el navegador no admite descompresión o falta el archivo, utiliza el JSON ordinario. La fecha de corte común utiliza la fecha de cierre más frecuente (la más reciente si empatan), sin retroceder todo el universo por un único activo atrasado. **Refresh market data** corre diariamente a las **18:30 de Lima** (23:30 UTC) y publica el nuevo corte en GitHub Pages. La web consulta el archivo publicado cada cinco minutos mientras está visible y hay una referencia registrada.

| Fuente                          | Datos                                                                                            | Acceso                                        |
| ------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| SEC Company Facts / Submissions | Fundamentos, historia contable disponible, vencimientos estándar cuando existen y presentaciones | Sin clave; identificación de cliente          |
| Yahoo chart                     | Cinco años de cierres ajustados, volumen, dividendos y splits                                    | Endpoint público no oficial                   |
| U.S. Treasury                   | Curva par nominal                                                                                | XML oficial                                   |
| iShares                         | Duración, TIR, SEC yield y gastos de SHY/TLT con fecha                                           | Página pública del emisor                     |
| BLS                             | IPC general/subyacente, desempleo, nóminas, salarios y participación laboral                     | Una consulta por lote; v2 con clave           |
| FRED                            | Series macro y fechas de observación                                                             | CSV actual sin clave; API histórica con clave |
| FMP                             | Consenso anual y revisiones entre capturas                                                       | Clave y acceso al endpoint; uso local/privado |

Universo objetivo: **160 acciones y 100 ETF** (260 símbolos), entre sectores estadounidenses, estilos, países, renta fija y materias primas. Los CIK de acciones adicionales se resuelven en el catálogo oficial SEC; si falla la consulta y no existe una identificación anterior verificada, la acción queda fuera del corte y se informa la incidencia. Cada corte puede contener menos activos si faltan precios. La falta de fundamentales bloquea nuevas compras sin eliminar el instrumento del catálogo de precios. CASH se crea localmente con la remuneración neta declarada en el mandato, no como cotización descargada.

**Diagnóstico reproducible:** `node scripts/diagnose_portfolio.mjs` compara sobre el archivo publicado una búsqueda limitada con tope SHY original y tope SHY de 50%, usando las mismas semillas y presupuestos de simulación. Es una sensibilidad de implementación, no un backtest ni resultados suficientes para recomendar operaciones.

**Escala del optimizador:** cada ejecución permite muestras de **20, 40, 60 u 80 activos**, con 40 como valor inicial, conservando SHY, SPY, el benchmark y la cartera existente, y seleccionando el resto por documentación, liquidez histórica y representación de sectores. Se registra cuáles quedaron fuera de la muestra. Una propuesta no constituye una optimización global de los 260 instrumentos: ampliar el catálogo no obliga a comprar. Los supuestos P/E y crecimiento de las acciones añadidas son **hipótesis sectoriales editables**, no previsiones verificadas. Para REIT se dejan vacíos hasta incorporar valoración FFO/AFFO.

Los vencimientos sólo se muestran cuando existe el concepto estándar en Company Facts. La dilución requiere historia de acciones y ajuste documentado por splits. El BPA se contrasta con beneficio neto y acciones, considerando períodos contables comparables o splits recientes: una discrepancia extrema (más de 3 veces en uno u otro sentido) bloquea automáticamente su utilización en valoración, guarda el dato original como `eps_unverified` y muestra un aviso. Es un control de plausibilidad, no una conciliación contable integral; un BPA validado no garantiza valor intrínseco correcto. No hay cobertura completa de clases múltiples, conceptos XBRL personalizados ni calendario integral de deuda.

Las capturas inmutables en `data/snapshots/` conservan la información observada y una huella del archivo completo; no duplican toda la historia de precios. Capturar hoy un período contable antiguo no reconstruye su publicación original. Corte de precios, período económico, presentación y observación se conservan por separado.

### Claves opcionales

Se configuran como variables de entorno o secrets de GitHub Actions; nunca se escriben en JSON público.

| Variable         | Uso                                                                                    |
| ---------------- | -------------------------------------------------------------------------------------- |
| `SEC_USER_AGENT` | Identificación propia con contacto autorizado; también admite variable del repositorio |
| `FRED_API_KEY`   | Versiones históricas: realtime_start/realtime_end iguales al corte                     |
| `BLS_API_KEY`    | API v2 registrada y consulta conjunta de seis series; sin clave se usa v1              |
| `FMP_API_KEY`    | Consenso anual según plan/acceso del proveedor                                         |

Sin clave, FRED sólo acepta CSV para captura actual (`observed_current`), no reconstrucción histórica. FMP sólo se consulta localmente o en un repositorio privado. Este repositorio público no publica consenso aunque se configure una clave. El archivo personal `data/research/latest.json`, ignorado por git, se puede cargar en **Datos y fuentes → Importar corte JSON**. La base FMP de estimaciones es no GAAP; la moneda de reporte y el BPA base comparable deben verificarse antes de usarla en valoración. Comparar revisiones exige mismo ejercicio, moneda y base contable. La fecha de observación impide introducir consenso actual en un corte histórico.

## Ejecutar y comprobar

```bash
git clone https://github.com/Hardnyx/Trading.git
cd Trading
python -m http.server 8000 --directory dist
```

Abre `http://localhost:8000`. HTML, CSS y módulos JavaScript están separados; no requiere framework ni dependencias npm. Simulación y composición se ejecutan en Web Workers.

Con Node.js 20+ y Python 3.10+:

```bash
npm run check
npm test
python -m unittest discover -s tests -p 'test_*.py'
```

Referencias: [CFA: mandato](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/basics-of-portfolio-planning-and-construction), [CFA: construcción](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/active-equity-investing-portfolio-construction), [Boyd: decisiones con costos](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html), [SHY](https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf), [TLT](https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf), [sectores](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs), [FMP: estimaciones](https://site.financialmodelingprep.com/faqs?code=analyst), [SEC](https://www.sec.gov/about/developer-resources), [FRED](https://fred.stlouisfed.org/docs/api/fred/).


### Diagnóstico de concentración SHY

El motor 0.7.0 selecciona activos para la muestra limitada utilizando una valoración prospectiva penalizada por dispersión, volatilidad y cobertura sectorial, no retornos históricos ganadores. Explica por qué SHY puede recibir mucho peso: su carry observado, su riesgo condicional y la prima incierta de la renta variable. Compara candidatos explorados con máximos orientativos de SHY de 25%, 50% y 75%, presentando utilidad equivalente, retorno y CVaR sin forzar cuotas ni prometer óptimos globales. La búsqueda sigue siendo aproximada; fuera de muestra continúan los candidatos excluidos.

El filtro de GJR exige al menos 126 días OOS, mejora QLIKE >0.015, cota inferior unilateral positiva mediante bloques semanales y controles de cola y parámetros. Estos umbrales reducen activaciones débiles pero no prueban superioridad estadística conjunta de 177 comparaciones. El respaldo diario EWMA es deliberado. Sin fundamento económico suficiente no se infla la rentabilidad accionaria para fabricar diversificación.


### Alcance del parche 0.7.2

- La comparación de topes SHY de 25/50/75 % **incluye siempre** efectivo y escalones deterministas CASH/SHY, y los evalúa fuera de muestra de simulación con las mismas trayectorias. No afirmar «ninguna candidata» sin probar las alternativas conservadoras.
- SPY puede incorporarse a las **referencias, sin autorización de compra**, cuando faltan retornos ETF fundamentados: prima hipotética **3,5 puntos porcentuales sobre DGS3MO**, con incertidumbre **±15 pp**, visible y marcada como *no validada*. No se utiliza ese proxy para autorizar nuevas posiciones del optimizador.
- Las anclas que se muestran para fondos Treasury ya distinguen escenarios de tasas mediante duración y una **aproximación explícita de convexidad**. El modelo aún NO calcula toda la curva, cupones y reinversión de forma exacta. La TIR neta no es una rentabilidad garantizada.
- El CVaR es una estimación de Monte Carlo con marginales Student-t solo en los GJR aceptados y dependencia por cópula gaussiana; **no es un límite garantizado ni una estimación de colas validada en eventos extremos**.
- La selección sigue limitada a **40 instrumentos por ejecución** por costo de simulación. La rentabilidad esperada fundamental de las acciones y la probabilidad de regímenes siguen sujetas a validación fuera de muestra; no se presenta la búsqueda como óptimo global.
- Se añadió una prueba de que los benchmarks no comprables no se conviertan silenciosamente en posiciones sugeridas.

**Criterio para usar recomendaciones:** no ejecutar operaciones únicamente por esta simulación. Las correcciones arreglan inconsistencias verificables, pero no sustituyen una evaluación walk-forward del error en retornos, riesgo extremo, cambio de carteras y costos netos.


### Modelo de cartera 0.8.1: solapamientos, topes y dividendos

El nuevo máximo ordinario por instrumento es **35%** y afecta a SHY, acciones y ETF. Los Treasury ETF (SHY, SGOV, IEF, TLT, etc.) comparten un máximo agregado de **60%**. Los límites sectoriales integran ETF de sector y las participaciones de emisores se suman únicamente cuando hay holdings comprobadas, fechadas y conocidas antes del corte. **No existen holdings inventadas**: las faltantes aparecen como datos incompletos. Para pares con ETF se usa correlación histórica **total** en el filtro; la correlación residual se conserva como diagnóstico. Monte Carlo continúa utilizando covarianza total.

El límite excepcional de **50%** por oportunidad solo admite evidencia originada en pronósticos prospectivos, con al menos 126 realizaciones maduras, alfa neta con límite inferior positivo superior a 2 puntos porcentuales y revisiones independientes de factores, incertidumbre y liquidez. **Actualmente no existe una autorización de ese tipo**, así que la excepción no altera propuestas normales. Los topes son guardarraíles prudenciales iniciales, no pesos óptimos validados por un backtest.

Los retornos históricos ajustados ya incluyen distribuciones. En modalidad **dividendos a efectivo**, el sistema extrae de cada trayectoria la fracción de precio y suma por separado distribuciones monetarias (sin reinvertir), disponibles para retiros, descontando una retención configurable. En modalidad **revertir/reinvertir**, conserva el rendimiento total ajustado. La tasa de flujo procede de los dividendos observados en los últimos 12 meses; se reparte de forma aproximada entre los pasos de la simulación: **no es un calendario real de pagos ni una previsión contractual de futuros dividendos**. La retención inicial del 0% es un dato pendiente de configuración fiscal, no una exención presumida.

La pantalla de composición ahora dispone de reglas globales, grupo Treasury, ingreso neto estimado, correlación total y residual entre ETF, y un informe de holdings desconocidas. Se restauraron márgenes, interlineados y paddings sin introducir estilos ornamentales.

**Holdings de ETF (en curso):** el refresco automático ya consulta la API pública actual de TickerInside para ETF de renta variable. TickerInside reproduce archivos de emisores y SEC N-PORT, indica el origen y distribuye su *snapshot* actual con licencia [CC BY 4.0](https://tickerinside.com/legal/). Trading guarda el original comprimido solo cuando cambia la fecha del fondo, además de las primeras fechas de observación y la cobertura conocida. Es una **fuente secundaria**, no una confirmación de vigencia diaria del ETF. Véase [API y contrato de datos](https://tickerinside.com/api/). La desagregación todavía es parcial; los valores y clases no reconocidos no se inventan. La descarga de los ETF sin cobertura, ex-dates/pay-dates exactos, impuestos por jurisdicción, curva completa, PIT y validación de colas siguen pendientes. Un tope conserva diversificación por construcción, no prueba superioridad económica.

**Límite agregado de renta variable:** se añadió un máximo inicial de **50%** en acciones directas y ETF de renta variable combinados. Evita que un máximo de 35% en SHY desplace el exceso automáticamente hacia acciones individuales con primas fundamentales todavía no validadas. Es configurable, no un óptimo econométrico.


### Calendario y conciliación de distribuciones (0.9.0)

El refresco incorpora el calendario mensual publicado por iShares para los fondos cuya pertenencia al grupo se verifica en el documento. Para SHY y TLT también descarga el historial de importes y fechas de pago desde la ficha del emisor. El calendario se conserva con hash y primera observación; no se convierte una fecha prevista en una declaración de importe. Las distribuciones condicionales de fin de año se excluyen mientras no exista importe declarado.

La simulación reconoce un derecho al cobro en la fecha exdividendo y lo convierte en efectivo o nuevas participaciones al pago. Un retiro anterior no puede usar ese derecho como liquidez. Los importes futuros sin declaración siguen estimándose desde los últimos doce meses; entre puntos de simulación se interpola el precio, sin reconstrucción intradía. Si falta un calendario completo conocido al corte, se conserva la aproximación uniforme y se indica en pantalla.

El registro puede conciliar resultados vencidos solo con una ventana completa de eventos exdividendo y sus importes, pagos y precios contrastados. Las discrepancias, ventanas incompletas y splits pendientes dejan la evaluación sin puntuar. La retención y la reinversión al cierre siguen siendo convenciones del modelo, no una liquidación fiscal ni rendimiento conciliado del broker. No se modifican previsiones anteriores para hacerlas coincidir con datos posteriores.
