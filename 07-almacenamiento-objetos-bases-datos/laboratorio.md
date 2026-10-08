# Laboratorio 07: Almacenamiento de Objetos en Cloud Storage y Bases de Datos Administradas con Cloud SQL (PostgreSQL) y Firestore

- **Duración estimada**: 85–90 minutos
- **Nivel**: Intermedio / Datos, Almacenamiento y Bases de Datos
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud`, `psql`, `python3`)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Implementar y operar una capa completa de persistencia políglota en Google Cloud Platform combinando los tres motores más utilizados en arquitecturas modernas:
1. **Cloud Storage** para objetos no estructurados (configurando **Versionado de Objetos**, recuperación de archivos borrados y **Reglas de Ciclo de Vida** automáticas hacia `Nearline` y `Archive`).
2. **Cloud SQL para PostgreSQL** para datos relacionales transaccionales (aprovisionando una instancia administrada, creando esquemas SQL y ejecutando consultas).
3. **Cloud Firestore** para datos NoSQL documentales flexibles (creando colecciones y documentos JSON anidados desde Python en Cloud Shell y explorándolos en tiempo real).

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Crear Buckets en **Cloud Storage** habilitando **Object Versioning** para recuperar versiones anteriores de archivos sobrescritos o eliminados accidentalmente.
2. Configurar **Políticas de Ciclo de Vida (*Object Lifecycle Management*)** en formato JSON para reducir costos moviendo objetos antiguos a clases `NEARLINE` y `ARCHIVE`.
3. Aprovisionar una instancia de base de datos relacional **Cloud SQL para PostgreSQL** desde la línea de comandos (`gcloud sql instances create`).
4. Crear bases de datos y usuarios en Cloud SQL, conectarse de forma segura con `gcloud sql connect` y ejecutar sentencias DDL/DML (`CREATE TABLE`, `INSERT`, `SELECT`).
5. Inicializar una base de datos NoSQL **Cloud Firestore (Modo Nativo)** y manipular colecciones y documentos JSON con esquema flexible mediante el SDK de Python y la Consola Web.

---

## 3. Estimación de Costos en la Nube

> [!TIP]
> **Costo total estimado por ejecutar este laboratorio durante 90 minutos: ~$0.02 a $0.03 USD**

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia en `us-central1` | Costo por 1.5 Horas de Laboratorio |
| :--- | :--- | :--- | :--- |
| **Cloud Storage Bucket** | 1 bucket con versionado y ciclo de vida (< 10 KB de datos) | Primeros 5 GB/mes gratis en Free Tier | **$0.000 USD** |
| **Cloud SQL para PostgreSQL (`sql-tienda-lab07`)** | 1 instancia `db-f1-micro` (Edición Enterprise, disco SSD 10 GB) | ~$0.015 / hora | **~$0.022 USD** |
| **Cloud Firestore (Modo Nativo)** | 1 base de datos NoSQL Serverless (3 documentos JSON) | Primeros 1 GiB y 50,000 lecturas/día **Gratuitos** | **$0.000 USD** |
| **TOTAL ESTIMADO DE LA SESIÓN** | **Ejecutando la limpieza al finalizar el laboratorio** | — | **~$0.022 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno e Inicio del Aprovisionamiento de Cloud SQL (10 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables de entorno y habilita las APIs de **Cloud Storage**, **Cloud SQL Admin** y **Cloud Firestore**:

```bash
mkdir -p ~/workshop-gcp/lab07
cd ~/workshop-gcp/lab07

# Verificación previa: debe existir un proyecto activo en Cloud Shell
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No hay proyecto activo. Ejecuta: gcloud config set project TU_PROJECT_ID"
fi

# Guardar las variables del laboratorio en env.sh (Cloud Shell las pierde tras 40 min de inactividad)
cat > env.sh << EOF
export PROJECT_ID="$PROJECT_ID"
export REGION="us-central1"
export SQL_INSTANCE="sql-tienda-lab07"
export BUCKET_NAME="gs://${PROJECT_ID}-datalake-lab07"
EOF
source env.sh

