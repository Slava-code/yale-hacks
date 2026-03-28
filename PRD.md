# MedGate — Product Requirements Document

**Author:** [Team Name]
**Date:** 2026-03-28
**Status:** Draft
**Version:** 1.0
**Context:** Hackathon project built on the GX10 hardware platform

---

## 1. Problem Statement

Healthcare institutions cannot use state-of-the-art cloud AI models (Claude, GPT-4, Gemini) for clinical workflows because sending Protected Health Information (PHI) to cloud APIs violates HIPAA. The compliance infrastructure required to make this legal — de-identification pipelines, audit logging, BAAs, re-identification systems — is so expensive and complex that most hospitals simply don't use AI at all.

Meanwhile, clinicians are buried in patient records, lab results, and visit histories spread across documents. A physician evaluating a patient with a complex multi-year history has to manually dig through dozens of files to piece together the clinical picture. AI could do this in seconds — summarize histories, suggest differential diagnoses, flag drug interactions — but the privacy barrier makes it inaccessible.

Existing approaches fall into two camps, both inadequate:

- **Fully on-premise LLMs:** Run open-source models locally. No cloud dependency, but model quality is significantly below frontier models (Claude, GPT-4). Requires expensive GPU infrastructure and ML expertise that hospitals don't have.
- **Cloud AI with BAAs:** Use cloud models with Business Associate Agreements. Better model quality, but BAAs don't solve the core problem — PHI still leaves the hospital's perimeter, creating ongoing liability. Configuration is complex, and a single misconfiguration can trigger a breach.

MedGate takes a third approach: **keep PHI on-premises, send only de-identified data to the cloud, and re-hydrate responses locally.** The compliance layer is hardware, not software. The hospital gets frontier-model intelligence with zero PHI exposure.

## 2. Goals & Objectives

1. **[P0]** Build a local AI gatekeeper running on the GX10 that intercepts all user queries, strips PHI, and replaces identifiers with ephemeral tokens before anything reaches a cloud model
2. **[P0]** Build a clinical knowledge graph from pre-processed PDF documents stored on the GX10, with entity extraction, relationship mapping, and source document + page-level links preserved per node
3. **[P0]** Deliver a chat interface where clinicians query naturally (using real patient names), with all privacy handling invisible to the user
4. **[P0]** Implement multi-turn gatekeeper queries — the cloud model can call back to the gatekeeper as many times as needed to gather sufficient clinical context before producing a final answer
5. **[P0]** Re-hydrate cloud model responses by swapping tokens back to real identifiers, and convert opaque reference tokens (e.g., `[REF_1]`) into clickable citations that open the source PDF at the correct page
6. **[P0]** Build a 3D interactive knowledge graph visualization with real-time traversal path highlighting, clickable nodes with info cards, and source PDF viewing from nodes
7. **[P0]** Demonstrate model agnosticism — same query, same privacy guarantee, switchable between Claude, GPT-4, and Gemini mid-session
8. **[P0]** Prepare a demo-ready prototype with ~300 synthetic clinical PDF documents across 30–40 fictional patients, pre-processed into the knowledge graph
9. **[P1]** Ingestion animation that visually simulates the document processing pipeline during the demo presentation
10. **[P1]** Show gatekeeper thought process — a secondary view displaying the gatekeeper's internal reasoning, what queries it receives from the cloud model, what it retrieves, and what it redacts

## 3. Target Users

### Clinician (Physician / Nurse)
- **Who they are:** Healthcare professionals who interact with patient records daily and need AI assistance for diagnosis, record review, and treatment planning
- **Key pain point:** Cannot use cloud AI tools with patient data due to HIPAA restrictions; manually searches through patient histories across many documents
- **What they need:** An AI assistant they can talk to naturally (mentioning patients by name) that pulls from the institution's full clinical knowledge base, with zero compliance burden on the clinician

### Hospital IT / CISO
- **Who they are:** Technical decision-makers responsible for the institution's security posture and HIPAA compliance
- **Key pain point:** Every new AI tool is a compliance risk; evaluating and approving cloud AI solutions requires extensive legal and technical review
- **What they need:** A hardware appliance that solves the compliance problem architecturally — PHI stays on-prem by design, not by configuration. Something they can approve once and deploy without ongoing compliance overhead for the AI layer

### Hackathon Judges (immediate audience)
- **Who they are:** Technical evaluators assessing the project's innovation, feasibility, and execution
- **What they need to see:** A working demo that clearly shows the privacy architecture in action — what the user types, what the cloud model sees (redacted), and what comes back (re-hydrated). The 3D knowledge graph and multi-model switching are the visual differentiators

