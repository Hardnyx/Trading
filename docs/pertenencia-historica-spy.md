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

## Condiciones de rechazo

- Hash o interpretación original que ya no coincida con el archivo derivado.
- Declaración publicada en o después de la fecha de corte, o más antigua que el límite de 120 días.
- Posición con ticker observado cuya prueba de publicación llegó posteriormente al corte.
- Cambio silencioso de CUSIP a un identificador de proveedor, o colisión ambigua presentada como vínculo verificable.
- Intento de tratar meses sin declaraciones elegibles como observaciones completas.

**Aceptación:** trazabilidad de pertenencia públicamente documentada en SPY, transiciones entre declaraciones e inventario de lo que queda sin enlace; resultado reproducible bajo CI. **H1.2 permanece parcial**, porque todavía falta el universo invertible completo, incluidos los deslistados, una fuente de security master con vigencias verificables, precios de ejecución y eventos corporativos históricos. El contraste es de cobertura y sesgo de supervivencia potencial, no de rentabilidad ni capacidad predictiva.
