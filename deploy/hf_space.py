"""Publish the free Hugging Face Space mirror of the app.

    hf auth login                                    # once, with a WRITE token (you run this)
    python deploy/hf_space.py --dump annual_reports.dump   # first time: data + Space
    python deploy/hf_space.py                        # later: update the Space files only
    python deploy/hf_space.py --set-secrets          # you run this: asks for the keys

Creates two repos under your Hugging Face account:
  <you>/annual-report-analyst-data  PRIVATE dataset holding the database dump
  <you>/annual-report-analyst       public Docker Space (deploy/hf-space/), which downloads
                                    the dump on start with the HF_TOKEN secret

--set-secrets stores GROQ_API_KEY (read from .env) and HF_TOKEN (pasted, hidden) as Space
secrets. Use a fine-grained READ token limited to the data repo for HF_TOKEN, not your
write token. ANTHROPIC_API_KEY is left out on purpose: on a public demo, strangers could
spend paid fallback tokens; when Groq's free limit is hit the Space just says so.
"""

import argparse
import getpass
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_DIR = ROOT / "deploy" / "hf-space"


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip("\"'")
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dump", type=Path, help="pg_dump -Fc file to upload to the private dataset")
    ap.add_argument("--set-secrets", action="store_true", help="store GROQ_API_KEY and HF_TOKEN")
    args = ap.parse_args()

    api = HfApi()
    user = api.whoami()["name"]
    space, data = f"{user}/annual-report-analyst", f"{user}/annual-report-analyst-data"

    if args.set_secrets:
        groq = env_value("GROQ_API_KEY")
        if not groq:
            raise SystemExit("GROQ_API_KEY is empty in .env")
        token = getpass.getpass(f"Fine-grained READ token for {data} (hidden): ").strip()
        api.add_space_secret(space, "GROQ_API_KEY", groq)
        api.add_space_secret(space, "HF_TOKEN", token)
        print("stored Space secrets GROQ_API_KEY and HF_TOKEN; restarting the Space")
        api.restart_space(space)
        return

    if args.dump:
        api.create_repo(data, repo_type="dataset", private=True, exist_ok=True)
        api.upload_file(
            path_or_fileobj=str(args.dump),
            path_in_repo="annual_reports.dump",
            repo_id=data,
            repo_type="dataset",
        )
        print(f"uploaded the dump to the private dataset {data}")

    api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_variable(space, "DATA_REPO", data)
    api.upload_folder(folder_path=str(SPACE_DIR), repo_id=space, repo_type="space")
    print(f"Space files uploaded: https://huggingface.co/spaces/{space}")
    print(f"App URL once built: https://{space.replace('/', '-').lower()}.hf.space")


if __name__ == "__main__":
    main()
