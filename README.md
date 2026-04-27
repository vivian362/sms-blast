# Gemini Creative Generator (Meta + Google)

This project generates **hyper-detailed ad creatives** for Meta and Google using a Google Gemini API key, a strict JSON schema, and reproducible output folders.

## What this gives you

- A local Python CLI script for generating creatives with Gemini.
- Strict structured JSON output validated against a schema.
- A deterministic folder structure for every generation.
- Editable files (`brief.json`, `prompt.txt`, `response_raw.txt`, `creative.json`) so you can revise and regenerate.
- Optional docs-context injection so your own Gemini documentation snippets can be used in every run.

## Quick Start

1. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set your Gemini API key:

```bash
export GEMINI_API_KEY="your_key_here"
```

3. Copy and edit the example brief:

```bash
cp examples/brief.example.json brief.json
```

4. Run generator:

```bash
python scripts/generate_creatives.py \
  --brief brief.json \
  --platform both \
  --model gemini-2.5-pro \
  --docs-context docs/gemini_context.md
```

5. Find outputs in `runs/<timestamp>/...`.

## Folder structure

Each run creates a hierarchy like:

```text
runs/
  20260427T120501Z/
    run_manifest.json
    meta/
      campaign_<slug>/
        adset_<slug>/
          creative_001/
            brief.json
            prompt.txt
            response_raw.txt
            creative.json
    google/
      campaign_<slug>/
        adgroup_<slug>/
          creative_001/
            brief.json
            prompt.txt
            response_raw.txt
            creative.json
```

This is intentionally verbose so edits can happen at every layer.

## About “all Gemini documentation”

You generally should not dump the full docs in every prompt because of token limits and noisy context. Instead:

- Keep a curated `docs/gemini_context.md` with your critical rules and excerpts.
- Update it as Gemini APIs evolve.
- The script prepends this context to the generation prompt.

Official references to curate from:
- https://ai.google.dev/gemini-api/docs
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/text-generation

## Notes

- If schema validation fails, the script saves outputs anyway and marks failures in `run_manifest.json`.
- Use the generated `creative.json` as editable source-of-truth and rerun with changes to your brief.
