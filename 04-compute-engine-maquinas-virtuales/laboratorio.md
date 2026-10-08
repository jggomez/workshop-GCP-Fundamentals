# Laboratorio 04: Creación de Máquinas Virtuales, Discos Persistentes, Snapshots y Clústeres Autoescalables en Compute Engine

- **Duración estimada**: 90 minutos (1 hora y 30 minutos)
- **Nivel**: Intermedio / Práctico
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud` CLI)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Aprovisionar y administrar infraestructura de cómputo y almacenamiento en bloque en **Google Compute Engine** utilizando **Google Cloud Shell**. Durante la sesión crearás una máquina virtual Linux con un servidor web automatizado, te conectarás a ella mediante SSH y túneles seguros, crearás y montarás un disco persistente adicional desde cero, realizarás copias de seguridad (*Snapshots*) con prueba de restauración y, finalmente, desplegarás un **Clúster de Máquinas Virtuales con Autoescalamiento y Autoreparación (Managed Instance Group - MIG)** sometiéndolo a una prueba de estrés de CPU en tiempo real.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Crear máquinas virtuales en Compute Engine mediante `gcloud compute instances create` inyectando scripts de inicio (*Startup Scripts*) y etiquetas de red (*Network Tags*).
2. Conectarse de forma segura a instancias Linux desde Cloud Shell usando **SSH directo**, **ejecución remota de comandos** y **túneles por Identity-Aware Proxy (`--tunnel-through-iap`)**.
3. Crear **Discos Persistentes (`pd-balanced`)**, asociarlos en caliente a una VM (`attach-disk`), descubrir el dispositivo de bloques en Linux (`lsblk`), formatearlo en `ext4`, montarlo y persistirlo con `UUID` en `/etc/fstab`.
4. Generar **Snapshots (Instantáneas)** de discos, inspeccionar su tamaño incremental y restaurar un nuevo disco a partir de una copia de seguridad.
5. Diseñar **Instance Templates (Plantillas de Instancia)** que consulten el servidor de metadatos interno de GCP (`metadata.google.internal`).
6. Configurar **Health Checks (Comprobaciones de Salud)**, crear un **Managed Instance Group (MIG)** con políticas de **Autoscaling** por uso de CPU y comprobar en vivo cómo el clúster escala horizontalmente ante picos de demanda.
7. Destruir ordenadamente toda la infraestructura creada para dejar el proyecto con **$0.00 USD de gasto residual**.

---

## 3. Estimación de Costos en la Nube

> [!IMPORTANT]
> **Costo total estimado por ejecutar este laboratorio durante 90 minutos: ~$0.04 a $0.08 USD** (cubierto al 100% si cuentas con créditos de Free Trial o cupón educativo, y elegible parcialmente dentro del *Free Tier* mensual si limpias los recursos al terminar).

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia en `us-central1` | Costo por 1.5 Horas de Laboratorio |
| :--- | :--- | :--- | :--- |
| **VM Individual (`vm-laboratorio-01`)** | 1x `e2-micro` (2 vCPUs compartidas, 1 GB RAM) + Boot Disk 10 GB | ~$0.0084 / hora | **~$0.013 USD** |
| **Disco Persistente de Datos (`disco-datos-01`)** | 1x `pd-balanced` de 10 GB + 1x Disco restaurado de 10 GB | $0.10 por GB/mes (~$0.0014/hora por 10 GB) | **~$0.004 USD** |
| **Snapshot (`snap-disco-datos-v1`)** | ~50 MB de bloques reales comprimidos | $0.026 por GB/mes | **< $0.001 USD** |
| **Clúster Autoescalable (MIG)** | De 1 a 4 instancias `e2-micro` durante la prueba de carga (~30 min) | ~$0.0084 / hora por instancia | **~$0.025 USD** |
| **Reglas de Firewall, Health Check y Plantilla** | Recursos lógicos de control de red y cómputo | Gratuitos | **$0.000 USD** |
| **TOTAL ESTIMADO DE LA SESIÓN** | **Ejecutando la limpieza al finalizar el laboratorio** | — | **~$0.043 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno en Cloud Shell (5 min)

1. Ingresa a [https://console.cloud.google.com](https://console.cloud.google.com) y abre **Google Cloud Shell** haciendo clic en el ícono `>_` de la esquina superior derecha.
2. Ejecuta el siguiente bloque en Cloud Shell para definir las variables de entorno de trabajo y asegurarte de que la API de Compute Engine esté activa:

```bash
mkdir -p ~/workshop-gcp/lab04
cd ~/workshop-gcp/lab04

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export REGION="us-central1"
export ZONE="us-central1-a"
EOF
source env.sh

gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE

# Asegurar que la API de Compute Engine esté habilitada
gcloud services enable compute.googleapis.com

echo "Entorno listo -> Proyecto: $PROJECT_ID | Región: $REGION | Zona: $ZONE"

# Este laboratorio usa la red 'default' (con su regla SSH predeterminada): verificar que exista
gcloud compute networks describe default --format="value(name)" 2>/dev/null \
  || echo "AVISO: tu proyecto no tiene la red 'default'. Créala con: gcloud compute networks create default --subnet-mode=auto && gcloud compute firewall-rules create default-allow-ssh --network=default --allow=tcp:22"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab04 && source env.sh`

---

### Paso 2: Creación de una Máquina Virtual y Regla de Firewall (15 min)

Crearemos nuestra primera máquina virtual llamada `vm-laboratorio-01` usando la imagen oficial de **Debian 12**. Además, le pasaremos un **Startup Script** para que apenas arranque instale automáticamente el servidor web **Nginx** y muestre una página personalizada.

#### 2.1. Crear la Regla de Firewall para permitir tráfico HTTP (Puerto 80)
Por defecto, la red VPC `default` bloquea todas las conexiones entrantes desde Internet hacia tus VMs (excepto SSH en el puerto 22). Crearemos una regla de firewall que permita el tráfico en el puerto TCP `80` únicamente hacia las VMs que tengan la etiqueta de red (`tag`) llamada `http-server`:

```bash
gcloud compute firewall-rules create allow-http-lab04 \
  --network=default \
  --action=ALLOW \
  --direction=INGRESS \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=http-server \
  --description="Permite trafico HTTP puerto 80 para el Laboratorio 04"
```

#### 2.2. Crear la Máquina Virtual `vm-laboratorio-01` desde Cloud Shell
Primero guardamos el *Startup Script* en un archivo. Pasarlo con `--metadata-from-file` es la forma recomendada: con `--metadata=startup-script='...'` gcloud separa los valores por comas, y cualquier coma dentro del script (por ejemplo en CSS) rompe el comando.

```bash
cat << 'SCRIPT' > startup-web.sh
#! /bin/bash
apt-get update
apt-get install -y nginx
HOSTNAME=$(hostname)
cat <<EOF > /var/www/html/index.html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Lab 04 GCP</title></head>
<body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
  <h1>¡Hola desde Google Compute Engine!</h1>
  <p>Servidor: <b>$HOSTNAME</b></p>
  <p>Desplegado automáticamente con un Startup Script desde Cloud Shell.</p>
</body>
</html>
EOF
systemctl restart nginx
SCRIPT
```

Ahora aprovisiona la máquina virtual:

```bash
gcloud compute instances create vm-laboratorio-01 \
  --zone=$ZONE \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=10GB \
  --boot-disk-type=pd-balanced \
  --tags=http-server \
  --labels=curso=workshop-gcp,laboratorio=lab04 \
  --metadata-from-file=startup-script=startup-web.sh
