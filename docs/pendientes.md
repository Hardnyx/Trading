# Trading · lo que falta

Backlog actualizado el 27 de octubre de 2026 para el motor 0.27.0, corte de
precios examinado del 27-oct, 260 instrumentos (160 acciones, 100 ETF).
Consultar las pruebas y los cierres en `docs/estado-validacion.md`. Cero
incidencias publicadas o pruebas de software aprobadas no acreditan datos
conciliados ni validez predictiva: BKNG volvió a mezclar bases tras su split
en 0.17.0 sin generar una incidencia. La protección se restaura en 0.18.0.
Este archivo lista **solo lo que falta**. Para el funcionamiento, consultar
`README.md` y `docs/`.

## Cómo usar y mantener este archivo

- Antes de trabajar, elige por prioridad (P0 → P2) y comprueba que el
  bloqueo indicado no siga vigente.
- Cada punto tiene evidencia y criterio de terminado. No lo marques como
  cerrado sin cumplir ese criterio con datos del corte vigente.
- Al cerrarlo, bórralo de aquí y registra el resultado en
  `docs/estado-validacion.md`. Si descubres un pendiente nuevo, añádelo con
  su evidencia.
- Regla del proyecto: nada se promueve a producción por complejidad. Hace
  falta evidencia prospectiva con información conocida al corte.

## P0 · Bloquean decisiones fiables

### 1. Crecimiento de BPA sin calibrar (el que ordena las acciones)
- **Evidencia:** 160 acciones comparten 33 combinaciones de supuestos de
  crecimiento y múltiplo (36 con 5 %/19×, 30 con 6 %/22×…). Tras la 0.17.0,
  el crecimiento es el principal motor de las anclas. No hay consenso: 0
  activos con `analyst_estimates`; FMP figura como `private_required`.
- **Bloqueo del consenso privado:** licencia y entorno autorizado. La
  historia pública SEC puede prepararse sin esa licencia; no asumir nuevas
  suscripciones ni publicar datos privados.
- **Avance en 0.19.0:** se conservan hasta doce años de BPA anual y sus
  versiones presentadas, sin consultas SEC adicionales. Hay un candidato
  contraído hacia un prior y un contraste secuencial frente a referencias,
  con bandas calculadas solo con errores conocidos en cada origen. Se
  identifican la convención del catálogo, las ediciones y el consenso.
- **Avance en 0.25.0:** el retorno por bloques ya no se usa como esperanza
  directa. Es una señal: equilibrio CAPM más alfa = IC × volatilidad
  residual × puntuación, neutral frente a SPY. Con IC 0,05 declarado, la
  dispersión entre acciones baja de 2,6 a 1,5 pp. El IC es una convención:
  medirlo con los sellos a 12 meses lo cerraría.
- **Falta:** vintages originales verificados y evidencia prospectiva. La
  reconstrucción desde companyfacts actual no certifica lo conocido entonces;
  el candidato y sus bandas no se promueven por generar un error histórico.
  También falta normalización de beneficios, cobertura de pérdidas y
  validación del crecimiento al horizonte de inversión, no solo anual.
- **Terminado cuando:** cada ancla de crecimiento indica su fuente y vintage,
  y existe un error de previsión medido fuera de muestra.

### 2. ETF sin ancla: internacionales, sectoriales con poca cobertura y gastos
- **Avance en 0.22.0:** 15 ETF de renta variable de EE. UU. con holdings
  fechadas de 120 días o menos y al menos 70% del peso en constituyentes con
  ancla obtienen un ancla compuesta (SPY, QQQ, DIA, XLK, VUG, QUAL, VIG,
  DGRO, SCHD…). SPY deja de ser solo comparador.
- **Falta:** internacionales y emergentes (VEA, VWO, EFA, EEM, países) tienen
  0% de cobertura: sus constituyentes no están en el universo; requieren un
  ancla por bloques a nivel de índice (rendimiento, crecimiento, valoración,
  divisa). IWM, XLRE, XBI, KRE, IBB, XLB, RSP y SPLV quedan bajo el 70%.
  Faltan ratios de gastos fechados, que hoy no se descuentan. La banda supone
  errores perfectamente correlacionados entre constituyentes; falta medir su
  diversificación. El umbral de 70% es operativo.
