<div align="center">

<img src="frontend/static/favicon.svg" alt="ContractsPulse logo" width="92" height="92" />

# ContractsPulse

**AI-powered contract intelligence — extract, analyze, redline, and negotiate with confidence.**

ContractsPulse turns dense PDF agreements into structured, risk-scored insights and ready-to-send vendor redlines. Built for legal, procurement, and engineering teams who need to understand a contract in minutes, not hours.

<p>
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" />
  <img alt="SvelteKit" src="https://img.shields.io/badge/SvelteKit-FF3E00?logo=svelte&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white" />
  <img alt="Redis" src="https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white" />
  <img alt="OpenAI" src="https://img.shields.io/badge/OpenAI-412991?logo=openai&logoColor=white" />
  <img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" />
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-22c55e" />
</p>

</div>

---

> [!TIP]
> **Just want to try it?** Run `./restart.sh`, open **[http://localhost:5173](http://localhost:5173)**, and log in with **`admin@admin.com`** / **`admin`**. See [Quick Start](#-quick-start-with-docker-recommended).

---

## 🚀 Key Features

*   **Intelligent Contract Ingestion** — Automated parsing, text extraction, and token-aware chunking of PDF agreements. Drag-and-drop multiple files at once, or paste raw contract text.
*   **AI-Powered Risk Analysis** — Clause-by-clause evaluation of legal liabilities, indemnifications, IP assignment, termination, and standard risk profiles, each scored **Critical → Low**.
*   **Plain-English Warnings** — Flags broad IP assignment and restrictive clauses with clear, developer-friendly side-project risk notes.
*   **Interactive Redlining** — Professional redline suggestions with mitigation language and plain-English rationale, viewable in a side-by-side diff.
*   **AI Vendor Email Drafting** — Generate a ready-to-send negotiation email summarizing your requested redlines for any contract version, with adjustable tone.
*   **Version Tracking & Verification** — Upload contract revisions, track versions, and verify how redlines were resolved between drafts.
*   **Portfolio Dashboard** — Portfolio health, risk heatmap, top risk categories, and critical triggers across every contract you own.
*   **Renewals Calendar** — Surface key dates and obligations so renewals and deadlines never slip.
*   **Secure Multi-User Scoping** — Database-backed JWT authentication isolates each user's contracts, reports, and activity logs.
*   **Rich CLI Client** — Analyze contracts, print reports, and submit redline feedback straight from your terminal.

### 🧭 Application Pages

| Page | Route | What it does |
|---|---|---|
| **Dashboard** | `/` | Portfolio health index, risk heatmap, and critical triggers at a glance. |
| **Contract Repository** | `/contracts` | Upload (drag & drop / paste), search, filter, and manage all agreements with live processing progress. |
| **Contract Cockpit** | `/contracts/{id}` | Deep dive: clauses, risks, redlines, version verification, and AI vendor email. |
| **Risk Inbox** | `/risk` | Consolidated, portfolio-wide feed of high-severity clauses with one-click redline copy. |
| **Vendors** | `/vendors` | Vendor-centric view of contracts and exposure. |
| **Calendar** | `/calendar` | Upcoming renewals, deadlines, and key contractual dates. |

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | SvelteKit 5 (runes), TypeScript, Vite |
| **Backend** | FastAPI (Python), Uvicorn, Pydantic / pydantic-ai |
| **AI** | OpenAI models for clause extraction, risk scoring, and redline/email generation |
| **Database** | PostgreSQL 16 with `pgvector` |
| **Cache / Queue** | Redis 7 |
| **Auth** | JWT (database-backed users) |
| **Packaging** | Docker & Docker Compose |

## 🗂 Project Structure

```
ContractsPulse/
├── backend/            # FastAPI app (API, AI agents, models, ingestion)
│   ├── app/
│   └── scripts/        # Maintenance scripts (e.g. change_credentials.py)
├── frontend/           # SvelteKit UI
│   ├── src/routes/     # Dashboard, contracts, risk, vendors, calendar
│   └── static/         # Branding assets (favicon / logo)
├── cli/                # Interactive CLI client
├── postgres/           # Persisted PostgreSQL data (volume)
├── redis/              # Persisted Redis data (volume)
├── docker-compose.yml  # frontend / api / db / redis services
├── restart.sh          # Helper: rebuild & restart the full stack
├── change-password.sh  # Helper: rotate the admin/user credentials
└── .env.example        # Environment template
```

## 🎨 Brand

The ContractsPulse mark pairs a **document** with a **pulse line** — the contract you're watching and the live risk signal we surface from it. The identity uses an indigo→violet gradient (`#5e6ad2 → #7c3aed`) that carries through the app's accent color and supports both light and dark themes.

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
| `OPENAI_MODEL_EXTRACTOR` | `openai:gpt-4.1-mini` | pydantic-ai model id used for clause extraction. | No |
| `OPENAI_MODEL_RISK` | `openai:gpt-4.1` | pydantic-ai model id used for risk scoring & redlines. | No |
| `DISABLE_SIGNUP` | `false` | Disable public user registration. Set to `true` for private instances. | No |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8000` | Comma-separated list of allowed browser origins. | No |
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

### Step 4: Log In With the Default Account
On first startup, the backend automatically seeds an administrator account if no users exist:

| Field | Value |
|---|---|
| **Email** | `admin@admin.com` |
| **Password** | `admin` |

> [!IMPORTANT]
> Change this password immediately after your first login (or register your own account and then set `DISABLE_SIGNUP=true`) before exposing the instance to a network.

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

### Changing the Default Username / Password

A helper script is included to rotate the seeded admin credentials (or any user's email/password) safely from your terminal. It runs inside the `api` container, so the stack must be up.

**Interactive (recommended)** — prompts securely for a new password:
```bash
./change-password.sh
```

Update a **different** user, or change the **login email** too:
```bash
# Update a specific account
./change-password.sh you@example.com

# Also change the login email of the admin account
NEW_EMAIL=you@example.com ./change-password.sh
```

**Non-interactive** (CI / automation) — pass the password via an environment variable:
```bash
CURRENT_EMAIL=admin@admin.com NEW_PASSWORD='ChangeMe!123' ./change-password.sh
```

> The script lives at `backend/scripts/change_credentials.py`. You can also call it directly:
> `docker compose exec api python scripts/change_credentials.py --help`

---

## 💾 Data Persistence

All application state is stored in the database, and the database is persisted to a host-mounted volume — so your users, contracts, extracted text, risk analyses, and redlines survive container restarts, rebuilds, and image upgrades.

| Data | Where it lives | Persisted via (in `docker-compose.yml`) |
|---|---|---|
| Users, contracts, clauses, risks, redlines, uploaded contract text | PostgreSQL | `./postgres:/var/lib/postgresql/data` |
| Cache / queue state | Redis | `./redis:/data` |

> [!NOTE]
> Uploaded PDFs are parsed on ingest and their text is stored in PostgreSQL, so there is no separate uploads directory to back up — **backing up `./postgres` backs up everything.**
>
> For named-volume deployments (e.g. Portainer), the included stack template maps `db_data` and `redis_data` named volumes for the same guarantee. To back up, stop the stack and archive the `./postgres` directory (or `docker run --rm -v ...` against the named volume).

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