# Laboratorio 05: Contenedores Serverless con Artifact Registry, Cloud Build, Cloud Run y Cloud Functions Orientadas a Eventos

- **Duración estimada**: 85–90 minutos
- **Nivel**: Intermedio / Desarrollo Cloud-Native y Serverless
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud` CLI)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Construir, empaquetar y desplegar aplicaciones modernas **100% Serverless** en Google Cloud sin administrar ni una sola máquina virtual. A lo largo de este laboratorio crearás un repositorio privado de contenedores en **Artifact Registry**, compilarás una imagen Docker en la nube usando **Cloud Build**, desplegarás un microservicio en **Cloud Run** practicando despliegues progresivos (*Canary Traffic Splitting*) entre revisiones y, finalmente, desarrollarás dos **Cloud Functions (2nd Gen)**: una invocada por HTTP y otra disparada automáticamente por eventos cuando se sube un archivo a un Bucket de **Cloud Storage**.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Crear y gestionar repositorios privados de imágenes Docker en **Artifact Registry**.
2. Escribir una aplicación web containerizada (`Dockerfile`) y compilarla remotamente con **Cloud Build (`gcloud builds submit`)** sin consumir recursos locales.
3. Desplegar servicios en **Cloud Run**, configurar variables de entorno, límites de escalado (`--min-instances=0`, `--max-instances`) y concurrencia.
4. Gestionar **Revisiones Inmutables** en Cloud Run y aplicar **División de Tráfico (*Traffic Splitting*)** para lanzamientos *Canary* (50% / 50%) y *Rollbacks* instantáneos.
5. Desplegar una **Cloud Function (2nd Gen) HTTP** directamente desde código fuente Python sin escribir un `Dockerfile`.
6. Construir una arquitectura **Orientada a Eventos (*Event-Driven*)** conectando un Bucket de Cloud Storage con una **Cloud Function** mediante **Eventarc**, e inspeccionar su ejecución asíncrona en **Cloud Logging**.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado de este laboratorio: $0.00 USD (Cubierto al 100% por el Free Tier mensual)**

| Servicio Utilizado | Nivel Gratuito Mensual (*Always Free Tier*) | Consumo en este Laboratorio | Costo Estimado |
| :--- | :--- | :--- | :--- |
| **Cloud Build** | Primeros 2,500 minutos de compilación al mes gratis (pool predeterminado `e2-standard-2`; ver [precios](https://cloud.google.com/build/pricing)) | ~4 minutos de compilación (imagen + 2 funciones) | **$0.00 USD** |
| **Artifact Registry** | Primeros 0.5 GB de almacenamiento por mes gratis | ~50 MB durante 1 hora (se borra al final) | **$0.00 USD** |
| **Cloud Run** | 2 millones de peticiones, 180,000 vCPU-seg y 360,000 GiB-seg gratis/mes (escala a cero sin tráfico) | ~30 peticiones de prueba | **$0.00 USD** |
| **Cloud Run functions (2nd Gen)** | Incluido en la capa gratuita de Cloud Run / Cloud Functions (2 millones de invocaciones/mes) | ~5 invocaciones | **$0.00 USD** |
| **Cloud Storage Bucket** | 5 GB/mes gratis en `us-central1` | 1 archivo de prueba de < 1 KB | **$0.00 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno y Habilitación de APIs en Cloud Shell (10 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Ejecuta el siguiente bloque para configurar tus variables de entorno y habilitar las APIs de **Artifact Registry**, **Cloud Build**, **Cloud Run**, **Cloud Functions** y **Eventarc**:

```bash
mkdir -p ~/workshop-gcp/lab05/app-cloudrun ~/workshop-gcp/lab05/fn-http ~/workshop-gcp/lab05/fn-storage
cd ~/workshop-gcp/lab05

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export PROJECT_NUMBER="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')"
export REGION="us-central1"
export IMAGE_URI="us-central1-docker.pkg.dev/${PROJECT_ID}/repo-contenedores-lab05/api-serverless:v1"
export EVENT_BUCKET="gs://${PROJECT_ID}-bandeja-entrada-lab05"
EOF
source env.sh

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION
gcloud config set functions/region $REGION

# Habilitar todas las APIs necesarias para el ecosistema Serverless y Eventos
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  eventarc.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com

