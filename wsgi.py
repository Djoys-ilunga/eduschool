import os
import sys

# Add the project directory to the path
project_dir = '/home/DJOMBE/eduschool'
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Set Flask app
from app import create_app
application = create_app()
