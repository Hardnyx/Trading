# Sellado de tiempo independiente de la evidencia prospectiva

**Desde:** 15-nov-2026. **Código:** [`timestamp_evidence.py`](../scripts/timestamp_evidence.py), workflow `timestamp-evidence.yml`. **Datos:** `data/timestamps/`.

## Para qué

El primer bloqueo operativo del [protocolo v3](protocolo-confirmacion-integral-v3.md) exige que los pronósticos originales tengan una **primera captura verificable de forma independiente**. La fecha de un commit de Git la fija quien lo hace; un sello RFC 3161 lo firma una autoridad externa y cualquiera puede comprobarlo con OpenSSL, sin confiar en este repositorio ni en GitHub.

## Cómo funciona

1. Tras cada actualización de mercado, revisión de señales y revisión del fondo, el workflow lista los archivos de evidencia nuevos o cambiados (pronósticos sellados, capturas mensuales del motor, revisiones del fondo, ledgers de señales y riesgo, y las capturas de datos de mercado, holdings y volatilidad).
2. Escribe un manifiesto con el SHA-256 de cada uno y pide a **DigiCert, Sectigo y FreeTSA** que firmen el hash del manifiesto. Exige al menos dos firmas válidas o no registra nada.
3. Guarda el manifiesto y los tokens `.tsr`. La CI rápida verifica todos los tokens en cada cambio.

## Verificar a mano

```bash
openssl ts -verify -data data/timestamps/<sello>.manifest.json -in data/timestamps/<sello>.digicert.tsr -CAfile /etc/ssl/certs/ca-certificates.crt
openssl ts -verify -data data/timestamps/<sello>.manifest.json -in data/timestamps/<sello>.freetsa.tsr -CAfile data/timestamps/freetsa-cacert.pem
sha256sum <archivo listado en el manifiesto>
```

## Qué prueba y qué no

Prueba que cada archivo existía con ese contenido **a más tardar** a la hora firmada. El primer sello, del 15-nov-2026 a las 02:24 UTC, cubre 1.385 archivos existentes; para ellos solo acredita esa fecha, no la de su creación. Desde ahora, cada pronóstico se sella minutos después de emitirse, antes de la siguiente apertura del mercado. No prueba que el pronóstico sea correcto ni que los datos de entrada sean las versiones originales de sus proveedores.
