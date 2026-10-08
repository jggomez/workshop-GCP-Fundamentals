# Laboratorio 08: Observabilidad con Cloud Logging y Cloud Monitoring + Automatización de Infraestructura como Código con Terraform

- **Duración estimada**: 85–90 minutos
- **Nivel**: Intermedio–Avanzado / SRE, Observabilidad y DevOps (IaC)
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud` + `terraform` CLI preinstalado)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Unificar las prácticas modernas de **DevOps e Ingeniería de Confiabilidad (SRE)** en Google Cloud Platform. En la primera mitad del laboratorio escribirás y desplegarás una arquitectura completa (Red VPC, Subred, Firewall, Bucket de Auditoría y Servidor Web en Compute Engine) de forma **100% declarativa utilizando Terraform** desde Cloud Shell. En la segunda mitad instrumentarás la **Observabilidad** sobre esa infraestructura utilizando **Cloud Logging** y **Cloud Monitoring**: emitirás registros estructurados JSON, construirás **Métricas basadas en Logs (*Log-based Metrics*)**, configurarás un **Sumidero de exportación (*Log Sink*)** hacia Cloud Storage y crearás **Sondas de Disponibilidad Global (*Uptime Checks*)** con canales de notificación, para finalmente destruir toda la infraestructura con un solo comando `terraform destroy`.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Escribir código declarativo de **Infraestructura como Código (IaC)** en lenguaje HCL de **Terraform** (`main.tf`, `variables.tf`, `outputs.tf`) utilizando el proveedor oficial `hashicorp/google`.
2. Ejecutar el flujo de vida completo de Terraform en Cloud Shell (`terraform init`, `plan`, `apply` y `destroy`) comprendiendo cómo resuelve automáticamente el grafo de dependencias entre recursos.
3. Escribir y consultar **Logs Estructurados (JSON)** con distintos niveles de severidad (`INFO`, `WARNING`, `ERROR`, `CRITICAL`) en **Cloud Logging** usando el lenguaje de consulta **LQL (*Logging Query Language*)**.
4. Crear **Métricas Basadas en Registros (*Log-based Metrics*)** para transformar eventos de error en series de tiempo numéricas.
5. Configurar un **Log Sink (Sumidero de Registros)** en el *Log Router* para archivar automáticamente registros críticos en un Bucket de Cloud Storage.
6. Crear **Uptime Checks (Comprobaciones de Disponibilidad)** y **Canales de Notificación** en **Cloud Monitoring** para vigilar servicios web en tiempo real.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado por ejecutar este laboratorio durante 90 minutos: < $0.01 USD (Prácticamente Gratuito)**

| Recurso / Servicio Utilizado | Nivel Gratuito / Precio de Referencia | Consumo en este Laboratorio | Costo Estimado |
| :--- | :--- | :--- | :--- |
| **Terraform en Cloud Shell** | Herramienta Open Source preinstalada gratis en Cloud Shell | Ejecución local en Cloud Shell | **$0.000 USD** |
| **Cloud Logging & Cloud Monitoring** | Primeros 50 GiB de logs y métricas de GCP al mes **Gratuitos** | Unos pocos kilobytes de logs y 1 Uptime Check | **$0.000 USD** |
| **Infraestructura desplegada por Terraform** | 1 VPC + 1 Bucket + 1 VM `e2-micro` (~$0.0084/hora) | Encendida durante ~40 minutos y destruida con `terraform destroy` | **~$0.006 USD** |
| **TOTAL ESTIMADO DE LA SESIÓN** | **Ejecutando la limpieza al finalizar el laboratorio** | — | **~$0.006 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno y Habilitación de APIs en Cloud Shell (5 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Verifica que `terraform` ya viene preinstalado en tu Cloud Shell y habilita las APIs de **Compute Engine**, **Cloud Storage**, **Cloud Logging** y **Cloud Monitoring**:

```bash
mkdir -p ~/workshop-gcp/lab08/terraform-gcp
cd ~/workshop-gcp/lab08/terraform-gcp

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en ../env.sh (fuera de la carpeta de Terraform)
cat > ../env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export USER_EMAIL="$(gcloud config get-value account 2>/dev/null)"
export REGION="us-central1"
export ZONE="us-central1-a"
EOF
source ../env.sh

