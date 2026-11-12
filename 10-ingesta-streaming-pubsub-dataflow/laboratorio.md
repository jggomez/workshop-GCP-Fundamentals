# Laboratorio 10: El Escudo de Ingesta — Pipeline de Pagos en Tiempo Real con Autocuración (Pub/Sub + Dataflow + BigQuery)

- **Duración estimada**: 120 minutos
- **Nivel**: Avanzado / Ingeniería de Datos en Streaming
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud`, `bq`, `python3`, Apache Beam)** + Verificaciones visuales en las consolas de **Pub/Sub**, **Dataflow** y **BigQuery**

---

## 1. Objetivo del Laboratorio

Construir un pipeline de pagos en tiempo real que **no colapse ni se contamine** cuando los productores envían datos malos. Un simulador publicará transacciones en **Cloud Pub/Sub**, el 80% válidas y el resto con problemas inyectados a propósito. Un pipeline de **Apache Beam** ejecutado en **Cloud Dataflow** hará tres cosas:
1. Cargar los pagos válidos y enriquecidos en una tabla particionada de **BigQuery** en segundos.
2. **Autocurar** los errores de formato recuperables (`" cop "` → `"COP"`, `"120.5"` → `120.5`) sin intervención humana.
3. Desviar a una **cuarentena en Cloud Storage** los mensajes irrecuperables (*poison pills*) y los eventos que llegan demasiado tarde, cada uno con su motivo, **sin detener el flujo**.

```text
[Simulador Python] ── 80% válidos, 10% reparables, 5% tardíos, 5% venenosos
        │
        ▼
[Cloud Pub/Sub: topic pagos-lab10] ──► [Suscripción pagos-lab10-dataflow]
        │
        ▼
[Cloud Dataflow / Apache Beam: ValidarYEnriquecer]
   ├──► Salida principal (válidos + reparados) ──► [BigQuery: pagos (particionada por día)]
   └──► Salida lateral "cuarentena" ──────────────► [Cloud Storage: bucket de cuarentena]
```

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Aprovisionar desde la terminal un topic y una suscripción de **Pub/Sub**, buckets, una tabla **particionada y clusterizada** de BigQuery y una **cuenta de servicio de mínimo privilegio** para Dataflow.
2. Demostrar el **desacoplamiento**: Pub/Sub retiene los mensajes aunque nadie los esté leyendo.
3. Programar en **Apache Beam** un `DoFn` con **salidas laterales** que separa datos limpios de datos corruptos en caliente.
4. Probar la lógica del pipeline **en local, en segundos y sin costo**, con `TestPipeline`.
5. Desplegar un job **streaming** en Dataflow, observar su grafo y su *backlog*, y escribir en BigQuery con la **Storage Write API**.
6. **Reconciliar** el sistema: comprobar que cada mensaje publicado terminó en BigQuery o en cuarentena, sin pérdidas.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado: menos de $0.20 USD**, casi todo por el job de Dataflow. El costo depende de cuánto tiempo lo dejes encendido: **la limpieza es obligatoria**.

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia | Costo del Laboratorio |
| :--- | :--- | :--- | :--- |
| **Dataflow (streaming)** | 1 worker `n1-standard-2` (2 vCPU, 7.5 GB; máximo 2) durante ~40 min, con Streaming Engine | ~$0.069 / vCPU-hora + ~$0.0036 / GiB-hora + Streaming Engine | **~$0.15 USD** |
| **Pub/Sub** | Unos 5,000 mensajes (se factura mínimo 1 KB por mensaje) | Primeros **10 GiB/mes gratis** | **$0.00 USD** |
| **BigQuery** | Unos 4,500 pagos vía Storage Write API | Capa gratuita mensual de ingesta y almacenamiento | **$0.00 USD** |
| **Cloud Storage** | 2 buckets con unos MB (staging y cuarentena) | Primeros 5 GB/mes gratis | **$0.00 USD** |
| **TOTAL ESTIMADO** | **Ejecutando la limpieza al finalizar** | — | **< $0.20 USD** |

---

## 4. Paso a Paso del Laboratorio

### Fase 1: Infraestructura Base (20 min)

#### 1.1. Variables, APIs y Verificaciones Previas
1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables y habilita las APIs:

```bash
mkdir -p ~/workshop-gcp/lab10
cd ~/workshop-gcp/lab10

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export REGION="us-central1"
export TOPIC="pagos-lab10"
export SUSCRIPCION="pagos-lab10-dataflow"
export BUCKET_DATAFLOW="gs://${PROJECT_ID}-dataflow-lab10"
export BUCKET_CUARENTENA="gs://${PROJECT_ID}-cuarentena-lab10"
export DATASET="pagos_lab10"
export TABLA="${PROJECT_ID}:pagos_lab10.pagos"
export SA_DATAFLOW="sa-dataflow-lab10@${PROJECT_ID}.iam.gserviceaccount.com"
export JOB_NAME="escudo-ingesta-lab10"
EOF
source env.sh

gcloud config set project $PROJECT_ID

# Habilitar las APIs de Pub/Sub, Dataflow (y Compute Engine para sus workers), BigQuery y Cloud Storage
gcloud services enable \
  pubsub.googleapis.com \
  dataflow.googleapis.com \
  compute.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com

# Los workers de Dataflow son VMs: necesitan la red "default" (o indicar otra con --subnetwork)
if gcloud compute networks describe default > /dev/null 2>&1; then
  echo "OK: existe la red default"
else
  echo "AVISO: no existe la red default. Créala con: gcloud compute networks create default --subnet-mode=auto"
fi
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab10 && source env.sh && source .venv/bin/activate`

#### 1.2. Pub/Sub: Topic y Suscripción
El topic recibe los pagos. La suscripción es la "cola" de la que leerá Dataflow. Si nadie lee, retiene los mensajes **7 días** (valor predeterminado):

```bash
source env.sh

