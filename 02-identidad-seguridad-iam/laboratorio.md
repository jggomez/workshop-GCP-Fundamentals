# Laboratorio 02: Seguridad de Menor Privilegio con Cloud IAM, Cuentas de Servicio, Roles Personalizados y Secret Manager

- **Duración estimada**: 80–90 minutos
- **Nivel**: Intermedio / Seguridad en la Nube
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud` CLI)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Implementar una arquitectura de seguridad basada en el **Principio de Menor Privilegio** y **Autenticación sin Llaves (*Keyless Authentication*)** en Google Cloud Platform. A lo largo de este laboratorio diseñarás un **Rol Personalizado de IAM** que impide la eliminación de datos, crearás una **Cuenta de Servicio (*Service Account*)** con permisos restringidos a nivel de recurso, practicarás la **Suplantación Segura (`--impersonate-service-account`)** desde Cloud Shell sin descargar archivos `.json` riesgosos, gestionarás el ciclo de vida y rotación de contraseñas en **Secret Manager** y desplegarás una máquina virtual en Compute Engine que consume secretos y escribe datos utilizando únicamente su identidad nativa.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Diseñar, crear y actualizar **Roles Personalizados (*Custom Roles*)** en Cloud IAM seleccionando permisos atómicos exactos.
2. Crear **Cuentas de Servicio dedicadas (*User-Managed Service Accounts*)** para reemplazar el uso riesgoso de la cuenta predeterminada de Compute Engine.
3. Aplicar políticas de IAM **a nivel de recurso individual** (sobre un Bucket específico y sobre un Secreto específico) en lugar de otorgar permisos excesivos a nivel de todo el proyecto.
4. Utilizar la **Suplantación de Cuenta de Servicio (`--impersonate-service-account`)** para probar permisos en vivo desde Cloud Shell sin generar ni descargar llaves privadas JSON.
5. Crear secretos en **Secret Manager**, rotar versiones (`v1`, `v2`, `latest`), deshabilitar o destruir versiones comprometidas y restringir quién puede leer su contenido (`roles/secretmanager.secretAccessor`).
6. Desplegar una máquina virtual en Compute Engine con una identidad personalizada adjunta y comprobar experimentalmente qué acciones le permite y qué acciones le bloquea Google Cloud.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado por ejecutar este laboratorio durante 90 minutos: < $0.01 USD (Prácticamente Gratuito)**

| Recurso / Servicio Utilizado | Costo Unitario en GCP | Consumo en este Laboratorio | Costo Estimado |
| :--- | :--- | :--- | :--- |
| **Cloud IAM (Roles Personalizados, Service Accounts y Políticas)** | 100% Gratuito en GCP | 1 Rol Personalizado + 1 Cuenta de Servicio | **$0.000 USD** |
| **Secret Manager** | Primeras 6 versiones de secretos activas al mes y 10,000 accesos son **Gratuitos** (*Free Tier*); luego $0.06/mes por versión | 1 secreto con 2 versiones durante 1 hora (eliminado al final) | **$0.000 USD** |
| **Cloud Storage Bucket (`boveda`)** | $0.020 por GB/mes (5 GB gratis en Free Tier) | < 2 KB de archivos de texto durante 1 hora | **$0.000 USD** |
| **Compute Engine VM (`vm-segura-lab02`)** | 1x `e2-micro` (~$0.0084 / hora) | Encendida durante ~25 minutos en el Paso 6 | **~$0.004 USD** |
| **TOTAL ESTIMADO DE LA SESIÓN** | **Ejecutando la limpieza al finalizar el laboratorio** | — | **~$0.004 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno y Habilitación de APIs en Cloud Shell (10 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Ejecuta los siguientes comandos para crear el directorio de trabajo del laboratorio, definir las variables de entorno y habilitar las APIs de **IAM**, **Resource Manager**, **Secret Manager** y **Compute Engine**:

```bash
mkdir -p ~/workshop-gcp/lab02
cd ~/workshop-gcp/lab02

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar TODAS las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad).
# El rol personalizado lleva un sufijo con fecha y hora: un ID de rol eliminado no puede reutilizarse
# hasta 44 días después, así que un nombre fijo fallaría al repetir el laboratorio en el mismo proyecto.
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export USER_EMAIL="$(gcloud config get-value account 2>/dev/null)"
export REGION="us-central1"
export ZONE="us-central1-a"
export ROLE_ID="OperadorBovedaSinBorrado_$(date +%Y%m%d%H%M)"
export SA_EMAIL="sa-app-backend@${PROJECT_ID}.iam.gserviceaccount.com"
export BUCKET_AUTORIZADO="gs://${PROJECT_ID}-boveda-autorizada"
export BUCKET_CONFIDENCIAL="gs://${PROJECT_ID}-rrhh-confidencial"
EOF
source env.sh

gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE

# Habilitar las APIs necesarias para seguridad, IAM y Secret Manager
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com

echo "Proyecto: $PROJECT_ID | Usuario: $USER_EMAIL | Rol: $ROLE_ID"

# El Paso 6 crea una VM en la red 'default' y se conecta por SSH: verificar que exista
gcloud compute networks describe default --format="value(name)" 2>/dev/null \
  || echo "AVISO: tu proyecto no tiene la red 'default'. Créala con: gcloud compute networks create default --subnet-mode=auto && gcloud compute firewall-rules create default-allow-ssh --network=default --allow=tcp:22"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables antes de seguir con: `cd ~/workshop-gcp/lab02 && source env.sh`

---

### Paso 2: Creación de un Rol Personalizado (Custom Role) en Cloud IAM (15 min)

### Escenario de Arquitectura
El equipo de auditoría de tu empresa exige que el servidor backend pueda **listar, leer y subir nuevos reportes** a un bucket de Cloud Storage, pero bajo ninguna circunstancia pueda **borrar ni sobrescribir** archivos existentes (para proteger la evidencia ante un eventual ataque de *ransomware* o un error de programación).

Si revisamos los roles predefinidos de Cloud Storage (`roles/storage.objectAdmin`), veremos que incluyen el permiso `storage.objects.delete`. Por lo tanto, crearemos un **Rol Personalizado** que contenga **únicamente** los permisos de lectura y creación, excluyendo `delete`.

#### 2.1. Inspeccionar permisos antes de crear el rol
Comparemos qué permisos tiene el rol predefinido `roles/storage.objectCreator`:

```bash
gcloud iam roles describe roles/storage.objectCreator
```
Verás que `objectCreator` solo tiene `storage.objects.create`, pero no permite listar ni leer objetos (`storage.objects.get`, `storage.objects.list`).

#### 2.2. Crear el Rol Personalizado `OperadorBovedaSinBorrado`
Ejecuta en Cloud Shell el comando para crear nuestro rol personalizado a nivel de proyecto. Su ID real es `$ROLE_ID` (por ejemplo `OperadorBovedaSinBorrado_202610071530`), definido en el Paso 1 con un sufijo de fecha para que puedas repetir el laboratorio sin choques de nombres:

```bash
gcloud iam roles create $ROLE_ID \
  --project=$PROJECT_ID \
  --title="Operador de Boveda (Sin Permiso de Borrado)" \
  --description="Permite listar, leer y crear objetos en Cloud Storage, pero prohibe eliminarlos" \
  --permissions="storage.buckets.get,storage.objects.list,storage.objects.get,storage.objects.create" \
  --stage=GA
```

#### 2.3. Verificar el Rol Personalizado en CLI y en Consola Web
1. Consulta el rol recién creado desde Cloud Shell:

```bash
gcloud iam roles describe $ROLE_ID --project=$PROJECT_ID
```

2. **En la Consola Web**:
   - Ve al menú `☰` -> **IAM y administración (IAM & Admin)** -> **Roles**.
   - Verás en la lista tu rol **`Operador de Boveda (Sin Permiso de Borrado)`** con un ícono personalizado que lo distingue de los más de 1,000 roles predefinidos de Google.

---

### Paso 3: Creación de una Cuenta de Servicio y Permisos a Nivel de Recurso (15 min)

Ahora crearemos la identidad exclusiva para nuestra aplicación backend (`sa-app-backend`) y crearemos dos buckets de Cloud Storage:
- **`boveda-autorizada`**: El único bucket donde nuestra aplicación tiene permiso de trabajar.
- **`rrhh-confidencial`**: Otro bucket del mismo proyecto al cual nuestra aplicación **NO debe tener acceso**.

