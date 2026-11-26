"""
Database setup — Django users, profiles, API keys, bank accounts.

The Django DB ships in the repo at wocshack/djangoWocshack_5/db.sqlite3 as a
clean seeded baseline (no longer kept out of version control). Re-running this
script is idempotent: get_or_create on Django objects, is_user_existing on
banking accounts. Safe to invoke against the committed DB without producing
duplicates. To regenerate the baseline from scratch, delete db.sqlite3 and run
setup/run_all.py.
"""
import os
import django
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoWocshack_5.settings.development')
django.setup()

from django.contrib.auth.models import User
from Account.models import UserProfile, PurchasedFeature
from Api.models import Css, ApiKey
from Bank.Utils import external_calls

# Add the VRC_Banking_System_Backend to the path for direct database access
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'VRC_Banking_System_Backend'))

print("=" * 80)
print("V.R.C Database Setup Script")
print("Centralizes creation of Django users, profiles, bank accounts, and API keys")
print("=" * 80)
print()


def create_superuser():
    """Create admin superuser with Django account and bank account"""
    print("[1/5] Creating Superuser...")
    print("-" * 80)

    username = 'admin'
    email = 'admin@tbox.traced'
    password = 'X#9kLm$P2v@nQ8w!ZjRe'
    bank_pin = '999999'
    initial_balance = 100000.00

    # Create Django user
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_superuser(username=username, email=email, password=password)
        print(f"[+] Django superuser '{username}' created successfully.")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
    else:
        user = User.objects.get(username=username)
        print(f"✓ Django superuser '{username}' already exists.")

    # Ensure admin profile is activated
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_activated = True
    profile.save()

    # Create admin API key
    admin_api_key = "vrc_8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
    ApiKey.objects.get_or_create(
        user=user,
        name='Default Key',
        defaults={
            'key_hash': ApiKey.hash_key(admin_api_key),
            'key_prefix': admin_api_key[:8],
            'is_active': True,
            'scopes': ['read', 'write', 'admin']
        }
    )

    # Create bank account
    try:
        # First check if user already exists in bank
        if external_calls.is_user_existing(user.id):
            print(f"  - Bank account already exists for '{username}' (User ID: {user.id})")
            # Get current balance
            current_balance = external_calls.get_user_balance(user.id)
            if current_balance is not None:
                print(f"    Current balance: ${current_balance:.2f}")
        else:
            # User doesn't exist, create new account
            result = external_calls.add_user(user_id=user.id, pin=bank_pin)
            if result and result.get('status') == 'success':
                print(f"[+] Bank account created for '{username}'")
                print(f"  User ID: {user.id}")
                print(f"  PIN: {bank_pin}")
                print(f"  Initial Balance: ${initial_balance:.2f}")

                # Set initial balance
                time.sleep(1)  # Wait for backend
                external_calls.set_balance(user_id=user.id, amount=initial_balance)
            elif result and result.get('error'):
                print(f"  [W] Warning: Could not create bank account: {result.get('error')}")
            elif result is None:
                print(f"  [W] Warning: Banking backend timed out (user may already exist)")
            else:
                print(f"  [W] Warning: Could not connect to banking backend")
    except Exception as e:
        print(f"  [W] Warning: Bank account creation failed: {e}")

    print()


