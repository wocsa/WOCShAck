"""
Markdown utilities for forum posts.

Markdown processing with proper sanitization
while allowing safe formatting.
"""
import markdown
from django.utils.html import escape
from django.utils.safestring import mark_safe
import re


def render_markdown(content):
    """
    Render markdown content safely.
    
    This function:
    1. Escapes HTML in code blocks to prevent XSS
    2. Converts markdown to HTML using python-markdown
    3. Sanitizes the output by removing dangerous HTML tags and attributes
    4. Returns safe HTML that can be rendered in templates
    
    Args:
        content (str): Markdown content to render
        
    Returns:
        str: Safe HTML content
    """
    if not content:
        return ""
    
    # First, escape HTML in code blocks to prevent XSS in code
    # This preserves the code content but prevents execution
    protected_content = protect_code_blocks(content)
    
    # Convert markdown to HTML
    html_content = markdown.markdown(
        protected_content,
        extensions=[
            'markdown.extensions.extra',  # Tables, footnotes, etc.
            'markdown.extensions.codehilite',  # Syntax highlighting
            'markdown.extensions.toc',  # Table of contents
        ]
    )
    
    # Sanitize the HTML to remove dangerous tags and attributes
    safe_html = sanitize_html(html_content)
    
    # Convert @username mentions to profile links
    safe_html = convert_mentions_to_links(safe_html)
    
    return mark_safe(safe_html)


def protect_code_blocks(content):
    """
    Protect code blocks from HTML injection.
    
    This function escapes HTML entities within code blocks to prevent
    XSS attacks while preserving the code display.
    
    Args:
        content (str): Content with potential code blocks
        
    Returns:
        str: Content with protected code blocks
    """
    # Pattern to match both inline and block code
    # Inline: `code`
    # Block: ```language\ncode\n```
    
    def escape_code_match(match):
        """Escape HTML entities in code content"""
        # Check if this is a block code match (has language group)
        if len(match.groups()) >= 2 and match.group(1) is not None:
            # Block code: ```language\ncode\n```
            language = match.group(1)
            code_content = match.group(2)
            return f"```{language}\n{escape(code_content)}\n```"
        else:
            # Inline code: `code`
            code_content = match.group(1) if len(match.groups()) >= 1 else match.group(0)
            return f"`{escape(code_content)}`"
    
    # Protect block code (```language\ncode\n```)
    content = re.sub(
        r'```(\w*)\n([\s\S]*?)```',
        escape_code_match,
        content,
        flags=re.DOTALL
    )
    
    # Protect inline code (`code`)
    content = re.sub(
        r'`([^`]+)`',
        escape_code_match,
        content
    )
    
    return content


def sanitize_html(html):
    """
    Sanitize HTML to prevent XSS.
    
    This function removes dangerous HTML tags and attributes while
    preserving safe formatting elements.
    
    Args:
        html (str): HTML content to sanitize
        
    Returns:
        str: Sanitized HTML content
    """
    # List of allowed tags (basic formatting only)
    allowed_tags = {
        'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins',
        'ul', 'ol', 'li', 'dl', 'dt', 'dd',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'blockquote', 'code', 'pre', 'tt',
        'a', 'img',  # These need special attribute handling
    }
    
    # List of allowed attributes by tag
    allowed_attributes = {
        'a': {'href', 'title', 'rel'},
        'img': {'src', 'alt', 'title', 'width', 'height'},
    }
    
    # Remove all tags except allowed ones
    sanitized = re.sub(
        r'<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>',
        lambda m: handle_tag(m, allowed_tags, allowed_attributes),
        html
    )
    
    # Remove dangerous protocols from URLs
    sanitized = re.sub(
        r'(href|src)=["\'](javascript:|data:|vbscript:)',
        r'\1="#"',
        sanitized,
        flags=re.IGNORECASE
    )
    
    # Add rel="nofollow noopener" to external links for security
    sanitized = re.sub(
        r'<a\s+([^>]*)href="([^"]*)"([^>]*)>',
        add_safe_link_attributes,
        sanitized,
        flags=re.IGNORECASE
    )
    
    return sanitized


def handle_tag(match, allowed_tags, allowed_attributes):
    """Handle individual HTML tags during sanitization"""
    closing_slash, tag_name, attributes = match.groups()
    tag_name = tag_name.lower()
    
    # Remove all dangerous tags
    if tag_name not in allowed_tags:
        return ''
    
    # Handle allowed attributes
    if tag_name in allowed_attributes:
        sanitized_attrs = sanitize_attributes(
            attributes, 
            allowed_attributes[tag_name]
        )
    else:
        sanitized_attrs = ''
    
    return f'<{closing_slash}{tag_name}{sanitized_attrs}>'


def sanitize_attributes(attributes, allowed_attrs):
    """Sanitize HTML attributes"""
    sanitized = []
    
    # Simple attribute parsing (not comprehensive, but secure)
    # This is a basic implementation - for production, consider using a proper HTML parser
    for attr_match in re.finditer(
        r'(\w+)\s*=\s*(["\'])(.*?)\2',
        attributes
    ):
        attr_name, quote, attr_value = attr_match.groups()
        attr_name = attr_name.lower()
        
        if attr_name in allowed_attrs:
            # Sanitize attribute value
            if attr_name in {'href', 'src'}:
                sanitized_value = sanitize_url(attr_value)
            else:
                sanitized_value = escape(attr_value)
            
            sanitized.append(f'{attr_name}="{sanitized_value}"')
    
    return ' ' + ' '.join(sanitized) if sanitized else ''


def sanitize_url(url):
    """Sanitize URLs to prevent XSS"""
    # Remove dangerous protocols
    dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'about:', 'file:']
    
    url_lower = url.lower()
    for protocol in dangerous_protocols:
        if url_lower.startswith(protocol):
            return '#'
    
    # Basic URL validation
    if not re.match(r'^[a-zA-Z]+:', url):
        # Relative URL - allow but ensure it's safe
        return url
    
    return url


def add_safe_link_attributes(match):
    """Add security attributes to links"""
    before_href, href_value, after_href = match.groups()
    
    # Check if rel attribute already exists
    if 'rel=' in before_href.lower() or 'rel=' in after_href.lower():
        # If rel exists, ensure it includes nofollow and noopener
        if 'nofollow' not in after_href and 'noopener' not in after_href:
            after_href += ' rel="nofollow noopener"'
    else:
        # Add rel attribute
        after_href += ' rel="nofollow noopener"'
    
    return f'<a {before_href}href="{href_value}"{after_href}>'


def convert_mentions_to_links(html):
    """
    Convert @username mentions to profile links.
    
    This function finds @username patterns in the HTML content and converts them
    to links pointing to the user's forum profile page.
    
    Args:
        html (str): HTML content containing @username mentions
        
    Returns:
        str: HTML content with @username mentions converted to links
    """
    # Pattern to match @username (alphanumeric, underscore, hyphen)
    # This matches the same pattern used in parse_mentions function
    mention_pattern = re.compile(r'@([a-zA-Z0-9_-]{1,150})\b')
    
    def replace_mention(match):
        username = match.group(1)
        # Create a link to the user's forum profile
        return f'<a href="/forum/user/{username}/" class="mention-link">@{username}</a>'
    
    # Replace all @username mentions with profile links
    return mention_pattern.sub(replace_mention, html)