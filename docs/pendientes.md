# Trading · lo que falta

Backlog actualizado el 27 de octubre de 2026 para el motor 0.19.0, corte de
precios examinado del 26-oct, 260 instrumentos (160 acciones, 100 ETF).
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
- **Falta:** vintages originales verificados y evidencia prospectiva. La
  reconstrucción desde companyfacts actual no certifica lo conocido entonces;
  el candidato y sus bandas no se promueven por generar un error histórico.
  También falta normalización de beneficios, cobertura de pérdidas y
  validación del crecimiento al horizonte de inversión, no solo anual.
- **Terminado cuando:** cada ancla de crecimiento indica su fuente y vintage,
  y existe un error de previsión medido fuera de muestra.

### 2. 94 de 100 ETF sin ancla económica: no se pueden comprar
- **Evidencia:** solo TLT, SHY, IEF, IEI, SGOV y SHV tienen perfil. Los ETF
  de índice (VTI, QQQ, sectoriales, internacionales) quedan en observación;
  SPY es solo comparador. 51 ETF tienen holdings fechadas.
- **Falta:** ancla por bloques para ETF de renta variable a partir de sus
  holdings: rendimiento por dividendo, recompras netas, crecimiento y cambio
  de múltiplo de los constituyentes, ponderados, con la misma reversión
  parcial que las acciones y cobertura mínima de composición.
- **Terminado cuando:** un ETF con ≥ 80 % del peso en constituyentes con ancla
  válida obtiene ancla y banda trazables (umbral operativo, a revisar); con
  menos cobertura sigue en observación.

### 3. Renta fija de crédito e inflación sin modelo
- **Evidencia:** AGG, BND, LQD, HYG, EMB, TIP e IGSB tienen historial de
  pagos, pero no perfil de retorno (TIR, duración, spread, pérdida esperada).
- **Falta:** perfil oficial fechado por emisor, un modelo de spread y
  default para crédito, y tasa real/breakeven para TIP. Hoy solo existe
  T10YIE; falta la serie real (DFII10).
- **Terminado cuando:** el ancla separa carry, efecto de tasas, spread y
  pérdida esperada, con su fuente y su fecha.

### 4. Validación prospectiva sin observaciones maduras
- **Evidencia al corte examinado:** registro diario de referencias
  estadísticas con 1 sesión sellada y 0 puntuadas. No replica el centro,
  EWMA ni los límites exactos del simulador: falta validar también esa
  distribución y el CVaR de cartera. Pronósticos a 12 meses: 2 sellados y
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
11. **Regímenes macro.** Probabilidades fijas a mano (base 0,55; recesión
    0,20; inflación 0,15; expansión 0,10). Las 14 series macro no informan
    nada. Falta condicionarlas al corte o declararlas sensibilidad pura en
    la interfaz.
12. **Convenciones sin calibrar.** La vida media de 10 años del re-rating,
    el prior del 6 % y la confianza subjetiva por empresa. Falta medir su
    error con vintages, o al menos mostrar la sensibilidad de la propuesta a
    cada una.
13. **Acciones con BPA negativo sin valoración.** INTC, GILD, APD, CRWD,
    TEAM y NET quedan excluidas. Falta una ruta por ventas, margen objetivo y
    dilución con su incertidumbre.

## P1 · Datos

14. **V y FCX sin BPA; BKNG sin base de split conciliada; WEC con informe posterior.**
    La recuperación desde el iXBRL original corre, pero no obtiene BPA.
    Hipótesis sin confirmar: BPA por clase de acción con dimensiones (Visa) o
    conceptos no estándar. BKNG queda bloqueado aunque falte beneficio neto;
    recuperar componentes reexpresados antes de rehabilitarlo. Requiere
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

20. **Estabilidad de la propuesta.** Solo se simulan 40 activos de 260 y la
    convergencia no está verificada. La propuesta cambia con semilla, versión
    y perturbaciones pequeñas (el sello del 26-oct y la propuesta actual
    difieren). Falta una métrica de estabilidad visible y desempate a favor
    de la menor rotación entre candidatas estadísticamente equivalentes.
21. **Comparación robusta** limitada a crecimiento en USD sin retiros, suelo
    ni meta. Falta extenderla a los demás mandatos.
22. **Topes prudenciales sin validar** (Treasury 60 %, renta variable 50 %,
    35 % por instrumento) y efectivo al 0 % por defecto. Con los anclajes
    actuales, los topes empujan ~35 % a acciones. Falta un análisis de
    sensibilidad de los topes, o que el usuario los confirme explícitamente.
23. **Operativa.** Faltan lotes enteros y precios ejecutables, conciliación
    con el broker, una política integrada de salida/reentrada por tesis
    invalidada y deshacer cambios de composición.

## P2 · Ingeniería y documentación

26. **Extractor Bloomberg** mencionado en la documentación pero inexistente
    en el repositorio. Requiere un equipo con licencia; sus datos no deben
    publicarse en Pages.
