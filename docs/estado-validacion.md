# Estado de validación de Trading

**Fecha del diagnóstico:** 27 de octubre de 2026, con cortes de precios publicados por el repositorio.
**Clasificación:** investigación activa; no es asesoramiento de inversión ni certificación predictiva.

## Estado actual consolidado · motor 0.19.0

### Historia y contraste del crecimiento · 0.19.0

El recolector añade `financials.earnings_history`: hasta doce años de BPA
anual diluido, con cada versión disponible, su presentación y enlace al
informe SEC. Se excluyen formularios no periódicos, registros futuros,
periodos no anuales y conflictos dentro del mismo accession. La descarga
aprovecha la consulta companyfacts existente. Las capturas originales del
proyecto conservan la historia observada sin reescribir archivos previos.

El candidato `annual-eps-shrinkage-shadow-1` usa hasta cinco crecimientos
anuales publicados al origen. Contrae la media logarítmica hacia 6% con fuerza
cinco; esos valores son convenciones fijas. El resultado siguiente se mide
con BPA actual y comparativo del **mismo informe**, evitando mezclar bases de
splits. Los errores de bandas solo entran después de publicarse su resultado;
se requieren cinco errores anteriores y se comunica su cobertura observada.
Los casos con pérdidas o sin comparativo positivo no reciben un crecimiento
calculado a partir de bases negativas. No se eliminan crecimientos extremos
para mejorar el error.

`python scripts/earnings_growth_research.py` produce el detalle auditable,
comparadores pareados y MAE, RMSE, sesgo y cobertura. CI conserva el informe
como artefacto. F5 muestra la procedencia del crecimiento usado, la captura
local de la historia y el diagnóstico reconstruido. La propuesta guarda esa
procedencia junto con sus supuestos.

**Límite de interpretación:** es una reconstrucción de presentaciones desde
la respuesta SEC actual, con universo seleccionado hoy y posibles
reexpresiones. No certifica vintages originales ni observaciones prospectivas.
Un crecimiento de BPA anual no equivale a retorno de inversión calibrado a
tres años. El candidato queda `production_eligible=false`; no cambia
crecimiento, confianza, anclas ni bandas de la simulación. El punto P0.1
permanece abierto.

**Comprobaciones de 0.19.0:** 178 pruebas JavaScript y 123 Python aprobadas,
con versiones de fuentes consistentes. Se comprueba que futuras
presentaciones no cambien la previsión ni la banda de un origen anterior,
que un split no mezcle cifras de informes distintos y que la historia
reconstruida no cambie las anclas de producción.

### Protecciones conservadas · 0.18.0

El universo contiene 260 instrumentos (160 acciones y 100 ETF). Los tickers y los indicadores de cálculo del commit definitivo `f43efeb` se conservan. El [backlog actualizado](pendientes.md) aplica los criterios de cierre proporcionados. Las correcciones de integridad de la auditoría se implementan así:

| Hallazgo | Estado de implementación | Límite que permanece |
|---|---|---|
| H7 · BPA mezclado tras un split | Comprobación por componente, independiente del beneficio neto y de la ruta de recuperación; también se aplica al cargar snapshots anteriores | BKNG se bloquea hasta contar con una base conciliada; no se inventa un BPA nuevo |
| H1 · Valor presente con BPA continuado | Valor presente, escenario base y fórmula usan el mismo múltiplo de referencia | La reversión parcial sigue siendo una convención para el retorno esperado |
| H3 · Intereses y retiros | El efectivo cobra desde cada pago y deja de cobrar al retirarse; se comparte el tratamiento con atribución y robustez | Los dividendos sin calendario mantienen su aproximación uniforme dentro del intervalo |
| H4 · Realización de intereses | Sin intereses de cuenta observados, el resultado permanece sin conciliar | Una tasa declarada no sustituye al rendimiento realizado |
| H2 · Alcance del registro de riesgo | Identifica referencias estadísticas y deja de atribuir su cobertura al simulador exacto | Validación de la distribución exacta y del CVaR de cartera pendiente |
| H5 · Covarianza después de marginales t | Registra matrices latente e inducida por separado; las porciones de varianza inicial usan la segunda | Aproximación numérica PSD; dependencia extrema y covarianza de todo el horizonte sin validar |
| H6 · Resultados ausentes | Registros de completado por instrumento, con hash del sello y de la fuente; no se reescriben resultados previos | Hace falta que se recupere una observación comparable |