echo "Proyecto: $PROJECT_ID ($PROJECT_NUMBER) | Región: $REGION"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab05 && source env.sh`

#### 1.1. Otorgar Permisos a la Cuenta de Servicio que Compila y Dispara Eventos
Desde mayo–junio de 2024, **Cloud Build usa la cuenta de servicio predeterminada de Compute Engine** (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) para compilar. Además, esa misma cuenta es la identidad por defecto del *trigger* de Eventarc del Paso 6. En organizaciones creadas desde mayo de 2024, la política *secure by default* `iam.automaticIamGrantsForDefaultServiceAccounts` impide que esa cuenta reciba el rol `Editor`, y las compilaciones y los triggers fallan por falta de permisos.

Para que el laboratorio funcione en **cualquier** tipo de proyecto (personal, universitario o corporativo), otorguemos explícitamente los roles mínimos que indica la documentación oficial:

```bash
export COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for ROLE in roles/run.builder roles/cloudbuild.builds.builder roles/run.invoker roles/eventarc.eventReceiver; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="$ROLE" \
    --condition=None > /dev/null && echo "Rol $ROLE otorgado a $COMPUTE_SA"
done
```

| Rol | Para qué lo necesita |
| :--- | :--- |
| `roles/run.builder` y `roles/cloudbuild.builds.builder` | Compilar la imagen (Paso 2) y las funciones (Pasos 5 y 6), y publicarlas en Artifact Registry |
| `roles/run.invoker` | Que el *trigger* de Eventarc pueda invocar la función del Paso 6 |
| `roles/eventarc.eventReceiver` | Que el *trigger* pueda recibir eventos de Cloud Storage |

*(Los permisos de IAM tardan normalmente unos 2 minutos en propagarse. Si la primera compilación falla con un error de permisos, espera un momento y vuelve a ejecutarla).*

---

### Paso 2: Creación del Repositorio en Artifact Registry y Compilación con Cloud Build (15 min)

#### 2.1. Crear un Repositorio Privado de Docker en Artifact Registry
```bash
gcloud artifacts repositories create repo-contenedores-lab05 \
  --repository-format=docker \
  --location=$REGION \
  --description="Repositorio privado de imagenes Docker para el Laboratorio 05"

# Verificar el repositorio creado
gcloud artifacts repositories list --location=$REGION
```

La ruta oficial de nuestro registro privado en Google Cloud tiene el formato:
`${REGION}-docker.pkg.dev/${PROJECT_ID}/repo-contenedores-lab05`

#### 2.2. Crear la Aplicación Web en Python (Flask) y su `Dockerfile`
Crearemos un microservicio web que devuelve en formato JSON la versión desplegada, el nombre de la revisión de Cloud Run (`K_REVISION`, inyectada automáticamente por Cloud Run) y el contenedor que respondió:

```bash
cd ~/workshop-gcp/lab05/app-cloudrun

# 1. Crear el archivo de dependencias requirements.txt
cat << 'EOF' > requirements.txt
Flask==3.1.3
gunicorn==23.0.0
EOF

