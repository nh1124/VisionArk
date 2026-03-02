"""AI generation tools: image generation, mermaid diagrams, code execution."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import (
    fail,
    get_api_key,
    get_gemini_client,
    get_project_id,
    get_user_id,
    make_result,
    resolve_artifacts_dir,
    resolve_reference_image,
)
from shared.paths import get_project_dir


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------

def _new_conversation_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    h = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
    return f"imgconv_{ts}_{h}"


def _conv_path(images_dir: Path, conv_id: str) -> Path:
    d = images_dir / "_conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{conv_id}.json"


def _load_conversation(images_dir: Path, conv_id: str) -> dict | None:
    p = _conv_path(images_dir, conv_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_conversation(images_dir: Path, conv_id: str, state: dict) -> None:
    p = _conv_path(images_dir, conv_id)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

async def _resolve_provider(ctx: ExecutionContext, hint: str) -> tuple[str, str]:
    """Return (provider, api_key).  Raises ValueError when no key is available."""
    if hint == "anthropic":
        raise ValueError("Anthropic does not support image generation.")

    if hint == "gemini":
        key = await get_api_key(ctx, "gemini")
        if not key:
            raise ValueError("Gemini API key not configured.")
        return "gemini", key

    if hint == "openai":
        key = await get_api_key(ctx, "openai")
        if not key:
            raise ValueError("OpenAI API key not configured.")
        return "openai", key

    # "auto" — Gemini first, then OpenAI
    gemini_key = await get_api_key(ctx, "gemini")
    if gemini_key:
        return "gemini", gemini_key
    openai_key = await get_api_key(ctx, "openai")
    if openai_key:
        return "openai", openai_key
    raise ValueError("No image-generation API key configured (need Gemini or OpenAI key).")


# ---------------------------------------------------------------------------
# Filename helper
# ---------------------------------------------------------------------------

def _make_filename(prefix: str | None, prompt: str, idx: int, ext: str) -> str:
    h = hashlib.md5(prompt.encode()).hexdigest()[:8]
    base = prefix if prefix else f"gen_{h}"
    suffix = f"_{idx}" if idx > 0 else ""
    return f"{base}{suffix}.{ext}"


# ---------------------------------------------------------------------------
# Gemini generation
# ---------------------------------------------------------------------------

_GEMINI_IMAGE_MODELS = [
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]


async def _generate_gemini(
    ctx: ExecutionContext,
    api_key: str,
    prompt: str,
    negative_prompt: str | None,
    reference_images: list[dict],
    prev_output_paths: list[str],
    size: str,
    n: int,
    filename_prefix: str | None,
    images_dir: Path,
    root_dir: Path,
) -> tuple[list[dict], list[str], str]:
    """Call Gemini image model and save images.  Returns (outputs, warnings, model_used).

    Tries models in _GEMINI_IMAGE_MODELS order, falling back on 404.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    full_prompt = prompt
    if negative_prompt:
        full_prompt += f"\n\nDo NOT include: {negative_prompt}"

    # Build content parts
    parts: list[Any] = [types.Part.from_text(text=full_prompt)]

    user_id = get_user_id(ctx)
    project_id = get_project_id(ctx)
    warnings: list[str] = []

    for ref in reference_images:
        ref_path = ref.get("path", "")
        try:
            data, mime = resolve_reference_image(ref_path, user_id, project_id)
            parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        except (ValueError, FileNotFoundError) as e:
            warnings.append(f"Skipped reference image '{ref_path}': {e}")

    # Inject previous conversation outputs as additional references
    for prev_path in prev_output_paths:
        try:
            data, mime = resolve_reference_image(prev_path, user_id, project_id)
            parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        except Exception as e:
            warnings.append(f"Could not load previous output '{prev_path}': {e}")

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )

    # Start with the first model; fall back to later entries on 404.
    active_model: str = _GEMINI_IMAGE_MODELS[0]

    outputs: list[dict] = []
    for i in range(n):
        model_to_use = active_model
        image_data = None
        while True:
            try:
                response = client.models.generate_content(
                    model=model_to_use,
                    contents=parts,
                    config=config,
                )
                for part in response.parts:
                    if part.inline_data is not None:
                        image_data = part.inline_data.data
                        break
                if not image_data:
                    warnings.append(f"Iteration {i + 1}: No image returned by Gemini ({model_to_use}).")
                break

            except Exception as e:
                err_str = str(e)
                current_idx = _GEMINI_IMAGE_MODELS.index(model_to_use)
                has_fallback = current_idx < len(_GEMINI_IMAGE_MODELS) - 1
                if ("404" in err_str or "NOT_FOUND" in err_str) and has_fallback:
                    model_to_use = _GEMINI_IMAGE_MODELS[current_idx + 1]
                    active_model = model_to_use  # persist for remaining iterations
                    warnings.append(f"Model '{_GEMINI_IMAGE_MODELS[current_idx]}' not found; retrying with '{model_to_use}'.")
                    continue
                warnings.append(f"Iteration {i + 1} failed: {e}")
                break

        if image_data is None:
            continue

        image_bytes = base64.b64decode(image_data) if isinstance(image_data, str) else image_data
        filename = _make_filename(filename_prefix, prompt, i, "png")
        file_path = images_dir / filename
        file_path.write_bytes(image_bytes)

        rel_path = file_path.relative_to(root_dir).as_posix()
        outputs.append({
            "path": rel_path,
            "mime_type": "image/png",
        })

    return outputs, warnings, active_model


