#!/usr/bin/env python3
"""Generate Meta and Google ad creatives with Gemini into structured folders."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from jsonschema import ValidationError, validate


SYSTEM_INSTRUCTIONS = """
You are an expert paid media creative strategist for Meta and Google Ads.
Return ONLY valid JSON (no markdown code fences).
You must comply with the provided schema and platform constraints.
Do not fabricate compliance approvals. Note uncertainties explicitly.
""".strip()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "untitled"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path | None) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8")


@dataclass
class GenerationResult:
    platform: str
    campaign_name: str
    group_name: str
    index: int
    output_dir: Path
    schema_valid: bool
    error: str | None


def build_prompt(
    platform: str,
    brief: dict[str, Any],
    schema: dict[str, Any],
    docs_context: str,
    creative_index: int,
) -> str:
    return (
        f"Platform: {platform}\n"
        f"Creative number: {creative_index}\n\n"
        "Use the input brief and produce one hyper-detailed ad creative JSON object.\n"
        "Output MUST match the provided JSON schema at minimum required fields.\n"
        "Include realistic, policy-conscious copy.\n\n"
        "=== Curated Gemini / policy context ===\n"
        f"{docs_context}\n\n"
        "=== Input brief JSON ===\n"
        f"{json.dumps(brief, indent=2)}\n\n"
        "=== Required output schema (JSON Schema) ===\n"
        f"{json.dumps(schema, indent=2)}\n"
    )


def safe_json_parse(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return json.loads(stripped)


def generate_one(
    client: genai.Client,
    model: str,
    prompt: str,
    response_schema: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        response_mime_type="application/json",
        temperature=0.7,
        top_p=0.95,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    text = response.text or ""
    parsed = safe_json_parse(text)
    validate(instance=parsed, schema=response_schema)
    return parsed, text


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set.")

    brief_path = Path(args.brief)
    schema_path = Path(args.schema)
    docs_context_path = Path(args.docs_context) if args.docs_context else None

    brief = read_json(brief_path)
    schema = read_json(schema_path)
    docs_context = read_text(docs_context_path)

    platforms = ["meta", "google"] if args.platform == "both" else [args.platform]
    count_per_platform = int(
        brief.get("creative_requirements", {}).get("count_per_platform", args.count_per_platform)
    )

    stamp = utc_stamp()
    run_dir = Path(args.output_dir) / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=api_key)
    manifest: dict[str, Any] = {
        "run_id": stamp,
        "model": args.model,
        "brief_path": str(brief_path),
        "schema_path": str(schema_path),
        "docs_context_path": str(docs_context_path) if docs_context_path else None,
        "results": [],
    }

    for platform in platforms:
        for index in range(1, count_per_platform + 1):
            campaign_name = f"{brief.get('project', {}).get('name', 'campaign')} {platform}"
            audience_name = brief.get("audiences", [{}])[0].get("name", "default audience")
            group_name = audience_name if platform == "meta" else f"{audience_name} adgroup"

            campaign_slug = slugify(campaign_name)
            group_prefix = "adset" if platform == "meta" else "adgroup"
            group_slug = slugify(group_name)
            creative_dir = (
                run_dir
                / platform
                / f"campaign_{campaign_slug}"
                / f"{group_prefix}_{group_slug}"
                / f"creative_{index:03d}"
            )
            creative_dir.mkdir(parents=True, exist_ok=True)

            prompt = build_prompt(platform, brief, schema, docs_context, index)
            write_json(creative_dir / "brief.json", brief)
            (creative_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

            result = GenerationResult(
                platform=platform,
                campaign_name=campaign_name,
                group_name=group_name,
                index=index,
                output_dir=creative_dir,
                schema_valid=False,
                error=None,
            )

            try:
                generated, raw_text = generate_one(client, args.model, prompt, schema)
                write_json(creative_dir / "creative.json", generated)
                (creative_dir / "response_raw.txt").write_text(raw_text, encoding="utf-8")
                result.schema_valid = True
            except (ValidationError, json.JSONDecodeError, Exception) as exc:
                result.error = str(exc)
                (creative_dir / "response_raw.txt").write_text(str(exc), encoding="utf-8")

            manifest["results"].append(
                {
                    "platform": result.platform,
                    "campaign_name": result.campaign_name,
                    "group_name": result.group_name,
                    "index": result.index,
                    "output_dir": str(result.output_dir),
                    "schema_valid": result.schema_valid,
                    "error": result.error,
                }
            )

    write_json(run_dir / "run_manifest.json", manifest)
    print(f"Completed. Output: {run_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, help="Path to brief JSON")
    parser.add_argument(
        "--platform",
        choices=["meta", "google", "both"],
        default="both",
        help="Platform to generate creatives for",
    )
    parser.add_argument("--model", default="gemini-2.5-pro", help="Gemini model name")
    parser.add_argument(
        "--schema",
        default="schemas/creative.schema.json",
        help="Path to JSON schema for output validation",
    )
    parser.add_argument(
        "--docs-context",
        default="docs/gemini_context.md",
        help="Optional path to curated Gemini/policy context",
    )
    parser.add_argument(
        "--output-dir",
        default="runs",
        help="Base output directory where timestamped run folders are created",
    )
    parser.add_argument(
        "--count-per-platform",
        type=int,
        default=2,
        help="Fallback count if missing in brief.creative_requirements.count_per_platform",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
