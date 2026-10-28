# Convenciones declaradas y reglas de revisión

Vigente desde el motor 0.33.0. Una convención permite calcular escenarios
condicionales; **no acredita capacidad predictiva** ni se convierte en un
estimador por aparecer en este registro. No se cambian reglas después de
examinar un resultado para presentarlo como validación prospectiva.

Se distinguen cuatro categorías:

1. **Dato observado:** fuente, fecha económica y primera observación
   comprobables. Un precio, P/E o TIR no es un retorno futuro.
2. **Política del mandato:** límites y preferencias explícitos, incluida
   región invertible, liquidez y costes. No se presentan como estimaciones.
3. **Convención declarada:** valor operativo y fuente metodológica, con
   incertidumbre, comparación prevista y condición de revisión. La decisión
   de transicionar exige superar mantener en todos los modelos alternativos
   declarados, neta de costes y con un margen por ruido de simulación.
4. **Candidato experimental:** investigación en sombra; no modifica anclas
   ni composición. Su promoción conserva los requisitos de §9.3.

| Convención | Valor operativo | Qué obligaría a revisarla | Contraste previsto |
|---|---|---|---|
| IC de señales por bloques | 0,05; cero en baja convicción | IC prospectivo indistinguible de cero o utilidad neta inferior a índices | Señal exacta sellada y retornos residuales a 1/3/12 meses; intervalos por bloques y universo al origen. El proxy anual reconstruido no sustituye ese IC |
| Reversión de múltiplos | Vida media de 10 años | Sesgo persistente del retorno o cambios grandes al eliminar re-rating | Modelo sin expansión de múltiplo; ventanas fuera de muestra con múltiplos conocidos al corte |
| Prior y confianza | Prior 6%, confianza inicial 60%, reducida por cobertura | Errores de previsión y cobertura incompatibles con el peso asignado | Comparación con prior común; calibración por calidad y horizonte; baja convicción con confianza ≤30% |
| Equilibrio CAPM y contracción beta | Beta 2/3 estimada + 1/3 hacia uno | Mala calibración de exposición o alfa no estable | Beta sin contracción y referencia de índice, periodos separados |
| Crédito: pérdidas y beta | IG 0,25%; AGG 0,08%; HYG 2%; EMB 0,75%; betas declaradas | Pérdidas, spreads o dependencia conjunta incompatibles con el escenario | En tres modelos se duplican pérdidas y se multiplica por 1,5 la exposición al spread; falta contrastar con impagos/spreads y periodos de estrés |
| Índices por P/E | Rendimiento de beneficios + breakeven, contraído al prior y neto de gastos | Error frente al índice o sensibilidad excesiva a pérdidas excluidas del P/E | Comparar con ancla por constituyentes y referencia constante; mantener rango amplio y fecha del emisor |
| Escenarios macro | Probit de curva para recesión; resto y magnitudes declarados | Rechazo de calibración de probabilidades o de dispersión conjunta | Frecuencias y Brier por régimen; episodios de estrés separados. El probit no fecha con certeza una recesión |
| Varianza a horizonte | Nivel de 500 sesiones, persistencia diaria 0,99 | QLIKE o cobertura peores en nuevos cortes | QLIKE a 21/63/252 sesiones frente a EWMA, con parámetros y ventanas fijados antes del resultado |
| Topes y efectivo | Restricciones del mandato; efectivo 0% hasta consignar otra tasa | Mandato incompatible o condiciones contractuales distintas | Sensibilidad de límites; rendimiento neto observado de la cuenta. La T-bill no se imputa al saldo del broker |

El límite combinado de 20% para alto rendimiento/emergentes permanece.
Los cinco modelos comparados no garantizan cobertura de toda incertidumbre
de parámetros ni de dependencia extrema. Si falta un ancla de una posición
mantenida, se conserva la cartera y se requiere completar Research; no se
utiliza un 6% genérico como evidencia para venderla.

Oro sigue en investigación: inflación menos gastos no se considera una
esperanza validada. Se incorporan DFII10 y DTWEXBGS a la recolección y un
contraste de predictores rezagados. Una regresión contemporánea explicativa
no permite conocer los shocks de mañana.

Fuentes metodológicas: Grinold–Kahn y CAPM describen estructuras, no el IC
particular de Trading; el [probit de la Fed de Nueva York](https://www.newyorkfed.org/research/capital_markets/ycfaq.html)
es una referencia de probabilidad; [World Gold Council](https://www.gold.org/goldhub/research/golds-long-term-expected-return-glter)
distingue el retorno de largo plazo del oro de una identidad con inflación.
