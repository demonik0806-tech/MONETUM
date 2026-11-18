import base64
from io import BytesIO, StringIO
import os
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "monetum_prod_key_987654321_xyz")
csrf = CSRFProtect(app)

db_url = os.environ.get("DATABASE_URL", "sqlite:///monetum.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg2://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    totp_secret = db.Column(db.String(32), nullable=True)
    two_fa_enabled = db.Column(db.Boolean, default=False)
    salario_mensual = db.Column(db.Float, default=2500000.0)
    meta_global_icono = db.Column(db.String(10), default="🗼")
    meta_global_nombre = db.Column(db.String(100), default="Mi Proyecto")
    meta_global_objetivo = db.Column(db.Float, default=1000000.0)
    meta_aporte_mensual = db.Column(db.Float, default=0.0)
    ahorro_acumulado = db.Column(db.Float, default=0.0)
    moneda_activa = db.Column(db.String(5), default="COP")
    idioma = db.Column(db.String(5), default="es")
    modo_oscuro = db.Column(db.Boolean, default=True)

class Presupuesto(db.Model):
    __tablename__ = "presupuestos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    limite_sugerido = db.Column(db.Float, nullable=False)
    gasto_actual = db.Column(db.Float, default=0.0)
    meta_asignada = db.Column(db.String(50), nullable=True)

class Deuda(db.Model):
    __tablename__ = "deudas"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nombre_deuda = db.Column(db.String(100), nullable=False)
    monto_total = db.Column(db.Float, nullable=False)
    tasa_interes = db.Column(db.Float, default=0.0)
    cuota_mensual = db.Column(db.Float, default=0.0)

@app.after_request
def agregar_cabeceras_seguridad(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
@csrf.exempt
def procesar_login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    usuario = Usuario.query.filter_by(username=username).first()
    if not usuario: return jsonify({"success": False, "error": "Usuario no encontrado"}), 401
    
    password_valido = False
    if usuario.password.startswith(("scrypt:", "pbkdf2:")):
        password_valido = check_password_hash(usuario.password, password)
    elif usuario.password == password:
        password_valido = True
        usuario.password = generate_password_hash(password)
        db.session.commit()

    if not password_valido: return jsonify({"success": False, "error": "Contraseña incorrecta"}), 401
    session["usuario"] = usuario.username
    return jsonify({"success": True, "redirect": url_for("panel_principal")})

@app.route("/panel")
def panel_principal():
    if "usuario" not in session: return redirect(url_for("login"))
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    presupuestos = Presupuesto.query.filter_by(usuario_id=usuario.id).all()
    deudas = Deuda.query.filter_by(usuario_id=usuario.id).all()
    return render_template("index.html", usuario=usuario, presupuestos=presupuestos, deudas=deudas)

@app.route("/api/actualizar-presupuesto", methods=["POST"])
@csrf.exempt
def actualizar_presupuesto():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    p = Presupuesto.query.filter_by(usuario_id=usuario.id, categoria=datos["categoria"]).first()
    if p:
        p.limite_sugerido = datos["limite"]
        p.gasto_actual = datos["gasto_actual"]
        p.meta_asignada = datos["meta"]
    else:
        db.session.add(Presupuesto(usuario_id=usuario.id, categoria=datos["categoria"], limite_sugerido=datos["limite"], gasto_actual=datos["gasto_actual"], meta_asignada=datos["meta"]))
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/eliminar-presupuesto", methods=["POST"])
@csrf.exempt
def eliminar_presupuesto():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    p = Presupuesto.query.filter_by(usuario_id=usuario.id, categoria=datos["categoria"]).first()
    if p:
        db.session.delete(p)
        db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/actualizar-deuda", methods=["POST"])
@csrf.exempt
def actualizar_deuda():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    d = Deuda.query.filter_by(usuario_id=usuario.id, nombre_deuda=datos["nombre"]).first()
    if d:
        d.monto_total = datos["monto"]
        d.tasa_interes = datos["interes"]
        d.cuota_mensual = datos["cuota"]
    else:
        db.session.add(Deuda(usuario_id=usuario.id, nombre_deuda=datos["nombre"], monto_total=datos["monto"], tasa_interes=datos["interes"], cuota_mensual=datos["cuota"]))
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/eliminar-deuda", methods=["POST"])
@csrf.exempt
def eliminar_deuda():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    d = Deuda.query.filter_by(usuario_id=usuario.id, nombre_deuda=datos["nombre"]).first()
    if d:
        db.session.delete(d)
        db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/depositar-meta", methods=["POST"])
@csrf.exempt
def depositar_meta():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    if "monto" in datos:
        usuario.ahorro_acumulado += float(datos["monto"])
        db.session.commit()
    return jsonify({"status": "ok", "nuevo_acumulado": usuario.ahorro_acumulado})

@app.route("/api/actualizar-inicio", methods=["POST"])
@csrf.exempt
def actualizar_inicio():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    if "salario" in datos: usuario.salario_mensual = float(datos["salario"])
    if "meta_icono" in datos: usuario.meta_global_icono = datos["meta_icono"]
    if "meta_nombre" in datos: usuario.meta_global_nombre = datos["meta_nombre"]
    if "meta_objetivo" in datos: usuario.meta_global_objetivo = float(datos["meta_objetivo"])
    if "meta_aporte" in datos: usuario.meta_aporte_mensual = float(datos["meta_aporte"])
    if "moneda" in datos: usuario.moneda_activa = datos["moneda"]
    if "idioma" in datos: usuario.idioma = datos["idioma"]
    if "modo_oscuro" in datos: usuario.modo_oscuro = bool(datos["modo_oscuro"])
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route("/api/actualizar-perfil", methods=["POST"])
@csrf.exempt
def actualizar_perfil():
    if "usuario" not in session: return jsonify({"error": "No autorizado"}), 403
    datos = request.json
    usuario = Usuario.query.filter_by(username=session["usuario"]).first()
    cambio_credenciales = False
    if datos.get("nuevo_username") and datos["nuevo_username"] != usuario.username:
        usuario.username = datos["nuevo_username"]
        cambio_credenciales = True
    if datos.get("nuevo_password"):
        usuario.password = generate_password_hash(datos["nuevo_password"])
        cambio_credenciales = True
    db.session.commit()
    if cambio_credenciales:
        session.pop("usuario", None)
        return jsonify({"status": "ok", "redirect": url_for("login")})
    return jsonify({"status": "ok"})

def inicializar_bd():
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        columnas_u = [col["name"] for col in inspector.get_columns("usuarios")]
        with db.engine.begin() as conn:
            if "moneda_activa" not in columnas_u: conn.execute(text("ALTER TABLE usuarios ADD COLUMN moneda_activa VARCHAR(5) DEFAULT 'COP'"))
            if "idioma" not in columnas_u: conn.execute(text("ALTER TABLE usuarios ADD COLUMN idioma VARCHAR(5) DEFAULT 'es'"))
            if "modo_oscuro" not in columnas_u: conn.execute(text("ALTER TABLE usuarios ADD COLUMN modo_oscuro BOOLEAN DEFAULT 1"))
            if "meta_aporte_mensual" not in columnas_u: conn.execute(text("ALTER TABLE usuarios ADD COLUMN meta_aporte_mensual FLOAT DEFAULT 0.0"))
            if "ahorro_acumulado" not in columnas_u: conn.execute(text("ALTER TABLE usuarios ADD COLUMN ahorro_acumulado FLOAT DEFAULT 0.0"))

        mi_usuario_fijo = "demonik"
        mi_clave_fija = "demonik22*"
        admin = Usuario.query.filter_by(username=mi_usuario_fijo).first()
        if not admin:
            db.session.add(Usuario(username=mi_usuario_fijo, password=generate_password_hash(mi_clave_fija)))
            db.session.commit()
        elif not admin.password.startswith(("scrypt:", "pbkdf2:")):
            admin.password = generate_password_hash(mi_clave_fija)
            db.session.commit()

inicializar_bd()

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto, debug=False)