gcloud config set project $PROJECT_ID

# Habilitar las APIs de bases de datos y almacenamiento
gcloud services enable \
  sqladmin.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com

echo "Proyecto activo: $PROJECT_ID | Región: $REGION"
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables con: `cd ~/workshop-gcp/lab07 && source env.sh`

#### 1.1. Lanzar la Creación de la Instancia de Cloud SQL en Segundo Plano (`--async`)
> [!TIP]
> **Truco de Ingeniería para Laboratorios**: Crear una instancia de base de datos relacional en Cloud SQL tarda unos **5 a 7 minutos** mientras Google aprovisiona la VM subyacente, formatea el disco cifrado e inicializa el motor PostgreSQL 16. Usando la bandera **`--async`**, dejaremos que Google Cloud la construya en segundo plano mientras nosotros realizamos el **Paso 2 (Cloud Storage)** sin perder un solo minuto de clase.

Ejecuta el siguiente comando en Cloud Shell:

```bash
gcloud sql instances create $SQL_INSTANCE \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB \
  --root-password="PasswordSeguraLab07!" \
  --deletion-protection \
  --async

echo "La instancia $SQL_INSTANCE se está aprovisionando en segundo plano..."
```
*(Nota: Observa que incluimos `--deletion-protection`, una buena práctica que impide que alguien borre una base de datos de producción por accidente).*

> [!WARNING]
> **No omitas `--edition=ENTERPRISE`.** Para PostgreSQL 16 o superior, la edición predeterminada de Cloud SQL es **Enterprise Plus**, que no admite máquinas de núcleo compartido como `db-f1-micro` y es considerablemente más cara. La edición Enterprise sí admite núcleo compartido, ideal para laboratorios. Ten en cuenta también que `db-f1-micro` no está cubierta por el SLA de Cloud SQL: úsala solo para pruebas.

---

### Paso 2: Almacenamiento de Objetos en Cloud Storage — Versionado y Ciclo de Vida (20 min)

Mientras nuestra instancia de PostgreSQL termina de crearse, trabajaremos a fondo con **Cloud Storage**.

#### 2.1. Crear el Bucket y Habilitar el Versionado de Objetos (*Object Versioning*)
```bash
# 1. Crear el bucket en us-central1 con acceso uniforme
gcloud storage buckets create $BUCKET_NAME \
  --location=$REGION \
  --uniform-bucket-level-access

# 2. Habilitar el Versionado de Objetos para proteger contra borrados o sobrescrituras accidentales
gcloud storage buckets update $BUCKET_NAME --versioning

# 3. Verificar que versioning_enabled esté en True
gcloud storage buckets describe $BUCKET_NAME --format="yaml(name, location, default_storage_class, versioning_enabled)"
```

#### 2.2. Probar la Protección de Versionado y Recuperación de un Archivo Sobrescrito
Simulemos que un analista sube un contrato importante (`contrato-marco.txt`) y luego otro usuario lo sobrescribe por error:

```bash
# 1. Crear y subir la Versión 1 (Original)
echo "CONTRATO OFICIAL V1: Monto acordado = $50,000 USD (Aprobado por Gerencia)" > contrato-marco.txt
gcloud storage cp contrato-marco.txt $BUCKET_NAME/

# 2. Sobrescribir el archivo por error con una Versión 2 corrupta
echo "CONTRATO V2 CORRUPTO: Monto = $0 USD (Error de digitacion)" > contrato-marco.txt
gcloud storage cp contrato-marco.txt $BUCKET_NAME/

# 3. Leer la versión actual en vivo (mostrará la V2 corrupta)
gcloud storage cat $BUCKET_NAME/contrato-marco.txt
```

¡Parece que perdimos el contrato original! Pero como activamos **Object Versioning**, listemos **todas las generaciones históricas** del objeto con la bandera `-a` (`--all-versions`):