gcloud config set project $PROJECT_ID

# Verificar versión de Terraform preinstalada en Cloud Shell
terraform -version

# Habilitar las APIs necesarias
gcloud services enable \
  compute.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

echo "Entorno listo en el proyecto: $PROJECT_ID"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab08/terraform-gcp && source ../env.sh`. El estado de Terraform (`terraform.tfstate`) vive en esa carpeta dentro de tu `$HOME` persistente, así que `terraform destroy` seguirá funcionando.

---

### Paso 2: Infraestructura como Código (IaC) con Terraform (25 min)

En lugar de ejecutar 6 comandos imperativos distintos de `gcloud` para crear una red, una subred, dos reglas de firewall, un bucket y una máquina virtual, declararemos toda nuestra arquitectura en tres archivos limpios de **Terraform**: `variables.tf`, `main.tf` y `outputs.tf`.

#### 2.1. Crear el Archivo de Variables (`variables.tf`)
```bash
cat << 'EOF' > variables.tf
variable "project_id" {
  description = "ID del proyecto de Google Cloud"
  type        = string
}

variable "region" {
  description = "Region para los recursos de GCP"
  default     = "us-central1"
}

variable "zone" {
  description = "Zona para la maquina virtual"
  default     = "us-central1-a"
}
EOF
```

#### 2.2. Crear la Arquitectura Declarativa Principal (`main.tf`)
Observa cómo en `main.tf` los recursos hacen referencia unos a otros (por ejemplo, `google_compute_subnetwork.subred_iac.id`). Gracias a esas referencias, **Terraform deduce automáticamente en qué orden exacto debe crearlos y en qué orden inverso debe destruirlos**:

```bash
cat << 'EOF' > main.tf
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# 1. Red VPC Personalizada creada por codigo
resource "google_compute_network" "vpc_iac" {
  name                    = "vpc-terraform-lab08"
  auto_create_subnetworks = false
  description             = "Red VPC gestionada 100% con Terraform"
}

# 2. Subred Regional dentro de la VPC
resource "google_compute_subnetwork" "subred_iac" {
  name          = "subnet-terraform-us"
  ip_cidr_range = "10.80.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_iac.id
}

# 3. Regla de Firewall para permitir HTTP (Puerto 80) al servidor monitoreado
resource "google_compute_firewall" "fw_http_iac" {
  name    = "fw-allow-http-terraform"
  network = google_compute_network.vpc_iac.name

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["web-monitoreado"]
}

# 3b. Regla de Firewall para administrar la VM por SSH solo a traves del tunel de Cloud IAP
resource "google_compute_firewall" "fw_ssh_iap" {
  name    = "fw-allow-ssh-iap-terraform"
  network = google_compute_network.vpc_iac.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["web-monitoreado"]
}

# 4. Bucket de Cloud Storage para archivar Logs Criticos de Auditoria
resource "google_storage_bucket" "bucket_logs" {
  name                        = "${var.project_id}-logs-auditoria-lab08"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  labels = {
    administrado_por = "terraform"
    laboratorio      = "lab08"
  }
}

