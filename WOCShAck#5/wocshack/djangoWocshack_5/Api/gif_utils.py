"""
Reusable GIF generation for CSS loaders.

Renders CSS in a headless Chrome browser, captures animation frames,
and assembles them into an animated GIF. Used by the editor save endpoint
and the publish flow to auto-generate preview GIFs.
"""
import io
import os
import time
import tempfile
import logging

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

GIF_WIDTH = 300
GIF_HEIGHT = 300
GIF_FRAMES = 20
GIF_FRAME_DELAY_MS = 100
GIF_DURATION_S = 2.0
GIF_LOOP = 0


def build_html_for_css(css_content, body_html=None):
    """Build a self-contained HTML page that renders the CSS animation.

    Args:
        css_content: Raw CSS string to embed.
        body_html: Optional HTML snippet to place in the body. Defaults to
                   ``<div class="loader"></div>`` to match the live editor.
    """
    body = body_html if body_html else '<div class="loader"></div>'
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}
body {{
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    overflow: hidden;
}}
{css_content}
</style>
</head>
<body>
{body}
</body>
</html>"""


def _create_chrome_driver(width=GIF_WIDTH, height=GIF_HEIGHT):
    """Create and return a headless Chrome WebDriver instance."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument(f'--window-size={width},{height}')
    chrome_options.add_argument('--hide-scrollbars')
    chrome_options.add_argument('--force-device-scale-factor=1')

    chrome_bin = os.environ.get('CHROME_BIN')
    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin

    chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
    if chromedriver_path and os.path.exists(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    driver.set_window_size(width, height)
    return driver


def generate_gif_for_css(css_content, filename_prefix, body_html=None):
    """
    Generate an animated GIF preview for the given CSS content.

    Args:
        css_content: The raw CSS string to render.
        filename_prefix: Used to build the output filename (e.g. a UUID).
        body_html: Optional HTML body snippet. Defaults to ``<div class="loader"></div>``.

    Returns:
        (ContentFile, filename) on success, or None on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.error('Pillow is not installed — cannot generate GIF.')
        return None

    driver = None
    try:
        driver = _create_chrome_driver()

        html_content = build_html_for_css(css_content, body_html=body_html)
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False, encoding='utf-8'
        ) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name

        try:
            driver.get(f'file://{tmp_path}')
            time.sleep(0.3)

            frames = []
            frame_delay = GIF_DURATION_S / GIF_FRAMES
            for _ in range(GIF_FRAMES):
                png_data = driver.get_screenshot_as_png()
                img = Image.open(io.BytesIO(png_data))
                img = img.resize((GIF_WIDTH, GIF_HEIGHT), Image.LANCZOS)
                img = img.convert('RGBA')
                frames.append(img)
                time.sleep(frame_delay)

            if not frames:
                logger.warning('No frames captured for %s', filename_prefix)
                return None

            gif_buffer = io.BytesIO()
            gif_frames = []
            for frame in frames:
                rgb_frame = Image.new('RGB', frame.size, (26, 26, 46))
                rgb_frame.paste(frame, mask=frame.split()[3] if frame.mode == 'RGBA' else None)
                gif_frames.append(rgb_frame.quantize(colors=256, method=Image.MEDIANCUT))

            gif_frames[0].save(
                gif_buffer,
                format='GIF',
                save_all=True,
                append_images=gif_frames[1:],
                duration=GIF_FRAME_DELAY_MS,
                loop=GIF_LOOP,
                optimize=True,
            )

            filename = f'{filename_prefix}.gif'
            return (ContentFile(gif_buffer.getvalue()), filename)

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except Exception as e:
        logger.exception('GIF generation failed for %s: %s', filename_prefix, e)
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
