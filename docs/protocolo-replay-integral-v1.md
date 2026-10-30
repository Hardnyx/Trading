# Replay integral: protocolo de desarrollo v1

Registrado el 30-oct-2026. La especificación ejecutable de calendario y
criterios está en [protocolo-replay-integral-v1.json](protocolo-replay-integral-v1.json).
El preflight registra su hash junto con el manifiesto de fuentes y los archivos
del motor. Cambiar el protocolo requiere otra versión y explicar el cambio.
Esto congela el plan de evaluación; no acredita que ya exista el evaluador.

## Muestra y causalidad

Se conservan los 48 cierres, de octubre de 2022 a septiembre de 2026, del
mercado congelado `8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5`.
Los resultados preliminares de este periodo ya se inspeccionaron. Son
desarrollo retrospectivo y no un holdout independiente. No hay una reserva
histórica no utilizada certificada. Antes de una prueba confirmatoria habrá
que registrar una nueva muestra independiente sin inspeccionar sus resultados.

Macro: versión oficial hasta el día anterior. Documentos: originales y
publicación previa, conservando enmiendas y sus fechas. Precios: cierre
conocido al decidir después del cierre; operaciones al cierre de la siguiente
sesión real observada. No se usa el mismo cierre para decidir y ejecutar.
Los precios y BPA deben compartir una base de acciones causal; los ajustes
actuales por eventos posteriores no sirven como prueba de esa condición.

El kernel y el catálogo congelados hoy identifican una política retrospectiva.
Eso no demuestra que sus parámetros estuvieran disponibles en cada fecha.
El entrenamiento, selección de modelos y calibración necesitan procedencia
por corte o deben declararse explícitamente retrospectivos. Una reproducción
del modelo actual y una prueba causal confirmatoria son experimentos distintos.

## Contrastes y referencias fijados antes del replay completo

| Pregunta | Medición principal | Referencia |
|---|---|---|
| Predicción de retorno | Reducción del error cuadrático del retorno total aritmético a 21, 63 y 252 sesiones | Media diaria histórica expansiva capitalizada al horizonte, con mínimo 252 intervalos diarios disponibles al corte |
| Ranking | Diferencia del IC de Spearman a los tres horizontes, sobre exactamente los mismos instrumentos | BPA TTM presentado / precio sobre la misma base de acciones |
| Valor económico | Diferencia anualizada del retorno logarítmico mensual de cuentas netas | SPY y efectivo con beta fijada con información previa, misma ejecución y remuneración realizada del efectivo |

La familia principal contiene siete contrastes. Se usa Holm al 5%, con
dirección de ventaja positiva, y se publican todos los resultados. No se
elige después el horizonte o indicador más favorable. Los resultados de
desarrollo siguen siendo descriptivos aunque un contraste resulte favorable.

La incertidumbre se calcula mediante bloques circulares de meses emparejados,
con la sección transversal completa en cada bloque. Se fijan 10.000 réplicas,
semilla 20261030 y bloques de 12 y 24 meses. Se requieren al menos cuatro
bloques de datos para cada longitud; si faltan, el resultado es muestra
insuficiente. Con solo 48 cierres, la sensibilidad de 24 meses no alcanza
ese mínimo. No se certificará significancia robusta omitiendo esa limitación.
Los solapamientos de horizontes, activos y trayectorias Monte Carlo no
aumentan artificialmente el número de observaciones independientes.

Riesgo: CRPS, Brier de pérdidas, excedencias p05/p95, varianza prevista frente
a realizada y pérdidas extremas con sus conteos e intervalos. Un IC positivo
no acredita calibración de riesgo. Pocas pérdidas severas tampoco permiten
certificar las colas.

Referencias secundarias: SPY, 50% SPY/50% SHY, pesos iguales en el mismo
universo causal y versiones del motor sin alfa o con covarianza incondicional.
Se reportan beta, duración y exposición crediticia antes de atribuir una
ventaja a capacidad predictiva.

## Costes, datos ausentes y resultados

Escenario base: spread 5 pb y deslizamiento 2 pb, sin comisión ni impuesto
personal; sensibilidad con spread y deslizamiento triples. Son supuestos
explícitos de investigación. Se contabilizan dividendos y eventos sobre
acciones coherentes, evitando sumar dividendos otra vez a precios de retorno
total. La tasa prevista del efectivo no se convierte en rendimiento realizado.

Cada ejecución deberá sellar datos, protocolo, parámetros, calibración,
semillas, presupuesto de búsqueda y fuentes del motor antes de puntuar.
Se reutilizarán `referenceRequest` y `composeMultiStart` de producción;
sus adaptadores históricos aún están pendientes. No se modificará el kernel
para mejorar este periodo sin abrir otra versión de investigación.

Los cortes bloqueados se conservan en la matriz. No se sustituyen por efectivo
ni se omiten de una supuesta cuenta completa. Una submuestra elegible debe
mostrar sus exclusiones, universo y referencias sobre las mismas fechas.
Las observaciones sin madurez o resultado verificable siguen sin puntuación.

La conclusión seguirá siendo no establecida si los intervalos permiten
ventaja y desventaja, falta potencia para el riesgo extremo, o no existe
confirmación fuera de muestra y prospectiva. Aprobar pruebas de software
no cambia esa conclusión.
