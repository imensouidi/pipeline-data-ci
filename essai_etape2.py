from pipeline.loader import charger_csv
from pipeline.processing import traiter_transactions

transactions = charger_csv("data/transactions_s42_001.csv")
resultat = traiter_transactions(transactions)

print("=== Transactions et flags ===")
for t in resultat.transactions:
    print(f"{t.montant:>10} €  ->  flag = {t.flag_montant_eleve}")

print("\n=== Somme envoyée par banque ===")
for banque, total in resultat.total_envoye_par_banque.items():
    print(f"{banque:<20} {total:>10} €")

print("\n=== Somme envoyée par IBAN ===")
for iban, total in resultat.total_envoye_par_iban.items():
    print(f"{iban}  {total:>10} €")

print("\n=== Somme reçue par IBAN ===")
for iban, total in resultat.total_recu_par_iban.items():
    print(f"{iban}  {total:>10} €")