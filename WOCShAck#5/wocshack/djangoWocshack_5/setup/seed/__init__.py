import random
import time

SEED_TAG = '[seed]'


def jitter(lo=0.5, hi=2.0):
    """Sleep for a random duration in [lo, hi] seconds."""
    time.sleep(random.uniform(lo, hi))

# Persona Definitions for realistic seeding
def get_personas():
    from django.contrib.auth.models import User
    
    # Exclude admins/superusers and fetch normal users
    all_users = list(User.objects.filter(is_superuser=False))
    
    personas = {
        'developers': [],
        'designers': [],
        'business': [],
        'staff': [],
        'users': [],
    }

    for user in all_users:
        # Default bucket
        personas['users'].append(user)
        
        try:
            bio = user.profile.biography.lower()
        except:
            bio = ""
            
        if user.is_staff or any(kw in bio for kw in ['manager', 'product', 'qa', 'devops', 'cybersecurity']):
            personas['staff'].append(user)
            
        elif any(kw in bio for kw in ['developer', 'software', 'backend', 'frontend', 'mobile']):
            personas['developers'].append(user)
            
        elif any(kw in bio for kw in ['designer', 'ux/ui', 'creative']):
            personas['designers'].append(user)
            
        elif any(kw in bio for kw in ['entrepreneur', 'marketing', 'content creator']):
            personas['business'].append(user)
            
    # For backward compatibility and easy single-fallback items
    # if anyone needs just one random user from a bucket:
    return personas

def get_demo_users():
    # Leaving this for backward compatibility if any script still expects a simple dict
    # but pointing instead to random choices from personas.
    personas = get_personas()
    return {
        'demo_user': random.choice(personas['users']) if personas['users'] else None,
        'demo_developer': random.choice(personas['developers']) if personas['developers'] else None,
        'demo_staff': random.choice(personas['staff']) if personas['staff'] else None,
        'demo_advertiser': random.choice(personas['business']) if personas['business'] else None,
    }
