"""Generate static demo narration audio files using Gemini TTS via Vertex AI.

ONE-TIME offline script — NOT part of the live FastAPI app.
Generates WAV files for agent persona narrations and results walkthrough
narrations, using the fixed scripts from .kiro/specs/demo/design.md.

Skips files that already exist (to avoid burning API credits on re-runs).
Use --force to regenerate specific files, or --force-all to regenerate everything.

Usage:
    uv run python scripts/generate_demo_narration.py              # only missing files
    uv run python scripts/generate_demo_narration.py --force curator results_banner
    uv run python scripts/generate_demo_narration.py --force-all  # regenerate everything

Requires:
    - GCP_PROJECT environment variable (or .env file in project root)
    - GCP_LOCATION environment variable (defaults to "us-central1")
    - Authenticated gcloud credentials (application-default or service account)

Output:
    frontend/public/audio/*.wav
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (same convention as the FastAPI app)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ID = os.environ.get("GCP_PROJECT")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

if not PROJECT_ID:
    print("ERROR: GCP_PROJECT environment variable is not set.", file=sys.stderr)
    print("Set it in your .env file or export it before running.", file=sys.stderr)
    sys.exit(1)

# Model: gemini-2.5-flash-tts (GA, matches project's existing Gemini 2.5 Flash usage)
MODEL = "gemini-2.5-flash-tts"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "audio"

# ---------------------------------------------------------------------------
# Narration scripts — exact text from .kiro/specs/demo/design.md
# ---------------------------------------------------------------------------

NARRATIONS: dict[str, str] = {
    "intro": (
       "[warm, confident] A gallery or auction house can spend hundreds of hours on a single piece "
        "- tracing ownership, checking for red flags, defending a price. "
        "Artgents does that research in 60 to 90 seconds - calls to Vertex AI "
        "and public museum archives. Here's how it works, then a completed run. "
        "Two independently-reasoning agents debate each contested step - not one averaged verdict."
    ),
    "built_with_kiro": (
        "[warm, clear] Every agent was built through Kiro's spec workflow - "
        "requirements, design, and tasks, all in .kiro/specs/. "
        "[short pause] These weren't written once and forgotten: real testing "
        "found a cross-object data bug in the provenance agent, the spec was "
        "updated with the fix, and that same fix was built into the next agent "
        "from day one - instead of being rediscovered there too."
    ),
    "visual_art_historian": (
        "[measured] I'm the first to look at the piece. I study the "
        "brushwork, the materials, the composition - and I try to place it "
        "in art history. [thoughtful pause] If there's no visible signature, "
        "I won't pretend to certainty I don't have. I'll tell you what style "
        "and period the evidence supports, and I'll separate that from any "
        "guess at who painted it."
    ),
    "compliance_auditor": (
        "[firm, terse] I'm the skeptic. I treat every gap in this artwork's "
        "ownership history as a risk - especially if it falls during the "
        "Second World War, or before international export rules existed in "
        "1970. I don't assume good faith. [short pause] My job is to ask: "
        "what if something's wrong here?"
    ),
    "provenance_historian": (
        "[warm, explaining] I look at the same evidence my colleague does, "
        "but I ask a different question: is this gap actually unusual? Most "
        "art from before the twentieth century has incomplete records - "
        "that's normal, not suspicious. I put the gap in context. "
        "[short pause] We don't always agree, and that disagreement is the "
        "point."
    ),
    "conservative_appraiser": (
        "[cautious, measured] I set the floor. I look at real comparable "
        "sales, and I ask: what's the worst reasonable case? An attribution "
        "that isn't certain, a market that's soft, a forced sale - I build "
        "all of that into a defensible minimum."
    ),
    "bullish_specialist": (
        "[confident, energetic] I set the ceiling. Same evidence as my "
        "colleague, different question: what's this worth to the right "
        "buyer, under the right conditions? Scarcity, momentum, a museum "
        "with real interest - I price the upside they're not accounting for."
    ),
    "curator": (
        "[measured, reflective] Once everyone else has spoken, I bring it "
        "together. I write the exhibition copy - but I don't get to soften "
        "what the others found. [short pause] If there's a real disagreement "
        "or a real risk flagged upstream, it shows up in what I write, every "
        "time, whether that makes a cleaner story or not."
    ),
}

# ---------------------------------------------------------------------------
# Voice assignment — from design.md's voice table
# All confirmed valid as Gemini TTS prebuilt voices (Vertex AI docs, Aug 2026)
# ---------------------------------------------------------------------------

VOICES: dict[str, str] = {
    "intro": "Kore",                       # Narrator/bookend tone (same as curator)
    "built_with_kiro": "Kore",             # Same narrator voice (framing segment)
    "visual_art_historian": "Aoede",       # Clear, measured, analytical
    "compliance_auditor": "Charon",        # Firm, lower register, terse
    "provenance_historian": "Leda",        # Warmer, more explanatory
    "conservative_appraiser": "Orus",      # Cautious, measured
    "bullish_specialist": "Puck",          # Energetic, confident
    "curator": "Kore",                     # Reserved, narrator/closing tone
}

# ---------------------------------------------------------------------------
# Results walkthrough narration — third-person narrator explaining each section
# These use the Kore voice (narrator tone) and are saved to
# frontend/public/audio/results_*.wav
# ---------------------------------------------------------------------------

RESULTS_NARRATIONS: dict[str, str] = {
    "results_banner": (
        "Here's the key finding. The system retrieved real, documented "
        "history — including Führermuseum and Munich Central Collecting Point "
        "records — but that evidence is tied to a different specific work by "
        "this artist, not the piece being assessed. Because it can't be "
        "connected to this object, both agents correctly say the standard "
        "provenance test cannot be applied. That's the honest answer."
    ),
    "results_visual": (
        "The Visual Art Historian identified this as an early fifteenth-century "
        "International Gothic painting. The attribution to Gentile da Fabriano "
        "is based on strong stylistic similarity to his documented works — but "
        "no signature is visible, so it remains 'attributed to,' not confirmed. "
        "That hedge language is preserved throughout everything that follows."
    ),
    "results_provenance": (
        "Both the Compliance Auditor and the Provenance Historian reached the "
        "same conclusion independently: cannot determine. The evidence scope is "
        "artist-general — meaning retrieval found facts about the artist's body "
        "of work, not this specific piece. Without object-specific data, the "
        "standard museum due-diligence test simply cannot be applied. Neither "
        "agent guessed."
    ),
    "results_valuation": (
        "The valuation corridor runs from fifty thousand to one hundred and "
        "twenty-five thousand dollars. Both appraisers anchor on the same "
        "Sotheby's comparable — two authenticated panels estimated at two "
        "hundred fifty to three hundred fifty thousand — but discount heavily "
        "for the unconfirmed attribution. Confidence is low on both sides, "
        "which is itself an honest signal."
    ),
    "results_curator": (
        "The Curator wrote exhibition copy in two variants: auction house and "
        "public gallery. Both correctly state that object-specific provenance "
        "research is still needed — that language wasn't optional. The "
        "disclosure floor guarantees it appears regardless of how the "
        "narrative reads. [pause] Thank you."
    ),
    "results_evidence": (
        "Every factual claim in the analysis carries a real, clickable source "
        "URL. The provenance sources come from Wikidata — real ownership "
        "records for documented works by this artist. The valuation comparables "
        "are real titles from the artist's catalogue. Nothing is asserted "
        "without a citation."
    ),
    "results_disclosures": (
        "The disclosure floor is structural. Because the provenance stage "
        "flagged 'requires human review,' that fact appears in the final "
        "exhibition copy automatically — the Curator cannot drop it, no matter "
        "how the narrative reads. This is enforced by code, not by asking the "
        "model nicely."
    ),
}

RESULTS_VOICES: dict[str, str] = {
    "results_banner": "Kore",
    "results_visual": "Kore",
    "results_provenance": "Kore",
    "results_valuation": "Kore",
    "results_curator": "Kore",
    "results_evidence": "Kore",
    "results_disclosures": "Kore",
}

# NOTE on voice "Leda": The Vertex AI docs list it in the Live API voice
# configuration page but NOT in the Gemini-TTS voices table (which shows
# 21 voices). If Leda fails at runtime, fall back to "Achernar" (Female,
# soft) or "Aoede" with a different style prompt. The script will print a
# clear error if any voice fails.


# ---------------------------------------------------------------------------
# Tag separation helper
# ---------------------------------------------------------------------------


def _separate_tags(text: str) -> tuple[str, str]:
    """Separate delivery-direction tags from spoken text.

    Returns (style_direction, spoken_text) where:
    - style_direction: e.g. " in a warm, confident tone" (from leading [tag])
      or "" if no leading tag
    - spoken_text: the actual words to speak, with inline [pause] tags
      replaced by " ... " to create natural pauses via punctuation
    """
    # Extract leading style tag (e.g. "[warm, confident]")
    leading_match = re.match(r'^\[([^\]]+)\]\s*', text)
    if leading_match:
        style = leading_match.group(1)
        style_direction = f" in a {style} tone"
        text = text[leading_match.end():]
    else:
        style_direction = ""

    # Strip inline pause/delivery tags — replace with ellipsis for natural pause
    spoken_text = re.sub(r'\[(?:short pause|thoughtful pause|pause)\]\s*', '... ', text)
    # Strip any other remaining tags that might slip through
    spoken_text = re.sub(r'\[[^\]]*\]\s*', '', spoken_text)
    # Clean up double spaces
    spoken_text = re.sub(r'  +', ' ', spoken_text).strip()

    return style_direction, spoken_text


# ---------------------------------------------------------------------------
# WAV file helper
# ---------------------------------------------------------------------------

def save_wav(filepath: Path, pcm_data: bytes, channels: int = 1,
             sample_rate: int = 24000, sample_width: int = 2) -> None:
    """Write raw PCM data to a WAV file with proper headers."""
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate demo narration audio files via Gemini TTS."
    )
    parser.add_argument(
        "--force",
        nargs="*",
        metavar="KEY",
        help="Regenerate specific files (by key name, e.g. 'curator results_banner'). "
             "Without arguments after --force, acts like --force-all.",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Regenerate all files, even if they already exist.",
    )
    args = parser.parse_args()

    # Determine which keys to force-regenerate
    force_all = args.force_all or (args.force is not None and len(args.force) == 0)
    force_keys: set[str] = set(args.force) if args.force and len(args.force) > 0 else set()

    print(f"Project: {PROJECT_ID}")
    print(f"Location: {LOCATION}")
    print(f"Model: {MODEL}")
    print(f"Output dir: {OUTPUT_DIR}")
    if force_all:
        print("Mode: regenerate ALL files")
    elif force_keys:
        print(f"Mode: regenerate specific files: {', '.join(sorted(force_keys))}")
    else:
        print("Mode: generate only MISSING files (use --force <key> to override)")
    print()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize Vertex AI client
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("Vertex AI client initialized.\n")

    success_count = 0
    skipped_count = 0
    errors: list[str] = []

    for persona_key, narration_text in NARRATIONS.items():
        voice_name = VOICES[persona_key]
        output_path = OUTPUT_DIR / f"{persona_key}.wav"

        # Skip if file exists and not forced
        if output_path.exists() and not force_all and persona_key not in force_keys:
            print(f"[{persona_key}] Already exists, skipping. (use --force {persona_key} to regenerate)")
            skipped_count += 1
            continue

        print(f"[{persona_key}] Generating with voice '{voice_name}'...")
        print(f"  Text: \"{narration_text[:80]}...\"")

        try:
            # Separate delivery tags from spoken text:
            # - Leading [tag] becomes a style instruction in the prompt
            # - Inline [pause] tags are stripped (replaced with punctuation pauses)
            style_direction, spoken_text = _separate_tags(narration_text)
            prompt_text = f"Say the following{style_direction}: {spoken_text}"

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        ),
                    ),
                ),
            )

            # Extract raw PCM audio data from response
            if (
                not response.candidates
                or not response.candidates[0].content
                or not response.candidates[0].content.parts
            ):
                raise RuntimeError("Empty response from Vertex AI — no audio generated")

            audio_data = response.candidates[0].content.parts[0].inline_data.data
            if not audio_data:
                raise RuntimeError("Response contained empty audio data")

            # Save as WAV (16-bit, 24kHz, mono — Gemini TTS default output format)
            save_wav(output_path, audio_data)

            duration_secs = len(audio_data) / (24000 * 2)  # 24kHz, 16-bit = 2 bytes/sample
            print(f"  ✓ Saved: {output_path.name} ({len(audio_data):,} bytes, ~{duration_secs:.1f}s)")
            print()
            success_count += 1

        except Exception as e:
            error_msg = f"  ✗ FAILED: {type(e).__name__}: {e}"
            print(error_msg)
            print()
            errors.append(f"{persona_key}: {e}")

    # --- Results walkthrough narrations ---
    print("\n--- Results Walkthrough Narrations ---\n")

    for section_key, narration_text in RESULTS_NARRATIONS.items():
        voice_name = RESULTS_VOICES[section_key]
        output_path = OUTPUT_DIR / f"{section_key}.wav"

        # Skip if file exists and not forced
        if output_path.exists() and not force_all and section_key not in force_keys:
            print(f"[{section_key}] Already exists, skipping. (use --force {section_key} to regenerate)")
            skipped_count += 1
            continue

        print(f"[{section_key}] Generating with voice '{voice_name}'...")
        print(f"  Text: \"{narration_text[:80]}...\"")

        try:
            prompt_text = f"Say the following in a calm, clear narrator tone — explaining a technical result to an interested audience: {narration_text}"

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        ),
                    ),
                ),
            )

            if (
                not response.candidates
                or not response.candidates[0].content
                or not response.candidates[0].content.parts
            ):
                raise RuntimeError("Empty response from Vertex AI — no audio generated")

            audio_data = response.candidates[0].content.parts[0].inline_data.data
            if not audio_data:
                raise RuntimeError("Response contained empty audio data")

            save_wav(output_path, audio_data)

            duration_secs = len(audio_data) / (24000 * 2)
            print(f"  ✓ Saved: {output_path.name} ({len(audio_data):,} bytes, ~{duration_secs:.1f}s)")
            print()
            success_count += 1

        except Exception as e:
            error_msg = f"  ✗ FAILED: {type(e).__name__}: {e}"
            print(error_msg)
            print()
            errors.append(f"{section_key}: {e}")

    # Summary
    print("=" * 60)
    total = len(NARRATIONS) + len(RESULTS_NARRATIONS)
    print(f"Done. {success_count} generated, {skipped_count} skipped (already exist), "
          f"{len(errors)} failed. ({total} total files)")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    elif success_count == 0 and skipped_count > 0:
        print("\nAll files already exist. Use --force <key> or --force-all to regenerate.")
    else:
        print("\nReview audio quality before committing.")


if __name__ == "__main__":
    main()
