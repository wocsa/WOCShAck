# Description  

Une vulnérabilité de type Information Disclosure via HTTP Headers a été identifiée.
Quel que soit l'endpoint consulté sur le domaine <IP>, l'application renvoie dans les en-têtes de réponse HTTP des informations sensibles concernant son environnement serveur, notamment :

Le serveur web utilisé (Server: nginx)

La version de PHP (X-Powered-By: PHP/8.2.28)

Cette fuite d'information est systématique et peut permettre à un attaquant d'identifier les technologies et versions utilisées, facilitant ainsi la recherche et l'exploitation de vulnérabilités connues.

# Exploitation  

1. Envoyer une requête HTTP classique vers n'importe quelle page du domaine.

1. Examiner les en-têtes HTTP de la réponse avec un proxy

1. Observer que les headers Server et X-Powered-By exposent respectivement le serveur web et la version de PHP utilisée.

1. Aucune authentification ni action particulière n'est nécessaire pour accéder à ces informations.

# PoC  

Requête (exemple) :
```http
GET /index.php?page=analytics/analytics.php HTTP/2
Host: <IP>
```
Mais cela fonctionne également sur d'autres pages.

Réponse (en-têtes HTTP) :
```http
HTTP/2 200 OK
Server: nginx
X-Powered-By: PHP/8.2.28
```
# Risk

Permet à un attaquant de cibler précisément des vulnérabilités affectant nginx et PHP (8.2.28).

Réduit significativement la phase de reconnaissance d'une attaque ciblée.

Peut être utilisée pour affiner des attaques basées sur des exploits publics, 0day ou brute-force ciblé. 


# Remediation  

Supprimer ou masquer les en-têtes HTTP sensibles :

Dans nginx :
`server_tokens off;`

Dans PHP :
    `expose_php = Off`

Adopter une politique de minimisation des informations exposées dans toutes les réponses HTTP.
# Author
CESI
