"""Mark an account Premium or Básico to test the plans, without the store.

    python backend/premium_test_account.py EMAIL grant [--days 30]
    python backend/premium_test_account.py EMAIL revoke
    python backend/premium_test_account.py EMAIL status

The Premium limits only apply with PREMIUM_ENFORCED=true in .env (restart the API and the worker after changing
it); with it off everyone keeps every feature. A grant is a courtesy in premium_grants, the same as "Dar Premium"
on painel.newzi.app, and revoke ends the courtesies only (a store plan is left alone).
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "engine" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from newzi_backend.env import load_local_environment  # noqa: E402

load_local_environment()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("action", choices=("grant", "revoke", "status"))
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)

    from newzi_backend.product_backend import ProductRepository
    from newzi_backend.subscriptions import entitlements, grant_manual, premium_enforced, revoke_manual, subscription_for
    repo = ProductRepository()
    user = repo.db.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (args.email,)).fetchone()
    if not user:
        sys.exit(f"no account with e-mail {args.email}")
    uid = user["id"]
    if args.action == "grant":
        grant_manual(repo, uid, args.days)
    elif args.action == "revoke":
        revoke_manual(repo, uid)
    plan = subscription_for(repo, uid)
    print(f"account {args.email}: plan {plan['tier']}" + (f" until {plan['expires_at']}" if plan["expires_at"] else ""))
    print(f"limits enforced (PREMIUM_ENFORCED): {'yes' if premium_enforced() else 'no — everyone has every feature'}")
    print(f"Premium features open to this account: {'yes' if entitlements(repo, uid)['premium'] else 'no'}")


if __name__ == "__main__":
    main()
