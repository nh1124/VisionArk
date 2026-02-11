# Project Directory Structure

## Overview
VisionArk follows a **Domain-Driven Design (DDD)** architecture, emphasizing a clear separation between business logic (`domains`), technical implementation (`infrastructure`), and application entry points (`app`).

## Root Directory (`VisionArk/`)
*   `assets/`: Centralized storage for prompts, skills, and roles.
*   `core/`: Core application source code.
    *   `backend/`: Python FastAPI backend.
    *   `frontend/`: Next.js frontend.
*   `va_sdk/`: Shared Python SDK for external integrations and plugins.
*   `integrations/`: External integration modules (LBS, Calendar, etc.) containing both backend logic and frontend manifests.
*   `docs/`: Project documentation.

## Backend Structure (`core/backend/`)

### 1. Application Layer (`app/`)
Contains the application entry points and configuration.
*   `main.py`: FastAPI application entry point, router inclusion, and startup logic.
*   `worker.py`: Background task worker (Celery/dict-queue) for async operations.
*   `config.py`: Environment configuration and settings.

### 2. Domain Layer (`domains/`)
Contains the core business logic, organized by domain. High-level policies reside here.
*   **`identity/`**: User authentication, profile management, and service synchronization.
*   **`knowledge/`**: RAG system, Vector Store interaction, file processing (PDF/Notes).
*   **`workspace/`**: File management, Context management, Notifications.
*   **`automation/`**: AES (Automated Execution System), Scheduler, Skill System, Commands.
*   **`orchestration/`**: Agent orchestration, routing, chat projection, and **Tools** (Standard Library).

### 3. Infrastructure Layer (`infrastructure/`)
Contains technical implementations and interfaces to external systems.
*   **`llm/`**: LLM Provider implementations (Gemini, VertexAI, etc.).
*   **`queue/`**: Task queue implementation.

### 4. Shared Kernel (`shared/`)
Contains code shared across all layers, with no domain-specific logic.
*   `database.py`: Database models and connection logic.
*   `security.py`: Hashing and encryption utilities.
*   `jwt.py`: Token management.
*   `paths.py`: Path resolution helpers.

## Key Design Decisions
*   **Externalization**: `va_sdk` and `integrations` are kept at the project root to allow them to be shared or developed independently of the core backend.
*   **Asset Centralization**: All "soft code" (prompts, skills) are in `assets/` to allow for easy editing without backend redeployment.
*   **Domain Isolation**: Services are grouped by business capability rather than technical function (e.g., no monolithic `services/` folder).
