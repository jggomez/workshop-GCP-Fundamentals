# Laboratorio 11: Machine Learning con SQL — BigQuery ML, Model Registry y AutoML en Vertex AI

- **Duración estimada**: 90 minutos
- **Nivel**: Intermedio / Machine Learning para Ingenieros de Datos
- **Entorno de trabajo**: **Google Cloud Shell (`bq`, `gcloud`, `curl`)** + Verificaciones visuales en las consolas de **BigQuery** y **Agent Platform (antes Vertex AI)**

---

## 1. Objetivo del Laboratorio

Entrenar, evaluar y usar modelos de Machine Learning **sin sacar los datos de BigQuery y sin escribir Python**, solo con SQL. Construirás tres modelos sobre datos públicos:
1. Una **regresión** que estima la masa de un pingüino a partir de sus medidas.
2. Una **clasificación** que predice si una persona gana más de 50,000 USD al año (datos del censo de EE. UU.). Este modelo se **registra automáticamente en el Model Registry** de Vertex AI, con versiones y alias.
3. Un **clustering** que agrupa pingüinos sin conocer su especie… y la descubre solo.

Al final prepararás un entrenamiento de **AutoML** sin código desde la consola, deteniéndote justo antes de lanzarlo, para entender qué automatiza y cuánto cuesta.

```text
[bigquery-public-data.ml_datasets]
        │  CREATE TABLE ... AS SELECT
        ▼
[BigQuery: dataset lab11_ml] ──► CREATE MODEL (LINEAR_REG | LOGISTIC_REG | KMEANS)
        │                               │
        │                               ├──► ML.EVALUATE / ML.PREDICT / ML.EXPLAIN_PREDICT
        │                               └──► MODEL_REGISTRY='VERTEX_AI' ──► [Model Registry: v1, v2]
        ▼
[Agent Platform: dataset tabular] ──► AutoML (configurado, NO lanzado)
```

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Preparar datos para ML en SQL, con una **división reproducible** entre entrenamiento y prueba.
2. Entrenar modelos de **regresión, clasificación y clustering** con `CREATE MODEL`.
3. Evaluar un modelo con las métricas correctas para su tipo (**R², MAE, precisión, recall, AUC**) y leer una **matriz de confusión**.
4. Usar la cláusula **`TRANSFORM`** para que el preprocesamiento viaje dentro del modelo y sea idéntico al entrenar y al predecir.
5. **Explicar** las predicciones con `ML.EXPLAIN_PREDICT` y `ML.GLOBAL_EXPLAIN`.
6. Registrar un modelo de BigQuery ML en el **Model Registry** y gestionar **versiones y alias**.
7. Configurar un entrenamiento de **AutoML tabular** y estimar su costo antes de lanzarlo.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado: menos de $0.05 USD.** Los datos son pequeños y cada consulta se cobra con un mínimo de 10 MB. **No lances el entrenamiento de AutoML** (costaría unos $21 USD por nodo-hora).

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia (US) | Costo del Laboratorio |
| :--- | :--- | :--- | :--- |
| **BigQuery ML: entrenamiento** | 4 modelos internos (lineal, logístico y k-means) sobre datos de KB a 5 MB | $312.50 / TiB procesado (mínimo 10 MB por consulta) | **~$0.02 USD** (medido: $0.015) |
| **BigQuery ML: evaluar y predecir** | Unas 15 consultas `ML.*` | $6.25 / TiB (dentro del **1 TiB gratis** al mes) | **$0.00 USD** |
| **BigQuery: almacenamiento** | 1 tabla de ~4 MB durante 1 hora | Primeros 10 GiB al mes gratis | **$0.00 USD** |
| **Model Registry** | 1 modelo con 2 versiones, sin desplegar | La página de precios no lista un cargo por registrar; se cobra al desplegar un endpoint | **$0.00 USD** |
| **Agent Platform: dataset tabular** | Metadatos que apuntan a la tabla de BigQuery | Sin costo de creación | **$0.00 USD** |
| **AutoML tabular** | **Solo se configura, no se lanza** | $21.252 / nodo-hora (1 a 3 h sugeridas para < 100,000 filas) | **$0.00 USD** |
| **TOTAL ESTIMADO** | **Ejecutando la limpieza al finalizar** | — | **< $0.05 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparar el Entorno (10 min)

