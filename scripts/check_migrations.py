"""Verifica statica minimale della genealogia Alembic del Gestionale."""

import ast
from pathlib import Path


EXPECTED_HEAD = "91c4f2b7a6de"
VERSIONS = Path(__file__).resolve().parents[1] / "gestionale" / "migrations" / "versions"


def valore_assegnato(albero, nome):
    for nodo in albero.body:
        if isinstance(nodo, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == nome for target in nodo.targets):
                return ast.literal_eval(nodo.value)
    raise ValueError(f"{nome} non definito")


def main():
    revisioni = {}
    for percorso in VERSIONS.glob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))
        revisione = valore_assegnato(albero, "revision")
        genitori = valore_assegnato(albero, "down_revision")
        if revisione in revisioni:
            raise SystemExit(f"Revision duplicata: {revisione}")
        if genitori is None:
            genitori = ()
        elif isinstance(genitori, str):
            genitori = (genitori,)
        else:
            genitori = tuple(genitori)
        revisioni[revisione] = {"file": percorso.name, "parents": genitori}

    riferimenti = {
        genitore
        for dati in revisioni.values()
        for genitore in dati["parents"]
    }
    mancanti = riferimenti - revisioni.keys()
    if mancanti:
        raise SystemExit(f"Revision genitrici mancanti: {sorted(mancanti)}")
    heads = sorted(revisioni.keys() - riferimenti)
    if heads != [EXPECTED_HEAD]:
        raise SystemExit(
            f"Head Alembic inattesi: {heads}; atteso soltanto {EXPECTED_HEAD}"
        )
    print(f"Genealogia Alembic valida: {len(revisioni)} revisioni, head {EXPECTED_HEAD}")


if __name__ == "__main__":
    main()
