# Laboratorio 09: Data Warehousing Moderno con BigQuery — Optimización de Costos, Apache Iceberg y Vistas Materializadas

- **Duración estimada**: 75–80 minutos
- **Nivel**: Intermedio / Analítica de Datos y FinOps
- **Entorno de trabajo**: **Google Cloud Shell (`bq`, `gcloud`, `python3`)** + Verificaciones visuales en **BigQuery Studio**

---

## 1. Objetivo del Laboratorio

Construir un pequeño Data Warehouse a partir de **36 millones de viajes reales de taxi en Nueva York** y medir con datos el impacto de cada decisión de diseño:
1. **Almacenamiento columnar**: comprobar cuánto cuesta realmente un `SELECT *` y por qué `LIMIT` no lo abarata.
2. **Particionamiento y clusterización**: reducir los bytes procesados por la misma consulta.
3. **FinOps**: poner topes de gasto y comparar on-demand frente al costo equivalente en slots, sin crear reservaciones.
4. **Lakehouse**: crear una tabla **Apache Iceberg** en tu propio bucket y leer un snapshot desde una tabla externa.
5. **Acelerar reportes**: precalcular resultados con una **Vista Materializada**.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Estimar el costo de una consulta con `bq query --dry_run` antes de ejecutarla.
2. Crear tablas **particionadas y clusterizadas** con `CREATE TABLE ... AS SELECT` y exigir filtros con `require_partition_filter`.
3. Limitar el gasto con `--maximum_bytes_billed` y auditar consumo con `INFORMATION_SCHEMA.JOBS_BY_USER`.
4. Crear una **conexión `CLOUD_RESOURCE`**, una tabla **Iceberg administrada** y una tabla **Iceberg externa** de solo lectura.
5. Crear una **Vista Materializada** y verificar que BigQuery reescribe automáticamente las consultas para usarla.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total medido en una corrida real: $0.00 USD dentro de la capa gratuita, o ~$0.11 USD si ya la agotaste.**

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia | Costo del Laboratorio |
| :--- | :--- | :--- | :--- |
| **Consultas BigQuery (on-demand)** | ~18 GB procesados (15 GB son la creación de las 2 tablas) | Primer **1 TiB/mes gratis**; luego $6.25 / TiB | **$0.00 USD** (máx. ~$0.11) |
| **Almacenamiento BigQuery** | 2 tablas de ~7.5 GB durante ~2 horas | Primeros **10 GiB/mes gratis**; luego ~$0.023 / GiB / mes | **< $0.01 USD** |
| **Cloud Storage** | Bucket `us-central1` con ~25 MB durante ~1 hora | Primeros 5 GB/mes gratis en Free Tier | **$0.00 USD** |
| **`EXPORT TABLE METADATA`** | 1 operación en slots Enterprise pay-as-you-go | $0.06 / slot-hora | **< $0.01 USD** |
| **Conexión** | 1 conexión `CLOUD_RESOURCE` | Sin costo | **$0.00 USD** |
| **TOTAL ESTIMADO** | **Ejecutando la limpieza al finalizar** | — | **~$0.00 a $0.11 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno (10 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables y habilita las APIs:

```bash
mkdir -p ~/workshop-gcp/lab09
cd ~/workshop-gcp/lab09

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export REGION="us-central1"
export BQ_LOCATION="US"
export DS_PRIVADO="lab09_privado"
export FUENTE="bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022"
export BUCKET_NAME="gs://${PROJECT_ID}-lakehouse-lab09"
export ICEBERG_URI="gs://${PROJECT_ID}-lakehouse-lab09/iceberg/viajes_enero"
export CONNECTION_ID="conn-lakehouse-lab09"
EOF

# bqsql: ejecuta SQL sin caché, con etiqueta y con un tope de 20 GB por consulta
cat >> env.sh << 'EOF'
bqsql() {
  local etiqueta="$1"; shift
  bq --location="$BQ_LOCATION" query --use_legacy_sql=false --nouse_cache \
    --label="lab09:${etiqueta}" --maximum_bytes_billed=20000000000 "$@"
}
EOF
source env.sh

gcloud config set project $PROJECT_ID

# Habilitar las APIs de BigQuery, sus conexiones y Cloud Storage
gcloud services enable \
  bigquery.googleapis.com \
  bigqueryconnection.googleapis.com \
  storage.googleapis.com

echo "Proyecto activo: $PROJECT_ID | BigQuery: $BQ_LOCATION | Bucket: $REGION"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab09 && source env.sh`

Ahora crea el dataset y el bucket:

```bash
# Dataset que alojará las tablas del laboratorio
bq --location=$BQ_LOCATION mk --dataset --description="Lab 09: datos internos" $PROJECT_ID:$DS_PRIVADO

# Bucket para Iceberg, sin borrado suave para no pagar por objetos eliminados
gcloud storage buckets create $BUCKET_NAME \
  --location=$REGION \
  --uniform-bucket-level-access \
  --soft-delete-duration=0

bq ls
```

> [!WARNING]
> **¿Por qué `US` y no `us-central1`?** Los datasets públicos de BigQuery están en la multirregión `US`, y una consulta no puede combinar datasets de ubicaciones distintas. Si creas tu dataset en `us-central1`, verás `Not found: Dataset ... was not found in location`. El bucket sí puede estar en `us-central1`, porque esa región forma parte de la multirregión US.

---

### Paso 2: Almacenamiento Columnar en la Práctica (10 min)

Trabajaremos con `tlc_yellow_trips_2022`: 36.2 millones de filas y 7.49 GB, sin particionar ni clusterizar. Es nuestra línea base.

#### 2.1. Estimar el Costo Antes de Ejecutar (`--dry_run`)
`--dry_run` no ejecuta la consulta ni cobra nada: solo informa cuántos bytes procesaría.

```bash
source env.sh

echo "--- A. SELECT * ---"
bq query --use_legacy_sql=false --dry_run "SELECT * FROM $FUENTE"

echo "--- B. SELECT * con LIMIT 10 ---"
bq query --use_legacy_sql=false --dry_run "SELECT * FROM $FUENTE LIMIT 10"

echo "--- C. Solo dos columnas ---"
bq query --use_legacy_sql=false --dry_run "SELECT payment_type, total_amount FROM $FUENTE"
```

Observa que **A y B procesan exactamente los mismos bytes** (7.49 GB): `LIMIT` recorta el resultado, no la lectura. En cambio, C lee solo dos columnas y procesa 0.69 GB, apenas un 9%. Eso es el almacenamiento columnar en acción.

#### 2.2. Ver la Caché de Resultados
Ejecuta dos veces la misma consulta, esta vez sin `--nouse_cache`, y mira si el job usó la caché:

```bash
SQL_CACHE="SELECT payment_type, COUNT(*) AS viajes FROM $FUENTE GROUP BY payment_type ORDER BY viajes DESC"

for intento in 1 2; do
  JOB="lab09_cache_${intento}_$(date +%s)"
  bq --location=$BQ_LOCATION query --use_legacy_sql=false --job_id=$JOB --label=lab09:paso2-cache "$SQL_CACHE" > /dev/null
  bq --format=json show -j $JOB | python3 -c "
import json, sys
s = json.load(sys.stdin)['statistics']['query']
print(f\"Intento $intento -> bytes facturados: {s['totalBytesBilled']} | caché: {s.get('cacheHit', False)}\")"
done
```

El segundo intento marca **0 bytes facturados** porque reutiliza el resultado. Por esta razón, desde aquí usaremos `bqsql`, que desactiva la caché y así mide costos reales.

---

### Paso 3: Particionamiento y Clusterización (20 min)

#### 3.1. Crear las Tablas Optimizadas
Crearemos dos copias de los datos de 2022:
- **`viajes_part`**: partición mensual por `pickup_datetime`.
- **`viajes_part_cluster`**: la misma partición, clusterizada por zona de origen y tipo de pago.

El filtro de fechas evita que los registros atípicos del dataset creen particiones fuera de 2022.

```bash
source env.sh

bqsql paso3-crear-part << SQL
CREATE OR REPLACE TABLE $DS_PRIVADO.viajes_part
PARTITION BY TIMESTAMP_TRUNC(pickup_datetime, MONTH)
OPTIONS (require_partition_filter = TRUE)
AS
SELECT * FROM $FUENTE
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01';
SQL

bqsql paso3-crear-cluster << SQL
CREATE OR REPLACE TABLE $DS_PRIVADO.viajes_part_cluster
PARTITION BY TIMESTAMP_TRUNC(pickup_datetime, MONTH)
CLUSTER BY pickup_location_id, payment_type
OPTIONS (require_partition_filter = TRUE)
AS
SELECT * FROM $FUENTE
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01';
SQL

# Inspeccionar las particiones creadas
bqsql paso3-particiones << SQL
SELECT partition_id, total_rows, ROUND(total_logical_bytes / POW(10, 6)) AS mb
FROM $DS_PRIVADO.INFORMATION_SCHEMA.PARTITIONS
WHERE table_name = 'viajes_part_cluster'
ORDER BY partition_id;
SQL
```

> [!NOTE]
> Elegimos partición **mensual** a propósito. Con particiones diarias tendríamos unos 330 trozos de 20 MB, y dentro de cada uno el clúster apenas podría descartar bloques. Verás 11 particiones de entre 500 y 760 MB y una casi vacía: el dataset público apenas trae 57 viajes de diciembre de 2022.

#### 3.2. Comparar la Misma Consulta en las Tres Tablas
Pregunta de negocio: **¿cuánto se facturó por tipo de pago en marzo de 2022 en los viajes que salieron del aeropuerto JFK (zona 132)?**

```bash
FILTRO="pickup_datetime >= '2022-03-01' AND pickup_datetime < '2022-04-01' AND pickup_location_id = '132'"
COLS="payment_type, COUNT(*) AS viajes, ROUND(SUM(total_amount), 2) AS ingresos_usd"

bqsql paso3-sin-optimizar << SQL
SELECT $COLS FROM $FUENTE WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC;
SQL

bqsql paso3-particionada << SQL
SELECT $COLS FROM $DS_PRIVADO.viajes_part WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC;
SQL

bqsql paso3-part-cluster << SQL
SELECT $COLS FROM $DS_PRIVADO.viajes_part_cluster WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC;
SQL
```

Las tres devuelven **el mismo resultado**. En el Paso 4 veremos cuántos bytes costó cada una.

#### 3.3. Probar la Protección `require_partition_filter`
Esta consulta **debe fallar** a propósito:

```bash
bqsql paso3-sin-filtro "SELECT COUNT(*) FROM $DS_PRIVADO.viajes_part WHERE pickup_location_id = '132'"
```

Verás un error similar a `Cannot query over table ... without a filter over column(s) 'pickup_datetime'`. Así, un analista distraído no puede escanear toda la tabla por accidente.

---

### Paso 4: FinOps — Topes de Gasto y Comparación de Modelos (15 min)

#### 4.1. Poner un Tope de Gasto (`--maximum_bytes_billed`)
Con un tope de 1 GB, esta consulta de varios GB **falla antes de cobrar**:

```bash
source env.sh

bq --location=$BQ_LOCATION query --use_legacy_sql=false --nouse_cache \
  --maximum_bytes_billed=1000000000 \
  "SELECT AVG(total_amount), AVG(trip_distance), AVG(fare_amount), AVG(tip_amount), AVG(tolls_amount), COUNT(DISTINCT pickup_location_id) FROM $FUENTE WHERE pickup_datetime IS NOT NULL"
```

Verás `Query exceeded limit for bytes billed`. En producción puedes fijar este límite en tus herramientas y añadir cuotas diarias por proyecto o usuario.

#### 4.2. Auditar el Consumo y Comparar Modelos
Todas nuestras consultas llevan la etiqueta `lab09`, así que podemos auditarlas con `INFORMATION_SCHEMA.JOBS_BY_USER`. Calcularemos para cada una dos costos:
- **On-demand**: bytes facturados × $6.25 por TiB.
- **Equivalente en slots**: `total_slot_ms` × $0.06 por slot-hora (Enterprise).

```bash
cat > costos.sql << 'SQL'
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'lab09') AS paso,
  ROUND(total_bytes_billed / POW(10, 9), 3) AS gb_facturados,
  ROUND(total_slot_ms / 1000, 1) AS slot_segundos,
  FORMAT('%.6f', total_bytes_billed / POW(1024, 4) * 6.25) AS usd_on_demand,
  FORMAT('%.6f', total_slot_ms / 3600000 * 0.06) AS usd_slots_enterprise
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_USER
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY' AND state = 'DONE' AND error_result IS NULL
  AND statement_type != 'SCRIPT'
  AND EXISTS (SELECT 1 FROM UNNEST(labels) WHERE key = 'lab09')
ORDER BY creation_time;
SQL

bq --location=$BQ_LOCATION query --use_legacy_sql=false --max_rows=50 < costos.sql
```

> [!NOTE]
> `INFORMATION_SCHEMA` puede tardar unos minutos en reflejar los jobs recientes. Si falta alguna fila, espera y vuelve a ejecutar: `bq --location=$BQ_LOCATION query --use_legacy_sql=false --max_rows=50 < costos.sql`

Busca las filas `paso3-sin-optimizar`, `paso3-particionada` y `paso3-part-cluster`, y responde:
1. ¿Cuántas veces menos bytes procesó la tabla particionada y clusterizada que la original?
2. ¿Qué etapa eliminó más datos: la partición o el clúster?
3. ¿Qué modelo sale más barato en cada fila, y por qué ese resultado es engañoso? (Lee la advertencia siguiente).

Resultados de referencia de una corrida real (Tus cifras de slots variarán; los bytes deben coincidir):

| Consulta | GB facturados | Reducción | On-demand | Slots (equivalente) |
| :--- | :--- | :--- | :--- | :--- |
| `paso3-sin-optimizar` | 1.154 | — | $0.00656 | $0.00005 |
| `paso3-particionada` | 0.116 | **10x** | $0.00066 | $0.00001 |
| `paso3-part-cluster` | 0.016 | **72x** | $0.00009 | $0.000002 |

La partición descarta 11 de los 12 meses; el clúster reduce 7 veces más lo que queda.

> [!CAUTION]
> `usd_slots_enterprise` es una **aproximación optimista**. Una reservación real cobra por los slots **escalados** (múltiplos de 50) y con un mínimo de 1 minuto, no por los slot-ms usados. Sirve para comparar órdenes de magnitud, no para predecir la factura.

---

### Paso 5: Lakehouse con Apache Iceberg (15 min)

Guardaremos los viajes de enero en **tu bucket, en formato abierto**, y los leeremos de dos maneras.

#### 5.1. Crear la Conexión y Darle Permisos
La conexión tiene su propia cuenta de servicio, que es quien accede al bucket:

```bash
source env.sh

bq mk --connection --location=$BQ_LOCATION --project_id=$PROJECT_ID \
  --connection_type=CLOUD_RESOURCE $CONNECTION_ID

CONNECTION_SA=$(bq --format=json show --connection $PROJECT_ID.$BQ_LOCATION.$CONNECTION_ID \
  | python3 -c "import json, sys; print(json.load(sys.stdin)['cloudResource']['serviceAccountId'])")
echo "export CONNECTION_SA=\"$CONNECTION_SA\"" >> env.sh
echo "Cuenta de servicio de la conexión: $CONNECTION_SA"

gcloud storage buckets add-iam-policy-binding $BUCKET_NAME \
  --member="serviceAccount:$CONNECTION_SA" --role="roles/storage.objectUser" > /dev/null
gcloud storage buckets add-iam-policy-binding $BUCKET_NAME \
  --member="serviceAccount:$CONNECTION_SA" --role="roles/storage.legacyBucketReader" > /dev/null
```

#### 5.2. Crear y Cargar la Tabla Iceberg Administrada
BigQuery administra la tabla, pero los archivos Parquet quedan en tu bucket. Como el permiso recién otorgado puede tardar en propagarse, reintentamos:

```bash
cat > crear_iceberg.sql << SQL
CREATE TABLE IF NOT EXISTS $DS_PRIVADO.viajes_iceberg (
  pickup_datetime TIMESTAMP,
  pickup_location_id STRING,
  payment_type STRING,
  trip_distance NUMERIC,
  total_amount NUMERIC
)
WITH CONNECTION \`$PROJECT_ID.$BQ_LOCATION.$CONNECTION_ID\`
OPTIONS (
  file_format = 'PARQUET',
  table_format = 'ICEBERG',
  storage_uri = '$ICEBERG_URI'
);
SQL

for i in $(seq 1 12); do
  bqsql paso5-crear-iceberg < crear_iceberg.sql && break
  echo "Intento $i: esperando la propagación de IAM, reintentando en 30 s..."; sleep 30
done

bqsql paso5-cargar-iceberg << SQL
INSERT INTO $DS_PRIVADO.viajes_iceberg
SELECT pickup_datetime, pickup_location_id, payment_type, trip_distance, total_amount
FROM $DS_PRIVADO.viajes_part_cluster
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2022-02-01';
SQL
```

#### 5.3. Publicar los Metadatos y Ver los Archivos
`EXPORT TABLE METADATA` escribe un snapshot Iceberg que cualquier otro motor puede leer:

```bash
bqsql paso5-exportar "EXPORT TABLE METADATA FROM $DS_PRIVADO.viajes_iceberg"

echo "--- Archivos en el bucket ---"
gcloud storage ls --recursive "$ICEBERG_URI/" | head -20
```

Verás una carpeta `data/` con archivos Parquet y una carpeta `metadata/`. En la consola (`☰` -> **Cloud Storage** -> **Buckets**) puedes navegar por ellas. **Míralos, pero no los modifiques**: alterar los archivos desde fuera de BigQuery puede corromper la tabla.

#### 5.4. Leer el Snapshot con una Tabla Externa Iceberg
Crearemos una tabla externa de **solo lectura** que apunta al archivo de metadatos:

```bash
METADATA_JSON=$(gcloud storage ls "$ICEBERG_URI/metadata/*.metadata.json" | sort -V | tail -n 1)
echo "Metadatos: $METADATA_JSON"

bqsql paso5-externa << SQL
CREATE OR REPLACE EXTERNAL TABLE $DS_PRIVADO.viajes_iceberg_ext
WITH CONNECTION \`$PROJECT_ID.$BQ_LOCATION.$CONNECTION_ID\`
OPTIONS (format = 'ICEBERG', uris = ['$METADATA_JSON']);
SQL

bqsql paso5-contar "SELECT
  (SELECT COUNT(*) FROM $DS_PRIVADO.viajes_iceberg) AS administrada,
  (SELECT COUNT(*) FROM $DS_PRIVADO.viajes_iceberg_ext) AS externa"
```

Ambas tienen las mismas filas: es **una sola copia** de los datos.

#### 5.5. Solo Lectura y Snapshots
Añadamos una fila a la tabla administrada e intentemos escribir en la externa (esto último **debe fallar**):

```bash
bqsql paso5-insertar "INSERT INTO $DS_PRIVADO.viajes_iceberg
  (pickup_datetime, pickup_location_id, payment_type, trip_distance, total_amount)
  VALUES (TIMESTAMP '2022-01-31 23:59:00', '132', '1', 10.5, 75.25)"

# Debe fallar: las tablas externas Iceberg no admiten DML
bqsql paso5-escribir-externa "DELETE FROM $DS_PRIVADO.viajes_iceberg_ext WHERE TRUE"

bqsql paso5-contar2 "SELECT
  (SELECT COUNT(*) FROM $DS_PRIVADO.viajes_iceberg) AS administrada,
  (SELECT COUNT(*) FROM $DS_PRIVADO.viajes_iceberg_ext) AS externa"
```

Ahora la externa tiene **una fila menos**: apunta a un snapshot fijo y debes actualizarla a mano. Por eso Google recomienda evitar este patrón en la mayoría de los casos (revisa la sección 7.2 de la teoría).

---

### Paso 6: Vista Materializada y Smart Tuning (10 min)

Gerencia ejecuta a diario un reporte de ingresos por mes y zona, que escanea datos cada vez.

#### 6.1. Medir el Reporte Antes de la Vista

```bash
source env.sh

cat > reporte.sql << SQL
SELECT TIMESTAMP_TRUNC(pickup_datetime, MONTH) AS mes, pickup_location_id,
  COUNT(*) AS viajes, SUM(total_amount) AS ingresos_usd
FROM $DS_PRIVADO.viajes_part_cluster
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01'
GROUP BY mes, pickup_location_id
SQL

bqsql paso6-antes --max_rows=3 < reporte.sql
```

#### 6.2. Crear la Vista Materializada

```bash
bqsql paso6-crear-mv << SQL
CREATE MATERIALIZED VIEW $DS_PRIVADO.mv_ingresos_zona
PARTITION BY TIMESTAMP_TRUNC(mes, MONTH)
OPTIONS (enable_refresh = TRUE, refresh_interval_minutes = 60)
AS
SELECT TIMESTAMP_TRUNC(pickup_datetime, MONTH) AS mes, pickup_location_id,
  COUNT(*) AS viajes, SUM(total_amount) AS ingresos_usd
FROM $DS_PRIVADO.viajes_part_cluster
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01'
GROUP BY mes, pickup_location_id;
SQL

# Forzar la primera actualización para no esperar al ciclo en segundo plano
bqsql paso6-refrescar "CALL BQ.REFRESH_MATERIALIZED_VIEW('$PROJECT_ID.$DS_PRIVADO.mv_ingresos_zona')"
```

#### 6.3. Repetir el Reporte sin Cambiar el SQL
Ejecutamos **exactamente el mismo archivo**, que sigue apuntando a la tabla base, y revisamos si BigQuery lo reescribió:

```bash
bqsql paso6-despues --max_rows=3 < reporte.sql

cat > mv_stats.sql << 'SQL'
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'lab09') AS paso,
  ROUND(total_bytes_billed / POW(10, 6), 1) AS mb_facturados,
  ARRAY(SELECT AS STRUCT m.table_reference.table_id AS vista, m.chosen
        FROM UNNEST(materialized_view_statistics.materialized_view) AS m) AS vistas_evaluadas
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_USER
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND EXISTS (SELECT 1 FROM UNNEST(labels) WHERE key = 'lab09' AND value IN ('paso6-antes', 'paso6-despues'))
ORDER BY creation_time;
SQL

bq --location=$BQ_LOCATION --format=prettyjson query --use_legacy_sql=false < mv_stats.sql
```

En `paso6-despues`, la vista aparece con `chosen: true` y los bytes bajan de **1,045 MB a 10.5 MB**, unas 100 veces menos: **el reporte se aceleró sin que nadie modificara su SQL**.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO!** Las tablas de BigQuery y los archivos de Cloud Storage cobran por almacenamiento mientras existan. Primero se elimina el dataset (y con él las tablas Iceberg) y después el bucket.

Ejecuta los siguientes comandos en **Cloud Shell**:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab09 && source env.sh

# 1. Eliminar el dataset con todas sus tablas y vistas
bq rm -r -f -d $PROJECT_ID:$DS_PRIVADO

# 2. Eliminar la conexión
bq rm -f --connection $PROJECT_ID.$BQ_LOCATION.$CONNECTION_ID

# 3. Eliminar el bucket y todos sus objetos
gcloud storage rm --recursive $BUCKET_NAME
```

### Auditoría Final de Limpieza
Verifica que no quede ningún recurso del laboratorio. Las tres secciones deben aparecer vacías:

```bash
echo "=== Dataset del Lab 09 ==="
bq ls | grep lab09

echo "=== Conexiones del Lab 09 ==="
bq ls --connection --location=$BQ_LOCATION | grep lab09

echo "=== Buckets del Lab 09 ==="
gcloud storage buckets list --format="value(name)" | grep lab09
```

---

## 6. Conclusiones

En este noveno laboratorio has diseñado un Data Warehouse midiendo cada decisión:
- Comprobaste que el **almacenamiento columnar** premia seleccionar pocas columnas, y que `LIMIT` no reduce los bytes.
- Con **partición y clúster** redujiste 72 veces los bytes de la misma consulta, y con `require_partition_filter` evitaste escaneos accidentales.
- Aplicaste **FinOps** con topes de gasto y auditoría en `INFORMATION_SCHEMA`, y comparaste on-demand con slots sin crear reservaciones.
- Creaste una tabla **Apache Iceberg** en tu propio bucket y entendiste la diferencia entre una tabla administrada y un snapshot externo de solo lectura.
- Aceleraste un reporte con una **Vista Materializada** sin tocar su SQL.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Reservación Enterprise Real**:
   Investiga `bq mk --reservation` con `--edition=ENTERPRISE`, `--slots=0` y `--autoscale_max_slots=50`, junto con `bq mk --reservation_assignment`. Ejecuta el reporte del Paso 6 con esa capacidad y compara `total_slot_ms` con lo que indica la facturación. **Elimina la asignación y la reservación al terminar**: cobran por slot-hora escalado.

2. **Reto 2 — Orden de las Columnas de Clúster**:
   Crea una tabla igual a `viajes_part_cluster`, pero con `CLUSTER BY payment_type, pickup_location_id`. Ejecuta la consulta del Paso 3.2 en ambas y explica la diferencia de bytes.

3. **Reto 3 — Expiración de Particiones**:
   Aplica `ALTER TABLE ... SET OPTIONS (partition_expiration_days = ...)` a una copia de `viajes_part` para que BigQuery borre datos antiguos. Calcula cuánto almacenamiento se ahorraría en un año.

---

## 8. Referencias Oficiales

- **Herramienta `bq`**: [https://docs.cloud.google.com/bigquery/docs/bq-command-line-tool](https://docs.cloud.google.com/bigquery/docs/bq-command-line-tool)
- **Estimar y Controlar Costos**: [https://docs.cloud.google.com/bigquery/docs/best-practices-costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)
- **Vista `INFORMATION_SCHEMA.JOBS`**: [https://docs.cloud.google.com/bigquery/docs/information-schema-jobs](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- **Tablas Iceberg Administradas**: [https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery](https://docs.cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery)
- **Tablas Externas Iceberg**: [https://docs.cloud.google.com/bigquery/docs/iceberg-external-tables](https://docs.cloud.google.com/bigquery/docs/iceberg-external-tables)
- **Vistas Materializadas**: [https://docs.cloud.google.com/bigquery/docs/materialized-views-intro](https://docs.cloud.google.com/bigquery/docs/materialized-views-intro)
- **Precios de BigQuery**: [https://cloud.google.com/bigquery/pricing](https://cloud.google.com/bigquery/pricing)