- **Terminado cuando:** todo ETF de renta variable comprable tiene ancla con
  fuente y fecha, neta de gastos, o queda en observación con el motivo.

### 3. Renta fija de alto rendimiento, emergente e inflación sin modelo
- **Avance en 0.23.0:** AGG, LQD e IGSB tienen perfil oficial fechado y un
  ancla: TIR − gastos − pérdida esperada de crédito (convención: 0,25%/año
  corporativo IG y 0,08% AGG). Un choque de diferencial por escenario, con
  beta por fondo, se suma al de tasas.
- **Falta:** HYG (pérdida por impago y diferencial de alto rendimiento), EMB
  (riesgo soberano emergente) y TIP (tasa real; falta descargar DFII10).
  BND no es iShares y no tiene perfil. Las convenciones de pérdida, beta y
  ampliación en recesión no están calibradas con historia de diferenciales.
- **Terminado cuando:** cada fondo de renta fija comprable separa carry,
  efecto de tasas, diferencial y pérdida esperada con fuente y fecha, y las
  convenciones se contrastan con historia de diferenciales e impagos.

### 4. Validación prospectiva sin observaciones maduras
- **Evidencia al corte examinado:** registro diario de referencias
  estadísticas con 2 sesiones selladas y 1 puntuada (260 activo-días).
  No replica el centro,
  EWMA ni los límites exactos del simulador: falta validar también esa
  distribución y el CVaR de cartera. Pronósticos a 12 meses: 3 sellados y
  0 vencidos. Eventos verificados: 0.
- **Falta (mientras se acumula):** gráfico de cobertura y QLIKE acumulados
  en Riesgo, alertas cuando Kupiec o Christoffersen rechacen, y una regla
  escrita que diga qué hacer al rechazar (volver a EWMA, recalibrar…).
  Puntuación por horizonte semanal y mensual, no solo a una sesión.
- **Terminado cuando:** el estado pasa a `evaluable` (≥ 20 sesiones y ≥ 500
  activo-días) y existe una decisión documentada sobre GJR frente a EWMA.

## P1 · Modelo frente al documento técnico (`docs/modelo-estocastico-eventos.md`)

5. **GJR sobre residuos factoriales (§4, Fase 1).** En producción se estima
   sobre retornos totales; el GJR residual solo existe en investigación
   (`multifactor_research.py`). 19 de 260 activos aceptados; 66 ajustes con ν
   en el borde (4,0) y 21 con persistencia ≥ 0,99. Falta promover el residual
   con la misma regla walk-forward y reestimar los ajustes en el borde.
6. **Modelo factorial dinámico (§7, Fase 3).** En el navegador solo están SPY
   y el proxy sectorial. Faltan factores de tasas, crédito y USD en B_t;
   volatilidades por factor Σ_f; DCC regularizado y comparado con la matriz
   simple.
7. **Dependencia de cola conjunta.** La simulación usa cópula gaussiana. La
   t bivariante y las coexcedencias solo están en investigación
   (`joint_tail_research.py`). Falta validarlas fuera de muestra e
   integrarlas sin doble conteo.
8. **Saltos condicionales p_{i,t} (§6, Fase 4).** No implementados; solo
   queda el Merton legado como comparador. Falta un procedimiento de
   identificación y un diagnóstico de doble conteo frente a GJR-t.
9. **Eventos y GARCH-X (§5, Fase 2).** `data/events/verified.json` está
   vacío y no hay consenso macro previo al dato. Bloqueado por datos. Falta
   una fuente de consenso con timestamp y la prueba incremental en holdout.
10. **Oro.** Usa el supuesto genérico de ETF y un ajuste −0,5 × cambio de
    tasas. Falta un modelo con tasas reales (DFII10) y dólar (DTWEXBGS); hoy
    no se descarga ninguna de las dos series.
