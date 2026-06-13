"""
CSS utility tools for minification, beautification, validation, and prefixing.
"""
import re


def minify_css(css_text):
    """Strip comments, collapse whitespace, and compress CSS."""
    if not css_text:
        return ''
    # Remove comments
    result = re.sub(r'/\*[\s\S]*?\*/', '', css_text)
    # Remove newlines and extra whitespace
    result = re.sub(r'\s+', ' ', result)
    # Remove spaces around punctuation
    result = re.sub(r'\s*([{}:;,>~+])\s*', r'\1', result)
    # Remove trailing semicolons before closing braces
    result = result.replace(';}', '}')
    # Remove leading/trailing whitespace
    result = result.strip()
    return result


def beautify_css(css_text):
    """Reformat CSS with proper indentation and spacing."""
    if not css_text:
        return ''
    # First minify to normalize
    css = minify_css(css_text)
    result = []
    indent = 0
    i = 0
    while i < len(css):
        char = css[i]
        if char == '{':
            result.append(' {\n')
            indent += 1
            result.append('    ' * indent)
        elif char == '}':
            indent = max(0, indent - 1)
            result.append('\n')
            result.append('    ' * indent)
            result.append('}\n')
            if indent == 0:
                result.append('\n')
            else:
                result.append('    ' * indent)
        elif char == ';':
            result.append(';\n')
            result.append('    ' * indent)
        elif char == ',':
            result.append(',\n')
            result.append('    ' * indent)
        else:
            result.append(char)
        i += 1
    # Clean up trailing whitespace on lines
    lines = ''.join(result).split('\n')
    lines = [line.rstrip() for line in lines]
    # Remove consecutive blank lines
    cleaned = []
    prev_blank = False
    for line in lines:
        if line == '':
            if not prev_blank:
                cleaned.append(line)
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return '\n'.join(cleaned).strip() + '\n'


def validate_css(css_text):
    """Parse CSS and return a list of errors/warnings."""
    errors = []
    warnings = []
    if not css_text:
        return {'errors': ['Empty CSS input'], 'warnings': []}

    # Check balanced braces
    open_count = css_text.count('{')
    close_count = css_text.count('}')
    if open_count != close_count:
        errors.append(f"Unbalanced braces: {open_count} opening vs {close_count} closing")

    # Check for unclosed comments
    comment_opens = len(re.findall(r'/\*', css_text))
    comment_closes = len(re.findall(r'\*/', css_text))
    if comment_opens != comment_closes:
        errors.append(f"Unclosed comment: {comment_opens} open vs {comment_closes} close")

    # Check for common property errors
    lines = css_text.split('\n')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip empty lines, comments, selectors, and braces
        if not stripped or stripped.startswith('/*') or stripped.startswith('*') or stripped.endswith('{') or stripped == '}':
            continue
        # Lines inside rules should have colons
        if '{' not in stripped and '}' not in stripped and ':' not in stripped and stripped not in ('@', ''):
            if not stripped.startswith('@') and not stripped.startswith('//'):
                warnings.append(f"Line {i}: Missing colon — possibly malformed property: '{stripped[:60]}'")

    # Check for !important overuse
    important_count = len(re.findall(r'!important', css_text))
    if important_count > 5:
        warnings.append(f"Excessive use of !important ({important_count} occurrences)")

    return {'errors': errors, 'warnings': warnings}


# Common CSS properties that need vendor prefixes
PREFIXED_PROPERTIES = {
    'transform': ['-webkit-transform', '-ms-transform'],
    'transition': ['-webkit-transition', '-o-transition'],
    'animation': ['-webkit-animation'],
    'animation-name': ['-webkit-animation-name'],
    'animation-duration': ['-webkit-animation-duration'],
    'animation-delay': ['-webkit-animation-delay'],
    'animation-fill-mode': ['-webkit-animation-fill-mode'],
    'flex': ['-webkit-flex', '-ms-flex'],
    'flex-direction': ['-webkit-flex-direction', '-ms-flex-direction'],
    'flex-wrap': ['-webkit-flex-wrap', '-ms-flex-wrap'],
    'justify-content': ['-webkit-justify-content'],
    'align-items': ['-webkit-align-items', '-ms-flex-align'],
    'align-self': ['-webkit-align-self', '-ms-flex-item-align'],
    'user-select': ['-webkit-user-select', '-moz-user-select', '-ms-user-select'],
    'appearance': ['-webkit-appearance', '-moz-appearance'],
    'backdrop-filter': ['-webkit-backdrop-filter'],
    'background-clip': ['-webkit-background-clip'],
    'box-shadow': ['-webkit-box-shadow'],
    'border-radius': ['-webkit-border-radius'],
}


def prefix_css(css_text):
    """Add vendor prefixes for common CSS properties."""
    if not css_text:
        return ''
    lines = css_text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        added_prefix = False
        for prop, prefixes in PREFIXED_PROPERTIES.items():
            # Match "property:" at the start of the trimmed line (not already prefixed)
            pattern = re.compile(r'^' + re.escape(prop) + r'\s*:')
            if pattern.match(stripped) and not stripped.startswith('-'):
                indent = line[:len(line) - len(line.lstrip())]
                value_part = stripped[len(prop):]  # includes ": value;"
                for prefix in prefixes:
                    result.append(f"{indent}{prefix}{value_part}")
                result.append(line)
                added_prefix = True
                break
        if not added_prefix:
            result.append(line)
    return '\n'.join(result)
