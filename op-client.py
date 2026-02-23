#!/usr/bin/env python3

import argparse
import os
import subprocess


def op_read(ref_url: str, account: str | None = None) -> str:
    args = ["op", "read", ref_url]
    if account is not None:
        args.append(f"--account={account}")
    proc = subprocess.run(args, capture_output=True, text=True, check=True)
    return proc.stdout


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-id", default=os.environ.get("OP_VAULT_ID"))
    matches = parser.parse_args()
    op_account_server: str = os.environ["OP_ACCOUNT_SERVER"]
    vault_id: str = matches.vault_id
    print(op_read(vault_id, account=op_account_server), end="")


if __name__ == "__main__":
    _main()
