# Market Guard — tableau de bord automatisé

Application web française de suivi des risques de marché. Collecte automatique via GitHub Actions, publication statique via GitHub Pages.

## Sources
- Yahoo Finance : S&P 500, Dow Jones et Nasdaq 100.
- FRED : série directe T10Y2Y, inscriptions au chômage, taux de chômage, charge-offs bancaires (CORALACBS), CPI et Fed Funds.
- La ligne NYSE A/D exacte ($ADLINENYA) n'est pas encore connectée. L'ancien proxy S&P 500 est exclu du verdict. Tant que la vraie série n'est pas disponible, les deux critères A/D restent UNKNOWN et le verdict global reste UNKNOWN.

## Courbe des taux
Le script calcule les moyennes mensuelles de T10Y2Y. Une inversion persistante est confirmée après trois moyennes mensuelles négatives consécutives. Il conserve le début et la fin de la dernière séquence négative, son ancienneté et le repère historique 12–18 mois. Ce repère n'est pas une prédiction de récession et ne déclenche pas seul une sortie.

## Analyse technique
- MM30 semaines et pente sur quatre semaines.
- Support calculé sur les plus bas des 26 semaines précédentes.
- Cassure confirmée après deux clôtures hebdomadaires sous le support.
- La méthode BlogBourse 2022 décrit les plus bas de janvier comme supports et les MM30 semaines descendantes sur les trois indices. Le calcul automatique de support sur 26 semaines est une approximation documentée, pas une reproduction exacte de l'analyse graphique.

## Score et limites
Les seuils chômage, charge-offs, inflation et score sont expérimentaux, non des seuils officiels BlogBourse. Le score ne remplace pas la séquence de signaux macro puis technique. Aucun backtest historique complet n'a encore été effectué. Les historiques Yahoo actuellement demandés sont limités à cinq ans : ils ne suffisent pas à valider 1987, 1990, 2000 ou 2008. Ne pas utiliser le verdict seul pour décider de vendre, particulièrement un ETF à levier.

## Publication et actualisation
Dans **Settings → Pages**, choisir **GitHub Actions**. Le workflow s'exécute du lundi au vendredi à 23:30 UTC et peut être lancé depuis **Actions → Refresh Market Guard data → Run workflow**. Le bouton Actualiser du site recharge les données déjà publiées ; il ne déclenche pas une collecte.

Alertes Telegram facultatives via les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`.

Aucune transaction n'est exécutée. Une donnée indisponible reste UNKNOWN, jamais positive par défaut.

## Backtest historique
Le script `backtest.py` teste uniquement les signaux techniques (MM30 semaines descendante + cassure confirmée de support 26 semaines) sur les indices S&P 500, Dow Jones et Nasdaq 100. Il examine les périodes 2000, 2008, 2020 et 2022 et rapporte la fréquence de signal. Il ne teste pas la macro, la largeur de marché, ni une stratégie d'exécution/portefeuille LQQ; c'est une première étape de validation, pas une preuve de rentabilité. Le workflow `Weekly Market Guard backtest` s'exécute chaque dimanche et peut être lancé manuellement. Les résultats sont publiés dans `data/backtest.json` et le tableau de bord.