```

#### 2.3. Verificar el estado y probar el servidor web
1. Lista tus instancias para ver su IP interna (`INTERNAL_IP`) y su IP externa pública (`EXTERNAL_IP`):

```bash
gcloud compute instances list
```

2. El `startup-script` tarda entre 30 segundos y un par de minutos en instalar Nginx. El siguiente bloque reintenta hasta que la página responda y luego la muestra:

```bash
# Obtener la IP pública automáticamente y hacer una petición HTTP con curl
export VM_EXT_IP=$(gcloud compute instances describe vm-laboratorio-01 --zone=$ZONE --format="get(networkInterfaces[0].accessConfigs[0].natIP)")

echo "Probando conexión a http://$VM_EXT_IP ..."
for i in $(seq 1 18); do
  curl -s --max-time 5 http://$VM_EXT_IP | grep -q "Compute Engine" && break
  echo "Intento $i: Nginx aún no responde, reintentando en 10 s..."; sleep 10
done
curl http://$VM_EXT_IP
```

3. **Verificación en la Consola Web**:
   - En la Consola de GCP, ve al menú `☰` -> **Compute Engine** -> **Instancias de VM (VM instances)**.
   - Verás tu instancia `vm-laboratorio-01` con un ícono verde. Si haces clic en el enlace de su **IP externa** (asegúrate de que el navegador use `http://` y no `https://`), verás la página web renderizada en tu navegador.

---

### Paso 3: Cómo Acceder a las Máquinas Virtuales (SSH e IAP) (10 min)

Existen tres formas principales de conectarse y administrar una máquina virtual Linux en Google Cloud. Vamos a practicarlas:

#### 3.1. Método 1: Ejecutar un comando remoto por SSH sin entrar en sesión interactiva
Ideal para scripts de automatización cuando quieres consultar algo rápido en la VM desde Cloud Shell:

```bash
# Consultar desde Cloud Shell el tiempo de actividad (uptime) y la memoria libre de nuestra VM
gcloud compute ssh vm-laboratorio-01 \
  --zone=$ZONE \
  --command="uptime && free -m"
```
*(Nota: Si es la primera vez que usas `gcloud compute ssh` en tu sesión de Cloud Shell y te pregunta si deseas generar llaves SSH y asignar una frase de contraseña o passphrase, simplemente presiona **Enter** dos veces para dejarla en blanco).*

#### 3.2. Método 2: Conexión mediante Túnel Seguro de Identity-Aware Proxy (IAP)
Como aprendimos en el `teoria.md`, en entornos corporativos nos conectamos a través del túnel **Cloud IAP** (`--tunnel-through-iap`), el cual valida tu identidad en IAM:

```bash
gcloud compute ssh vm-laboratorio-01 \
  --zone=$ZONE \
  --tunnel-through-iap \
  --command="echo 'Conectado exitosamente a través de túnel seguro IAP en:' \$(hostname)"
```

#### 3.3. Método 3: Sesión SSH interactiva
También puedes hacer clic en el botón **SSH** al lado de la VM en la Consola Web (que abre una terminal en el navegador), o entrar desde **Cloud Shell** con `gcloud compute ssh vm-laboratorio-01 --zone=$ZONE` (sin `--command`).

> [!NOTE]
> **Todavía NO entres en modo interactivo.** Primero crearemos y conectaremos el disco nuevo; usaremos la sesión interactiva en el Paso 4.3.

---

### Paso 4: Creación, Asociación, Formateo y Montaje de Discos Persistentes (20 min)

En la vida real, es una **excelente práctica arquitectónica** separar el disco del Sistema Operativo (`Boot Disk`) del disco donde viven los datos de tu aplicación o base de datos (`Data Disk`). Así, si necesitas actualizar el sistema operativo o cambiar de máquina, solo desconectas el disco de datos y lo conectas al nuevo servidor.

#### 4.1. Crear un Disco Persistente adicional desde Cloud Shell
Asegúrate de estar en tu terminal de **Cloud Shell** (fuera de la VM) y crea un disco persistente SSD equilibrado (`pd-balanced`) de **10 GB** en la misma zona de nuestra máquina virtual:

```bash
gcloud compute disks create disco-datos-01 \
  --size=10GB \
  --type=pd-balanced \
  --zone=$ZONE \
  --labels=uso=datos-aplicacion,laboratorio=lab04
```

