# Estado de validación de Trading

**Fecha del diagnóstico:** 25 de octubre de 2026, con cortes de precios publicados por el repositorio.
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
