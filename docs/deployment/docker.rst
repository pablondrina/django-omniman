Docker Deployment
=================

This guide covers deploying Omniman using Docker and Docker Compose.


Dockerfile
----------

.. code-block:: dockerfile

   # Dockerfile

   FROM python:3.11-slim as builder

   WORKDIR /app

   # Install build dependencies
   RUN apt-get update && apt-get install -y \
       build-essential \
       libpq-dev \
       && rm -rf /var/lib/apt/lists/*

   # Install Python dependencies
   COPY requirements.txt .
   RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

   # Production image
   FROM python:3.11-slim

   WORKDIR /app

   # Install runtime dependencies
   RUN apt-get update && apt-get install -y \
       libpq5 \
       && rm -rf /var/lib/apt/lists/*

   # Create non-root user
   RUN useradd --create-home --shell /bin/bash app
   USER app

   # Copy wheels from builder
   COPY --from=builder /app/wheels /wheels
   RUN pip install --no-cache /wheels/*

   # Copy application
   COPY --chown=app:app . .

   # Collect static files
   RUN python manage.py collectstatic --noinput

   # Expose port
   EXPOSE 8000

   # Health check
   HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
       CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')"

   # Run with gunicorn
   CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "myproject.wsgi:application"]


Docker Compose
--------------

Development
~~~~~~~~~~~

.. code-block:: yaml

   # docker-compose.yml

   version: "3.8"

   services:
     web:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DEBUG=true
         - DATABASE_URL=postgres://postgres:postgres@db:5432/omniman
         - REDIS_URL=redis://redis:6379/0
       depends_on:
         - db
         - redis
       volumes:
         - .:/app
       command: python manage.py runserver 0.0.0.0:8000

     db:
       image: postgres:15-alpine
       environment:
         - POSTGRES_DB=omniman
         - POSTGRES_USER=postgres
         - POSTGRES_PASSWORD=postgres
       volumes:
         - postgres_data:/var/lib/postgresql/data
       ports:
         - "5432:5432"

     redis:
       image: redis:7-alpine
       ports:
         - "6379:6379"

   volumes:
     postgres_data:

Production
~~~~~~~~~~

.. code-block:: yaml

   # docker-compose.prod.yml

   version: "3.8"

   services:
     web:
       build:
         context: .
         dockerfile: Dockerfile
       environment:
         - DJANGO_SETTINGS_MODULE=myproject.settings.production
         - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
         - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}
         - REDIS_URL=redis://redis:6379/0
       depends_on:
         db:
           condition: service_healthy
         redis:
           condition: service_started
       deploy:
         replicas: 3
         resources:
           limits:
             cpus: "1"
             memory: 512M
         restart_policy:
           condition: on-failure
           delay: 5s
           max_attempts: 3

     nginx:
       image: nginx:alpine
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
         - ./nginx/ssl:/etc/nginx/ssl:ro
         - static_files:/var/www/static:ro
       depends_on:
         - web

     db:
       image: postgres:15-alpine
       environment:
         - POSTGRES_DB=${DB_NAME}
         - POSTGRES_USER=${DB_USER}
         - POSTGRES_PASSWORD=${DB_PASSWORD}
       volumes:
         - postgres_data:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
         interval: 10s
         timeout: 5s
         retries: 5
       deploy:
         resources:
           limits:
             cpus: "2"
             memory: 2G

     redis:
       image: redis:7-alpine
       command: redis-server --appendonly yes
       volumes:
         - redis_data:/data
       deploy:
         resources:
           limits:
             cpus: "0.5"
             memory: 256M

     worker:
       build: .
       command: python manage.py process_directives --watch --interval 2
       environment:
         - DJANGO_SETTINGS_MODULE=myproject.settings.production
         - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
         - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}
         - REDIS_URL=redis://redis:6379/0
       depends_on:
         - db
         - redis
       deploy:
         replicas: 2
         restart_policy:
           condition: on-failure
           delay: 5s
           max_attempts: 5

     # Manutenção periódica (cron jobs via container efêmero)
     # Alternativa: usar cron do host ou um scheduler como ofelia
     cron:
       build: .
       command: >
         sh -c "
         while true; do
           python manage.py cleanup_idempotency_keys --days 7;
           python manage.py release_expired_holds;
           sleep 86400;
         done
         "
       environment:
         - DJANGO_SETTINGS_MODULE=myproject.settings.production
         - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
         - DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}
       depends_on:
         - db
       deploy:
         replicas: 1
         restart_policy:
           condition: on-failure

   volumes:
     postgres_data:
     redis_data:
     static_files:


Nginx Configuration
-------------------

.. code-block:: nginx

   # nginx/nginx.conf

   upstream omniman {
       server web:8000;
   }

   server {
       listen 80;
       server_name _;

       location /static/ {
           alias /var/www/static/;
           expires 30d;
       }

       location / {
           proxy_pass http://omniman;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }


Kubernetes Deployment
---------------------

Deployment
~~~~~~~~~~

.. code-block:: yaml

   # k8s/deployment.yaml

   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: omniman-web
     labels:
       app: omniman
       component: web
   spec:
     replicas: 3
     selector:
       matchLabels:
         app: omniman
         component: web
     template:
       metadata:
         labels:
           app: omniman
           component: web
       spec:
         containers:
           - name: web
             image: myregistry/omniman:latest
             ports:
               - containerPort: 8000
             envFrom:
               - secretRef:
                   name: omniman-secrets
               - configMapRef:
                   name: omniman-config
             resources:
               requests:
                 cpu: "250m"
                 memory: "256Mi"
               limits:
                 cpu: "1000m"
                 memory: "512Mi"
             livenessProbe:
               httpGet:
                 path: /health/
                 port: 8000
               initialDelaySeconds: 30
               periodSeconds: 10
             readinessProbe:
               httpGet:
                 path: /health/
                 port: 8000
               initialDelaySeconds: 5
               periodSeconds: 5

Service
~~~~~~~

.. code-block:: yaml

   # k8s/service.yaml

   apiVersion: v1
   kind: Service
   metadata:
     name: omniman-web
   spec:
     selector:
       app: omniman
       component: web
     ports:
       - port: 80
         targetPort: 8000
     type: ClusterIP

   ---
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: omniman-ingress
     annotations:
       kubernetes.io/ingress.class: nginx
       cert-manager.io/cluster-issuer: letsencrypt-prod
   spec:
     tls:
       - hosts:
           - api.example.com
         secretName: omniman-tls
     rules:
       - host: api.example.com
         http:
           paths:
             - path: /
               pathType: Prefix
               backend:
                 service:
                   name: omniman-web
                   port:
                     number: 80

ConfigMap and Secrets
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # k8s/configmap.yaml

   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: omniman-config
   data:
     DJANGO_SETTINGS_MODULE: "myproject.settings.production"
     DB_HOST: "postgresql.database.svc.cluster.local"
     DB_NAME: "omniman"
     REDIS_URL: "redis://redis.cache.svc.cluster.local:6379/0"

   ---
   apiVersion: v1
   kind: Secret
   metadata:
     name: omniman-secrets
   type: Opaque
   stringData:
     DJANGO_SECRET_KEY: "your-secret-key"
     DB_USER: "omniman"
     DB_PASSWORD: "secure-password"


Docker Commands
---------------

Build
~~~~~

.. code-block:: bash

   # Build image
   docker build -t omniman:latest .

   # Build with build args
   docker build \
       --build-arg PYTHON_VERSION=3.11 \
       -t omniman:latest .

   # Multi-platform build
   docker buildx build \
       --platform linux/amd64,linux/arm64 \
       -t myregistry/omniman:latest \
       --push .

Run
~~~

.. code-block:: bash

   # Run container
   docker run -d \
       --name omniman \
       -p 8000:8000 \
       -e DATABASE_URL=postgres://... \
       omniman:latest

   # Run with docker-compose
   docker-compose up -d

   # Production with env file
   docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

Manage
~~~~~~

.. code-block:: bash

   # Run migrations
   docker-compose exec web python manage.py migrate

   # Create superuser
   docker-compose exec web python manage.py createsuperuser

   # View logs
   docker-compose logs -f web

   # Scale
   docker-compose up -d --scale web=3

   # Restart
   docker-compose restart web


CI/CD Pipeline
--------------

GitHub Actions
~~~~~~~~~~~~~~

.. code-block:: yaml

   # .github/workflows/deploy.yml

   name: Deploy

   on:
     push:
       branches: [main]

   jobs:
     build:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4

         - name: Set up Docker Buildx
           uses: docker/setup-buildx-action@v3

         - name: Login to Registry
           uses: docker/login-action@v3
           with:
             registry: ghcr.io
             username: ${{ github.actor }}
             password: ${{ secrets.GITHUB_TOKEN }}

         - name: Build and push
           uses: docker/build-push-action@v5
           with:
             context: .
             push: true
             tags: ghcr.io/${{ github.repository }}:latest
             cache-from: type=gha
             cache-to: type=gha,mode=max

     deploy:
       needs: build
       runs-on: ubuntu-latest
       steps:
         - name: Deploy to server
           uses: appleboy/ssh-action@v1.0.0
           with:
             host: ${{ secrets.SSH_HOST }}
             username: ${{ secrets.SSH_USER }}
             key: ${{ secrets.SSH_KEY }}
             script: |
               cd /opt/omniman
               docker-compose pull
               docker-compose up -d


See Also
--------

- :doc:`production` - Production configuration
- :doc:`performance` - Performance optimization