Verifica que el disco exista ejecutando:

```bash
gcloud compute disks list
```
Observa que ahora tienes dos discos en tu zona: `vm-laboratorio-01` (el disco de arranque de la VM) y `disco-datos-01` (nuestro nuevo disco independiente).

#### 4.2. Asociar (Attach) el disco en caliente a la Máquina Virtual
Sin apagar nuestra máquina virtual `vm-laboratorio-01`, vamos a conectarle el disco `disco-datos-01` asignándole el nombre de dispositivo lógico `disco-extra`:

```bash
gcloud compute instances attach-disk vm-laboratorio-01 \
  --disk=disco-datos-01 \
  --device-name=disco-extra \
  --zone=$ZONE
```

#### 4.3. Descubrir, Formatear y Montar el Disco dentro de la VM Linux
El disco ya está "enchufado" virtualmente a la VM, pero como es un disco virgen recién creado, no tiene sistema de archivos ni está montado en ninguna carpeta.

1. **Entra por SSH de forma interactiva a la máquina virtual**:

```bash
gcloud compute ssh vm-laboratorio-01 --zone=$ZONE
```

*(Observa que tu prompt de terminal cambió de `tu_usuario@cloudshell` a **`tu_usuario@vm-laboratorio-01`**).*

2. **Descubre los discos conectados** usando `lsblk` y mirando los enlaces simbólicos de Google Cloud en `/dev/disk/by-id/`:

```bash
lsblk
ls -l /dev/disk/by-id/google-*
```

Analiza la salida:
- `sda` (10G) es tu disco de arranque donde está montada la raíz `/`.
- **`sdb` (10G)** (apuntado también por `/dev/disk/by-id/google-disco-extra`) es nuestro nuevo disco de 10 GB que aún no tiene particiones ni punto de montaje (`MOUNTPOINTS` está vacío).

3. **Formatear el disco nuevo con el sistema de archivos `ext4`**:

```bash
sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/disk/by-id/google-disco-extra
```

4. **Crear el directorio de montaje `/mnt/datos` y montar el disco**:

```bash
sudo mkdir -p /mnt/datos
sudo mount -o discard,defaults /dev/disk/by-id/google-disco-extra /mnt/datos

# Dar permisos de escritura a todos los usuarios en el disco montado para nuestras pruebas
sudo chmod a+w /mnt/datos
```

5. **Verificar con `df -h` que el disco de 10 GB ya esté montado en `/mnt/datos` y escribir datos de prueba**:

```bash
df -h /mnt/datos

# Crear un archivo importante de prueba dentro del nuevo disco persistente
cat <<EOF > /mnt/datos/registro-clientes.txt
ID_CLIENTE,NOMBRE,FECHA_REGISTRO,ESTADO
1001,Empresa Alpha S.A.,$(date -Iseconds),ACTIVO
1002,Corporacion Beta,$(date -Iseconds),ACTIVO
1003,Laboratorio GCP 04,$(date -Iseconds),VERIFICADO
EOF

cat /mnt/datos/registro-clientes.txt
```

6. **Configurar el montaje automático en `/etc/fstab` (Para que sobreviva a reinicios)**:
Si reiniciáramos la VM ahora mismo, Linux olvidaría que `/mnt/datos` estaba montado. Vamos a respaldar `/etc/fstab` y registrar el identificador único universal (`UUID`) del disco:

```bash
# Hacer copia de seguridad de /etc/fstab
sudo cp /etc/fstab /etc/fstab.backup

# Obtener el UUID del disco y agregarlo a /etc/fstab con la opción nofail (permite que la VM arranque aunque el disco se desconecte)
UUID_DISCO=$(sudo blkid -s UUID -o value /dev/disk/by-id/google-disco-extra)
echo "UUID=$UUID_DISCO /mnt/datos ext4 discard,defaults,nofail 0 2" | sudo tee -a /etc/fstab

# Ver la línea agregada en /etc/fstab
tail -n 2 /etc/fstab

# Forzar que todos los buffers en memoria se escriban en el disco físico antes del snapshot
sync
```