```bash
gcloud storage ls -a $BUCKET_NAME/contrato-marco.txt
```

Verás **dos líneas** con el formato `gs://.../contrato-marco.txt#<NUMERO_GENERACION>`. La primera línea es la **Versión 1 original archivada**. Restauremósla automáticamente copiando esa primera generación de vuelta como versión principal:

```bash
# Capturar la URI exacta de la primera generación (Versión 1) y restaurarla
PRIMERA_VERSION=$(gcloud storage ls -a $BUCKET_NAME/contrato-marco.txt | head -n 1)
echo "Restaurando desde la generación histórica: $PRIMERA_VERSION"

gcloud storage cp "$PRIMERA_VERSION" $BUCKET_NAME/contrato-marco.txt

# Comprobar que el archivo activo volvió a ser el contrato original de $50,000 USD
gcloud storage cat $BUCKET_NAME/contrato-marco.txt
```

#### 2.3. Configurar Reglas de Ciclo de Vida (*Object Lifecycle Management*) para Optimizar Costos
Ahora crearemos un archivo `lifecycle.json` con tres reglas automáticas de FinOps:
1. Cambiar objetos de `STANDARD` a **`NEARLINE`** cuando cumplan **30 días**.
2. Cambiar objetos a **`ARCHIVE`** cuando cumplan **90 días**.
3. Eliminar versiones antiguas archivadas (`isLive: false`) cuando ya haya al menos **3 versiones más nuevas**.

```bash
cat << 'EOF' > lifecycle.json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 30, "matchesStorageClass": ["STANDARD"]}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "ARCHIVE"},
        "condition": {"age": 90, "matchesStorageClass": ["NEARLINE"]}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"isLive": false, "numNewerVersions": 3}
      }
    ]
  }
}
EOF

# Aplicar la política de ciclo de vida al bucket y verificarla
gcloud storage buckets update $BUCKET_NAME --lifecycle-file=lifecycle.json
gcloud storage buckets describe $BUCKET_NAME --format="json(lifecycle_config)"
```

---

### Paso 3: Base de Datos Relacional Administrada con Cloud SQL (PostgreSQL) (25 min)

Verifiquemos si nuestra instancia de **Cloud SQL (`sql-tienda-lab07`)** que lanzamos en el Paso 1 ya pasó al estado **`RUNNABLE`** (Lista para recibir conexiones):

```bash
# Esperar hasta que la instancia esté RUNNABLE (máximo ~15 minutos)
for i in $(seq 1 30); do
  ESTADO=$(gcloud sql instances describe $SQL_INSTANCE --format="value(state)" 2>/dev/null)
  [ "$ESTADO" = "RUNNABLE" ] && echo "Instancia $SQL_INSTANCE lista (RUNNABLE)" && break
  echo "Intento $i: estado actual '${ESTADO:-PENDING_CREATE}', reintentando en 30 s..."; sleep 30
done

gcloud sql instances list
```

#### 3.1. Crear una Base de Datos Relacional (`db_ecommerce`) dentro de la Instancia
Una instancia de Cloud SQL puede alojar múltiples bases de datos lógicas. Creemos la base de datos `db_ecommerce`:

```bash
gcloud sql databases create db_ecommerce --instance=$SQL_INSTANCE

# Listar las bases de datos dentro de nuestra instancia PostgreSQL
gcloud sql databases list --instance=$SQL_INSTANCE
```

#### 3.2. Conectarse a Cloud SQL y Ejecutar Operaciones Transaccionales SQL
Utilizaremos `gcloud sql connect`, el cual autoriza temporalmente la dirección IP de tu Cloud Shell y abre el cliente interactivo `psql` conectado a `db_ecommerce`.

Podemos enviarle un script SQL completo de creación de tablas, inserción de inventario y consulta analítica directamente desde Cloud Shell:

