# Estado de validación de Trading

**Fecha del diagnóstico:** 26 de octubre de 2026, con cortes de precios publicados por el repositorio.
**Clasificación:** investigación activa; no es asesoramiento de inversión ni certificación predictiva.

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

**Sigue pendiente:** ampliar fuentes de pagos declarados a todas las acciones y ETF, fiscalidad por instrumento y jurisdicción, conciliación con el broker, curvas completas y evidencia prospectiva suficiente sobre retornos, colas y noticias. La publicación de un calendario no resuelve esos puntos.