def assign_user_roles():
    """Assign appropriate roles to users based on their biographies and profiles"""
    print("[2.5/5] Assigning User Roles...")
    print("-" * 80)

    # Get all users
    users = User.objects.all()
    staff_assigned = 0
    developer_assigned = 0
    verified_assigned = 0

    for user in users:
        if user.is_superuser:
            print(f"  - {user.username}: Admin (superuser)")
            continue

        # Get user profile
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=user)

        # Assign roles based on biography and username
        biography = profile.biography.lower() if profile.biography else ""
        username = user.username.lower()

        # Assign Staff roles to users with moderation/management backgrounds
        if any(keyword in biography for keyword in ['product manager', 'qa engineer', 'cybersecurity', 'devops']):
            if not user.is_staff:
                user.is_staff = True
                user.save()
                print(f"  ✓ {user.username}: Assigned Staff role (management background)")
                staff_assigned += 1
            else:
                print(f"  - {user.username}: Already Staff")

        # Assign Developer roles to users with development backgrounds
        elif any(keyword in biography for keyword in ['developer', 'software', 'backend', 'frontend', 'mobile app']):
            if not PurchasedFeature.has_feature(user, PurchasedFeature.FEATURE_DEVELOPER_ROLE):
                # Purchase the developer role for this user
                PurchasedFeature.objects.create(
                    user=user,
                    feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
                    price_paid=PurchasedFeature.get_price(PurchasedFeature.FEATURE_DEVELOPER_ROLE),
                    is_active=True
                )
                print(f"  ✓ {user.username}: Assigned Developer role (development background)")
                developer_assigned += 1
            else:
                print(f"  - {user.username}: Already Developer")

        # Assign Verified badges to users with design/creative backgrounds
        elif any(keyword in biography for keyword in ['designer', 'ux/ui', 'marketing', 'content creator']):
            if not PurchasedFeature.has_feature(user, PurchasedFeature.FEATURE_VERIFIED_BADGE):
                # Purchase the verified badge for this user
                PurchasedFeature.objects.create(
                    user=user,
                    feature_type=PurchasedFeature.FEATURE_VERIFIED_BADGE,
                    price_paid=PurchasedFeature.get_price(PurchasedFeature.FEATURE_VERIFIED_BADGE),
                    is_active=True
                )
                print(f"  ✓ {user.username}: Assigned Verified badge (creative background)")
                verified_assigned += 1
            else:
                print(f"  - {user.username}: Already Verified")

        else:
            print(f"  - {user.username}: Regular User")

    print(f"\n[+] Role Assignment Summary:")
    print(f"  - Staff roles assigned: {staff_assigned}")
    print(f"  - Developer roles assigned: {developer_assigned}")
    print(f"  - Verified badges assigned: {verified_assigned}")
    print()


def create_predefined_users():
    """Create predefined test users with Django accounts and bank accounts"""
    print("[2/5] Creating Predefined Users...")
    print("-" * 80)

    import csv
    csv_path = os.path.join(os.path.dirname(__file__), 'users.csv')
    PREDEFINED_USERS = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'initial_balance' in row and row['initial_balance']:
                    row['initial_balance'] = float(row['initial_balance'])
                PREDEFINED_USERS.append(row)
    except Exception as e:
        print(f"  [W] Could not read {csv_path}: {e}")
        return

    django_created = 0
    django_skipped = 0
    bank_created = 0
    bank_failed = 0

    for user_data in PREDEFINED_USERS:
        username = user_data['username']
        email = user_data['email']

        # Create Django user
        if User.objects.filter(username=username).exists():
            print(f"  - Django user '{username}' already exists")
            user = User.objects.get(username=username)
            django_skipped += 1
        elif User.objects.filter(email=email).exists():
            print(f"  - Email '{email}' already exists")
            django_skipped += 1
            continue
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=user_data.get('password', 'Tr@c3d!7BxN#m9Kw2YpL'),
                first_name=user_data['first_name'],
                last_name=user_data['last_name']
            )

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.totp_key = None
            profile.cart = '[]'
            profile.biography = user_data.get('biography', '')
            profile.is_activated = True

            avatar_filename = f"{username}.png"
            avatar_src = os.path.join(os.path.dirname(__file__), 'avatars', avatar_filename)
            if os.path.exists(avatar_src):
                import shutil
                uploads_dir = os.path.join(
                    os.path.dirname(__file__), '..', 'Account', 'static', 'uploads'
                )
                os.makedirs(uploads_dir, exist_ok=True)
                shutil.copy2(avatar_src, os.path.join(uploads_dir, avatar_filename))
                profile.picture_path = avatar_filename

            profile.save()

            # Create API key
            ApiKey.objects.get_or_create(
                user=user,
                name='Default Key',
                defaults={
                    'key_hash': ApiKey.hash_key(user_data['api_key']),
                    'key_prefix': user_data['api_key'][:8],
                    'is_active': True,
                    'scopes': ['read', 'write']
                }
            )

            print(f"  [+] Django user created: {username} ({email})")
            django_created += 1

        # Create bank account
        try:
            # First check if user already exists in bank
            if external_calls.is_user_existing(user.id):
                print(f"    - Bank account already exists for '{username}' (User ID: {user.id})")
                # Get current balance
                current_balance = external_calls.get_user_balance(user.id)
                if current_balance is not None:
                    print(f"      Current balance: ${current_balance:.2f}")
            else:
                # User doesn't exist, create new account
                result = external_calls.add_user(user_id=user.id, pin=user_data['bank_pin'])
                if result and result.get('status') == 'success':
                    print(f"    [+] Bank account created (User ID: {user.id}, PIN: {user_data['bank_pin']})")
                    bank_created += 1

                    # Set initial balance
                    time.sleep(1)  # Wait for backend
                    external_calls.set_balance(user_id=user.id, amount=user_data['initial_balance'])
                    print(f"    [+] Initial balance set: ${user_data['initial_balance']:.2f}")
                elif result and result.get('error'):
                    print(f"    [W] Bank account creation failed: {result.get('error')}")
                    bank_failed += 1
                elif result is None:
                    print(f"    [W] Banking backend timed out (user may already exist)")
                    bank_failed += 1
                else:
                    print(f"    [W] Could not connect to banking backend")
                    bank_failed += 1
        except Exception as e:
            print(f"    [W] Bank account creation failed: {e}")
            bank_failed += 1

    print(f"\n[+] Users Summary:")
    print(f"  - Django users created: {django_created}")
    print(f"  - Django users skipped: {django_skipped}")
    print(f"  - Bank accounts created: {bank_created}")
    print(f"  - Bank accounts failed: {bank_failed}")
    print()


