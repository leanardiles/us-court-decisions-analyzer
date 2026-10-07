# Court Opinions Analyzer

AI-assisted analysis of election-law opinions, with human-in-the-loop verification.

**Capstone I + II** | Katz School of Applied Sciences & Cardozo Law School (Yeshiva University)  
**Team:** Leandro Ardiles, Alex Ji, Enock Katenda, Tafadzwa Nyemba  
**Status:** Capstone II in progress — corpus ingested; System A vs System B evaluation not yet run

There are two stores. Do not mix them up:

| Store | What it is | Who uses it |
|---|---|---|
| **Capstone I app** (SQLite + FastAPI/React) | System A baseline: one Groq call, validator, scholar review | Leandro / local demo |
| **Capstone II corpus** (shared Supabase Postgres + pgvector) | 539 unique LEXIS decisions, families, chunks, retrieve | Whole team; Alex’s agents |

Identity is the **LEXIS citation**, not the file name. `Craig v. Simon.docx` and `Craig v. Simon(2).docx` are different decisions in the same lawsuit.

---

## Capstone II — corpus and retrieve

The LEXIS Word dump is parsed with rules (no Groq). Embeddings are a local model. Groq is reserved for agent runs.

**What is loaded now**

- 541 Word files parsed; 539 decisions stored (one true re-export skipped; one stub with no LEXIS cite not stored)
- 427 litigation families; citation links in `decision_relations`
- ~14,977 chunks with character offsets and 384-d embeddings (`BAAI/bge-small-en-v1.5`)
- Frozen 50-decision pilot: `backend/data/pilot_50_manifest.json`
- Row-level security is **on** (no public REST policies). Use the Postgres connection, not the publishable/anon key, to read tables.

**Ingest / retrieve** (from `backend/`, venv activated; on this Mac use `./venv/bin/python` if `python` is missing)

```bash
./venv/bin/python -m app.ingest.load_supabase --ping
./venv/bin/python -m app.ingest.load_supabase --query "Purcell principle days before an election" --k 5
./venv/bin/python -m app.ingest.load_supabase --query "..." --lexis "2020 U.S. Dist. LEXIS 187996"
```

From Python (agents):

```python
from app.ingest.load_supabase import retrieve
hits = retrieve(question, k=8, lexis_citation=cite, print_results=False)
```

Parser regression tests (need the local Word folder or `WORD_CORPUS_DIR`):

```bash
cd backend && PYTHONPATH=. ./venv/bin/python -m unittest tests.test_extract_qa -v
```

Do **not** commit `backend/.env`, the Word dump, or full-text JSON dumps. Copy `backend/.env.example` and get the DB password privately. Quote `SUPABASE_DB_PASSWORD` if it contains `#` or `$`. Connect through the session pooler (`aws-0-us-east-2.pooler.supabase.com:6543`), not `db.*.supabase.co`.

Details: [`backend/app/ingest/README.md`](backend/app/ingest/README.md). Faculty status: `current_docs/Capstone_II_Status_Report_5_Oct_2026.pdf`. QA fix list: `current_docs/database-qa-2026-10-06.md`.

---

## 📋 Project Overview (Capstone I app)

A web-based platform that enables legal scholars to analyze court opinions with AI assistance and human verification. The system implements a three-tier workflow:

1. **AI Analysis** → Automated analysis of court opinions using Llama 3.3 70B / Llama 4 Maverick (Groq Cloud) or mock AI
2. **TA Verification** → Human validators verify AI findings
3. **Scholar Review** → Legal scholars review verified results

### Key Features