```bash
cat << 'EOF' > inicializar_inventario.sql
-- 1. Crear tabla relacional con restricciones de integridad (Constraints)
CREATE TABLE IF NOT EXISTS productos (
    id_producto SERIAL PRIMARY KEY,
    sku VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    precio_usd NUMERIC(10, 2) CHECK (precio_usd >= 0),
    stock INT NOT NULL DEFAULT 0,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Insertar registros transaccionales
INSERT INTO productos (sku, nombre, categoria, precio_usd, stock) VALUES
    ('LAP-PRO-16', 'Laptop Workstation 16GB', 'Computo', 1299.99, 15),
    ('MON-4K-27', 'Monitor IPS 4K 27 Pulgadas', 'Perifericos', 349.50, 40),
    ('TEC-MEC-RGB', 'Teclado Mecanico Inalambrico', 'Perifericos', 89.90, 120),
    ('SRV-RACK-2U', 'Servidor Edge Cloud', 'Infraestructura', 2450.00, 5)
ON CONFLICT (sku) DO NOTHING;

-- 3. Consultar todos los productos ordenados por precio
SELECT id_producto, sku, nombre, categoria, precio_usd, stock FROM productos ORDER BY precio_usd DESC;

-- 4. Consulta analítica: Valor total del inventario por categoría
SELECT 
    categoria,
    COUNT(*) AS total_productos,
    SUM(stock) AS unidades_totales,
    SUM(precio_usd * stock) AS valor_inventario_usd
FROM productos
GROUP BY categoria
ORDER BY valor_inventario_usd DESC;
EOF
```

Ahora conéctate y ejecuta el script SQL (cuando `psql` te pida **`Password for user postgres:`**, escribe o pega **`PasswordSeguraLab07!`** y presiona **Enter**):

```bash
gcloud sql connect $SQL_INSTANCE \
  --user=postgres \
  --database=db_ecommerce < inicializar_inventario.sql
```

¡Observa la tabla de resultados devuelta por PostgreSQL 16 corriendo en Cloud SQL!
También puedes explorar tu instancia visualmente en la **Consola Web**: ve a `☰` -> **SQL** -> haz clic en **`sql-tienda-lab07`**, donde verás gráficas en tiempo real de CPU, memoria, conexiones activas y el **Cloud SQL Studio**.

---

### Paso 4: Base de Datos NoSQL Documental con Cloud Firestore (20 min)

Ahora complementaremos nuestra arquitectura relacional con una base de datos **NoSQL Documental Serverless**: **Cloud Firestore**. Mientras que en Cloud SQL guardamos el catálogo estructurado de productos, en Firestore guardaremos **carritos de compra y pedidos en tiempo real** con estructuras JSON anidadas y flexibles.

#### 4.1. Crear la Base de Datos Firestore en Modo Nativo
Un proyecto solo puede tener una base de datos llamada `(default)`. Si ya la creaste antes (por ejemplo, en un intento anterior de este laboratorio o desde Firebase), la reutilizamos en lugar de fallar:

```bash
if gcloud firestore databases describe --database="(default)" > /dev/null 2>&1; then
  echo "La base de datos (default) ya existe; la reutilizaremos:"
  gcloud firestore databases describe --database="(default)" --format="table(name, locationId, type)"
else
  gcloud firestore databases create \
    --database="(default)" \
    --location=$REGION \
    --type=firestore-native
fi
```

> [!NOTE]
> Si la base de datos existente está en **modo Datastore** (`DATASTORE_MODE`), el script de Python del siguiente paso fallará. En ese caso usa un proyecto nuevo o crea una base de datos con nombre, por ejemplo `--database=lab07-nativa`, y pásala al cliente con `firestore.Client(database="lab07-nativa")`.

#### 4.2. Insertar y Consultar Documentos JSON Anidados usando Python desde Cloud Shell
Crearemos un script en Python (`app_firestore.py`) que se conecta a Firestore usando tu identidad nativa de Cloud Shell (sin llaves ni contraseñas), inserta tres documentos con estructuras distintas (demostrando la flexibilidad *Schemaless* de NoSQL) y realiza una consulta filtrada:

