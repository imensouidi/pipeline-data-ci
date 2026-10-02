"""Outils IBAN : calcul de la clé de contrôle et validation (norme ISO 13616, modulo 97)."""
import re

_FORMAT_IBAN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}")


def _en_nombre(texte: str) -> int:
    """Convertit lettres et chiffres en nombre (A=10, B=11, ..., Z=35)."""
    return int("".join(str(int(caractere, 36)) for caractere in texte))


def calculer_iban(pays: str, bban: str) -> str:
    """Construit un IBAN valide à partir du code pays et du BBAN (numéro de compte national)."""
    cle = 98 - _en_nombre(bban + pays + "00") % 97
    return f"{pays}{cle:02d}{bban}"


def iban_valide(iban: str) -> bool:
    """Vérifie le format et la clé de contrôle d'un IBAN."""
    if not _FORMAT_IBAN.fullmatch(iban):
        return False
    return _en_nombre(iban[4:] + iban[:4]) % 97 == 1
