# Agent Chat File Access Issue Report

## 1. Existing Processing Flow Confirmation

Based on the investigation of the logs and codebase, the current flow for file handling in chat is:

1.  **File Upload**:
    *   User uploads a file via the Frontend.
    *   `POST /api/files/project/{id}/upload` is called.
    *   `FileService` saves the file to the shared volume (`/app/data/users/.../projects/.../refs/`).
    *   Database record (`UploadedFile`) is created.

2.  **Chat Request**:
    *   User sends a message referencing the file.
    *   `atmos-backend` enqueues a task for `atmos-worker`.

3.  **Agent Execution (Worker)**:
    *   The Agent (LLM) decides to check for files.
    *   Agent calls tool `list_files` to discover available files.
    *   Agent attempts to use `read_reference` if files are found.

## 2. Analysis of the Cause

The failure occurs at the **Agent Execution** step.

*   **Symptom**: The Agent calls `list_files` but repeatedly gets the root directory listing instead of the target subdirectory (e.g., `refs/`), or fails to find files it expects.
*   **Root Cause**: **Parameter Mismatch**.
    *   The `ListFilesTool` is defined to accept a parameter named `directory`.
    *   However, the Agent is calling the tool with the argument `path` (e.g., `{"path": "refs"}`).
    *   The tool implementation in `files.py` only looks for `directory`. When it's missing, it defaults to `""` (root).
    *   As a result, `list_files(path="refs")` behaves like `list_files(directory="")`, listing the root folder. The Agent sees `[dir] refs/` in the output and gets confused, thinking it looked inside `refs` and found nothing (or a nested `refs` folder).

**Evidence from Logs**:
```json
Step 3
list_files
Success
 {"path":"refs"}
[dir] refs/
```
If the tool had correctly listed `refs/`, it would show the files inside it. Instead, it listed the root, which contains the `refs` folder itself.

## 3. Improvement Proposal

To fix this issue and prevent recurrence, I propose the following improvements:

### A. Robust Tool Argument Handling (Immediate Fix)
Modify `ListFilesTool` (and potentially `ReadReferenceTool`) in `core/backend/domains/orchestration2/tools/library/files.py` to accept common aliases for parameters.
*   **ListFilesTool**: Accept `path` as a fallback for `directory`.
*   **ReadReferenceTool**: Accept `path` as a fallback for `file_path`.

### B. Definition Update
Review the Tool Definition string to ensure it aligns with the Agent's training or system prompt instructions. However, making the code robust is safer than relying on the LLM to strictly follow the parameter name "directory".

### C. Logging Enhancements
Add a warning log when unknown arguments are passed to tools, to make debugging easier in the future.

## 4. Deep Diagnosis of Agent Confusion

The user asked: "Why did the agent get confused?"
The confusion stems from a **Silent Failure** mechanism in the tool implementation combined with **Strong Prior Bias** in the LLM.

1.  **Strong Prior Bias**:
    *   The LLM (Gemini/Claude) is trained on vast amounts of code where file listing functions (like `os.listdir`, `ls`) typically accept a `path` argument.
    *   Despite the Tool Definition explicitly specifying `directory`, the model's training bias led it to hallucinate the parameter name `path`. Note that `read_reference` uses `file_path`, potentially contributing to the mix-up.

2.  **Silent Failure (The Trap)**:
    *   The `ListFilesTool.invoke` method interprets arguments loosely:
        ```python
        directory = call.arguments.get("directory", "")
        ```
    *   When the agent sent `{"path": "refs"}`, `directory` became `""` (the default).
    *   The tool **did not error**. Instead, it successfully listed the **root directory**.

3.  **The Cognitive Feedback Loop**:
    *   **Agent Expectation**: "I am listing content of `refs/`."
    *   **Tool Reality**: "I am listing content of `root`."
    *   **Output**: `[dir] refs/`, `[file] README.md`, etc.
    *   **Agent Interpretation**: The agent sees `[dir] refs/` in the output.
        *   *Scenario A*: It thinks "Oh, `refs` is empty" (if it ignored the fact that it's seeing the folder itself).
        *   *Scenario B*: It thinks "I am looking at the parent directory, let me try to go into refs" (loop).
        *   In this case, the agent likely concluded "I can't see the *files* I uploaded inside refs" because the output didn't show the *contents* of refs, only the folder entry itself.

**Conclusion**: The lack of strict argument validation caused the tool to do "something valid but wrong" instead of throwing an error. If the tool had returned `Error: Unknown argument 'path'. Did you mean 'directory'?`, the agent would have self-corrected immediately.

## 5. Next Steps (Action Plan)

1.  Update `core/backend/domains/orchestration2/tools/library/files.py`.
2.  Modify `ListFilesTool.invoke` to handle `path` argument.
3.  Modify `ReadReferenceTool.invoke` to handle `path` argument (preventative).
