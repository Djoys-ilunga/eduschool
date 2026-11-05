from app.models import db
from datetime import datetime


class Plan(db.Model):
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    prix = db.Column(db.Float, nullable=False, default=0)
    devise = db.Column(db.String(10), nullable=False, default='USD')
    max_eleves = db.Column(db.Integer, nullable=False, default=50)
    max_enseignants = db.Column(db.Integer, nullable=False, default=5)
    feature_limitees = db.Column(db.Boolean, default=True)

    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Plan {self.nom} (${self.prix}/mois)>'


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False)

    date_debut = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_fin = db.Column(db.DateTime, nullable=True)  # NULL = renouvellement automatique
    statut = db.Column(db.String(20), nullable=False, default='active')  # active, expiree, annulee
    renouvellement_auto = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='abonnements', lazy=True)
    plan = db.relationship('Plan', backref='abonnements', lazy=True)

    @property
    def est_active(self):
        if self.statut != 'active':
            return False
        if self.date_fin and self.date_fin < datetime.utcnow():
            return False
        return True

    def __repr__(self):
        return f'<Subscription ecole={self.school_id} plan={self.plan_id}>'


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    devise = db.Column(db.String(10), nullable=False, default='USD')
    methode = db.Column(db.String(30), nullable=True)  # mobile_money, carte, virement, especes
    reference = db.Column(db.String(100), nullable=True)
    statut = db.Column(db.String(20), nullable=False, default='en_attente')  # en_attente, complete, echoue, rembourse
    date_paiement = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    # Relations
    subscription = db.relationship('Subscription', backref='paiements', lazy=True)

    def __repr__(self):
        return f'<Payment {self.montant} {self.devise} ({self.statut})>'
