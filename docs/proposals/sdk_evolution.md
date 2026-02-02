# Proposal: VisionArk SDK Evolution

This report outlines a strategic roadmap to evolve the current integration development system into a more robust, type-safe, and developer-friendly SDK.

## 1. Current Limitations (The "DX" Gap)

While the current Vertical Integration Pattern is effective for small projects, it has several scalability and developer experience (DX) issues:

- **Implicit Context (`**kwargs`)**: Developers must "know" that `user_id` and `db_session` are available. There is no IDE completion or type safety.
- **Scattered Logic**: Handlers must be manually imported in `__init__.py`. Discovery relies on string-based name matching.
- **High Setup Friction**: Configuring `ServiceRegistry` and `manifest.json` correctly is a multi-step manual process prone to error.
- **Tight Coupling**: Integrations depend directly on the core's internal data models, making breaking changes in the core dangerous for all integrations.

## 2. Proposed Improvements

### A. Type-Safe Integration Context
Replace string-based dictionary access with a dedicated, typed context object.
```python
# From: async def run(self, query: str, **kwargs)
# To:
async def run(self, query: str, ctx: IntegrationContext) -> ToolResult:
    user = await ctx.get_user()
    db = ctx.db
```

### B. Class-Based Lifecycle Management
Encapsulate the entire integration (tools, handlers, manifest) into a single class. This allows the SDK to manage registration and state more cleanly.

### C. Automated Dependency Injection
Automatically prepare and inject initialized API clients or service configurations based on the `manifest.json`, so the developer doesn't have to write credential-fetching boilerplate.

### D. Integration CLI (Scaffolder)
A tool to generate the correct folder structure, boilerplate code, and perform validation checks on the `manifest.json`.

## 3. Implementation Roadmap

| Phase | Focus | Impact |
| :--- | :--- | :--- |
| **P0: Refine** | `IntegrationContext` implementation. | Immediate type safety improve. |
| **P1: Decouple** | Extract `va_sdk` into a standalone library. | Modular architecture. |
| **P2: Automate** | CLI/Scaffolder and DI for API clients. | Radical reduction in boilerplate. |

## 4. Strategic Recommendation: "Update now or defer?"

> [!IMPORTANT]
> **Conclusion: Defer full rewrite until the number of integrations exceeds 10.**

### Rationale for Deferring:
1. **Current Scale**: With only a few integrations (Google Calendar, LINE, etc.), the overhead of a major SDK rewrite outweighs the benefits.
2. **"Copy-Paste" DX**: The current "copy an existing integration" workflow is actually quite effective for small teams.
3. **API Stability**: The core architecture (Reasoning Engine, Node flow) is still evolving. Locking down an SDK now might create legacy baggage too early.

### Signs to Start Updating:
- When you plan to allow **third-party developers** (outside the core team) to build integrations.
- When you find yourself spending more than 30% of integration development time on **debugging "context missing" or "auth setup" issues**.
- When the `va_sdk` folder needs to be shared across multiple backend repositories.

---
> [!TIP]
> **Compromise**: Implement the `IntegrationContext` object *now* as a small refactor without changing the entire architecture. This provides 80% of the DX benefit with 20% of the effort.
