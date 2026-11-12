# Laboratorio 09 (Versión Corta): Consultas sobre Grandes Volúmenes de Datos con BigQuery — Datasets, Tablas, Caché, Particionamiento y Clusterización

- **Duración estimada**: 35–40 minutos
- **Nivel**: Inicial / Analítica de Datos
- **Entorno de trabajo**: **Google Cloud Shell (`bq`, `python3`)** + Verificaciones visuales en **BigQuery Studio**

> [!NOTE]
> Esta es la versión corta del [Laboratorio 09 completo](./laboratorio.md). Se centra en consultar grandes volúmenes de datos y en las técnicas que abaratan esas consultas. Los temas de FinOps avanzado, Apache Iceberg y vistas materializadas solo están en la versión completa.

---

## 1. Objetivo del Laboratorio

Consultar en segundos **cientos de millones e incluso miles de millones de filas** sin aprovisionar un solo servidor, y comprobar con cifras reales qué hace que una consulta sea cara o barata en BigQuery.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Explorar **datasets y tablas** con `bq ls`, `bq show` y `bq head`.
2. Estimar el costo de una consulta con `--dry_run` antes de ejecutarla.
3. Ejecutar agregaciones sobre **213 millones de filas** y entender por qué solo pagas las columnas que lees.
4. Aprovechar la **caché de resultados** para repetir consultas sin costo.
5. Crear tablas **particionadas y clusterizadas** y medir cuántos bytes ahorran.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total medido en una corrida real: $0.00 USD dentro de la capa gratuita, o ~$0.14 USD si ya la agotaste.**