# ---------------------------------------------------------------------------
# OpenAI generation
# ---------------------------------------------------------------------------

def _process_openai_response(resp: Any, images_dir: Path, root_dir: Path, prompt: str, filename_prefix: str | None) -> list[dict]:
    outputs = []
    for i, item in enumerate(resp.data):
        if hasattr(item, "b64_json") and item.b64_json:
            image_bytes = base64.b64decode(item.b64_json)
        elif hasattr(item, "url") and item.url:
            import urllib.request
            with urllib.request.urlopen(item.url) as r:  # noqa: S310
                image_bytes = r.read()
        else:
            continue

        filename = _make_filename(filename_prefix, prompt, i, "png")
        file_path = images_dir / filename
        file_path.write_bytes(image_bytes)
        rel_path = file_path.relative_to(root_dir).as_posix()
        outputs.append({"path": rel_path, "mime_type": "image/png"})
    return outputs


async def _generate_openai(
    ctx: ExecutionContext,
    api_key: str,
    prompt: str,
    reference_images: list[dict],
    prev_output_paths: list[str],
    size: str,
    quality: str,
    n: int,
    filename_prefix: str | None,
    images_dir: Path,
    root_dir: Path,
) -> tuple[list[dict], list[str]]:
    """Call OpenAI gpt-image-1 and save images.  Returns (outputs, warnings)."""
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)
    oai_quality = "high" if quality == "high" else "medium"
    warnings: list[str] = []

    user_id = get_user_id(ctx)
    project_id = get_project_id(ctx)

    # Collect reference image bytes (first one only for edit endpoint)
    ref_bytes: bytes | None = None
    for ref in reference_images:
        ref_path = ref.get("path", "")
        try:
            data, _ = resolve_reference_image(ref_path, user_id, project_id)
            ref_bytes = data
            break
        except (ValueError, FileNotFoundError) as e:
            warnings.append(f"Skipped reference image '{ref_path}': {e}")

    if len(reference_images) > 1:
        warnings.append("OpenAI edit endpoint supports only one reference image; using the first valid one.")

    # Check if we have any reference image (from args or previous conversation)
    if ref_bytes is None and prev_output_paths:
        try:
            ref_bytes, _ = resolve_reference_image(prev_output_paths[-1], user_id, project_id)
        except Exception as e:
            warnings.append(f"Could not load previous output for edit: {e}")

    use_edit = ref_bytes is not None

    outputs: list[dict] = []
    if use_edit:
        # Edit endpoint: one at a time
        for i in range(n):
            try:
                resp = await client.images.edit(
                    model="gpt-image-1",
                    image=io.BytesIO(ref_bytes),
                    prompt=prompt,
                    n=1,
                    size=size,
                )
                outputs.extend(_process_openai_response(resp, images_dir, root_dir, prompt, filename_prefix))
            except Exception as e:
                warnings.append(f"Edit iteration {i + 1} failed: {e}")
    else:
        try:
            resp = await client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                n=n,
                size=size,
                quality=oai_quality,
            )
            outputs.extend(_process_openai_response(resp, images_dir, root_dir, prompt, filename_prefix))
        except Exception as e:
            warnings.append(f"Generation failed: {e}")

    return outputs, warnings


# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------

