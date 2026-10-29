# Contraste TTM e IC · protocolo fijado el 29-oct-2026

Este contraste precede a la lectura de sus resultados. No ajusta ni promueve
el IC de 0,05, los crecimientos del catálogo o una nueva composición.

1. Congelar `dist/data/market.json` con precios del 28-oct, hash registrado.
   Universo actual de 160 acciones, sin reconstruir miembros históricos.
2. Obtener una respuesta companyfacts por empresa, con el descargador del
   proyecto y su pausa SEC. Conservar URL, fecha de observación, hash de la
   respuesta y todas las versiones de BPA necesarias para reproducir el
   cálculo. Son respuestas actuales, no vintages originales certificados.
3. En cada último cierre disponible del mes, admitir solo informes con fecha
   **anterior** al origen. Sin hora verificada se excluye todo el mismo día.
   Reutilizar el extractor TTM de producción: anual + YTD − YTD comparable,
   o anual directo. Rechazar fallback FY, conflictos en los componentes
   elegidos, BPA no positivo, antigüedad mayor de 550 días y bases por acción
   mezcladas alrededor de splits según la salvaguarda actual.
4. Reexpresar BPA a las unidades por acción del precio ajustado por splits
   del proveedor actual, conservando valor y componentes originales. Los
   dividendos proceden del índice histórico por ex-fecha, limitado a los
   365 días terminados en el origen, con cobertura completa. No se usa el
   dividendo de hoy para rellenar un origen antiguo.
   Excluir orígenes anteriores a ajustes de precio posteriores que el
   repositorio clasifica como operaciones distintas de splits: sin conciliar
   la operación no se mezclan ese precio reexpresado y el BPA anterior.
5. Reutilizar `resolveAssumptions`, `valuation` y `marketExposure` actuales
   sin cambiar producción. El crecimiento, múltiplo de referencia y horizonte
   son convenciones del catálogo actual. El score transversal se centra,
   estandariza y limita a ±3 como en el código. No reconstruye las confianzas
   históricas ni la neutralización por holdings del SPY.
6. Medir por origen con al menos 30 acciones y horizontes 21/63/252 sesiones:
   IC de rangos frente al retorno logarítmico residual de mercado, referencia
   BPA/precio sobre exactamente las mismas observaciones y diferencia pareada
   de ambos IC. Medir también Pearson entre score y residuo dividido por su
   volatilidad estimada al origen. El IC de rangos no es el IC de Pearson de
   Grinold–Kahn, y este diagnóstico tampoco calibra el coeficiente completo.
7. Intervalos aproximados con bloques móviles de 1/3/12 meses, 2.000
   remuestreos y semilla fija 20261029. Sin al menos dos bloques completos o
   con huecos entre meses, no publicar intervalo. Mostrar el subconjunto de
   orígenes sin solapamiento; las acciones correlacionadas no cuentan como
   observaciones temporales independientes.

No hay búsqueda de hiperparámetros ni una muestra de holdout históricamente
intacta: el universo y las convenciones se eligieron después de muchos de
esos retornos. El ejercicio supera el proxy anual anterior en reconstrucción
contable y fidelidad de fórmula, pero no acredita una estrategia ni un IC
prospectivo. Un resultado débil o una referencia simple superior no se
disimula cambiando ventanas, semillas, universo o el umbral de cobertura.

La [documentación SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
explica que companyfacts agrega conceptos de taxonomías estándar de ámbito
entidad y se actualiza con nuevas publicaciones. No garantiza conceptos
personalizados, clases de acciones ni una respuesta idéntica a la que existía
en un corte antiguo.

```sh
python scripts/ttm_signal_research.py collect
node scripts/ttm_signal_replay.mjs
python scripts/ttm_signal_research.py summarize
```

Los tres JSON, el mercado congelado y este protocolo se conservan como
artefactos de investigación. La aplicación y su núcleo 1.0.0 no cambian.
