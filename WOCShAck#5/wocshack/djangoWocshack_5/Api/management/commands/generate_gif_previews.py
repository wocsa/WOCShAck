"""
Management command to generate animated GIF previews for CSS loaders.

This command renders each CSS loader in a headless browser, captures multiple frames
of the animation, and assembles them into animated GIF files. The GIF previews are
stored in the media directory and referenced by the Css model's preview_gif field.

This approach prevents CSS source code scraping by displaying GIF images in the shop
instead of live CSS code rendered in iframes.

Uses multi-threaded generation with a pool of Chrome workers for fast parallel processing.

Usage:
    python manage.py generate_gif_previews              # Generate for all CSS without previews
    python manage.py generate_gif_previews --force       # Regenerate all previews
    python manage.py generate_gif_previews --css-id UUID # Generate for specific CSS file
    python manage.py generate_gif_previews --workers 4   # Use 4 parallel Chrome instances
"""
import io
import os
import sys
import time
import base64
import tempfile
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.conf import settings

from Api.models import Css

logger = logging.getLogger(__name__)

# GIF generation parameters
GIF_WIDTH = 300          # Width of the GIF in pixels
GIF_HEIGHT = 300         # Height of the GIF in pixels
GIF_FRAMES = 20          # Number of frames to capture
GIF_FRAME_DELAY_MS = 100 # Delay between frames in milliseconds (100ms = 10fps)
GIF_DURATION_S = 2.0     # Total animation capture duration in seconds
GIF_LOOP = 0             # 0 = infinite loop


def build_html_for_css(css_content, body_html=None):
    """
    Build a self-contained HTML page that renders
    the CSS loader animation. Uses a minimal HTML structure matching the
    shop preview style.
    """
    body = body_html if body_html else '<div class="loader"></div>'
    # Escape any problematic characters for embedding in HTML
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


