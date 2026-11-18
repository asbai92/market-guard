# Market Guard

Tableau de bord statique en français, actualisé par GitHub Actions après la clôture américaine les jours ouvrés.

## Installation et publication
Le dépôt doit être public avec GitHub Free. Dans **Settings → Pages**, sélectionner **GitHub Actions** comme source. Puis dans **Actions**, lancer **Refresh Market Guard data → Run workflow**. Le site sera publié sur `https://asbai92.github.io/market-guard/` si Pages est activé.

## Sources
- Yahoo Finance Chart : S&P 500, Dow Jones et Nasdaq 100.
- FRED CSV public : taux 10 ans/2 ans, inscriptions chômage, chômage, charge-offs bancaires, CPI et Fed Funds.
- Ligne A/D : non intégrée tant qu'une source publique stable et vérifiable n'est pas disponible. Elle reste donc inconnue, jamais assimilée à un signal rassurant.

## Méthode
Les articles BlogBourse décrivent un faisceau d'indices : inversion de courbe, chômage, défauts bancaires, divergence A/D, puis rupture d'un support majeur et dégradation de la MM30 semaines. L'article de février 2022 ajoute la perte du rebond de l'A/D, un nouveau plus bas A/D, les trois indices sous leurs précédents plus bas et les MM30 semaines descendantes.

Les seuils programmés sont des approximations opérationnelles, non des seuils officiels de l'auteur. Le score est expérimental et n'a pas été validé par backtest. Le signal EXIT doit être interprété comme un avertissement à examiner, jamais comme un ordre de vente.

## Alertes facultatives
Créer les secrets GitHub Actions `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`. Une notification est envoyée uniquement lors d'une dégradation du verdict.

## Limites
Les données peuvent être retardées, corrigées ou indisponibles. Une collecte incomplète produit UNKNOWN. Aucun ordre de bourse n'est exécuté. Ne pas utiliser seul pour gérer un ETF à levier.