#### 3.1. Crear la Cuenta de Servicio `sa-app-backend`
```bash
gcloud iam service-accounts create sa-app-backend \
  --display-name="Service Account Backend App Lab 02" \
  --description="Identidad de minimo privilegio para el backend del Laboratorio 02"

# El correo completo de la Service Account ya quedó guardado en $SA_EMAIL (env.sh del Paso 1)
echo "Correo de la Service Account: $SA_EMAIL"
```

Verifica que la cuenta exista pero que **NO** tenga ningún permiso global en el proyecto todavía:

```bash
gcloud iam service-accounts list --filter="email:$SA_EMAIL"
```

#### 3.2. Crear los dos Buckets de prueba en Cloud Storage
```bash
# $BUCKET_AUTORIZADO y $BUCKET_CONFIDENCIAL ya están definidos en env.sh (Paso 1)
echo "Autorizado: $BUCKET_AUTORIZADO | Confidencial: $BUCKET_CONFIDENCIAL"

gcloud storage buckets create $BUCKET_AUTORIZADO --location=$REGION --uniform-bucket-level-access
gcloud storage buckets create $BUCKET_CONFIDENCIAL --location=$REGION --uniform-bucket-level-access

# Subir un archivo secreto de prueba al bucket de RRHH (con nuestro usuario administrador)
echo "Nomina Confidencial Directorio: $150,000 USD" > nomina-rrhh.txt
gcloud storage cp nomina-rrhh.txt $BUCKET_CONFIDENCIAL/
```

#### 3.3. Asignar nuestro Rol Personalizado ÚNICAMENTE sobre el Bucket Autorizado
En lugar de usar `gcloud projects add-iam-policy-binding` (que daría permiso en **todos** los buckets del proyecto), aplicaremos la política IAM **directamente sobre el recurso `$BUCKET_AUTORIZADO`**:

```bash
gcloud storage buckets add-iam-policy-binding $BUCKET_AUTORIZADO \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="projects/${PROJECT_ID}/roles/${ROLE_ID}"
```

Inspecciona la política IAM del bucket autorizado para confirmar cómo quedó registrado nuestro rol personalizado:

```bash
gcloud storage buckets get-iam-policy $BUCKET_AUTORIZADO
```

---

### Paso 4: Prueba de Seguridad sin Llaves JSON — Suplantación de Identidad (`Impersonation`) (15 min)

¿Cómo podemos probar desde **Cloud Shell** si los permisos de `sa-app-backend` funcionan correctamente **sin descargar jamás un archivo `key.json`**?
Usando la bandera **`--impersonate-service-account`**.

#### 4.1. Autorizar a nuestro usuario para suplantar (`Token Creator`) a la Cuenta de Servicio
Como aprendimos en el `teoria.md`, una Cuenta de Servicio también es un **Recurso**. Otorguemos a nuestro propio usuario el rol `roles/iam.serviceAccountTokenCreator` sobre `sa-app-backend`:

```bash
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --member="user:${USER_EMAIL}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

Los cambios de IAM **tardan normalmente unos 2 minutos en propagarse (y pueden tardar 7 minutos o más)**, según la documentación oficial. En lugar de esperar un tiempo fijo, reintentemos hasta que la suplantación funcione:

```bash
for i in $(seq 1 30); do
  if gcloud storage ls $BUCKET_AUTORIZADO/ --impersonate-service-account=$SA_EMAIL > /dev/null 2>&1; then
    echo "Permisos propagados: ya puedes actuar como $SA_EMAIL"; break
  fi
  echo "Intento $i: esperando la propagación de IAM (15 s)..."; sleep 15
done
```

#### 4.2. Ejecutar pruebas positivas y negativas actuando como `sa-app-backend`

**Prueba 1 (Permitida ✅): Subir y leer un archivo en el Bucket Autorizado**
```bash
echo "Reporte de transacciones del dia - OK" > reporte-ventas.txt

# Subir archivo actuando como la Service Account
gcloud storage cp reporte-ventas.txt $BUCKET_AUTORIZADO/ \
  --impersonate-service-account=$SA_EMAIL

# Listar y leer el archivo actuando como la Service Account
gcloud storage ls $BUCKET_AUTORIZADO/ --impersonate-service-account=$SA_EMAIL
gcloud storage cat $BUCKET_AUTORIZADO/reporte-ventas.txt --impersonate-service-account=$SA_EMAIL
```
¡Funcionó! La cuenta de servicio pudo subir y leer el archivo en su bucket asignado.

**Prueba 2 (Bloqueada por el Rol Personalizado 🛡️): Intentar BORRAR el archivo en el Bucket Autorizado**
```bash
gcloud storage rm $BUCKET_AUTORIZADO/reporte-ventas.txt \
  --impersonate-service-account=$SA_EMAIL