11. **Regímenes macro.** Desde 0.23.0 se aplican centrados: añaden
    dispersión y colas, pero no mueven el retorno esperado. Sus
    probabilidades y magnitudes siguen fijas a mano (base 0,55; recesión
    0,20; inflación 0,15; expansión 0,10) y las 14 series macro no las
    informan. Falta condicionarlas al corte, o declararlas sensibilidad pura
    en la interfaz, y contrastar la dispersión que generan con la historia.
12. **Convenciones sin calibrar.** La vida media de 10 años del re-rating,
    el prior del 6 % y la confianza subjetiva por empresa. Falta medir su
    error con vintages, o al menos mostrar la sensibilidad de la propuesta a
    cada una.
13. **Acciones con BPA negativo sin valoración.** INTC, GILD, APD, CRWD,
    TEAM y NET quedan excluidas. Falta una ruta por ventas, margen objetivo y
    dilución con su incertidumbre.

## P1 · Datos

14. **V y FCX sin BPA; BKNG y CRWD sin base de split conciliada; WEC con informe posterior.**
    La recuperación desde el iXBRL original corre, pero no obtiene BPA.
    Hipótesis sin confirmar: BPA por clase de acción con dimensiones (Visa) o
    conceptos no estándar. BKNG (25:1) y CRWD (4:1) quedan bloqueadas aunque
    falte beneficio neto; recuperar componentes reexpresados antes de
    rehabilitarlas. Requiere
    acceso a la SEC con el `SEC_USER_AGENT` del proyecto.
15. **HON:** acciones declaradas 633,7 M (31-mar-2026) → 316,9 M
    (30-jun-2026), frente a un ajuste del proveedor de 0,9535. Falta un
    documento que lo explique antes de tratarlo como contrasplit.
16. **Calendario bursátil.** Sellos y vencimientos usan una regla de días
    laborables que no certifica festivos de NYSE. Falta un calendario oficial
    fechado.
17. **Precios de fuente única.** Yahoo es un endpoint no oficial y no hay
    respaldo. Falta una segunda fuente y su conciliación.
18. **Holdings:** 49 de 100 ETF sin composición. Falta cobertura oficial del
    emisor y auditoría de clasificación sectorial.
19. **Flujos y fiscalidad:** pagos declarados solo para 12 ETF iShares; sin
    fiscalidad por instrumento ni jurisdicción. La retención del 0 % es un
    supuesto pendiente, no una exención.

## P2 · Optimización y operativa

20. **Estabilidad de la propuesta.** Se simulan 20–80 activos de 260, con 40
    como valor inicial, y la convergencia no está verificada. Desde 0.27.0,
    tras revisar el efectivo, se prueban intercambios de 5 puntos entre
    posiciones y sustituciones completas por cualquier instrumento simulado.
    Solo se acepta una mejora pareada significativa (z ≥ 1,645) en los
    escenarios de verificación: entre candidatas equivalentes se conserva la
    cartera con menos operaciones. Esto cubre el contraejemplo CI → NFLX de la
    revisión de 0.24.0, pero sigue siendo local y mide solo error de Monte
    Carlo. La propuesta aún cambia con la semilla, el corte y la muestra de
    40 (dos cortes seguidos dieron carteras distintas). Falta una métrica de
    estabilidad visible: proponer con varias semillas y muestras y mostrar
    cuánto coinciden los pesos.
21. **Comparación robusta** limitada a crecimiento en USD sin retiros, suelo
    ni meta. Falta extenderla a los demás mandatos.
22. **Topes prudenciales sin validar** (Treasury 60 %, renta variable 50 %,
    35 % por instrumento) y efectivo al 0 % por defecto. Con los anclajes
    del 27-oct, la reproducción con seis posiciones alcanza 50% en acciones.
    Falta un análisis de sensibilidad de los topes, o que el usuario los
    confirme explícitamente.
23. **Operativa.** Faltan lotes enteros y precios ejecutables, conciliación
    con el broker, una política integrada de salida/reentrada por tesis
    invalidada y deshacer cambios de composición.

## P2 · Ingeniería y documentación

26. **Extractor Bloomberg** mencionado en la documentación pero inexistente
    en el repositorio. Requiere un equipo con licencia; sus datos no deben
    publicarse en Pages.
