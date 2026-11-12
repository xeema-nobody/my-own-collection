"""CLI: python -m fetcher.publisher [--dry-run] [--max N]  (see scripts/publish.sh)."""
import argparse
import asyncio
import sys

from fetcher.config import settings
from fetcher.publisher.runner import main

ap = argparse.ArgumentParser(description="Work the Vinted publish queue in the fetcher Chrome profile")
ap.add_argument("--dry-run", action="store_true", help="fill and read back, never click Upload; release the item")
ap.add_argument("--max", type=int, default=1, help="max items this run (default 1)")
a = ap.parse_args()
sys.exit(asyncio.run(main(settings, a.dry_run, max(1, a.max))))