## 4. User Stories & Use Cases

### Core Flows (P0)

> **As a** clinician, **I want to** ask "What's the history for John Smith? He's been coming in with headaches and fatigue," **so that** I get a full clinical summary — and the cloud AI never sees John Smith's name.

> **As a** clinician, **I want to** see citations in the AI's response that link to the exact page of the original clinical document, **so that** I can verify the information and read the full context.

> **As a** clinician, **I want** the AI to automatically ask the gatekeeper for more information when it needs it (lab results, family history, medication list), **so that** I get a thorough answer without having to manually feed it context.

> **As a** clinician, **I want to** see the 3D knowledge graph light up along the retrieval path as the AI gathers information, **so that** I can understand which parts of the patient's record are being accessed.

> **As a** clinician, **I want to** click on a node in the knowledge graph and see its contents (patient summary, visit details, lab results) and optionally open the source PDF, **so that** I can browse clinical data visually.

> **As a** hospital IT lead watching the demo, **I want to** see a side-by-side view of what the clinician typed versus what the cloud model received, **so that** I can verify that PHI is genuinely stripped before it leaves the device.

> **As a** hospital IT lead, **I want to** see the same query routed to different AI providers (Claude, GPT-4, Gemini) with identical privacy guarantees, **so that** I know the institution isn't locked into a single vendor.

### Important Flows (P1)

> **As a** demo presenter, **I want** an ingestion animation that shows PDF documents being processed into the knowledge graph, **so that** the audience understands how the system is set up at an institution.

> **As a** hackathon judge, **I want to** see the gatekeeper's internal thought process (what queries it receives, what it retrieves, what it redacts), **so that** I can evaluate the technical depth of the architecture.

## 5. Scope

### In Scope (Hackathon Prototype)

- **Local AI Gatekeeper:** A model running on the GX10's NPU that intercepts user queries, performs de-identification (token replacement for all 18 HIPAA identifiers), serves as a queryable knowledge base for cloud models, and re-hydrates responses with real identifiers and clickable citations. The gatekeeper is instructed via system prompt on its role and response format; the cloud model is similarly instructed on how to query the gatekeeper and handle tokens.

- **Clinical Knowledge Graph:** Pre-processed from ~300 synthetic clinical PDFs. Entities include patients, conditions, medications, procedures, lab results, visits, and providers. Relationships are edges (PATIENT→HAS_CONDITION, VISIT→RESULTED_IN→LAB_RESULT, PATIENT→PRESCRIBED→MEDICATION, etc.). Each node stores its source PDF path and page number for citation linking. Graph is stored on the GX10's local storage and loaded into memory at startup.

- **Citation System:** Facts returned by the gatekeeper include opaque reference tokens (e.g., `[REF_1]`, `[REF_2]`). Each token maps to a specific source document and page, but the cloud model sees only the token — it cannot infer which document, which page, or any structural information about the corpus. The cloud model passes these tokens through in its response. During re-hydration, the GX10 resolves each token to its source (e.g., `[REF_1]` → `discharge_summary_john_smith.pdf, page 3`) and converts them to clickable links. Clicking a citation opens the source PDF at the referenced page in a viewer that overlays the main interface.

- **3D Knowledge Graph Visualization:** Interactive force-directed 3D graph rendered alongside the chat panel. Nodes are color-coded by entity type (patients, conditions, medications, visits, etc.). Edges show relationships. Features: rotate/zoom, click nodes to see info cards, click to open source PDF (overlays the graph, close to return), real-time traversal path highlighting (nodes and edges pulse/illuminate as the gatekeeper accesses them during a query). Built with Three.js / 3d-force-graph or similar.

- **Chat Interface (Custom Frontend):** A custom-built chat UI — not a third-party client. This is critical because the frontend must route all user queries to the GX10 gatekeeper first, before anything reaches a cloud API. The interface shows the clinician's conversation on the left, the knowledge graph on the right. The frontend also handles re-hydrated response rendering with clickable citation links.

- **Redacted View / Gatekeeper View (Secondary Display):** A separate view (second monitor, split screen, or toggle) showing: (a) the de-identified version of every message sent to the cloud model, (b) the cloud model's queries back to the gatekeeper, (c) the gatekeeper's redacted responses. This is the "proof" panel that makes the privacy architecture visible.

