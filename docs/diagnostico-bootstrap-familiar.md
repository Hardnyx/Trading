# Error familiar bajo siete nulos sintéticos

**Hito:** H0.3. **Fecha:** 9 de noviembre de 2026 UTC. **Evidencia:** simulación metodológica, no pronósticos bursátiles.

El análisis previo [de una sola prueba](diagnostico-bootstrap-confirmatorio.md) identificó tasas de rechazo nulo mayores que el umbral inicial de Holm bajo un proceso AR(1). Este complemento comprueba el **error familiar bajo el nulo global** de siete efectos sintéticos. Para Holm, cuando los siete nulos son verdaderos, ocurre al menos un rechazo exactamente si el menor valor p es menor o igual que `0.05/7`.

El script `scripts/confirmatory_familywise_bootstrap.py` construye siete series mensuales sintéticas con factor común AR(1) gaussiano. En cada réplica, el bootstrap centrado de 10 000 sorteos toma los **mismos índices mensuales para los siete contrastes**. No calcula siete valores p con remuestreos independientes, ni utiliza precios, resultados históricos, resultados confirmatorios o ajustes del motor.

## Rejilla fijada para diagnóstico

- Meses consecutivos: 96 y 192.
- Dependencia temporal AR(1) supuesta: 0 y 0,6.
- Correlación contemporánea de los siete efectos: 0 y 0,75.
- Bloques mensuales circulares: 12 y 24.
- Réplicas nulas independientes por combinación: 256; semilla determinista 20261109.
- Bootstrap: 10 000 sorteos por réplica, el número y umbral del protocolo v2.

Se generan **16 combinaciones** y se publica cada frecuencia con su intervalo Wilson Monte Carlo del 95 %. El programa detiene anticipadamente la simulación de una réplica solo cuando **todos** los siete conteos de excedencias hacen imposible superar `alpha/7`. Ocho casos adversariales de la prueba unitaria contrastan esa optimización con los valores p completos sobre los mismos índices remuestreados.

```bash
python scripts/confirmatory_familywise_bootstrap.py --verify \
  --output out/confirmatory-familywise-bootstrap-v1.json
```

La fuente de incertidumbre es puramente sintética. Los siete contrastes reales no tienen una matriz de dependencia común AR(1), comparten horizontes distintos, instrumentos, observaciones faltantes y una cuenta económica. **La tasa bajo el nulo global no prueba control fuerte del error familiar para configuraciones con nulos parcialmente verdaderos**. Tampoco representa la potencia para magnitudes económicas relevantes ni permite reducir el umbral de 96 meses.

**Criterio de interpretación:** comparar con el **5 % familiar nominal**, no con el 0,714 % del primer contraste individual. Si las tasas simuladas son superiores a 5 %, documentar la posible distorsión de tamaño finito. No editar v1/v2, no corregir a posteriori los p-valores registrados y no utilizar las simulaciones para elegir favorablemente bloque, semilla, horizonte o familia de hipótesis. Una revisión inferencial requiere propuesta de protocolo nueva y nueva cohorte prospectiva; la validación de Trading sigue sin acreditarse.

## Resultado reproducido del diagnóstico conjunto