gcloud pubsub topics create $TOPIC
gcloud pubsub subscriptions create $SUSCRIPCION --topic=$TOPIC --ack-deadline=60

gcloud pubsub subscriptions describe $SUSCRIPCION \
  --format="yaml(name, topic, ackDeadlineSeconds, messageRetentionDuration)"
```

#### 1.3. Cloud Storage: Staging de Dataflow y Cuarentena

```bash
# Archivos temporales y de staging de Dataflow
gcloud storage buckets create $BUCKET_DATAFLOW \
  --location=$REGION --uniform-bucket-level-access --soft-delete-duration=0

# Cuarentena: aquí terminan los mensajes rechazados, con su motivo
gcloud storage buckets create $BUCKET_CUARENTENA \
  --location=$REGION --uniform-bucket-level-access --soft-delete-duration=0
```

#### 1.4. BigQuery: Tabla Analítica Particionada y Clusterizada
La tabla se **particiona por el día del pago** (`event_time`) y se **clusteriza por país y método de pago**, las columnas por las que filtrarán los analistas (repasa el Módulo 09). El esquema debe coincidir con el que usará el pipeline:

```bash
source env.sh

bq --location=$REGION mk --dataset --description="Lab 10: pagos en tiempo real" $PROJECT_ID:$DATASET

bq mk --table \
  --time_partitioning_field=event_time \
  --time_partitioning_type=DAY \
  --clustering_fields=pais,metodo_pago \
  --description="Pagos validados y enriquecidos por Dataflow" \
  $TABLA \
  id_pago:STRING,event_time:TIMESTAMP,ingestado_en:TIMESTAMP,latencia_seg:FLOAT,id_comercio:STRING,pais:STRING,metodo_pago:STRING,moneda:STRING,monto:FLOAT,monto_usd:FLOAT,categoria_riesgo:STRING,reparado:BOOLEAN,reparaciones:STRING

bq show --format=prettyjson $TABLA | grep -A3 -E '"timePartitioning"|"clustering"'
```

#### 1.5. Cuenta de Servicio de Mínimo Privilegio para los Workers
Por defecto, los workers de Dataflow usan la cuenta de servicio de Compute Engine, que suele tener demasiados permisos. Crearemos una dedicada con **solo** lo necesario:

```bash
source env.sh

gcloud iam service-accounts create sa-dataflow-lab10 --display-name="Workers Dataflow Lab 10"

# Esperar a que la cuenta de servicio esté disponible
for i in $(seq 1 12); do
  gcloud iam service-accounts describe $SA_DATAFLOW > /dev/null 2>&1 && break
  sleep 5
done

# 1. Ejecutar trabajo de Dataflow (nivel proyecto)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_DATAFLOW" --role="roles/dataflow.worker" --condition=None --quiet > /dev/null

# 2. Leer de la suscripción (solo esa suscripción)
gcloud pubsub subscriptions add-iam-policy-binding $SUSCRIPCION \
  --member="serviceAccount:$SA_DATAFLOW" --role="roles/pubsub.subscriber" > /dev/null
gcloud pubsub subscriptions add-iam-policy-binding $SUSCRIPCION \
  --member="serviceAccount:$SA_DATAFLOW" --role="roles/pubsub.viewer" > /dev/null

# 3. Escribir en los dos buckets (solo esos buckets)
for B in $BUCKET_DATAFLOW $BUCKET_CUARENTENA; do
  gcloud storage buckets add-iam-policy-binding $B \
    --member="serviceAccount:$SA_DATAFLOW" --role="roles/storage.objectAdmin" > /dev/null
done

# 4. Escribir en el dataset de BigQuery (solo ese dataset)
bq query --use_legacy_sql=false \
  "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$PROJECT_ID\`.$DATASET TO 'serviceAccount:$SA_DATAFLOW'"

echo "Cuenta de servicio lista: $SA_DATAFLOW"
```

---

### Fase 2: El Simulador del Caos (25 min)

#### 2.1. Preparar el Entorno de Python
Instalaremos **Apache Beam** (con los conectores de Google Cloud) en un entorno virtual. Tarda unos **2 a 3 minutos**:

```bash
cd ~/workshop-gcp/lab10 && source env.sh

python3 -m venv .venv
source .venv/bin/activate
pip install --quiet "apache-beam[gcp]==2.77.0"

python -c "import apache_beam; print('Apache Beam', apache_beam.__version__)"
```

#### 2.2. Escribir el Simulador
El simulador genera pagos de 5 países con una mezcla controlada de caos:

| Categoría | Proporción | Qué tiene | Destino esperado |
| :--- | :--- | :--- | :--- |
| `VALIDO` | 80% | Pago correcto | BigQuery |
| `REPARABLE` | 10% | Moneda y país en minúsculas con espacios, monto como texto | BigQuery, marcado `reparado = TRUE` |
| `TARDIO` | 5% | Ocurrió hace 2 a 6 horas | Cuarentena: `EVENTO_TARDIO` |
| `VENENO` | 5% | JSON truncado, monto negativo, moneda `XYZ` o sin país | Cuarentena: motivo según el caso |

```bash
cat > simulador.py << 'EOF'
"""Simulador del caos: publica pagos en Pub/Sub con errores inyectados.

Mezcla de mensajes:
  80% válidos | 10% sucios pero reparables | 5% tardíos (2 a 6 h) | 5% venenosos (irrecuperables)
Al terminar guarda un resumen por categoría en resumen_simulador.json (se acumula entre ejecuciones).
"""
import argparse
import json
import os
import random
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from google.cloud import pubsub_v1