La matriz inducida utiliza una expansión de Hermite de orden 25 y cuadratura sobre la transformación efectivamente simulada. Se informa su resto de proyección; no constituye una recalibración empírica. Referencia metodológica: [correlaciones y cópula gaussiana mediante Hermite](https://arxiv.org/abs/1608.00738).

Los puntos 24 y 25 del backlog se cierran: la prueba del navegador cubre cualquier cambio de `dist/**`, incluida toda plantilla y CSS, y se actualizan README, estado consolidado y tabla del documento técnico. Las secciones posteriores conservan la historia de implementación y sus fechas.

**Prioridades todavía abiertas:** historia de BPA y calibración de crecimiento con información disponible al corte; anclas económicas de ETF con cobertura trazable; crédito/TIPS y tasas reales; observaciones prospectivas maduras; dependencia conjunta; eventos verificados; estabilidad del optimizador y conciliación real de cuenta. No se promueve ninguno de esos modelos por haber aprobado pruebas de software.

**Comprobaciones de 0.18.0:** 174 pruebas JavaScript y 114 Python aprobadas, versiones de fuentes consistentes y sin errores de formato del diff. Incluyen el BPA mezclado con beneficio neto ausente, la igualdad numérica de la fórmula de valoración, varios retiros dentro de un intervalo, intereses desde la fecha de pago, conciliación pendiente de intereses no observados, matriz inducida PSD y completado inmutable de resultados recuperados. Estas comprobaciones corresponden al software y no sustituyen validación económica.

## 1. Qué significa «implementado»

El proyecto distingue cuatro estados que **no son intercambiables**:

- **Operativo:** el software ejecuta una función y sus pruebas pasan.
- **Experimental:** calcula pronósticos paralelos, conserva sus errores y no decide operaciones.
- **Validado en riesgo:** demuestra mejora predefinida de riesgo en múltiples cortes fuera de muestra y supera comparadores sencillos.
- **Validado económicamente:** demuestra mejora de utilidad neta, estabilidad, costos y selección de cartera usando datos realmente disponibles en cada fecha.

La aprobación de GitHub Actions certifica ejecución y consistencia de software. **No convierte un pronóstico en uno estadísticamente calibrado.**

## 2. Evidencia reproducible añadida

| Investigación | Comando | Regla de promoción |
| --- | --- | --- |
| Integridad temporal de capturas | `python scripts/run_research_audit.py` | No permitir archivos obtenidos después de emitir la previsión; rechazar solicitudes históricas que no son vintages originales |
| Eventos SEC con fecha real y primera observación | `python scripts/build_event_registry.py` | Mantener sello original de publicación y recepción; no inventar consenso |
| GJR-t sobre residuos multifactoriales | `python scripts/multifactor_research.py` | Comparar QLIKE con EWMA residual mediante múltiples ventanas independientes |
| Riesgo de cola | `python scripts/tail_research.py` | Comprobar cobertura VaR, agrupamiento de excepciones, ES y co-excedencias |
| Densidad conjunta Student-t vs normal | `python scripts/joint_tail_research.py` | Ganancia estable de logscore predictivo fuera de muestra, no solo dentro de muestra |
| Noticias y GARCH-X | `python scripts/news_garchx_research.py --events out/sec-filing-events.json` | Necesita sorpresas verificadas con consenso conocido ANTES del evento y mejora incremental en holdout |
| Estabilidad de cartera | `node scripts/portfolio_stability.mjs` | Estabilidad ante semillas, límites del universo y presupuesto de búsqueda |
| Holdings fechadas de ETF | `python scripts/refresh_data.py` (captura actual) | Conservar primeros accesos, cobertura parcial y fuente TickerInside/issuer/SEC; no usar nuevas capturas para reconstruir carteras históricas |
| Pronóstico prospectivo permanente | `node scripts/seal_forecast.mjs --skip-ineligible` | Sellado antes de la siguiente sesión de mercado, sin sobrescritura |
| Resultados posteriores a maduración | `node scripts/seal_forecast.mjs --score` | No evaluar un retorno a doce meses antes de conocerlo |
| Riesgo diario sellado por activo | `python scripts/risk_ledger.py seal --skip-ineligible`, `score`, `summary` | Sellar h, VaR95 y ES95 antes de la apertura siguiente; puntuar solo la primera sesión posterior; interpretar desde 20 sesiones y 500 activo-días |

El workflow **Research evidence (shadow)** ejecuta estas investigaciones, guarda archivos JSON como artefactos y nunca modifica directamente el optimizador de la página.

## 3. Primeros resultados (no constituyen pruebas de superioridad)

Una ejecución sobre 63 pronósticos de volatilidad multifactorial encontró diferencias promedio QLIKE (EWMA menos GJR) de aproximadamente +0,0114 para AMZN, +0,0126 para NVDA y −0,0031 para SHY. Estas ventanas son pequeñas para declarar estabilidad.

La prueba de densidad bivariante Student-t frente a normal produjo mejoras de logscore en un primer holdout para varios instrumentos, pero el modelo aún supone covarianza histórica aproximadamente constante. **No es DCC-GARCH ni garantiza cobertura del CVaR anual.**

El registro automático extrae alrededor de mil acontecimientos de la SEC en los archivos revisados, todos con sello temporal. **Ninguno contiene por sí solo una sorpresa numérica verificada frente a un consenso anterior**. Por eso la evaluación GARCH-X comunica «evidencia insuficiente»; no se asigna un sentimiento artificial a cada 10-Q o 8-K.

La auditoría de estabilidad del motor mostró SHY en 60 % con 40 activos y búsqueda base, 75 % al utilizar 30 activos y 45 % con búsqueda ampliada. El CVaR calculado para cada configuración no es necesariamente pareado al de otra: cambian las candidatas y las trayectorias. **La selección es sensible al problema de búsqueda.**

La evaluación de vintages reconoce que las capturas de octubre de 2026 no son registros contables completos que reproduzcan lo que se conocía todos los días de años anteriores. En la primera revisión no había pronósticos de doce meses con origen original y resultado ya maduro. Cualquier afirmación de rentabilidad predictiva histórica sería prematura.

## 4. Futuro registro automático de previsiones

El workflow de renovación de mercado añade el intento de sellar una previsión una sola vez por corte de mercado.

- El archivo `data/forecasts/YYYY-MM-DD.json` solo se crea si se obtuvo el mercado antes del primer horario de apertura ordinario siguiente (regla conservadora de días laborables). No sobrescribe un origen anterior para el mismo corte.
- Incluye fecha y hora de emisión, hash SHA-256 del mercado y parámetros de volatilidad, modelo, corte de precios, pesos y distribución de pronóstico.
- La evaluación `--score` opera exclusivamente después del vencimiento y escribe un archivo de resultado independiente. Un activo deslistado o ausente no se transforma en rentabilidad cero: su evaluación queda incompleta.
- Los retornos realizados calculados posteriormente sobre precios ajustados son una **aproximación bruta**, no una medida de rentabilidad operativa neta y sin sesgos.
- Los orígenes sellados no prueban capacidad de predicción hasta acumular suficientes observaciones maduras en horizontes distintos y hacer comparaciones ajustadas por dependencia temporal.

Los días festivos de NYSE, datos de alto impacto publicados intradía, las correcciones de proveedores y los cambios en composición histórica de índices requerirán infraestructura adicional para una certificación completa.

## 5. Interfaz de atribución

La propuesta ofrece para USD sin retiros un desglose de retorno medio y pérdida condicional en el peor 5 % sobre los mismos escenarios de verificación, junto a la contribución a varianza. Los costos iniciales se concilian separadamente.

```math
E[R_p]\approx\sum_i w_i E[R_i]-C,\qquad
ES_{95}^{\mathrm{pérdida}}=\sum_i\left(-w_i E[R_i\mid R_p\leq VaR_{5}]\right)+C.
```

Los resultados son **aditivos para la muestra simulada y sus supuestos específicos**. No son contribuciones causales, gradientes CVaR ni pruebas de que un instrumento tenga una prima futura conocida.

## 6. Lo que sigue realmente pendiente

| Tema | Estado actual | Lo que falta para producir señales |
| --- | --- | --- |
| Retornos económicos esperados | Anclas y valoración parcial | Vintages contables/consenso, calibración de priors y errores de previsión maduros |
| Factor-GJR residual | Candidato multifactorial experimental | Validación extensa y comparación de riesgo de cartera contra el modelo sencillo |
| Correlación dinámica DCC | No promovida | Estimación, shrinkage, sensibilidad por régimen y pruebas de cola fuera de muestra |
| Student-t multivariante | Challenger de densidad aislado | Integración con volatilidad condicional y calibración de coexcedencias sin doble conteo |
| Eventos/news y GARCH-X | Registro de releases; challenger sin datos de sorpresa suficientes | Sorpresas con consenso original, modelos de enlace, inferencia temporal y suficientes eventos |
| Renta fija | TIR, duración y convexidad proxy | Cero cupón/par, rolldown de curva completa, reinversión, crédito y liquidez |
| Universo de activos | 177+ instrumentos, 40 simulados en la web | Incorporación iterativa del catálogo, convergencia de pesos y búsqueda más rigurosa |
| Holdings de ETF | Ingesta automática, parcial, con datos fechados, atribuidos y originales comprimidos | Mayor cobertura oficial, auditoría de clasificación sectorial, reconciliación de posiciones no reconocidas y vintages suficientemente largos |
| Backtest de decisiones | Registro prospectivo y diagnósticos | Maduración de observaciones y comparaciones con SPY, SHY, efectivo y cartera pasiva neta de costos |
| Operativa | Costos y reglas parciales | Política de mantener/reducir/salir asociada a invalidación de tesis y utilidad incremental |

**Regla invariable:** no se habilitarán nuevas distribuciones, shocks, priors ni reglas de compra solamente por complejidad matemática. Deben aportar evidencia incremental y resultados reproducibles con información conocida al corte.

### Prioridades consolidadas de los hilos del proyecto (26 de octubre)

1. **Vigencia de fundamentales (0.11.0):** panel por empresa, período BPA, fecha de presentación, captura XBRL y vínculo al informe; bloqueo de nuevas propuestas cuando existe informe posterior no conciliado. En la captura revisada había 13 candidatos a rezago y 4 empresas sin BPA utilizable de 100. La API companyfacts consultada para KO, NEE y C no contenía BPA estándar del informe reciente. La descarga por sí sola no resuelve esa cobertura. **Pendiente:** extraer y conciliar hechos del documento original, conservar contexto/unidad/escala y rechazar resultados no comparables. No se ha implementado ese extractor alternativo ni se declara actualizado el BPA faltante.
2. **Retornos:** normalización contable de beneficios extraordinarios/cíclicos, consenso privado integrado y calibración de crecimiento, múltiplos e incertidumbre con vintages originales. El estrés de margen ya implementado no sustituye esta tarea.
3. **Universo y riesgo:** ampliar la simulación más allá de 40 instrumentos, verificar convergencia, completar holdings, GJR residual, dependencia dinámica y colas multivariantes fuera de muestra.
4. **Operativa:** el detalle de transición y alertas está implementado; faltan política integrada de salida/reentrada, deshacer cambios de composición, lotes enteros y conciliación de operaciones con broker.
5. **Datos adicionales:** ampliar pagos oficiales, fiscalidad por instrumento y jurisdicción, curva completa/rolldown y sorpresas informativas conocidas antes del evento para GARCH-X.
6. **Bloomberg externo:** el extractor Excel/Python pedido no consta en este repositorio ni en el workspace auditado. Falta implementación/prueba autorizada en un equipo con Bloomberg, almacenamiento raw/normalizado, caché y control de consumo. Sus datos no se deben publicar en Pages.
7. **Validación económica:** el registro prospectivo y las pruebas de software existen; falta maduración suficiente y comparación neta contra SPY, SHY, efectivo y cartera pasiva. No puede completarse anticipando resultados futuros.

La guarda de vigencia compara el período del último 10-Q/10-K/20-F con el BPA y filtra documentos posteriores al corte. Un 8-K o una enmienda no acreditan un período nuevo. Para capturas antiguas sin `report_date`, una presentación posterior exige verificación conservadora. La ausencia de informe posterior detectado no certifica cobertura completa. El reloj de descarga no se usa para rejuvenecer la fecha económica del dato; una captura conservada tras fallo se identifica explícitamente.

### Monitor de precios 0.12.0

Se separan tres capas: precios observados para todo el catálogo (177 instrumentos: 100 acciones y 77 ETF en el corte revisado; el efectivo se añade por separado en el compositor), anclas económicas con cobertura fundamental/renta fija y composición restringida a una muestra de hasta 40. El monitor no reduce el catálogo a la muestra del optimizador. Permite filtrar acciones con BPA pendiente, posiciones de cuenta/cartera y rupturas/cruces observados. Las cuentas existentes no se borran por falta de BPA.

Indicadores descriptivos: MA50/MA200 de cierres ajustados, retorno de 126 sesiones, ruptura frente a las 63 previas excluyendo el cierre actual, caída desde máximo de 252 y volatilidad logarítmica anualizada de 63 sesiones con razón 21/63. Se requieren al menos 252 observaciones válidas, orden estricto y cierre común vigente. No se usa retorno histórico como ancla esperada, no se interpreta BPA ausente como venta y no se habilitan compras nuevas por una ruptura. Las distancias son sobre el índice ajustado por distribuciones, no precios de órdenes.

Yahoo sigue siendo un endpoint público no oficial para cierres ajustados; se conserva fecha económica y primera captura disponible del resultado descargado. La colección evita la barra diaria incompleta de la sesión en curso. [HISTORIALCOTIZACIONES](https://support.microsoft.com/es-es/excel/functions/stockhistory-function) ofrece históricos y generalmente actualiza tras completar la sesión, no sustituye el estado contable ni una fuente intradía. Un adaptador Excel puede ser una alternativa local, no un requisito del sitio público. **Pendiente:** validar reglas técnicas y su utilidad incremental con costos fuera de muestra antes de darles capacidad de decisión.

### Universo ampliado y presupuesto de composición 0.13.0

El catálogo curado pasa a 260 instrumentos previstos: 160 empresas y 100 ETF. Se añaden 60 empresas de software, semiconductores, seguros, salud, industria, comercio, energía y materiales, además de 23 ETF globales, de estilo y capitalización. Cada CIK nuevo debe resolverse por símbolo exacto en el registro SEC; en la comprobación de identidad se sustituyó MMC por el ticker vigente MRSH. Una identidad válida no acredita precio descargado, cobertura contable completa ni inclusión histórica en un índice.

Los nuevos estados financieros siguen las mismas reglas de fechas, BPA comparable y advertencias de informes posteriores. No se relajan para conseguir más candidatas. Los ETF sin clasificación, holdings o ancla económica suficiente permanecen en observación y no reciben permiso automático de compra. Los supuestos sectoriales son hipótesis editables, no consenso.

Los 23 ETF nuevos tienen grupo económico: 17 USA, 3 internacionales ex-USA y 3 globales (VT, ACWI, URTH). Los globales pueden incluir Estados Unidos y no se presentan como una cartera exclusivamente extranjera. Sin holdings comprobadas no se inventan pesos geográficos ni por emisor; la exposición desconocida sigue consumiendo capacidad de concentración y los topes de renta variable agregada permanecen vigentes.

En Límites de la propuesta se habilitan muestras máximas de 20, 40, 60 u 80 activos. Cuarenta sigue siendo el presupuesto predeterminado. Cuenta, comparadores y diversificación se retienen con los mismos controles; el presupuesto se guarda en la propuesta y cambiarlo invalida el resultado. Mayor tamaño aumenta memoria y tiempo; no prueba convergencia ni optimalidad global. La selección sigue dependiendo del conjunto elegible y las hipótesis. El registro shadow y la comprobación de estabilidad siguen siendo necesarios.

## 7. Cómo ejecutar la investigación

```bash
python -m pip install -r requirements-research.txt
python -m unittest discover -s tests -p "test_*.py"
npm test
python scripts/run_research_audit.py
python scripts/build_event_registry.py
python scripts/multifactor_research.py
python scripts/tail_research.py
python scripts/joint_tail_research.py
python scripts/news_garchx_research.py --events out/sec-filing-events.json
node scripts/portfolio_stability.mjs
```

Los JSON de `out/` son diagnósticos temporales. No deben copiarse a `dist/data/` ni usarse en decisiones del navegador hasta que superen validación y revisión de licencias.


### Modelo de cartera 0.8.1: solapamientos, topes y dividendos

El nuevo máximo ordinario por instrumento es **35%** y afecta a SHY, acciones y ETF. Los Treasury ETF (SHY, SGOV, IEF, TLT, etc.) comparten un máximo agregado de **60%**. Los límites sectoriales integran ETF de sector y las participaciones de emisores se suman únicamente cuando hay holdings comprobadas, fechadas y conocidas antes del corte. **No existen holdings inventadas**: las faltantes aparecen como datos incompletos. Para pares con ETF se usa correlación histórica **total** en el filtro; la correlación residual se conserva como diagnóstico. Monte Carlo continúa utilizando covarianza total.

El límite excepcional de **50%** por oportunidad solo admite evidencia originada en pronósticos prospectivos, con al menos 126 realizaciones maduras, alfa neta con límite inferior positivo superior a 2 puntos porcentuales y revisiones independientes de factores, incertidumbre y liquidez. **Actualmente no existe una autorización de ese tipo**, así que la excepción no altera propuestas normales. Los topes son guardarraíles prudenciales iniciales, no pesos óptimos validados por un backtest.

Los retornos históricos ajustados ya incluyen distribuciones. En modalidad **dividendos a efectivo**, el sistema extrae de cada trayectoria la fracción de precio y suma por separado distribuciones monetarias (sin reinvertir), disponibles para retiros, descontando una retención configurable. En modalidad **revertir/reinvertir**, conserva el rendimiento total ajustado. La tasa de flujo procede de los dividendos observados en los últimos 12 meses; se reparte de forma aproximada entre los pasos de la simulación: **no es un calendario real de pagos ni una previsión contractual de futuros dividendos**. La retención inicial del 0% es un dato pendiente de configuración fiscal, no una exención presumida.

La pantalla de composición ahora dispone de reglas globales, grupo Treasury, ingreso neto estimado, correlación total y residual entre ETF, y un informe de holdings desconocidas. Se restauraron márgenes, interlineados y paddings sin introducir estilos ornamentales.

**Pendiente:** descarga y conciliación diaria de todas las holdings de emisores, ex-dates/pay-dates exactos, tratamiento fiscal por jurisdicción, curva de tasas completa, validación PIT y calibración predictiva del riesgo de cola. Un tope conserva diversificación por construcción, no prueba superioridad económica.

**Control adicional 0.8.1:** la exposición a renta variable directa y ETF accionarios también se limita a 50% agregado por defecto, para que el tope individual de SHY no transfiera sin más el riesgo hacia acciones con retornos no calibrados. No sustituye una evaluación histórica de objetivos y utilidad.

### Correcciones 0.8.3: exposición completa y conciliación de distribuciones

- Los 77 ETF del catálogo publicado tienen clasificación económica. VGSH, VGIT, VGLT y SHV consumen el presupuesto Treasury; los fondos de estilo, dividendos y países consumen el de renta variable. Los ETF de clasificación desconocida no se autorizan para compras nuevas.
- El límite inicial de 20% por acción suma exposición directa e indirecta por emisor y agrega clases conocidas. La composición faltante consume capacidad mediante cotas conservadoras por emisor y sector. Las cotas se identifican como tales y no como holdings observadas.
- La ingesta cubre también el catálogo ampliado de ETF accionarios y admite hasta 5.000 posiciones, en lugar de recortar cada fondo a 300. Conservar una captura no obliga a considerarla vigente: a partir de 120 días se trata como composición desconocida. Una respuesta antigua del proveedor no reemplaza otra más reciente; las revisiones del mismo día se archivan con hashes diferentes.
- El dividendo del paso usa el precio del mismo paso para conservar la identidad de rendimiento total. La retención también se aplica al reinvertir. La atribución concilia con la valoración sobre los mismos escenarios, costos y política.
- El diario conserva la política efectivamente simulada. Sin conciliación realizada de distribuciones o impuestos, no calcula Brier ni cobertura usando solo precios ajustados. Los resultados incompletos pueden reevaluarse en un refresco futuro; no se fijan como un desenlace definitivo. Las capturas originales existentes no se reescriben.

Sobre el mismo corte del 23 de octubre, semilla 20261024, USD 100.000, 300 candidatas, 600 escenarios de búsqueda y 3.000 de verificación, la comprobación determinista cambió AMZN de 20% a 15%, sustituyó GOOGL 5% por MU 5% y NVDA 5%, conservando SHY 35%, efectivo 15%, CMCSA 20% y NFLX 5%. El retorno mediano simulado fue 5,70% y CVaR 12,08%, frente a 5,43% y 13,35% en 0.8.1. **La diferencia describe dos resultados de búsqueda bajo supuestos, no una mejora económica demostrada fuera de muestra.**

La cobertura real del proveedor sigue siendo parcial. Fechas de pago confirmadas, fiscalidad por instrumento, curvas completas, sorpresa de noticias, calibración de retornos y validación de colas continúan pendientes de datos y evidencia suficientes.


### Distribuciones con fecha y derecho de cobro (0.9.0)

- Ingesta del calendario mensual oficial iShares con comprobación de pertenencia al grupo, publicación, alineación de fechas y primera observación. Las fuentes originales se identifican por SHA-256; el repositorio conserva los hechos normalizados.
- Historial del emisor para SHY/TLT con importe por participación, fecha exdividendo, registro y pago. El índice de eventos exdividendo de Yahoo se conserva para todo el universo con su ventana de cobertura. No suministra por sí solo fechas de pago.
- Simulación con cuentas por cobrar, efectivo disponible y reinversión al pago. Las retiradas y pagos se ordenan por fecha dentro de un mismo paso semanal. La valoración entre pasos sigue siendo interpolada; no es una simulación intradía.
- Si el calendario no cubre todo el horizonte o no era conocido al corte, se utiliza y etiqueta la aproximación uniforme. Los importes no declarados son supuestos derivados del rendimiento distribuido histórico, no obligaciones contractuales futuras.
- Conciliación realizada bajo la retención supuesta y la reinversión al cierre del mandato. Se exige contraste de eventos, cantidades y precios. Un split sin resolver o una ventana incompleta mantiene el resultado pendiente. No se confunde esta convención con operaciones, retenciones o abonos reales del broker.

Las pruebas incluyen un retiro antes y después de un pago dentro del mismo intervalo de simulación, una cuenta por cobrar al vencimiento, reinversión con retención, fechas no conocidas al origen y preservación del pronóstico original. La prueba de identidad contable no demuestra calibración predictiva.

El contraste contable posterior sobre los 12 eventos de SHY del 23 de octubre de 2025 al 23 de octubre de 2026 detectó importes de Yahoo observados a tres decimales frente a seis del emisor. La conciliación admite esa rejilla únicamente para la fuente de Yahoo y cuando el importe oficial redondea al dato observado; conserva el importe preciso del emisor y registra los emparejamientos por redondeo. No aplica una tolerancia porcentual arbitraria ni acredita capacidad predictiva.

**Sigue pendiente:** ampliar fuentes de pagos declarados a todas las acciones y ETF, fiscalidad por instrumento y jurisdicción, conciliación con el broker, curvas completas y evidencia prospectiva suficiente sobre retornos, colas y noticias. La publicación de un calendario no resuelve esos puntos.

### Ampliación de pagos oficiales y explicación de anclas (26 de octubre)

La ingesta de historiales oficiales se amplía de SHY/TLT a doce ETF: SHY, TLT, AGG, IEF, IEI, SGOV, SHV, TIP, LQD, HYG, EMB e IGSB. Se contrastaron las doce páginas reales con el parser. Cada página debe identificar el ticker, el producto y USD antes de aceptar su tabla. Los historiales normalizados se archivan por fondo y hash de la fuente, sin sobrescribir una captura anterior. Un fallo conserva el historial previo y deja el refresco como parcial. Esta cobertura de pagos no incorpora automáticamente nuevos perfiles de duración ni autoriza compras de ETF sin una expectativa de retorno fundamentada.

La composición distingue ahora el BPA publicado de los supuestos efectivos de crecimiento, P/E de salida, horizonte de valoración y confianza asignada. Una propuesta antigua sin ese desglose solicita recalcularla. Los supuestos de valoración no se presentan como consenso ni como parámetros calibrados.

En el corte de precios del 23 de octubre, CMCSA utiliza crecimiento del BPA de 4%, P/E de salida 16 y valoración a tres años. El modelo de valoración produce 38,92% anual; la mezcla con un prior de 6% y confianza asignada de 51,43% reduce el ancla a 22,93%. Esto explica su prioridad bajo esos supuestos; no prueba que el múltiplo sea alcanzable ni que la rentabilidad se materialice en los doce meses simulados. El margen normalizado, por sí solo, tampoco modifica la base de BPA del modo de valoración propio.

La cartera mostrada (SHY 35%, efectivo 15%, CMCSA 20%, AMZN 15%, MU/NFLX/NVDA 5% cada una) alcanza los topes de SHY, CMCSA y renta variable agregada. Las correcciones contables y la ampliación de fuentes no se usan para forzar una cartera distinta. Continúan pendientes calibración de supuestos, normalización de beneficios cíclicos y evidencia prospectiva madura.

### Comparación robusta de carteras

Se incorpora [optimización bajo incertidumbre de valoración](optimizacion-robusta.md): cinco modelos económicos alternativos, universo fijo, números aleatorios comunes, búsqueda por asignaciones e intercambios locales, minimización del arrepentimiento y verificación semanal con semilla independiente. La mejora frente a mantener exige un margen superior al costo mínimo y al error Monte Carlo aproximado ajustado por la familia de comparaciones.

El procedimiento vive en investigación; no altera las anclas de producción. Distingue un estrés proporcional del BPA de una normalización contable, y la admisibilidad por topes de una demostración de superioridad económica. El workflow conserva una referencia sintética; las cuentas locales y sus informes están excluidos de Git. Ninguna salida constituye un óptimo global ni una validación prospectiva madura.


### Página 0.10.0: comparación robusta de la sesión

El botón **Comparar robustez** ejecuta el núcleo compartido en un Web Worker y muestra pesos candidatos, cinco escenarios, referencia al mantener, costos y límite inferior de mejora. El usuario conserva el control de la cartera: el cálculo no aplica pesos; una acción separada los copia para simular. El resultado caduca cuando cambian sus entradas o el corte y puede cancelarse durante su ejecución. El soporte actual se limita a crecimiento en USD sin flujos, suelo ni meta de capital; un mandato incompatible recibe una explicación explícita.

Los perfiles Treasury oficiales se amplían a IEF, IEI, SGOV y SHV mediante la página del emisor ya contrastada por ticker, producto y moneda. Se preservan fuente, hash, fecha y última captura válida cuando falla la actualización. Esta ampliación no acredita la calibración de sus retornos ni sustituye modelos propios de crédito o inflación.

### Transición de la candidata y conciliación de efectivo

La comparación robusta incorpora un panel desplegable de cambios por instrumento, cantidades fraccionarias a precios del corte y costos desagregados. Los montos se calculan sobre capital neto de costos y se verifica la igualdad de efectivo inicial, ventas, compras, costos y reserva final. Cuando no existe ventaja robusta, se muestra como comparación hipotética. Esto cubre la explicación operativa de la candidata; siguen pendientes señales por invalidación de tesis, lotes enteros, precios ejecutables y conciliación real con broker.

### Recuperación desde el informe original SEC

Cuando el BPA falta, no supera la conciliación de escala o hay un informe primario
posterior, el recolector intenta el iXBRL del último 10-Q/10-K/20-F. Extrae sólo
conceptos estándar US GAAP consolidados en USD y USD/acción; conserva periodo,
fecha de presentación, accession, URL y captura del documento. Omite dimensiones,
otras entidades, unidades/transformaciones no soportadas y duplicados discrepantes.
No interpreta conceptos particulares del emisor ni sustituye cifras ausentes.

La reconstrucción TTM conserva sus componentes (anual + acumulado actual −
acumulado anterior) para auditar fuentes y fechas. Una combinación de informes
alrededor de un split permanece bloqueada si no se acredita la misma base por
acción. La comprobación de vigencia y el bloqueo por beneficio/acciones siguen
activos. La tabla de cobertura distingue la captura de companyfacts de la captura
del informe original. Recuperar datos no valida crecimiento, múltiplos ni retornos.

### 0.14.0 — Puente del BPA y sensibilidad a la base contable

Se recolectan por separado BPA diluido total, de operaciones continuadas y
operaciones discontinuadas netas de impuestos mediante conceptos estándar SEC
US GAAP (incluido el alias histórico de discontinuadas). El iXBRL original puede
completar esos conceptos cuando se activa la recuperación de un informe.

El puente exige tres observaciones publicadas al corte, mismo periodo/método y
los mismos intervalos en sus componentes TTM. Se verifica la reconstrucción de
cada cifra y total = continuadas + discontinuadas. La tolerancia de redondeo es
min(0,05; max(0,005; 0,5% del BPA total absoluto)), en USD/acción; es una regla
operativa conservadora, no un umbral estimado. Un componente ausente no se
interpreta como cero. Se rechazan bases distintas alrededor de splits.

El usuario puede seleccionar BPA continuado conciliado para la previsión propia.
La opción exige BPA continuado positivo y no permite mezclarlo con modelos de
márgenes o consenso sin otra conciliación. Conserva los bloqueos de vigencia.
Por defecto se utiliza BPA total reportado. Para previsión propia con ambas bases
positivas y conciliadas, la diferencia entre sus retornos de valoración fija un
mínimo de amplitud simétrica alrededor del modo de la previsión. El modo reportado
no cambia por este diagnóstico y tampoco se altera la confianza subjetiva.

La página presenta cifras, diferencia, fecha, estado del puente y sensibilidad.
No es una normalización completa: operaciones continuadas puede incluir deterioros,
reestructuraciones, impuestos excepcionales y beneficios de pico del ciclo. Los
rangos son sensibilidad condicional a supuestos, no intervalos de predicción
calibrados. Queda pendiente estimar errores y cobertura fuera de muestra con
vintages y horizontes comparables.

Las capturas se guardan como instantes UTC y se muestran completas en la zona
horaria configurada en el navegador, detectada con Intl sin geolocalización. Se
explicita la zona y su desfase aplicable a ese instante, incluido horario de verano. Se eliminó el recorte de fecha UTC en la propuesta, que hacía aparecer
27 de octubre para una captura realizada el 26 por la noche en Lima. Fechas
contables y fechas de presentación permanecen como fechas de sus documentos.

### Continuidad de FRED y auditoría de calibración

Las consultas FRED actuales permiten que el proveedor determine su propio día de
versión y guardan la fecha efectivamente devuelta. Los cortes históricos fijan
explícitamente `realtime_start` y `realtime_end`. Esto evita imponer el día UTC
siguiente al proveedor durante la noche estadounidense. No se atribuye al error
HTTP 400 una causa única sin disponer de su diagnóstico autenticado.

Si falla la API en una descarga del día, se intenta el CSV oficial. Queda marcado
como `observed_current`, con `api_fallback` y código HTTP sanitizado; el estado del
proveedor informa cuántas series usan cada vía. El respaldo actual está prohibido
para reconstruir cortes históricos. Si fallan ambas vías se mantiene la incidencia
visible y el dato anterior con su fecha. No se exportan claves ni URLs autenticadas.
Fuente técnica: https://fred.stlouisfed.org/docs/api/fred/series_observations.html

La validación prospectiva añade una auditoría separada por versión, modelo,
horizonte, moneda y métodos de retorno/volatilidad. Selecciona ventanas sin solape
por vencimiento más temprano, sin mirar aciertos ni rentabilidades. Presenta sesgo,
MAE, RMSE, Brier, cobertura y un intervalo Wilson 95% descriptivo para la cobertura.
El mínimo de 20 ventanas es una regla operativa, no un análisis de potencia.
Sin solape no significa independencia; se necesitan pruebas fuera de muestra y
estabilidad adicional. Este diagnóstico no promueve parámetros automáticamente ni
convierte una muestra inmadura en evidencia de capacidad predictiva.

### 0.15.0 — Coherencia de riesgo y evidencia diaria

**Correlación residual comparable.** La matriz residual usa ahora la misma
ventana equiponderada que la correlación total (252 o 500 sesiones según la
vista). Antes se calculaba con EWMA λ=0,94, cuya muestra efectiva ronda 32
sesiones (vida media ≈11): en el corte del 26 de octubre mostraba TLT–AMZN
−0,67 frente a −0,13 con 500 sesiones equiponderadas. Esa matriz alimentaba
además el tope de correlación entre pares de acciones del compositor. La EWMA
se conserva como diagnóstico reciente, con su vida media y el desvío máximo
frente a la ventana completa. No es una regularización óptima estimada ni un
DCC; la ventana completa reduce el ruido muestral sin validar su estabilidad.

**Proceso simulado visible.** Proyecciones describe el proceso que corre el
Monte Carlo: GJR-t validado más EWMA diario, o EWMA diario, siempre sin saltos.
El selector GBM/Merton y los parámetros de salto solo aparecen con el
comparador legado elegido en Componer cartera, que es el único modo donde se
aplican. Antes la página mostraba Merton con 0,35 saltos anuales aunque la
intensidad efectiva fuese cero.

**Rendimiento declarado del efectivo.** El mandato admite la tasa anual neta
que paga la cuenta sobre efectivo USD (0–20%). CASH crece a esa tasa de forma
determinista y sin riesgo de precio; 0% significa efectivo explícitamente no
remunerado, como pide la §3 del documento técnico. No se infiere de Treasury
3M ni de Fed funds: depende del contrato de cada cuenta.

**Registro diario sellado de riesgo.** La validación de la cartera a doce
meses agrupa por versión del motor y exige 20 ventanas sin solape: con una
versión nueva cada pocos días, esa muestra no puede completarse. El documento
técnico (§8) se formula sobre pronósticos a una sesión, que acumulan evidencia
en semanas. `scripts/risk_ledger.py` sella cada corte, antes de la apertura
siguiente y una sola vez, la varianza h_{t+1|t}, el VaR95 y el ES95 de cada
instrumento con GJR-GARCH-t (parámetros del mismo corte) y con la referencia
EWMA(0,94) sobre las 500 sesiones previas, además del modelo que usa el modo
híbrido. Cada sello conserva hashes del mercado y la calibración.

La puntuación usa la primera sesión posterior presente en un corte publicado
más tarde y se escribe en `data/risk-forecasts/scores/` sin tocar el sello. Un
resultado ausente queda sin puntuar. `dist/data/risk-calibration.json` resume
por **versión del modelo de riesgo** (1.0.0), independiente de la versión del
motor: QLIKE, tasa de excepciones VaR95 con Kupiec, agrupamiento de
excepciones con Christoffersen, profundidad de cola (pérdida realizada media
sobre ES sellado en días de excepción) y QLIKE pareado EWMA − GJR. Riesgo
muestra el resumen. Los contrastes agregados tratan los activos como
independientes, lo que no son; los mínimos de 20 sesiones y 500 activo-días
son reglas operativas. El registro no promueve parámetros ni decide
operaciones.

La versión del motor pasa a 0.15.0 para invalidar propuestas calculadas con la
correlación residual anterior.

### 0.16.0 — Ley de innovación coherente con el GJR aceptado

Los GJR aceptados se estiman por verosimilitud Student-t estandarizada y su
filtro de VaR95 usa cuantiles t, pero el Monte Carlo los simulaba con
innovaciones gaussianas que nunca se validaron. Ahora cada activo aceptado
transforma su shock gaussiano correlacionado al mismo cuantil de su t con ν
propio y varianza unitaria: Φ(z) = F_ν(x)·√((ν−2)/ν). La correlación sigue
siendo una cópula gaussiana, sin la dependencia de cola que imponía el factor
t radial retirado en 0.7.0. Los activos sin GJR aceptado conservan EWMA
gaussiano. La transformación usa la beta incompleta regularizada y una erfc
con error relativo menor que 1,2·10⁻⁷, tabuladas por ν. Coincide con scipy en
menos de 5·10⁻⁶ hasta z = 5.

Impacto medido sobre el corte del 26 de octubre, semilla 20261024. El CVaR95
a 12 meses de una cartera fija (TLT 20, SHV 25, CMCSA 15, HPQ 5, AMZN 20,
MU 5, CI 5) pasa de 13,95 % a 13,97 %; el percentil 1 de AMZN, de −57,0 % a
−58,4 %. A doce meses las colas diarias se diluyen al agregarse y el riesgo
de cola lo dominan la incertidumbre del ancla y los regímenes; el efecto será
mayor en horizontes cortos. La propuesta por defecto cambió de HPQ/MU/CI a
NFLX/GOOGL con CVaR 15,5 % frente a 14,6 %: es otra muestra de la
sensibilidad de la búsqueda, no una mejora demostrada. La marginal t por
activo se contrasta en el registro diario sellado (VaR95 y ES95 GJR-t frente
a EWMA gaussiano). Las coexcedencias conjuntas siguen sin validar.

### 0.17.0 — El retorno esperado ya no supone convergencia total al múltiplo sectorial

Diagnóstico sobre el corte del 26 de octubre. Las 142 acciones con BPA
utilizable compartían 34 combinaciones genéricas de supuestos por sector (por
ejemplo, las 24 tecnológicas: P/E de salida 22 y crecimiento 6%). El retorno
anual del modelo suponía que cada P/E alcanzaba esa referencia en tres años, y
la correlación entre el retorno del modelo y el componente de cambio de
múltiplo era 0,99. CMCSA (P/E 7 → 16) obtenía 31,9 de sus 40,3 puntos anuales
del re-rating; MU, HPQ y CI, 22, 19 y 14 puntos. 83 acciones caras recibían
contracción. Las propuestas elegían, en la práctica, la distancia a un múltiplo
sectorial genérico.

Los datos publicados no permiten estimar un múltiplo histórico propio por
empresa: la historia contable conserva acciones en circulación y márgenes de
unos 11 trimestres, no BPA. Se adopta el enfoque por bloques de las hipótesis
de mercado de largo plazo: retorno = dividendos + crecimiento del BPA +
reversión parcial y lenta del múltiplo. La brecha logarítmica entre P/E
observado y referencia se cierra con vida media de 10 años: φ = 1 − 0,5^(h/10),
≈19% a tres años. Es una convención declarada, no una estimación calibrada. La
convergencia total y la ausencia de reversión pasan a ser extremos de la
banda, es decir, incertidumbre y no expectativa. El valor justo de Valoración y
las alertas de prima del seguimiento conservan el múltiplo de referencia
completo. Un múltiplo editado por el usuario se respeta tal cual. La variante
robusta «sin expansión» parte del múltiplo efectivo. La propuesta y Valoración
muestran el desglose BPA + múltiplo + dividendos, que suma exactamente el
retorno del modelo.

Efecto en las anclas: mediana de 1,0% a 5,2%, percentil 90 de 11,8% a 8,1% y
máxima de 23,6% (CMCSA) a 11,9% (NVDA). La propuesta por defecto pasa a TLT 20,
SHY 15, SGOV 20, IEI 5, efectivo 5, AMZN 15, NFLX 15 y VZ 5, con media 4,1%,
mediana 3,6% y CVaR 14,0%. Los supuestos de crecimiento siguen siendo
genéricos por sector y dominan ahora el orden; requieren vintages de consenso
o de BPA para calibrarse.

### Hechos contables solo de informes periódicos

Cinco de las siete incidencias del corte del 26 de octubre (SCHW, ANET, MDT,
FDX y ED, con «BPA no comparable con beneficio/acciones») no eran fallos del
BPA. El beneficio neto anual procedía de **DEF 14A**: la tabla
pay-versus-performance de los proxy statements repite el beneficio neto
etiquetado en miles o millones sin escala (SCHW 8.852.000 en lugar de
8.852 M$; FDX 4.433 en lugar de 4.433 M$). Al presentarse después del 10-K,
la regla «última presentación por período» lo prefería. La selección de
hechos acepta ahora solo 10-K, 10-Q, 20-F, 40-F, sus versiones de transición
y sus enmiendas, que sí pueden reexpresar cifras. Con companyfacts actual,
las cinco empresas concilian beneficio neto ≈ BPA × acciones con ratios
entre 0,94 y 1,01. La comprobación de conciliación sigue activa. Las dos
incidencias restantes (SPGI, BKNG) son BPA de informes distintos alrededor de
un split y siguen bloqueadas a propósito.

### Splits frente a ajustes por escisión

Yahoo publica como «splits» los ajustes de precio de escisiones: FDX 1,241
(FedEx Freight), GE 1,253 (GE Vernova), HON 1,061, BDX 1,272, SPGI 1,057,
CMCSA 1,067, IBM 1,046, DELL 1,973, entre otros. Tratados como splits,
inflaban el historial de acciones anterior (dilución ficticia del 24% en FDX),
bloqueaban el BPA de SPGI por «informes distintos alrededor de un split» e
impedían el puente de BPA continuado. Un split debe cambiar las acciones en
circulación declaradas en la portada del 10-Q/10-K en su proporción, y el
cambio observado debe quedar más cerca del ratio declarado que de 1. Sin
observaciones a ambos lados (por ejemplo, los ETF), solo se acepta un ratio
p/q sencillo con q ≤ 10. El resto se conserva en `price_adjustments`, sin
alterar bases por acción. Los precios ajustados del proveedor siguen
incluyendo el valor distribuido.

Observación sin resolver: HON declara 633,7 M acciones al 31-mar-2026 y
316,9 M al 30-jun-2026, mientras el proveedor indica un ajuste de 0,9535. No
se reinterpreta como contrasplit sin un documento que lo acredite.
