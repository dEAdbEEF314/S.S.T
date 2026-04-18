# Frontend Implementation Specification: SST Dashboard

## Overview
Detailed plan for building the React-based frontend for the S.S.T Dashboard. The frontend will reside in `ui/frontend/` and be served by the FastAPI backend.

## Technical Stack
- **Framework**: React 18 (Vite)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui (Radix UI based)
- **Icons**: Lucide React
- **Data Fetching**: TanStack Query (React Query) v5
- **Routing**: React Router DOM v6

## Directory Structure
```
ui/frontend/
├── src/
│   ├── components/       # Reusable shadcn/ui components
│   │   ├── dashboard/    # Stats cards, system health
│   │   ├── pipeline/     # Data table for flow runs
│   │   ├── llm/          # Chat interface components
│   │   └── ui/           # Raw shadcn/ui primitives
│   ├── hooks/            # Custom hooks for API fetching
│   ├── lib/              # Utils (cn, formatters)
│   ├── pages/            # Page-level components
│   ├── App.tsx           # Layout and Routing
│   └── main.tsx
├── tailwind.config.js
└── vite.config.ts
```

## Core Components Detail

### 1. Dashboard (Home)
- **StatsGrid**: 4 cards showing counts for Scanned, Processing, Archive, and Review.
- **SystemHealth**: Indicator lights for S3, Prefect, and LLM connectivity.

### 2. Pipeline Table
- Uses `shadcn/ui` table with automatic polling every 5 seconds.
- **Badge mapping**: Maps Prefect states to colored badges.
- **App ID link**: Clickable ID to filter LLM logs or view Archive details.

### 3. LLM Chat Viewer
- **ChatWindow**: A scrollable area with "System", "User", and "Assistant" bubbles.
- **Markdown Rendering**: Support for formatted AI responses.
- **Language Support**: Uses `Noto Sans JP` font stack to ensure Japanese characters are rendered perfectly.

## Localization & Internationalization (i18n)
- **Zero-Corruption Policy**: All data displayed is treated as UTF-8. No manual escaping of Japanese strings.
- **Font Priority**: `Inter, "Noto Sans JP", sans-serif`.
- **UI Labels**: Initial version will have UI labels in English with metadata (Album names, Chat logs) displayed in the configured language (Japanese).

## Build & Deployment
1. Vite builds the project into `ui/frontend/dist/`.
2. FastAPI (`ui/src/ui/main.py`) mounts the `dist` directory to serve the SPA.
3. Dockerfile for `ui` will be updated to include Node.js build stage (multi-stage build).

## Implementation Steps (Phase 4)
1. Initialize Vite project in `ui/frontend`.
2. Install Tailwind CSS and initialize shadcn/ui.
3. Implement basic layout with a sidebar (Dashboard, Pipeline, Logs, Archive, Review).
4. Create the API client layer using Axios/Fetch with TanStack Query.
5. Build individual pages starting with Dashboard.