- **Model Switching:** A dropdown or toggle in the frontend that switches between cloud AI providers (Claude, GPT-4, Gemini). Each provider receives identically de-identified payloads. The system prompt and tool interface adapt per provider's API format (Claude XML tool calling, OpenAI function calling, Gemini's format) through a thin adapter layer. Switching is possible mid-session.

- **Ephemeral Token Mapping:** For each user interaction, the gatekeeper generates random, non-derivable tokens for all detected PHI. The mapping (token ↔ real identifier) exists only in the GX10's memory for the duration of the interaction. After the re-hydrated response is delivered to the user, the mapping is destroyed. A new mapping is generated for the next query. Tokens are never transmitted — only the gatekeeper knows the mapping.

- **De-Identification Rules:**

  | Stripped (Replaced with Tokens) | Preserved (Sent to Cloud) |
  |---|---|
  | Patient names | Age (except 90+) |
  | Medical record numbers (MRNs) | Sex / gender |
  | Social Security numbers | Diagnoses and conditions |
  | Specific dates (converted to relative) | Symptoms and chief complaints |
  | Addresses and locations | Lab results and vitals |
  | Phone numbers, emails, URLs | Medications and dosages |
  | Family member and provider names | Procedures and treatment plans |
  | Device and vehicle identifiers | Relative temporal relationships |

- **Mock Demo Data:** ~300 synthetic clinical PDF documents across 30–40 fictional patients. Document types include discharge summaries, progress notes, lab reports, imaging reports, and referral letters. Patient histories vary in complexity — some patients have 2–3 documents, others have 20+. Documents are generated using Claude/GPT-4 with realistic clinical language, then converted to PDF. No real patient or institution names. The knowledge graph is pre-built offline from these documents, with all nodes, edges, and source links ready at demo time. Estimated graph size: 1,000–2,000 nodes, several thousand edges.

- **Ingestion Animation:** A visual animation played during the demo presentation that simulates the document ingestion process — PDFs appearing, being "processed," and nodes/edges materializing in the knowledge graph. This represents the one-time setup that would occur when MedGate is deployed at an institution. The actual graph is pre-computed; the animation is presentational.

- **Demo Scenario:** A differential diagnosis workflow. A clinician queries about a patient with a complex multi-visit history (recurring symptoms over months that individually seem minor but together point to a specific condition). The demo shows: (1) the ingestion animation, (2) the user's raw query with patient name, (3) the redacted version sent to the cloud, (4) the cloud model querying the gatekeeper 2–4 times for additional context (with graph traversal lighting up), (5) the re-hydrated response with the patient's real name and clickable citations, (6) clicking a citation to view the source PDF, (7) model switching to show the same privacy guarantee across providers.

### Out of Scope (Hackathon)

- **Real-time document ingestion** — Documents are pre-processed offline. Live PDF ingestion during the demo is simulated with an animation. A production version would support incremental ingestion as new documents appear.
- **Role-based access control** — No per-user access restrictions for the prototype. All users see the same knowledge graph. Production would support role-based data granularity (nurse vs. physician vs. researcher).
- **Immutable audit logging** — No compliance-grade logging for the prototype. Production would log every query, mapping event, gatekeeper response, and re-hydration for auditing.
- **Real-time NER on arbitrary free text** — The prototype relies on the pre-built knowledge graph having PHI already tagged at construction time. User prompt de-identification is handled by the gatekeeper model via its system prompt instructions, not a dedicated NER pipeline. Production would add a dedicated NER model trained on clinical text.
- **EHR integration** — No direct connection to Epic, Cerner, or other EHR systems. Documents are manually placed on the device. Production would support HL7 FHIR, DICOM metadata, and direct EHR exports.
- **Secure enclave / TPM for mapping keys** — Ephemeral mappings are held in regular memory. Production would use hardware-backed secure storage.
- **Expert Determination validation** — No formal statistical analysis of re-identification risk. The prototype follows Safe Harbor method conceptually. Production would involve a qualified expert per 164.514(b)(1).
- **Character-level citation highlighting** — Citations link to the page level. Highlighting the exact text region on the page is a post-prototype enhancement. Source page numbers are stored from day one so no re-processing is needed.

### Future Considerations