class GenerateImageTool:
    definition = ToolDef(
        name="generate_image",
        description=(
            "Generate or edit images from text prompts. Supports multiple providers "
            "(Gemini / OpenAI), reference images, and multi-turn editing via conversation_id. "
            "Returns a JSON envelope with provider, model, saved file paths, and warnings."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate.",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "Elements to exclude from the image (Gemini only).",
                },
                "reference_images": {
                    "type": "array",
                    "description": "Project-relative paths to reference images with optional role/weight.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "role": {"type": "string", "enum": ["style", "composition", "subject"]},
                            "weight": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["path"],
                    },
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1024x1536", "1536x1024"],
                    "description": "Output image dimensions. Defaults to 1024x1024.",
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "high"],
                    "description": "Generation quality. Defaults to standard.",
                },
                "n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "description": "Number of images to generate (1–4). Defaults to 1.",
                },
                "filename_prefix": {
                    "type": "string",
                    "description": "Prefix for saved filenames. Auto-generated if omitted.",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Resume a previous image conversation (enables iterative editing).",
                },
                "edit_instruction": {
                    "type": "string",
                    "description": "Editing instruction when continuing a conversation.",
                },
                "provider_hint": {
                    "type": "string",
                    "enum": ["auto", "gemini", "openai", "anthropic"],
                    "description": "Force a specific provider. Defaults to auto.",
                },
            },
            "required": ["prompt"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        args = call.arguments
        prompt: str = args.get("prompt", "")
        negative_prompt: str | None = args.get("negative_prompt")
        reference_images: list[dict] = args.get("reference_images") or []
        size: str = args.get("size", "1024x1024")
        quality: str = args.get("quality", "standard")
        n: int = int(args.get("n", 1))
        filename_prefix: str | None = args.get("filename_prefix")
        conversation_id: str | None = args.get("conversation_id")
        edit_instruction: str | None = args.get("edit_instruction")
        provider_hint: str = args.get("provider_hint", "auto")

        try:
            # Prepare images directory
            artifacts_dir = await resolve_artifacts_dir(ctx)
            images_dir = artifacts_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            root_dir = get_project_dir(get_user_id(ctx), get_project_id(ctx))

            # Load existing conversation if requested
            conv_state: dict | None = None
            prev_output_paths: list[str] = []
            if conversation_id:
                conv_state = _load_conversation(images_dir, conversation_id)
                if conv_state:
                    prev_output_paths = conv_state.get("last_outputs", [])
                    # Inherit provider preference from conversation
                    if provider_hint == "auto" and conv_state.get("provider"):
                        provider_hint = conv_state["provider"]

            # Resolve provider
            provider, api_key = await _resolve_provider(ctx, provider_hint)

            # Use edit_instruction as prompt when continuing a conversation
            effective_prompt = edit_instruction if (conv_state and edit_instruction) else prompt

            # Generate
            if provider == "gemini":
                outputs, warnings, model = await _generate_gemini(
                    ctx, api_key, effective_prompt, negative_prompt,
                    reference_images, prev_output_paths, size, n,
                    filename_prefix, images_dir, root_dir,
                )
            else:
                outputs, warnings = await _generate_openai(
                    ctx, api_key, effective_prompt,
                    reference_images, prev_output_paths, size, quality, n,
                    filename_prefix, images_dir, root_dir,
                )
                model = "gpt-image-1"

            if not outputs:
                return fail(call, "Image generation produced no outputs. " + "; ".join(warnings))

            # Persist conversation state
            new_conv_id = conversation_id or _new_conversation_id()
            _save_conversation(images_dir, new_conv_id, {
                "provider": provider,
                "model": model,
                "last_outputs": [o["path"] for o in outputs],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

            envelope = {
                "success": True,
                "provider": provider,
                "model": model,
                "conversation_id": new_conv_id,
                "outputs": outputs,
                "warnings": warnings,
            }
            return make_result(call, json.dumps(envelope, indent=2))

        except Exception as e:
            return fail(call, f"Image generation failed: {e}")


# ---------------------------------------------------------------------------
# Unchanged tools
# ---------------------------------------------------------------------------

class MermaidVisualizerTool:
    definition = ToolDef(
        name="generate_mermaid_visualizer",
        description=(
            "Create a Mermaid diagram and save as markdown artifact. "
            "HOW TO USE: generate_mermaid_visualizer(diagram_type=\"flowchart\", data=\"A --> B\", title=\"Flow\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Mermaid diagram data"},
                "diagram_type": {"type": "string", "description": "Diagram type: gantt, flowchart, sequence, class"},
                "title": {"type": "string", "description": "Title for the artifact"},
            },
            "required": ["data"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        data = call.arguments.get("data", "")
        diagram_type = call.arguments.get("diagram_type", "flowchart")
        title = call.arguments.get("title", "Diagram")

        content = f"```mermaid\n{diagram_type}\n{data}\n```"

        from domains.orchestration2.tools.library.files import SaveArtifactTool

        save_call = ToolCallRef(
            tool_name="save_artifact",
            call_id=call.call_id,
            arguments={"file_path": f"visuals/{title}.md", "content": content, "overwrite": True},
        )
        saver = SaveArtifactTool()
        return await saver.invoke(save_call, ctx)


class ExecuteCodeTool:
    definition = ToolDef(
        name="execute_code",
        description=(
            "Execute Python code or perform complex calculations via Gemini. "
            "HOW TO USE: execute_code(prompt=\"Calculate standard deviation of [1, 5, 10, 20]\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Code or logic to execute"},
            },
            "required": ["prompt"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        prompt = call.arguments.get("prompt", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(code_execution=types.ToolCodeExecution())]
                ),
            )
            return make_result(call, resp.text or "No output from code execution")
        except Exception as e:
            return fail(call, f"Code execution failed: {e}")
