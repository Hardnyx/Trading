# CUSIP y ticker: observaciones originales por fecha

## Medición del 31-oct-2026

Se verificaron **92 N-PORT originales**, con 34.709 observaciones explícitas
y 3.089 CUSIP distintos en los fondos de contraste. El cruce con SPY tiene
cobertura en **12/48 cierres**, entre el **96,09% y el 97,27% del peso** de SPY
en esos cortes. No se renormaliza el peso pendiente. Son pesos de cartera,
no porcentajes del número de empresas ni pruebas predictivas independientes.

Otros 22 cierres carecen de SPY admisible por antigüedad y 14 tienen SPY
admisible pero no un cruce explícito admisible dentro de los límites de fecha.
Entre las causas están el desfase de calendarios trimestrales, la publicación
diferida y cortes anteriores al día de disponibilidad conservador. No se
amplía la antigüedad ni se adelanta la publicación para completar esos huecos.
El motor completo sigue apto en **0/48 cierres**.

## Contrato de fuentes

El módulo `scripts/historical_identifiers.py` recupera N-PORT originales de
IVV, ITOT, IYY, ISCB e ILCB y cruza sus identificadores explícitos con los de SPY.
La selección de fondos utiliza series SEC fijas; la identidad del registrante
y de la serie se vuelve a comprobar en cada XML. Esa selección sirve para
descubrir documentos y no prueba pertenencia histórica al S&P 500.

El [reporte por cierre](../data/historical/identifier-observations-v1/coverage.md)
muestra el peso con coincidencia y el peso pendiente. El
[resumen JSON](../data/historical/identifier-observations-v1/coverage.json)
conserva los hashes y las exclusiones. Las posiciones completas, la evidencia
por coincidencia y los símbolos originales están en `observations.json.gz`
en el mismo directorio. Los originales se conservan en
`data/historical/identifier-sources-v1/`, con manifiesto y archivos comprimidos.

## Qué acepta

- CUSIP idéntico y con dígito verificador válido en ambos instrumentos.
- Ticker explícito en el bloque de identificadores del instrumento, conservado
  exactamente como aparece. No se convierten barras, puntos o clases de acciones.
- Posición de contraste clasificada como acción, larga y denominada en USD.
- Documento publicado antes del cierre: día posterior al mayor entre la fecha
  de presentación y sesenta días desde su composición, igual que en SPY.
- Composición de contraste no mayor de 120 días. Los holdings de SPY deben
  superar por separado sus controles de disponibilidad y antigüedad.

El registro conserva fecha de cartera, disponibilidad, accession, URL y hash
de cada XML. La fecha de descarga es la real. No se finge una descarga anterior.
Las enmiendas futuras quedan fuera de los cortes anteriores. Si varias fuentes
de la misma fecha discrepan en ticker o identidad LEI, la coincidencia queda
bloqueada. No se elige la mayoría ni se deduce un ticker a partir del nombre.

## Qué sigue pendiente

Un símbolo publicado por un fondo es una **observación de identidad**. No
certifica continuidad del símbolo hasta el cierre, correspondencia con el
identificador de un proveedor de precios, eventos corporativos ni una ancla
fundamental válida. El campo `price_instrument_binding` permanece nulo.
Tampoco reconstruye el universo histórico completo ni empresas deslistadas.

La ausencia de tickers en un XML no se rellena usando el catálogo actual.
No se renormalizan pesos desconocidos. Un archivo con muchos instrumentos y
ningún ticker explícito es evidencia de una limitación de esa fuente, no un
mapa completo de identificadores. Por eso se conservan también esos originales.

La [matriz integral](../data/historical/replay-plan-v1/coverage.md) incorpora
la cobertura observada sin habilitar el componente de identificadores ni
el motor. Todas las predicciones y órdenes del replay siguen pendientes.

## Ejecución y recuperación

```sh
python -m unittest tests.test_historical_identifiers tests.test_historical_replay_plan
python scripts/historical_identifiers.py --collect
python scripts/historical_identifiers.py
python scripts/historical_replay_plan.py
```

La colección utiliza `SEC_USER_AGENT`, el limitador global y los reintentos
del colector existente. Conserva el primer original de cada accession y
checkpoints después de cada archivo. Un fallo de red no elimina los originales
recuperados ni convierte la colección parcial en completa. La auditoría
posterior vuelve a comprobar los bytes, la respuesta de descubrimiento SEC,
el registrante, la serie, las fechas y las observaciones derivadas.

El workflow `Historical identifier evidence (research)` ejecuta los controles,
reanuda la colección y publica únicamente evidencia pública mediante un commit
normal a `main`. Comparte la cola de las fuentes históricas para evitar dos
publicaciones simultáneas de la matriz. No modifica los datos ni parámetros
del motor de producción.

Fuentes de descubrimiento: [EDGAR por serie IVV](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000004310&type=NPORT-P&owner=exclude&count=100&output=atom)
y la misma consulta para ITOT `S000004317`, IYY `S000004330`, ISCB
`S000004433` e ILCB `S000004367`. El manifiesto conserva las consultas exactas, limitadas a la
última fecha de decisión. Cada coincidencia enlaza además su documento original.
