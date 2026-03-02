# Description  
L'application permet aux utilisateurs de générer des reçus de dons au format PDF, en fonction d'entrées comme le nom de l'association, le nom du donateur et le montant du don.  
Cependant, elle ne filtre pas correctement les données saisies par l'utilisateur avant de les intégrer dans le contenu du PDF.  
Il est ainsi possible d'injecter du **code JavaScript** directement dans le fichier PDF généré.  
Lors de l'ouverture du PDF avec un lecteur prenant en charge JavaScript (comme **pdf.js** ou certains navigateurs), cela conduit à une **exécution arbitraire de code JavaScript**.

---

# Exploitation  
1. Accéder à la page "Générer un reçu de don".
2. Dans le champ "Nom du donateur", entrer la charge utile suivante :
   ```javascript
   '; } app.alert("CODE INJECTION"); //
   ```
![YWH R563084 image](YWH-R563084-image.png)
3. Soumettre le formulaire pour générer le reçu.
4. Télécharger et ouvrir le PDF généré avec un navigateur ou un lecteur PDF supportant JavaScript.
5. Observer l'exécution du JavaScript sous forme d'une alerte affichée.


![YWH R563087 image](YWH-R563087-image.png)
---

# PoC  
### Charge utile utilisée :
```javascript
'; } app.alert("CODE INJECTION"); //
```

### Étapes :
- Soumettre cette charge utile dans le champ "Nom du donateur".
- Générer et télécharger le reçu PDF.
- À l'ouverture du fichier, le code JavaScript s'exécute automatiquement.
![YWH R563090 image](YWH-R563090-image.png)
---

## Risque  
- **Dropper de malware** : Un attaquant pourrait générer un PDF malveillant capable de télécharger et exécuter un malware à l'ouverture.
- **Phishing** : Le PDF pourrait afficher une fausse page de connexion ou une interface trompeuse pour voler des identifiants.
- **Exécution dans le contexte du navigateur** : Si le PDF est ouvert dans un navigateur (par ex. via pdf.js), cela permettrait de détourner des sessions, voler des cookies ou rediriger vers des sites malveillants.
- **Impact sur la réputation** : Les PDFs générés par votre plateforme pourraient être détectés comme malveillants par les antivirus ou les navigateurs, ce qui entacherait gravement votre image de marque.

---

## Remédiation  
- **Sanitisation des entrées** : Filtrer correctement toutes les entrées utilisateur avant de les intégrer dans le contenu du PDF.
- **Désactiver JavaScript** : Si ce n'est pas nécessaire, désactiver totalement la possibilité d'exécuter du JavaScript dans les PDFs générés.
- **Utiliser un Content Security Policy (CSP)** : Si vous utilisez un visualiseur web tel que pdf.js, appliquer une CSP stricte pour limiter les risques d'exécution de scripts.
- **Validation serveur** : Implémenter une validation côté serveur pour refuser toute entrée suspecte contenant du code potentiellement malveillant.

# Risk

This vulnerability could compromise the confidentiality, integrity, or availability of user data and application functionality.


# Remediation

Proper input validation, access controls, and security best practices should be applied to mitigate this vulnerability.

# Author
ESNA
