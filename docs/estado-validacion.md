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
