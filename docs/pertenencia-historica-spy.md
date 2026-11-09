# Recuperación de pertenencia histórica documentada en SPY

**Hito:** H1.2. **Corte descriptivo inicial:** 31-dic-2024. **Muestra:** 48 fechas de investigación previamente registradas. **Estado:** diagnóstico de pertenencia a SPY, no universo invertible completo.

El repositorio conserva declaraciones SEC N-PORT originales del ETF SPY y extractos explícitos de CUSIP/ticker observados en N-PORT originales de otras series. El nuevo `scripts/historical_spy_membership_audit.py` vuelve a analizar los originales archivados, coteja el manifiesto y el derivado publicado y construye una secuencia **sin adelantarse a la fecha de publicación** de las posiciones reveladas del fondo.

La fecha `as_of` de una declaración representa la cartera declarada para un periodo anterior; `available_after_day` es la fecha conservadora desde la que puede usarse públicamente. Se exige `available_after_day < cut` y antigüedad de hasta 120 días. **El informe de SPY no certifica que cada posición siguiera perteneciendo al índice o al fondo en la fecha de decisión.** Un mes sin información fresca queda bloqueado, sin imputación automática.

## Entregable y controles

```bash
python scripts/historical_spy_membership_audit.py --verify
python scripts/historical_spy_membership_audit.py --output out/historical-spy-membership-audit-v1.json
```

El reporte de CI identifica para cada corte el documento original usado, su periodo de cartera y disponibilidad, número de posiciones positivas, CUSIP con dígito válido, duplicados y posiciones sin CUSIP válido, y peso con observación explícita de ticker anterior a la fecha. Las posiciones no se normalizan ni se sustituyen por componentes actuales.

Los cambios entre dos declaraciones **distintas** se registran como `newly_disclosed_cusips` y `no_longer_disclosed_cusips`. Un CUSIP ausente en la siguiente declaración **no** demuestra una exclusión del índice, una retirada de bolsa, una fusión o la quiebra del emisor. No se cuentan las declaraciones trimestrales repetidas como transiciones nuevas.

Para el primer corte candidato se compara además la lista de acciones elegidas por el piloto retrospectivo con los **tickers literales** que figuraban en fuentes SEC públicas. Este control documenta la dependencia del catálogo posterior y localiza símbolos que no tienen respaldo en ese extracto de SPY. **Un ticker coincidente no acredita identidad histórica, precio válido, listado, elegibilidad ni que la acción fuera negociable al corte.** Una acción ausente de SPY podría ser una inversión legítima: el objetivo es documentar cobertura, no forzar el universo a las posiciones del ETF.

**Cobertura inversa:** comprobar que todos los 127 símbolos del piloto coincidan con cadenas de ticker públicas es insuficiente, porque aun así podrían faltar cientos de posiciones históricamente declaradas. El informe calcula la diferencia en ambos sentidos, incluyendo el peso declarado no cubierto por las acciones del piloto. Produce una cola priorizada por **peso original** de CUSIP que estuvieron en la declaración pública de SPY pero no figuran en la selección retrospectiva. No se consultan retornos futuros ni se usa esa cola para optimizar, modificar el motor o completar artificialmente el histórico. La cola solo solicita evidencia externa de identidad y precios; no declara que esos emisores fueran necesariamente invertibles a la fecha del corte.

## Resultado observado sobre archivos congelados

La ejecución de CI del 9-nov-2026 UTC con el commit [`03d2f0b`](https://github.com/Hardnyx/Trading/commit/03d2f0b1ec7cd0876f51f566bc661a6ad27cc5f6) concluyó sin errores: [run 42542612093](https://github.com/Hardnyx/Trading/actions/runs/42542612093). Los resultados se verificaron releyendo y reconciliando las declaraciones SEC archivadas.

- Calendario registrado: **48 cortes**; **26** con información original de SPY pública y suficientemente reciente; **22** bloqueados o sin fuente fresca.
- Cambios entre declaraciones distintas: **15 transiciones**. Son diferencias de CUSIP divulgados, **no** verificaciones de altas/bajas de cotización.
- Piloto retrospectivo de 31-dic-2024: **127 acciones**; **127** tienen coincidencia literal con tickers SEC disponibles antes del corte. No es una unión histórica certificada de valores.
- Declaración SPY originalmente fechada el 30-sep-2024 y disponible conservadoramente después del 29-nov-2024: peso positivo total **0,99989845** de NAV; peso no cubierto por la selección del piloto **0,38488811** de NAV, equivalente a **38,488811 puntos porcentuales del fondo**; **351 CUSIP distintos válidos** de esa fuente no están cubiertos por la selección retrospectiva.
- La cola de `priority_vendor_identity_requests` identifica esos CUSIP y los ordena según su peso originalmente divulgado, sin atribuirles un precio, rendimiento, nueva identidad, disponibilidad bursátil o estado de desliste.

**Interpretación:** demostrar que todos los símbolos sobrevivientes del piloto aparecían en fuentes históricas no elimina el riesgo de selección. La declaración pública deja fuera de la muestra piloto una parte material del peso original de SPY. Esta evidencia no implica que los 351 instrumentos debieran comprarse ni que todos siguieran vigentes al 31-dic-2024. Es necesario recuperar identidades históricas continuas y precios/elegibilidad originales antes de construir el universo completo.

## Condiciones de rechazo

- Hash o interpretación original que ya no coincida con el archivo derivado.
- Declaración publicada en o después de la fecha de corte, o más antigua que el límite de 120 días.
- Posición con ticker observado cuya prueba de publicación llegó posteriormente al corte.
- Cambio silencioso de CUSIP a un identificador de proveedor, o colisión ambigua presentada como vínculo verificable.
- Intento de tratar meses sin declaraciones elegibles como observaciones completas.

**Aceptación:** trazabilidad de pertenencia públicamente documentada en SPY, transiciones entre declaraciones e inventario de lo que queda sin enlace; resultado reproducible bajo CI. **H1.2 permanece parcial**, porque todavía falta el universo invertible completo, incluidos los deslistados, una fuente de security master con vigencias verificables, precios de ejecución y eventos corporativos históricos. El contraste es de cobertura y sesgo de supervivencia potencial, no de rentabilidad ni capacidad predictiva.
