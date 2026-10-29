# Seguimiento y actuación ante fallos de validación

Protocolo `monthly-validation-review-v1`, fijado el 29-oct-2026 antes de que
maduren las primeras observaciones del núcleo 1.0.0. Es seguimiento del
modelo emitido: no recalibra parámetros, no cambia carteras y no autoriza
operaciones.

## Qué muestra Riesgo

El panel **Evidencia del modelo** diferencia el núcleo exacto de precios,
el registro mensual de señales y la referencia estadística anterior. Los
p-valores de esa referencia previa no validan el simulador actual.

Los estados posibles son:

| Estado | Significado y actuación |
|---|---|
| Seguimiento no disponible/desactualizado | No se puede comprobar el estado. Se avisa también junto a la propuesta. |
| Evidencia incompleta | Hay fallos de actualización, publicación, conciliación o resultados maduros ausentes. Reparar la trazabilidad antes de interpretar pruebas. |
| Acumulando, sin validar | Hay registros, pero no una muestra suficiente para las pruebas fijadas. Continuar la evaluación en sombra. |
| Sin rechazo, sin validar | No se detecta rechazo con las pruebas disponibles. Revisar precisión, cola y comparación con referencias; no equivale a adecuación. |
| Modelo en revisión | Hay rechazo en la revisión mensual. Suspender nuevas promociones y documentar el diagnóstico antes de cambiar un componente. |

Un informe no corresponde a la sesión si difiere su corte, captura o versión
del núcleo. Cuatro días naturales sin actualizar son el límite operativo
de frescura del informe; no certifican el calendario de la bolsa. Los
fallos de la actualización de datos se conservan hasta una actualización
satisfactoria o una captura nueva. No se emiten señales nuevas usando un
refresh fallido. Un fallo del propio seguimiento puede dejar de publicarse;
el límite de frescura permite detectar ese caso desde el navegador.

## Unidad de evidencia y comprobaciones

Se leen los sellos y primeras puntuaciones de `data/simulator-validation`.
La primera publicación Git debe conservar el mismo blob y preceder al
origen del retorno. Se separan versiones del núcleo y se comprueba la
compatibilidad entre sello y resultado. Un resultado vencido que no está
guardado se marca incompleto; no se presenta como un pronóstico que aún no
ha vencido. Tampoco se rellenan activos desaparecidos con cero.

Las pruebas se hacen **por activo o cesta y horizonte**, nunca juntando
activos correlacionados para aumentar artificialmente n. Se selecciona un
subconjunto cronológico sin solapamiento. Los datos faltantes y los huecos
entre ventanas interrumpen la secuencia usada para agrupamiento de excepciones.
Las fechas de un resultado ya congelado sobreviven al desplazamiento de
la ventana histórica del proveedor.

Para cada serie se conservan:

- Tasa de excepciones VaR95 e intervalo binomial exacto de 95%, bajo su
  hipótesis de independencia temporal. Cero excepciones no implica riesgo cero.
- Kupiec como diagnóstico asintótico, junto a una prueba binomial exacta
  para el rechazo de cobertura. Se necesitan 20 orígenes y ningún resultado
  ausente para habilitar esta última; no es un análisis de potencia.
- Christoffersen como diagnóstico asintótico de independencia. Solo entra
  en la familia de revisión con 100 transiciones y cinco excepciones como
  mínimo. Son umbrales operativos declarados, no una garantía asintótica.
- Ganancias de CRPS y QLIKE frente al EWMA sin retorno supuesto, sobre los
  mismos resultados. CRPS tiene una banda aproximada por bloques de cinco
  orígenes cuando hay veinte; las ganancias anteriores son descriptivas.
- Residuo medio de ES y número de observaciones de cola. No se convierte
  una media cercana a cero con pocas colas en validación del ES.

Las curvas acumuladas de la propuesta sellada muestran excepciones y QLIKE
a 1/5/21 sesiones. Sin resultados no se dibuja una curva ficticia de cero.
Si QLIKE no está definido, ese punto no se convierte en cero.

## Revisión mensual y multiplicidad

Los contadores se actualizan con los datos; la decisión formal se congela
con la primera evaluación procesada de cada mes. No se vuelve a probar
dentro del mismo mes para escoger un resultado favorable. Si el refresh
falló, la revisión nueva queda aplazada hasta disponer de una captura apta.

La familia contiene cobertura exacta e independencia para todas las series
emitidas del núcleo actual. Una prueba aún no evaluable permanece en la
familia con p=1 para el ajuste de Holm. El presupuesto del chequeo mensual k
es `0,05 / (k × (k + 1))`; la suma de los presupuestos de revisiones de ese
núcleo no supera 0,05. Holm admite dependencia entre pruebas; el gasto
entre revisiones no presupone independencia temporal de las revisiones.

Esa contabilidad no repara un p-valor mal especificado, un calendario
incompleto o la aproximación asintótica de Christoffersen. El control de
error depende de esas hipótesis, y no es una probabilidad de que el modelo
sea correcto. El índice cuenta también revisiones sin pruebas habilitadas:
es conservador y no se optimiza después de observar los resultados.

## Actuación concreta ante rechazo

1. Conservar el sello, primera puntuación, revisión y datos utilizados.
   Corregir el problema no reescribe esos resultados.
2. Revisar fechas, publicaciones, precios, unidades, muestra ausente y
   error Monte Carlo de los cuantiles emitidos. Un rechazo del núcleo no
   identifica por sí mismo al GJR como causa.
3. Comparar núcleo y EWMA sobre los mismos activos/cestas, fechas y
   horizontes: cobertura, agrupamiento, CRPS, QLIKE y cola. No utilizar el
   p-valor agrupado del registro estadístico legado para escoger ganador.
4. Si EWMA tiene mejor respaldo, preparar la retirada o recalibración del
   componente cuestionado como candidato en sombra. El fallback no se
   promueve solo porque el modelo actual rechace: debe superar su propio
   contraste y los controles de riesgo aplicables.
5. Documentar la decisión, evidencia y criterio de reentrada. Una modificación
   material de la ley o del procedimiento de varianza incrementa la versión
   del núcleo y conserva la cohorte anterior.

La interfaz muestra el aviso de revisión también junto a la propuesta. Los
cálculos siguen disponibles como escenarios de investigación. No se ordena
conservar unos pesos por decreto ni se ejecuta una transición automática.
Una corrección matemática demostrada puede requerir un cambio; no hace
falta esperar a una revisión favorable para corregirla y versionarla.

## Trazabilidad y operación

- Código: `scripts/validation_watch.py`.
- [Estado actual](../dist/data/validation-review.json).
- Revisiones inmutables: `data/validation-reviews/AAAA-MM.kernel-VERSIÓN.json.gz`.
- Se registran hashes de entradas y código, y versiones Python/NumPy/SciPy.
- El workflow de señales actualiza y despliega el informe, incluso si el
  refresh de datos acabó mal. La revisión mensual anterior permanece intacta.

```sh
python -m unittest tests.test_validation_watch
python scripts/validation_watch.py --preview
python scripts/validation_watch.py
```

Fuentes de los diagnósticos: [Kupiec (1995), ficha de la Reserva Federal](https://fedinprint.org/item/fedgfe/34596),
[Christoffersen (1998), artículo original](https://users.ssc.wisc.edu/~behansen/718/Christoffersen1998.pdf)
y [prueba binomial exacta de SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html).
Los umbrales, calendario y política operativa anteriores son decisiones
de este proyecto, no criterios regulatorios ni calibraciones de mercado.