```
> **Resultado esperado**: Recibirás un error **`HTTPError 403: ... does not have storage.objects.delete access to the Google Cloud Storage object`**. ¡Tu rol personalizado `OperadorBovedaSinBorrado` acaba de impedir la destrucción de datos!

**Prueba 3 (Bloqueada por Aislamiento de Recurso 🛡️): Intentar espiar el Bucket de RRHH Confidencial**
```bash
gcloud storage ls $BUCKET_CONFIDENCIAL/ \
  --impersonate-service-account=$SA_EMAIL
```
> **Resultado esperado**: **`HTTPError 403: ... does not have storage.objects.list access`**. Aunque ambos buckets viven en el mismo proyecto de GCP, la cuenta de servicio está completamente ciega frente al bucket de RRHH.

---

### Paso 5: Gestión y Rotación de Credenciales con Secret Manager (15 min)

Ahora nuestra aplicación backend necesita conectarse a una pasarela de pagos externa utilizando una llave privada (`API_KEY`). En lugar de poner esa llave en el código o en un script, la guardaremos en **Secret Manager**.

#### 5.1. Crear el Contenedor del Secreto y su Versión 1 (`v1`)
```bash
# 1. Crear el contenedor lógico del secreto con replicación automática
gcloud secrets create api-key-pasarela-pagos \
  --replication-policy="automatic" \
  --labels=entorno=produccion,laboratorio=lab02

# 2. Agregar la Versión 1 del secreto (usando printf para no incluir saltos de línea innecesarios)
printf "sk_live_VERSION1_987654321_ANTIGUA" | \
  gcloud secrets versions add api-key-pasarela-pagos --data-file=-
```

#### 5.2. Rotar el Secreto (Crear Versión 2 y Deshabilitar Versión 1)
Supongamos que por política de seguridad rotamos la credencial a una nueva llave:

```bash
# 1. Agregar la Versión 2 (pasa automáticamente a ser 'latest')
printf "sk_live_VERSION2_SUPER_SECRETA_2026_ACTIVA" | \
  gcloud secrets versions add api-key-pasarela-pagos --data-file=-

# 2. Listar las versiones existentes del secreto
gcloud secrets versions list api-key-pasarela-pagos

# 3. Deshabilitar la Versión 1 para que ninguna aplicación pueda seguir usando la credencial vieja
gcloud secrets versions disable 1 --secret=api-key-pasarela-pagos

# 4. Verificar que la versión 1 esté DISABLED y la versión 2 esté ENABLED
gcloud secrets versions list api-key-pasarela-pagos
```

#### 5.3. Otorgar permiso de lectura del Secreto exclusivamente a `sa-app-backend`
Si intentamos leer el secreto usando nuestra cuenta de servicio `sa-app-backend` ahora mismo, fallará con error `403`. Otorguémosle el rol **`roles/secretmanager.secretAccessor`** **únicamente sobre este secreto**:

```bash
gcloud secrets add-iam-policy-binding api-key-pasarela-pagos \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

Probemos leer la versión `latest` actuando como la cuenta de servicio (reintentando mientras el nuevo permiso se propaga):

```bash
for i in $(seq 1 20); do
  gcloud secrets versions access latest \
    --secret=api-key-pasarela-pagos \
    --impersonate-service-account=$SA_EMAIL 2>/dev/null && { echo ""; break; }
  echo "Intento $i: esperando la propagación de IAM (15 s)..."; sleep 15
done
```
Verás impreso en pantalla: `sk_live_VERSION2_SUPER_SECRETA_2026_ACTIVA`.

**Verificación en la Consola Web**:
- Ve al menú `☰` -> **Seguridad (Security)** -> **Secret Manager**.
- Haz clic en **`api-key-pasarela-pagos`**. Observa las versiones `1` (*Disabled*) y `2` (*Enabled*), y en la pestaña **Permisos (Permissions)** verifica cómo `sa-app-backend` figura únicamente como *Secret Manager Secret Accessor*.

---

### Paso 6: Integración Real — Máquina Virtual con Identidad de Mínimo Privilegio (15 min)

