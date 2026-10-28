# Trading · lo que falta

Backlog actualizado el 28 de octubre de 2026 para el motor 0.31.0, corte de
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
- **Avance en 0.29.0:** los gastos netos que publica TickerInside junto a
  los holdings se descuentan del ancla compuesta, fechados con esa misma
  observación. EFA y EEM obtienen un ancla por rendimiento de beneficios
  (P/E fechado del emisor + inflación implícita, contraído al prior, neto
  de gastos).
- **Avance en 0.31.0:** ACWX, IJH e IJR toman el mismo ancla, con URLs del
  catálogo oficial de iShares.
- **Falta:** los fondos país (EWJ, EWZ, INDA, MCHI…) siguen en observación
  hasta tener un límite por riesgo país: el bloque de beneficios daría
  anclas altas a mercados baratos por riesgo político, de gobierno o de
  divisa. IWM queda fuera porque el P/E del emisor excluye a las empresas con
  pérdidas, cerca del 40% del Russell 2000. VEA, VWO y VXUS no son iShares. IWM, XLRE, XBI, KRE, IBB,
  XLB, RSP y SPLV quedan bajo el 70%. Los gastos provienen de un
  agregador, no del folleto. El bloque de beneficios no distingue
  crecimiento ni ciclo de márgenes por región. La banda supone errores
  perfectamente correlacionados entre constituyentes; falta medir su
  diversificación. El umbral de 70% es operativo.
- **Terminado cuando:** todo ETF de renta variable comprable tiene ancla con
  fuente y fecha, neta de gastos, o queda en observación con el motivo.

### 3. Renta fija de alto rendimiento, emergente e inflación sin modelo
- **Avance en 0.23.0:** AGG, LQD e IGSB tienen perfil oficial fechado y un
  ancla: TIR − gastos − pérdida esperada de crédito (convención: 0,25%/año
  corporativo IG y 0,08% AGG). Un choque de diferencial por escenario, con
  beta por fondo, se suma al de tasas.
- **Avance en 0.29.0:** HYG (pérdida esperada 2%/año, beta de diferencial
  3) y EMB (0,75%, beta 1,5) tienen perfil del emisor y ancla. TIP usa su
  rendimiento real publicado más la inflación implícita a 10 años; sus
  escenarios mueven la tasa real (tasa − inflación) y la inflación realizada
  se devenga al principal.
- **Falta:** JNK, BKLN, BND, VCIT y VCSH no son iShares y no tienen perfil.
  Las convenciones de pérdida, beta, ampliación en recesión y cambio de
  inflación no están calibradas con historia de diferenciales, impagos e
  inflación. Los saltos de tasas de HYG y TIP usan la misma regla que los
  Treasuries.
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
    dispersión y colas, pero no mueven el retorno esperado. Desde 0.29.0 la
    probabilidad de recesión sale de la curva al corte (probit de la Fed de
    Nueva York sobre 10A − 3M; 13% al 27-oct). Falta: las de inflación y
    expansión siguen proporcionales a una convención; las magnitudes siguen
    fijas a mano. También falta contrastar la dispersión generada con la
    historia.
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

20. **Estabilidad de la propuesta.** Desde 0.28.0, cada propuesta corre tres
    búsquedas independientes y concilia sus ganadoras en escenarios comunes,
    con la estabilidad visible en la propuesta. Al corte del 27-oct, el
    objetivo es plano: carteras que comparten 40–75% de los pesos quedan a
    USD 50–700 entre sí sobre USD 100.000. Falta: (a) variar también la
    muestra de 40 activos, que hoy es la misma en las tres búsquedas; (b)
    decidir si conviene proponer una mezcla de las ganadoras equivalentes
    (cartera remuestreada), lo que choca con el máximo de posiciones; (c)
    contrastar la estabilidad entre cortes consecutivos; (d) escalar el
    presupuesto de búsqueda con el universo elegible. En 0.31.0, añadir tres
    índices a la muestra hizo que las búsquedas no reencontraran una cartera
    USD 161 mejor (z 1,88), sin que ninguno de los índices fuera elegido.
    Doblar el presupuesto a 600 candidatas por búsqueda recuperó esa
    familia de carteras (+USD 217 en escenarios comunes), pero no mejoró el
    corte publicado (−USD 24, ruido) y cuesta 25–50% más de tiempo: no se
    cambió el valor por defecto.
21. **Comparación robusta** limitada a crecimiento en USD sin retiros, suelo
    ni meta. Falta extenderla a los demás mandatos.
22. **Topes prudenciales sin validar** (Treasury 60 %, renta variable 50 %,
    35 % por instrumento) y efectivo al 0 % por defecto. Con los anclajes
    del 27-oct, la reproducción con seis posiciones alcanza 50% en acciones.
    Falta un análisis de sensibilidad de los topes, o que el usuario los
    confirme explícitamente. Desde 0.30.0, alto rendimiento y emergente
    (HYG, JNK, BKLN, EMB) tienen un tope combinado de 20%, editable; tampoco
    está validado. Falta un límite por riesgo país.
23. **Operativa.** Faltan lotes enteros y precios ejecutables, conciliación
    con el broker, una política integrada de salida/reentrada por tesis
    invalidada y deshacer cambios de composición.

## P2 · Ingeniería y documentación

26. **Extractor Bloomberg** mencionado en la documentación pero inexistente
    en el repositorio. Requiere un equipo con licencia; sus datos no deben
    publicarse en Pages.
