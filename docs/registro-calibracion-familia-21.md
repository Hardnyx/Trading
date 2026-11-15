# Calibración de la familia de tres pruebas a 21 sesiones (rediseño de H0.3)

**Registro:** [estudio-calibracion-familia-21-v1.json](estudio-calibracion-familia-21-v1.json), publicado en [`0f69fdb`](https://github.com/Hardnyx/Trading/commit/0f69fdb5) antes de implementar. Ejecución: `python scripts/confirmatory_family21_stress.py`. Resultado completo: [auditorias/calibracion-familia-21-v1.json](auditorias/calibracion-familia-21-v1.json).

**Por qué.** Con la familia v2 de siete pruebas, ningún método controló el error familiar con 96 meses ([fixed-b](registro-diagnostico-fixed-b.md)), porque los horizontes de 63 y 252 sesiones se solapan entre orígenes mensuales y generan persistencia. Con solo 21 sesiones evaluadas cada mes no hay solapamiento por construcción. La rejilla conserva los escenarios de persistencia alta como estrés.

## Resultado (15-nov-2026 UTC): 64 escenarios × 2 brazos × 512 réplicas

| Brazo | Escenarios con exceso | Con AR(1) 0 | 0,3 | 0,6 | 0,85 | Error familiar con AR(1) ≤ 0,3 | Detección de +0,5 DT con AR(1) ≤ 0,3 |
|---|---:|---:|---:|---:|---:|---|---|
| A · t de Student (meses independientes) | 48/64 | 0 | 16 | 16 | 16 | — | — |
| **B · KVB, b = 1** | **5/64** | **0** | **0** | **0** | 5 | **2,3 %–5,5 %** | **73 %–91 % (96 meses); 91 %–99 % (192 meses)** |

Los cinco excesos de KVB están todos en 96 meses con AR(1) 0,85; el peor tiene cota inferior simultánea 8,2 %. Con 192 meses, ninguno.

## Lectura

- **La reducción a tres pruebas a 21 sesiones resuelve el problema de calibración en el rango del diseño.** KVB no muestra exceso hasta AR(1) 0,6, cuando con siete pruebas fallaba desde 0,6 a 96 meses. Aun así, ninguna cota superior queda por debajo del 5 % en todos los escenarios: no se certifica control universal.
- **La prueba t simple solo vale si los efectos mensuales son independientes;** con cualquier autocorrelación falla, así que no es una opción segura.
- **Potencia:** con 96 meses, KVB detecta un desplazamiento de 0,5 desviaciones estándar del efecto mensual entre el 73 % y el 91 % de las veces.

## Siguiente paso de H0.3

Un registro confirmatorio v3 con esta familia y KVB, que fije antes de cualquier cohorte nueva los tamaños de efecto económicamente relevantes, la potencia correspondiente y el número de meses. No modifica v2 ni habilita inferencia.
