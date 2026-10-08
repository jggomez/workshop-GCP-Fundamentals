# Curso Práctico de Google Cloud Platform (GCP) — Playbooks y Laboratorios

Bienvenido al repositorio oficial del curso de **Google Cloud Platform (GCP)**. Este repositorio está diseñado como una guía teórico-práctica para estudiantes y profesionales que desean dominar la infraestructura, servicios y arquitecturas modernas en la nube de Google.

El curso consta de **16 sesiones**, combinando **Playbooks teóricos profundos (`teoria.md`)** y **Laboratorios prácticos paso a paso (`laboratorio.md`)** diseñados para completarse en un máximo de **90 minutos** utilizando **Google Cloud Shell** (sin necesidad de instalar herramientas en tu computadora local) y la **Consola Web de Google Cloud**.

---

## Estructura del Repositorio

```text
workshop-gcp/
├── README.md                                              # Guía general, mapa del curso y reglas de control de costos
├── 01-introduccion-exploracion-gcp/
│   ├── teoria.md                                          # Playbook 01: Ecosistema GCP, jerarquía, red global, IAM y servicios
│   └── laboratorio.md                                     # Lab 01: Recorrido por GCP, Cloud Shell, gcloud CLI, APIs y presupuestos
├── 02-identidad-seguridad-iam/
│   ├── teoria.md                                          # Playbook 02: Cloud IAM, Service Accounts, Impersonation, Custom Roles y Secret Manager
│   └── laboratorio.md                                     # Lab 02: Roles personalizados, cuentas de servicio sin llaves JSON y secretos
├── 03-redes-virtuales-vpc/
│   ├── teoria.md                                          # Playbook 03: Arquitectura VPC global, subredes, firewall, IPs públicas y Cloud NAT
│   └── laboratorio.md                                     # Lab 03: VPC custom multi-región, firewall zero-trust, IPs estáticas y Cloud NAT
├── 04-compute-engine-maquinas-virtuales/
│   ├── teoria.md                                          # Playbook 04: Compute Engine, familias de VMs, discos, snapshots y MIGs
│   └── laboratorio.md                                     # Lab 04: VMs, SSH/IAP, discos persistentes, snapshots y clúster autoescalable
├── 05-contenedores-serverless-cloud-run-functions/
│   ├── teoria.md                                          # Playbook 05: Contenedores, Artifact Registry, Cloud Build, Cloud Run y Cloud Functions
│   └── laboratorio.md                                     # Lab 05: Despliegue en Cloud Run, traffic splitting Canary y funciones por eventos
├── 06-orquestacion-contenedores-gke/
│   ├── teoria.md                                          # Playbook 06: Arquitectura Kubernetes, GKE Autopilot vs Standard, Pods, Deployments, Ingress
│   └── laboratorio.md                                     # Lab 06: Clúster GKE, Namespaces, ConfigMaps, Secrets, Services, Ingress y HPA
├── 07-almacenamiento-objetos-bases-datos/
│   ├── teoria.md                                          # Playbook 07: Cloud Storage, Cloud SQL, AlloyDB, Cloud Spanner, Firestore y Bigtable
│   └── laboratorio.md                                     # Lab 07: Cloud Storage (versionado/lifecycle), Cloud SQL (PostgreSQL) y Firestore NoSQL
├── 08-monitoreo-observabilidad-iac/
│   ├── teoria.md                                          # Playbook 08: Principios SRE, Cloud Logging, Cloud Monitoring y Terraform (IaC)
│   └── laboratorio.md                                     # Lab 08: Despliegue declarativo con Terraform, logs JSON, métricas, sinks y Uptime Checks
└── tools/
    └── validate_labs.py                                   # Validador automático de los comandos gcloud de todos los laboratorios
```

Cada carpeta de módulo contiene dos archivos fundamentales:

1. **`teoria.md` (Playbook Teórico)**: Un documento de referencia técnica profunda que explica la arquitectura interna, conceptos clave, diagramas de flujo en Mermaid, tablas comparativas, casos de uso reales, seguridad, costos (FinOps) y enlaces a la documentación oficial.
2. **`laboratorio.md` (Laboratorio Práctico)**: Una guía paso a paso (máximo 1.5 horas) centrada en el uso de la terminal interactiva **Google Cloud Shell (`gcloud`, `kubectl`, `terraform` CLI)** apoyada por verificaciones visuales en la **Consola de Google Cloud**. Incluye objetivos, estimación exacta de costos, resultados de aprendizaje, pasos guiados, limpieza total de recursos, conclusiones, retos adicionales y referencias.

---

## Mapa del Curso (Clases 01 a 08 Completadas + Siguientes Módulos)

A continuación se presenta la ruta oficial del curso con los **8 módulos iniciales listos para dictar**:

| Clase | Módulo / Tema | Enfoque Principal | Estado |
| :--- | :--- | :--- | :--- |
| **01** | **[Introducción y Exploración de GCP](./01-introduccion-exploracion-gcp/)** | Infraestructura global, proyectos, facturación, Cloud Shell, `gcloud` CLI y catálogo de servicios | ✅ Disponible ([Teoría](./01-introduccion-exploracion-gcp/teoria.md) \| [Lab](./01-introduccion-exploracion-gcp/laboratorio.md)) |
| **02** | **[Identidad, Seguridad e IAM](./02-identidad-seguridad-iam/)** | Usuarios, grupos, Service Accounts, roles personalizados, suplantación sin llaves y Secret Manager | ✅ Disponible ([Teoría](./02-identidad-seguridad-iam/teoria.md) \| [Lab](./02-identidad-seguridad-iam/laboratorio.md)) |
| **03** | **[Redes Virtuales en la Nube (VPC)](./03-redes-virtuales-vpc/)** | Arquitectura VPC global, subredes regionales, reglas de Firewall, IPs públicas estáticas y Cloud NAT | ✅ Disponible ([Teoría](./03-redes-virtuales-vpc/teoria.md) \| [Lab](./03-redes-virtuales-vpc/laboratorio.md)) |
| **04** | **[Compute Engine y Máquinas Virtuales](./04-compute-engine-maquinas-virtuales/)** | Creación de VMs, SSH/IAP, Persistent Disks, Snapshots, Instance Templates y Autoescalamiento (MIG) | ✅ Disponible ([Teoría](./04-compute-engine-maquinas-virtuales/teoria.md) \| [Lab](./04-compute-engine-maquinas-virtuales/laboratorio.md)) |
| **05** | **[Contenedores y Cómputo Serverless](./05-contenedores-serverless-cloud-run-functions/)** | Artifact Registry, Cloud Build, Cloud Run (revisiones y Canary) y Cloud Functions (2nd Gen + Eventos) | ✅ Disponible ([Teoría](./05-contenedores-serverless-cloud-run-functions/teoria.md) \| [Lab](./05-contenedores-serverless-cloud-run-functions/laboratorio.md)) |
| **06** | **[Orquestación de Contenedores con GKE](./06-orquestacion-contenedores-gke/)** | Arquitectura Kubernetes, GKE Autopilot vs Standard, Pods, Deployments, Services, Secrets, Ingress y HPA | ✅ Disponible ([Teoría](./06-orquestacion-contenedores-gke/teoria.md) \| [Lab](./06-orquestacion-contenedores-gke/laboratorio.md)) |
| **07** | **[Almacenamiento de Objetos y Bases de Datos](./07-almacenamiento-objetos-bases-datos/)** | Cloud Storage (clases, versionado, lifecycle), Cloud SQL (PostgreSQL) y Cloud Firestore (NoSQL) | ✅ Disponible ([Teoría](./07-almacenamiento-objetos-bases-datos/teoria.md) \| [Lab](./07-almacenamiento-objetos-bases-datos/laboratorio.md)) |
| **08** | **[Monitoreo, Observabilidad e IaC](./08-monitoreo-observabilidad-iac/)** | Principios de observabilidad (SRE), Cloud Logging, Cloud Monitoring, Uptime Checks y Terraform (IaC) | ✅ Disponible ([Teoría](./08-monitoreo-observabilidad-iac/teoria.md) \| [Lab](./08-monitoreo-observabilidad-iac/laboratorio.md)) |
| **09–16** | **Módulos Avanzados y Especialización** | Balanceo Global/Cloud Armor, Mensajería (Pub/Sub), Analítica (BigQuery), Pipelines de Datos, IA Generativa (Vertex AI) y Proyecto Final | Próximamente |

---

## Requisitos Previos para el Estudiante

Para realizar los laboratorios de este repositorio **no necesitas instalar ningún software en tu computadora**. Todo se ejecuta desde el navegador web:

1. **Navegador Web Moderno**: Google Chrome, Firefox, Edge o Safari actualizado.
2. **Cuenta de Google Cloud Platform**:
   - Puedes utilizar los **$300 USD de crédito gratuito (Free Trial por 90 días)** para cuentas nuevas en [cloud.google.com/free](https://cloud.google.com/free).
   - O bien, un cupón educativo / proyecto asignado por el instructor.
3. **Google Cloud Shell**: Entorno Linux preconfigurado gratuito incluido dentro de la consola de GCP que ya trae instalado `gcloud` (incluidos los componentes `alpha` y `beta`), `bq`, `kubectl`, `git`, `docker`, `terraform` y un editor de código basado en VS Code. Los laboratorios usan `gcloud storage` (la herramienta actual para Cloud Storage) en lugar del antiguo `gsutil`.

> [!IMPORTANT]
> **Cuentas universitarias o corporativas**: si tu proyecto pertenece a una Organización creada desde mayo de 2024, hereda políticas *secure by default* (por ejemplo, la cuenta de servicio predeterminada de Compute Engine **no** recibe el rol `Editor`). Los laboratorios ya otorgan explícitamente los permisos necesarios, pero si ves un error `403 PERMISSION_DENIED` revisa la nota de permisos del laboratorio correspondiente o consulta con tu instructor.

---

## Cómo Trabajar con los Laboratorios en Cloud Shell

Cloud Shell tiene límites que afectan directamente a los laboratorios (según su [documentación oficial](https://docs.cloud.google.com/shell/docs/limitations)):

| Límite de Cloud Shell | Cómo lo manejan los laboratorios |
| :--- | :--- |
| La sesión termina tras **40 minutos de inactividad** y se pierden las variables de entorno | Cada laboratorio guarda sus variables en `~/workshop-gcp/labNN/env.sh`. Si te desconectas, ejecuta `cd ~/workshop-gcp/labNN && source env.sh` y continúa. La limpieza final siempre empieza recargando ese archivo. |
| Las preferencias de `gcloud` (perfiles, región, zona) **solo viven en la pestaña y sesión actuales** | Cada laboratorio vuelve a configurar proyecto, región y zona en su Paso 1. |
| Cuota de **50 horas semanales** | Cierra Cloud Shell cuando no lo uses. |
| Los cambios de IAM tardan normalmente **~2 minutos (hasta 7 o más)** en propagarse | Los pasos que dependen de un permiso recién otorgado reintentan automáticamente en lugar de esperar un tiempo fijo. |

Cada laboratorio comienza además con una **verificación previa** que comprueba que haya un proyecto activo (y, cuando corresponde, que exista la red `default`).

---

## Reglas de Oro para el Control de Costos (FinOps)

En la nube se paga por lo que se aprovisiona y permanece encendido. Sigue siempre estas tres reglas en cada sesión:

1. **Configura una Alerta de Presupuesto desde el Día 1**: En el **Laboratorio 01** aprenderás a configurar alertas para recibir un correo automático si tu consumo supera umbrales pequeños (por ejemplo, $1, $5 o $10 USD).
2. **Ejecuta SIEMPRE la sección de "Limpieza de Recursos (Cleanup)"**: Al final de cada archivo `laboratorio.md` encontrarás una sección dedicada con los comandos exactos de `gcloud`, `kubectl` o `terraform destroy` para eliminar todas las máquinas, clústeres, bases de datos, discos, snapshots e IPs creadas durante la práctica.
3. **Verifica que tu proyecto quede limpio**: Antes de cerrar tu sesión de Cloud Shell, ejecuta los comandos de auditoría indicados al final del laboratorio para confirmar que no queden recursos huérfanos generando costos.

> [!CAUTION]
> Un presupuesto de Cloud Billing **solo envía alertas: no detiene el gasto**. La única forma segura de no pagar por recursos olvidados es ejecutar la limpieza de cada laboratorio.

---

## Mantenimiento: Validación Automática de los Comandos

Los comandos de Google Cloud cambian con frecuencia (flags que desaparecen, valores por defecto nuevos, servicios renombrados). Para detectar estos cambios antes de dictar una clase, el repositorio incluye un validador que **no crea ni modifica ningún recurso**:

```bash
# Requiere gcloud CLI (con componentes alpha y beta) y Python 3
python3 tools/validate_labs.py            # validación completa (~5 minutos)
python3 tools/validate_labs.py --no-run   # solo sintaxis bash y flags documentados, sin llamar a la API
```

El validador:
1. Revisa la sintaxis bash de todos los bloques de código (`bash -n`).
2. Extrae cada comando `gcloud` de los laboratorios y comprueba que el comando exista y que sus flags estén documentados en `gcloud ... --help`.
3. Ejecuta cada comando contra un **proyecto inexistente**: gcloud valida los argumentos localmente y la API responde 403/404, así que solo se reportan errores de sintaxis o de valores (por ejemplo, `unrecognized arguments`).

**Recomendación**: ejecuta el validador después de actualizar gcloud (`gcloud components update`) y, al menos una vez por trimestre, realiza una corrida completa real de cada laboratorio en un proyecto de prueba, ya que el validador no puede comprobar el comportamiento de los servicios en ejecución (tiempos de propagación, autoescalado, precios).

**Última revisión completa contra la documentación oficial**: octubre de 2026 (gcloud CLI 563, proveedor de Terraform `hashicorp/google` 8.x). La documentación técnica de Google Cloud se encuentra ahora en `docs.cloud.google.com`.