```bash
# Instalar la librería cliente oficial de Cloud Firestore en un entorno virtual limpio
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet google-cloud-firestore

cat << 'EOF' > app_firestore.py
from datetime import datetime, timezone
from google.cloud import firestore

# Inicializar cliente Serverless de Firestore (detecta el proyecto automáticamente)
db = firestore.Client()
coleccion = db.collection("pedidos_tiempo_real")

print("1. Insertando documentos JSON con esquema flexible en Firestore...")

# Documento 1: Pedido con envío a domicilio y metadatos de geolocalización
coleccion.document("ORD-2026-001").set({
    "cliente": {"nombre": "Carlos Mendoza", "vip": True},
    "items": [
        {"sku": "LAP-PRO-16", "cantidad": 1, "precio_unitario": 1299.99},
        {"sku": "TEC-MEC-RGB", "cantidad": 2, "precio_unitario": 89.90}
    ],
    "total_usd": 1479.79,
    "estado": "PAGADO",
    "modalidad_entrega": "DOMICILIO_EXPRESS",
    "coordenadas_entrega": firestore.GeoPoint(4.6097, -74.0817),
    "actualizado_en": datetime.now(timezone.utc)
})

# Documento 2: Pedido de retiro en tienda (Observa que tiene campos distintos sin romper la base de datos)
coleccion.document("ORD-2026-002").set({
    "cliente": {"nombre": "Laura Gomez", "vip": False},
    "items": [
        {"sku": "MON-4K-27", "cantidad": 1, "precio_unitario": 349.50}
    ],
    "total_usd": 349.50,
    "estado": "PENDIENTE_PAGO",
    "modalidad_entrega": "RETIRO_EN_TIENDA",
    "sucursal_retiro": "Sede Norte",
    "notas_especiales": ["Empacar para regalo", "Llamar al llegar"],
    "actualizado_en": datetime.now(timezone.utc)
})

# Documento 3: Pedido corporativo grande
coleccion.document("ORD-2026-003").set({
    "cliente": {"nombre": "TechCorp S.A.", "vip": True, "nit": "900.123.456-7"},
    "items": [
        {"sku": "SRV-RACK-2U", "cantidad": 2, "precio_unitario": 2450.00}
    ],
    "total_usd": 4900.00,
    "estado": "PAGADO",
    "actualizado_en": datetime.now(timezone.utc)
})

print("\n2. Consultando en Firestore todos los pedidos con estado == 'PAGADO':")
print("-" * 65)
pedidos_pagados = coleccion.where(filter=firestore.FieldFilter("estado", "==", "PAGADO")).stream()

for doc in pedidos_pagados:
    datos = doc.to_dict()
    print(f"ID Documento: {doc.id} | Cliente: {datos['cliente']['nombre']} | Total: ${datos['total_usd']} USD | Items: {len(datos['items'])}")
EOF

python3 app_firestore.py
deactivate
```

#### 4.3. Exploración Visual en Tiempo Real en la Consola de Firestore
1. En la Consola Web de Google Cloud, ve al menú `☰` -> **Firestore** -> **Datos (Data)**.
2. Verás la colección **`pedidos_tiempo_real`** y dentro de ella los documentos `ORD-2026-001`, `ORD-2026-002` y `ORD-2026-003`.
3. Haz clic en cada documento para expandir sus mapas (`cliente`), arreglos (`items`) y coordenadas (`coordenadas_entrega`). Si editas cualquier valor directamente en la interfaz web, se actualiza en milisegundos.

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO OBLIGATORIO!** La instancia de **Cloud SQL** se cobra por cada hora que permanezca encendida. Como en el Paso 1 le activamos la protección contra borrado (`--deletion-protection`), primero desactivaremos esa bandera y luego eliminaremos la instancia junto con la base de datos Firestore y el Bucket de Cloud Storage.

