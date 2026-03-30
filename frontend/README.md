# RxTract Frontend

> A modern, accessible React SPA for the RxTract platform -- prescription analysis, RAG-powered document Q&A, and semantic search.

---

## Features

| Page | Route | Description |
|------|-------|-------------|
| Chat | `/` | RAG Q&A -- ask questions and get AI-generated answers grounded in your indexed documents |
| Search | `/search` | Semantic search across all indexed documents with relevance scoring |
| Prescription Analysis | `/prescription` | Upload prescription images, get real-time OCR analysis with OpenCV image preprocessing and intelligent medicine candidate suggestions via SSE streaming, then chat about results |
| Login | `/login` | JWT-based authentication |
| Register | `/register` | Account creation with email verification |
| Verify Email | `/verify-email` | Email verification flow |

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 19 | Component library with hooks |
| TypeScript | Type-safe codebase |
| Vite | Fast build tool with HMR |
| Tailwind CSS 4 | Utility-first styling |
| React Router v7 | Client-side routing with protected routes |
| TanStack Query | Server state management and caching |
| Zustand | Client state management (auth, settings, quota, toast) |
| Axios | HTTP client with interceptors |
| React Aria Components | Accessible UI primitives (WAI-ARIA compliant) |
| react-markdown | Markdown rendering for chat responses |
| Heroicons | SVG icon library |

---

## Getting Started

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

Create a `.env` file (optional -- defaults work for local development):

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | RxTract API base URL | `http://localhost:8001/api/v1` |

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

## Project Structure

```
frontend/
├── src/
│   ├── api/                  # API client modules
│   │   ├── base.ts           # Health check and base client config
│   │   ├── client.ts         # Shared Axios instance with JWT interceptors
│   │   ├── types.ts          # TypeScript type definitions for API responses
│   │   ├── auth.ts           # Login, register, email verification, resend
│   │   ├── data.ts           # File upload, processing, asset management
│   │   ├── nlp.ts            # Vector search, indexing, RAG Q&A
│   │   └── prescription.ts   # OCR analysis with SSE streaming, prescription chat
│   ├── components/
│   │   ├── ui/               # Reusable UI primitives
│   │   │   ├── Logo.tsx      # SVG logo component
│   │   │   ├── QuotaPanel.tsx    # Daily usage quota bars
│   │   │   └── ToastContainer.tsx # Auto-dismissing toast notifications
│   │   └── layout/           # App layout (Sidebar, MainLayout)
│   ├── pages/
│   │   ├── ChatPage.tsx            # RAG document Q&A
│   │   ├── SearchPage.tsx          # Semantic search
│   │   ├── PrescriptionPage.tsx    # OCR analysis with real-time progress + chat
│   │   ├── LoginPage.tsx           # User authentication
│   │   ├── RegisterPage.tsx        # Account creation
│   │   └── VerifyEmailPage.tsx     # Email verification
│   ├── stores/
│   │   ├── authStore.ts      # JWT token + user state (persisted)
│   │   ├── settingsStore.ts  # API URL + preferences (persisted)
│   │   ├── quotaStore.ts     # Daily usage tracking (queries, prescriptions)
│   │   └── toastStore.ts     # Toast notification state (error, warning, info)
│   └── utils/                # Shared utility functions
├── public/                   # Static assets
├── index.html                # App shell
├── vite.config.ts            # Vite configuration
└── tsconfig.json             # TypeScript configuration
```

---

## API Integration

The frontend communicates with the RxTract API via Axios. All data routes require JWT authentication.

### Authentication Flow

```
Register -> Verify Email -> Login -> Store JWT -> Attach to all API requests
```

### Core API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/health` | Health check | No |
| `POST` | `/api/v1/auth/register` | Create account | No |
| `POST` | `/api/v1/auth/login` | Get JWT token | No |
| `GET` | `/api/v1/auth/verify?token=...` | Verify email address | No |
| `POST` | `/api/v1/auth/resend-verification` | Resend verification email | No |
| `POST` | `/api/v1/data/upload/{project_id}` | Upload files | Yes |
| `POST` | `/api/v1/data/process/{project_id}` | Process into chunks | Yes |
| `DELETE` | `/api/v1/data/asset/{project_id}/{file_id}` | Delete single asset | Yes |
| `DELETE` | `/api/v1/data/project/{project_id}/assets` | Delete all project assets | Yes |
| `POST` | `/api/v1/nlp/index/push/{project_id}` | Index to vector DB | Yes |
| `GET` | `/api/v1/nlp/index/info/{project_id}` | Get index statistics | Yes |
| `POST` | `/api/v1/nlp/index/search/{project_id}` | Semantic search | Yes |
| `POST` | `/api/v1/nlp/index/answer/{project_id}` | RAG Q&A | Yes |
| `POST` | `/api/v1/prescription/analyze` | Analyze prescription (JSON) | Yes |
| `POST` | `/api/v1/prescription/analyze-stream` | Analyze prescription (SSE) | Yes |
| `POST` | `/api/v1/prescription/chat` | Chat about prescription results | Yes |
| `GET` | `/api/v1/quota/status` | Get daily usage quota status | Yes |

---

## Responsive Design

The frontend is fully responsive with:

- **Mobile sidebar**: Hamburger menu with backdrop overlay
- **Adaptive layouts**: Components reflow for small screens
- **Touch-friendly**: Appropriately sized tap targets

---

## License

Same as the main RxTract project -- see [LICENCE](../LICENCE).