✅ **Role-Based Access Control** (Admin, Scholar, Validator)  
✅ **JWT Authentication** with secure password hashing  
✅ **Database-Driven Architecture** (13-table relational schema with round tracking)  
✅ **RESTful API** with auto-generated documentation  
✅ **Parquet File Processing** with automated parsing  
✅ **Project Management** with CRUD operations and scholar assignment  
✅ **Project Lifecycle Workflow** (draft → ready → active)  
✅ **Parquet Upload & Removal** (one file per project)  
✅ **Dynamic Case Viewer** with on-demand modal  
✅ **Cardozo Law Branded UI** (professional design system)  
✅ **Module-Based Verification** with configurable research questions  
✅ **Module Detail Page** with full module management  
✅ **Two-Level Context System** (project-wide + module-specific)  
✅ **Collapsed Context Preview** with view/edit modal (project and module level)  
✅ **AI Provider Selection** (Dummy AI, Llama 3.1 8B, Llama 3.3 70B, Llama 4 Maverick via Groq)  
✅ **Cloud AI Integration** with Groq API (free tier: 14,400 requests/day)  
✅ **Structured AI Responses** with parsed answer, reasoning and confidence scoring  
✅ **Anchored Confidence Scoring** based on evidence quality criteria  
✅ **Mock AI Analysis** for testing validator workflow  
✅ **Clone Module** with pre-populated form (name left blank for scholar)  
✅ **Module Deletion** with tiered confirmation based on validation status  
✅ **Validator Dashboard** with accordion layout grouped by project  
✅ **Project-level progress bar** across all modules  
✅ **Accurate Validation Status Display** (waiting / in progress / complete)  
✅ **Case-by-Case Validation Interface** with AI review and corrections  
✅ **Submit All Validations** — validator explicitly submits to trigger scholar notification  
✅ **Validation Completion Summary** with accuracy statistics  
✅ **Scholar Review Interface** with approve/reject workflow  
✅ **Trust Validator Bulk Approve** feature  
✅ **Feedback Library** for AI improvement (Round 2)  
✅ **Module Results Page** with validation analytics  
✅ **Confidence Calibration Table** — accuracy by confidence tier  
✅ **Answer Distribution Analysis** — AI vs validator answer breakdown  
✅ **Trust Threshold Recommendation** — actionable scholar guidance  
✅ **Alternating Color Backgrounds** for module cards  
🚧 **Multi-Round Feedback Loop** (In progress)  
🚧 **New Round Workflow** (In progress)  
🚧 **Mark Module as Complete** (In progress)

---

## 🏗️ Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **Database (app):** SQLite via SQLAlchemy (Capstone I HITL workflow)
- **Database (corpus):** Supabase Postgres + pgvector (Capstone II ingest/retrieve)
- **Authentication:** JWT (python-jose) + bcrypt
- **Data Processing:** Pandas, PyArrow (Parquet upload for the app); rule-based Word XML parse for ingest
- **Embeddings:** local `fastembed` (`BAAI/bge-small-en-v1.5`, 384-d) — not Groq
- **AI Integration:** Groq API (reserved for System A / System B agent runs)

### Frontend
- **Framework:** React 18
- **Build Tool:** Vite
- **Styling:** Tailwind CSS 3.4+
- **State Management:** React Hooks

### AI Models
- **Cloud Inference:** Groq API (free tier)
- **Models:**
  - Llama 3.1 8B Instant (`llama-3.1-8b-instant`) — Fast
  - Llama 3.3 70B Versatile (`llama-3.3-70b-versatile`) — Recommended
  - Llama 4 Maverick 17B (`meta-llama/llama-4-maverick-17b-128e-instruct`) — Best Quality
