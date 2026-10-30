# Corrección causal del calendario de cuentas TTM

Protocolo `reconstructed-ttm-account-v2`, fijado antes de ejecutar los
resultados corregidos. Conserva las reglas, exposición, posiciones,
referencias, costes y diagnósticos del
[protocolo v1](protocolo-cuenta-historica-0.35.md), publicado en `fb2b414`.
No modifica producción ni elige parámetros a partir de los retornos.

## Defecto encontrado en v1

El paquete del estudio TTM incluía solo orígenes con al menos 21 sesiones
posteriores para medir ranking. Reutilizar esos orígenes en una cuenta
sucesiva omitía la revisión del 30-sep-2026, cuya señal sí podía calcularse.
Las cuentas v1 conservaron su última orden del 31-ago hasta el fin de la
muestra. Sus NAV y costes concilian, pero no representan una revisión cada
mes hasta septiembre. No se presentan como el recorrido mensual completo.

La evidencia v1 se conserva en el commit `7584ed5` y en
`docs/auditorias/ttm-account-summary-2026-10-29.json`. La corrección se
registra aunque mejore o empeore el rendimiento; no se escoge entre ambas.

## Cambio único de la regla causal

Los orígenes se derivan de los últimos cierres SPY observados de **todos
los meses anteriores al mes del corte final**, tras 252 sesiones de
calentamiento. El mes del corte puede estar incompleto y no se usa como
cierre mensual. No se condiciona un origen a disponer de su retorno futuro.
Se conservan las dos sesiones de retraso para ejecución. Si ese cierre aún
no está observado, la orden queda pendiente, sin mover su fecha.

Los TTM de cada origen se reconstruyen de nuevo con `eps_at` del estudio
anterior, utilizando las mismas versiones SEC archivadas. No se descargan
datos nuevos ni se recalibran supuestos. Se conservan la selección por
presentación anterior, las salvaguardas de bases por acción y los sesgos
de universo/catálogo y operaciones corporativas declarados en v1.

El adaptador exige que las fechas entregadas coincidan con ese calendario,
incluso si una fecha carece de suficientes señales. En tal caso se mantiene
la cuenta por falta de información; no se borra su revisión. Se guardan
también las exclusiones contables por origen y los hashes del preparador
Python y de sus dependencias.

Con el mercado congelado al 28-oct se esperan 48 revisiones: 31-oct-2022 a
30-sep-2026. Esta cifra se deduce del calendario, antes de leer sus retornos.
El archivo de resumen corregido y su figura se identifican como v2. El
criterio de superioridad permanece sin acreditar y no hay promoción automática.