7. **Sal de la sesión SSH de la máquina virtual para regresar a tu Cloud Shell**:

```bash
exit
```

*(Asegúrate de que tu prompt vuelva a mostrar **`@cloudshell` (`$PROJECT_ID`)** antes de continuar con el Paso 5).*

---

### Paso 5: Copias de Seguridad (Snapshots) y Restauración de Discos (15 min)

Ahora que nuestro disco `disco-datos-01` contiene el archivo `registro-clientes.txt`, realizaremos un **Snapshot (Instantánea)** y probaremos cómo restaurar ese snapshot en un disco completamente nuevo para verificar que los datos están a salvo.

#### 5.1. Crear un Snapshot del disco `disco-datos-01`
Ejecuta en **Cloud Shell**:

```bash
gcloud compute snapshots create snap-disco-datos-v1 \
  --source-disk=disco-datos-01 \
  --source-disk-zone=$ZONE \
  --storage-location=$REGION \
  --description="Primer backup incremental del disco de datos Lab 04"
```

#### 5.2. Inspeccionar el Snapshot creado
```bash
gcloud compute snapshots list \
  --format="table(name, diskSizeGb:label=TAMANO_DISCO_GB, storageBytes:label=BYTES_REALES_COBRADOS, status)"
```

> [!TIP]
> **Observa la columna `BYTES_REALES_COBRADOS` (`storageBytes`)**: Aunque el disco original mide **10 GB**, verás que el snapshot ocupa apenas unos pocos megabytes (o incluso menos) porque los snapshots de Google Cloud comprimen y guardan **únicamente los bloques que contienen información real**.

#### 5.3. Simulacro de Recuperación: Crear un Nuevo Disco a partir del Snapshot
Imagina que alguien borró por accidente datos o necesitas clonar este disco hacia otro entorno. Creemos un nuevo disco llamado `disco-restaurado-01` usando como origen nuestro snapshot `snap-disco-datos-v1`:

```bash
# 1. Crear el nuevo disco restaurado desde el snapshot
gcloud compute disks create disco-restaurado-01 \
  --source-snapshot=snap-disco-datos-v1 \
  --type=pd-balanced \
  --zone=$ZONE

# 2. Asociar el disco restaurado a nuestra VM para comprobar que los archivos están adentro
gcloud compute instances attach-disk vm-laboratorio-01 \
  --disk=disco-restaurado-01 \
  --device-name=disco-restaurado \
  --zone=$ZONE

# 3. Montar el disco restaurado en /mnt/recuperacion y leer el archivo registro-clientes.txt
gcloud compute ssh vm-laboratorio-01 --zone=$ZONE --command="
  sudo mkdir -p /mnt/recuperacion &&
  sudo mount -o discard,defaults /dev/disk/by-id/google-disco-restaurado /mnt/recuperacion &&
  echo '=== CONTENIDO RECUPERADO DESDE EL SNAPSHOT ===' &&
  cat /mnt/recuperacion/registro-clientes.txt
"
```

¡Acabas de comprobar el ciclo completo de respaldo y recuperación ante desastres (*Disaster Recovery*) de un disco en Google Cloud!

---

### Paso 6: Creación de un Clúster de Máquinas Virtuales con Autoescalamiento (MIG) (20 min)

En esta etapa final construiremos una arquitectura de producción elástica: un **Managed Instance Group (MIG)** que monitorea la salud del servidor web (*Autohealing*) y escala automáticamente de **1 a 4 máquinas virtuales** cuando el uso de CPU supera el **60%**.

#### 6.1. Crear una Plantilla de Instancia (Instance Template)
Nuestra plantilla instalará `nginx` y la herramienta `stress` (para simular picos de carga), y consultará al **Servidor de Metadatos de GCP (`metadata.google.internal`)** para mostrar en pantalla el nombre y zona de cada nodo del clúster:

