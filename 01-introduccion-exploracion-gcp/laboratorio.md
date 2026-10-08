# Laboratorio 01: Introducción a Google Cloud Platform, Gobernanza, Jerarquía de Recursos y Herramientas de Gestión (`Cloud Console`, `Cloud Shell` y `gcloud` CLI)

- **Duración estimada**: 80–90 minutos
- **Nivel**: Introductorio / Fundamentos y Gobernanza Cloud
- **Entorno de trabajo**: Navegador Web + **Google Cloud Shell** (No requiere instalar nada en tu computadora)

---

## 1. Objetivo del Laboratorio

Explorar de forma práctica los pilares de **Gobernanza**, **Jerarquía de Recursos**, **Facturación (Cloud Billing)**, **Infraestructura Global** y **Herramientas de Gestión** de Google Cloud Platform. A lo largo de este laboratorio inspeccionarás la ubicación de tu proyecto dentro de la jerarquía organizacional (Organización, Folders y Proyectos), auditarás su **Cuenta de Facturación (`Billing Account`)** configurando un presupuesto con alertas, dominarás **Google Cloud Shell** (incluyendo su disco persistente `$HOME` y su *Web Preview*), administrarás múltiples perfiles en **`gcloud` CLI (`configurations`)**, consultarás las regiones y zonas globales de Google y auditarás la actividad del proyecto en **Cloud Logging**.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Identificar y auditar la **Jerarquía de Recursos** de GCP (`Organization -> Folders -> Projects -> Resources`) y los tres identificadores de todo proyecto (`Project Name`, `Project ID` y `Project Number`) tanto en **Cloud Console** como por CLI.
2. Inspeccionar **Cuentas de Facturación (`Cloud Billing Accounts`)** desde `gcloud billing` y configurar **Presupuestos y Alertas de Gasto** para proteger tus créditos o tarjeta.
3. Aplicar **Etiquetas de Gobernanza (`Labels`)** y consultar el catálogo de **Políticas de Organización (`Organization Policies`)**.
4. Dominar **Google Cloud Shell**, su almacenamiento persistente de 5 GB en `$HOME`, el editor integrado y la **Vista Previa Web (*Web Preview*)**.
5. Crear y alternar entre **Configuraciones Nombradas de `gcloud` (`gcloud config configurations`)** para administrar distintos entornos (`dev`, `prod`) y regiones con fluidez.
6. Explorar la **Infraestructura Global de Google Cloud** (Regiones, Zonas y catálogo de servicios IaaS, PaaS y Serverless) utilizando filtros (`--filter`) y formatos avanzados (`--format=table`, `json`, `value`).
7. Habilitar APIs, crear un primer recurso en Cloud Storage y rastrear su huella de auditoría administrativa en **Cloud Logging**.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado de este laboratorio: $0.00 USD (100% Gratuito)**

| Recurso / Servicio Utilizado | Costo Unitario en GCP | Consumo en este Laboratorio | Costo Estimado |
| :--- | :--- | :--- | :--- |
| **Google Cloud Shell + Web Preview** | Gratuito (incluye 5 GB persistentes en `$HOME` y 50 horas semanales) | ~1.5 horas | **$0.00 USD** |
| **Resource Manager, IAM y Billing API** | Consultas de jerarquía, etiquetas y metadatos de facturación | Gratuito | **$0.00 USD** |
| **Alertas de Presupuesto (Billing Budgets)** | Gratuito en la consola de facturación | 1 presupuesto | **$0.00 USD** |
| **Cloud Storage Bucket (Prueba rápida)** | Primeros 5 GB/mes gratis en `us-central1` | < 1 KB durante 15 minutos (eliminado al final) | **$0.00 USD** |
| **Cloud Logging (Admin Activity Audit Logs)** | 100% Gratuito (retención de 400 días sin costo) | Consultas de auditoría | **$0.00 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Gobernanza Visual en Cloud Console — Jerarquía de Recursos y Facturación (15 min)

Antes de crear cualquier recurso en la nube, todo arquitecto o ingeniero debe verificar **cómo está estructurada su organización**, **en qué proyecto está parado** y **qué cuenta de facturación respalda ese proyecto**.