- Dedicated NER pipeline (clinical NER model) for real-time de-identification of arbitrary unstructured text, catching identifiers that the gatekeeper's LLM-based approach might miss (family member names, landmarks, institutional references in clinical narratives)
- EHR integration with automated knowledge graph updates from live clinical data streams
- Incremental ingestion — automatic detection and processing of new documents
- Role-based access control with different data granularity per clinical role
- Immutable, tamper-proof audit logging for compliance auditing
- Hardware-backed secure enclave for ephemeral mapping keys
- Expert Determination pathway for formal re-identification risk quantification
- Surrogation mode (replacing identifiers with realistic fake values instead of tokens) for use cases where natural-sounding text improves model reasoning
- Multi-institution deployment — separate knowledge graphs per institution with shared compliance infrastructure
- Patient-facing mode — a restricted interface where patients can query their own records through the same privacy architecture

## 6. The GX10 Hardware Platform

MedGate runs on the **ASUS Ascent GX10**, a compact on-premises AI supercomputer powered by the **NVIDIA GB10 Grace Blackwell Superchip**:

- **NVIDIA Blackwell GPU:** 6,144 CUDA cores, 5th-gen Tensor Cores, up to **1 petaFLOP (1,000 TOPS)** at FP4 precision. This is a full data-center-class GPU, not a low-power NPU — it runs 13B–27B parameter gatekeeper models at ~11-17 tokens/sec (solo-loaded, Q4 quantization).
- **128 GB Unified LPDDR5x Memory:** Shared between the Grace CPU and Blackwell GPU in a single address space (like Apple Silicon). Runs the gatekeeper model (~18-20GB), maintains the knowledge graph in memory, and holds ephemeral token mappings during active sessions. All simultaneously, with >100GB headroom.
- **1 TB Local Storage:** Stores source PDF documents, the pre-processed knowledge graph, model weights, and (in production) audit logs. Supports hundreds of thousands of clinical documents for a typical institution.
- **20-core ARM Grace CPU:** 10x Cortex-X925 + 10x Cortex-A725 cores. Handles the FastAPI backend server, token management, and graph traversal — freeing the GPU entirely for model inference.

**Deployment model:** The GX10 is installed on-site within the hospital's physical infrastructure. The hospital owns the device. It becomes part of their IT environment like an EHR server or imaging system. PHI never leaves the premises. What reaches the cloud is de-identified data that is no longer PHI under HIPAA's Privacy Rule.

## 7. Compliance Architecture

MedGate's compliance design is grounded in HIPAA's de-identification standard, 45 CFR 164.514:

- **164.514(b) — Safe Harbor De-Identification:** All 18 HIPAA-specified identifiers are removed from data before it leaves the GX10. De-identified data is no longer PHI under the Privacy Rule.
- **164.514(c) — Re-Identification Codes:** HIPAA permits assigning a code to allow re-identification, provided: (1) the code is not derived from the individual's information, (2) the code cannot be reverse-engineered to identify the individual, (3) the re-identification mechanism is not disclosed. MedGate's ephemeral token mapping satisfies all three — tokens are randomly generated, the mapping never leaves the device, and it is destroyed after each interaction.

**Implication:** Because de-identified data is not PHI, cloud AI providers do not need to sign a BAA for the AI queries themselves. The institution retains full control over their data, their mapping keys, and their compliance posture.

**Note:** The hackathon prototype demonstrates this architecture conceptually. Production deployment would require formal compliance validation, audit logging, and potentially Expert Determination analysis. The prototype is designed so that all production compliance features can be added without re-architecting — the privacy boundary (PHI stays on GX10, only de-identified data exits) is structural, not configurable.

