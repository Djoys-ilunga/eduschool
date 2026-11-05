"""Lancement production EduSchool via Waitress (WSGI).
Usage: python run_prod.py
Accessible sur http://0.0.0.0:8080 et http://<IP_LOCALE>:8080
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from waitress import serve
from app import create_app

app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("  EduSchool - Serveur de production")
    print("  http://0.0.0.0:8080")
    print("=" * 50)
    serve(app, host='0.0.0.0', port=8080, threads=8)