#### 1.1. Variables y APIs
1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables y habilita las APIs:

```bash
mkdir -p ~/workshop-gcp/lab11
cd ~/workshop-gcp/lab11

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
export DATASET="lab11_ml"
export MODELO_REGISTRY="clasificador-ingresos-lab11"
export DATASET_AUTOML="census_lab11"
EOF
source env.sh

gcloud services enable bigquery.googleapis.com aiplatform.googleapis.com
```

> [!NOTE]
> **¿Por qué `US` y no `us-central1`?** Los datos públicos que usaremos viven en la multirregión `US` y BigQuery no permite consultar entre ubicaciones distintas (Módulo 09). Los modelos de BigQuery quedan en `US`; el **Model Registry** y AutoML usan una región concreta, `us-central1`.

#### 1.2. Crear el Dataset

```bash
source env.sh
bq mk --location=$BQ_LOCATION --dataset \
  --description="Laboratorio 11: Machine Learning con BigQuery ML" $PROJECT_ID:$DATASET
```

---

### Paso 2: Preparar los Datos del Censo (10 min)

Usaremos `census_adult_income`: 32,561 personas con su edad, educación, ocupación, horas de trabajo y si ganan más de 50,000 USD al año. Crearemos una copia limpia con:
- Nombres de columna en español y textos sin espacios sobrantes (el original trae `" Private"`).
- La etiqueta como booleano: `gana_mas_50k`.
- Una columna `particion` **reproducible**: un *hash* de cada fila decide si va a `ENTRENAMIENTO` (80%) o a `PRUEBA` (20%). Con `RAND()` cada ejecución daría una división distinta y no podrías comparar modelos.

```bash
source env.sh

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`$PROJECT_ID.$DATASET.census\` AS
SELECT
  age AS edad,
  TRIM(workclass) AS tipo_empleo,
  TRIM(education) AS educacion,
  TRIM(marital_status) AS estado_civil,
  TRIM(occupation) AS ocupacion,
  TRIM(relationship) AS relacion,
  TRIM(sex) AS sexo,
  hours_per_week AS horas_semana,
  capital_gain AS ganancia_capital,
  capital_loss AS perdida_capital,
  TRIM(income_bracket) = '>50K' AS gana_mas_50k,
  IF(MOD(ABS(FARM_FINGERPRINT(TO_JSON_STRING(t))), 10) < 8, 'ENTRENAMIENTO', 'PRUEBA') AS particion
FROM \`bigquery-public-data.ml_datasets.census_adult_income\` AS t"

bq query --use_legacy_sql=false "
SELECT particion, COUNT(*) AS personas, ROUND(AVG(IF(gana_mas_50k, 1, 0)) * 100, 1) AS pct_mas_50k
FROM \`$PROJECT_ID.$DATASET.census\`
GROUP BY particion ORDER BY particion"
```

Observa que solo **~24%** gana más de 50K: las clases están **desbalanceadas**. Un modelo "tonto" que siempre diga `false` acertaría el 76% de las veces; por eso en el Paso 4 no basta con mirar la exactitud (*accuracy*).

---

### Paso 3: Regresión — Estimar la Masa de un Pingüino (15 min)

Una **regresión** predice un **número**. Usaremos `penguins` (344 pingüinos de la Antártida) para estimar `body_mass_g` a partir de la especie, la isla, el sexo y tres medidas del cuerpo.

#### 3.1. Entrenar el Modelo

```bash
source env.sh

bq query --use_legacy_sql=false "
CREATE OR REPLACE MODEL \`$PROJECT_ID.$DATASET.masa_pinguinos\`
OPTIONS(model_type = 'LINEAR_REG', input_label_cols = ['body_mass_g']) AS
SELECT species, island, sex, culmen_length_mm, culmen_depth_mm, flipper_length_mm, body_mass_g
FROM \`bigquery-public-data.ml_datasets.penguins\`
WHERE body_mass_g IS NOT NULL"
```

