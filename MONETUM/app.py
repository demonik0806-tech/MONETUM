from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import pyotp
import os

app = Flask(__name__)
app.secret_key = 'monetum_secreto_seguro'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos de Base de Datos
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    totp_secret = db.Column(db.String(32), nullable=False)

class Presupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    monto = db.Column(db.Float, nullable=False)

class Deuda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nombre_deuda = db.Column(db.String(100), nullable=False)
    monto = db.Column(db.Float, nullable=False)

# Crear tablas y usuario de prueba si no existen
with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username="admin").first():
        secreto = pyotp.random_base32()
        nuevo_usuario = Usuario(username="admin", password="password123", totp_secret=secreto)
        db.session.add(nuevo_usuario)
        db.session.commit()
        print(f"Guarda este secreto para Google Authenticator: {secreto}")

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        totp_code = request.form.get('totp_code')

        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.password == password:
            totp = pyotp.TOTP(usuario.totp_secret)
            if totp.verify(totp_code):
                session['usuario_id'] = usuario.id
                return redirect(url_for('panel_principal'))
            else:
                flash('Código de autenticador inválido.')
        else:
            flash('Usuario o contraseña incorrectos.')
            
    return render_template('login.html')

@app.route('/panel')
def panel_principal():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    usuario_actual = Usuario.query.get(session['usuario_id'])
    presupuestos = Presupuesto.query.filter_by(usuario_id=usuario_actual.id).all()
    deudas = Deuda.query.filter_by(usuario_id=usuario_actual.id).all()
    
    return render_template("index.html", usuario=usuario_actual, presupuestos=presupuestos, deudas=deudas)

@app.route('/eliminar_deuda/<nombre>', methods=['POST'])
def eliminar_deuda(nombre):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
        
    deuda = Deuda.query.filter_by(nombre_deuda=nombre, usuario_id=session['usuario_id']).first()
    if deuda:
        db.session.delete(deuda)
        db.session.commit()
    return redirect(url_for('panel_principal'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)