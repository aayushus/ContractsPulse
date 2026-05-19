# 📑 ContractsPulse

**ContractsPulse** is an advanced contract intelligence and analysis platform designed to streamline legal and procurement workflows. By leveraging state-of-the-art AI orchestration and modern design engineering, it enables rapid extraction, analysis, and management of complex contractual documents.

---

## 🚀 Key Features & Project Goals
*   **Intelligent Contract Ingestion**: Automated parsing, text extraction, and token-aware chunking of PDF agreements.
*   **AI-Powered Risk Analysis**: Deep learning evaluation targeting legal liabilities, indemnifications, and standard risk profiles.
*   **Plain-English Warnings**: Flagging of broad Intellectual Property (IP) assignment clauses with clear side-project risks for developers.
*   **Interactive Redlining**: Automated, professional redlines suggesting mitigation text, accompanied by plain-English rationales.
*   **User Identity & Scoping**: Secure database-backed JWT authentication to isolate contract history, reports, and activity logs.

---

## 🏠 Homelab & Self-Hosting Guide

ContractsPulse is fully optimized for self-hosting in homelabs alongside premium applications like **Vaultwarden**, **Home Assistant**, and **Portainer**. 

Thanks to our dynamic hostname resolution, the frontend and API can be exposed securely behind a **single domain/port** using a reverse proxy. This eliminates mixed-content SSL issues, CORS configuration headers, and the need to expose raw API ports (`9432`) to your local network or the internet.

```
                  ┌──────────────────────┐
                  │  HTTPS Reverse Proxy │
                  │  (Caddy/Traefik/NPM) │
                  └──────────┬───────────┘
                             │
              ┌──────────────┴──────────────┐
       /api   │                             │   /
              ▼                             ▼
   ┌────────────────────┐        ┌────────────────────┐
   │    Backend API     │        │      Frontend      │
   │ (Port 9432, Docker)│        │ (Port 5173, Docker)│
   └────────────────────┘        ┌────────────────────┐
```

---

## ⚙️ Environment Configuration

The application is configured using a unified `.env` file located in the project root directory.

### `.env` Variables Reference

| Variable | Default Value | Description | Required |
|---|---|---|---|
| `OPENAI_API_KEY` | *(None)* | OpenAI platform API Key for clause extraction and analysis. | **Yes** |
| `JWT_SECRET` | `super-secret-contractspulse-key-change-it` | Key used to encode/decode JWT authorization tokens. | **Yes** |
| `DISABLE_SIGNUP` | `false` | Disable public user registration. Set to `true` for private instances. | No |
| `POSTGRES_USER` | `postgres` | Username for the PostgreSQL database container. | No |
| `POSTGRES_PASSWORD` | `postgres` | Password for the PostgreSQL database container. | No |
| `POSTGRES_DB` | `contractspulse` | Database name for persistent tables. | No |
| `DATABASE_URL` | `postgresql://...` | Connection URI used by the FastAPI backend to query PostgreSQL. | No |
| `REDIS_URL` | `redis://redis:6379/0` | Connection URI used to connect to Redis cache/queue. | No |

---

## 🐳 Quick Start with Docker (Recommended)

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine installed and running.
*   An active **OpenAI API Key** configured in the `.env` file.

### Step 1: Clone and Set Up the Environment
Create your local environment file by copying the template:
```bash
cp .env.example .env
```
Open `.env` and fill in your `OPENAI_API_KEY`:
```ini
OPENAI_API_KEY=sk-proj-xxxxxx...
```

### Step 2: Spin Up the Stack
Use the helper restart script to pull, build, and run all services in detached mode:
```bash
./restart.sh
```
Alternatively, execute standard Docker Compose commands:
```bash
docker compose up -d --build
```