Toma unos 30 a 60 segundos. Las columnas de texto (`species`, `island`, `sex`) se convierten solas a variables numéricas (*one-hot encoding*) y los valores nulos se imputan solos: es el **preprocesamiento automático** de BigQuery ML. Por eso verás el aviso `The input data has NULL values in one or more columns: sex`: es informativo, no un error.

#### 3.2. Evaluar y Ver lo que Aprendió

```bash
source env.sh

# Métricas de regresión
bq query --use_legacy_sql=false "
SELECT ROUND(mean_absolute_error, 1) AS mae_gramos, ROUND(r2_score, 3) AS r2
FROM ML.EVALUATE(MODEL \`$PROJECT_ID.$DATASET.masa_pinguinos\`)"

# Pesos de las variables numéricas: cuántos gramos suma cada milímetro
bq query --use_legacy_sql=false "
SELECT processed_input AS variable, ROUND(weight, 2) AS gramos_por_unidad
FROM ML.WEIGHTS(MODEL \`$PROJECT_ID.$DATASET.masa_pinguinos\`)
WHERE weight IS NOT NULL
ORDER BY ABS(weight) DESC"
```

- **MAE** (*Mean Absolute Error*): el error promedio en gramos. Un MAE de ~230 g sobre pingüinos de 3,000 a 6,000 g es un error de alrededor del 5%.
- **R²**: qué proporción de la variación de la masa explica el modelo (1.0 sería perfecto). Un valor cercano a 0.87 es muy bueno para un modelo tan simple.
- Los **pesos** se leen en unidades reales: en la corrida de prueba, cada milímetro de aleta sumó ~16 g y cada milímetro de profundidad del pico ~70 g. `__INTERCEPT__` es el punto de partida antes de sumar las variables.

> [!NOTE]
> Con menos de 500 filas, BigQuery ML no separa datos de evaluación (`data_split_method = 'AUTO_SPLIT'`), así que estas métricas son **sobre los datos de entrenamiento** y tienden a ser optimistas. En el Paso 4 lo haremos bien, con una partición de prueba.

#### 3.3. Predecir

```bash
source env.sh

bq query --use_legacy_sql=false "
SELECT ROUND(predicted_body_mass_g) AS masa_estimada_g
FROM ML.PREDICT(MODEL \`$PROJECT_ID.$DATASET.masa_pinguinos\`, (
  SELECT 'Gentoo penguin (Pygoscelis papua)' AS species, 'Biscoe' AS island, 'MALE' AS sex,
         49.0 AS culmen_length_mm, 15.5 AS culmen_depth_mm, 225.0 AS flipper_length_mm))"
```

Predecir es un `SELECT`: lo puedes usar en una vista, en un dashboard o en una consulta programada.

---

### Paso 4: Clasificación Registrada en el Model Registry (20 min)

Una **clasificación** predice una **categoría**, aquí `true` o `false`: ¿gana más de 50K? Este modelo tiene dos novedades:
- **`TRANSFORM`**: el preprocesamiento queda **dentro del modelo**. Agrupar la edad en 5 rangos (`ML.QUANTILE_BUCKETIZE`) y estandarizar las horas (`ML.STANDARD_SCALER`) se aplicará **igual** al entrenar y al predecir, sin que quien consume el modelo tenga que repetirlo. Esto evita el error más común en producción: el *training-serving skew* (ver la teoría, sección de Feature Store).
- **`MODEL_REGISTRY = 'VERTEX_AI'`**: al terminar el entrenamiento, el modelo aparece en el **Model Registry** de Vertex AI como la versión 1, con el alias `v1`.

#### 4.1. Entrenar y Registrar la Versión 1