COMERCIOS = [f"COM-{n:02d}" for n in range(1, 21)]
PAISES = {"CO": "COP", "MX": "MXN", "PE": "PEN", "CL": "CLP", "US": "USD"}
RANGOS = {"COP": (5000, 8000000), "MXN": (20, 40000), "PEN": (5, 8000), "CLP": (1000, 2000000), "USD": (1, 2500)}
METODOS = ["TARJETA", "PSE", "BILLETERA", "TRANSFERENCIA"]


def pago_valido(retraso=timedelta(seconds=0)):
    pais = random.choice(list(PAISES))
    moneda = PAISES[pais]
    return {
        "id_pago": str(uuid.uuid4()),
        "event_time": (datetime.now(timezone.utc) - retraso).isoformat(),
        "monto": round(random.uniform(*RANGOS[moneda]), 2),
        "moneda": moneda, "pais": pais,
        "metodo_pago": random.choice(METODOS),
        "id_comercio": random.choice(COMERCIOS),
    }


def generar():
    """Devuelve (categoria, bytes) según la mezcla de caos."""
    r = random.random()
    if r < 0.80:
        return "VALIDO", json.dumps(pago_valido()).encode()
    if r < 0.90:  # Errores de formato que el pipeline puede reparar
        p = pago_valido()
        p["moneda"] = f" {p['moneda'].lower()} "
        p["pais"] = p["pais"].lower()
        p["monto"] = str(p["monto"])
        return "REPARABLE", json.dumps(p).encode()
    if r < 0.95:  # Llega con 2 a 6 horas de retraso
        return "TARDIO", json.dumps(pago_valido(timedelta(hours=random.uniform(2, 6)))).encode()
    p = pago_valido()  # Veneno: irrecuperable
    tipo = random.choice(["JSON_ROTO", "MONTO_NEGATIVO", "MONEDA_FALSA", "SIN_PAIS"])
    if tipo == "JSON_ROTO":
        return "VENENO", json.dumps(p).encode()[:25]
    if tipo == "MONTO_NEGATIVO":
        p["monto"] = -abs(p["monto"])
    elif tipo == "MONEDA_FALSA":
        p["moneda"] = "XYZ"
    else:
        del p["pais"]
    return "VENENO", json.dumps(p).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, help="projects/PROYECTO/topics/NOMBRE")
    parser.add_argument("--mensajes", type=int, default=1000)
    parser.add_argument("--por-segundo", type=float, default=50, help="0 = ráfaga sin pausas")
    args = parser.parse_args()

    publicador = pubsub_v1.PublisherClient()
    conteo, futuros = Counter(), []
    inicio = time.time()
    for i in range(args.mensajes):
        categoria, datos = generar()
        conteo[categoria] += 1
        futuros.append(publicador.publish(args.topic, datos))
        if args.por_segundo and i % max(int(args.por_segundo), 1) == 0:
            time.sleep(max(0, (i / args.por_segundo) - (time.time() - inicio)))
    for f in futuros:
        f.result()  # Esperar la confirmación de Pub/Sub

    previo = Counter()
    if os.path.exists("resumen_simulador.json"):
        previo = Counter(json.load(open("resumen_simulador.json")))
    total = previo + conteo
    json.dump(dict(total), open("resumen_simulador.json", "w"), indent=2)
    print(f"Publicados {args.mensajes} mensajes en {time.time() - inicio:.1f} s: {dict(conteo)}")
    print(f"Acumulado de todas las ejecuciones: {dict(total)}")


if __name__ == "__main__":
    main()
EOF
```

#### 2.3. Publicar sin Nadie Escuchando: el Desacoplamiento en Acción
Todavía **no existe ningún consumidor**. Publiquemos una ráfaga de 1,000 pagos de golpe:

```bash
cd ~/workshop-gcp/lab10 && source env.sh && source .venv/bin/activate

python simulador.py --topic=projects/$PROJECT_ID/topics/$TOPIC --mensajes=1000 --por-segundo=0
```

¿Se perdieron por no haber nadie leyendo? Echemos un vistazo a la suscripción **sin confirmar** los mensajes (sin `--auto-ack`), así siguen disponibles para Dataflow:

```bash
gcloud pubsub subscriptions pull $SUSCRIPCION --limit=3
```

Los mensajes están ahí, esperando. Esto es **desacoplamiento**: el productor no sabe ni le importa si el consumidor está caído, lento o aún no existe. En la consola, ve a `☰` -> **Pub/Sub** -> **Suscripciones** -> **`pagos-lab10-dataflow`** -> pestaña **Métricas** y observa el número de **mensajes sin confirmar** (*unacked messages*); la métrica tarda 1 o 2 minutos en aparecer.

> [!NOTE]
> Los 3 mensajes que acabas de ver volverán a estar disponibles cuando venza su **ack deadline** (60 s). Pub/Sub nunca descarta un mensaje no confirmado hasta que vence la retención.

---

### Fase 3: El Pipeline en Apache Beam (40 min)

#### 3.1. El Escudo: `ValidarYEnriquecer` con Salidas Laterales
El corazón del pipeline es un `DoFn` que, para cada mensaje, emite **a la salida principal** (`validos`) o **a la salida lateral** (`cuarentena`). Nunca lanza una excepción por un dato malo: en streaming, Dataflow reintenta indefinidamente los elementos que fallan, y un solo mensaje venenoso atascaría todo el flujo.

Lee el código con calma antes de ejecutarlo. Observa:
- El orden de las validaciones: **primero** se intenta reparar el formato, **después** se aplican las reglas de negocio.
- La regla `MAX_RETRASO_MIN = 60`: un pago que llega con más de una hora de retraso no se carga; va a cuarentena como `EVENTO_TARDIO` para que alguien lo revise.
- El enriquecimiento: conversión a USD, categoría de riesgo, hora de ingesta y latencia.
- La **segunda capa del escudo**: las filas que BigQuery rechace (`failed_rows_with_errors`) también van a cuarentena.
- Los rechazos se escriben en **ventanas de 1 minuto**: en streaming no existe "el final" para cerrar un archivo.

```bash
cd ~/workshop-gcp/lab10

