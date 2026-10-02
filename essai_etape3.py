from pipeline.database import (
    connecter,
    fichier_deja_traite,
    initialiser_schema,
    inserer_resultat,
    statistiques,
)
from pipeline.loader import calculer_hash, charger_csv
from pipeline.processing import traiter_transactions

chemin = "data/transactions_s42_001.csv"
resultat = traiter_transactions(charger_csv(chemin))
empreinte = calculer_hash(chemin)

connexion = connecter("output/pipeline.db")
initialiser_schema(connexion)

if fichier_deja_traite(connexion, empreinte):
    print("Fichier déjà traité : il n'est PAS inséré une deuxième fois.")
else:
    inserer_resultat(connexion, "transactions_s42_001.csv", empreinte, resultat)
    print("Fichier inséré en base.")

print("Contenu de la base :", statistiques(connexion))

print("\n=== Table total_envoye_par_banque ===")
for banque, total in connexion.execute(
    "SELECT banque_source, total_centimes / 100.0 FROM total_envoye_par_banque ORDER BY banque_source"
):
    print(f"{banque:<20} {total:>10.2f} €")

connexion.close()