Como este script contiene comas (en el CSS `rgba(0,0,0,0.1)`), es **obligatorio** pasarlo desde un archivo con `--metadata-from-file`; con `--metadata=startup-script='...'` gcloud fallaría con `Bad syntax for dict arg`.

```bash
cat << 'SCRIPT' > startup-mig.sh
#! /bin/bash
apt-get update
apt-get install -y nginx stress
HOSTNAME=$(hostname)
ZONE=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/zone" -H "Metadata-Flavor: Google" | awk -F/ '{print $NF}')
INTERNAL_IP=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip" -H "Metadata-Flavor: Google")

cat <<EOF > /var/www/html/index.html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Clúster Autoescalable GCP</title></head>
<body style="font-family: sans-serif; background-color: #f0f4f8; text-align: center; padding-top: 40px;">
  <div style="background: white; max-width: 600px; margin: auto; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
    <h1 style="color: #1a73e8;">Clúster MIG Autoescalable</h1>
    <p><b>Nombre del Nodo (VM):</b> $HOSTNAME</p>
    <p><b>Zona Física de GCP:</b> $ZONE</p>
    <p><b>IP Privada VPC:</b> $INTERNAL_IP</p>
  </div>
</body>
</html>
EOF
systemctl enable nginx
systemctl restart nginx
SCRIPT

gcloud compute instance-templates create plantilla-web-cluster-v1 \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=10GB \
  --boot-disk-type=pd-balanced \
  --tags=http-server \
  --metadata-from-file=startup-script=startup-mig.sh
```

#### 6.2. Crear un Health Check HTTP (Sonda de Autoreparación)
El MIG utilizará este *Health Check* cada 10 segundos para verificar que el puerto `80` responda `HTTP 200 OK`. Si en alguna VM falla Nginx, el MIG la recreará automáticamente:

```bash
gcloud compute health-checks create http hc-http-cluster-lab04 \
  --port=80 \
  --request-path=/index.html \
  --check-interval=10s \
  --timeout=5s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3
```

#### 6.3. Crear el Grupo de Instancias Administrado (MIG) y activar el Autoescalamiento
Crearemos el clúster llamado `cluster-web-mig` comenzando con 1 instancia y luego le aplicaremos la política de autoescalamiento:

```bash
# 1. Crear el Managed Instance Group (MIG) con Autohealing conectado al Health Check
gcloud compute instance-groups managed create cluster-web-mig \
  --base-instance-name=nodo-web \
  --template=plantilla-web-cluster-v1 \
  --size=1 \
  --zone=$ZONE \
  --health-check=hc-http-cluster-lab04 \
  --initial-delay=90

# 2. Configurar la política de Autoescalamiento (Mínimo: 1 VM, Máximo: 4 VMs, Meta de CPU: 60%)
gcloud compute instance-groups managed set-autoscaling cluster-web-mig \
  --zone=$ZONE \
  --min-num-replicas=1 \
  --max-num-replicas=4 \
  --target-cpu-utilization=0.60 \
  --cool-down-period=60
```

#### 6.4. Verificar el nodo inicial del clúster
Lista las instancias que pertenecen al clúster MIG:

```bash
# Esperar a que el grupo esté estable (VM creada y sin acciones pendientes); máximo 5 minutos
gcloud compute instance-groups managed wait-until cluster-web-mig --stable --zone=$ZONE --timeout=300

gcloud compute instance-groups managed list-instances cluster-web-mig --zone=$ZONE
```

Verás una instancia con un nombre autogenerado similar a `nodo-web-xxxx`. Si su `HEALTH_STATE` todavía no es `HEALTHY`, espera un minuto más (el *Health Check* necesita 2 respuestas correctas después del `--initial-delay` de 90 segundos) y vuelve a listar.

#### 6.5. ¡Prueba de Fuego! Simular un Pico de Tráfico/CPU y Observar el Autoescalamiento
Vamos a inyectar carga del 100% de CPU durante 4 minutos en la instancia del clúster para superar el umbral del 60% y obligar a Google Cloud a escalar horizontalmente el clúster:

