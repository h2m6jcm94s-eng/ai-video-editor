#!/usr/bin/env python3
"""Interactive setup script — collects env vars and writes .env files."""

import os
import sys
import getpass

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
DIM = "\033[2m"


def ask(prompt: str, default: str = "", secret: bool = False, optional: bool = False) -> str:
    tag = f"{DIM}[optional]{RESET} " if optional else ""
    default_hint = f" {DIM}(default: {default}){RESET}" if default else ""
    full_prompt = f"  {tag}{CYAN}{prompt}{RESET}{default_hint}: "
    try:
        value = getpass.getpass(full_prompt) if secret else input(full_prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)
    value = value.strip()
    return value if value else default


def section(title: str):
    print(f"\n{BOLD}{title}{RESET}")
    print("─" * len(title))


def main():
    print(f"\n{BOLD}{CYAN}AI Video Editor — Environment Setup{RESET}")
    print("This will create .env and apps/web/.env.local with your credentials.\n")

    env: dict[str, str] = {}
    web_env: dict[str, str] = {}

    # ── Clerk Auth ────────────────────────────────────────────────────────────
    section("Clerk Auth  (https://dashboard.clerk.com)")
    print(f"  {DIM}Create a Clerk app → API Keys → copy both keys.{RESET}")
    env["CLERK_SECRET_KEY"] = ask("CLERK_SECRET_KEY", secret=True)
    pk = ask("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    env["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] = pk
    web_env["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] = pk

    # ── Database ──────────────────────────────────────────────────────────────
    section("Neon Postgres  (https://neon.tech)")
    print(f"  {DIM}Create a project → Connection string (pooled).{RESET}")
    env["DATABASE_URL"] = ask("DATABASE_URL", default="postgresql://user:pass@host/dbname")

    # ── Cloudflare R2 ─────────────────────────────────────────────────────────
    section("Cloudflare R2  (https://dash.cloudflare.com → R2)")
    print(f"  {DIM}Create a bucket → Manage R2 API Tokens → create token with read+write.{RESET}")
    env["R2_ENDPOINT"] = ask("R2_ENDPOINT (e.g. https://<acct>.r2.cloudflarestorage.com)")
    env["R2_ACCESS_KEY_ID"] = ask("R2_ACCESS_KEY_ID")
    env["R2_SECRET_ACCESS_KEY"] = ask("R2_SECRET_ACCESS_KEY", secret=True)
    env["R2_BUCKET_NAME"] = ask("R2_BUCKET_NAME", default="ai-video-editor")

    # ── Redis ─────────────────────────────────────────────────────────────────
    section("Redis  (local Docker or Upstash / Redis Cloud)")
    env["REDIS_URL"] = ask("REDIS_URL", default="redis://localhost:6379")

    # ── Temporal ──────────────────────────────────────────────────────────────
    section("Temporal  (local Docker or Temporal Cloud)")
    env["TEMPORAL_HOST"] = ask("TEMPORAL_HOST", default="localhost:7233")

    # ── Web URL ───────────────────────────────────────────────────────────────
    env["WEB_URL"] = ask("WEB_URL (frontend origin)", default="http://localhost:3000")
    api_url = ask("NEXT_PUBLIC_API_URL (API base URL)", default="http://localhost:4000")
    env["API_PORT"] = "4000"
    web_env["NEXT_PUBLIC_API_URL"] = api_url

    # ── AI Provider ───────────────────────────────────────────────────────────
    section("AI Providers  (at least one required for cut-list generation)")
    print(f"  {DIM}Claude is the primary provider. Others are fallbacks.{RESET}")
    env["AI_PROVIDER"] = ask("AI_PROVIDER (comma-separated chain)", default="claude,gemini,programmatic")

    anthropic = ask("ANTHROPIC_API_KEY  (https://console.anthropic.com)", secret=True, optional=True)
    if anthropic:
        env["ANTHROPIC_API_KEY"] = anthropic

    google = ask("GOOGLE_API_KEY  (https://aistudio.google.com/apikey)", secret=True, optional=True)
    if google:
        env["GOOGLE_API_KEY"] = google

    groq = ask("GROQ_API_KEY  (https://console.groq.com)", secret=True, optional=True)
    if groq:
        env["GROQ_API_KEY"] = groq

    openai = ask("OPENAI_API_KEY  (https://platform.openai.com)", secret=True, optional=True)
    if openai:
        env["OPENAI_API_KEY"] = openai

    kimi = ask("KIMI_API_KEY", secret=True, optional=True)
    if kimi:
        env["KIMI_API_KEY"] = kimi

    qwen = ask("QWEN_API_KEY", secret=True, optional=True)
    if qwen:
        env["QWEN_API_KEY"] = qwen

    openrouter = ask("OPENROUTER_API_KEY  (https://openrouter.ai/keys)", secret=True, optional=True)
    if openrouter:
        env["OPENROUTER_API_KEY"] = openrouter

    # ── Modal (optional GPU) ──────────────────────────────────────────────────
    section("Modal  (optional — GPU upscaling workers)")
    modal_id = ask("MODAL_TOKEN_ID", optional=True)
    if modal_id:
        env["MODAL_TOKEN_ID"] = modal_id
        env["MODAL_TOKEN_SECRET"] = ask("MODAL_TOKEN_SECRET", secret=True)

    # ── Write files ───────────────────────────────────────────────────────────
    root = os.path.dirname(os.path.abspath(__file__))

    env_path = os.path.join(root, ".env")
    with open(env_path, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    os.chmod(env_path, 0o600)

    web_env_path = os.path.join(root, "apps", "web", ".env.local")
    os.makedirs(os.path.dirname(web_env_path), exist_ok=True)
    with open(web_env_path, "w") as f:
        for k, v in web_env.items():
            f.write(f"{k}={v}\n")
    os.chmod(web_env_path, 0o600)

    print(f"\n{GREEN}✓ Written:{RESET} .env (permissions 600)")
    print(f"{GREEN}✓ Written:{RESET} apps/web/.env.local (permissions 600)")
    print(f"\n{DIM}Run `pnpm install && uv sync` then `docker compose -f infra/docker/docker-compose.yml up -d` to start services.{RESET}\n")


if __name__ == "__main__":
    main()