# 5. Maquina Virtual con Servidor Web que sera vigilado por Cloud Monitoring
resource "google_compute_instance" "vm_web_iac" {
  name         = "vm-monitoreada-lab08"
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["web-monitoreado"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subred_iac.id
    access_config {
      # Asigna IP publica efimera para que los Uptime Checks globales puedan consultarla
    }
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update
    apt-get install -y nginx
    cat <<HTML > /var/www/html/index.html
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>SRE & IaC Lab 08</title></head>
    <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
      <h1>Infraestructura Desplegada con Terraform</h1>
      <p>Estado del Servicio: <b>OPERATIVO (200 OK)</b></p>
      <p>Vigilado por Google Cloud Observability</p>
    </body>
    </html>
    HTML
    systemctl restart nginx
  EOT

  labels = {
    administrado_por = "terraform"
    entorno          = "produccion"
  }
}
EOF
```

#### 2.3. Crear el Archivo de Valores de Salida (`outputs.tf`)
Los `outputs` le piden a Terraform que al terminar el despliegue nos imprima datos clave (como la dirección IP pública asignada a la máquina virtual):

```bash
cat << 'EOF' > outputs.tf
output "vm_nombre" {
  value = google_compute_instance.vm_web_iac.name
}

output "vm_ip_publica" {
  value = google_compute_instance.vm_web_iac.network_interface[0].access_config[0].nat_ip
}

output "url_servidor_web" {
  value = "http://${google_compute_instance.vm_web_iac.network_interface[0].access_config[0].nat_ip}"
}

output "bucket_auditoria_uri" {
  value = google_storage_bucket.bucket_logs.url
}
EOF
```

#### 2.4. Ejecutar el Ciclo de Vida de Terraform (`init`, `plan`, `apply`)
```bash
# 1. Inicializar Terraform (descarga el plugin oficial de Google Cloud)
terraform init

# 2. Validar la sintaxis de nuestros archivos .tf
terraform validate

# 3. Generar el Plan de Ejecución (verás "Plan: 6 to add, 0 to change, 0 to destroy")
terraform plan -var="project_id=${PROJECT_ID}"

# 4. Aplicar los cambios reales en Google Cloud
terraform apply -var="project_id=${PROJECT_ID}" -auto-approve
```

¡Observa la velocidad y limpieza de Terraform! En uno o dos minutos creó los 6 recursos interconectados y te mostró los `Outputs` finales.

Guarda la IP pública de la VM recién creada por Terraform en una variable de entorno y comprueba tras unos 30 segundos que Nginx ya responde:

```bash
export VM_IP=$(terraform output -raw vm_ip_publica)
echo "export VM_IP=\"$VM_IP\"" >> ../env.sh
echo "IP del servidor creado por Terraform: $VM_IP"

# Reintentar hasta que el startup-script termine de instalar Nginx (máximo ~3 minutos)
for i in $(seq 1 18); do
  curl -s --max-time 5 http://$VM_IP | grep -q "OPERATIVO" && break
  echo "Intento $i: Nginx aún no responde, reintentando en 10 s..."; sleep 10
done
curl http://$VM_IP
```

> [!TIP]
> **Demostración de Idempotencia de IaC**: Si vuelves a ejecutar ahora mismo `terraform plan -var="project_id=${PROJECT_ID}"`, verás que Terraform consulta la API de GCP, compara con su archivo `terraform.tfstate` y responde: **`No changes. Your infrastructure matches the configuration.`**

---

### Paso 3: Emisión y Consulta de Logs Estructurados en Cloud Logging (15 min)

Ahora simulemos que nuestro sistema de pagos en producción emite registros estructurados en formato **JSON** con distintas severidades (`INFO`, `WARNING`, `ERROR`, `CRITICAL`) hacia **Cloud Logging**.

#### 3.1. Escribir Logs Estructurados con `gcloud logging write`
```bash
# 1. Emitir un evento normal (INFO)
gcloud logging write log-pagos-lab08 \
  '{"transaccion_id": "TX-101", "modulo": "pasarela-pagos", "monto_usd": 150.0, "mensaje": "Pago procesado correctamente"}' \
  --payload-type=json \
  --severity=INFO

# 2. Emitir una advertencia de latencia alta (WARNING)
gcloud logging write log-pagos-lab08 \
  '{"transaccion_id": "TX-102", "modulo": "pasarela-pagos", "latencia_ms": 2850, "mensaje": "Respuesta lenta del proveedor bancario"}' \
  --payload-type=json \
  --severity=WARNING

# 3. Emitir dos errores críticos de fallo de conexión con el banco (ERROR y CRITICAL)
gcloud logging write log-pagos-lab08 \
  '{"transaccion_id": "TX-103", "modulo": "pasarela-pagos", "codigo_error": "ERR_BANCO_TIMEOUT", "mensaje": "Fallo al procesar cobro de tarjeta"}' \
  --payload-type=json \
  --severity=ERROR

gcloud logging write log-pagos-lab08 \
  '{"transaccion_id": "TX-104", "modulo": "pasarela-pagos", "codigo_error": "ERR_BANCO_TIMEOUT", "mensaje": "Caida total del gateway bancario primario"}' \
  --payload-type=json \
  --severity=CRITICAL
```

#### 3.2. Consultar y Filtrar con LQL (*Logging Query Language*)
Consultemos desde Cloud Shell **únicamente** los registros de severidad `ERROR` o superior (`severity >= ERROR`) cuyo campo JSON `codigo_error` sea `ERR_BANCO_TIMEOUT`:

```bash
gcloud logging read \
  'logName="projects/'$PROJECT_ID'/logs/log-pagos-lab08" AND severity>=ERROR AND jsonPayload.codigo_error="ERR_BANCO_TIMEOUT"' \
  --format="table(timestamp, severity, jsonPayload.transaccion_id:label=TX_ID, jsonPayload.codigo_error:label=CODIGO, jsonPayload.mensaje:label=MENSAJE)"
```

**Verificación en la Consola Web**:
- Ve a `☰` -> **Logging** -> **Explorador de registros (Logs Explorer)**.
- En la caja de consulta pega: `logName="projects/TU_PROJECT_ID/logs/log-pagos-lab08"` (reemplazando `TU_PROJECT_ID`) y haz clic en **Ejecutar consulta (Run query)**. Verás tus eventos coloreados según su severidad (azul para `INFO`, naranja para `WARNING` y rojo para `ERROR`/`CRITICAL`).

---

### Paso 4: Creación de Métricas Basadas en Logs y Exportación con Log Sinks (15 min)

#### 4.1. Crear una Métrica Basada en Registros (*Log-based Metric*)
Queremos que cada vez que aparezca un error `ERR_BANCO_TIMEOUT` en los logs, Google Cloud incremente un contador numérico en **Cloud Monitoring**:

```bash
gcloud logging metrics create metrica_errores_banco_lab08 \
  --description="Cuenta la cantidad de fallos ERR_BANCO_TIMEOUT en la pasarela de pagos" \
  --log-filter='logName="projects/'$PROJECT_ID'/logs/log-pagos-lab08" AND severity>=ERROR AND jsonPayload.codigo_error="ERR_BANCO_TIMEOUT"'

# Verificar que la métrica basada en logs esté activa
gcloud logging metrics list --filter="name:metrica_errores_banco_lab08"
```

#### 4.2. Crear un Sumidero de Registros (*Log Sink*) hacia el Bucket de Cloud Storage
Por cumplimiento normativo, todos los errores (`severity >= ERROR`) de nuestra pasarela de pagos deben exportarse automáticamente al bucket `${PROJECT_ID}-logs-auditoria-lab08` que creamos con Terraform:

```bash
# 1. Crear el Sink en el Log Router apuntando a nuestro Bucket
gcloud logging sinks create sink-auditoria-errores-lab08 \
  storage.googleapis.com/${PROJECT_ID}-logs-auditoria-lab08 \
  --log-filter='logName="projects/'$PROJECT_ID'/logs/log-pagos-lab08" AND severity>=ERROR'

# 2. Obtener la identidad (Service Account) exclusiva del Sink y darle permiso de escritura en el Bucket
export SINK_SA=$(gcloud logging sinks describe sink-auditoria-errores-lab08 --format="value(writerIdentity)")
echo "Identidad del Log Sink: $SINK_SA"

gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-logs-auditoria-lab08 \
  --member="$SINK_SA" \
  --role="roles/storage.objectCreator"
```

#### 4.3. Emitir Nuevos Errores para Alimentar la Métrica y el Sink
Tanto las **métricas basadas en registros** como los **sinks** solo procesan las entradas que llegan **después** de haber sido creados; los 4 registros del Paso 3 no se cuentan ni se exportan. Emitamos dos errores nuevos:

```bash
for TX in TX-201 TX-202; do
  gcloud logging write log-pagos-lab08 \
    "{\"transaccion_id\": \"$TX\", \"modulo\": \"pasarela-pagos\", \"codigo_error\": \"ERR_BANCO_TIMEOUT\", \"mensaje\": \"Reintento fallido contra el banco\"}" \
    --payload-type=json \
    --severity=ERROR
done
```

> [!NOTE]
> - La métrica `metrica_errores_banco_lab08` aparecerá en **Monitoring → Explorador de métricas** (busca `logging/user/metrica_errores_banco_lab08`) uno o dos minutos después.
> - Los sinks hacia Cloud Storage escriben **en lotes por hora**: según la documentación oficial, los primeros archivos pueden tardar **de 2 a 3 horas** en aparecer en el bucket. Es normal no verlos durante la clase; lo importante es que el sink y sus permisos queden bien configurados.

---

### Paso 5: Cloud Monitoring — Uptime Checks (Sondas Globales) y Alertas (15 min)

Ahora configuraremos **Cloud Monitoring** para que vigile desde múltiples ubicaciones alrededor del mundo que el servidor web `vm-monitoreada-lab08` (desplegado por Terraform en `$VM_IP`) esté respondiendo `HTTP 200 OK`.

#### 5.1. Crear un Uptime Check (Comprobación de Disponibilidad Global) desde Cloud Shell
```bash
gcloud monitoring uptime create uptime-servidor-terraform-lab08 \
  --resource-type=uptime-url \
  --resource-labels=host=$VM_IP,project_id=$PROJECT_ID \
  --protocol=http \
  --port=80 \
  --path="/" \
  --period=1 \
  --timeout=10 \
  --matcher-content="OPERATIVO"

# Listar los Uptime Checks configurados en el proyecto
gcloud monitoring uptime list-configs \
  --format="table(displayName, monitoredResource.labels.host:label=IP_VIGILADA, httpCheck.path, period)"
```

#### 5.2. Crear un Canal de Notificación por Correo Electrónico
Crearemos un canal de notificación (`Notification Channel`) en Cloud Monitoring con tu correo para poder conectarlo a alertas de SRE:

```bash
gcloud beta monitoring channels create \
  --display-name="Correo Ingeniero SRE Lab 08" \
  --type=email \
  --channel-labels=email_address=$USER_EMAIL

# Listar los canales de notificación creados
gcloud beta monitoring channels list \
  --format="table(name, displayName, type, labels.email_address)"
```

#### 5.3. Visualización en Tiempo Real en la Consola de Cloud Monitoring
1. En la Consola Web de Google Cloud, ve al menú `☰` -> **Monitoring** -> **Verificaciones de tiempo de actividad (Uptime checks)**.
2. Verás tu sonda **`uptime-servidor-terraform-lab08`** apuntando a `$VM_IP`.
3. Después de 1 a 2 minutos, haz clic sobre ella: verás los **semáforos en verde (`Passed`)** reportando la latencia en milisegundos medida desde regiones de Estados Unidos, Europa, Asia y Sudamérica hacia tu máquina virtual.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

Aquí comprobarás una de las mayores ventajas de **Terraform**: en lugar de borrar manualmente la VM, luego el firewall, luego la subred, luego la VPC y luego el bucket recordando los nombres exactos, un solo comando (`terraform destroy`) leerá el estado y destruirá toda la infraestructura en el orden correcto.

Ejecuta los siguientes comandos en **Cloud Shell**:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab08/terraform-gcp && source ../env.sh

# 1. Eliminar los recursos de Observabilidad (Uptime Check, Canal de Notificación, Log Sink y Métrica)
UPTIME_ID=$(gcloud monitoring uptime list-configs --filter="displayName:uptime-servidor-terraform-lab08" --format="value(name)")
if [ -n "$UPTIME_ID" ]; then
  gcloud monitoring uptime delete "$UPTIME_ID" --quiet
fi

CHANNEL_ID=$(gcloud beta monitoring channels list --filter="displayName:'Correo Ingeniero SRE Lab 08'" --format="value(name)")
if [ -n "$CHANNEL_ID" ]; then
  gcloud beta monitoring channels delete "$CHANNEL_ID" --quiet
fi

gcloud logging sinks delete sink-auditoria-errores-lab08 --quiet
gcloud logging metrics delete metrica_errores_banco_lab08 --quiet

# 2. Destruir toda la infraestructura (VM, 2 reglas de Firewall, Subred, VPC y Bucket) automáticamente con Terraform
terraform destroy -var="project_id=${PROJECT_ID}" -auto-approve
```

### Auditoría Final de Limpieza
Verifica que `terraform destroy` haya dejado tu proyecto con cero recursos activos:

```bash
echo "=== Instancias de VM ==="
gcloud compute instances list

echo "=== Redes VPC (Solo debe quedar 'default') ==="
gcloud compute networks list

echo "=== Buckets Cloud Storage ==="
gcloud storage buckets list

echo "=== Uptime Checks Activos ==="
gcloud monitoring uptime list-configs
```

---

## 6. Conclusiones

Con este octavo módulo has completado la primera mitad del curso unificando **Infraestructura como Código (IaC)** y **Observabilidad (SRE)**:
- Dejaste atrás la creación manual de recursos para adoptar **Terraform**: definiste una red VPC, subred, firewall, bucket y servidor web en código declarativo HCL, los desplegaste con `terraform apply` y los destruiste limpiamente con `terraform destroy`.
- Aplicaste los pilares de **Google Cloud Observability**: emitiste logs estructurados en JSON con niveles de severidad, los filtraste con **LQL**, convertiste errores de texto en **Métricas Basadas en Registros** y automatizaste su exportación mediante el **Log Router (`Sinks`)**.
- Configuraste **Uptime Checks globales** y canales de notificación en **Cloud Monitoring** para detectar caídas antes de que los usuarios las reporten.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Escalar o Modificar Infraestructura Declarativamente con Terraform**:
   En tu archivo `main.tf`, cambia el atributo `machine_type = "e2-micro"` a `"e2-small"` o agrega una nueva etiqueta en `labels` y ejecuta `terraform plan -var="project_id=${PROJECT_ID}"`. Analiza cómo Terraform identifica exactamente qué se puede actualizar en caliente (`~ update in-place`) frente a qué requiere recreación.

2. **Reto 2 — Estado Remoto de Terraform en un Bucket de Cloud Storage (`backend "gcs"`)**:
   Investiga cómo agregar un bloque `backend "gcs" { bucket = "..." prefix = "terraform/state" }` dentro del bloque `terraform {}` en `main.tf` y ejecutar `terraform init -migrate-state` para que el archivo `terraform.tfstate` quede guardado y protegido en Cloud Storage en lugar del disco local.

3. **Reto 3 — Simulación de Caída e Incidente en el Uptime Check**:
   Antes de destruir el entorno, apaga Nginx en `vm-monitoreada-lab08` a través del túnel de IAP (Terraform creó la regla `fw-allow-ssh-iap-terraform` para eso): `gcloud compute ssh vm-monitoreada-lab08 --zone=$ZONE --tunnel-through-iap --command="sudo systemctl stop nginx"`. Observa en la pantalla de **Uptime Checks** de Cloud Monitoring cómo en menos de 90 segundos las regiones mundiales pasan de verde a **rojo (`Failed - Connection Refused`)**.

---

## 8. Referencias Oficiales

- **Guía de Introducción a Terraform en Google Cloud Shell**: [https://docs.cloud.google.com/docs/terraform/create-vm-instance](https://docs.cloud.google.com/docs/terraform/create-vm-instance)
- **Lenguaje de Consultas de Cloud Logging (LQL)**: [https://docs.cloud.google.com/logging/docs/view/logging-query-language](https://docs.cloud.google.com/logging/docs/view/logging-query-language)
- **Referencia CLI: `gcloud logging` (`write`, `read`, `metrics`, `sinks`)**: [https://docs.cloud.google.com/sdk/gcloud/reference/logging](https://docs.cloud.google.com/sdk/gcloud/reference/logging)
- **Referencia CLI: `gcloud monitoring uptime`**: [https://docs.cloud.google.com/sdk/gcloud/reference/monitoring/uptime](https://docs.cloud.google.com/sdk/gcloud/reference/monitoring/uptime)