## 8. Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOSPITAL PREMISES                            │
│                                                                     │
│  ┌──────────┐     ┌──────────────────────────────────────────────┐  │
│  │ Clinician │────▶│                  GX10                        │  │
│  │ (Browser) │◀────│                                              │  │
│  └──────────┘     │  1. Receive raw query (with PHI)             │  │
│       ▲           │  2. Strip PHI → generate token mapping       │  │
│       │           │  3. Forward sanitized query to cloud ────────│──│──▶ Cloud AI
│       │           │  4. Receive cloud queries for more context   │◀─│──  (Claude/
│       │           │  5. Traverse knowledge graph                 │  │    GPT-4/
│       │           │  6. Return redacted info + citation refs ────│──│──▶ Gemini)
│       │           │  7. Receive final response from cloud  ◀─────│──│──
│       │           │  8. Re-hydrate tokens → real identifiers     │  │
│       │           │  9. Convert citation tokens → clickable links│  │
│       │           │  10. Destroy mapping                         │  │
│       │           │  11. Return response to clinician             │  │
│       │           └──────────────────────────────────────────────┘  │
│       │                          │                                  │
│       │                    ┌─────┴─────┐                            │
│       │                    │ Knowledge │                            │
│       │                    │   Graph   │                            │
│       │                    │ (1TB SSD) │                            │
│       └────────────────────│ + Source  │                            │
│         (clickable links   │   PDFs    │                            │
│          open source docs) └───────────┘                            │
│                                                                     │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ PRIVACY BOUNDARY ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│  Nothing above this line contains PHI when it exits the GX10.       │
└─────────────────────────────────────────────────────────────────────┘
```

## 9. Demo Layout

```
┌─────────────────────────────────┬─────────────────────────────────┐
│                                 │                                 │
│     CLINICIAN CHAT VIEW         │     3D KNOWLEDGE GRAPH          │
│                                 │                                 │
│  User: "Tell me about John      │     ○ Patient nodes (blue)      │
│  Smith, he's been having         │     ○ Condition nodes (red)     │
│  headaches and joint pain        │     ○ Medication nodes (green)  │
│  for 8 months..."               │     ○ Visit nodes (yellow)      │
│                                 │     ○ Lab result nodes (purple)  │
│  AI: "Based on John Smith's     │                                 │
│  clinical history, the           │     Traversal path lights up    │
│  recurring headaches,           │     as gatekeeper retrieves      │
│  joint pain, and abnormal       │     information.                 │
│  ANA results [Lab Report, p2]    │                                 │
│  suggest evaluation for          │     Click node → info card      │
│  systemic lupus..."             │     Click "View PDF" → opens     │
│                                 │     source document over graph   │
│  [Claude ▼] [GPT-4] [Gemini]   │                                 │
│                                 │                                 │
└─────────────────────────────────┴─────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  SECONDARY DISPLAY — REDACTED VIEW (what cloud model sees)        │
│                                                                   │
│  → User query (redacted): "[PATIENT_1], presenting with           │
│    headaches and joint pain for 8 months..."                      │
│  → Cloud model asks gatekeeper: "Lab results for [PATIENT_1]?"   │
│  → Gatekeeper returns: "ANA positive [REF_1],                    │
│    ESR elevated [REF_2], CBC within normal [REF_3]"              │
│  → Cloud model asks: "Family history for [PATIENT_1]?"           │
│  → Gatekeeper returns: "Mother: [CONDITION_1] [REF_4]"           │
│  → Final response (redacted): "[PATIENT_1] should be             │
│    evaluated for systemic lupus erythematosus..."                 │
└───────────────────────────────────────────────────────────────────┘
```

## 10. Key Features Summary

| Feature | Description | Priority |
|---|---|---|
| **Local AI Gatekeeper** | On-device model that de-identifies queries, retrieves clinical knowledge, and re-hydrates responses. All PHI processing happens locally on the Blackwell GPU. | P0 |
| **Clinical Knowledge Graph** | Pre-processed structured graph of clinical entities and relationships, stored on-device. Each node links to source PDF + page number. | P0 |
| **Citation System** | Facts carry opaque reference tokens (`[REF_1]`, `[REF_2]`) through the cloud model — no document names, no page numbers, no corpus structure leaked. Re-hydration resolves tokens to clickable links that open the source PDF at the correct page. | P0 |
| **3D Graph Visualization** | Interactive force-directed 3D graph with color-coded nodes, clickable info cards, source PDF viewing, and real-time traversal path highlighting. | P0 |
| **Ephemeral Token Mapping** | Random non-derivable tokens replace PHI per session. Mapping lives only in memory, destroyed after re-hydration. | P0 |
| **Model Agnosticism** | Switchable between Claude, GPT-4, Gemini mid-session. Same privacy guarantee regardless of provider. | P0 |
| **Multi-Turn Gatekeeper Queries** | Cloud models query the gatekeeper as many times as needed for sufficient clinical context. | P0 |
| **Custom Chat Frontend** | Routes all queries through GX10 first. Renders re-hydrated responses with clickable citations. | P0 |
| **Redacted View** | Secondary display showing de-identified messages, gatekeeper queries, and internal reasoning. | P0 |
| **Mock Demo Data** | ~300 synthetic clinical PDFs, 30–40 patients, pre-processed into knowledge graph with source links. | P0 |
| **Ingestion Animation** | Visual simulation of the document processing pipeline during demo presentation. | P1 |
| **Gatekeeper Thought Process View** | Display of gatekeeper's internal reasoning in the secondary view. | P1 |

---

*This document is the source of truth for the MedGate hackathon project. All team members and coding agents should reference this document for product requirements, architectural decisions, and scope boundaries. Last updated: 2026-03-28*.