### Step 3: Access the Application Services
Once the containers are online, the following services are active:
*   **Web Frontend UI**: [http://localhost:5173](http://localhost:5173)
*   **FastAPI Backend API Docs**: [http://localhost:9432/docs](http://localhost:9432/docs)

---

## 🎛 Portainer & Homelab Deployment

If deploying via **Portainer**, you can paste the stack definition below directly into the Portainer "Add Stack" editor. 

Ensure you map persistent data to named Docker volumes (or local storage paths) so database records, user history, and AI reports survive updates.

### Copy-Pasteable Portainer / Docker Compose Template
```yaml
version: '3.8'

services:
  frontend:
    image: node:20-alpine
    working_dir: /app
    volumes:
      - ./frontend:/app
    ports:
      - "5173:5173"
    command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
    environment:
      - NODE_ENV=development
    depends_on:
      - api
    restart: unless-stopped

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "9432:9432"
    volumes:
      - ./backend:/app
    env_file:
      - .env
    depends_on:
      - db
      - redis
    command: uvicorn app.main:app --host 0.0.0.0 --port 9432 --reload
    restart: unless-stopped

  db:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    env_file:
      - .env
    volumes:
      - db_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  db_data:
    driver: local
  redis_data:
    driver: local
```

---

## 🔒 Controlling Registrations (`DISABLE_SIGNUP`)

For private homelab instances, you can restrict public user signups after seeding your primary user account.

### How to Disable Signups
Set the environment variable in your `.env` file:
```ini
DISABLE_SIGNUP=true
```
Then, restart the API container:
```bash
docker compose restart api
```

### System Behavior Under `DISABLE_SIGNUP=true`
*   **Frontend**: The "Sign Up" tab on the authentication card is **disabled** and hidden. A monochromatic warning banner alerts users: *"Registration has been disabled by the system administrator. Please log in using existing credentials."*
*   **Backend**: The `GET /api/v1/auth/signup-status` endpoint reports `{"signup_disabled": true}`. Any direct requests to `POST /api/v1/auth/signup` are instantly blocked with a `403 Forbidden` error.

---

## 🛡 Reverse Proxy Setup (Single Domain SSL)

To run ContractsPulse securely behind an external URL (e.g. `https://contracts.your-domain.com`) without exposing multiple ports, use one of the copy-pasteable proxy configurations below.

### 1. Nginx Proxy Manager (NPM)
1.  Add a new **Proxy Host**.
2.  Set **Domain Names** to `contracts.your-domain.com`.
3.  Set **Scheme** to `http`, **Forward Hostname/IP** to `frontend` (or the server IP running Docker), and **Forward Port** to `5173`.
4.  Enable **Websockets Support** (required for SvelteKit hot reload and stream events).
5.  Go to the **Custom Locations** tab and add the following entry to route backend API requests:
    *   **Define Location**: `/api`
    *   **Scheme**: `http`
    *   **Forward Hostname/IP**: `api` (or the server IP running Docker)
    *   **Forward Port**: `9432`
6.  Under the **SSL** tab, request a Let's Encrypt Certificate and force SSL.

### 2. Caddy Server (Caddyfile)
Caddy provides automated HTTPS out-of-the-box. Add the following block to your `Caddyfile`:
```caddy
contracts.your-domain.com {
    # Route all API traffic to the backend API container
    handle /api* {
        reverse_proxy api:9432
    }

    # Route all other traffic to the SvelteKit frontend container
    handle {
        reverse_proxy frontend:5173
    }
}
```

### 3. Traefik (Docker Labels)
If you prefer configuring via container labels directly inside your Compose file, append these labels to your services:
```yaml
services:
  frontend:
    # ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.contracts-fe.rule=Host(`contracts.your-domain.com`)"
      - "traefik.http.routers.contracts-fe.entrypoints=websecure"
      - "traefik.http.routers.contracts-fe.tls.certresolver=myresolver"
      - "traefik.http.services.contracts-fe.loadbalancer.server.port=5173"

  api:
    # ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.contracts-api.rule=Host(`contracts.your-domain.com`) && PathPrefix(`/api`)"
      - "traefik.http.routers.contracts-api.entrypoints=websecure"
      - "traefik.http.routers.contracts-api.tls.certresolver=myresolver"
      - "traefik.http.services.contracts-api.loadbalancer.server.port=9432"
```

---

## 🔐 Database Seeding & Default Credentials

To provide a seamless out-of-the-box experience, the FastAPI backend automatically executes DDL checks on startup:
1.  Creates database tables for `users` and `contracts` if they do not exist.
2.  Ensures the `contracts` schema has the mandatory `user_id` foreign key.
3.  Seeds a **default administrator account** if no users are registered in the system:
    *   **Email**: `admin@admin.com`
    *   **Password**: `admin`

> [!IMPORTANT]
> Change the default password immediately after your initial login, or register your custom account first and then set `DISABLE_SIGNUP=true` to secure your instance.

---

## 💻 CLI Client Setup & Usage

ContractsPulse comes with a rich, interactive Command Line Interface (CLI) client for developer productivity.

### Step 1: Install CLI Dependencies
The CLI client lives in the `/cli` folder. Navigate to it or run the installation inside a Python virtual environment:
```bash
cd cli
pip install -r requirements.txt
cd ..
```

### Step 2: Configure CLI Target URL
By default, the CLI client communicates with `http://localhost:8000`. Since the Docker Compose stack exposes the FastAPI API on port `9432`, export the override environment variable in your terminal session:
```bash
export CONTRACTSPULSE_API_URL="http://localhost:9432"
```

### Step 3: Run Commands
You can upload agreements directly from the command line for structured analysis:

#### 1. Analyze a Contract PDF
```bash
python cli/contractpulse.py analyze --file SampleContract-Shuttle.pdf
```
*The CLI will upload the document, display a live CLI spinner while the backend extracts and scores risks, and print a premium, formatted ASCII report with plain-English side-project warning notifications and redline recommendations.*

#### 2. Print a Stored Report (or Save to PDF)
To review an existing contract analysis or save it locally as a PDF file:
```bash
python cli/contractpulse.py report <contract_uuid> --output pdf --save ./report.pdf
```

#### 3. Submit Interactive Redline Feedback
To submit feedback on a specific clause classification directly from your terminal:
```bash
python cli/contractpulse.py feedback <contract_uuid> <clause_uuid> --is-risky --note "This clause restricts all open source projects."
```

### 🗝 CLI Backward Compatibility
The CLI does not prompt or store login sessions. To support legacy CLI workflows seamlessly without breaking terminal automation:
*   Unauthenticated requests that do not supply an `Authorization: Bearer <token>` header automatically fall back to the default seeded user (`admin@admin.com`).
*   All CLI-uploaded contracts, reports, and status queries map to this default administrator account, allowing instant terminal workflows out-of-the-box.

---

## 🔧 Manual Local Setup (Non-Docker)

If you prefer to run the backend and frontend services locally outside of Docker containers, follow these steps:

### Prerequisites
*   **PostgreSQL** installed locally and running (configured to match `.env`).
*   **Redis Server** installed and running on port `6379`.
*   **Node.js** (version 20 or higher) and **npm** installed.
*   **Python** (version 3.10 or higher) installed.

### 1. Manual Backend Setup
1.  Navigate into the backend directory:
    ```bash
    cd backend
    ```
2.  Create and activate a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  Install python dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Start the FastAPI backend with Uvicorn:
    ```bash
    uvicorn app.main:app --host 127.0.0.1 --port 9432 --reload
    ```

### 2. Manual Frontend Setup
1.  Navigate into the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install npm packages:
    ```bash
    npm install
    ```
3.  Start the SvelteKit development server:
    ```bash
    npm run dev
    ```
4.  Access the web interface at `http://localhost:5173`.

---

## 📄 License

This project is licensed under the permissive open-source **MIT License**. Please refer to the `LICENSE` file for full terms and conditions.