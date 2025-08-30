#!/usr/bin/env python3
"""
download_and_extract.py

Downloads multiple GitHub repository archives and extracts them into their own folders
inside the process_markdown repository. Also downloads two raw CLI files.

Targets:
1. https://github.com/assafelovic/gpt-researcher -> ./gpt-researcher (default branch)
2. https://github.com/morganross/llm-doc-eval -> ./llm-doc-eval (default branch)
3. https://github.com/morganross/FilePromptForge -> ./FilePromptForge (default branch)
4. https://github.com/morganross/apicostmultiplier -> ./apicostmultiplier (default branch)
5. MA_CLI raw files:
   - Multi_Agent_CLI.py
   - README_CLI.md

Usage:
    python download_and_extract.py

No external dependencies required (uses Python stdlib).
"""
from __future__ import annotations
import sys
import shutil
import urllib.request
import urllib.error
import zipfile
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
    print(f"Downloading: {url}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = resp.getheader("Content-Length")
            if total is not None:
                total = int(total)
            written = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = (written / total) * 100
                        print(f"\r  {written}/{total} bytes ({pct:.1f}%)", end="", flush=True)
        if total:
            print()  # newline after progress
        print(f"Saved to: {dest}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP Error {e.code} while downloading {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL Error while downloading {url}: {e}") from e


def safe_extract_zip(zip_path: Path, extract_to: Path) -> None:
    """
    Safely extract a zip file, preventing path traversal vulnerabilities.
    """
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            member_path = extract_to.joinpath(member)
            # Resolve and ensure the member_path is inside extract_to
            try:
                member_path.resolve().relative_to(extract_to.resolve())
            except Exception:
                raise RuntimeError(f"Unsafe path in zip file: {member}")
        zf.extractall(extract_to)
    print(f"Extracted {zip_path.name} -> {extract_to}")


def download_and_extract_pairs(pairs: List[Tuple[str, Path]]) -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="pm_dl_"))
    try:
        for url, target_dir in pairs:
            zip_name = url.rstrip("/").split("/")[-1]
            # ensure zip_name ends with .zip; if not, create a reasonable filename
            if not zip_name.endswith(".zip"):
                zip_name = target_dir.name + ".zip"
            tmp_zip = tmpdir / zip_name
            try:
                download_file(url, tmp_zip)
            except Exception as e:
                print(f"ERROR downloading {url}: {e}", file=sys.stderr)
                continue
            # For GitHub zip archives, extraction usually creates a top-level folder like repo-branch/
            # We'll extract into a temporary folder, then move/rename to the desired folder to avoid nesting issues.
            temp_extract = tmpdir / (target_dir.name + "_extract")
            try:
                safe_extract_zip(tmp_zip, temp_extract)
            except Exception as e:
                print(f"ERROR extracting {tmp_zip}: {e}", file=sys.stderr)
                continue

            # If extraction produced exactly one top-level directory, move its contents up into target_dir
            entries = list(temp_extract.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                # move that inner directory to the desired location
                if target_dir.exists():
                    # target already exists — merge extracted contents into the existing target
                    print(f"Target directory {target_dir} already exists. Merging contents.")
                    for entry in entries[0].iterdir():
                        dest = target_dir / entry.name
                        # remove existing destination if present so move won't fail
                        if dest.exists():
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                        shutil.move(str(entry), str(dest))
                else:
                    shutil.move(str(entries[0]), str(target_dir))
            else:
                # move/copy all contents of temp_extract into target_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                for entry in entries:
                    dest = target_dir / entry.name
                    if entry.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.move(str(entry), str(dest))
                    else:
                        shutil.move(str(entry), str(dest))
            print(f"Finished: {url} -> {target_dir}")
    finally:
        # Cleanup temporary dir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


def find_llm_doc_zip_url() -> Optional[str]:
    """
    Try common GitHub archive zip URLs for the llm-doc-eval repository.
    Prioritize 'main' then 'master'. Return the first reachable URL.
    """
    base = "https://github.com/morganross/llm-doc-eval"
    candidates = [
        f"{base}/archive/refs/heads/main.zip",
        f"{base}/archive/refs/heads/master.zip",
        # fallback to the generic archive (GitHub will 302 to default branch archive if available)
        f"{base}/archive/refs/heads/main.zip",
    ]
    for url in candidates:
        req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                # If we got a 200/302/etc, treat it as OK
                if resp.status in (200, 302, 301):
                    return url
        except Exception:
            continue
    return None


def main() -> None:
    base_dir = Path(__file__).resolve().parent

    pairs: List[Tuple[str, Path]] = []

    # 1) gpt-researcher - prefer default branch archive (main then master); 
    def _find_gpt_repo_zip():
        base = "https://github.com/assafelovic/gpt-researcher"
        candidates = [
            f"{base}/archive/refs/heads/main.zip",
            f"{base}/archive/refs/heads/master.zip",
        ]
        for url in candidates:
            req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status in (200, 301, 302):
                        return url
            except Exception:
                continue
        # fallback to the release tag if none of the branch archives were reachable
        return candidates[-1]

    gpt_url = _find_gpt_repo_zip()
    # extract/rename to a stable folder name 'gpt-researcher'
    gpt_target = base_dir / "gpt-researcher"
    pairs.append((gpt_url, gpt_target))

    # 2) llm-doc-eval repo zip (try main then master)
    llm_url = find_llm_doc_zip_url()
    if llm_url is None:
        # fallback: try GitHub generic archive URL (this will likely 404 but we attempt)
        llm_url = "https://github.com/morganross/llm-doc-eval/archive/refs/heads/main.zip"
        print("Could not verify llm-doc-eval zip URL in advance; will attempt fallback URL:", llm_url)
    llm_target = base_dir / "llm-doc-eval"
    pairs.append((llm_url, llm_target))

    # 3) FilePromptForge repo zip (try main then master)
    base_fpf = "https://github.com/morganross/FilePromptForge"
    fpf_candidates = [
        f"{base_fpf}/archive/refs/heads/main.zip",
        f"{base_fpf}/archive/refs/heads/master.zip",
    ]
    fpf_url = None
    for url in fpf_candidates:
        req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status in (200, 301, 302):
                    fpf_url = url
                    break
        except Exception:
            continue
    if fpf_url is None:
        fpf_url = f"{base_fpf}/archive/refs/heads/main.zip"
        print("Could not verify FilePromptForge zip URL in advance; will attempt fallback URL:", fpf_url)
    fpf_target = base_dir / "FilePromptForge"
    pairs.append((fpf_url, fpf_target))

    # 4) apicostmultiplier repo zip (try main then master)
    base_apicost = "https://github.com/morganross/apicostmultiplier"
    apicost_candidates = [
        f"{base_apicost}/archive/refs/heads/main.zip",
        f"{base_apicost}/archive/refs/heads/master.zip",
    ]
    apicost_url = None
    for url in apicost_candidates:
        req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status in (200, 301, 302):
                    apicost_url = url
                    break
        except Exception:
            continue
    if apicost_url is None:
        apicost_url = f"{base_apicost}/archive/refs/heads/main.zip"
        print("Could not verify apicostmultiplier zip URL in advance; will attempt fallback URL:", apicost_url)
    apicost_target = base_dir / "apicostmultiplier"
    pairs.append((apicost_url, apicost_target))

    # Also download two raw CLI files into MA_CLI folder
    ma_cli_dir = base_dir / "MA_CLI"
    ma_cli_dir.mkdir(parents=True, exist_ok=True)
    cli_files = [
        ("https://raw.githubusercontent.com/morganross/GPT-Researcher-Multi-Agent-CLI/refs/heads/master/Multi_Agent_CLI.py", ma_cli_dir / "Multi_Agent_CLI.py"),
        ("https://raw.githubusercontent.com/morganross/GPT-Researcher-Multi-Agent-CLI/refs/heads/master/README_CLI.md", ma_cli_dir / "README_CLI.md"),
    ]
    for url, dest in cli_files:
        try:
            download_file(url, dest)
        except Exception as e:
            print(f"ERROR downloading CLI file {url}: {e}", file=sys.stderr)

    print("Starting downloads and extraction. This may take a few moments.")
    download_and_extract_pairs(pairs)

    # Remove unwanted frontend folder under the downloaded gpt-researcher target, if present.
    # Some upstream archives include a 'frontend' folder that this project doesn't use;
    # remove it to avoid clutter and potential import/path conflicts.
    try:
        frontend_dir = gpt_target / "frontend"
        if frontend_dir.exists():
            print(f"Removing unwanted folder: {frontend_dir}")
            shutil.rmtree(frontend_dir)
            print(f"Removed {frontend_dir}")
    except Exception as e:
        print(f"Warning: failed to remove frontend dir {frontend_dir}: {e}", file=sys.stderr)

    # .env propagation skipped: GUI does not require environment injection into downloaded targets.

    print("All done.")


if __name__ == "__main__":
    main()
