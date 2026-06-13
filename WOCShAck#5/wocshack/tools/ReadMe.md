TBox - Caricatural Email Provider

TBox is a fun and exaggerated email provider built for CTF (Capture The Flag) challenges. It allows you to simulate sending emails with a simple GET request.
How It Works

To send an email using TBox, just use the following URL format:

http://localhost/send?source=your_email@example.com&destination=recipient@example.com&subject=Test%20Subject&content=This%20is%20the%20email%20content

    source: The sender's email.
    destination: The recipient's email.
    subject: The subject of the email.
    content: The content/body of the email.

License

This project is licensed under the MIT License.