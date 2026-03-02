# Description  
Dear,

When we access your website, you use the ?page= parameter to render a specific file.
However, this field only has little protections, and we are able to read arbitrary files from the system.

# Exploitation  
Access the webpage https://<IP>/index.php?page=/<path> and replace <path> with the full path of the file you want to access (for example: https://<IP>/index.php?page=/var/www/html/startbootstrap-sb-admin-2-gh-pages/LICENSE)

# PoC

See Exploitation section above.

# Risk
A protection is enabled to prevent anyone to access /etc.
The user who is running the webserver doesn't seem to have a lot of privileges: the user cannot read log files (I've tested /var/log/nginx/error.log and /var/log/nginx/access.log), or access to standard Linux files.
If any sensible file is readable by this user outside of /etc, a malicious user could leak it.

# Remediation  
To remediate the issue, you can use the realpath() function in PHP to get the full path of the file that the user is trying to access, and then verify if it belongs to a certain list of allowed files or directories (like /var/www/html/)
# Author
sdbfhzebigfez
