<![CDATA[# RxTract Frontend

> A modern, accessible React SPA for the RxTract platform — prescription analysis, RAG-powered document Q&A, and semantic search.

---

## ✨ Features

| Page | Description |
|------|-------------|
| **Prescription Analysis** | Upload prescription images, get real-time OCR analysis with medicine matching via SSE progress streaming |
| **Chat** | RAG Q&A — ask questions and get AI-generated answers grounded in your indexed documents |
| **Search** | Semantic search across all indexed documents with relevance scoring |
| **Upload & Process** | Upload documents (PDF, TXT, MD, JSON, CSV, DOCX), configure chunking parameters, and index to vector DB |
| **Login / Register** | JWT-based authentication with email verification |
| **Settings** | Configure API URL and application preferences |

---

## 🛠️ Tech Stack

| Technology | Purpose |
|------------|---------|
| **React 18** | Component library with hooks |
| **TypeScript** | Type-safe codebase |
| **Vite** | Fast build tool with HMR |
| **Tailwind CSS** | Utility-first styling |
| **React Router v6** | Client-side routing with protected routes |
| **TanStack Query** | Server state management and caching |
| **Zustand** | Client state management (auth, settings) |
| **React Aria Components** | Accessible UI primitives (WAI-ARIA compliant) |
| **Heroicons** | SVG icon library |

---

## 🚀 Getting Started

### Prerequisites
- **Node.js** 18+ and **pnpm**
- Running RxTract API backend (see [root README](../README.md))

### Quick Start

```bash
# Install dependencies
pnpm install

# Start development server
pnpm dev
```

The dev server runs at **http://localhost:5777** with hot module replacement.

> **Tip:** Use `bash dev.sh` from the project root to start both backend and frontend simultaneously.

### Environment Variables

Create a `.env` file (optional — defaults work for local development):

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | RxTract API base URL | `http://localhost:8000/api/v1` |

### Build for Production

```bash
pnpm build
```

Output is generated in the `dist/` directory, ready to be served by Nginx or any static file server.

### Docker

```bash
docker build -t rxtract-frontend .
docker run -p 80:80 rxtract-frontend
```

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── api/                # API client modules
│   │   ├── base.ts         # Health check and base client config
│   │   ├── data.ts         # File upload, processing, asset management
│   │   ├── nlp.ts          # Vector search, indexing, RAG Q&A
│   │   ├── prescription.ts # OCR analysis with SSE streaming
│   │   └── auth.ts         # Login, register, email verification
│   ├── components/
│   │   ├── ui/             # Reusable UI primitives (Button, StatusBadge, Card, etc.)
│   │   ├── layout/         # App layout (Sidebar with mobile responsiveness)
│   │   └── features/       # Feature-specific components
│   ├── pages/
│   │   ├── PrescriptionPage.tsx   # OCR analysis with real-time progress bar
│   │   ├── ChatPage.tsx           # RAG document Q&A
│   │   ├── SearchPage.tsx         # Semantic search
│   │   ├── UploadPage.tsx         # Document upload & processing workflow
│   │   ├── IndexInfoPage.tsx      # Vector DB statistics dashboard
│   │   ├── LoginPage.tsx          # User authentication
│   │   ├── RegisterPage.tsx       # Account creation
│   │   ├── VerifyEmailPage.tsx    # Email verification flow
│   │   ├── LearningAssistantChatPage.tsx  # AI learning assistant
│   │   ├── LearningBooksAdminPage.tsx     # Learning corpus management
│   │   └── SettingsPage.tsx       # Application settings
│   ├── stores/
│   │   ├── authStore.ts    # JWT token + user state (persisted)
│   │   └── settingsStore.ts # API URL + preferences (persisted)
│   └── utils/              # Shared utility functions
├── public/                 # Static assets
├── index.html              # App shell
├── vite.config.ts          # Vite configuration
├── tailwind.config.js      # Tailwind CSS theme
└── tsconfig.json           # TypeScript configuration
```

---

## 🔌 API Integration

The frontend communicates with the RxTract API. All data routes require JWT authentication.

### Authentication Flow
```
Register → Verify Email → Login → Store JWT → Attach to all API requests
```

### Core API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/` | Health check | ❌ |
| `POST` | `/auth/register` | Create account | ❌ |
| `POST` | `/auth/login` | Get JWT token | ❌ |
| `GET` | `/auth/verify-email` | Verify email address | ❌ |
| `POST` | `/data/upload/{project_id}` | Upload files | ✅ |
| `POST` | `/data/process/{project_id}` | Process into chunks | ✅ |
| `POST` | `/nlp/index/push/{project_id}` | Index to vector DB | ✅ |
| `GET` | `/nlp/index/info/{project_id}` | Get index statistics | ✅ |
| `POST` | `/nlp/index/search/{project_id}` | Semantic search | ✅ |
| `POST` | `/nlp/index/answer/{project_id}` | RAG Q&A | ✅ |
| `POST` | `/prescription/analyze` | Analyze prescription (SSE) | ✅ |

---

## 📱 Responsive Design

The frontend is fully responsive with:
- **Mobile sidebar**: Hamburger menu with backdrop overlay
- **Adaptive layouts**: Components reflow for small screens
- **Touch-friendly**: Appropriately sized tap targets

---

## 📝 License

Same as the main RxTract project — Apache License 2.0.
]]>
