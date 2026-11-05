from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.auth import auth_bp
from app.auth.forms import LoginForm, ResetPasswordRequestForm, ResetPasswordForm
from app.auth.decorators import rate_limit
from app.models.user import User
from app.models import db
from app.utils.audit import log_action
from datetime import datetime, timedelta
import secrets
import os


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(max_attempts=5, window=300)
def login():
    """Page de connexion. Redirige vers le dashboard si déjà connecté."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        login_input = form.email.data.strip().lower()
        
        # Login par email OU matricule
        if '@' in login_input:
            user = db.session.execute(
                db.select(User).filter_by(email=login_input)
            ).scalar_one_or_none()
        else:
            # Login par matricule (eleves)
            from app.models.student import StudentProfile
            profile = db.session.execute(
                db.select(StudentProfile).filter_by(matricule=login_input.upper())
            ).scalar_one_or_none()
            user = profile.user if profile else None

        if user is None or not user.check_password(form.password.data):
            flash('Email ou mot de passe incorrect.', 'danger')
            return redirect(url_for('auth.login'))

        if not user.actif:
            flash('Votre compte a été désactivé. Contactez un administrateur.', 'warning')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        user.derniere_connexion = datetime.utcnow()
        db.session.commit()

        log_action('login', details=f'Connexion réussie pour {user.email}')

        flash(f'Bienvenue, {user.prenom} !', 'success')

        # Redirection après login
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
def logout():
    """Déconnexion."""
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
@rate_limit(max_attempts=3, window=3600)
def reset_password_request():
    """Page de demande de reinitialisation de mot de passe."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = db.session.execute(
            db.select(User).filter_by(email=form.email.data.strip().lower())
        ).scalar_one_or_none()

        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()

            reset_url = url_for('auth.reset_password_token', token=token, _external=True)
            
            # Envoi par email via Brevo
            try:
                from app.utils.email import send_password_reset
                success, _ = send_password_reset(user, reset_url)
                
                if success:
                    flash('Un email de reinitialisation a ete envoye a votre adresse. Verifiez votre boite de reception (et les spams).', 'info')
                else:
                    flash(
                        f'Email non envoye. Lien direct : <a href="{reset_url}">{reset_url}</a> (Valable 15 minutes)',
                        'warning'
                    )
            except Exception as e:
                flash(
                    f'Erreur envoi email. Lien direct : <a href="{reset_url}">{reset_url}</a> (Valable 15 minutes)',
                    'warning'
                )
        else:
            flash(
                'Si un compte existe avec cet email, un lien de reinitialisation a ete envoye.',
                'info'
            )

        return redirect(url_for('auth.reset_password_request'))

    return render_template('auth/reset_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@rate_limit(max_attempts=5, window=300, lockout=900)
def reset_password_token(token):
    """Page de reinitialisation avec token."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    user = db.session.execute(
        db.select(User).filter_by(reset_token=token)
    ).scalar_one_or_none()

    if user is None or user.reset_token_expiry is None or user.reset_token_expiry < datetime.utcnow():
        flash('Le lien de réinitialisation est invalide ou a expiré.', 'danger')
        return redirect(url_for('auth.reset_password_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_form.html', form=form)