```bash
# 1. Capturar automáticamente el nombre de la primera VM del clúster MIG
export NODO_INICIAL=$(gcloud compute instance-groups managed list-instances cluster-web-mig --zone=$ZONE --format="value(instance.basename())" | head -n 1)
echo "Inyectando carga de CPU en el nodo: $NODO_INICIAL"

# 2. Ejecutar 'stress' en segundo plano dentro del nodo durante 240 segundos (4 minutos)
gcloud compute ssh $NODO_INICIAL \
  --zone=$ZONE \
  --command="nohup stress --cpu 4 --timeout 240s > /dev/null 2>&1 &"
```

**Observa cómo reacciona el clúster en tiempo real:**
1. **En la Consola Web**:
   - Ve a `☰` -> **Compute Engine** -> **Grupos de instancias (Instance groups)** y haz clic en **`cluster-web-mig`**.
   - Entra a la pestaña **Supervisión (Monitoring)**. Después de 60 a 90 segundos verás cómo la gráfica de uso de CPU sube por encima del 60% y el tamaño del grupo (**Instances**) salta automáticamente de **1 a 3 o 4 máquinas virtuales**.
2. **Desde Cloud Shell**:
   Ejecuta el siguiente comando cada 30 segundos durante los próximos 2 minutos:

```bash
gcloud compute instance-groups managed list-instances cluster-web-mig --zone=$ZONE
```

¡Verás aparecer nuevas instancias (`nodo-web-xxxx`) con `ACTION: CREATING` y luego `NONE` (`RUNNING`) creadas de manera 100% autónoma por el *Autoscaler* de Compute Engine!

> [!TIP]
> Si después de 3 minutos el grupo sigue con 1 sola VM, revisa en la pestaña **Supervisión (Monitoring)** que la CPU haya superado el 60% y repite la carga durante más tiempo (por ejemplo `--timeout 480s`). Las `e2-micro` son máquinas de núcleo compartido y la métrica tarda un poco en reflejar la carga sostenida. Después de que termina la carga, el autoscaler espera unos 10 minutos antes de reducir el grupo.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO!** En este laboratorio hemos aprovisionado hasta 5 máquinas virtuales, múltiples discos persistentes y un snapshot. Para asegurarte de que no se siga cobrando ni un solo centavo después de terminar la clase, ejecuta los siguientes comandos en **Cloud Shell** en este orden exacto (porque no puedes borrar una plantilla si el MIG la sigue usando, ni puedes borrar un disco si sigue adjunto a una VM).

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab04 && source env.sh

# 1. Eliminar el Clúster Autoescalable (MIG) — Esto destruye automáticamente todas las VMs nodo-web-*
gcloud compute instance-groups managed delete cluster-web-mig \
  --zone=$ZONE \
  --quiet

# 2. Eliminar la Plantilla de Instancia (Instance Template) y el Health Check
gcloud compute instance-templates delete plantilla-web-cluster-v1 --quiet
gcloud compute health-checks delete hc-http-cluster-lab04 --quiet

# 3. Eliminar nuestra primera Máquina Virtual (vm-laboratorio-01)
# Nota: Al borrar la VM se borra su disco de arranque, pero los discos de datos adicionales quedan desacoplados
gcloud compute instances delete vm-laboratorio-01 \
  --zone=$ZONE \
  --quiet

# 4. Eliminar los dos Discos Persistentes adicionales (el original y el restaurado)
gcloud compute disks delete disco-datos-01 disco-restaurado-01 \
  --zone=$ZONE \
  --quiet

# 5. Eliminar el Snapshot de copia de seguridad
gcloud compute snapshots delete snap-disco-datos-v1 --quiet

# 6. Eliminar la regla de Firewall creada para el laboratorio
gcloud compute firewall-rules delete allow-http-lab04 --quiet
```

### Auditoría Final de Limpieza (Verificación Cero Costos)
Ejecuta este bloque de verificación final. **Todos los comandos deben responder `Listed 0 items.`**:

```bash
echo "=== Verificando Instancias de VM ==="
gcloud compute instances list