- **Mock AI:** Built-in dummy responses for testing

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ and npm
- Git
- **Groq API Key** (free) - [Sign up here](https://console.groq.com)

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/leanardiles/us-court-decisions-analyzer.git
cd us-court-decisions-analyzer
```

**2. Backend Setup**
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (Git Bash):
source venv/Scripts/activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create database tables
python init_db.py

# Create test users
python create_test_users.py
```

**3. Environment Variables Setup**

Create a `.env` file in the `backend/` directory:
```bash
cp .env.example .env
```

Then edit `.env`. For the **Capstone I app** you need a Groq key (https://console.groq.com). For **Capstone II ingest/retrieve** you also need the shared Supabase values (password sent privately — do not paste it into Slack or a PDF):

```env
GROQ_API_KEY=gsk_your_actual_api_key_here
DATABASE_URL=sqlite:///./database.db
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=your_publishable_key_here
SUPABASE_DB_PASSWORD='your_database_password'
SUPABASE_DB_URL=postgresql://postgres.YOUR_PROJECT:URL_ENCODED_PASSWORD@aws-0-us-east-2.pooler.supabase.com:6543/postgres?sslmode=require
```

See `backend/.env.example`. **Never commit `.env`.** The publishable key cannot read the corpus tables (RLS is on).

**4. Frontend Setup**
```bash
cd frontend
npm install
```

### Running the Application

**Start Backend** (Terminal 1)
```bash
cd backend
source venv/Scripts/activate  # Windows Git Bash
uvicorn app.main:app --reload --port 8000
```
Backend runs on: http://localhost:8000  
API Documentation: http://localhost:8000/docs

**Start Frontend** (Terminal 2)
```bash
cd frontend
npm run dev
```
Frontend runs on: http://localhost:5173

---

## 🤖 AI Provider Options

When creating a module, scholars can choose from:

1. **🎭 Dummy AI (Testing)** - Instant mock responses for testing validator workflow
2. **⚡ Llama 3.1 8B (Groq - Fast)** - Quick analysis for simple questions
3. **🎯 Llama 3.3 70B (Groq - Recommended)** - Balanced speed and accuracy (default)
4. **🔥 Llama 4 Maverick 17B (Groq - Best Quality)** - Highest accuracy for complex legal questions

All Groq models run on cloud infrastructure with **no local setup required**. The free tier provides 14,400 requests per day, which is more than sufficient for typical research projects.

**AI Provider is locked after the first module is created** to ensure data integrity across all modules in a project. The same provider is used across all rounds of a module.

### Structured AI Responses

All Groq-powered analyses return structured responses with three components:

- **ANSWER** — The direct answer to the research question
- **REASONING** — 2-4 sentences citing specific parts of the opinion
- **CONFIDENCE** — A score from 0.0 to 1.0 based on evidence quality:
  - `0.90–1.00` = Answer explicitly and unambiguously stated in the opinion
  - `0.70–0.89` = Answer strongly implied but not directly stated
  - `0.50–0.69` = Opinion is ambiguous or requires significant interpretation
  - `0.00–0.49` = Opinion lacks sufficient information or question does not apply

### Why Groq Instead of Local Ollama?

- ✅ **No GPU required** - Runs entirely in the cloud
- ✅ **Faster inference** - Optimized hardware for LLM inference
- ✅ **Free tier** - 14,400 requests/day (far exceeds typical usage)
- ✅ **No installation** - Just need an API key
- ✅ **No disk space** - Models hosted remotely
- ✅ **Better for collaboration** - Team members don't need powerful computers

---

## 📊 Database Schema

Current schema includes 13 tables, with round tracking across key tables:

- **users** - User accounts with role-based access (admin/scholar/validator)
- **projects** - Research projects containing court case collections
- **court_cases** - Individual court opinions with metadata
- **verification_modules** - Research questions for AI analysis (tracks `ai_round`)
- **module_case_samples** - Random case samples per module and round
- **validator_assignments** - Links validators to cases for verification, per round
- **ai_analyses** - AI-generated answers with reasoning and confidence, per round
- **validation_feedback** - Validator corrections and scholar review, per round
- **feedback_library** - Approved corrections for Round 2 training
- **project_contexts** - Project-wide guidance for AI
- And 3 more supporting tables

See `backend/docs/DATABASE_SCHEMA.txt` for complete schema documentation.

---

## 📈 Validation Analytics

After each validation round, scholars can access a **Module Results Page** with:

### 1. Overview
- Total cases analyzed, AI correct count, AI incorrect count
- Overall accuracy percentage with color-coded bar

### 2. Confidence Calibration
Accuracy broken down by confidence tier — answers the key research question: *does high AI confidence actually predict correctness?*

| Confidence Tier | Cases | AI Correct | Accuracy |
|---|---|---|---|
| High (0.90-1.00) | — | — | — |
| Medium (0.70-0.89) | — | — | — |
| Low (0.50-0.69) | — | — | — |
| Very Low (0.00-0.49) | — | — | — |

### 3. Answer Distribution
Side-by-side comparison of what AI said vs what validators confirmed — detects systematic bias.

### 4. Trust Threshold Recommendation
Actionable guidance based on accuracy:
- **≥85%** → High confidence, ready for corpus-wide application
- **70-84%** → Moderate confidence, consider another round
- **<70%** → Low confidence, revise context and rerun

---

## 🔐 Authentication

### API Endpoints

| Method | Endpoint | Description | Access |
|--------|----------|-------------|--------|
| POST | `/auth/register` | Create new user | Public |
| POST | `/auth/login` | Get JWT token | Public |
| GET | `/auth/me` | Get current user | Authenticated |

### User Roles

- **Admin:** Create projects, upload data, assign scholars, manage system
- **Scholar:** Manage assigned projects, create modules, assign validators, review results
- **Validator:** Verify AI-generated analyses for assigned cases

### Test Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@cardozo.edu | admin12345 |
| Scholar | scholar1@cardozo.edu | scholar123 |
| Validator (TA1) | ta1@cardozo.edu | validator123 |
| Validator (TA2) | ta2@cardozo.edu | validator123 |

---

## 📁 Project Structure
```
us-court-decisions-analyzer/
├── backend/
│   ├── app/
│   │   ├── ingest/         # Capstone II: Word → Supabase + retrieve
│   │   ├── routers/        # Capstone I API endpoints
│   │   ├── core/           # Configuration (config.py)
│   │   ├── database.py     # SQLite connection (app only)
│   │   ├── models.py       # SQLAlchemy models (app only)
│   │   └── main.py         # FastAPI app
│   ├── data/               # pilot_50_manifest.json (no full opinion dump)
│   ├── tests/              # ingest QA tests (test_extract_qa.py)
│   ├── .env.example
│   └── requirements.txt
├── frontend/               # Capstone I React UI
├── supabase/migrations/    # ingest schema + RLS
├── current_docs/           # status PDFs, QA note (Word dump is gitignored)
└── README.md
```

---

## 🛠️ Development Workflow

### Common Commands

**Backend:**
```bash
# Start server
uvicorn app.main:app --reload --port 8000

# Reset database (wipes all data)
python init_db.py --drop
python init_db.py
python create_test_users.py

# Add new dependency
pip install package-name
pip freeze > requirements.txt

# Capstone II retrieve / ingest (does not start the web app)
./venv/bin/python -m app.ingest.load_supabase --query "..." --k 5
PYTHONPATH=. ./venv/bin/python -m unittest tests.test_extract_qa -v
```

**Frontend:**
```bash
# Start dev server
npm run dev

# Build for production
npm run build

# Add new dependency
npm install package-name
```

**Git:**
```bash
git status
git add .
git commit -m "feat: description"
git push
```

---

## 🔧 Team Setup Instructions

### For New Team Members

**1. Clone and Install**
```bash
git clone https://github.com/leanardiles/us-court-decisions-analyzer.git
cd us-court-decisions-analyzer
cd backend
python -m venv venv
source venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

**2. Get Your Groq API Key**
- Go to https://console.groq.com
- Sign up for a free account
- Navigate to API Keys
- Create a new API key
- Copy the key (starts with `gsk_`)

**3. Create Your .env File**
```bash
cd backend
cp .env.example .env
```

Edit `.env` and paste your API key:
```env
GROQ_API_KEY=gsk_paste_your_key_here
DATABASE_URL=sqlite:///./database.db
SECRET_KEY=your-secret-key-here
```

**4. Initialize Database**
```bash
python init_db.py
python create_test_users.py
```

**5. Start the App**
```bash
# Terminal 1: Backend
cd backend
source venv/Scripts/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

**6. Test It Works**
- Go to http://localhost:5173
- Login as `scholar1@cardozo.edu` / `scholar123`
- Create a module with Groq Llama 70B
- Launch it and verify AI analysis runs successfully

---

## 📈 Development Progress

**✅ Completed (Sessions 1-4)**
- [x] Complete authentication system with JWT
- [x] Database schema (13 tables)
- [x] Project management with Parquet upload
- [x] Role-based dashboards
- [x] Project lifecycle workflow
- [x] Scholar assignment

**✅ Completed (Days 1-3)**
- [x] Module creation with 5 answer types
- [x] Two-level context system (project + module)
- [x] Case sampling and validator assignment

**✅ Completed (Days 4-5)**
- [x] Mock AI analysis generation
- [x] Realistic dummy responses by answer type
- [x] Module status tracking

**✅ Completed (Days 6-7)**
- [x] Validator dashboard with progress tracking
- [x] Case-by-case validation interface
- [x] AI review with correct/incorrect decisions
- [x] Validation completion summary
- [x] UI polish and Cardozo branding

**✅ Completed (Day 8)**
- [x] Scholar review interface
- [x] Approve/reject corrections workflow
- [x] Trust Validator bulk approve
- [x] Feedback library integration
- [x] Dynamic button states

**✅ Completed (Day 8.5 - Mar 21, 2026)**
- [x] Groq Cloud API integration
- [x] Migration from Ollama to Groq for better team collaboration
- [x] AI provider selection dropdown (4 options: Dummy, 8B, 70B, 405B)
- [x] Real AI analysis with Llama models (cloud-hosted)
- [x] Environment variable management with .env
- [x] AI provider locked after first module creation
- [x] Per-case validator assignment (fixed case count bug)

**✅ Completed (Day 9 - Mar 23, 2026)**
- [x] Clone module with pre-populated form (name left blank)
- [x] Collapsed project context preview with view/edit modal
- [x] Module context preview with view/edit modal (locked after launch)
- [x] Module context field reordered in creation form
- [x] Module deletion with tiered confirmation based on status
- [x] Accurate validation status display (waiting / in progress / complete)
- [x] Enriched module assignment endpoint with completion and correction data
- [x] Alternating color backgrounds for module cards
- [x] Fixed project status update regardless of scholar/upload order
- [x] Fixed logout button across all pages
- [x] Fixed login without requiring page refresh
- [x] Fixed ai_provider missing from module form reset
- [x] Structured AI responses with real reasoning and confidence scoring
- [x] Anchored confidence scoring with evidence quality criteria
- [x] Fixed Groq API integration (expired key + tokens_used bug)
- [x] Updated Groq model names to current versions

**✅ Completed (Day 10 - Mar 29, 2026)**
- [x] Schema migration — added round tracking to module_case_samples, validator_assignments, validation_feedback
- [x] Submit All Validations — validator explicitly submits to trigger validation_complete status
- [x] Scholar notification on module card when validation complete
- [x] Module Detail Page — dedicated page for full module management
- [x] Simplified module cards on project page (name, status, question, View Module button)
- [x] Module Results Page with four analytics sections
- [x] Confidence calibration table (accuracy by confidence tier)
- [x] Answer distribution analysis (AI vs validator breakdown)
- [x] Trust threshold recommendation with actionable guidance
- [x] Validator Dashboard redesigned as accordion grouped by project
- [x] Project-level progress bar across all modules
- [x] Scholar email shown on validator dashboard
- [x] Various UI improvements (login page, button colors, context previews)

**🚧 Next Steps**
- [ ] New Round workflow (start-new-round endpoint + UI)
- [ ] Mark Module as Complete
- [ ] Full corpus AI application (apply to all cases after trust threshold reached)
- [ ] Demo preparation and final testing

**Progress: ~95% complete** 🎯

---

## 💰 Cost Analysis (Groq API)

### Free Tier Limits
- **Requests per day:** 14,400
- **Requests per minute:** 30
- **Tokens per minute:** 7,000

### Typical Usage
- **Average case:** ~500 tokens (input + output)
- **Module with 10 cases:** ~5,000 tokens
- **Daily capacity:** ~100 modules (far exceeds typical usage)

### Cost if Scaling Beyond Free Tier
- **Llama 3.1 8B:** $0.05 per million tokens (~$0.0003 per case)
- **Llama 3.3 70B:** $0.59 per million tokens (~$0.003 per case)
- **Llama 4 Maverick:** $0.50 per million tokens (~$0.0025 per case)

**Example:** Analyzing 1,000 cases with 70B = ~$3.00 total

---

## 🚀 Future Enhancement Ideas

### Module Management
- **Module templates** - Save frequently-used module configurations
- **Batch module creation** - Create multiple similar modules at once
- **Per-module AI provider** - Currently locked at project level; future versions may allow per-module selection for A/B testing
- **Inter-case consistency** - Analyze whether AI errors cluster by state, court, or date

### Multi-Validator Support
- **Multiple validators per module** - Assign 2+ validators independently
- **Inter-annotator agreement metrics** - Calculate Cohen's Kappa score
- **Disagreement resolution workflow** - Scholar reviews conflicting validations
- **Validator quality tracking** - Monitor individual accuracy over time

### Enhanced Document Viewing
- **MS Word preview for validators** - Visual document rendering during case review
- **Split-pane viewer** - Opinion text and validation form side-by-side
- **Annotation tools** - Highlight and annotate relevant passages

### Advanced AI Features
- **Multiple AI model comparison** - Run same cases through different models simultaneously
- **Additional API providers** - Add Claude (Anthropic) and GPT-4 (OpenAI)
- **Fine-tuned models** - Train custom Llama on approved corrections
- **Active learning** - Prioritize uncertain cases for human review
- **Error pattern detection** - Identify systematic biases in AI responses

### Workflow Enhancements
- **Email notifications** - Alert validators when new assignments arrive
- **Export functionality** - Download validated results as CSV/Excel/JSONL
- **Audit trail** - Complete history of changes
- **Project cloning** - Duplicate entire projects with all modules

### Research Features
- **Inter-coder reliability reports** - Statistical analysis of validator agreement
- **Confusion matrices** - Visualize AI error patterns by category
- **Model comparison reports** - Side-by-side accuracy for different AI providers
- **Publication-ready exports** - Tables and figures for academic papers

---

## 📚 Documentation

- **Capstone II ingest/retrieve:** [`backend/app/ingest/README.md`](backend/app/ingest/README.md)
- **Faculty status (5 Oct 2026):** `current_docs/Capstone_II_Status_Report_5_Oct_2026.pdf`
- **Database QA (6 Oct 2026):** `current_docs/database-qa-2026-10-06.md`
- **Alex handover:** `current_docs/Handover_Enock_to_Alex.pdf`
- **API Documentation (Capstone I app):** http://localhost:8000/docs
- **App schema (SQLite):** `backend/docs/DATABASE_SCHEMA.txt`
- **Groq API Docs:** https://console.groq.com/docs

---

## 🐛 Troubleshooting

### "No API key found - falling back to mock"
**Problem:** Groq API key not loaded  
**Solution:**
1. Check `.env` file exists in `backend/` directory
2. Verify `GROQ_API_KEY=gsk_...` is set (no quotes)
3. Restart backend server after editing `.env`
4. Check `main.py` has `load_dotenv()` at the top

### "403 Access Denied" from Groq API
**Problem:** API key expired or deleted  
**Solution:**
1. Go to https://console.groq.com/keys
2. Create a new API key
3. Update `GROQ_API_KEY` in your `.env` file
4. Save — backend will auto-reload

### "Generated by Groq Cloud API" showing as reasoning
**Problem:** Old hardcoded placeholder in database from before structured response parsing was implemented  
**Solution:** Delete the affected module and create a fresh one — existing database records won't update automatically

### "Invalid AI provider" error when creating second module
**Problem:** `ai_provider` gets wiped from form state after first module creation  
**Solution:** Ensure all three form reset locations in `ProjectDetailPage.jsx` include `ai_provider: selectedAIProvider`

### "Module uses dummy AI instead of Groq"
**Problem:** Project's default AI provider still set to old value  
**Solution:**
1. Create a new project (defaults to `groq-llama-70b`)
2. Or update existing project in database: `UPDATE projects SET ai_provider='groq-llama-70b' WHERE id=X;`

### Backend won't start / import errors
**Problem:** Missing dependencies  
**Solution:**
```bash
cd backend
source venv/Scripts/activate
pip install -r requirements.txt
```

### Frontend shows connection errors
**Problem:** Backend not running  
**Solution:**
1. Check backend is running on port 8000
2. Visit http://localhost:8000/docs to verify
3. Check CORS settings in `main.py`

### Database reset needed after schema changes
**Problem:** New columns added to models but database not updated  
**Solution:**
```bash
cd backend
source venv/Scripts/activate
python init_db.py --drop
python init_db.py
python create_test_users.py
```

---

## 🤝 Contributing

This is a capstone project for academic purposes. For questions or collaboration:
- **Leandro Ardiles** — repo, Capstone I app, Groq account — [GitHub](https://github.com/leanardiles)
- **Enock Katenda** — ingest, schema, retrieve
- **Alex Ji** — System B agents
- **Tafadzwa Nyemba** — Q1/Q2 ground truth
- **Course:** COM 6001 Capstone II, Katz School · Partner: Cardozo School of Law

---

## 📄 License

This project is developed as part of academic coursework at Yeshiva University.