# Comparación de hechos contables FSD con presentación iXBRL original

**Hito:** H1.2. **Fecha del desarrollo:** 9-nov-2026 UTC. **Alcance:** cotejo numérico acotado, sin certificar fundamentales históricos.

El objetivo es verificar directamente determinados datos del extracto trimestral SEC FSD contra el documento primario iXBRL contenido en la presentación EDGAR **completa**. No se acepta un ZIP derivado o un encabezado como sustituto de los importes originales. La [guía SEC FSD](https://www.sec.gov/files/fsds.pdf) advierte que sus periodos (`qtrs`) se expresan en trimestres redondeados y que los valores de NUM tienen precisión limitada; por ello el cotejo no aplica tolerancias ad hoc ni declara error del emisor cuando un valor no coincide.

## Contrato de entrada

El programa `scripts/historical_sec_numeric_concordance.py` requiere un informe previo generado con `historical_sec_fsd_intake.py`, el archivo `.txt` completo por accession y el mismo número de presentación. Primero ejecuta `historical_sec_original_filing.reconcile()` para comprobar CIK, formulario, fecha/hora de aceptación y concordancia documental. Opcionalmente vuelve a verificar el SHA-256 del ZIP FSD.

Si se proporciona `--archive`, el comparador **vuelve a extraer** del ZIP fuente todas las filas de presentaciones y hechos numéricos para la selección CIK/tags/corte registrada y exige igualdad exacta con el informe recibido. Un SHA-256 válido del ZIP, por sí solo, no impide que alguien modifique después el JSON de extracción. El campo `derived_fsd_rows_reproduced_from_original_zip` informa si esta segunda verificación efectivamente se ejecutó. Sin ZIP permanece `false`; no se emite certificación de las filas derivadas.

Después extrae **exactamente un documento primario 10-K/10-Q**, excluye exhibits y busca hechos `ix:nonFraction` solo en documentos XHTML bien formados. Si el documento original emplea HTML que este parser XML no soporta, falla explícitamente, sin inventar una coincidencia. No interpreta transformaciones numéricas distintas del formato decimal compatible ni reemplaza la revisión del documento completo.

Para cada observación de NUM se exige: categoría US-GAAP incluida en el subconjunto conservador del motor, `version` de taxonomía consistente, fecha final exacta, número de trimestres compatible, unidad USD o USD/acción, ausencia **expresa** de segmento y coregistrante. El contexto original también debe ser del mismo emisor y no contener segmentación. El importe se compara con `Decimal` exacto, sin operaciones en coma flotante ni márgenes elegidos después de observar resultados.

Se registran por separado coincidencias, discrepancias de importe, claves originales no encontradas, observaciones originales ambiguas, contextos derivados con segmentación o dimensión desconocida y conceptos no soportados. Dos originales distintos con la misma clave se clasifican como ambiguos; nunca se elige el que coincide mejor con el extracto.

## Reproducción local

```bash
python -m unittest tests.test_historical_sec_numeric_concordance
python scripts/historical_sec_numeric_concordance.py --fsd-report out/sec-fsd-research.json --original out/sec-originals/0000950170-24-118967.txt --accession 0000950170-24-118967 --archive 2024q4.zip --output out/sec-numeric-crosscheck.json --verify
```

Las rutas anteriores son una **instrucción de ejecución**, no una afirmación de que los archivos se hayan obtenido. Para el acceso original, seguir [adquisicion-originales-sec.md](adquisicion-originales-sec.md). Solo se ejecutan pruebas sintéticas en CI y una comprobación de argumentos sin red; los informes con datos de proveedores permanecen bajo `out/`, ignorado por Git.

## Límites y criterios de promoción

**Un hecho numérico coincidente no equivale a una fuente point-in-time admitida.** El comparador no demuestra cuándo se publicó por primera vez el documento, si un extracto trimestral estaba disponible en la fecha histórica, cuál era el valor invertible correspondiente al CIK, ni si la cobertura XBRL es exhaustiva. Los archivos FSD pueden redondear los límites temporales o la precisión numérica; los no coincidentes requieren revisión, no imputación automática.

Las banderas `full_xbrl_document_numeric_fact_set_reconciled=false`, `original_filing_publication_independently_verified=false`, `fundamentals_and_quality_component_certified=false`, `eligible_full_engine_cuts_added=0` y `predictive_validation=not-established` permanecen inmutables. Para admitir un corte histórico se necesitan fuentes originales independientes, identidad y cadena de precios verificadas y reconstrucción causal del modelo; este módulo no modifica las 48 fechas ya examinadas ni el protocolo confirmatorio.

## Cotejo secundario de instancia XBRL incrustada

Cuando un documento primario iXBRL de la presentación completa no supera el parser estricto de XHTML, se mantiene su bloqueo. Como investigación complementaria, `scripts/historical_sec_embedded_instance.py` busca **exactamente** el nombre de instancia incluido en el reporte FSD dentro de los bloques `<DOCUMENT>` del mismo archivo `.txt` original EDGAR. Nunca se consulta un documento de otro accession, ni se acepta un XML arbitrario sin enlace con el original. Si la instancia está ausente, duplicada o mal formada, el procedimiento falla expresamente.

La instancia debe ser XBRL XML bien formado; se excluyen contextos con segmento o dimensiones, identificadores CIK distintos, unidades ajenas y hechos que no correspondan a la taxonomía US-GAAP registrada. Las cifras se comparan como literales decimales exactos, sin tolerancia ajustada tras examinar diferencias. Las claves contables con importes originales distintos se clasifican como ambiguas en vez de elegir el valor favorable. Si se facilita el ZIP original FSD, todas las filas seleccionadas se vuelven a extraer y confrontar antes de la comparación.

```bash
python -m unittest tests.test_historical_sec_embedded_instance
python scripts/historical_sec_embedded_instance.py --fsd-report out/sec-fsd-research.json --original out/sec-originals/0000950170-24-118967.txt --accession 0000950170-24-118967 --archive out/sec-fsd/2024q4.zip --output out/sec-embedded-instance-review.json --verify
```

Este cotejo es **secundario**: ni una coincidencia literal en una instancia extraída permite afirmar que el primario iXBRL fue conciliado ni que los bytes estuvieron disponibles al corte histórico. Tampoco constituye validación completa de hechos, EPS TTM, títulos negociables o pronósticos. El nuevo workflow de investigación es exclusivamente manual y conserva ambos resultados por separado, aun cuando el primario falle.

## Confrontación observable del estado financiero original

El 10-nov-2026 se comprobó la tabla pública del [10-Q original de MSFT](https://www.sec.gov/Archives/edgar/data/789019/000095017024118967/msft-20240930.htm), apartado **Income Statements**, tres meses terminados el 30-sep. El estado financiero expresa cifras en millones de USD: utilidad neta de **24.667** (2024) y **22.291** (2023). Las dos filas FSD `NetIncomeLoss` consolidadas, sin dimensiones, reproducen esos importes al multiplicar por un millón. Los otros dos registros FSD están segmentados, por lo que se excluyen de esta confrontación.

La evidencia puntual y el enlace al documento están registrados por separado en [la observación SEC](../data/historical/sec-first-cut-original-source-observation-v1.json) y protegidos por un test que exige igualdad decimal con las cifras originales de la extracción FSD. La lectura de la tabla **no equivale al cotejo de etiquetas iXBRL ni de sus contextos temporales**, no autentica el primer instante de publicación y no permite calcular EPS TTM, certificar el universo invertible o contar el corte como válido.