echo "=== Verificando Discos Persistentes ==="
gcloud compute disks list

echo "=== Verificando Snapshots ==="
gcloud compute snapshots list

echo "=== Verificando Grupos de Instancias (MIGs) ==="
gcloud compute instance-groups managed list
```

---

## 6. Conclusiones

En este laboratorio has dominado el ciclo completo de **Infraestructura como Servicio (IaaS)** en Google Cloud Platform:
- Aprendiste a aprovisionar servidores Linux automatizando su configuración inicial desde el primer segundo mediante **Startup Scripts**.
- Comprobaste que en la nube el almacenamiento está desacoplado del cómputo: creaste un **Disco Persistente** independiente, lo conectaste en caliente, lo formateaste en `ext4` y protegiste su montaje mediante `UUID` en `/etc/fstab` con la bandera `nofail`.
- Implementaste una estrategia real de respaldo y recuperación usando **Snapshots incrementales**, restaurando un volumen nuevo con los datos íntegros.
- Evolucionaste de administrar "servidores individuales" (*Pets*) a administrar **clústeres elásticos y autocurables (*Cattle*)** mediante **Instance Templates**, **Health Checks** y **Managed Instance Groups (MIGs)** con autoescalamiento basado en demanda real de CPU.

---

## 7. Retos Prácticos (Challenges)

Si deseas llevar tus habilidades al siguiente nivel (puedes intentarlos antes de ejecutar la limpieza o recreando un recurso rápido):

1. **Reto 1 — Redimensionamiento de Disco en Caliente (Zero-Downtime Resize)**:
   Crea un disco persistente de `10GB`, móntalo en una VM y luego usa el comando `gcloud compute disks resize` para aumentarlo a `25GB` **sin apagar la máquina ni desmontar el disco**. Luego entra por SSH y averigua cómo usar el comando `sudo resize2fs` de Linux para que `df -h` reconozca los nuevos 25 GB inmediatamente.

2. **Reto 2 — Prueba de Autoreparación (Autohealing en Acción)**:
   Con el clúster MIG encendido, entra por SSH a uno de los nodos (`nodo-web-*`) y detén intencionalmente el servidor web ejecutando `sudo systemctl stop nginx`. Monitorea con `gcloud compute instance-groups managed list-instances` qué ocurre cuando el *Health Check* detecta que el puerto 80 dejó de responder tras 3 intentos fallidos (`RECREATING`).

3. **Reto 3 — Clúster de Ahorro Extremo con Spot VMs y Cobertura Regional**:
   Investiga en la ayuda de `gcloud compute instance-templates create --help` cómo agregar la bandera `--provisioning-model=SPOT` para que las máquinas de tu clúster cuesten hasta un **80% menos**, y cómo crear un MIG **Regional** (`--region=us-central1` en lugar de `--zone=us-central1-a`) para que tus instancias se distribuyan automáticamente en 3 zonas distintas de Iowa.

---

## 8. Referencias Oficiales

- **Referencia CLI: `gcloud compute instances`**: [https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances)
- **Guía paso a paso para agregar y formatear Discos Persistentes en Linux**: [https://docs.cloud.google.com/compute/docs/disks/add-persistent-disk](https://docs.cloud.google.com/compute/docs/disks/add-persistent-disk)
- **Creación y restauración de Snapshots de discos**: [https://docs.cloud.google.com/compute/docs/disks/create-snapshots](https://docs.cloud.google.com/compute/docs/disks/create-snapshots)
- **Uso de Scripts de Inicio (Startup Scripts) en VMs Linux**: [https://docs.cloud.google.com/compute/docs/instances/startup-scripts/linux](https://docs.cloud.google.com/compute/docs/instances/startup-scripts/linux)
- **Creación de Grupos de Instancias Administrados (MIGs)**: [https://docs.cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances](https://docs.cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances)