Cuando se crea una VM sin especificar `--service-account`, Compute Engine le adjunta la **cuenta de servicio predeterminada de Compute Engine** (que en muchos proyectos tiene el rol `Editor`, demasiado amplio). Profundizaremos en Compute Engine en el **Laboratorio 04**; por ahora lanzaremos una VM asignándole explícitamente nuestra identidad blindada **`sa-app-backend`**.

#### 6.1. Crear la VM `vm-segura-lab02` adjuntando nuestra Cuenta de Servicio
```bash
gcloud compute instances create vm-segura-lab02 \
  --zone=$ZONE \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --service-account=$SA_EMAIL \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

> [!NOTE]
> **¿Por qué usamos `--scopes=https://www.googleapis.com/auth/cloud-platform`?**
> En Compute Engine, los *Access Scopes* son un mecanismo heredado. La mejor práctica oficial de Google Cloud es establecer el scope de la VM en `cloud-platform` y controlar **todos los permisos reales a través de los roles de IAM de la Cuenta de Servicio adjunta**.

#### 6.2. Comprobar la Identidad y Ejecutar el Flujo desde Dentro de la VM
Conectémonos por SSH a `vm-segura-lab02` y ejecutemos una prueba completa donde la máquina virtual:
1. Verifica qué identidad tiene activa (`gcloud auth list`).
2. Recupera en memoria el secreto `api-key-pasarela-pagos` desde **Secret Manager**.
3. Genera un archivo de auditoría y lo sube al **Bucket Autorizado (`$BUCKET_AUTORIZADO`)**.
4. Intenta listar otras máquinas virtuales del proyecto (lo cual debe ser **denegado por IAM**).

Ejecuta el siguiente bloque desde tu **Cloud Shell**:

```bash
gcloud compute ssh vm-segura-lab02 --zone=$ZONE --command="
  echo '=== 1. IDENTIDAD ACTIVA DENTRO DE LA VM ==='
  gcloud auth list

  echo -e '\n=== 2. LEYENDO SECRETO DESDE SECRET MANAGER (SIN LLAVES JSON) ==='
  SECRETO_LEIDO=\$(gcloud secrets versions access latest --secret=api-key-pasarela-pagos)
  echo 'Secreto recuperado exitosamente (primeros 16 caracteres):' \${SECRETO_LEIDO:0:16}...

  echo -e '\n=== 3. ESCRIBIENDO REPORTE EN EL BUCKET AUTORIZADO ==='
  echo \"Transaccion procesada desde \$(hostname) en fecha \$(date -Iseconds) usando llave \${SECRETO_LEIDO:0:15}***\" > /tmp/transaccion-vm.txt
  gcloud storage cp /tmp/transaccion-vm.txt ${BUCKET_AUTORIZADO}/

  echo -e '\n=== 4. INTENTANDO LISTAR OTRAS VMs DEL PROYECTO (DEBE FALLAR CON 403) ==='
  gcloud compute instances list || echo '-> BLOQUEADO CORRECTAMENTE POR IAM: La VM no tiene permiso para espiar la infraestructura.'
"
```

Verifica desde Cloud Shell que el archivo creado por la máquina virtual llegó al bucket autorizado:

```bash
gcloud storage cat $BUCKET_AUTORIZADO/transaccion-vm.txt
```

¡Acabas de construir una arquitectura *Zero-Trust* donde el servidor cumple su función de negocio leyendo secretos en memoria y guardando datos sin almacenar una sola credencial en disco y sin permisos para comprometer el resto de tu nube!

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

Para dejar nuestro proyecto completamente limpio y sin cargos activos, ejecuta en **Cloud Shell** la siguiente secuencia de limpieza:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab02 && source env.sh

# 1. Eliminar la Máquina Virtual
gcloud compute instances delete vm-segura-lab02 --zone=$ZONE --quiet

# 2. Eliminar los dos Buckets de Cloud Storage y su contenido
gcloud storage rm --recursive $BUCKET_AUTORIZADO
gcloud storage rm --recursive $BUCKET_CONFIDENCIAL

# 3. Eliminar el Secreto y todas sus versiones en Secret Manager
gcloud secrets delete api-key-pasarela-pagos --quiet

# 4. Eliminar la Cuenta de Servicio (Service Account)
gcloud iam service-accounts delete $SA_EMAIL --quiet

