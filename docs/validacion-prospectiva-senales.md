# Registro prospectivo de señales completas

Protocolo `monthly-complete-stock-signal-v1`, incorporado el 29-oct-2026.
Evalúa la señal que se emitió realmente, con sus datos y código originales.
No modifica el motor 0.35.0, el núcleo de precios 1.0.0 ni los parámetros
de inversión. No convierte la estabilidad de los pesos en acierto predictivo.

## Emisión y conservación

Se conserva la **primera captura elegible procesada de cada mes de Nueva
York**, sin sustituirla por una revisión posterior ni por una cartera más
favorable. La captura debe ser anterior a la emisión. Se rechazan observaciones
posteriores, emisiones anteriores al cierre y datos de precios demasiado
antiguos para la ventana conservadora de dos sesiones. La regla de días
laborables puede descartar alguna emisión durante festivos; no certifica
el calendario oficial de la bolsa.

El contexto es el canónico, sin cuenta personal ni overrides del usuario.
Se registra todo el universo de acciones, incluidas las que no entran en
las 40 posiciones simuladas y las que carecen de señal utilizable. Por acción
se conservan:

- Señal por bloques, score, confianza efectiva y base de investigación.
- BPA efectivo, componentes contables y supuestos del catálogo y efectivos.
- Beta original y ajustada, volatilidad residual, IC aplicado, alfa,
  equilibrio CAPM y neutralización frente al benchmark.
- Ancla final acotada de producción y ancla del mismo modelo con IC cero.
- Fuente, evidencia de crecimiento, calidad y motivos de exclusión.

Se sella también el ancla económica de SPY, con fuente y banda declarada.
Un proxy genérico destinado solo a comparar no se acepta como ancla económica.

El mercado completo y la calibración de volatilidad usados se archivan
comprimidos, con hashes. Los hashes del grafo de módulos importados, motor,
núcleo y referencia identifican la cohorte. Cambiar el código crea una cohorte
distinta; no se agregan sus resultados automáticamente. Las anteriores siguen
esperando sus propios vencimientos. Una compatibilidad entre versiones tendría
que justificarse por separado.

## Inicio real y primera publicación

El retorno comienza en el cierre de la **segunda sesión observada de SPY
posterior al corte de precios**. Desde ese cierre se cuentan 21, 63 o 252
sesiones. El origen y el vencimiento no se desplazan para encontrar precios
de una acción que falten.

Antes de asignar una puntuación se verifica el commit que añadió por primera
vez el fichero y que su contenido coincide con el sello actual. El cierre
inicial debe ser posterior tanto al día de emisión como al día de esa primera
publicación. Un fichero publicado después de que empezara su retorno se
excluye aunque declare una fecha antigua. Sin historial de publicación
verificable, queda pendiente y no recibe puntuación prospectiva.

Esto usa el historial de Git y los logs de Actions como evidencia operativa,
no como firma criptográfica ni servicio externo de timestamp. No certifica
que los históricos SEC o los precios del proveedor fueran idénticos en fechas
anteriores a su captura. El sello sí conserva lo observado para esta emisión.

## Qué se evalúa al vencer

Se utilizan retornos totales de precios ajustados del proveedor. No son
ejecuciones, dividendos netos de impuestos, flujos de una cuenta ni una
estrategia de compraventa.

Sobre la misma muestra de acciones con resultado disponible se calculan:

- IC de rangos de la señal por bloques y de BPA/precio frente al retorno
  residual de mercado, y su diferencia pareada.
- Pearson entre score y residuo dividido por volatilidad al origen.
- Ranking del alfa emitido frente al retorno activo del periodo.
- Sesgo, MAE y error cuadrático del ancla, frente al ancla con IC cero y
  una previsión ingenua de cero. Se conservan las diferencias pareadas de MAE.
- Error del ancla SPY, frente a cero y una extrapolación de la tasa corta
  declarada al corte; esta última no representa interés efectivo de una cuenta.

Los puntos se extrapolan mediante `(1 + ancla)^(sesiones / 252) − 1`.
**No son la media ni la distribución completa del simulador.** El registro
de riesgo del núcleo sigue siendo una evaluación distinta. Rank IC, Pearson,
habilidad declarada y ventaja económica no se consideran intercambiables.

La primera puntuación madura se congela. Conserva los precios de los extremos,
la muestra ausente, el hash del sello, código de evaluación y hash de datos
realizados. No se recalcula después de una revisión favorable del proveedor.
Una acción desaparecida o sin precio sigue en el denominador de resultados
esperados y se marca ausente. No se inventa un retorno ni se rellena una
señal que faltaba cuando se emitió.

## Incertidumbre y decisiones

Cada diagnóstico transversal requiere al menos 30 acciones con resultado.
Las medias se agregan por **origen**, no juntando acciones correlacionadas
como observaciones temporales independientes. Se informan los orígenes
solapados y el subconjunto sin solapamiento.

Los intervalos descriptivos por bloques requieren al menos 20 orígenes y
cuatro bloques completos de meses consecutivos de la misma cohorte. Se usan
bloques de 1/3/12 meses para 21/63/252 sesiones, 1.000 remuestreos y semilla
fija `0x20261029`. Si faltan meses o hay pocas observaciones, el intervalo
queda vacío. Son bandas por métrica sin corrección por múltiples revisiones
ni una garantía de cobertura predictiva.

No existe promoción automática del IC o de otra convención. Alcanzar un
recuento habilita diagnóstico, no validación. Una conclusión favorable
requiere precisión, valor incremental frente a referencias, varios subperiodos
y una revisión documentada antes de cambiar parámetros. La ventaja de una
cartera exige además su propia evaluación neta de costes y rotación.

## Operación

```sh
node --test tests/signal-ledger.test.mjs
node scripts/signal_ledger.mjs
```

El workflow `Stock signal validation (prospective)` se ejecuta tras una
actualización de mercado satisfactoria, al cambiar su implementación o
manualmente. Es el único escritor automático del registro, con concurrencia
serializada y commits normales a `main`. Un conflicto no se resuelve
sobrescribiendo un sello. Después del primer commit mensual se comprueba
su publicación y se actualiza solo el resumen.

- Sellos: `data/signal-validation/forecasts/AAAA-MM.json.gz`.
- Entradas originales: `data/signal-validation/inputs/`.
- Primeros resultados maduros: `data/signal-validation/scores/`.
- [Resumen vigente](../dist/data/signal-validation.json).

Los controles de software cubren paridad con producción, fechas causales,
publicación tardía, revisiones, datos faltantes, separación de cohortes y
conservación de los primeros sellos y resultados. Aprobarlos no demuestra
que las predicciones sean acertadas.

## Primera emisión comprobada

El sello de octubre se emitió el 29-oct-2026 a las 12:20 de Lima y apareció
en `c81bd62fdeb2e1a72ea36be2a71687e01b44b274`. La verificación de publicación
se guardó en `f4b83a8`. Usa código `c4172ee`, precios del 28-oct y cohorte
`8f9ae829a773397f8311d7b4a71ec86f13fa31cbed288331a39e6b469e9b8b21`.
Contiene 147 señales utilizables, 13 exclusiones y el ancla SPY. Se verificó
el hash de ambos archivos de entrada y se reconstruyeron todos los valores
de señal, score, confianza y anclas con tolerancia numérica de 10⁻¹².
Los tres horizontes siguen sin observaciones maduras.