class Command(BaseCommand):
    help = 'Generate animated GIF preview images for CSS loaders to prevent source code scraping.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate GIF previews even for CSS files that already have one.',
        )
        parser.add_argument(
            '--css-id',
            type=str,
            help='Generate GIF for a specific CSS file by UUID.',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=4,
            help='Number of parallel Chrome instances for GIF generation (default: 4).',
        )
        parser.add_argument(
            '--width',
            type=int,
            default=GIF_WIDTH,
            help=f'GIF width in pixels (default: {GIF_WIDTH}).',
        )
        parser.add_argument(
            '--height',
            type=int,
            default=GIF_HEIGHT,
            help=f'GIF height in pixels (default: {GIF_HEIGHT}).',
        )
        parser.add_argument(
            '--frames',
            type=int,
            default=GIF_FRAMES,
            help=f'Number of frames to capture (default: {GIF_FRAMES}).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually generating.',
        )

    def handle(self, *args, **options):
        force = options['force']
        css_id = options.get('css_id')
        num_workers = options['workers']
        width = options['width']
        height = options['height']
        num_frames = options['frames']
        dry_run = options['dry_run']

        # Ensure media directory exists
        previews_dir = Path(settings.MEDIA_ROOT) / 'css_previews'
        previews_dir.mkdir(parents=True, exist_ok=True)

        # Get CSS files to process
        if css_id:
            try:
                css_files = Css.objects.filter(id=css_id)
                if not css_files.exists():
                    raise CommandError(f'CSS file with ID {css_id} not found.')
            except Exception as e:
                raise CommandError(f'Invalid CSS ID: {e}')
        elif force:
            css_files = Css.objects.all()
        else:
            css_files = Css.objects.filter(
                preview_gif__isnull=True
            ) | Css.objects.filter(
                preview_gif=''
            )

        total = css_files.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No CSS files need GIF previews generated.'))
            return

        self.stdout.write(f'Found {total} CSS file(s) to process.')

        if dry_run:
            for css in css_files:
                self.stdout.write(f'  Would generate: {css.name} ({css.id})')
            self.stdout.write(self.style.SUCCESS(f'Dry run complete. {total} GIFs would be generated.'))
            return

        # Try to import Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            HAS_SELENIUM = True
        except ImportError:
            HAS_SELENIUM = False

        # Clamp workers to number of items
        num_workers = min(num_workers, total)

        start_time = time.time()

        if HAS_SELENIUM:
            self.stdout.write(f'Using Selenium + headless Chrome with {num_workers} parallel worker(s).')
            success, failed = self._generate_with_selenium(
                css_files, width, height, num_frames, num_workers
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Selenium not available. Falling back to placeholder GIF generation.\n'
                    'Install selenium and chromium/chrome for animated GIF previews:\n'
                    '  pip install selenium\n'
                    '  apt-get install chromium-browser (or install Chrome)\n'
                )
            )
            success, failed = self._generate_placeholders(css_files, width, height, num_workers)

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(
            f'\nGIF generation complete: {success} succeeded, {failed} failed '
            f'out of {total} total in {elapsed:.1f}s.'
        ))

    def _create_chrome_driver(self, width, height):
        """Create and return a new headless Chrome WebDriver instance."""
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

    def _generate_with_selenium(self, css_files, width, height, num_frames, num_workers):
        """
        Generate animated GIF previews using multiple parallel
        headless Chrome instances. Each worker thread gets its own WebDriver.
        """
        import threading
        from PIL import Image

        # Materialize the queryset into a list of tuples
        # so each thread can work independently without sharing DB cursors
        css_items = list(css_files.values_list('id', 'name', 'css_content', 'html_template'))
        total = len(css_items)

        # Test that Chrome works before spawning workers
        try:
            test_driver = self._create_chrome_driver(width, height)
            test_driver.quit()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to start Chrome WebDriver: {e}'))
            self.stderr.write('Falling back to placeholder GIF generation.')
            return self._generate_placeholders(css_files, width, height, num_workers)

        success_count = 0
        failed_count = 0
        counter_lock = threading.Lock()
        progress_idx = [0]  # mutable counter for progress tracking

        def _worker_generate_gif(css_id, css_name, css_content, html_template):
            """Worker function: create driver, render CSS, capture frames, save GIF."""
            nonlocal success_count, failed_count

            driver = None
            try:
                driver = self._create_chrome_driver(width, height)

                html_content = build_html_for_css(css_content, body_html=html_template)
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.html', delete=False, encoding='utf-8'
                ) as tmp:
                    tmp.write(html_content)
                    tmp_path = tmp.name

                try:
                    driver.get(f'file://{tmp_path}')
                    time.sleep(0.3)

                    # Capture frames
                    frames = []
                    frame_delay = GIF_DURATION_S / num_frames
                    for _ in range(num_frames):
                        png_data = driver.get_screenshot_as_png()
                        img = Image.open(io.BytesIO(png_data))
                        img = img.resize((width, height), Image.LANCZOS)
                        img = img.convert('RGBA')
                        frames.append(img)
                        time.sleep(frame_delay)

                    if not frames:
                        with counter_lock:
                            failed_count += 1
                            progress_idx[0] += 1
                            self.stdout.write(f'  [{progress_idx[0]}/{total}] {css_name}... NO FRAMES')
                        return

                    # Assemble GIF
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

                    # Save to DB (thread-safe: each item updates its own row)
                    css_obj = Css.objects.get(id=css_id)
                    gif_filename = f'{css_id}.gif'
                    gif_content = ContentFile(gif_buffer.getvalue())
                    css_obj.preview_gif.save(gif_filename, gif_content, save=True)

                    gif_size_kb = len(gif_buffer.getvalue()) / 1024
                    with counter_lock:
                        success_count += 1
                        progress_idx[0] += 1
                        self.stdout.write(
                            f'  [{progress_idx[0]}/{total}] {css_name}... '
                            f'OK ({len(frames)} frames, {gif_size_kb:.1f} KB)'
                        )

                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            except Exception as e:
                with counter_lock:
                    failed_count += 1
                    progress_idx[0] += 1
                    self.stdout.write(f'  [{progress_idx[0]}/{total}] {css_name}... FAILED: {e}')

            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        # Run workers in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for css_id, css_name, css_content, html_template in css_items:
                fut = executor.submit(_worker_generate_gif, css_id, css_name, css_content, html_template)
                futures.append(fut)

            # Wait for all to complete
            for fut in as_completed(futures):
                # Exceptions are already handled inside the worker
                pass

        return success_count, failed_count

    def _generate_placeholders(self, css_files, width, height, num_workers):
        """
        Generate placeholder GIF images when Selenium is not available.
        Uses thread pool for parallel generation.
        """
        import threading
        from PIL import Image, ImageDraw

        css_items = list(css_files.values_list('id', 'name'))
        total = len(css_items)

        success_count = 0
        failed_count = 0
        counter_lock = threading.Lock()
        progress_idx = [0]

        def _worker_placeholder(css_id, css_name):
            nonlocal success_count, failed_count
            try:
                frames = []
                for frame_num in range(8):
                    img = Image.new('RGB', (width, height), (26, 26, 46))
                    draw = ImageDraw.Draw(img)
                    center_x, center_y = width // 2, height // 2
                    offset = frame_num * 5

                    for i in range(5):
                        radius = 20 + i * 15 + offset % 15
                        color = (102, 126, 234)
                        draw.ellipse(
                            [center_x - radius, center_y - radius,
                             center_x + radius, center_y + radius],
                            outline=color, width=3
                        )

                    try:
                        draw.text((center_x, height - 30), 'CSS Loader',
                                  fill=(150, 150, 180), anchor='mm')
                    except Exception:
                        pass

                    frames.append(img.quantize(colors=128, method=Image.MEDIANCUT))

                gif_buffer = io.BytesIO()
                frames[0].save(
                    gif_buffer, format='GIF', save_all=True,
                    append_images=frames[1:], duration=150, loop=0, optimize=True,
                )

                css_obj = Css.objects.get(id=css_id)
                gif_content = ContentFile(gif_buffer.getvalue())
                css_obj.preview_gif.save(f'{css_id}.gif', gif_content, save=True)

                gif_size_kb = len(gif_buffer.getvalue()) / 1024
                with counter_lock:
                    success_count += 1
                    progress_idx[0] += 1
                    self.stdout.write(
                        f'  [{progress_idx[0]}/{total}] {css_name}... OK (placeholder, {gif_size_kb:.1f} KB)'
                    )

            except Exception as e:
                with counter_lock:
                    failed_count += 1
                    progress_idx[0] += 1
                    self.stdout.write(f'  [{progress_idx[0]}/{total}] {css_name}... FAILED: {e}')

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_worker_placeholder, cid, cname) for cid, cname in css_items]
            for fut in as_completed(futures):
                pass

        return success_count, failed_count