# 5. Eliminar el Rol Personalizado de IAM
# (Nota: un rol eliminado puede recuperarse con 'gcloud iam roles undelete' durante 7 días; su ID no puede
#  reutilizarse hasta 44 días después del borrado. Por eso el ID lleva un sufijo de fecha en env.sh)
gcloud iam roles delete $ROLE_ID --project=$PROJECT_ID --quiet
```

### Verificación Final de Limpieza
Ejecuta los siguientes comandos para confirmar que no queden instancias, buckets ni secretos activos:

```bash
echo "=== Instancias VM ==="
gcloud compute instances list

echo "=== Buckets Cloud Storage ==="
gcloud storage buckets list

echo "=== Secretos en Secret Manager ==="
gcloud secrets list
```

---

## 6. Conclusiones

En este segundo laboratorio has dominado los pilares de seguridad e identidad que distinguen a un arquitecto profesional de Google Cloud:
- Comprendiste por qué los roles básicos (`Owner`/`Editor`) y las llaves descargadas (`key.json`) son riesgos críticos de seguridad y cómo reemplazarlos por **Cuentas de Servicio dedicadas** y **Suplantación Segura (`--impersonate-service-account`)**.
- Creaste un **Rol Personalizado (*Custom Role*)** para hacer cumplir reglas de negocio estrictas (permitir escribir pero impedir borrar objetos en Cloud Storage).
- Aplicaste permisos de IAM **a nivel de recurso** (sobre un bucket y un secreto específicos), demostrando que un servicio puede operar en un proyecto sin siquiera saber que existen otros buckets o servidores al lado suyo.
- Administraste el ciclo de vida de credenciales críticas con **Secret Manager**, rotando versiones y entregándolas dinámicamente a una máquina virtual en tiempo de ejecución.

---

## 7. Retos Prácticos (Challenges)

Pon a prueba tu dominio de seguridad en GCP con estos tres retos:

1. **Reto 1 — Acceso Temporal con IAM Conditions (Expiración Automática)**:
   Crea una cuenta de servicio de prueba y asígnale el rol `roles/compute.viewer` sobre tu proyecto, pero agregando una **Condición de IAM (`--condition`)** que haga que el permiso expire automáticamente dentro de **15 minutos** usando la expresión CEL `request.time < timestamp("AAAA-MM-DDTHH:MM:SSZ")`.
   *(Pista: Revisa `gcloud projects add-iam-policy-binding --help` buscando la bandera `--condition-from-file` o `--condition`)*.

2. **Reto 2 — Auditoría Forense de Secret Manager (Data Access Logs)**:
   Habilita los registros de auditoría de lectura de datos (*Data Read Audit Logs*) para el servicio **Secret Manager** en `IAM & Admin -> Audit Logs` (en la consola web), accede a un secreto desde Cloud Shell y luego busca en **Cloud Logging** el evento exacto (`google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion`) que revela **quién** leyó el secreto y desde qué dirección IP.

3. **Reto 3 — Destrucción Criptográfica Irreversible de una Versión**:
   Crea un secreto con 3 versiones (`1`, `2`, `3`). Investiga cuál es el comando de `gcloud secrets versions` para **destruir permanentemente (`destroy`)** la versión `1` (a diferencia de `disable`), e intenta luego volver a habilitarla para comprobar que la destrucción de una versión en Secret Manager es irreversible.

---

## 8. Referencias Oficiales

- **Referencia CLI: `gcloud iam roles`**: [https://docs.cloud.google.com/sdk/gcloud/reference/iam/roles](https://docs.cloud.google.com/sdk/gcloud/reference/iam/roles)
- **Referencia CLI: `gcloud iam service-accounts`**: [https://docs.cloud.google.com/sdk/gcloud/reference/iam/service-accounts](https://docs.cloud.google.com/sdk/gcloud/reference/iam/service-accounts)
- **Referencia CLI: `gcloud secrets` (Secret Manager)**: [https://docs.cloud.google.com/sdk/gcloud/reference/secrets](https://docs.cloud.google.com/sdk/gcloud/reference/secrets)
- **Control de Acceso en Cloud Storage con IAM**: [https://docs.cloud.google.com/storage/docs/access-control/iam](https://docs.cloud.google.com/storage/docs/access-control/iam)
- **Guía de Suplantación de Cuentas de Servicio (`--impersonate-service-account`)**: [https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct)