cat > pipeline.py << 'EOF'
"""El Escudo de Ingesta: Pub/Sub -> Dataflow (Apache Beam) -> BigQuery + cuarentena en Cloud Storage.

Cada mensaje sigue uno de tres caminos:
  1. VÁLIDO      -> se enriquece y va a BigQuery.
  2. REPARADO    -> tenía errores menores (formato), se corrige en caliente y va a BigQuery.
  3. CUARENTENA  -> es irrecuperable o llegó demasiado tarde; va a Cloud Storage con su motivo.
"""
import argparse
import json
import logging
from datetime import datetime, timezone

import apache_beam as beam
from apache_beam.io import fileio
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.transforms.window import FixedWindows
from apache_beam.utils.timestamp import Timestamp

MONEDAS_A_USD = {"USD": 1.0, "COP": 0.00025, "MXN": 0.055, "PEN": 0.27, "CLP": 0.0011}
PAISES = {"CO", "MX", "PE", "CL", "US"}
METODOS = {"TARJETA", "PSE", "BILLETERA", "TRANSFERENCIA"}
CAMPOS = ("id_pago", "event_time", "monto", "moneda", "pais", "metodo_pago", "id_comercio")
MAX_RETRASO_MIN = 60  # Regla de negocio: un pago con más de 60 min de retraso es EVENTO_TARDIO
# Esquema de la tabla destino (el mismo que usa `bq mk` en la Fase 1)
ESQUEMA_BQ = ("id_pago:STRING,event_time:TIMESTAMP,ingestado_en:TIMESTAMP,latencia_seg:FLOAT,"
              "id_comercio:STRING,pais:STRING,metodo_pago:STRING,moneda:STRING,monto:FLOAT,"
              "monto_usd:FLOAT,categoria_riesgo:STRING,reparado:BOOLEAN,reparaciones:STRING")


