# Market Guard — tableau de bord automatisé

Application web française de surveillance du risque de marché. Les données sont collectées par GitHub Actions après la clôture américaine, puis publiées via GitHub Pages.

## Publication
Dans **Settings → Pages**, choisir **GitHub Actions** comme source si ce n'est pas déjà configuré. Dans **Actions**, lancer **Refresh Market Guard data → Run workflow**. L'URL attendue est https://asbai92.github.io/market-guard/.

## Sources et critères
- Yahoo Finance : S&P 500, Dow Jones et Nasdaq 100.
- FRED : spread 10 ans–2 ans, inscriptions chômage, taux de chômage, charge-offs bancaires (CORALACBS), CPI et Fed Funds.
- DeanFinancials : ligne A/D calculée sur l'univers S&P 500. C'est un proxy, pas la ligne NYSE/Dow Jones exacte. Les données A/D de plus de quatre jours sont considérées indisponibles.
- Technique : MM30 semaines, pente de la MM30, supports hebdomadaires sur 26 semaines et cassure confirmée sur deux clôtures hebdomadaires.

La logique reprend les éléments décrits dans les deux articles BlogBourse : dégradation de l'A/D, inflation et taux, puis confirmation technique par les grands indices. Le score, les seuils de chômage/charge-offs/inflation et certains choix de calcul sont des règles opérationnelles expérimentales, pas des seuils officiels de l'auteur. Aucun backtest ni pouvoir prédictif n'est revendiqué.

## Actualisation et alertes
Le workflow s'exécute du lundi au vendredi à 23:30 UTC et peut être lancé manuellement dans Actions. Le bouton du site recharge les dernières données publiées ; il ne déclenche pas une collecte. Alertes Telegram facultatives via les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`.

## Sécurité et limites
Le site est statique et ne demande aucune donnée personnelle. Aucune transaction n'est exécutée. Une collecte incomplète produit UNKNOWN. Ne pas utiliser ce verdict seul pour décider de vendre, en particulier un ETF à levier comme LQQ.