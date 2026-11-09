# Recepción de estados financieros SEC as-filed, H1.2

**Fecha:** 9-nov-2026 UTC. **Alcance:** adquisición retrospectiva, no certificación causal del motor.

La [SEC publica conjuntos trimestrales](https://www.sec.gov/dera/data/financial-statement-data-sets.html) de estados financieros extraídos de presentaciones XBRL tal como fueron declaradas. El [ZIP 2024 Q4](https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip) puede servir para investigar el primer corte candidato del 31-dic-2024. **Un extracto descargado hoy no demuestra que ese mismo ZIP existiera antes de una decisión histórica.** Los archivos SEC tampoco sustituyen la revisión de los documentos originales.

## Contrato de ingesta

El script `scripts/historical_sec_fsd_intake.py` consume un ZIP **local**, recorre `sub.txt` y `num.txt` en streaming y conserva SHA-256 del archivo, identificador CIK explícito, accession `adsh`, formulario, hora de aceptación, fecha del ejercicio y valores numéricos originales. La fecha `accepted` se interpreta en hora de Nueva York y se compara con la hora de información expresada en UTC, sin confundir fecha fiscal y disponibilidad.

Se preservan por separado formularios originales y enmiendas `/A`; no se elige la versión que arroje el mejor resultado ex post. Cada dato conserva `tag`, `version`, `ddate`, `qtrs`, `uom`, `coreg`, `segments`, `value` y `footnote`. La SEC [añadió `segments` a sus conjuntos reprocesados en diciembre de 2024](https://www.sec.gov/dera/data/financial-statement-data-sets.html): si falta la columna se registra como desconocida, nunca como certificación de ausencia de dimensiones. Los datos segmentados no se mezclan silenciosamente con los consolidados. La ingesta rechaza acceso futuro al corte, valores no finitos y claves duplicadas.

## Reproducción

Solicitar una fuente sin descargar ni publicar datos de emisores:

```bash
python scripts/historical_sec_fsd_intake.py --template out/historical-sec-fsd-source-request-v1.json --verify
```

Con el ZIP original adquirido por separado, un CIK histórico independiente y un instante de información explícito:

```bash
python scripts/historical_sec_fsd_intake.py --archive 2024q4.zip --cutoff 2024-12-31T21:00:00Z --cik 0000000123 --tag NetIncomeLoss --output out/sec-fsd-example-research.json --verify
```

El CIK indicado es solamente un ejemplo de sintaxis y **no** corresponde a un valor negociable certificado. El corte temporal debe corresponder a la decisión efectiva; el ejemplo de 21:00 UTC representa las 16:00 de Nueva York de ese día, no la verificación independiente de todas las sesiones especiales.

## Requisitos que permanecen bloqueados

1. Preservar y verificar por número de acceso los **documentos originales**, junto con la primera publicación independientemente comprobada.
2. Resolver identidad histórica CIK–valor negociable, enmiendas disponibles al corte y etiquetas XBRL compatibles; reconstruir TTM y bases por acción sin información futura.
3. Vincular precios brutos, splits y dividendos originales con el dato financiero de igual fecha, y reproducir las entradas verdaderas del motor.

El informe conserva `fundamentals_and_quality_component_certified=false`, `eligible_full_engine_cuts_added=0`, `confirmatory_origins_added=0` y `predictive_validation=not-established`. CI ejecuta tests con **ZIP sintéticos** y publica únicamente una plantilla de solicitud, no archivos de proveedores ni fundamentales supuestamente certificados.

El adaptador no automatiza descargas SEC para preservar la separación entre adquisición, auditoría original y cálculo; cualquier adquisición automatizada futura debe respetar la [política de acceso](https://www.sec.gov/about/privacy-information).