class ValidarYEnriquecer(beam.DoFn):
    """Valida, repara y enriquece un pago. Los rechazos salen por la etiqueta 'cuarentena'."""

    def __init__(self, ahora=None):
        self._ahora = ahora  # Permite fijar el reloj en las pruebas

    def process(self, mensaje):
        crudo = mensaje.decode("utf-8", errors="replace") if isinstance(mensaje, bytes) else mensaje
        ahora = self._ahora or datetime.now(timezone.utc)
        try:
            pago = json.loads(crudo)
            if not isinstance(pago, dict):
                raise ValueError("el mensaje no es un objeto JSON")
        except ValueError as error:
            yield self._rechazo("JSON_INVALIDO", str(error), crudo, ahora)
            return

        faltantes = [c for c in CAMPOS if pago.get(c) in (None, "")]
        if faltantes:
            yield self._rechazo("CAMPO_FALTANTE", ",".join(faltantes), crudo, ahora)
            return

        reparaciones = []
        # Autocuración: normalizar errores de formato recuperables
        moneda = str(pago["moneda"]).strip().upper()
        pais = str(pago["pais"]).strip().upper()
        metodo = str(pago["metodo_pago"]).strip().upper()
        if (moneda, pais, metodo) != (pago["moneda"], pago["pais"], pago["metodo_pago"]):
            reparaciones.append("FORMATO_TEXTO")
        monto = pago["monto"]
        if isinstance(monto, str):
            try:
                monto = float(monto.replace(",", "."))
                reparaciones.append("MONTO_COMO_TEXTO")
            except ValueError:
                yield self._rechazo("MONTO_INVALIDO", f"monto={pago['monto']!r}", crudo, ahora)
                return

        if not isinstance(monto, (int, float)) or monto <= 0:
            yield self._rechazo("MONTO_INVALIDO", f"monto={pago['monto']!r}", crudo, ahora)
            return
        if moneda not in MONEDAS_A_USD:
            yield self._rechazo("MONEDA_NO_SOPORTADA", moneda, crudo, ahora)
            return
        if pais not in PAISES or metodo not in METODOS:
            yield self._rechazo("CATALOGO_INVALIDO", f"pais={pais} metodo={metodo}", crudo, ahora)
            return
        try:
            event_time = datetime.fromisoformat(str(pago["event_time"]).replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except ValueError:
            yield self._rechazo("FECHA_INVALIDA", str(pago["event_time"]), crudo, ahora)
            return

        retraso_min = (ahora - event_time).total_seconds() / 60
        if retraso_min > MAX_RETRASO_MIN:
            yield self._rechazo("EVENTO_TARDIO", f"retraso={retraso_min:.0f} min", crudo, ahora)
            return

        monto_usd = round(float(monto) * MONEDAS_A_USD[moneda], 2)
        yield {
            "id_pago": str(pago["id_pago"]),
            "event_time": Timestamp.from_utc_datetime(event_time.astimezone(timezone.utc)),
            "ingestado_en": Timestamp.from_utc_datetime(ahora),
            "latencia_seg": round(max(retraso_min, 0) * 60, 3),
            "id_comercio": str(pago["id_comercio"]),
            "pais": pais,
            "metodo_pago": metodo,
            "moneda": moneda,
            "monto": float(monto),
            "monto_usd": monto_usd,
            "categoria_riesgo": "ALTO" if monto_usd >= 1000 else "MEDIO" if monto_usd >= 200 else "BAJO",
            "reparado": bool(reparaciones),
            "reparaciones": ",".join(reparaciones),
        }

    @staticmethod
    def _rechazo(motivo, detalle, crudo, ahora):
        return beam.pvalue.TaggedOutput("cuarentena", json.dumps({
            "motivo": motivo, "detalle": detalle, "mensaje_original": crudo,
            "rechazado_en": ahora.isoformat()}, ensure_ascii=False))


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--suscripcion", required=True, help="projects/PROYECTO/subscriptions/NOMBRE")
    parser.add_argument("--tabla", required=True, help="PROYECTO:DATASET.TABLA")
    parser.add_argument("--cuarentena", required=True, help="gs://BUCKET/carpeta")
    args, beam_args = parser.parse_known_args(argv)
    opciones = PipelineOptions(beam_args, streaming=True, save_main_session=True)

    p = beam.Pipeline(options=opciones)
    resultado = (
        p
        | "LeerPubSub" >> beam.io.ReadFromPubSub(subscription=args.suscripcion)
        | "ValidarYEnriquecer" >> beam.ParDo(ValidarYEnriquecer()).with_outputs("cuarentena", main="validos"))

    escritura = resultado.validos | "EscribirBigQuery" >> beam.io.WriteToBigQuery(
        args.tabla,
        schema=ESQUEMA_BQ,
        method=beam.io.WriteToBigQuery.Method.STORAGE_WRITE_API,
        create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
        write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
        triggering_frequency=5)

    # Filas que BigQuery rechace (por ejemplo, un esquema incompatible) también van a cuarentena
    rechazos_bq = escritura.failed_rows_with_errors | "FormatearRechazoBQ" >> beam.Map(
        lambda fallo: json.dumps({"motivo": "RECHAZO_BIGQUERY", "detalle": fallo["error_message"][:500],
                                  "mensaje_original": json.dumps(fallo["failed_row"], default=str),
                                  "rechazado_en": datetime.now(timezone.utc).isoformat()}))

    (
        (resultado.cuarentena, rechazos_bq)
        | "UnirRechazos" >> beam.Flatten()
        | "VentanasDe1Min" >> beam.WindowInto(FixedWindows(60))
        | "EscribirCuarentena" >> fileio.WriteToFiles(
            path=args.cuarentena, shards=1, max_writers_per_bundle=0,
            file_naming=fileio.default_file_naming(prefix="rechazos", suffix=".json")))

    resultado_job = p.run()
    if opciones.view_as(StandardOptions).runner == "DataflowRunner":
        print("Job enviado a Dataflow. Síguelo en la consola: Dataflow -> Jobs")
    else:
        resultado_job.wait_until_finish()  # En local, el pipeline corre hasta que lo detengas (Ctrl+C)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
EOF
```

#### 3.2. Probar en Local, en Segundos y Gratis
Arrancar un job de Dataflow tarda varios minutos y cuesta dinero, así que **nunca depures en la nube lo que puedes probar en tu terminal**. `TestPipeline` ejecuta el pipeline en memoria con mensajes de ejemplo y un reloj fijo:

```bash
cat > test_pipeline.py << 'EOF'
"""Pruebas locales del escudo: se ejecutan en segundos y sin costo, antes de pagar workers de Dataflow."""
import json
import unittest
from datetime import datetime, timedelta, timezone

import apache_beam as beam
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to

from pipeline import ValidarYEnriquecer

AHORA = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


def pago(**cambios):
    base = {"id_pago": "P-1", "event_time": (AHORA - timedelta(seconds=2)).isoformat(), "monto": 250000,
            "moneda": "COP", "pais": "CO", "metodo_pago": "PSE", "id_comercio": "COM-01"}
    base.update(cambios)
    return json.dumps(base).encode()


class EscudoDeIngesta(unittest.TestCase):

    def clasificar(self, mensajes, esperados_validos, esperados_motivos):
        with TestPipeline() as p:
            salida = (p | beam.Create(mensajes)
                      | beam.ParDo(ValidarYEnriquecer(ahora=AHORA)).with_outputs("cuarentena", main="validos"))
            assert_that(salida.validos | "IdYReparado" >> beam.Map(lambda f: (f["id_pago"], f["reparado"])),
                        equal_to(esperados_validos), label="validos")
            assert_that(salida.cuarentena | "Motivo" >> beam.Map(lambda r: json.loads(r)["motivo"]),
                        equal_to(esperados_motivos), label="cuarentena")

    def test_pago_valido_pasa_sin_reparar(self):
        self.clasificar([pago()], [("P-1", False)], [])

    def test_errores_de_formato_se_autocuran(self):
        self.clasificar([pago(id_pago="P-2", moneda=" cop ", pais="co", monto="250000.50")],
                        [("P-2", True)], [])

    def test_mensajes_venenosos_van_a_cuarentena(self):
        venenosos = [
            b'{"id_pago": "P-3", "monto": ',                      # JSON truncado
            pago(id_pago="P-4", monto=-50),                       # monto negativo
            pago(id_pago="P-5", moneda="XYZ"),                    # moneda inexistente
            pago(id_pago="P-6", pais=None),                       # campo faltante
            pago(id_pago="P-7", event_time=(AHORA - timedelta(hours=3)).isoformat()),  # llega 3 h tarde
        ]
        self.clasificar(venenosos, [], ["JSON_INVALIDO", "MONTO_INVALIDO", "MONEDA_NO_SOPORTADA",
                                         "CAMPO_FALTANTE", "EVENTO_TARDIO"])

    def test_enriquecimiento(self):
        with TestPipeline() as p:
            filas = (p | beam.Create([pago(monto=5000000)])
                     | beam.ParDo(ValidarYEnriquecer(ahora=AHORA)).with_outputs("cuarentena", main="validos")).validos
            assert_that(filas | beam.Map(lambda f: (f["monto_usd"], f["categoria_riesgo"])),
                        equal_to([(1250.0, "ALTO")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
EOF

cd ~/workshop-gcp/lab10 && source .venv/bin/activate
python test_pipeline.py 2>&1 | grep -E "^(test_|Ran|OK|FAIL|ERROR)|\.\.\. "
```

Deberías ver **4 pruebas en `ok`**. Cada una demuestra una promesa del escudo: los pagos válidos pasan intactos, los errores de formato se autocuran, cada tipo de veneno va a cuarentena con su motivo correcto y el enriquecimiento calcula bien el riesgo.

> [!NOTE]
> **¿Por qué no ejecutar el pipeline completo en local, leyendo de Pub/Sub?** En Python, el `DirectRunner` en streaming no admite transformaciones multilenguaje como el conector de BigQuery (Storage Write API), y el runner local **Prism** todavía no admite la lectura de Pub/Sub. Por eso la estrategia profesional es la de este laboratorio: **probar la lógica con `TestPipeline`** en local y hacer la prueba de integración en Dataflow.

#### 3.3. Ejercicio: Romper y Arreglar
Comprueba que las pruebas realmente protegen tu código:
1. Abre `pipeline.py` con el editor de Cloud Shell (`cloudshell edit pipeline.py`) y cambia `MAX_RETRASO_MIN = 60` por `MAX_RETRASO_MIN = 600`.
2. Vuelve a ejecutar `python test_pipeline.py`: la prueba `test_mensajes_venenosos_van_a_cuarentena` **debe fallar**, porque un pago de hace 3 horas ya no se considera tardío.
3. **Restaura el valor a `60`** y confirma que las 4 pruebas vuelven a pasar antes de continuar.

---

### Fase 4: Despliegue en Dataflow y Pruebas en Vivo (35 min)

#### 4.1. Lanzar el Job Streaming
El **mismo archivo** que probaste en local se lanza a la nube cambiando el *runner*. Las opciones clave:
- `--streaming`: el job corre indefinidamente leyendo de Pub/Sub.
- `--service_account_email`: los workers usan la cuenta de mínimo privilegio de la Fase 1.
- `--max_num_workers=2`: **tope de gasto**; el autoescalado nunca pasará de 2 workers.
- `--enable_streaming_engine`: el estado y el *shuffle* se gestionan fuera de los workers.

```bash
cd ~/workshop-gcp/lab10 && source env.sh && source .venv/bin/activate

python pipeline.py \
  --runner=DataflowRunner \
  --project=$PROJECT_ID \
  --region=$REGION \
  --job_name=$JOB_NAME \
  --temp_location=$BUCKET_DATAFLOW/temp \
  --staging_location=$BUCKET_DATAFLOW/staging \
  --service_account_email=$SA_DATAFLOW \
  --max_num_workers=2 \
  --enable_streaming_engine \
  --suscripcion=projects/$PROJECT_ID/subscriptions/$SUSCRIPCION \
  --tabla=$TABLA \
  --cuarentena=$BUCKET_CUARENTENA/rechazos
```

> [!NOTE]
> La primera vez, Beam descarga el **servicio de expansión de Java** para el conector de BigQuery (Storage Write API es una transformación multilenguaje). Por eso el comando tarda uno o dos minutos antes de enviar el job.

Espera a que el job pase a estado **Running** y a que sus workers estén listos (suele tardar **3 a 5 minutos**):

```bash
for i in $(seq 1 40); do
  ESTADO=$(gcloud dataflow jobs list --region=$REGION --status=active \
    --filter="name=$JOB_NAME" --format="value(state)" 2>/dev/null | head -n 1)
  echo "Intento $i: estado '${ESTADO:-PENDIENTE}'"
  [ -z "$ESTADO" ] && [ $i -ge 8 ] && echo "No aparece ningún job tras 2 minutos" && break
  [ "$ESTADO" = "Running" ] && break
  sleep 15
done

export JOB_ID=$(gcloud dataflow jobs list --region=$REGION --status=active \
  --filter="name=$JOB_NAME" --format="value(id)" | head -n 1)
if [ -z "$JOB_ID" ]; then
  echo "ERROR: no hay ningún job activo. Revisa la salida del comando de lanzamiento anterior."
else
  echo "export JOB_ID=\"$JOB_ID\"" >> env.sh
  echo "Job: https://console.cloud.google.com/dataflow/jobs/$REGION/$JOB_ID?project=$PROJECT_ID"
fi
```

> [!NOTE]
> `Running` no significa que ya esté procesando: Dataflow todavía tarda **2 a 4 minutos** en arrancar la VM del worker y descargar los contenedores de Python y Java. En la corrida de prueba, el job pasó a `Running` a los 3 min del lanzamiento y procesó el primer mensaje unos 3 min después.

Abre el enlace. En la consola de Dataflow observa:
- El **grafo del job**: `LeerPubSub` → `ValidarYEnriquecer` → dos ramas, `EscribirBigQuery` y `EscribirCuarentena`.
- Haz clic en `ValidarYEnriquecer`: verás **dos salidas**, `validos` y `cuarentena`, con su número de elementos.
- La pestaña **Métricas del job**: *data freshness*, *throughput* y número de workers.

El pipeline empieza por **los 1,000 mensajes acumulados en la Fase 2**: nada se perdió mientras no había consumidor.

#### 4.2. Tráfico en Vivo
Con el pipeline corriendo, publica un flujo continuo de 50 pagos por segundo durante 1 minuto y después una ráfaga instantánea:

```bash
cd ~/workshop-gcp/lab10 && source env.sh && source .venv/bin/activate

python simulador.py --topic=projects/$PROJECT_ID/topics/$TOPIC --mensajes=3000 --por-segundo=50
python simulador.py --topic=projects/$PROJECT_ID/topics/$TOPIC --mensajes=1000 --por-segundo=0
```

Vuelve a la consola de Dataflow: el *throughput* sube, la ráfaga se absorbe y el pipeline **no se detiene** por el 5% de veneno que lleva cada lote.

#### 4.3. Consultar los Datos Limpios en BigQuery
Los pagos aparecen en BigQuery **segundos** después de publicarse:

```bash
source env.sh

bq query --use_legacy_sql=false --nouse_cache "
SELECT
  COUNT(*) AS pagos,
  COUNTIF(reparado) AS autocurados,
  ROUND(SUM(monto_usd), 2) AS total_usd,
  ROUND(APPROX_QUANTILES(TIMESTAMP_DIFF(ingestado_en, event_time, MILLISECOND), 100)[OFFSET(50)] / 1000, 2) AS latencia_p50_seg,
  MAX(ingestado_en) AS ultimo_pago
FROM \`$PROJECT_ID.$DATASET.pagos\`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)"

bq query --use_legacy_sql=false --nouse_cache "
SELECT pais, metodo_pago, categoria_riesgo, COUNT(*) AS pagos, ROUND(SUM(monto_usd), 2) AS total_usd
FROM \`$PROJECT_ID.$DATASET.pagos\`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
GROUP BY pais, metodo_pago, categoria_riesgo
ORDER BY total_usd DESC
LIMIT 8"
```

Ejecuta la primera consulta varias veces: `pagos` y `ultimo_pago` crecen mientras el simulador publica. Observa también los **autocurados**: pagos que llegaron con formato incorrecto y que el escudo salvó.

> [!NOTE]
> La `latencia_p50_seg` de esta primera consulta sale alta (en la corrida de prueba, ~150 s) porque incluye los 1,000 mensajes de la Fase 2, que esperaron en la suscripción a que el pipeline existiera, y el arranque del worker. Pub/Sub no los perdió: los guardó hasta que hubo quien los leyera. Con el pipeline ya caliente, los pagos nuevos tardan pocos segundos.

> [!TIP]
> Fíjate en que ambas consultas filtran por `event_time`: como la tabla está particionada por esa columna, BigQuery solo lee la partición de hoy (Módulo 09).

#### 4.4. Inspeccionar la Cuarentena
Los rechazos se escriben en archivos por ventana de 1 minuto, así que aparecen **1 o 2 minutos** después de cada envío:

```bash
source env.sh

gcloud storage ls $BUCKET_CUARENTENA/rechazos/ | head -5

# Un rechazo de ejemplo, con su motivo y el mensaje original
gcloud storage cat "$BUCKET_CUARENTENA/rechazos/*" | head -n 1 | python3 -m json.tool

# Resumen de rechazos por motivo
gcloud storage cat "$BUCKET_CUARENTENA/rechazos/*" | python3 -c "
import collections, json, sys
motivos = collections.Counter(json.loads(linea)['motivo'] for linea in sys.stdin if linea.strip())
for motivo, cantidad in motivos.most_common():
    print(f'{motivo:22} {cantidad}')"
```

Cada archivo es una **bitácora de incidentes**: un equipo puede corregir los datos y volver a publicarlos, o usarlos para avisar al productor que está enviando basura.

#### 4.5. Reconciliación: ¿Se Perdió Algo?
La prueba definitiva de un pipeline confiable: **todo lo publicado debe estar en BigQuery o en cuarentena**. Espera un par de minutos tras el último envío para que se cierre la última ventana de cuarentena, y compara:

```bash
cd ~/workshop-gcp/lab10 && source env.sh

python3 - << EOF
import json, subprocess

publicado = json.load(open("resumen_simulador.json"))
esperado_bq = publicado.get("VALIDO", 0) + publicado.get("REPARABLE", 0)
esperado_cuarentena = publicado.get("TARDIO", 0) + publicado.get("VENENO", 0)

consulta = "SELECT COUNT(*) FROM \`$PROJECT_ID.$DATASET.pagos\` WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)"
en_bq = int(subprocess.run(["bq", "query", "--use_legacy_sql=false", "--nouse_cache", "--format=csv", consulta],
                           capture_output=True, text=True).stdout.split()[-1])
cuarentena = subprocess.run(["gcloud", "storage", "cat", "$BUCKET_CUARENTENA/rechazos/*"],
                            capture_output=True, text=True).stdout
en_cuarentena = sum(1 for linea in cuarentena.splitlines() if linea.strip())

print(f"Publicados por el simulador : {sum(publicado.values())}  {publicado}")
print(f"BigQuery    esperado {esperado_bq:5} | real {en_bq:5}")
print(f"Cuarentena  esperado {esperado_cuarentena:5} | real {en_cuarentena:5}")
print("RECONCILIADO: no se perdió ni se duplicó ningún pago" if (en_bq, en_cuarentena) == (esperado_bq, esperado_cuarentena)
      else "Aún no cuadra: espera 1 o 2 minutos (ventanas abiertas) y vuelve a ejecutar")
EOF
```

Con el modo **exactly-once** de Dataflow (el predeterminado) y la Storage Write API, los números cuadran exactamente, aunque Pub/Sub entregue algún mensaje duplicado: Dataflow lo deduplica.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO!** Un job de Dataflow en streaming **nunca termina solo** y cobra cada hora por sus workers aunque no reciba mensajes. Detenlo primero y espera a que termine antes de borrar el resto.

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab10 && source env.sh

# 1. Detener el job. "drain" termina de procesar lo pendiente; "cancel" lo detiene de inmediato
JOB_ID=$(gcloud dataflow jobs list --region=$REGION --status=active --filter="name=$JOB_NAME" --format="value(id)" | head -n 1)
[ -n "$JOB_ID" ] && gcloud dataflow jobs drain $JOB_ID --region=$REGION

# Esperar a que el job termine (Drained o Cancelled)
for i in $(seq 1 40); do
  ACTIVOS=$(gcloud dataflow jobs list --region=$REGION --status=active --filter="name=$JOB_NAME" --format="value(id)")
  [ -z "$ACTIVOS" ] && echo "Job detenido" && break
  echo "Intento $i: el job sigue drenando, reintentando en 15 s..."; sleep 15
done

# 2. Pub/Sub: suscripción y topic
gcloud pubsub subscriptions delete $SUSCRIPCION --quiet
gcloud pubsub topics delete $TOPIC --quiet

# 3. BigQuery: dataset con la tabla
bq rm -r -f -d $PROJECT_ID:$DATASET

# 4. Cloud Storage: buckets de staging y cuarentena
gcloud storage rm --recursive $BUCKET_DATAFLOW $BUCKET_CUARENTENA

# 5. Cuenta de servicio y su permiso a nivel de proyecto
gcloud projects remove-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_DATAFLOW" --role="roles/dataflow.worker" --condition=None --quiet > /dev/null
gcloud iam service-accounts delete $SA_DATAFLOW --quiet

# 6. Entorno virtual local
deactivate 2>/dev/null; rm -rf ~/workshop-gcp/lab10/.venv
```

> [!NOTE]
> Si el *drain* no termina en unos 10 minutos, fuerza la detención con `gcloud dataflow jobs cancel $JOB_ID --region=$REGION`. Los mensajes que el pipeline no alcanzó a confirmar seguirían en la suscripción, pero aquí ya no importa porque la borramos.

### Auditoría Final de Limpieza
Todas las secciones deben aparecer vacías:

```bash
source ~/workshop-gcp/lab10/env.sh

echo "=== Jobs de Dataflow activos ==="
gcloud dataflow jobs list --region=$REGION --status=active --format="value(id, name)"

echo "=== Pub/Sub del Lab 10 ==="
gcloud pubsub topics list --format="value(name)" | grep lab10
gcloud pubsub subscriptions list --format="value(name)" | grep lab10

echo "=== Dataset del Lab 10 ==="
bq ls | grep pagos_lab10

echo "=== Buckets del Lab 10 ==="
gcloud storage buckets list --format="value(name)" | grep lab10

echo "=== Cuenta de Servicio del Lab 10 ==="
gcloud iam service-accounts list --format="value(email)" | grep lab10
```

---

## 6. Conclusiones

En este décimo laboratorio construiste un pipeline de streaming que se defiende solo:
- **Pub/Sub** desacopló productores y consumidores: los 1,000 pagos publicados sin nadie escuchando esperaron intactos hasta que llegó Dataflow.
- Con **salidas laterales** de Apache Beam separaste en caliente los datos limpios de los venenosos, sin lanzar excepciones que atascaran el flujo.
- El pipeline **autocuró** los errores de formato recuperables y desvió a **cuarentena** lo irrecuperable y lo tardío, cada caso con su motivo.
- Probaste la lógica **en local, gratis y en segundos**, y desplegaste exactamente el mismo código en **Dataflow**.
- Escribiste en BigQuery con la **Storage Write API** y **reconciliaste** el sistema: ningún pago se perdió ni se duplicó.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Nueva Regla Antifraude**:
   Agrega una regla que envíe a cuarentena con motivo `MONTO_SOSPECHOSO` cualquier pago mayor a 20,000 USD. Escribe primero la prueba en `test_pipeline.py`, comprueba que falla, implementa la regla y verifica que pasa.

2. **Reto 2 — Reprocesar la Cuarentena**:
   Escribe un script que lea los archivos de cuarentena, filtre los `EVENTO_TARDIO`, actualice su `event_time` a la hora actual (simulando una corrección aprobada por el negocio) y los vuelva a publicar en el topic. Comprueba que llegan a BigQuery.

3. **Reto 3 — Alerta de Calidad de Datos**:
   Usando lo aprendido en el Módulo 08, crea en **Cloud Monitoring** una alerta sobre la métrica de elementos producidos por la salida `cuarentena` del paso `ValidarYEnriquecer`, para que te avise si el porcentaje de rechazos se dispara (un productor desplegó un bug).

---

## 8. Referencias Oficiales

- **Guía Rápida de Pub/Sub**: [https://docs.cloud.google.com/pubsub/docs/publish-receive-messages-console](https://docs.cloud.google.com/pubsub/docs/publish-receive-messages-console)
- **Referencia CLI: `gcloud pubsub`**: [https://docs.cloud.google.com/sdk/gcloud/reference/pubsub](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub)
- **Guía Rápida de Dataflow con Python**: [https://docs.cloud.google.com/dataflow/docs/guides/create-pipeline-python](https://docs.cloud.google.com/dataflow/docs/guides/create-pipeline-python)
- **Opciones de Pipeline de Dataflow**: [https://docs.cloud.google.com/dataflow/docs/reference/pipeline-options](https://docs.cloud.google.com/dataflow/docs/reference/pipeline-options)
- **Probar Pipelines de Beam (`TestPipeline`)**: [https://beam.apache.org/documentation/pipelines/test-your-pipeline/](https://beam.apache.org/documentation/pipelines/test-your-pipeline/)
- **Salidas Laterales en Beam (*Additional Outputs*)**: [https://beam.apache.org/documentation/programming-guide/#additional-outputs](https://beam.apache.org/documentation/programming-guide/#additional-outputs)
- **Conector BigQuery de Apache Beam (Storage Write API)**: [https://beam.apache.org/documentation/io/built-in/google-bigquery/](https://beam.apache.org/documentation/io/built-in/google-bigquery/)
- **Detener un Pipeline (Drain vs Cancel)**: [https://docs.cloud.google.com/dataflow/docs/guides/stopping-a-pipeline](https://docs.cloud.google.com/dataflow/docs/guides/stopping-a-pipeline)
