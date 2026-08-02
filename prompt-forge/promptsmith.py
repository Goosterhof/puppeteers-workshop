#!/usr/bin/env python3
"""The Promptsmith — forge generation prompts for the Workshop's video stack.

Talks to the local Ollama daemon (qwen3:14b by default) and turns a rough idea
into ready-to-paste prompts for the specific model you are about to run.
Every target bakes in the constraints this workshop learned the hard way:

  wan    Wan 2.2 i2v (Enhanced Lightning 14B) — motion-first, identity from the
         start image, positive-only phrasing (cfg=1 distilled IGNORES negatives).
  flux   Flux 2 Klein 9B (4-step distilled, cfg 1.0) — single dense paragraph,
         no negative prompt exists, say what you WANT.
  relay  LTX2 Relay Prompt — time-ranged segments `[25%:50%] she says "..."`.

Usage:
  promptsmith.py wan "the town crier swings his bell twice, cloak sways"
  promptsmith.py flux "pirate captain portrait, painterly, warm rim light"
  promptsmith.py relay "mascot greets the viewer then rings the bell" --variants 2
  echo "idea" | promptsmith.py wan -

Options:
  --variants N   number of prompt variants to forge (default 3)
  --model NAME   Ollama model (default qwen3:14b, or qwen3-vl:8b with --image)
  --image PATH   ground the prompts in a start image (the Promptsmith gets eyes:
                 the stillness inventory is read off the actual pixels)
  --fast         skip the reasoning pass (quicker, noticeably lazier output)
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:14b"
VISION_MODEL = "qwen3-vl:8b"  # used automatically when an image is given

FORGE_PROFILES = {
    "wan": (
        "You write prompts for Wan 2.2 image-to-video (Enhanced Lightning 14B, "
        "4-step distilled, cfg=1). The start image defines the subject's identity "
        "— never redesign or restyle it, and NEVER name or re-describe the "
        "subject's species, breed, or character type, not even a synonym or "
        "taxonomy of the user's own words ('sauropod' for a triceratops morphs "
        "the character): refer to it only as 'the subject' or with the user's "
        "exact noun, and spend your words on MOTION language. DO anchor identity "
        "with a stillness inventory: name the distinctive details from the "
        "user's description and state they 'stay exactly as drawn' or 'perfectly "
        "still' (proven to help the model hold identity). Structure each prompt: "
        "(1) one-line framing of the subject as given, (2) the ONE continuous "
        "action in present tense with "
        "concrete physical verbs and explicit amplitude ('swings vigorously' vs "
        "'sways gently, tiny motion amplitude'), (3) the stillness inventory, "
        "(4) camera — default 'locked-off static camera, no zoom' unless the user "
        "asks for movement, (5) the background, stated positively ('the flat "
        "uniform background stays perfectly still' — distilled cfg=1 models IGNORE "
        "negative prompts, so never say 'no X'). Keep each prompt under 110 words."
    ),
    "flux": (
        "You write prompts for FLUX.2 Klein 9B, a 4-step distilled text-to-image "
        "model at cfg 1.0. There is NO negative prompt — everything must be stated "
        "positively as what you WANT to see. Write one dense flowing paragraph per "
        "prompt covering: subject (specific, physical), art style / medium, "
        "lighting, composition and framing, color palette, background. Concrete "
        "nouns beat adjectives; 'weathered brass bell with a rope-wrapped handle' "
        "beats 'detailed bell'. Keep each prompt under 120 words."
    ),
    "relay": (
        "You write LTX2 Relay Prompts for Wan2GP: a sequence of time-ranged "
        "segments in the form `[start%:end%] description`, covering 0% to 100% "
        "with no gaps. Spoken lines go in double quotes inside their segment, "
        "e.g. `[25%:50%] she says \"Hear ye, hear ye!\"`. Each segment describes "
        "one clear beat of motion or speech; 3-5 segments per prompt. Positive "
        "phrasing only — these are distilled cfg=1 models that ignore negatives."
    ),
}


VISION_RIDER = (
    "\n\nYou are SHOWN the actual start image. Ground every prompt in what you "
    "see: derive the stillness inventory from the real, visible details (name "
    "them concretely — emblems, held objects, clothing, textures), match the "
    "actual art style and background, and never invent elements that are not "
    "in the picture. The user's idea tells you what should MOVE; the image "
    "tells you everything else."
)


def forge(target: str, idea: str, variants: int, model: str, think: bool,
          image_b64: str | None = None) -> str:
    system = (
        FORGE_PROFILES[target]
        + (VISION_RIDER if image_b64 else "")
        + f"\n\nProduce exactly {variants} distinct prompt variant(s), numbered "
        "1., 2., ... — each a different creative interpretation, not a rewording. "
        "Output ONLY the numbered prompts, no preamble, no commentary."
    )
    user_msg = {"role": "user", "content": idea}
    if image_b64:
        user_msg["images"] = [image_b64]
    payload = {
        "model": model,
        "stream": False,
        "think": think,
        # 8k is plenty for prompt drafting; the default 32k inflates the KV
        # cache by ~3 GB and pushed the loaded model to 14 GB VRAM.
        "options": {"num_ctx": 8192},
        "messages": [
            {"role": "system", "content": system},
            user_msg,
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.load(resp)
    return body["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="promptsmith",
        description="Forge Wan2GP / ComfyUI generation prompts from a rough idea.",
    )
    parser.add_argument("target", choices=sorted(FORGE_PROFILES))
    parser.add_argument("idea", help="rough idea text, or '-' to read from stdin")
    parser.add_argument("--variants", type=int, default=3)
    parser.add_argument("--model", default=None,
                        help=f"Ollama model (default {DEFAULT_MODEL}, or {VISION_MODEL} with --image)")
    parser.add_argument("--image", help="start image to ground the prompts in (path)")
    parser.add_argument(
        "--fast",
        dest="think",
        action="store_false",
        help="skip the reasoning pass (quicker, noticeably lazier output)",
    )
    args = parser.parse_args()

    idea = sys.stdin.read().strip() if args.idea == "-" else args.idea
    if not idea:
        parser.error("the forge needs raw material — give it an idea")

    image_b64 = None
    if args.image:
        import base64
        from pathlib import Path

        source = Path(args.image)
        if not source.is_file():
            parser.error(f"the lead is missing — no image at {args.image}")
        image_b64 = base64.b64encode(source.read_bytes()).decode()
    model = args.model or (VISION_MODEL if image_b64 else DEFAULT_MODEL)

    try:
        print(forge(args.target, idea, args.variants, model, args.think, image_b64))
    except urllib.error.URLError as exc:
        print(
            "The Promptsmith found the forge cold — Ollama is not answering at "
            f"localhost:11434 ({exc.reason}). Light it with `ollama serve` (or "
            "check `systemctl status ollama`) and strike again.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
