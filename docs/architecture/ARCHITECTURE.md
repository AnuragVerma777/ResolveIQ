# ResolveIQ — Architecture & System Workflow Specifications

This document details the complete system architecture, data flow, integration boundaries, and end-to-end dispute resolution workflow for **ResolveIQ**.

---

## 1. System Architecture Diagram

```mermaid
flowchart TD
    %% Styling
    classDef client fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef backend fill:#1e293b,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef service fill:#090d16,stroke:#3b82f6,stroke-width:1.5px,color:#cbd5e1;
    classDef external fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f3e8ff;
    classDef devtool fill:#27272a,stroke:#71717a,stroke-width:2px,stroke-dasharray: 5 5,color:#a1a1aa;

    %% Subgraph Developer Tooling (Completely Out-of-Band)
    subgraph DevEnvironment["🛠️ Developer Engineering Environment (Offline / Out-of-Band)"]
        direction TB
        DevCursor["👨‍💻 IDE / Cursor / Codex"]
        PayPalAIToolkit["🧰 PayPal AI Toolkit (paypal/AI-Toolkit)<br/>• MCP Server Plugin<br/>• OpenAPI Schema Exploration<br/>• Prototype Dispute Fixtures"]
        DevCursor <-->|"Local MCP JSON-RPC"| PayPalAIToolkit
    end

    %% Client Layer
    subgraph FrontendApp["🖥️ Client Presentation Layer (React + Vite + Tailwind)"]
        direction TB
        UI["ResolveIQ Web Application<br/>(SPA on Vercel / Static Mount)"]
        subgraph Views["Interactive Modules"]
            V1["PayPal Live Hub<br/>(Dispute Command Center)"]
            V2["Dispute Investigation<br/>(Intake & Evidence Ingestion)"]
            V3["Evidence Intelligence<br/>(Evidence Matrix & Completeness Score)"]
            V4["Resolution Studio<br/>(Grounded AI Rebuttal Editor)"]
            V5["Automation Settings<br/>(Zapier Webhooks & Deliveries)"]
        end
        UI --> Views
    end

    %% Backend Layer
    subgraph BackendApp["⚡ Backend Intelligence Engine (FastAPI + Python 3.11)"]
        direction TB
        API["FastAPI Gateway (/api)"]
        SecurityMW["Security Middleware<br/>• 25MB Body Size Limiter<br/>• CORS Strict Origin Allowlist<br/>• Atomic Submission Mutex Lock"]

        subgraph CoreServices["Internal Core Subsystems"]
            DocProc["📄 Document Processor<br/>• PyMuPDF (native vector text)<br/>• python-docx (Word documents)<br/>• Tesseract OCR fallback<br/>• Magic byte MIME validation"]
            EvidenceEngine["⚖️ Evidence Intelligence Engine<br/>• Rule-based claim grounding<br/>• Contradiction detection<br/>• Explainable completeness scoring"]
            AuditSubsys["🔒 Audit Trail Subsystem<br/>• Immutable action ledger<br/>• Cryptographic SHA-256 hashes"]
        end

        API --> SecurityMW
        SecurityMW --> CoreServices
    end

    %% Storage Layer
    subgraph DataLayer["💾 Persistence Layer"]
        DB[("SQLite Database<br/>• WAL Mode<br/>• Foreign Key Enforced<br/>• Auto-migrating Schema")]
        Storage[("Encrypted File Vault<br/>• /uploads directory<br/>• Sanitized safe filenames")]
    end

    %% External Cloud Integrations
    subgraph ExternalServices["🌐 External Production Integrations"]
        GeminiCloud["✨ Google Gemini API<br/>(gemini-2.5-flash / Pro)<br/>• Zero-shot document extraction<br/>• Strict JSON schema grounding<br/>• Rebuttal generation with citations"]
        PayPalLiveAPI["💳 PayPal REST APIs<br/>(api-m.sandbox.paypal.com)<br/>• OAuth2 Token lifecycle & cache<br/>• GET /v1/customer/disputes<br/>• POST /v1/customer/disputes/{id}/provide-evidence"]
        ZapierCatch["⚡ Zapier Webhook Gateway<br/>(hooks.zapier.com)<br/>• Real-time dispute alerts<br/>• Missing evidence notifications<br/>• Submission receipt dispatch"]
    end

    %% Runtime Connections
    Views -->|"REST / JSON over HTTPS"| API

    CoreServices -->|"Query & Transact"| DB
    DocProc -->|"Store & Read Files"| Storage

    CoreServices -->|"REST Client (backend/paypal/client.py)"| PayPalLiveAPI
    CoreServices -->|"Structured LLM Prompts"| GeminiCloud
    CoreServices -->|"HTTP Dispatch (Backoff & Retry)"| ZapierCatch

    %% Dev Tool Note Link
    DevEnvironment -.->|"Code Generation & API Specs<br/>(Design Time Only — Zero Runtime Impact)"| BackendApp

    class UI,Views,V1,V2,V3,V4,V5 client;
    class API,SecurityMW,CoreServices,DocProc,EvidenceEngine,AuditSubsys backend;
    class DB,Storage service;
    class GeminiCloud,PayPalLiveAPI,ZapierCatch external;
    class DevEnvironment,DevCursor,PayPalAIToolkit devtool;
```