# 2. Crear el código de la aplicación main.py (Versión 1.0)
cat << 'EOF' > main.py
import os
import socket
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({
        "servicio": "API Serverless en Google Cloud Run",
        "version_app": os.environ.get("APP_VERSION", "v1.0-estable"),
        "revision_cloud_run": os.environ.get("K_REVISION", "local"),
        "instancia_contenedor": socket.gethostname(),
        "mensaje": "Escala a cero automaticamente cuando no hay trafico ($0 USD)"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
EOF

# 3. Crear el Dockerfile optimizado para producción con Gunicorn
cat << 'EOF' > Dockerfile
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=True
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
EOF
```

#### 2.3. Compilar la Imagen en la Nube con Cloud Build y guardarla en Artifact Registry
En lugar de usar `docker build` local y gastar ancho de banda subiendo capas, le enviaremos el código a **Cloud Build** para que lo compile en la nube y deposite la imagen `v1` directamente en nuestro **Artifact Registry**:

```bash
# $IMAGE_URI ya está definido en env.sh (Paso 1)
echo "Imagen a construir: $IMAGE_URI"

gcloud builds submit --tag $IMAGE_URI .
```

Verifica que la imagen ya esté almacenada dentro de tu repositorio de Artifact Registry:

```bash
gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/repo-contenedores-lab05
```

---

### Paso 3: Despliegue del Contenedor en Google Cloud Run (15 min)

Ahora desplegaremos nuestra imagen `v1` como un servicio de **Cloud Run** llamado `api-serverless-lab05`:

```bash
gcloud run deploy api-serverless-lab05 \
  --image=$IMAGE_URI \
  --region=$REGION \
  --allow-unauthenticated \
  --port=8080 \
  --min-instances=0 \
  --max-instances=3 \
  --concurrency=80 \
  --set-env-vars="APP_VERSION=v1.0-estable" \
  --revision-suffix=v1
```

> [!NOTE]
> **¿Qué hacen estas banderas clave?**
> - `--allow-unauthenticated`: Hace que el endpoint HTTPS sea público en Internet (si usas `--no-allow-unauthenticated`, el servicio queda privado y exige un token de identidad IAM para ser invocado).
> - `--min-instances=0`: Habilita el **escalado a cero** para no cobrar nada cuando no hay peticiones.
> - `--revision-suffix=v1`: Le da un nombre legible (`api-serverless-lab05-v1`) a esta primera revisión inmutable.

#### 3.1. Probar el Servicio de Cloud Run
Capturaremos la URL HTTPS generada por Cloud Run y le haremos una petición:

```bash
export SERVICE_URL=$(gcloud run services describe api-serverless-lab05 --region=$REGION --format="value(status.url)")
echo "URL pública de tu servicio Cloud Run: $SERVICE_URL"

# Hacer una petición HTTP GET y formatear el JSON con jq
curl -s $SERVICE_URL | jq .
```

Verás una respuesta instantánea como:
```json
{
  "instancia_contenedor": "localhost",
  "mensaje": "Escala a cero automaticamente cuando no hay trafico ($0 USD)",
  "revision_cloud_run": "api-serverless-lab05-v1",
  "servicio": "API Serverless en Google Cloud Run",
  "version_app": "v1.0-estable"
}
```

---

### Paso 4: Revisiones Inmutables y División de Tráfico Canary (Traffic Splitting) (15 min)

Supongamos que tu equipo lanza una nueva versión **`v2.0-canary`** con una nueva funcionalidad, pero por prudencia no quieres enviársela de golpe al 100% de tus clientes.

#### 4.1. Desplegar una Segunda Revisión (`v2`) con `--no-traffic` y Etiqueta de Prueba
En Cloud Run ni siquiera necesitamos recompilar la imagen si queremos probar una nueva configuración o versión mediante variables de entorno, o podemos desplegar una revisión nueva indicando **`--no-traffic`** para que reciba **0% del tráfico de producción** inicialmente:

```bash
gcloud run deploy api-serverless-lab05 \
  --image=$IMAGE_URI \
  --region=$REGION \
  --set-env-vars="APP_VERSION=v2.0-canary-nueva-interfaz" \
  --revision-suffix=v2 \
  --no-traffic \
  --tag=canary
```

Observa la salida del comando:
1. La URL principal (`$SERVICE_URL`) **sigue enviando el 100% del tráfico a `v1`**.
2. Pero gracias a `--tag=canary`, Cloud Run te creó una **URL exclusiva de prueba** (`https://canary---api-serverless-lab05-...run.app`) que apunta directamente a `v2`.

Listemos las revisiones activas de nuestro servicio:

```bash
gcloud run revisions list --service=api-serverless-lab05 --region=$REGION
```

#### 4.2. Dividir el Tráfico en Producción: 50% a `v1` y 50% a `v2` (Canary Release)
Ahora dividamos el tráfico del endpoint principal mitad y mitad entre ambas revisiones:

```bash
gcloud run services update-traffic api-serverless-lab05 \
  --region=$REGION \
  --to-revisions="api-serverless-lab05-v1=50,api-serverless-lab05-v2=50"
```

Comprobemos el balanceo en tiempo real haciendo 6 peticiones seguidas a la URL principal `$SERVICE_URL`:

```bash
for i in {1..6}; do
  curl -s $SERVICE_URL | jq -c '{version: .version_app, revision: .revision_cloud_run}'
done
```

¡Observa cómo aproximadamente la mitad de las peticiones responden con **`v1.0-estable`** y la otra mitad con **`v2.0-canary-nueva-interfaz`**!

**Verificación en la Consola Web**:
- Ve a `☰` -> **Cloud Run** -> haz clic en **`api-serverless-lab05`** -> pestaña **Revisiones (Revisions)**. Verás gráficamente cómo el tráfico está dividido **50% / 50%** entre las dos revisiones.

#### 4.3. Promover el 100% del Tráfico a la última revisión (`v2`)
Una vez validado que `v2` no tiene errores, enviamos el 100% del tráfico a la última revisión:

```bash
gcloud run services update-traffic api-serverless-lab05 \
  --region=$REGION \
  --to-latest
```

---

### Paso 5: Creación de una Cloud Function (2nd Gen) HTTP desde Código Fuente (15 min)

Ahora pasaremos al modelo **FaaS (*Function as a Service*)** con **Cloud Run functions (2nd Gen)**. Aquí no escribiremos ningún `Dockerfile`: solo entregaremos una función en Python (`main.py`) y Google Cloud se encargará de todo lo demás.

#### 5.1. Escribir el Código de la Función HTTP (Calculadora de Impuestos / Conversor)
```bash
cd ~/workshop-gcp/lab05/fn-http

cat << 'EOF' > requirements.txt
functions-framework==3.*
EOF

cat << 'EOF' > main.py
import functions_framework
from flask import jsonify

@functions_framework.http
def calcular_cotizacion(request):
    """Función HTTP Serverless que calcula el costo total con impuestos."""
    request_json = request.get_json(silent=True)
    request_args = request.args

    monto = 100.0
    cliente = "Estudiante GCP"

    if request_json and "monto" in request_json:
        monto = float(request_json["monto"])
        cliente = request_json.get("cliente", cliente)
    elif request_args and "monto" in request_args:
        monto = float(request_args["monto"])
        cliente = request_args.get("cliente", cliente)

    impuesto = round(monto * 0.19, 2)
    total = round(monto + impuesto, 2)

    return jsonify({
        "cliente": cliente,
        "subtotal_usd": monto,
        "impuesto_19_usd": impuesto,
        "total_usd": total,
        "motor": "Cloud Run functions (2nd Gen)"
    })
EOF
```

#### 5.2. Desplegar la Función HTTP de 2.ª Generación (`--gen2`)
```bash
gcloud functions deploy fn-cotizador-http \
  --gen2 \
  --runtime=python313 \
  --region=$REGION \
  --source=. \
  --entry-point=calcular_cotizacion \
  --trigger-http \
  --allow-unauthenticated
```
*(El despliegue tarda ~60-90 segundos mientras Cloud Build empaqueta la función con Buildpacks).*

> [!NOTE]
> **`gcloud functions deploy` vs `gcloud run deploy --function`**: desde 2024 las Cloud Functions 2nd Gen se llaman **Cloud Run functions** y se ejecutan como servicios de Cloud Run. Ambos comandos son válidos. `gcloud functions deploy --gen2` (el que usamos aquí) crea la función y su *trigger* en un solo paso. La documentación más reciente usa el flujo nativo de Cloud Run: `gcloud run deploy NOMBRE --source . --function=PUNTO_DE_ENTRADA --base-image=python313 --region=$REGION` y, para eventos, un *trigger* separado con `gcloud eventarc triggers create`. Lo exploramos en el Reto 4.

#### 5.3. Invocar la Función HTTP pasando parámetros
```bash
export FN_URL=$(gcloud functions describe fn-cotizador-http --region=$REGION --format="value(serviceConfig.uri)")
echo "URL de tu Cloud Function: $FN_URL"

# Probar enviando una petición POST con JSON
curl -s -X POST $FN_URL \
  -H "Content-Type: application/json" \
  -d '{"cliente": "Empresa Cloud S.A.", "monto": 250}' | jq .
```

---

### Paso 6: Creación de una Cloud Function Orientada a Eventos (Trigger de Cloud Storage) (15 min)

El caso de uso más potente de **Cloud Functions** es reaccionar automáticamente a eventos de la infraestructura. Crearemos un bucket de Cloud Storage y una función que se ejecute **sola** cada vez que un usuario suba un archivo nuevo a ese bucket.

#### 6.1. Otorgar permiso al Agente de Servicio de Cloud Storage para publicar eventos
Para que Cloud Storage pueda notificar eventos a **Eventarc** en tu proyecto, su agente de servicio interno necesita el rol `roles/pubsub.publisher`:

```bash
export GCS_SERVICE_ACCOUNT=$(gcloud storage service-agent --project=$PROJECT_ID)

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${GCS_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"
```

#### 6.2. Crear el Bucket Disparador de Eventos
```bash
# $EVENT_BUCKET ya está definido en env.sh (Paso 1)
gcloud storage buckets create $EVENT_BUCKET \
  --location=$REGION \
  --uniform-bucket-level-access
```

#### 6.3. Escribir y Desplegar la Función Impulsada por CloudEvents
```bash
cd ~/workshop-gcp/lab05/fn-storage

cat << 'EOF' > requirements.txt
functions-framework==3.*
cloudevents==1.*
EOF

cat << 'EOF' > main.py
import functions_framework
from cloudevents.http import CloudEvent

@functions_framework.cloud_event
def procesar_archivo_nuevo(cloud_event: CloudEvent):
    """Se dispara automáticamente cuando se sube un archivo al Bucket."""
    data = cloud_event.data
    bucket = data.get("bucket")
    nombre_archivo = data.get("name")
    tamano_bytes = data.get("size")
    tipo_contenido = data.get("contentType")
    fecha_creacion = data.get("timeCreated")

    print(f"[EVENTO DETECTADO] Nuevo archivo subido a gs://{bucket}/{nombre_archivo}")
    print(f"[METADATOS] Tamano: {tamano_bytes} bytes | Tipo: {tipo_contenido} | Fecha: {fecha_creacion}")
EOF

# Desplegar la función conectada al evento 'finalized' (creación de objeto) del bucket
gcloud functions deploy fn-auditor-archivos \
  --gen2 \
  --runtime=python313 \
  --region=$REGION \
  --source=. \
  --entry-point=procesar_archivo_nuevo \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=${PROJECT_ID}-bandeja-entrada-lab05"
```

> [!NOTE]
> - **Si es tu primer trigger de Eventarc en el proyecto**, el despliegue puede fallar con un error de permisos del *Eventarc Service Agent* mientras Google lo aprovisiona. Es normal: espera uno o dos minutos y **vuelve a ejecutar el mismo comando**.
> - El bucket debe estar en la **misma región** que el *trigger* (`us-central1` en ambos casos).
> - Un *trigger* recién creado puede tardar **hasta 2 minutos** en quedar operativo.

#### 6.4. Probar el Disparo Automático Subiendo un Archivo al Bucket
Subamos un archivo de prueba a nuestro bucket `$EVENT_BUCKET` y verifiquemos en los registros (**Cloud Logging**) que la función despertó sola, procesó el evento y volvió a escalar a cero:

```bash
echo "Factura #99812 - Cliente: Corporacion Andina - Monto: $4,200 USD" > factura-99812.txt
gcloud storage cp factura-99812.txt $EVENT_BUCKET/

# Reintentar la lectura de logs hasta que aparezca el evento (máximo ~3 minutos)
for i in $(seq 1 12); do
  gcloud functions logs read fn-auditor-archivos --gen2 --region=$REGION --limit=10 2>/dev/null \
    | grep "EVENTO DETECTADO" && break
  echo "Intento $i: el evento aún no aparece en Cloud Logging, reintentando en 15 s..."; sleep 15
done

# Ver los últimos logs completos de la función
gcloud functions logs read fn-auditor-archivos \
  --gen2 \
  --region=$REGION \
  --limit=10
```

¡Observa en la salida de los logs tu mensaje **`[EVENTO DETECTADO] Nuevo archivo subido a gs://.../factura-99812.txt`** con su tamaño exacto en bytes y tipo `text/plain`!

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

Ejecuta los siguientes comandos en **Cloud Shell** para eliminar las funciones, el servicio de Cloud Run, el repositorio de Artifact Registry y los buckets creados:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab05 && source env.sh

# 1. Eliminar las dos Cloud Functions (2nd Gen) y su trigger de Eventarc
gcloud functions delete fn-auditor-archivos --region=$REGION --quiet
gcloud functions delete fn-cotizador-http --region=$REGION --quiet

# 2. Eliminar el Servicio de Cloud Run
gcloud run services delete api-serverless-lab05 --region=$REGION --quiet

# 3. Eliminar el Repositorio de Contenedores en Artifact Registry (y sus imágenes)
gcloud artifacts repositories delete repo-contenedores-lab05 --location=$REGION --quiet

# 4. Eliminar el Bucket de entrada de eventos y su contenido
gcloud storage rm --recursive $EVENT_BUCKET

# 5. Eliminar los artefactos que Google crea automáticamente al compilar funciones y fuentes:
#    - Repositorio 'gcf-artifacts' de Artifact Registry (imágenes de las funciones)
#    - Buckets de código fuente de Cloud Build y Cloud Functions
#    ⚠️ Omite este paso si en este proyecto tienes OTRAS funciones o compilaciones que quieras conservar.
gcloud artifacts repositories delete gcf-artifacts --location=$REGION --quiet 2>/dev/null || echo "Repositorio gcf-artifacts no encontrado"
for B in $(gcloud storage buckets list --format="value(name)" | grep -E "^(gcf-v2-|${PROJECT_ID}_cloudbuild)"); do
  echo "Eliminando bucket automático gs://$B"
  gcloud storage rm --recursive "gs://$B"
done
```

### Auditoría Final de Limpieza
Verifica que no queden servicios ni repositorios activos:

```bash
echo "=== Servicios Cloud Run / Cloud Functions 2nd Gen ==="
gcloud run services list

echo "=== Repositorios Artifact Registry (no debe quedar repo-contenedores-lab05 ni gcf-artifacts) ==="
gcloud artifacts repositories list --location=$REGION

echo "=== Buckets Cloud Storage ==="
gcloud storage buckets list
```

---

## 6. Conclusiones

En este quinto laboratorio has construido aplicaciones nativas de la nube utilizando el paradigma **Serverless**:
- Empaquetaste una aplicación en contenedor con **Cloud Build** y la almacenaste de forma privada en **Artifact Registry** sin necesitar Docker local.
- Desplegaste un microservicio en **Cloud Run** con HTTPS automático y escalado a cero (`--min-instances=0`), y ejecutaste una estrategia de lanzamiento **Canary (50%/50%)** entre revisiones inmutables sin tiempo de inactividad.
- Comprendiste la diferencia práctica entre desplegar contenedores personalizados en **Cloud Run** y desplegar funciones puras en **Cloud Run functions (2nd Gen)**, tanto por invocación síncrona HTTP como mediante arquitecturas asíncronas **Orientadas a Eventos (*Event-Driven*)** con Cloud Storage y Eventarc.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Servicio Cloud Run Privado Invocado con Token de Identidad IAM**:
   Despliega un servicio en Cloud Run usando **`--no-allow-unauthenticated`** en lugar de `--allow-unauthenticated`. Comprueba que al hacer `curl $URL` normal devuelve `Error 403 Forbidden`, y luego investiga cómo pasar el encabezado `-H "Authorization: Bearer $(gcloud auth print-identity-token)"` en `curl` para autenticarte de forma segura.

2. **Reto 2 — Inyección de un Secreto de Secret Manager en Cloud Run**:
   En lugar de pasar un valor sensible en texto plano con `--set-env-vars`, crea un secreto en **Secret Manager** y revisa `gcloud run deploy --help` para descubrir cómo usar la bandera **`--set-secrets="MI_API_KEY=nombre-secreto:latest"`** para que Cloud Run monte el secreto automáticamente en tu contenedor.

3. **Reto 3 — Ejecución de una Tarea por Lotes con Cloud Run Jobs**:
   Investiga el comando **`gcloud run jobs create`** y **`gcloud run jobs execute`**. Crea un *Job* rápido que utilice la imagen pública `python:3.13-slim` y ejecute el comando `--command="python3"` con `--args="-c,import time; print('Iniciando proceso batch...'); time.sleep(5); print('Proceso completado con exito!')"` verificando cómo corre y se apaga al finalizar.

4. **Reto 4 — Desplegar una Función con el Flujo Nativo de Cloud Run**:
   Vuelve a desplegar la función HTTP del Paso 5 con `gcloud run deploy fn-cotizador-run --source=. --function=calcular_cotizacion --base-image=python313 --region=$REGION --allow-unauthenticated` (desde la carpeta `fn-http`). Compara en la consola de Cloud Run el servicio resultante con `fn-cotizador-http` y elimínalo al terminar con `gcloud run services delete fn-cotizador-run --region=$REGION`.

---

## 8. Referencias Oficiales

- **Referencia CLI: `gcloud run deploy` y `update-traffic`**: [https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy)
- **Referencia CLI: `gcloud functions deploy` (2nd Gen)**: [https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy)
- **Referencia CLI: `gcloud artifacts repositories`**: [https://docs.cloud.google.com/sdk/gcloud/reference/artifacts/repositories](https://docs.cloud.google.com/sdk/gcloud/reference/artifacts/repositories)
- **Tutorial de Cloud Functions con Eventos de Cloud Storage**: [https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage](https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage)