#### 1.1. Explorar la Jerarquía de Recursos (`Manage Resources`) en la Consola Web
1. Abre tu navegador e ingresa a [https://console.cloud.google.com](https://console.cloud.google.com).
2. En la barra superior, haz clic en el **Selector de Proyectos** y observa la estructura:
   - Si trabajas con una cuenta corporativa o universitaria, verás el **Nodo de Organización** (tu dominio) y posibles **Carpetas (*Folders*)** desplegables.
   - Si trabajas con una cuenta personal `@gmail.com`, verás tus proyectos bajo **Sin organización (*No organization*)**.
3. Abre el menú de navegación izquierdo (`☰`) -> **IAM y administración (IAM & Admin)** -> **Administrar recursos (Manage resources)**.
   - Esta pantalla muestra el árbol jerárquico completo donde viven tus proyectos y desde donde los administradores corporativos crean **Carpetas (*Folders*)** por departamento o entorno.

#### 1.2. Verificar la Cuenta de Facturación (`Billing Account`) y Crear un Presupuesto con Alertas
1. En el menú izquierdo (`☰`), ve a **Facturación (Billing)**.
2. Observa cómo tu proyecto está vinculado a una **Cuenta de Facturación** (ej. *Mi cuenta de facturación*). Si tienes varios proyectos, verás en ** Administración de cuentas (Account management)** qué proyectos están siendo pagados por esa misma cuenta.
3. En el menú izquierdo de Facturación, haz clic en **Presupuestos y alertas (Budgets & alerts)** y luego en **+ CREAR PRESUPUESTO (+ CREATE BUDGET)**:
   - **Nombre**: `Presupuesto-Control-Curso-GCP`
   - **Alcance (Projects)**: Selecciona tu proyecto actual y haz clic en **Siguiente (Next)**.
   - **Importe (Amount)**: Selecciona **Importe especificado (Specified amount)** e ingresa `10` USD (o el equivalente en tu moneda local). Haz clic en **Siguiente**.
   - **Acciones (Threshold rules)**: Verifica que estén activos los umbrales al **50%**, **90%** y **100%** del gasto real, y marca **"Enviar alertas por correo electrónico a los administradores y usuarios de facturación"**.
4. Haz clic en **Finalizar (Finish)**.

---

### Paso 2: Dominando Google Cloud Shell, `$HOME` Persistente y `Web Preview` (15 min)

A partir de ahora trabajaremos desde **Google Cloud Shell**, la estación de trabajo Linux gratuita que Google ejecuta directamente en tu navegador.

#### 2.1. Activar Cloud Shell e Inspeccionar su Arquitectura
1. Haz clic en el ícono **`>_` (Activar Cloud Shell)** en la esquina superior derecha de la consola web.
2. Ejecuta los siguientes comandos para inspeccionar el hardware virtual, el sistema operativo y el disco persistente de 5 GB montado en tu carpeta `$HOME`:

```bash
# 1. Ver el sistema operativo, kernel y CPUs de la máquina de Cloud Shell
uname -a
lscpu | grep -E "Model name|CPU\(s\):"

# 2. Comprobar que tu directorio $HOME (/home/tu_usuario) es un disco persistente independiente de 5 GB
df -h $HOME

# 3. Verificar las herramientas preinstaladas listas para usar
gcloud --version | head -n 1
kubectl version --client
terraform -version | head -n 1
```

#### 2.2. Probar la Herramienta de Vista Previa Web (*Web Preview*) de Cloud Shell
Cloud Shell incluye un proxy inverso autenticado que te permite probar aplicaciones web antes de desplegarlas en IaaS, PaaS o Serverless:

```bash
mkdir -p ~/workshop-gcp/lab01
cd ~/workshop-gcp/lab01

# Crear una página HTML rápida y levantar un servidor web en el puerto 8080 en segundo plano
cat << 'EOF' > index.html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Cloud Shell Web Preview</title></head>
<body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
  <h1 style="color: #1a73e8;">¡Hola desde Google Cloud Shell!</h1>
  <p>Esta página corre en el puerto 8080 dentro de tu VM efímera de Cloud Shell.</p>
</body>
</html>
EOF

python3 -m http.server 8080 &> /dev/null &
SERVER_PID=$!
echo "Servidor local corriendo en PID: $SERVER_PID (Puerto 8080)"
```

1. En la barra de herramientas superior derecha de la ventana de Cloud Shell, haz clic en el ícono de **Vista previa web (Web Preview)** (un cuadrado con un ojo o flecha) y selecciona **Vista previa en el puerto 8080 (Preview on port 8080)**.
2. Se abrirá una pestaña segura mostrando tu página web. Una vez que la veas, cierra esa pestaña y detén el servidor temporal ejecutando:

```bash
kill $SERVER_PID
```

---

### Paso 3: Gobernanza, Jerarquía de Recursos y Facturación desde `gcloud` CLI (15 min)

Todo lo que vimos en la interfaz gráfica de gobernanza y facturación se puede consultar y automatizar desde `gcloud`.

#### 3.1. Habilitar la API de Cloud Resource Manager e Inspeccionar el Proyecto
```bash
mkdir -p ~/workshop-gcp/lab01
cd ~/workshop-gcp/lab01

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi
echo "Mi Project ID activo es: $PROJECT_ID"

# Guardar las variables del laboratorio en un archivo para recuperarlas si la sesión se reinicia
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export BUCKET_NAME="gs://${PROJECT_ID}-lab01-gobernanza"
EOF
source env.sh

# Habilitar la API de Resource Manager y de Facturación
gcloud services enable cloudresourcemanager.googleapis.com cloudbilling.googleapis.com

# Consultar los 3 identificadores del proyecto (Name, Project ID y Project Number)
gcloud projects describe $PROJECT_ID \
  --format="table(name:label=NOMBRE_PROYECTO, projectId:label=PROJECT_ID, projectNumber:label=PROJECT_NUMBER, lifecycleState:label=ESTADO)"
```

> [!IMPORTANT]
> **Cloud Shell se desconecta tras 40 minutos de inactividad** y al reconectar se pierden las variables de entorno (`$PROJECT_ID`, `$BUCKET_NAME`, etc.). Si eso ocurre, recupéralas antes de continuar con:
> ```bash
> cd ~/workshop-gcp/lab01 && source env.sh
> ```
> Todos los laboratorios del curso siguen este mismo patrón con su propio archivo `env.sh`.

#### 3.2. Consultar el Árbol de Ancestros (*Resource Hierarchy*) de tu Proyecto
¿Cómo sabemos desde la terminal si nuestro proyecto está dentro de una Carpeta (*Folder*) y una Organización (*Organization*)? Con el comando **`get-ancestors`**:

```bash
gcloud projects get-ancestors $PROJECT_ID \
  --format="table(type:label=NIVEL_JERARQUIA, id:label=IDENTIFICADOR)"
```
- Si estás en una cuenta corporativa, verás la lista desde `project` subiendo por cada `folder` hasta llegar a `organization`.
- Si estás en una cuenta personal, verás únicamente el nivel `project`.

#### 3.3. Aplicar Etiquetas de Gobernanza Financiera (*Labels*) al Proyecto
En FinOps es fundamental etiquetar los proyectos y recursos por departamento, centro de costos y entorno:

> [!NOTE]
> La edición de etiquetas de un **proyecto** solo está disponible en el canal **`alpha`** de `gcloud` (`gcloud projects update` en GA únicamente permite cambiar el nombre). Cloud Shell ya trae instalados los componentes `alpha` y `beta`.

```bash
# Agregar etiquetas (labels) de gobernanza a nuestro proyecto
gcloud alpha projects update $PROJECT_ID \
  --update-labels=entorno=laboratorio,curso=workshop-gcp,centro_costo=educacion

# Verificar que las etiquetas hayan quedado registradas en los metadatos del proyecto
gcloud projects describe $PROJECT_ID --format="yaml(name, projectId, labels)"
```

#### 3.4. Auditar la Cuenta de Facturación (*Billing Account*) Vinculada desde CLI
```bash
# 1. Listar las Cuentas de Facturación a las que tu usuario tiene acceso
gcloud billing accounts list

# 2. Verificar exactamente qué Cuenta de Facturación está pagando este proyecto y si billingEnabled es True
gcloud billing projects describe $PROJECT_ID \
  --format="table(projectId, billingAccountName.basename():label=BILLING_ACCOUNT_ID, billingEnabled)"
```

---

### Paso 4: Gestión Avanzada de Perfiles en `gcloud` (`Configurations`) (10 min)

En el trabajo diario como ingeniero de nube, a menudo debes administrar varios entornos (por ejemplo, un entorno de `desarrollo` en la región `us-central1` y un entorno de `contingencia` en `us-east1`). En lugar de reconfigurar `gcloud` cada vez, aprenderemos a usar **`gcloud config configurations`**.

```bash
# 0. Guardar la cuenta activa: cada perfil nuevo nace vacío y hay que indicarle cuenta y proyecto
export ACCOUNT=$(gcloud config get-value account 2>/dev/null)

# 1. Ver las configuraciones (perfiles) existentes en tu Cloud Shell (verás 'cloudshell-...' o 'default')
gcloud config configurations list

# 2. Crear un nuevo perfil llamado 'perfil-latam' que apunte por defecto a São Paulo (southamerica-east1)
#    (al crearlo, gcloud lo activa automáticamente)
gcloud config configurations create perfil-latam
gcloud config set account $ACCOUNT
gcloud config set project $PROJECT_ID
gcloud config set compute/region southamerica-east1
gcloud config set compute/zone southamerica-east1-a

# 3. Crear y activar nuestro perfil principal del curso ('perfil-us-central') apuntando a Iowa (us-central1)
gcloud config configurations create perfil-us-central
gcloud config set account $ACCOUNT
gcloud config set project $PROJECT_ID
gcloud config set compute/region us-central1
gcloud config set compute/zone us-central1-a

# 4. Listar todos tus perfiles de un vistazo para comparar sus regiones y zonas
gcloud config configurations list
```

¡Observa la tabla! Ambos perfiles existen y **`perfil-us-central`** tiene `IS_ACTIVE = True`. Si quisieras trabajar en Sudamérica, bastaría con ejecutar `gcloud config configurations activate perfil-latam`, o usar el perfil solo para un comando con `--configuration=perfil-latam`.

> [!WARNING]
> **Particularidad de Cloud Shell:** según la documentación oficial, las preferencias de `gcloud` en Cloud Shell se guardan en una carpeta temporal (`tmp`), **solo para la pestaña actual, y no persisten entre sesiones**. Los perfiles que acabas de crear desaparecerán cuando se cierre la sesión. Por eso **cada laboratorio del curso vuelve a configurar proyecto, región y zona en su Paso 1**.
>
> Si quisieras perfiles permanentes en Cloud Shell, la documentación recomienda agregar `export CLOUDSDK_CONFIG=$HOME/.config/gcloud` a tu archivo `~/.bashrc` (que sí vive en el disco persistente `$HOME`) y crear allí tus configuraciones. En una laptop con gcloud instalado localmente, los perfiles sí persisten sin hacer nada.

---

### Paso 5: Exploración de la Red Global (Regiones y Zonas) y Modelos Cloud (IaaS, PaaS, Serverless) (15 min)

Ahora usaremos nuestro perfil activo para explorar la infraestructura física global de Google y el catálogo de servicios.

#### 5.1. Habilitar la API de Compute Engine y Explorar Regiones y Zonas
```bash
gcloud services enable compute.googleapis.com

# 1. Contar el total de Regiones y Zonas globales disponibles hoy en tu proyecto
echo "Total de Regiones Globales:" $(gcloud compute regions list --format="value(name)" | wc -l)
echo "Total de Zonas Globales:" $(gcloud compute zones list --format="value(name)" | wc -l)

# 2. Listar las regiones de América y ver cuántas zonas tiene cada una
gcloud compute regions list \
  --filter="name ~ ^(us|northamerica|southamerica)" \
  --format="table(name:label=REGION, zones.len():label=CANTIDAD_ZONAS, status)"
```

#### 5.2. Explorar los Catálogos de IaaS vs PaaS / Serverless en las APIs de GCP
Comparemos desde la terminal cómo se ven las ofertas de **IaaS** (tipos de máquinas virtuales en `us-central1-a`) frente al catálogo de APIs **PaaS y Serverless** de Google Cloud:

```bash
# 1. Oferta IaaS: Ver tamaños de máquinas virtuales (Serie E2) en la zona us-central1-a
gcloud compute machine-types list \
  --filter="zone:(us-central1-a) AND name ~ ^e2-" \
  --format="table(name, guestCpus:label=vCPUs, memoryMb:label=RAM_MB, description)" \
  --sort-by=memoryMb

# 2. Oferta PaaS y Serverless: Buscar en el catálogo de Google APIs de Contenedores, Funciones y BigQuery
gcloud services list --available \
  --filter="config.name ~ ^(run|cloudfunctions|bigquery|sqladmin|aiplatform)\.googleapis\.com$" \
  --format="table(config.name:label=API_ID, config.title:label=SERVICIO_CLOUD)"
```

---

### Paso 6: Prueba de Extremo a Extremo y Auditoría de Gobernanza en Cloud Logging (15 min)

Para cerrar el laboratorio, crearemos un recurso real en **Cloud Storage** etiquetado bajo nuestras normas de gobernanza y luego consultaremos los **Registros de Auditoría de Actividad del Administrador (*Admin Activity Audit Logs*)** para verificar cómo Google Cloud registra cada cambio hecho en el proyecto.

#### 6.1. Crear un Bucket con Etiquetas de Gobernanza y Subir un Archivo
```bash
# (Si la sesión se reinició: cd ~/workshop-gcp/lab01 && source env.sh)
echo "Bucket a crear: $BUCKET_NAME"

# 1. Crear el bucket en us-central1 con acceso uniforme
gcloud storage buckets create $BUCKET_NAME \
  --location=us-central1 \
  --uniform-bucket-level-access

# 2. Aplicar las etiquetas de FinOps (gcloud storage buckets create no acepta --labels; se agregan con update)
gcloud storage buckets update $BUCKET_NAME \
  --update-labels=entorno=laboratorio,modulo=lab01,responsable=estudiante
gcloud storage buckets describe $BUCKET_NAME --format="yaml(name, labels)"

# 3. Crear un reporte JSON de nuestro entorno y subirlo al bucket
cat << EOF > reporte-gobernanza.json
{
  "proyecto_id": "$PROJECT_ID",
  "region_predeterminada": "$(gcloud config get-value compute/region)",
  "zona_predeterminada": "$(gcloud config get-value compute/zone)",
  "modelos_explorados": ["IaaS", "CaaS", "PaaS", "Serverless"],
  "estado_gobernanza": "Presupuesto y Etiquetas Configurados"
}
EOF

gcloud storage cp reporte-gobernanza.json $BUCKET_NAME/
gcloud storage cat $BUCKET_NAME/reporte-gobernanza.json
```

#### 6.2. Auditar la Actividad Administrativa en Cloud Logging
En gobernanza cloud, toda acción que crea, modifica o elimina un recurso queda grabada de forma inmutable durante 400 días en el registro de auditoría `cloudaudit.googleapis.com/activity`. Consultemos las últimas 5 acciones ejecutadas en nuestro proyecto:

```bash
gcloud logging read "logName:cloudaudit.googleapis.com%2Factivity" \
  --limit=5 \
  --format="table(timestamp, protoPayload.authenticationInfo.principalEmail:label=EJECUTADO_POR, protoPayload.serviceName:label=SERVICIO, protoPayload.methodName:label=ACCION)"
```

¡Observa cómo aparece tu usuario, el servicio `storage.googleapis.com` o `cloudresourcemanager.googleapis.com` y la hora exacta de cada operación!

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

Siguiendo nuestras reglas de oro de **FinOps**, eliminaremos el bucket de prueba y el perfil secundario para dejar el proyecto completamente limpio y listo para el siguiente módulo:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab01 && source env.sh

# 1. Eliminar el bucket de prueba y todos sus objetos
gcloud storage rm --recursive $BUCKET_NAME

# 2. Asegurar que quede activo el perfil principal en us-central1 y borrar el perfil de prueba 'perfil-latam'
#    (si la sesión se reinició, los perfiles ya no existen y estos comandos solo mostrarán un aviso)
gcloud config configurations activate perfil-us-central 2>/dev/null || echo "Perfil perfil-us-central no encontrado (la sesión se reinició)"
gcloud config configurations delete perfil-latam --quiet 2>/dev/null || echo "Perfil perfil-latam no encontrado (la sesión se reinició)"

# 3. Verificar que no queden buckets ni instancias activas en el proyecto
echo "=== Buckets Activos ==="
gcloud storage buckets list

echo "=== Instancias VM Activas ==="
gcloud compute instances list
```

---

## 6. Conclusiones

En este primer laboratorio has sentado las bases arquitectónicas, financieras y operativas de Google Cloud Platform:
- Comprendiste las diferencias prácticas entre **IaaS, CaaS, PaaS y Serverless**, y cómo se mapean a los servicios del catálogo de GCP.
- Exploraste la **Gobernanza y Jerarquía de Recursos** (`Organization -> Folders -> Projects`), comprobando el árbol de ancestros, etiquetando recursos para FinOps y vinculando controles de presupuesto sobre la **Cuenta de Facturación (`Cloud Billing Account`)**.
- Dominaste las tres herramientas centrales de gestión: **Cloud Console**, **Cloud Shell** (incluyendo `$HOME` persistente y *Web Preview*) y **`gcloud` CLI** (incluyendo la gestión profesional de múltiples perfiles con `gcloud config configurations`).
- Verificaste la trazabilidad total de tus acciones mediante los registros de auditoría en **Cloud Logging**.

---

## 7. Retos Prácticos (Challenges)

Pon a prueba lo aprendido resolviendo estos tres retos desde **Cloud Shell**:

1. **Reto 1 — Explorador de Restricciones de Gobernanza (*Organization Policy Constraints*)**:
   Lista las políticas de organización configuradas sobre tu proyecto con `gcloud org-policies list --project=$PROJECT_ID` (agrega `--show-unset` para ver también las restricciones disponibles que no tienen valor explícito). Luego identifica en la consola web (`IAM & Admin -> Organization Policies`) qué hace la restricción llamada **`compute.vmExternalIpAccess`**.
   *(Nota: `gcloud org-policies list-custom-constraints` exige `--organization=ID`, por lo que solo funciona si tu proyecto pertenece a una Organización; con una cuenta personal `@gmail.com` no hay nodo de organización).*

2. **Reto 2 — Exportación de Regiones Globales en Formato JSON**:
   Usando `gcloud compute regions list` con `--filter` y `--format=json`, genera un archivo llamado `~/workshop-gcp/lab01/regiones-europa.json` que contenga únicamente las regiones ubicadas en Europa (`europe-*`).

3. **Reto 3 — Descubrimiento de Hardware Especializado para IA (GPUs)**:
   Usa `gcloud compute accelerator-types list` filtrando por la zona `us-central1-a` para descubrir qué modelos de tarjetas aceleradoras GPU (**NVIDIA**) ofrece Google Cloud en esa zona bajo el modelo IaaS.

---

## 8. Referencias Oficiales

- **Jerarquía de Recursos de Google Cloud**: [https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- **Guía de Presupuestos y Alertas de Cloud Billing**: [https://docs.cloud.google.com/billing/docs/how-to/budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- **Administración de Configuraciones (`configurations`) en `gcloud` CLI**: [https://docs.cloud.google.com/sdk/docs/configurations](https://docs.cloud.google.com/sdk/docs/configurations)
- **Uso de Filtros y Formatos en `gcloud` (`--filter` y `--format`)**: [https://docs.cloud.google.com/sdk/gcloud/reference/topic/formats](https://docs.cloud.google.com/sdk/gcloud/reference/topic/formats)
- **Vista Previa Web (*Web Preview*) en Cloud Shell**: [https://docs.cloud.google.com/shell/docs/using-web-preview](https://docs.cloud.google.com/shell/docs/using-web-preview)