---

## 2. End-to-End Dispute Resolution Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Merchant as Merchant / Claims Specialist
    participant UI as ResolveIQ Frontend (React)
    participant API as FastAPI Backend Engine
    participant DocEngine as Document Processor & OCR
    participant AI as Gemini 2.5 Flash
    participant PayPal as PayPal Sandbox REST API
    participant Zapier as Zapier Webhooks

    Note over Merchant, PayPal: Phase 1: Ingestion & Pre-Flight Verification
    Merchant->>UI: Select dispute (e.g. PP-D-849201 - INR / SNAD / Fraud)
    UI->>API: GET /api/paypal/disputes/{id}
    API->>PayPal: GET /v1/customer/disputes/{id}
    PayPal-->>API: 200 OK (Dispute details, buyer claim, response deadline)
    API->>API: Pre-flight check (status == UNDER_REVIEW, deadline valid, actions allow PROVIDE_EVIDENCE)
    API-->>UI: Pre-flight approved & dispute loaded

    Note over Merchant, AI: Phase 2: Document Processing & Evidence Extraction
    Merchant->>UI: Upload Proof of Delivery (PDF) & Tax Invoice (DOCX/PNG)
    UI->>API: POST /api/documents/upload
    API->>DocEngine: Extract text (PyMuPDF / docx / OCR) + detect MIME
    DocEngine-->>API: Raw extracted text & metadata
    API->>AI: Extract structured facts (carrier, tracking, recipient, delivery date)
    AI-->>API: JSON entity payload
    API->>API: Persist document record & audit entry
    API-->>UI: Upload verified & entities displayed

    Note over Merchant, AI: Phase 3: Evidence Grounding & Completeness Scoring
    UI->>API: POST /api/disputes/{id}/classify-and-match
    API->>API: Categorize dispute & determine evidentiary policy
    API->>API: Evidence Intelligence (evaluate tracking, match buyer address, detect contradictions)
    API->>API: Calculate Explainable Completeness Score (0-100%)
    API-->>UI: Return match matrix, completeness breakdown, missing warnings

    Note over Merchant, AI: Phase 4: Resolution Studio & Rebuttal Generation
    UI->>API: POST /api/disputes/{id}/generate-response
    API->>AI: Generate professional rebuttal using ONLY verified facts + doc references
    AI-->>API: Structured response with claim citations
    API->>API: Verify citation grounding (reject any hallucinated claims)
    API-->>UI: Editable rebuttal draft with cited evidence tags

    Note over Merchant, Zapier: Phase 5: Merchant Review & Explicit Approval
    Merchant->>UI: Review claims, optionally edit text, verify attachments
    Merchant->>UI: Click "Explicitly Approve & Sign Response"
    UI->>API: POST /api/disputes/{id}/resolution/{resp_id}/approve
    API->>API: Set status = APPROVED, timestamp approval in immutable audit log
    API-->>UI: Approval confirmed

    Note over Merchant, Zapier: Phase 6: Submission & Automated Notification
    Merchant->>UI: Click "Submit Evidence to PayPal"
    UI->>API: POST /api/disputes/{id}/resolution/{resp_id}/submit
    API->>API: Acquire submission mutex lock (prevent duplicate submissions)
    API->>PayPal: POST /v1/customer/disputes/{id}/provide-evidence
    PayPal-->>API: 200 OK (evidence acknowledged)
    API->>API: Record submission outcome & update dispute state
    API->>Zapier: POST dispute.submitted webhook event
    Zapier-->>API: 200 OK (event queued in automation flow)
    API->>API: Release mutex lock & commit audit log
    API-->>UI: Submission receipt & Zapier delivery confirmed
    UI-->>Merchant: Display real submission status & confirmation badge
```
