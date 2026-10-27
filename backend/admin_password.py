"""Create the password of Analytics Newzi (painel.newzi.app).

    python backend/admin_password.py

Asks for the password twice without showing it and prints the ADMIN_PASSWORD_HASH line for /etc/newzi/newzi.env
(the password itself is never stored). Restart newzi-api afterwards; a new password ends every open panel session.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from newzi_backend.admin import hash_password  # noqa: E402

MIN_LENGTH = 12


def main():
    password = getpass.getpass("Senha do painel: ")
    if len(password) < MIN_LENGTH:
        sys.exit(f"use pelo menos {MIN_LENGTH} caracteres")
    if getpass.getpass("Repita a senha: ") != password:
        sys.exit("as senhas não conferem")
    print("\nColoque esta linha em /etc/newzi/newzi.env (substituindo a anterior, se houver):\n")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