```bash
source env.sh

bq query --use_legacy_sql=false "
CREATE OR REPLACE MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`
TRANSFORM(
  ML.QUANTILE_BUCKETIZE(edad, 5) OVER() AS rango_edad,
  ML.STANDARD_SCALER(horas_semana) OVER() AS horas_semana_std,
  * EXCEPT(edad, horas_semana)
)
OPTIONS(
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['gana_mas_50k'],
  data_split_method = 'NO_SPLIT',
  enable_global_explain = TRUE,
  model_registry = 'VERTEX_AI',
  vertex_ai_model_id = '$MODELO_REGISTRY',
  vertex_ai_model_version_aliases = ['v1']
) AS
SELECT * EXCEPT(particion, relacion, perdida_capital)
FROM \`$PROJECT_ID.$DATASET.census\`
WHERE particion = 'ENTRENAMIENTO'"
```

Usamos `data_split_method = 'NO_SPLIT'` porque **nosotros** ya separamos los datos: el modelo nunca ve la partición `PRUEBA`.

#### 4.2. Evaluar con Datos que el Modelo Nunca Vio

```bash
source env.sh

bq query --use_legacy_sql=false "
SELECT ROUND(precision, 3) AS precision, ROUND(recall, 3) AS recall,
       ROUND(accuracy, 3) AS exactitud, ROUND(f1_score, 3) AS f1, ROUND(roc_auc, 3) AS auc
FROM ML.EVALUATE(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`,
  (SELECT * FROM \`$PROJECT_ID.$DATASET.census\` WHERE particion = 'PRUEBA'))"

bq query --use_legacy_sql=false "
SELECT * FROM ML.CONFUSION_MATRIX(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`,
  (SELECT * FROM \`$PROJECT_ID.$DATASET.census\` WHERE particion = 'PRUEBA'))"
```

| Métrica | Pregunta que responde |
| :--- | :--- |
| **Precisión** | De los que el modelo dijo "gana más de 50K", ¿cuántos realmente ganan más? |
| **Recall** | De todos los que realmente ganan más de 50K, ¿a cuántos encontró? |
| **AUC** | ¿Qué tan bien ordena a las personas por probabilidad, sin importar el umbral? (0.5 = azar, 1.0 = perfecto) |

En la matriz de confusión, las filas son la realidad (`expected_label`) y las columnas, la predicción; la diagonal son los aciertos. Fíjate en la fila `true`: en la corrida de prueba el modelo **se perdió** a 719 de las 1,539 personas que sí ganan más de 50K (recall de 0.53), consecuencia del desbalance de clases. Aun así, el AUC de ~0.90 indica que **ordena** muy bien a las personas por probabilidad.

#### 4.3. Mover el Umbral de Decisión
Por defecto, el modelo dice `true` si la probabilidad es mayor a 0.5. Si para el negocio es más grave **perder** a un cliente de altos ingresos que molestar a uno que no lo es, puedes bajar el umbral:

```bash
source env.sh

bq query --use_legacy_sql=false "
SELECT * FROM ML.CONFUSION_MATRIX(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`,
  (SELECT * FROM \`$PROJECT_ID.$DATASET.census\` WHERE particion = 'PRUEBA'),
  STRUCT(0.3 AS threshold))"
```

Compara con la matriz anterior: en la corrida de prueba los aciertos de la fila `true` subieron de 820 a 1,205 (recall de 0.53 a 0.78), a cambio de que los falsos positivos pasaran de 286 a 772 (precisión de 0.74 a 0.61). **El umbral es una decisión de negocio, no técnica.**

#### 4.4. Predecir y Explicar
Dos personas nuevas. `ML.EXPLAIN_PREDICT` devuelve, además de la predicción, **qué variables pesaron más** en cada caso:

```bash
source env.sh

bq query --use_legacy_sql=false "
SELECT persona, predicted_gana_mas_50k AS prediccion, ROUND(probability, 3) AS probabilidad,
  (SELECT STRING_AGG(f.feature || ' (' || CAST(ROUND(f.attribution, 2) AS STRING) || ')', ', ')
   FROM UNNEST(top_feature_attributions) AS f) AS variables_que_mas_influyeron
FROM ML.EXPLAIN_PREDICT(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`, (
  SELECT 'Ana' AS persona, 45 AS edad, 'Private' AS tipo_empleo, 'Masters' AS educacion,
         'Married-civ-spouse' AS estado_civil, 'Exec-managerial' AS ocupacion, 'Female' AS sexo,
         50 AS horas_semana, 5000 AS ganancia_capital
  UNION ALL
  SELECT 'Luis', 22, 'Private', 'HS-grad', 'Never-married', 'Handlers-cleaners', 'Male', 30, 0),
  STRUCT(3 AS top_k_features))"

# Importancia global: qué variables pesan más en TODO el modelo
bq query --use_legacy_sql=false "
SELECT feature AS variable, ROUND(attribution, 3) AS importancia
FROM ML.GLOBAL_EXPLAIN(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`)
ORDER BY attribution DESC LIMIT 6"
```

Observa:
- Para predecir pasamos `edad` y `horas_semana` **crudas**: el modelo aplica solo su `TRANSFORM`. En las explicaciones aparecen `rango_edad` y `horas_semana_std`, las variables transformadas.
- `probabilidad` es la confianza en la clase predicha. La explicabilidad es clave en dominios regulados (crédito, seguros, salud): hay que poder justificar **por qué** el modelo decidió algo.

---

### Paso 5: Clustering — Descubrir Especies sin Etiquetas (10 min)

**K-means** es aprendizaje **no supervisado**: no le damos la respuesta. Le pedimos que agrupe a los pingüinos en 3 grupos usando solo sus 4 medidas, y luego comparamos los grupos con la especie real, que el modelo **nunca vio**.

```bash
source env.sh

bq query --use_legacy_sql=false "
CREATE OR REPLACE MODEL \`$PROJECT_ID.$DATASET.grupos_pinguinos\`
OPTIONS(model_type = 'KMEANS', num_clusters = 3, standardize_features = TRUE) AS
SELECT culmen_length_mm, culmen_depth_mm, flipper_length_mm, body_mass_g
FROM \`bigquery-public-data.ml_datasets.penguins\`
WHERE body_mass_g IS NOT NULL"

bq query --use_legacy_sql=false "
SELECT CENTROID_ID AS grupo, REGEXP_EXTRACT(species, r'^\w+') AS especie_real, COUNT(*) AS pinguinos
FROM ML.PREDICT(MODEL \`$PROJECT_ID.$DATASET.grupos_pinguinos\`,
  (SELECT * FROM \`bigquery-public-data.ml_datasets.penguins\` WHERE body_mass_g IS NOT NULL))
GROUP BY grupo, especie_real
ORDER BY grupo, pinguinos DESC"
```

Uno de los grupos debería contener prácticamente solo **Gentoo** (los más grandes y de aleta más larga). Adelie y Chinstrap se parecen más en tamaño y se mezclan un poco. Con `standardize_features = TRUE` todas las medidas pesan lo mismo; sin ello, los gramos dominarían a los milímetros. En un negocio, este mismo patrón sirve para **segmentar clientes**.

---

### Paso 6: Model Registry — Versiones y Alias (10 min)

#### 6.1. Ver el Modelo Registrado

```bash
source env.sh

gcloud ai models list --region=$REGION --filter="displayName=$MODELO_REGISTRY" \
  --format="table(name.basename(), displayName, versionId, versionAliases.list())"
```

El modelo que entrenaste con SQL ya es un recurso de Vertex AI: desde aquí se podría **desplegar en un endpoint** para predicciones en línea vía API REST, o usar en **predicción por lotes**, sin volver a entrenarlo.

#### 6.2. Entrenar la Versión 2 con Más Variables
La v2 añade `relacion` y `perdida_capital`. Al usar **el mismo `vertex_ai_model_id`**, el Registry no crea un modelo nuevo: crea la **versión 2** del mismo modelo.

```bash
source env.sh

bq query --use_legacy_sql=false "
CREATE OR REPLACE MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos_v2\`
TRANSFORM(
  ML.QUANTILE_BUCKETIZE(edad, 5) OVER() AS rango_edad,
  ML.STANDARD_SCALER(horas_semana) OVER() AS horas_semana_std,
  * EXCEPT(edad, horas_semana)
)
OPTIONS(
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['gana_mas_50k'],
  data_split_method = 'NO_SPLIT',
  model_registry = 'VERTEX_AI',
  vertex_ai_model_id = '$MODELO_REGISTRY',
  vertex_ai_model_version_aliases = ['v2']
) AS
SELECT * EXCEPT(particion)
FROM \`$PROJECT_ID.$DATASET.census\`
WHERE particion = 'ENTRENAMIENTO'"

gcloud ai models list-version $MODELO_REGISTRY --region=$REGION \
  --format="table(versionId, versionAliases.list(), versionCreateTime)"
```

Verás la versión 1 (`v1`, `default`) y la versión 2 (`v2`). El alias `default` es la versión que se usa si alguien pide el modelo sin indicar versión.

#### 6.3. Comparar Versiones con los Mismos Datos de Prueba

```bash
source env.sh

bq query --use_legacy_sql=false "
SELECT 'v1' AS version, ROUND(precision, 3) AS precision, ROUND(recall, 3) AS recall, ROUND(roc_auc, 3) AS auc
FROM ML.EVALUATE(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos\`,
  (SELECT * FROM \`$PROJECT_ID.$DATASET.census\` WHERE particion = 'PRUEBA'))
UNION ALL
SELECT 'v2', ROUND(precision, 3), ROUND(recall, 3), ROUND(roc_auc, 3)
FROM ML.EVALUATE(MODEL \`$PROJECT_ID.$DATASET.clasificador_ingresos_v2\`,
  (SELECT * FROM \`$PROJECT_ID.$DATASET.census\` WHERE particion = 'PRUEBA'))"
```

Gracias a la partición reproducible, ambas versiones se miden **exactamente con las mismas personas**: la comparación es justa. En la corrida de prueba la v2 apenas mejoró el AUC (0.900 → 0.903) y el recall, y perdió algo de precisión: **más variables no siempre significan un modelo mucho mejor**. Si la v2 convence, en un flujo real se le movería el alias `default` (o `produccion`) para promoverla.

#### 6.4. Verificación Visual
En la consola, ve a **Agent Platform → Model Registry** y abre `clasificador-ingresos-lab11`:
- La pestaña de **versiones** muestra la 1 y la 2 con sus alias.
- La **fuente** del modelo es BigQuery: hay un enlace de vuelta al modelo en BigQuery Studio.

---

### Paso 7: AutoML Guiado — Configurar sin Lanzar (15 min)

**AutoML** prueba por ti decenas de arquitecturas, preprocesamientos e hiperparámetros, y entrega el mejor modelo. No requiere SQL ni código, pero **cobra por nodo-hora de entrenamiento**. Por eso aquí lo configuraremos completo y nos detendremos **antes** de lanzarlo.

#### 7.1. Crear un Dataset Tabular a Partir de BigQuery
El dataset de AutoML no copia los datos: es un registro que **apunta** a la tabla `census`. Lo crearemos con la API REST (no existe un comando `gcloud` para esto):

```bash
source env.sh

curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/datasets" \
  -d "{
    \"displayName\": \"$DATASET_AUTOML\",
    \"metadataSchemaUri\": \"gs://google-cloud-aiplatform/schema/dataset/metadata/tabular_1.0.0.yaml\",
    \"metadata\": {\"inputConfig\": {\"bigquerySource\": {\"uri\": \"bq://$PROJECT_ID.$DATASET.census\"}}}
  }" | grep '"name"'

# La creación tarda 1 a 2 minutos: esperar a que aparezca y guardar su ID
for i in $(seq 1 20); do
  ID_AUTOML=$(curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/datasets" \
    | python3 -c "import json, sys; d = [x for x in json.load(sys.stdin).get('datasets', []) if x['displayName'] == '$DATASET_AUTOML']; print(d[0]['name'].split('/')[-1] if d else '')")
  [ -n "$ID_AUTOML" ] && break
  echo "Intento $i: el dataset aún se está creando, reintentando en 15 s..."; sleep 15
done
echo "export ID_AUTOML=\"$ID_AUTOML\"" >> env.sh
echo "Dataset de AutoML: $ID_AUTOML"
```

#### 7.2. Configurar el Entrenamiento en la Consola

> [!CAUTION]
> **NO hagas clic en "Start Training" / "Iniciar entrenamiento".** El entrenamiento de AutoML tabular cuesta **$21.252 USD por nodo-hora** y Google sugiere de 1 a 3 horas para menos de 100,000 filas. En este paso solo recorremos el asistente.

1. En la consola, ve a **Agent Platform → Datasets** y abre `census_lab11` (región `us-central1`).
2. Revisa la pestaña de análisis: AutoML ya detectó las 12 columnas y su tipo.
3. Haz clic en **Train new model** → **Other**.
4. **Training method**: deja **Classification** y **AutoML**. Clic en **Continue**.
5. **Model details**: en **Target column** elige `gana_mas_50k`. Abre **Advanced options** y observa los tipos de división de datos: **Random** (80/10/10), **Manual** (con una columna como nuestra `particion`) y **Chronological**. Clic en **Continue**.
6. **Training options**: aquí excluirías columnas que no deben entrenar el modelo; en este caso, **excluye `particion`** (es un artefacto nuestro, no un dato de la persona). Observa las **transformaciones** que AutoML propone para cada columna: es el preprocesamiento que en el Paso 4 escribiste a mano con `TRANSFORM`. Clic en **Continue**.
7. **Compute and pricing**: escribe `1` en el presupuesto (*budget*) de nodo-horas. Ese es el tope máximo que pagarías (~$21 USD); AutoML puede terminar antes con *early stopping*.
8. **Haz clic en "Cancel"** y confirma que no quieres guardar el entrenamiento.

> [!TIP]
> **¿AutoML o BigQuery ML?** Con un presupuesto de 1 hora, AutoML suele superar ligeramente a una regresión logística en AUC, a cambio de costar unas mil veces más que el modelo que entrenaste en el Paso 4 por menos de un centavo. AutoML gana cuando el problema es complejo y no tienes tiempo de experimentar; BigQuery ML gana para iterar rápido y barato. Más en la teoría.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO Y EN ORDEN!** Borra **primero los modelos uno por uno** con `bq rm -m` y **después** el dataset. Si borras directamente el dataset, los modelos desaparecen de BigQuery pero sus versiones **quedan huérfanas en el Model Registry**, y Vertex AI no permite borrarlas desde su lado (*"BQML model can not be deleted from Vertex, delete it from BQML"*).

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab11 && source env.sh

# 1. Borrar los modelos registrados (versión más reciente primero) y los demás modelos
bq rm -f -m $PROJECT_ID:$DATASET.clasificador_ingresos_v2
bq rm -f -m $PROJECT_ID:$DATASET.clasificador_ingresos
bq rm -f -m $PROJECT_ID:$DATASET.masa_pinguinos
bq rm -f -m $PROJECT_ID:$DATASET.grupos_pinguinos

# 2. Esperar a que el Model Registry quede sin el modelo
for i in $(seq 1 20); do
  QUEDA=$(gcloud ai models list --region=$REGION --filter="displayName=$MODELO_REGISTRY" --format="value(name)" 2>/dev/null)
  [ -z "$QUEDA" ] && echo "Model Registry limpio" && break
  echo "Intento $i: el Registry aún tiene el modelo, reintentando en 15 s..."; sleep 15
done

# 3. Borrar el dataset de AutoML (Agent Platform)
[ -n "$ID_AUTOML" ] && curl -s -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/datasets/$ID_AUTOML" | grep '"name"'

# 4. Borrar el dataset de BigQuery con la tabla census
bq rm -r -f -d $PROJECT_ID:$DATASET
```

### Auditoría Final de Limpieza
Todas las secciones deben aparecer vacías:

```bash
source ~/workshop-gcp/lab11/env.sh

echo "=== Modelos del Lab 11 en el Model Registry ==="
gcloud ai models list --region=$REGION --filter="displayName=$MODELO_REGISTRY" --format="value(name)" 2>/dev/null

echo "=== Datasets de AutoML del Lab 11 ==="
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/datasets" | grep "$DATASET_AUTOML"

echo "=== Dataset de BigQuery del Lab 11 ==="
bq ls | grep $DATASET
```

---

## 6. Conclusiones

En este undécimo laboratorio hiciste Machine Learning **donde viven los datos**:
- Entrenaste una **regresión**, una **clasificación** y un **clustering** solo con SQL, sin mover un byte fuera de BigQuery y por menos de un centavo cada uno.
- Separaste entrenamiento y prueba de forma **reproducible** y elegiste la métrica correcta para cada problema, incluido el efecto del **desbalance de clases** y del **umbral** de decisión.
- Con **`TRANSFORM`** el preprocesamiento viajó dentro del modelo, y con **`ML.EXPLAIN_PREDICT`** justificaste cada predicción.
- Tu modelo de SQL quedó en el **Model Registry** de Vertex AI con **versiones y alias**, listo para desplegarse como API.
- Configuraste **AutoML** y entendiste su costo antes de gastarlo: la decisión entre BigQuery ML y AutoML también es una decisión de **FinOps**.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Árboles contra Regresión**:
   Entrena un `BOOSTED_TREE_CLASSIFIER` con los mismos datos de `ENTRENAMIENTO` y compáralo con la v1 y la v2 usando la consulta del Paso 6.3. ¿Mejora el AUC? Revisa en `INFORMATION_SCHEMA.JOBS` cuánto tiempo y cuántos bytes costó cada entrenamiento (los árboles son un modelo **externo**: se entrenan en Vertex AI).

2. **Reto 2 — ¿Cuántos Grupos?**:
   Entrena modelos K-means con 2, 3, 4 y 5 grupos y compara su `davies_bouldin_index` en `ML.EVALUATE` (menor es mejor). ¿Coincide el mejor valor con las 3 especies reales?

3. **Reto 3 — Predicción por Lotes Programada**:
   Usando lo aprendido en el Módulo 09, crea una **consulta programada** que cada día ejecute `ML.PREDICT` del clasificador sobre una tabla de "personas nuevas" y guarde los resultados en una tabla `predicciones` con la fecha de ejecución.

---

## 8. Referencias Oficiales

- **Introducción a BigQuery ML**: [https://docs.cloud.google.com/bigquery/docs/bqml-introduction](https://docs.cloud.google.com/bigquery/docs/bqml-introduction)
- **Sentencia `CREATE MODEL`**: [https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create)
- **Cláusula `TRANSFORM`**: [https://docs.cloud.google.com/bigquery/docs/bigqueryml-transform](https://docs.cloud.google.com/bigquery/docs/bigqueryml-transform)
- **Evaluar Modelos (`ML.EVALUATE`)**: [https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-evaluate](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-evaluate)
- **Explicabilidad en BigQuery ML**: [https://docs.cloud.google.com/bigquery/docs/xai-overview](https://docs.cloud.google.com/bigquery/docs/xai-overview)
- **Registrar Modelos de BigQuery ML en el Model Registry**: [https://docs.cloud.google.com/bigquery/docs/managing-models-vertex](https://docs.cloud.google.com/bigquery/docs/managing-models-vertex)
- **Entrenar un Modelo AutoML Tabular**: [https://docs.cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/train-model](https://docs.cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/train-model)
- **Precios de BigQuery ML**: [https://cloud.google.com/bigquery/pricing#bqml](https://cloud.google.com/bigquery/pricing#bqml)
- **Precios de Vertex AI (Agent Platform)**: [https://cloud.google.com/vertex-ai/pricing](https://cloud.google.com/vertex-ai/pricing)
