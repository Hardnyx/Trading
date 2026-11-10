# Obtención reproducible de fuentes SEC para el primer corte

**Hito:** H1.2. **Fecha:** 10-nov-2026 UTC. **Resultado esperado:** recibos de adquisición original, conciliación documental y comparación numérica; nunca validación predictiva.

La fuente pública de Financial Statement Data Sets de la SEC enumera el ZIP 2024 Q4 (https://www.sec.gov/dera/data/financial-statement-data-sets.html). El nuevo colector scripts/sec_fsd_acquisition.py limita la descarga a ese trimestre, verifica HTTP 200 en la URL oficial, longitud, SHA-256, estructura ZIP, seguridad de nombres y presencia de SUB/NUM. No sobrescribe archivos y elimina copias parciales tras un error. El archivo permanece bajo out/sec-fsd/, ignorado por Git.

El flujo de GitHub Actions «Acquire first-cut SEC sources (research)» ejecuta una revisión sintética sin red y, mediante SEC_USER_AGENT previamente configurado, intenta descargar además el expediente completo de MSFT 0000950170-24-118967. Después aplica los colectores existentes de FSD y el cotejo conservador iXBRL de NetIncomeLoss para el candidato retrospectivo de 31-dic-2024. Se almacenan únicamente informes JSON como artefactos efímeros, no el ZIP ni la presentación original. Se ejecuta únicamente de forma manual; no se repiten automáticamente descargas SEC tras cambios de código. No se aplica a otros emisores ni implica aprobación de un corte.

Para ejecutarlo localmente desde la raíz de Trading, primero configurar SEC_USER_AGENT con un contacto real autorizado. En Windows CMD, usar estos comandos:

    set "SEC_USER_AGENT=TradingResearch contacto-real@dominio.com"
    python scripts/sec_fsd_acquisition.py --quarter 2024q4
    python scripts/sec_original_acquisition.py --accession 0000950170-24-118967
    python scripts/historical_sec_fsd_intake.py --archive out/sec-fsd/2024q4.zip --cutoff 2024-12-31T21:00:00Z --cik 789019 --tag NetIncomeLoss --output out/sec-fsd-research.json --verify
    python scripts/historical_sec_numeric_concordance.py --fsd-report out/sec-fsd-research.json --original out/sec-originals/0000950170-24-118967.txt --accession 0000950170-24-118967 --archive out/sec-fsd/2024q4.zip --output out/sec-numeric-crosscheck.json --verify

El correo mostrado es solo un marcador; no debe ejecutarse literalmente. Los recibos acreditan únicamente qué bytes se descargaron en la fecha de ejecución. Una respuesta 403, ausencia de SEC_USER_AGENT, divergencia documental o XHTML no admitido por el parser bloquea expresamente el resultado, sin sustituir la fuente. La SEC considera los FSD derivados, no equivalentes a la presentación original.

**Bloqueos vigentes:** demostrar el primer instante de divulgación de los bytes históricos, cotejar todos los hechos relevantes, construir valores TTM, verificar identidad CIK–instrumento y la ejecución de las cotizaciones históricas. H1 mantiene cero cortes integrales certificados. No se altera v1/v2 ni se inspeccionan outcomes para elegir parámetros.

## Primera descarga real y formato del ZIP

El 10-nov-2026 UTC, el [workflow 42861989595](https://github.com/Hardnyx/Trading/actions/runs/42861989595) recuperó el FSD original 2024q4 de 122.932.548 bytes (SHA-256 `9a2cbbaf39c94aa642b33d512f4def92b198d3bfd12d2267bcd27abe55b9902d`) y el archivo completo 10-Q de MSFT de 20.482.578 bytes (SHA-256 `869604009236bade7152e0275bc940cd6f625af066d8d296ae27a9cf6477fed8`). Se comprobó el SEC-HEADER y el tamaño indexado, pero el paso numérico falló porque el campo `accepted` del FSD incluye un sufijo decimal cero (`.0`) que el parser anterior rechazaba. El adaptador permite ahora únicamente fracciones compuestas por ceros (sin redondear valores no nulos) y compara exactamente el instante con el encabezado EDGAR. La extracción y el cotejo continúan siendo resultados de investigación no certificados hasta que se verifique una ejecución completa.

## Precisión observada entre SUB y el encabezado original

En la [ejecución 42862554153](https://github.com/Hardnyx/Trading/actions/runs/42862554153), el ZIP y el original volvieron a descargarse, y el adaptador extrajo cuatro registros de NetIncomeLoss (dos sin segmento y dos segmentados), todos bajo el accession registrado. El SUB derivado indicó aceptación `2024-10-30 16:07:00.0`, mientras el encabezado original del 10-Q fue `2024-10-30 16:07:17`. No son timestamps idénticos: se permite únicamente la clasificación explícita de minuto reportado compatible si el archivo derivado termina en fracción cero y la presentación original está dentro del mismo minuto. El instante original debe ser anterior al corte de información, incluso si el SUB aparenta una hora menor. Esta coincidencia por minuto se registra separada y **no** acredita aceptación exacta ni primera publicación independiente.

## SGML y documento primario iXBRL

La [ejecución 42863438590](https://github.com/Hardnyx/Trading/actions/runs/42863438590) superó recepción, validación de bytes y reconstrucción FSD; el parser del primario real rechazó una declaración XML situada en la segunda línea por espacio ASCII inicial del cuerpo SGML. La siguiente revisión elimina solo espacios ASCII iniciales **para el análisis XML**, conserva el SHA-256 de los bytes originales intactos y sigue rechazando cualquier contenido anterior no blanco, DTD, entidades externas o XHTML no bien formado. Esto no cambia ningún dato del emisor ni autoriza una inferencia de PIT.

## Observación recuperada y límites de acceso

Los recibos verificados en el workflow 42862554153 y las cuatro filas FSD reales se conservan en el informe data/historical/sec-first-cut-original-source-observation-v1.json. Los dos importes consolidados de NetIncomeLoss corresponden a periodos terminados el 30-sep-2023 y el 30-sep-2024, por 22.291 y 24.667 millones de USD; los otros dos registros tienen una dimensión RetainedEarnings y no se suman como observaciones independientes. Las unidades y la segmentación permanecen trazables, sin convertir esos importes en crecimiento TTM o alfa.

La ejecución 42863895340 recibió HTTP 404 al intentar recuperar nuevamente el ZIP, después de dos descargas satisfactorias. Es una limitación de acceso observada, no un cambio confirmado de contenido. El workflow pasa a manual para evitar transferencias reiteradas; los archivos originales no se publican en Git y los hashes se mantienen para cotejos futuros. El FSD 2024q4.zip reporta un Last-Modified HTTP de enero de 2025, posterior al corte retrospectivo de diciembre de 2024. No se declara disponibilidad anterior del archivo derivado ni procedencia PIT por ese dato.

La comparación numérica original sigue pendiente: se detectó una envoltura XML con espacio inicial y se corrigió el parser mediante pruebas sintéticas, pero no se ha repetido el cotejo completo sobre una nueva recuperación válida. Ninguno de los catorce componentes del primer corte se promueve.

## Reejecución sin nuevas descargas SEC

El workflow manual restaura únicamente los dos originales y sus recibos mediante una clave de caché que incorpora **ambos hashes observados**. El paso `scripts/sec_first_cut_source_replay.py --verify` **recalcula** SHA-256 de los bytes FSD y EDGAR, vuelve a comprobar el encabezado, las fechas y la estructura del ZIP, y exige que los recibos coincidan con [la observación congelada](../data/historical/sec-first-cut-original-source-observation-v1.json). Una coincidencia de clave de caché por sí sola no permite continuar.

Si no existe caché, los descargadores oficiales se ejecutan con el contacto SEC configurado. El caché solo se guarda **después** de verificar las huellas originales; de este modo una nueva descarga coincidente permite repetir los análisis sin depender de una futura respuesta HTTP 200. La caché es temporal y puede ser expulsada: si ocurre, se vuelve a exigir descarga y la misma comprobación. Los originales no se publican como adjuntos descargables del workflow ni se incorporan a `main`.

Un archivo distinto, una recepción truncada, un recibo manipulado o un cambio de encabezado provoca un fallo explícito. El resultado se limita a integridad de los bytes recuperados: ni el caché ni la hora de descarga en 2026 acreditan disponibilidad histórica en 2024, identidad bursátil o habilidad predictiva.

## Recuperación focalizada de EDGAR sin volver a descargar FSD

El [extracto FSD completo y congelado](../data/historical/sec-first-cut-fsd-extract-v1.json), producido por la ejecución real 42862554153, queda en Git con los **4.163 bytes exactos** del artefacto, preservando todas las filas y su SHA-256 `464019f23f683c8e65d7b85554ef9d121c12f3882a0d8d27f59ba4c49838f6c5`. `python scripts/sec_first_cut_fsd_extract.py --verify` comprueba el hash original y la correspondencia completa con la observación SEC (accession, CIK, 4 hechos, segmentos, periodos y banderas no confirmatorias). Esto **no sustituye** el ZIP FSD original en una certificación posterior.

El nuevo workflow [EDGAR-only](https://github.com/Hardnyx/Trading/actions/workflows/sec-first-cut-edgar-replay.yml) exige únicamente el archivo completo original de MSFT (aproximadamente 20,5 MB), confronta su SHA-256 previamente registrado y ejecuta **por separado** la comparación estricta del XHTML primario y la comparación con el XML extraído de la misma presentación. Mantiene ambos resultados separados y notifica un fallo del workflow si el primario continúa bloqueado, aunque el cotejo secundario sea satisfactorio. Solo publica JSON de investigación y el recibo de adquisición, nunca los bytes de la presentación.

Existe un único activador `push` mediante un marcador inalterado del primer intento, además de ejecución manual; los cambios sucesivos en Python y documentos no disparan nuevas descargas. La disponibilidad del servidor SEC sigue siendo incierta. Una copia de 2026, incluso verificable por su hash y por el expediente EDGAR, no demuestra por sí misma la cadena de publicación y disponibilidad histórica de todas las fuentes al corte.

## Subconjunto conciliado en documentos originales

[Ejecutado correctamente el 10-nov-2026: workflow 42881818024](https://github.com/Hardnyx/Trading/actions/runs/42881818024). Los bytes originales de Microsoft coinciden con el SHA-256 ya registrado, el primario iXBRL y su instancia extraída procesan los marcadores SGML observados, y ambos confirman **2 importes NetIncomeLoss consolidados exactos y 2 filas derivadas con dimensión excluidas**. Se conservaron los reportes completos en `data/historical/sec-first-cut-primary-inline-review-v1.json` y `data/historical/sec-first-cut-embedded-instance-review-v1.json`, verificados por pruebas de integridad. Un ZIP FSD de 2026 no es por ello vintage certificado de diciembre de 2024. La admisibilidad PIT, la cobertura de otros hechos y la identidad del instrumento permanecen bloqueadas.
