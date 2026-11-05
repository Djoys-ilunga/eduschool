#!/usr/bin/env python3
"""EduSchool — Plateforme SaaS de gestion scolaire multi-établissements."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8080)