Ejecuta los siguientes comandos en **Cloud Shell**:

```bash
# 0. Recuperar las variables del laboratorio (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab07 && source env.sh

# 1. Desactivar la protección contra borrado de la instancia de Cloud SQL y luego eliminarla
gcloud sql instances patch $SQL_INSTANCE --no-deletion-protection --quiet
gcloud sql instances delete $SQL_INSTANCE --quiet

# 2. Eliminar la base de datos de Cloud Firestore
gcloud firestore databases delete --database="(default)" --quiet

# 3. Eliminar el Bucket de Cloud Storage y todas las versiones de objetos dentro de él
gcloud storage rm --recursive $BUCKET_NAME
```

### Auditoría Final de Limpieza
Verifica que todos los servicios de almacenamiento y bases de datos hayan sido eliminados:

```bash
echo "=== Instancias Cloud SQL ==="
gcloud sql instances list

echo "=== Bases de Datos Firestore ==="
gcloud firestore databases list

echo "=== Buckets Cloud Storage ==="
gcloud storage buckets list
```

---

## 6. Conclusiones

En este séptimo laboratorio has construido una capa de persistencia políglota completa en Google Cloud Platform:
- En **Cloud Storage**, aprendiste a proteger tus archivos contra errores humanos habilitando **Object Versioning** (restaurando una generación anterior) y automatizaste el ahorro de costos mediante políticas de **Object Lifecycle Management**.
- En **Cloud SQL para PostgreSQL**, aprovisionaste una base de datos relacional administrada con protección contra borrado accidental, diseñaste tablas con restricciones de integridad y ejecutaste consultas analíticas SQL.
- En **Cloud Firestore**, experimentaste la agilidad y velocidad de una base de datos **NoSQL Documental Serverless**, almacenando documentos JSON jerárquicos con esquemas flexibles sin administrar servidores.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Generación de una URL Firmada Temporal (`Signed URL`) en Cloud Storage**:
   Investiga el comando `gcloud storage sign-url`. Descubre cómo generar un enlace temporal válido únicamente durante **10 minutos (`--duration=10m`)** para compartir un archivo privado de tu bucket con un cliente externo sin tener que hacer público el bucket.

2. **Reto 2 — Copia de Seguridad a Demanda (*On-Demand Backup*) en Cloud SQL**:
   Antes de realizar un cambio riesgoso en una tabla de producción de Cloud SQL, siempre se debe tomar un backup manual. Investiga cómo usar `gcloud sql backups create --instance=...` y `gcloud sql backups list` para crear y verificar un respaldo instantáneo de una instancia de Cloud SQL.

3. **Reto 3 — Subcolecciones y Transacciones en Cloud Firestore**:
   Modifica el script `app_firestore.py` para agregar una **Subcolección** llamada `historial_estados` dentro del documento `ORD-2026-001` (`coleccion.document("ORD-2026-001").collection("historial_estados").add(...)`) que registre cada cambio de estado del pedido (`CREADO` -> `PAGADO` -> `ENVIADO`) con su marca de tiempo.

---

## 8. Referencias Oficiales

- **Referencia CLI: `gcloud storage buckets` y Ciclo de Vida**: [https://docs.cloud.google.com/storage/docs/managing-lifecycles](https://docs.cloud.google.com/storage/docs/managing-lifecycles)
- **Versionado de Objetos en Cloud Storage**: [https://docs.cloud.google.com/storage/docs/object-versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- **Referencia CLI: `gcloud sql instances` y `databases`**: [https://docs.cloud.google.com/sdk/gcloud/reference/sql](https://docs.cloud.google.com/sdk/gcloud/reference/sql)
- **Guía Rápida de Cloud Firestore con Python**: [https://docs.cloud.google.com/firestore/native/docs/create-database-server-client-library](https://docs.cloud.google.com/firestore/native/docs/create-database-server-client-library)
