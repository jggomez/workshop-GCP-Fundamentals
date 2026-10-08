# Laboratorio 06: Orquestación de Contenedores con Google Kubernetes Engine (GKE) — Pods, Deployments, ConfigMaps, Secrets, Services, Ingress y HPA

- **Duración estimada**: 90 minutos (1 hora y 30 minutos)
- **Nivel**: Intermedio–Avanzado / Orquestación de Contenedores
- **Entorno de trabajo**: **Google Cloud Shell (`gcloud` + `kubectl` CLI)** + Verificaciones visuales en **Google Cloud Console**

---

## 1. Objetivo del Laboratorio

Aprovisionar y operar un clúster de **Google Kubernetes Engine (GKE)** desde **Google Cloud Shell** para desplegar una arquitectura completa de microservicios utilizando manifiestos declarativos YAML. Durante el laboratorio crearás **Namespaces**, **Pods**, **ConfigMaps**, **Secrets**, **Deployments** con múltiples réplicas, comprobarás la **Autoreparación (*Self-Healing*)** en tiempo real, expondrás los servicios a Internet mediante **Services (`LoadBalancer` y `NodePort`)** y un enrutador **Ingress de Capa 7**, y configurarás un **Horizontal Pod Autoscaler (HPA)**.

---

## 2. ¿Qué aprenderá el estudiante?

Al finalizar este laboratorio, serás capaz de:
1. Crear un clúster de Kubernetes en **GKE** mediante `gcloud container clusters create` (conociendo también el comando para **GKE Autopilot**) y conectar `kubectl` automáticamente.
2. Organizar recursos dentro del clúster utilizando **Namespaces** y lanzar **Pods** para inspeccionar su ciclo de vida y logs.
3. Desacoplar variables de configuración y credenciales sensibles creando **ConfigMaps** y **Secrets** e inyectándolos dentro de un **Deployment**.
4. Desplegar aplicaciones altamente disponibles con **Deployments**, probar la **Autoreparación (*Self-Healing*)** eliminando Pods en vivo y ejecutar **Actualizaciones sin Caída (*Rolling Updates*)**.
5. Exponer cargas de trabajo usando **Services** (`ClusterIP`, `NodePort` y `LoadBalancer`) y configurar un **Ingress** en GKE que enrute múltiples rutas URL (`/frontend` y `/api`) a través de un Balanceador de Carga de Google Cloud.
6. Configurar el autoescalamiento horizontal de Pods con **Horizontal Pod Autoscaler (HPA)**.

---

## 3. Estimación de Costos en la Nube

> [!IMPORTANT]
> **Costo total estimado por ejecutar este laboratorio durante 90 minutos: ~$0.08 a $0.14 USD** (El primer clúster Zonal de un proyecto no paga la tarifa de administración de GKE gracias al *GKE Cluster Management Free Tier*; solo pagas los 2 nodos `e2-medium` y el balanceador durante 1 hora).

| Recurso Aprovisionado | Especificación y Cantidad | Precio de Referencia en `us-central1` | Costo por 1.5 Horas de Laboratorio |
| :--- | :--- | :--- | :--- |
| **Control Plane del Clúster GKE Zonal** | 1 clúster zonal | **Gratuito** para el primer clúster zonal (descuento de $74.40/mes automático) | **$0.000 USD** |
| **Nodos de Trabajo (`Worker Nodes`)** | 2x instancias `e2-medium` (2 vCPUs, 4 GB RAM, disco 20 GB) | ~$0.0335 / hora por nodo | **~$0.100 USD** |
| **Balanceador de Carga (Service / Ingress)** | 1 regla de reenvío durante ~40 minutos | ~$0.025 / hora | **~$0.018 USD** |
| **TOTAL ESTIMADO DE LA SESIÓN** | **Ejecutando la limpieza al finalizar el laboratorio** | — | **~$0.118 USD** |

---

## 4. Paso a Paso del Laboratorio

### Paso 1: Preparación del Entorno y Creación del Clúster GKE (15 min)