| Recurso | Especificación | Precio de Referencia | Costo del Laboratorio |
| :--- | :--- | :--- | :--- |
| **Consultas BigQuery (on-demand)** | ~24 GB procesados (15 GB son la creación de las 2 tablas) | Primer **1 TiB/mes gratis**; luego $6.25 / TiB | **$0.00 USD** (máx. ~$0.14) |
| **Almacenamiento BigQuery** | 2 tablas de ~7.5 GB durante menos de 1 hora | Primeros **10 GiB/mes gratis**; luego ~$0.023 / GiB / mes | **< $0.01 USD** |
| **TOTAL ESTIMADO** | **Ejecutando la limpieza al finalizar** | — | **~$0.00 a $0.14 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno (5 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables, habilita la API y crea tu dataset:

```bash
mkdir -p ~/workshop-gcp/lab09-corto
cd ~/workshop-gcp/lab09-corto

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export BQ_LOCATION="US"
export DATASET="lab09_corto"
export TAXIS_NY="bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022"
export TAXIS_CHICAGO="bigquery-public-data.chicago_taxi_trips.taxi_trips"
export WIKIPEDIA="bigquery-public-data.wikipedia.pageviews_2024"
EOF

# medir: ejecuta una consulta (tope de 20 GB) y muestra bytes facturados, costo, duración y caché
cat >> env.sh << 'EOF'
medir() {
  local etiqueta="$1"; shift
  local job="lab09c_${etiqueta//-/_}_$(date +%s)"
  bq --location="$BQ_LOCATION" query --use_legacy_sql=false --job_id="$job" \
    --label="lab09c:${etiqueta}" --maximum_bytes_billed=20000000000 "$@" || return 1
  bq --format=json show -j "$job" | python3 -c '
import json, sys
job = json.load(sys.stdin)
stats = job["statistics"]
gb = int(stats["query"].get("totalBytesBilled", 0)) / 1e9
usd = gb * 1e9 / 2**40 * 6.25
segundos = (int(stats["endTime"]) - int(stats["startTime"])) / 1000
cache = stats["query"].get("cacheHit", False)
print(f">> {gb:.3f} GB facturados | ~${usd:.4f} USD | {segundos:.1f} s | caché: {cache}")'
}
EOF
source env.sh

gcloud config set project $PROJECT_ID
gcloud services enable bigquery.googleapis.com

# Crear el dataset en la multirregión US, donde viven los datasets públicos
bq --location=$BQ_LOCATION mk --dataset --description="Lab 09 corto" $PROJECT_ID:$DATASET
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta, recupera tus variables con: `cd ~/workshop-gcp/lab09-corto && source env.sh`

> [!WARNING]
> **¿Por qué `US`?** Los datasets públicos de BigQuery están en la multirregión `US`, y una consulta no puede combinar datasets de ubicaciones distintas. Si creas tu dataset en `us-central1`, el Paso 5 fallará con `Not found: Dataset ... was not found in location`.

---

### Paso 2: Datasets y Tablas — Explorar sin Gastar (7 min)

En BigQuery, los datos se organizan en **proyecto → dataset → tabla**. Un **dataset** es un contenedor con una ubicación fija (por ejemplo `US`) y sus propios permisos. Una **tabla** guarda los datos en formato columnar.

Google publica cientos de datasets abiertos en el proyecto `bigquery-public-data`. Exploremos tres tablas:

```bash
source env.sh

# Algunas tablas del dataset público de taxis de Nueva York
bq ls --max_results=5 bigquery-public-data:new_york_taxi_trips

# Script que resume el tamaño, las filas, la partición y el clúster de una tabla
cat > info_tabla.py << 'EOF'
import json, sys
t = json.load(sys.stdin)
ref = t["tableReference"]
particion = t.get("timePartitioning", {}).get("field", "ninguna")
cluster = t.get("clustering", {}).get("fields", "ninguno")
print(f"{ref['datasetId']}.{ref['tableId']}")
print(f"   filas: {int(t['numRows']):,} | tamaño: {int(t['numBytes']) / 1e9:,.1f} GB")
print(f"   partición: {particion} | clúster: {cluster}")
EOF

for TABLA in $TAXIS_NY $TAXIS_CHICAGO $WIKIPEDIA; do
  bq --format=json show "${TABLA/./:}" | python3 info_tabla.py
done
```

Verás una tabla de 36 millones de filas, otra de **213 millones** y otra de **más de 58 mil millones de filas (2.66 TB)**. Fíjate en que la de Wikipedia ya está particionada y clusterizada: volveremos a ella en el Paso 5.

Ahora mira el esquema y una muestra de datos:

```bash
# Esquema: nombre y tipo de cada columna
bq show --schema --format=prettyjson "${TAXIS_CHICAGO/./:}" | head -30

# Vista previa de 5 filas de algunas columnas: GRATIS, no ejecuta ninguna consulta
bq head -n 5 --selected_fields=trip_start_timestamp,trip_miles,trip_total,payment_type,company \
  "${TAXIS_CHICAGO/./:}"
```

> [!TIP]
> **`bq head` y la pestaña *Vista previa* de la consola son gratuitas**: leen las filas directamente del almacenamiento sin lanzar una consulta. En cambio, `SELECT * ... LIMIT 5` sí se cobra completo, como verás en el siguiente paso.

---

### Paso 3: Consultas sobre Grandes Volúmenes de Datos (10 min)

#### 3.1. Estimar Antes de Ejecutar (`--dry_run`)
`--dry_run` valida la consulta y calcula los bytes que procesaría, **sin ejecutarla ni cobrar nada**:

```bash
source env.sh

echo "--- A. SELECT * sobre 213 millones de viajes ---"
bq query --use_legacy_sql=false --dry_run "SELECT * FROM $TAXIS_CHICAGO"

echo "--- B. El mismo SELECT * con LIMIT 5 ---"
bq query --use_legacy_sql=false --dry_run "SELECT * FROM $TAXIS_CHICAGO LIMIT 5"

echo "--- C. Solo las dos columnas que necesitamos ---"
bq query --use_legacy_sql=false --dry_run \
  "SELECT trip_start_timestamp, trip_total FROM $TAXIS_CHICAGO"

echo "--- D. Contar filas ---"
bq query --use_legacy_sql=false --dry_run "SELECT COUNT(*) FROM $TAXIS_CHICAGO"
```

| Consulta | Bytes | Costo on-demand | Por qué |
| :--- | :--- | :--- | :--- |
| A. `SELECT *` | ~83 GB | ~$0.47 | Lee las 23 columnas completas |
| B. `SELECT * ... LIMIT 5` | ~83 GB | ~$0.47 | `LIMIT` recorta el resultado, **no la lectura** |
| C. Dos columnas | ~3.4 GB | ~$0.02 | **Almacenamiento columnar**: solo lee esas columnas |
| D. `COUNT(*)` | 0 bytes | $0.00 | Se responde con los metadatos de la tabla |

**No ejecutes A ni B**: con el dry run ya sabemos lo que costarían.

#### 3.2. Agregar 213 Millones de Filas en Segundos
Ahora sí ejecutamos una consulta real: viajes e importe promedio por año en Chicago.

```bash
cat > chicago.sql << SQL
SELECT
  EXTRACT(YEAR FROM trip_start_timestamp) AS anio,
  COUNT(*) AS viajes,
  ROUND(AVG(trip_total), 2) AS importe_promedio_usd
FROM $TAXIS_CHICAGO
GROUP BY anio
ORDER BY anio
SQL

medir chicago --nouse_cache --max_rows=20 < chicago.sql
```

BigQuery reparte el trabajo entre cientos de **slots** en paralelo: en la corrida de referencia procesó los 213 millones de filas (3.4 GB, unos $0.02) en **menos de un segundo de ejecución**, sin que hubiera que aprovisionar ningún servidor. En la línea `>>` verás los GB facturados, el costo y la duración.

---

### Paso 4: Caché de Resultados (3 min)

Ejecuta **la misma consulta dos veces más**, ahora con la caché activa (es el comportamiento predeterminado):

```bash
source env.sh

medir chicago-cache-1 --max_rows=3 < chicago.sql
medir chicago-cache-2 --max_rows=3 < chicago.sql
```

Como el Paso 3.2 se ejecutó con `--nouse_cache`, la primera ejecución vuelve a leer los 3.4 GB y guarda el resultado. La segunda muestra **`caché: True`**, **0 GB facturados** y un tiempo mucho menor. BigQuery guarda los resultados unas **24 horas** y los reutiliza si la consulta es idéntica y las tablas no cambiaron.

> [!NOTE]
> La caché no se usa si cambias aunque sea un espacio en el SQL, si la consulta usa funciones no deterministas como `CURRENT_TIMESTAMP()` o si las tablas cambiaron. Para medir costos reales, como en el resto de este laboratorio, se desactiva con `--nouse_cache`.

---

### Paso 5: Particionamiento y Clusterización (12 min)

#### 5.1. Crear Tus Propias Tablas Optimizadas
`tlc_yellow_trips_2022` (7.49 GB) no está particionada ni clusterizada. Crearemos dos copias con los datos de 2022:
- **`viajes_part`**: partición mensual por fecha de inicio del viaje.
- **`viajes_part_cluster`**: la misma partición, clusterizada además por zona de origen y tipo de pago.

```bash
source env.sh

medir crear-part --nouse_cache << SQL
CREATE OR REPLACE TABLE $DATASET.viajes_part
PARTITION BY TIMESTAMP_TRUNC(pickup_datetime, MONTH)
OPTIONS (require_partition_filter = TRUE)
AS SELECT * FROM $TAXIS_NY
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01';
SQL

medir crear-cluster --nouse_cache << SQL
CREATE OR REPLACE TABLE $DATASET.viajes_part_cluster
PARTITION BY TIMESTAMP_TRUNC(pickup_datetime, MONTH)
CLUSTER BY pickup_location_id, payment_type
OPTIONS (require_partition_filter = TRUE)
AS SELECT * FROM $TAXIS_NY
WHERE pickup_datetime >= '2022-01-01' AND pickup_datetime < '2023-01-01';
SQL

bq ls $DATASET
```

Cada creación lee la tabla completa (unos 7.5 GB). Es el costo único de reorganizar los datos para que las consultas futuras salgan baratas.

#### 5.2. La Misma Consulta en Tres Tablas
Pregunta de negocio: **¿cuánto se facturó por tipo de pago en marzo de 2022 en los viajes que salieron del aeropuerto JFK (zona 132)?**

```bash
FILTRO="pickup_datetime >= '2022-03-01' AND pickup_datetime < '2022-04-01' AND pickup_location_id = '132'"
COLS="payment_type, COUNT(*) AS viajes, ROUND(SUM(total_amount), 2) AS ingresos_usd"

echo "=== 1. Tabla original (sin optimizar) ==="
medir sin-optimizar --nouse_cache "SELECT $COLS FROM $TAXIS_NY WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC"

echo "=== 2. Tabla particionada ==="
medir particionada --nouse_cache "SELECT $COLS FROM $DATASET.viajes_part WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC"

echo "=== 3. Tabla particionada y clusterizada ==="
medir part-cluster --nouse_cache "SELECT $COLS FROM $DATASET.viajes_part_cluster WHERE $FILTRO GROUP BY payment_type ORDER BY viajes DESC"
```

Las tres devuelven **el mismo resultado**, pero compara las líneas `>>`:

| Tabla | GB facturados (referencia) | Reducción |
| :--- | :--- | :--- |
| Original | ~1.154 | — |
| Particionada | ~0.116 | **10x**: solo lee la partición de marzo |
| Particionada + clúster | ~0.02 | **más de 60x**: dentro de marzo, solo lee los bloques de la zona 132 |

#### 5.3. La Protección `require_partition_filter`
Esta consulta **debe fallar** a propósito, porque no filtra por fecha:

```bash
medir sin-filtro --nouse_cache "SELECT COUNT(*) FROM $DATASET.viajes_part WHERE pickup_location_id = '132'"
```

Verás `Cannot query over table ... without a filter over column(s) 'pickup_datetime'`. Así nadie puede escanear la tabla completa por accidente.

#### 5.4. A Escala de Google: 58 Mil Millones de Filas
La tabla de Wikipedia (2.66 TB) está particionada por día (`datehour`) y clusterizada por `wiki` y `title`. Veamos las páginas más visitadas de la Wikipedia en español durante un día:

```bash
cat > wikipedia.sql << SQL
SELECT title, SUM(views) AS visitas
FROM $WIKIPEDIA
WHERE datehour >= '2024-06-01' AND datehour < '2024-06-02'
  AND wiki = 'es'
GROUP BY title
ORDER BY visitas DESC
LIMIT 10
SQL

echo "--- Estimación (dry run) ---"
bq query --use_legacy_sql=false --dry_run < wikipedia.sql

echo "--- Ejecución real ---"
medir wikipedia --nouse_cache < wikipedia.sql
```

Observa dos cosas:
1. El dry run habla de un **"upper bound"**: en tablas clusterizadas, BigQuery solo puede calcular un **máximo**, porque no sabe cuántos bloques descartará hasta ejecutar la consulta. Los bytes reales pueden ser menores, nunca mayores.
2. De 2.66 TB, la consulta lee unos **0.21 GB (menos del 0.01%)** y responde en alrededor de un segundo: la partición elimina 365 de 366 días, y el clúster deja fuera todos los idiomas excepto el español.
3. ¿Por qué aparecen el *Borussia Dortmund*, el *Real Madrid* y la *Liga de Campeones*? El 1 de junio de 2024 se jugó la final de la Champions League entre ambos equipos.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO!** Tus dos tablas ocupan unos 15 GB y cobran almacenamiento mientras existan. Las tablas públicas no son tuyas y no generan ningún costo de almacenamiento.

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab09-corto && source env.sh

# 1. Eliminar el dataset con todas sus tablas
bq rm -r -f -d $PROJECT_ID:$DATASET
```

### Auditoría Final de Limpieza
Este comando no debe mostrar nada:

```bash
bq ls | grep lab09_corto
```

---

## 6. Conclusiones

- Exploraste **datasets y tablas**, y aprendiste que `bq head` y la vista previa son gratuitas.
- Comprobaste que en BigQuery **pagas por las columnas que lees**: `SELECT *` sobre 213 millones de filas cuesta 25 veces más que leer dos columnas, y `LIMIT` no lo arregla.
- Agregaste **213 millones de filas en segundos** sin aprovisionar servidores.
- Viste que la **caché** repite una consulta idéntica gratis.
- Con **partición y clúster** redujiste más de 60 veces los bytes de una consulta, y consultaste una tabla de 2.66 TB leyendo solo una fracción mínima.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Tu Propia Pregunta a Wikipedia**: modifica `wikipedia.sql` para buscar las páginas más vistas en otro idioma (`wiki = 'en'`, `'pt'`, `'fr'`) o en otro día. Ejecuta siempre primero el dry run.
2. **Reto 2 — El Orden del Clúster Importa**: crea una tabla igual a `viajes_part_cluster` pero con `CLUSTER BY payment_type, pickup_location_id` y repite la consulta del Paso 5.2. ¿Cambian los bytes? ¿Por qué?
3. **Reto 3 — Explora en BigQuery Studio**: en la consola ve a `☰` -> **BigQuery** -> **Studio**, pega `chicago.sql` en el editor y observa la estimación de bytes en la esquina superior derecha antes de ejecutarla.

---

## 8. Referencias Oficiales

- **Herramienta `bq`**: [https://docs.cloud.google.com/bigquery/docs/bq-command-line-tool](https://docs.cloud.google.com/bigquery/docs/bq-command-line-tool)
- **Datasets Públicos de BigQuery**: [https://docs.cloud.google.com/bigquery/public-data](https://docs.cloud.google.com/bigquery/public-data)
- **Resultados en Caché**: [https://docs.cloud.google.com/bigquery/docs/cached-results](https://docs.cloud.google.com/bigquery/docs/cached-results)
- **Tablas Particionadas**: [https://docs.cloud.google.com/bigquery/docs/partitioned-tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables)
- **Tablas Clusterizadas**: [https://docs.cloud.google.com/bigquery/docs/clustered-tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables)
- **Estimar y Controlar Costos**: [https://docs.cloud.google.com/bigquery/docs/best-practices-costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)
- **Precios de BigQuery**: [https://cloud.google.com/bigquery/pricing](https://cloud.google.com/bigquery/pricing)
