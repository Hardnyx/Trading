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