1. Abre la Consola de Google Cloud ([https://console.cloud.google.com](https://console.cloud.google.com)) y activa **Google Cloud Shell** (`>_`).
2. Configura las variables de entorno y habilita la API de Kubernetes Engine (`container.googleapis.com`):

```bash
mkdir -p ~/workshop-gcp/lab06
cd ~/workshop-gcp/lab06

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
export CLUSTER_NAME="cluster-gke-lab06"
EOF
source env.sh

gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE

# Habilitar la API de Google Kubernetes Engine
gcloud services enable container.googleapis.com compute.googleapis.com
```

> [!IMPORTANT]
> Si Cloud Shell se desconecta (40 minutos de inactividad), recupera tus variables y la conexión al clúster con:
> ```bash
> cd ~/workshop-gcp/lab06 && source env.sh
> gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE
> kubectl config set-context --current --namespace=ns-tienda
> ```

#### 1.1. Crear el Clúster de GKE
> [!NOTE]
> **¿Standard Zonal vs Autopilot en un Laboratorio de 90 minutos?**
> - En producción se suele crear un clúster **GKE Autopilot Regional** con el comando:
>   `gcloud container clusters create-auto nombre-cluster --region=us-central1`
> - Sin embargo, en un laboratorio en vivo de 90 minutos utilizaremos un clúster **GKE Standard Zonal de 2 nodos `e2-medium`** porque arranca en solo **~3 minutos** y tus Pods pasan a estado `Running` en **2 segundos** (ya que los nodos ya están encendidos).

Ejecuta el siguiente comando en Cloud Shell para crear el clúster (tarda aproximadamente **3 a 4 minutos**):

```bash
gcloud container clusters create $CLUSTER_NAME \
  --zone=$ZONE \
  --num-nodes=2 \
  --machine-type=e2-medium \
  --disk-size=20GB \
  --disk-type=pd-balanced
```

#### 1.2. Conectar `kubectl` al Clúster y Explorar los Nodos
Cuando termina `clusters create`, `gcloud` configura automáticamente tu archivo `~/.kube/config`. Si alguna vez necesitas reconectarte desde otra sesión, el comando es:

```bash
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

# 1. Verificar que kubectl se comunique con el Control Plane y listar los 2 Worker Nodes
kubectl get nodes -o wide

# 2. Listar los Namespaces que vienen precreados en el clúster
kubectl get namespaces
```

Observa en `kubectl get nodes -o wide` cómo tus 2 nodos corren el sistema operativo optimizado de Google (**Container-Optimized OS**) con `containerd`.

---

### Paso 2: Namespaces y Ciclo de Vida de un Pod (10 min)

En lugar de mezclar nuestros objetos en el namespace `default`, crearemos un **Namespace** dedicado para nuestra aplicación llamado `ns-tienda` y lo estableceremos como nuestro namespace activo por defecto:

```bash
# 1. Crear el Namespace 'ns-tienda'
kubectl create namespace ns-tienda

# 2. Configurar kubectl para que todos los siguientes comandos apunten por defecto a 'ns-tienda'
kubectl config set-context --current --namespace=ns-tienda
```

#### 2.1. Crear nuestro primer Pod individual mediante un Manifiesto YAML
```bash
cat << 'EOF' > pod-explorador.yaml
apiVersion: v1
kind: Pod
metadata:
  name: pod-nginx-prueba
  labels:
    rol: prueba-unitaria
spec:
  containers:
  - name: contenedor-nginx
    image: nginx:1.27-alpine
    ports:
    - containerPort: 80
EOF

# Aplicar el manifiesto en Kubernetes
kubectl apply -f pod-explorador.yaml

# Ver el estado del Pod y su dirección IP interna dentro del clúster
kubectl get pods -o wide
```

Inspeccionemos qué hizo Kubernetes por debajo (`Events`) y ejecutemos un comando dentro del contenedor:

```bash
# Ver los eventos del Pod (Scheduled -> Pulled -> Created -> Started)
kubectl describe pod pod-nginx-prueba | tail -n 15

# Ejecutar un comando dentro del Pod en vivo
kubectl exec pod-nginx-prueba -- nginx -v

# Eliminar el Pod individual (comprobando que un Pod suelto no se recrea si lo borras)
kubectl delete pod pod-nginx-prueba
```

---

### Paso 3: Creación de ConfigMaps y Secrets (10 min)

Antes de desplegar nuestra aplicación real con alta disponibilidad, crearemos un **ConfigMap** (para variables de configuración públicas) y un **Secret** (para credenciales sensibles) que luego inyectaremos en nuestros Pods:

```bash
cat << 'EOF' > config-y-secretos.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cm-config-tienda
data:
  NOMBRE_TIENDA: "CloudStore Latam - GKE Edition"
  MODO_OPERACION: "Produccion-Alta-Disponibilidad"
---
apiVersion: v1
kind: Secret
metadata:
  name: secret-credenciales-db
type: Opaque
stringData:
  DB_HOST: "10.20.1.50"
  DB_TOKEN_SECRETO: "gke_token_super_confidencial_998877"
EOF

kubectl apply -f config-y-secretos.yaml

# Verificar que el ConfigMap y el Secret existan en nuestro namespace 'ns-tienda'
kubectl get configmaps
kubectl get secrets
```

---

### Paso 4: Despliegue de Alta Disponibilidad con `Deployment` y Prueba de Autoreparación (20 min)

Ahora crearemos un **Deployment** llamado `deploy-frontend` con **3 réplicas**. Cada Pod del Deployment leerá las variables del `ConfigMap` y del `Secret` y mostrará también su propio nombre de Pod (`HOSTNAME`) para que podamos distinguir qué Pod atiende cada petición:

#### 4.1. Crear y aplicar el Manifiesto del Deployment (`deployment-frontend.yaml`)
```bash
cat << 'EOF' > deployment-frontend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deploy-frontend
  labels:
    app: tienda-frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: tienda-frontend
  template:
    metadata:
      labels:
        app: tienda-frontend
    spec:
      containers:
      - name: web-server
        image: python:3.12-alpine
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: cm-config-tienda
        env:
        - name: TOKEN_DB
          valueFrom:
            secretKeyRef:
              name: secret-credenciales-db
              key: DB_TOKEN_SECRETO
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "250m"
            memory: "256Mi"
        command: ["/bin/sh", "-c"]
        args:
        - |
          cat << 'PYEOF' > server.py
          import os, socket
          from http.server import BaseHTTPRequestHandler, HTTPServer

          class Handler(BaseHTTPRequestHandler):
              def do_GET(self):
                  self.send_response(200)
                  self.send_header("Content-type", "application/json; charset=utf-8")
                  self.end_headers()
                  token = os.environ.get("TOKEN_DB", "")
                  token_masked = token[:10] + "***" if token else "no-token"
                  body = (
                      f'{{"tienda": "{os.environ.get("NOMBRE_TIENDA")}", '
                      f'"modo": "{os.environ.get("MODO_OPERACION")}", '
                      f'"pod_que_respondio": "{socket.gethostname()}", '
                      f'"secret_inyectado": "{token_masked}"}}\n'
                  )
                  self.wfile.write(body.encode("utf-8"))

          HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
          PYEOF
          python3 server.py
EOF

kubectl apply -f deployment-frontend.yaml
```

#### 4.2. Verificar los 3 Pods en Ejecución
```bash
kubectl rollout status deployment/deploy-frontend
kubectl get deployments
kubectl get pods -o wide
```

Observa cómo Kubernetes distribuyó automáticamente tus 3 Pods entre los 2 nodos de trabajo del clúster.

#### 4.3. ¡Demostración de Autoreparación (*Self-Healing*) en Tiempo Real!
¿Qué sucede si uno de los 3 Pods sufre un fallo fatal o alguien lo elimina por accidente? Probémoslo en vivo:

```bash
# 1. Capturar el nombre del primer Pod de la lista
POD_VICTIMA=$(kubectl get pods -l app=tienda-frontend -o jsonpath="{.items[0].metadata.name}")
echo "Simulando caída abrupta del Pod: $POD_VICTIMA"

# 2. Eliminar el Pod e inmediatamente listar los Pods del Deployment
kubectl delete pod $POD_VICTIMA --wait=false
kubectl get pods -l app=tienda-frontend
```

¡Observa la salida! Mientras el Pod viejo aparece como `Terminating`, el controlador del Deployment **ya creó instantáneamente un Pod nuevo** (`ContainerCreating` -> `Running`) para mantener siempre el estado deseado de **`3/3` réplicas vivas**.

---

### Paso 5: Exposición con `Services` (`LoadBalancer`) e `Ingress` de Capa 7 (20 min)

Nuestros 3 Pods están corriendo dentro de la red privada del clúster, pero aún no son accesibles desde el exterior.

#### 5.1. Exponer el Deployment con un Service tipo `LoadBalancer`
Crearemos un manifiesto `service-frontend.yaml` que selecciona todos los Pods con la etiqueta `app: tienda-frontend` y le pide a Google Cloud un Balanceador de Carga externo en el puerto `80`:

```bash
cat << 'EOF' > service-frontend.yaml
apiVersion: v1
kind: Service
metadata:
  name: svc-tienda-loadbalancer
spec:
  type: LoadBalancer
  selector:
    app: tienda-frontend
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
EOF

kubectl apply -f service-frontend.yaml
```

Espera unos **45 a 60 segundos** hasta que la columna **`EXTERNAL-IP`** deje de decir `<pending>` y muestre una dirección IP pública real:

```bash
kubectl get service svc-tienda-loadbalancer
```

Cuando ya aparezca la `EXTERNAL-IP`, guárdala en una variable y haz **6 peticiones seguidas con `curl`** para observar cómo el Service balancea la carga entre los **3 Pods distintos**:

```bash
export LB_IP=$(kubectl get service svc-tienda-loadbalancer -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
echo "IP Pública del Balanceador GKE: $LB_IP"

for i in {1..6}; do
  curl -s http://$LB_IP
done
```

¡Fíjate en el campo `"pod_que_respondio"` de cada línea! Verás cómo responden diferentes Pods (`deploy-frontend-...`) y cómo todos leyeron correctamente el `ConfigMap` y el `Secret` enmascarado (`gke_token_***`).

#### 5.2. Crear un Segundo Microservicio (`svc-catalogo`) y Unificarlos con un `Ingress`
En una arquitectura real con múltiples microservicios, exponemos los servicios internamente (`NodePort` o `ClusterIP` con *NEG*) y colocamos delante un objeto **`Ingress`** que enruta por ruta URL (`/api/catalogo` vs `/`):

```bash
cat << 'EOF' > microservicio-catalogo-e-ingress.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deploy-catalogo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api-catalogo
  template:
    metadata:
      labels:
        app: api-catalogo
    spec:
      containers:
      - name: catalogo
        image: hashicorp/http-echo:1.0
        args:
        - "-listen=:5678"
        - "-text={\"microservicio\": \"API de Catalogo en GKE\", \"items\": [\"Laptop Pro\", \"Monitor 4K\"]}"
        ports:
        - containerPort: 5678
---
apiVersion: v1
kind: Service
metadata:
  name: svc-catalogo-interno
spec:
  type: NodePort
  selector:
    app: api-catalogo
  ports:
  - port: 80
    targetPort: 5678
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ingress-unificado-tienda
spec:
  rules:
  - http:
      paths:
      - path: /catalogo
        pathType: Prefix
        backend:
          service:
            name: svc-catalogo-interno
            port:
              number: 80
      - path: /
        pathType: Prefix
        backend:
          service:
            name: svc-tienda-loadbalancer
            port:
              number: 80
EOF

kubectl apply -f microservicio-catalogo-e-ingress.yaml

# Inspeccionar el objeto Ingress creado
kubectl get ingress ingress-unificado-tienda
```

> [!TIP]
> **Verificación en la Consola Web**:
> Ve a `☰` -> **Kubernetes Engine** -> **Puertas de enlace, servicios e Ingress (Gateways, Services & Ingress)**.
> En la pestaña **Servicios (Services)** verás tu `svc-tienda-loadbalancer` con su IP pública activa, y en la pestaña **Ingress** verás cómo GKE aprovisiona un Balanceador de Carga de Aplicaciones global con reglas de ruta para `/catalogo` y `/`. *(Nota: Un Ingress global de Capa 7 en GCP suele tardar entre 4 y 6 minutos en propagar su IP Anycast y sus Health Checks en todos los puntos de presencia del mundo).*

---

### Paso 6: Autoescalamiento de Pods (HPA) y Actualización Progresiva (*Rolling Update*) (15 min)

#### 6.1. Configurar un Horizontal Pod Autoscaler (HPA)
Configuremos un **HPA** sobre `deploy-frontend` para que escale automáticamente entre un mínimo de **2 Pods** y un máximo de **6 Pods** si el uso promedio de CPU supera el **50%** de lo solicitado en `requests.cpu`. Lo definimos de forma declarativa con la API estable `autoscaling/v2`, que funciona igual en cualquier versión actual de `kubectl` y de GKE:

```bash
cat << 'EOF' > hpa-frontend.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: deploy-frontend
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: deploy-frontend
  minReplicas: 2
  maxReplicas: 6
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
EOF

kubectl apply -f hpa-frontend.yaml

# Verificar el estado del HPA (la columna TARGETS puede mostrar <unknown> durante el primer minuto)
kubectl get hpa
```

> [!NOTE]
> El equivalente imperativo en las versiones actuales de `kubectl` es `kubectl autoscale deployment deploy-frontend --cpu=50% --min=2 --max=6`. La bandera antigua `--cpu-percent` ya no aparece en la referencia oficial de `kubectl autoscale`, por eso preferimos el manifiesto YAML.
>
> Como el HPA tiene `minReplicas: 2` y no hay carga, en unos 5 minutos reducirá el Deployment de 3 a 2 Pods. Es el comportamiento esperado.

#### 6.2. Actualizar la Configuración en Caliente sin Caída del Servicio (*Rolling Update*)
Si cambiamos el nombre de la tienda en el `ConfigMap` y reiniciamos progresivamente el Deployment (`rollout restart`), Kubernetes actualizará los Pods de uno en uno sin perder ni una sola petición:

```bash
# Actualizar el ConfigMap a una Versión 2.0
kubectl create configmap cm-config-tienda \
  --from-literal=NOMBRE_TIENDA="CloudStore Latam v2.0 - Actualizado sin Downtime" \
  --from-literal=MODO_OPERACION="Rolling-Update-Exitoso" \
  -o yaml --dry-run=client | kubectl apply -f -

# Disparar el reemplazo progresivo (Rolling Restart) de los Pods y esperar a que termine
kubectl rollout restart deployment/deploy-frontend
kubectl rollout status deployment/deploy-frontend

# Comprobar que el Balanceador de Carga ya devuelve la versión 2.0
curl -s http://$LB_IP
```

---

## 5. Limpieza de Recursos en Google Cloud (Cleanup)

> [!CAUTION]
> **¡PASO MUY IMPORTANTE!** Antes de eliminar un clúster de GKE, es una buena práctica **eliminar primero los objetos `Ingress` y `Service` tipo `LoadBalancer`** para que Kubernetes destruya limpiamente los Balanceadores de Carga externos y las reglas de firewall en tu proyecto de GCP, y a continuación eliminar el clúster completo.

Ejecuta los siguientes comandos en **Cloud Shell**:

```bash
# 0. Recuperar las variables y la conexión al clúster (por si la sesión de Cloud Shell se reinició)
cd ~/workshop-gcp/lab06 && source env.sh
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

# 1. Eliminar primero el Ingress y los Services para liberar los Load Balancers de GCP
kubectl delete ingress ingress-unificado-tienda --namespace=ns-tienda --ignore-not-found
kubectl delete service svc-tienda-loadbalancer svc-catalogo-interno --namespace=ns-tienda --ignore-not-found

# 2. Esperar a que GKE borre de verdad las reglas de reenvío de los balanceadores (puede tardar varios minutos).
#    Si borras el clúster antes, los recursos del balanceador pueden quedar huérfanos y seguir cobrando.
for i in $(seq 1 40); do
  PENDIENTES=$(gcloud compute forwarding-rules list --format="value(name)" | wc -l)
  [ "$PENDIENTES" -eq 0 ] && echo "Balanceadores liberados." && break
  echo "Intento $i: quedan $PENDIENTES reglas de reenvío, esperando 15 s..."; sleep 15
done

# 3. Eliminar el Clúster completo de GKE (destruye todos los Worker Nodes y discos asociados)
gcloud container clusters delete $CLUSTER_NAME \
  --zone=$ZONE \
  --quiet

# 4. Eliminar los Network Endpoint Groups (NEGs) que GKE pudo dejar huérfanos al borrar el Ingress
gcloud compute network-endpoint-groups list --filter="name~^k8s" --format="value(name,zone.basename())" \
  | while read NEG NEG_ZONE; do
      gcloud compute network-endpoint-groups delete $NEG --zone=$NEG_ZONE --quiet
    done
```

> [!NOTE]
> El bucle del paso 2 espera a que **no quede ninguna** regla de reenvío en el proyecto. Si tu proyecto tiene otros balanceadores ajenos a este laboratorio, el bucle se detendrá tras unos 10 minutos; en ese caso verifica manualmente con `gcloud compute forwarding-rules list` que ya no aparezcan reglas con prefijo `k8s2-` o con la descripción `ns-tienda/svc-tienda-loadbalancer`.

### Auditoría Final de Limpieza
Verifica que no queden clústeres de GKE, instancias de VM ni reglas de balanceo activas:

```bash
echo "=== Clústeres GKE ==="
gcloud container clusters list

echo "=== Instancias de VM en Compute Engine ==="
gcloud compute instances list

echo "=== Reglas de Reenvío de Balanceadores de Carga ==="
gcloud compute forwarding-rules list

echo "=== Network Endpoint Groups de GKE (no debe quedar ninguno k8s*) ==="
gcloud compute network-endpoint-groups list --filter="name~^k8s"
```

---

## 6. Conclusiones

En este sexto laboratorio has dominado la orquestación de contenedores con **Google Kubernetes Engine (GKE)**:
- Comprendiste la separación entre el **Control Plane** (administrado por Google) y los **Worker Nodes** donde corren tus Pods.
- Aplicaste las mejores prácticas de arquitectura en Kubernetes: aislaste tus cargas en un **Namespace (`ns-tienda`)**, inyectaste configuración y secretos externos mediante **ConfigMaps** y **Secrets**, y definiste límites de recursos (`requests` y `limits`).
- Comprobaste en vivo el poder declarativo de un **Deployment**: cómo repara instantáneamente Pods caídos (*Self-Healing*) y cómo actualiza versiones en caliente (*Rolling Update*) sin interrumpir el tráfico.
- Expusiste tus microservicios usando **Services (`LoadBalancer` y `NodePort`)** e **Ingress de Capa 7**, y configuraste el autoescalamiento elástico con **Horizontal Pod Autoscaler (HPA)**.

---

## 7. Retos Prácticos (Challenges)

1. **Reto 1 — Despliegue en un Clúster GKE Autopilot**:
   Investiga el comando `gcloud container clusters create-auto`. Explica qué diferencias observas al ejecutar `kubectl get nodes` en un clúster **Autopilot** recién creado cuando todavía no has desplegado ningún Pod propio frente a cuando despliegas un Deployment con 3 réplicas.

2. **Reto 2 — Sondas de Salud (`Liveness Probe` y `Readiness Probe`)**:
   Investiga cómo agregar un bloque `readinessProbe` y `livenessProbe` HTTP (`httpGet: path: / port: 8080`) dentro del contenedor de `deployment-frontend.yaml`. Explica cuál es la diferencia entre que falle una sonda *Readiness* (dejar de enviarle tráfico temporalmente) y que falle una sonda *Liveness* (reiniciar el contenedor).

3. **Reto 3 — Almacenamiento Persistente en Kubernetes con `PersistentVolumeClaim (PVC)`**:
   Los Pods son efímeros, pero ¿qué pasa si un contenedor necesita guardar datos en un Disco Persistente de Google Cloud? Investiga cómo crear un manifiesto de tipo `PersistentVolumeClaim` solicitando `5Gi` con `storageClassName: standard-rwo` y cómo montarlo en una carpeta `/datos` dentro de un Pod.

---

## 8. Referencias Oficiales

- **Referencia CLI: `gcloud container clusters`**: [https://docs.cloud.google.com/sdk/gcloud/reference/container/clusters](https://docs.cloud.google.com/sdk/gcloud/reference/container/clusters)
- **Guía de Inicio Rápido de GKE**: [https://docs.cloud.google.com/kubernetes-engine/docs/deploy-app-cluster](https://docs.cloud.google.com/kubernetes-engine/docs/deploy-app-cluster)
- **Configuración de Ingress para Balanceo de Carga de Aplicaciones en GKE**: [https://docs.cloud.google.com/kubernetes-engine/docs/how-to/load-balance-ingress](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/load-balance-ingress)
- **Autoescalamiento Horizontal de Pods (HPA) en GKE**: [https://docs.cloud.google.com/kubernetes-engine/docs/how-to/horizontal-pod-autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/horizontal-pod-autoscaling)