El [commit `8f08908`](https://github.com/Hardnyx/Trading/commit/8f0890875b64610dcbb2f64197eb807df0522fc1) aprobó [CI 42647440162](https://github.com/Hardnyx/Trading/actions/runs/42647440162), con **407 pruebas Python** y el artefacto `confirmatory-familywise-bootstrap`; [Pages 42647440235](https://github.com/Hardnyx/Trading/actions/runs/42647440235) también aprobó. Las tasas siguientes proceden de la rejilla fija y la semilla sintética 20261109, reproducidas localmente y generadas por la CI. Son frecuencias de **al menos un rechazo** entre siete hipótesis nulas verdaderas, no frecuencias por test.

| Meses | AR(1) temporal | Correlación entre pruebas | Bloque | Rechazos | Frecuencia familiar |
|---|---:|---:|---:|---:|---:|
| 96 | 0.0 | 0.00 | 12 | 31/256 | 12.11 % |
| 96 | 0.0 | 0.00 | 24 | 64/256 | 25.00 % |
| 96 | 0.0 | 0.75 | 12 | 13/256 | 5.08 % |
| 96 | 0.0 | 0.75 | 24 | 28/256 | 10.94 % |
| 96 | 0.6 | 0.00 | 12 | 54/256 | 21.09 % |
| 96 | 0.6 | 0.00 | 24 | 77/256 | 30.08 % |
| 96 | 0.6 | 0.75 | 12 | 29/256 | 11.33 % |
| 96 | 0.6 | 0.75 | 24 | 43/256 | 16.80 % |
| 192 | 0.0 | 0.00 | 12 | 28/256 | 10.94 % |
| 192 | 0.0 | 0.00 | 24 | 35/256 | 13.67 % |
| 192 | 0.0 | 0.75 | 12 | 6/256 | 2.34 % |
| 192 | 0.0 | 0.75 | 24 | 13/256 | 5.08 % |
| 192 | 0.6 | 0.00 | 12 | 41/256 | 16.02 % |
| 192 | 0.6 | 0.00 | 24 | 57/256 | 22.27 % |
| 192 | 0.6 | 0.75 | 12 | 24/256 | 9.38 % |
| 192 | 0.6 | 0.75 | 24 | 31/256 | 12.11 % |

**Comparación:** el error familiar nominal registrado es **5 %**; en 15 de 16 escenarios sintéticos la frecuencia de rechazo estimada lo superó. Para 96 meses, AR(1) 0,6, correlación entre pruebas cero y bloque 24, el resultado fue **77/256 = 30,08 %**, con intervalo Wilson Monte Carlo al 95 % de aproximadamente **24,79 %–35,96 %**. Con 192 meses, AR(1) 0,6, correlación cero y bloque 24 persistió una frecuencia de 57/256 = 22,27 %. La precisión limitada por 256 repeticiones exige interpretar diferencias pequeñas respecto al 5 % con cautela.

**Conclusión técnica:** el bootstrap centrado y Holm registrados no han demostrado calibración suficiente en muestra finita en esta clase de procesos generadores conjuntos. Esta prueba bajo nulo global **no** establece control fuerte de error familiar ante nulos parcialmente falsos, ni los siete verdaderos objetivos estadísticos y sus horizontes. Por tanto, **no activa** v2. Resolver esta brecha requiere análisis independiente de distribución conjunta, dependencia, métodos de bootstrap y efectos mínimos económicamente justificables. Si la solución altera el procedimiento, documentar **un protocolo v3 prospectivo** con nueva cohorte, sin reinterpretar resultados de desarrollo ni alterar v1/v2.

## Control positivo con distribución nula conocida

Para comprobar si los rechazos excesivos se explican por Holm o por el remuestreo, el mismo generador agrega una referencia **analítica exacta para sus propios datos sintéticos**. Cada serie marginal AR(1) es gaussiana, estacionaria, de varianza unitaria y con `phi` conocido. Por tanto:

```text
Var(S_n) = n + 2 * sum((n - k) * phi**k, k=1..n-1)
p_oracle = 1 - Phi(S_n / sqrt(Var(S_n)))
```

Se calculan siete valores p marginales exactos y se aplica la **misma regla de entrada Holm** (`min(p) <= 0.05/7`). El factor común entre pruebas no invalida los valores p marginales ni exige independencia transversal para el control de Holm. La referencia usa **parámetros verdaderos del generador, que no están disponibles en el mercado**: es un control positivo de la simulación y nunca una alternativa inferencial lista para utilizar.

Con las mismas 256 matrices de siete series de cada combinación (semilla 20261109), el control analítico produce:

| Meses | AR(1) | Correlación entre pruebas | Rechazos del control / 256 |
|---|---:|---:|---:|
| 96 | 0.0 | 0.00 | 12 (4,69 %) |
| 96 | 0.0 | 0.75 | 6 (2,34 %) |
| 96 | 0.6 | 0.00 | 10 (3,91 %) |
| 96 | 0.6 | 0.75 | 5 (1,95 %) |
| 192 | 0.0 | 0.00 | 9 (3,52 %) |
| 192 | 0.0 | 0.75 | 6 (2,34 %) |
| 192 | 0.6 | 0.00 | 14 (5,47 %) |
| 192 | 0.6 | 0.75 | 13 (5,08 %) |

Cada control es idéntico para bloques 12 y 24, porque el control analítico no utiliza bloques. El artefacto conserva, por bloque, los rechazos del bootstrap, los del control y las discrepancias **solo bootstrap / solo control** sobre las **mismas réplicas**, sin reejecutar ni seleccionar un nuevo nulo. Las frecuencias de 5,08 % y 5,47 % son estimaciones Monte Carlo, no violaciones demostradas del control nominal.

**Lectura:** el control exacto se aproxima al tamaño esperado en esta rejilla, mientras que el bootstrap centrado registra hasta 30,08 % de rechazos familiares. Esto localiza el defecto metodológico probable en la calibración del bootstrap bajo estos generadores, no demuestra un error de Holm. Tampoco acredita control fuerte para hipótesis parcialmente nulas ni autoriza suponer que AR(1) gaussiano describe las medidas bursátiles. **No se modifica ni activa v2; H0.3 sigue abierto.**