def create_css_files():
    """Import CSS files from css_files directory"""
    print("[3/5] Importing CSS Files...")
    print("-" * 80)

    import random
    from django.db.models import Avg

    CSS_FILES_DIR = os.path.join(os.path.dirname(__file__), '..', 'css_files')

    # Price ranges for different tiers
    PRICE_RANGES = [
        (0.00, 0.00),      # Free (10% chance)
        (0.99, 4.99),      # Low tier (40% chance)
        (5.00, 9.99),      # Mid tier (30% chance)
        (10.00, 19.99),    # High tier (15% chance)
        (20.00, 49.99),    # Premium tier (5% chance)
    ]
    PRICE_WEIGHTS = [10, 40, 30, 15, 5]

    def generate_random_price():
        price_range = random.choices(PRICE_RANGES, weights=PRICE_WEIGHTS, k=1)[0]
        if price_range[0] == 0.00 and price_range[1] == 0.00:
            return 0.00
        return round(random.uniform(price_range[0], price_range[1]), 2)

    def generate_author_display_name(user):
        """Generate a professional author name from a Django user.

        Uses the user's full name (first + last) when available,
        falling back to a title-cased username.
        """
        full_name = user.get_full_name().strip()
        if full_name:
            return full_name
        # Fallback: title-case the username
        return user.username.title()

    # Check if users exist
    users = list(User.objects.all())
    if not users:
        print("  ✗ Error: No users found. Cannot create CSS files.")
        print()
        return

    # Filter out admin user - only use normal users for CSS creation
    normal_users = [user for user in users if not user.is_superuser]
    if not normal_users:
        print("  ✗ Error: No normal users found. Cannot create CSS files.")
        print()
        return

    # Check if directory exists
    if not os.path.exists(CSS_FILES_DIR):
        print(f"  ✗ Error: CSS files directory not found at {CSS_FILES_DIR}")
        print()
        return

    # Get all CSS files
    css_files = [f for f in os.listdir(CSS_FILES_DIR) if f.endswith('.css')]
    if not css_files:
        print(f"  ✗ No CSS files found in {CSS_FILES_DIR}")
        print()
        return

    print(f"  Found {len(css_files)} CSS files to import...")

    created = 0
    skipped = 0
    errors = 0

    for css_filename in css_files:
        # Generate a clean name
        name = css_filename.replace('.css', '').replace('_', ' ').replace('-', ' ')

        if Css.objects.filter(name=name).exists():
            skipped += 1
            continue

        # Read file
        css_file_path = os.path.join(CSS_FILES_DIR, css_filename)
        try:
            with open(css_file_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
        except Exception as e:
            errors += 1
            continue

        # Skip empty files
        if not css_content.strip():
            skipped += 1
            continue

        # Assign to random normal user (not admin)
        creator = random.choice(normal_users)

        # Use the creator's full name as the professional author display name
        author = generate_author_display_name(creator)

        # Generate price
        price = generate_random_price()

        # Create CSS entry
        try:
            Css.objects.create(
                name=name,
                css_content=css_content,
                author=author,
                creator=creator,
                price=price
            )
            created += 1
        except Exception as e:
            errors += 1

    print(f"\n[+] CSS Files Summary:")
    print(f"  - Created: {created}")
    print(f"  - Skipped: {skipped}")
    print(f"  - Errors:  {errors}")

    if created > 0:
        total_css = Css.objects.count()
        free_css = Css.objects.filter(price=0.00).count()
        avg_price = Css.objects.exclude(price=0.00).aggregate(avg_price=Avg('price'))['avg_price'] or 0

        print(f"\n[+] Database Statistics:")
        print(f"  - Total CSS files: {total_css}")
        print(f"  - Free CSS files: {free_css} ({free_css/total_css*100:.1f}%)")
        print(f"  - Average price (paid): ${avg_price:.2f}")
    print()


def setup_forum_categories():
    """Create default forum categories"""
    print("[5/6] Setting up Forum Categories...")
    print("-" * 80)

    from Forum.models import Category

    categories = [
        {
            'name': 'General Discussion',
            'slug': 'general',
            'description': 'General discussions about V.R.C platform and community topics.',
            'icon': 'chat-bubble-left-right',
            'order': 1,
        },
        {
            'name': 'CSS Showcase',
            'slug': 'css-showcase',
            'description': 'Share your CSS creations and get feedback from the community.',
            'icon': 'sparkles',
            'order': 2,
        },
        {
            'name': 'Help & Support',
            'slug': 'help-support',
            'description': 'Get help with using the platform or creating CSS files.',
            'icon': 'question-mark-circle',
            'order': 3,
        },
        {
            'name': 'Bug Reports',
            'slug': 'bug-reports',
            'description': 'Report bugs and issues with the V.R.C platform.',
            'icon': 'exclamation-triangle',
            'order': 4,
        },
        {
            'name': 'Feature Requests',
            'slug': 'feature-requests',
            'description': 'Suggest new features and improvements for the platform.',
            'icon': 'light-bulb',
            'order': 5,
        },
        {
            'name': 'Off-Topic',
            'slug': 'off-topic',
            'description': 'Casual conversations and discussions not related to V.R.C.',
            'icon': 'chat-bubble-oval-left-ellipsis',
            'order': 6,
        },
    ]

    created_count = 0
    for cat_data in categories:
        category, created = Category.objects.get_or_create(
            slug=cat_data['slug'],
            defaults=cat_data
        )
        if created:
            print(f"  + Created category: {category.name}")
            created_count += 1
        else:
            print(f"  - Category already exists: {category.name}")

    print(f"\n  [+] Categories created: {created_count}")
    print(f"  [i] Total categories in database: {Category.objects.count()}")
    print()


def display_summary():
    """Display final summary with all credentials"""
    print("[6/6] Setup Summary")
    print("-" * 80)
    print()
    print("=" * 80)
    print("[+] Database Setup Completed Successfully!")
    print("=" * 80)
    print()
    print("Django Login Credentials:")
    print("-" * 80)
    print("  Admin:    admin / X#9kLm$P2v@nQ8w!ZjRe")
    print("    API Key:  vrc_8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918")
    print("  Test Users:")
    print("    - johndoe       / Tr@c3d!7BxN#m9Kw2YpL → 🛠️ Developer (Software developer)")
    print("      API Key: vrc_c2713b62c903791bdefc5a6a99df04d4330de491bbc7a0ca6a5007337e4a6028")
    print("    - janedoe       / Tr@c3d!7BxN#m9Kw2YpL → ✅ Verified (UX/UI designer)")
    print("      API Key: vrc_7618385caea382f562305468e586330381aae549829075b78dca7cb0d0aefac6")
    print("    - bobsmith      / Tr@c3d!7BxN#m9Kw2YpL → 👥 User (Entrepreneur)")
    print("      API Key: vrc_2a0fd2f46b67e5ba88e2869c397c0792365361d39e24ae48669e93ce0276e122")
    print("    - alicejohnson  / Tr@c3d!7BxN#m9Kw2YpL → 👥 User (Data scientist)")
    print("      API Key: vrc_ecf131afcb0956491d6096cb4f10e754583b12ef32813752c7f61bac2119a75b")
    print("    - charliebrown  / Tr@c3d!7BxN#m9Kw2YpL → ✅ Verified (Marketing specialist)")
    print("      API Key: vrc_56a4e2de5fa7a0db241606502556bcfb19c30f905979b43ae4dc8ce2334021ec")
    print("    - davidwilson   / Tr@c3d!7BxN#m9Kw2YpL → 🛠️ Developer (Web developer)")
    print("      API Key: vrc_7dfccb03d89581c04664713c37793ac19813ddbd7bd81f745adffddbeafe35f4")
    print("    - emilydavis    / Tr@c3d!7BxN#m9Kw2YpL → ✅ Verified (UX/UI designer)")
    print("      API Key: vrc_f0ef1990f64cd5da79a6f2e2f7fdffbe32d08819d7c882f307e848b74b4c9b32")
    print("    - michaeljohnson/ Tr@c3d!7BxN#m9Kw2YpL → 🛠️ Developer (Backend developer)")
    print("      API Key: vrc_4260dcdd1109cfca0a5f6972960f6c63eb0caa76f640c0d38a1ac91b84819933")
    print("    - sarahmiller   / Tr@c3d!7BxN#m9Kw2YpL → 👮 Staff (Product manager)")
    print("      API Key: vrc_60b80ae262f1eecbca08533da9c8c0eedb35bee995aab924c30f35b9a2ac3321")
    print("    - robertlee     / Tr@c3d!7BxN#m9Kw2YpL → 👮 Staff (DevOps engineer)")
    print("      API Key: vrc_e057fc86cb3815ffbd4b392b793d7044ecc00df94baacaed97a251cf61ba51dd")
    print("    - jenniferwhite / Tr@c3d!7BxN#m9Kw2YpL → 👮 Staff (QA engineer)")
    print("      API Key: vrc_846c94c11e13fe45011642c02ed167fdc991dda3367a6d4ac129ec0d6a13bef2")
    print("    - thomasgreen   / Tr@c3d!7BxN#m9Kw2YpL → 👮 Staff (Cybersecurity specialist)")
    print("      API Key: vrc_2effcbc7abd5779c4fa5b640eec7c15dc547e1c44abecf967a0e7b28f60b2ea4")
    print("    - lisaadams     / Tr@c3d!7BxN#m9Kw2YpL → 👥 User (Technical writer)")
    print("      API Key: vrc_57d183da355c502f3797663747e008fbb2a33b1a0f5224d7e6b95caa431b2a6c")
    print("    - danielclark   / Tr@c3d!7BxN#m9Kw2YpL → 🛠️ Developer (Mobile app developer)")
    print("      API Key: vrc_9f5ded6e8e50d7de8050d6a7a9daf1646dc189c0fad7f483293065b0d18bca2f")
    print()
    print("Bank Account PINs:")
    print("-" * 80)
    print("  admin           → PIN: 999999  (Balance: $100,000.00) 👑 Admin")
    print("  johndoe         → PIN: 123456  (Balance: $5,000.00) 🛠️ Developer")
    print("  janedoe         → PIN: 234567  (Balance: $7,500.00) ✅ Verified")
    print("  bobsmith        → PIN: 345678  (Balance: $3,000.00) 👥 User")
    print("  alicejohnson    → PIN: 456789  (Balance: $10,000.00) 👥 User")
    print("  charliebrown    → PIN: 567890  (Balance: $2,500.00) ✅ Verified")
    print("  davidwilson     → PIN: 678901  (Balance: $4,500.00) 🛠️ Developer")
    print("  emilydavis      → PIN: 789012  (Balance: $6,000.00) ✅ Verified")
    print("  michaeljohnson  → PIN: 890123  (Balance: $5,500.00) 🛠️ Developer")
    print("  sarahmiller     → PIN: 901234  (Balance: $7,000.00) 👮 Staff")
    print("  robertlee       → PIN: 012345  (Balance: $4,000.00) 👮 Staff")
    print("  jenniferwhite   → PIN: 112233  (Balance: $3,500.00) 👮 Staff")
    print("  thomasgreen     → PIN: 223344  (Balance: $8,000.00) 👮 Staff")
    print("  lisaadams       → PIN: 334455  (Balance: $4,800.00) 👥 User")
    print("  danielclark     → PIN: 445566  (Balance: $6,500.00) 🛠️ Developer")
    print()
    print("=" * 80)
    print()


def fix_existing_attempts():
    """Fix attempts for all existing users in the bank database"""
    print("[0/5] Fixing Bank Account Attempts...")
    print("-" * 80)

    try:
        # Get all Django users
        django_users = User.objects.all()
        if not django_users.exists():
            print("No Django users found. Skipping attempts migration.")
            print()
            return

        print(f"Found {django_users.count()} Django users")

        updated_count = 0

        # Check each user and fix attempts if needed
        for django_user in django_users:
            # Check if user exists in bank
            if external_calls.is_user_existing(django_user.id):
                # Get current attempts
                attempts = external_calls.get_user_attempts(django_user.id)
                if attempts is not None and attempts == 3:
                    # Fix attempts from 3 to 0
                    result = external_calls.reset_attempts(django_user.id)
                    if result and result.get('status') == 'success':
                        updated_count += 1
                        print(f"  ✓ Fixed user {django_user.id} ({django_user.username}): 3 → 0 attempts")
                    else:
                        print(f"  ⚠ Could not fix user {django_user.id} ({django_user.username})")
                elif attempts is not None:
                    print(f"  - User {django_user.id} ({django_user.username}): {attempts} attempts (no change needed)")
                else:
                    print(f"  ? User {django_user.id} ({django_user.username}): could not get attempts")
            else:
                print(f"  - User {django_user.id} ({django_user.username}): no bank account")

        print(f"\n✓ Updated {updated_count} users from 3 attempts to 0 attempts")
        print("Note: New users will be created with correct attempts (0) going forward.")

    except Exception as e:
        print(f"⚠ Warning: Attempts migration failed: {e}")
        # Don't fail the entire setup if this fails
        import traceback
        traceback.print_exc()

    print()


def generate_gif_previews():
    """Generate GIF preview images for CSS loaders that do not have one yet.

    This renders each CSS loader and captures it as an animated GIF file,
    which is displayed in the shop instead of live CSS code to prevent
    CSS source code scraping.
    """
    print("[5.5/6] Generating GIF Previews for CSS Loaders...")
    print("-" * 80)

    css_without_preview = Css.objects.filter(
        preview_gif__isnull=True
    ) | Css.objects.filter(
        preview_gif=''
    )

    total = css_without_preview.count()
    if total == 0:
        print("  All CSS files already have GIF previews.")
        print()
        return

    print(f"  Found {total} CSS file(s) without GIF previews.")
    print("  To generate animated GIF previews using headless Chrome, run:")
    print("    python manage.py generate_gif_previews")
    print()
    print("  Generating placeholder previews now...")

    try:
        from django.core.management import call_command
        call_command('generate_gif_previews')
    except Exception as e:
        print(f"  [W] GIF preview generation failed: {e}")
        print("  [i] You can generate previews later with: python manage.py generate_gif_previews")
    print()


def create_developer_subscriptions():
    """Ensure every user with the developer role has an active Free subscription."""
    from decimal import Decimal
    from Developer.models import DeveloperPlan, DeveloperSubscription
    from django.utils import timezone

    print("[+] Creating Developer Subscriptions...")
    print("-" * 80)

    free_plan, plan_created = DeveloperPlan.objects.get_or_create(
        slug='free',
        defaults={
            'name': 'Free',
            'price_monthly': Decimal('0.00'),
            'price_yearly': Decimal('0.00'),
            'css_limit': 5,
            'api_calls_limit': 1000,
            'commission_rate': Decimal('0.60'),
            'features': {'editor': True, 'analytics_basic': True},
            'is_active': True,
        },
    )
    if plan_created:
        print("  [+] Created 'Free' developer plan.")

    dev_users = PurchasedFeature.objects.filter(
        feature_type=PurchasedFeature.FEATURE_DEVELOPER_ROLE,
        is_active=True,
    ).select_related('user')

    created = 0
    for pf in dev_users:
        user = pf.user
        has_active = DeveloperSubscription.objects.filter(
            user=user,
            status__in=[DeveloperSubscription.Status.ACTIVE, DeveloperSubscription.Status.TRIAL],
        ).exists()
        if not has_active:
            DeveloperSubscription.objects.create(
                user=user,
                plan=free_plan,
                status=DeveloperSubscription.Status.ACTIVE,
                current_period_start=timezone.now(),
                current_period_end=timezone.now() + timezone.timedelta(days=30),
            )
            print(f"  ✓ {user.username}: subscribed to Free plan")
            created += 1
        else:
            print(f"  - {user.username}: already has active subscription")

    print(f"\n  Subscriptions created: {created}")
    print()


def main():
    try:
        fix_existing_attempts()
        create_superuser()
        create_predefined_users()
        assign_user_roles()
        create_developer_subscriptions()
        create_css_files()
        generate_gif_previews()
        setup_forum_categories()
        display_summary()

    except Exception as e:
        print(f"\n[X] Setup failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
