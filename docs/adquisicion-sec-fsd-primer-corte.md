# Obtención reproducible de fuentes SEC para el primer corte

**Hito:** H1.2. **Fecha:** 10-nov-2026 UTC. **Resultado esperado:** recibos de adquisición original, conciliación documental y comparación numérica; nunca validación predictiva.

La fuente pública de Financial Statement Data Sets de la SEC enumera el ZIP 2024 Q4 (https://www.sec.gov/dera/data/financial-statement-data-sets.html). El nuevo colector scripts/sec_fsd_acquisition.py limita la descarga a ese trimestre, verifica HTTP 200 en la URL oficial, longitud, SHA-256, estructura ZIP, seguridad de nombres y presencia de SUB/NUM. No sobrescribe archivos y elimina copias parciales tras un error. El archivo permanece bajo out/sec-fsd/, ignorado por Git.

El flujo de GitHub Actions «Acquire first-cut SEC sources (research)» ejecuta una revisión sintética sin red y, mediante SEC_USER_AGENT previamente configurado, intenta descargar además el expediente completo de MSFT 0000950170-24-118967. Después aplica los colectores existentes de FSD y el cotejo conservador iXBRL de NetIncomeLoss para el candidato retrospectivo de 31-dic-2024. Se almacenan únicamente informes JSON como artefactos efímeros, no el ZIP ni la presentación original. Se puede ejecutar manualmente; una modificación del propio workflow dispara una ejecución de comprobación. No se aplica a otros emisores ni implica aprobación de un corte.

Para ejecutarlo localmente desde la raíz de Trading, primero configurar SEC_USER_AGENT con un contacto real autorizado. En Windows CMD, usar estos comandos:

    set "SEC_USER_AGENT=TradingResearch contacto-real@dominio.com"
    python scripts/sec_fsd_acquisition.py --quarter 2024q4
    python scripts/sec_original_acquisition.py --accession 0000950170-24-118967
    python scripts/historical_sec_fsd_intake.py --archive out/sec-fsd/2024q4.zip --cutoff 2024-12-31T21:00:00Z --cik 789019 --tag NetIncomeLoss --output out/sec-fsd-research.json --verify
    python scripts/historical_sec_numeric_concordance.py --fsd-report out/sec-fsd-research.json --original out/sec-originals/0000950170-24-118967.txt --accession 0000950170-24-118967 --archive out/sec-fsd/2024q4.zip --output out/sec-numeric-crosscheck.json --verify

El correo mostrado es solo un marcador; no debe ejecutarse literalmente. Los recibos acreditan únicamente qué bytes se descargaron en la fecha de ejecución. Una respuesta 403, ausencia de SEC_USER_AGENT, divergencia documental o XHTML no admitido por el parser bloquea expresamente el resultado, sin sustituir la fuente. La SEC considera los FSD derivados, no equivalentes a la presentación original.

**Bloqueos vigentes:** demostrar el primer instante de divulgación de los bytes históricos, cotejar todos los hechos relevantes, construir valores TTM, verificar identidad CIK–instrumento y la ejecución de las cotizaciones históricas. H1 mantiene cero cortes integrales certificados. No se altera v1/v2 ni se inspeccionan outcomes para elegir parámetros.
