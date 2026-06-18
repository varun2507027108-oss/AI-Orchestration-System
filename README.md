# 🌿 AI Founder Orchestration System

<p align="center">
  <img src="https://img.shields.io/badge/Frontend-Next.js%2015-059669?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js 15" />
  <img src="https://img.shields.io/badge/Backend-FastAPI-10B981?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Orchestration-LangGraph-34D399?style=for-the-badge&logo=python&logoColor=white" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Database-SQLite-047857?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
</p>

An advanced, multi-agent AI pipeline designed to guide founders from a raw startup idea to a fully structured, ready-to-build project. The system orchestrates six specialised AI agents operating in sequence with a **human-in-the-loop gate interrupt** for risk control, producing custom PRDs, database architectures, issues backlogs, promotional copies, and compiled PDF reports.

---

## 🗺️ System Architecture

The workflow is managed as a stateful graph using **LangGraph**, executing agents sequentially and saving intermediate artifacts and decision logs to a local SQLite database.

```mermaid
graph TD
    Start([ Founder Submits Idea ]) --> Advisor[1. Startup Advisor]
    Advisor --> Gate{Risk Assessment Gate}
    
    Gate -- Risk >= 0.8 --> Interrupted([ Awaiting Revision ])
    Interrupted --> Resume[Founder Revises Idea]
    Resume --> Advisor
    
    Gate -- Risk < 0.8 --> Researcher[2. Market Researcher]
    Researcher --> PM[3. Product Manager]
    PM --> Architect[4. System Architect]
    Architect --> EM[5. Engineering Manager]
    EM --> Marketing[6. Marketing Specialist]
    Marketing --> Export[Generate PDF & Sync Integrations]
    Export --> End([ deep deep interaction console ])
```

---

## 👥 Meet the Agents

| Agent | Icon | Role & Description | LLM / Client |
| :--- | :---: | :--- | :--- |
| **Startup Advisor** | 💡 | Evaluates the initial idea, identifies risks, and sets the gate decision. | Groq (`ADVISOR_API_KEY`) |
| **Market Research** | 🔍 | Researches competitors and market trends using web search. | Groq (`RESEARCHER_API_KEY`) |
| **Product Manager** | 📋 | Drafts the PRD (Product Requirements Document) based on the research. | Gemini (`PM_API_KEY`) |
| **System Architect** | 📐 | Compiles the tech stack, system architecture, and outputs SQL schemas. | Nvidia NIM (`ARCHITECT_API_KEY`) |
| **Engineering Manager** | ⚙️ | Generates task backlogs, creates sprints, and syncs issues to GitHub. | Groq (`EM_API_KEY`) |
| **Marketing Specialist** | 📣 | Develops brand assets, launch strategies, and marketing copy. | Groq (`MARKETING_API_KEY`) |

---

## 📂 Project Structure

```directory
├── backend/
│   ├── main.py              # FastAPI application server & REST endpoints
│   ├── graph.py             # LangGraph workflow, nodes, and conditional routing
│   ├── models.py            # Pydantic validation schemas & state definitions
│   ├── db.py                # SQLite persistence handlers & connection life cycles
│   ├── config.py            # Configuration settings & environment variables loader
│   ├── requirements.txt     # Python backend dependencies
│   ├── test_api.py          # End-to-end integration test runner
│   └── tools/               # External modules (Tavily search, GitHub sync, Notion sync, PDF compiler)
└── frontend/
    ├── app/                 # Next.js 15 App Router pages (globals, landing, intake, tracking console)
    ├── components/          # Reusable UI components & animations (Framer Motion)
    ├── lib/                 # Next.js config utilities
    ├── package.json         # Frontend Node dependencies & scripts
    └── tsconfig.json        # Next.js TypeScript config
```

---

## ⚙️ Environment Configuration

### Backend Setup (`backend/.env`)
Create a `.env` file inside the `backend` folder and populate it with your keys:

```env
# Generic LLM API Keys
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
NVIDIA_NIM_API_KEY=your_nvidia_nim_api_key
TAVILY_API_KEY=your_tavily_api_key

# Agent-Specific API Key Routing (Falls back to generic keys above if empty)
ADVISOR_API_KEY=
RESEARCHER_API_KEY=
PM_API_KEY=
ARCHITECT_API_KEY=
EM_API_KEY=
MARKETING_API_KEY=

# Integration Tokens (Optional)
GITHUB_TOKEN=your_github_personal_access_token
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id

# Server Configurations
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ALLOWED_ORIGIN=http://localhost:3000
```

---

## 🚀 Getting Started

### 1. Start the Backend Server
Prerequisites: Python 3.10+ installed.

```bash
cd backend
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The FastAPI Swagger interactive docs will be available at `http://127.0.0.1:8000/docs`.

### 2. Start the Frontend Application
Prerequisites: Node.js 18+ installed.

```bash
cd frontend
# Install Node dependencies
npm install

# Run the development server
npm run dev
```

Open `http://localhost:3000` in your browser to access the landing page.

---

## 🧪 Running Integration Tests
To verify the complete workflow end-to-end (Safe flow, gate interrupts, resume logic, and PDF generation):

```bash
cd backend
python test_api.py
```

---

## ✨ Design & Aesthetic Philosophy
The frontend uses an **"Ethereal Nature Tech"** design system:
* **Glassmorphism**: Translucent panels with background blurs, subtle borders, and soft inner shadows.
* **Harmonious Dark Theme**: Deep forest greens (`#047857`, `#059669`) combined with sleek slate/black colors.
* **Micro-animations**: Smooth layout animations powered by `framer-motion` for transitions between stages and state updates.
* **Console-Like Metrics**: A robust sidebar displaying the step-by-step decision logs, risk scores, and generated file exports.
