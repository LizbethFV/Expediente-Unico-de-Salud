from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
import os
import random
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import json
import re
from better_profanity import profanity

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una-clave-por-defecto-segura")

# ==========================================
# CONFIGURACIÓN PARA SUBIR ARCHIVOS
# ==========================================
UPLOAD_FOLDER = 'static/firmas'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

UPLOAD_DOCS_FOLDER = 'static/expedientes'
app.config['UPLOAD_DOCS_FOLDER'] = UPLOAD_DOCS_FOLDER
os.makedirs(UPLOAD_DOCS_FOLDER, exist_ok=True)

# ==========================================
# CONEXIÓN A MONGODB (CORREGIDA)
# ==========================================
MONGO_URI = os.getenv("MONGO_URL")
if not MONGO_URI:
    # Dejamos una cadena local vacía o de respaldo por si corres en tu PC
    MONGO_URI = "mongodb://localhost:27017/expediente_salud"

client = MongoClient(MONGO_URI)

# FORZAMOS el uso de 'expediente_db' que es donde Dokploy y tu string original guardaban los datos
db = client['expediente_db']

groserias_mexicanas = [
    # --- Insultos comunes ---
    "pendejo", "pendeja", "pendejos", "pendejas", "pndjo", "pndja",
    "cabron", "cabrona", "cabrones", "cabronas", "cbrn",
    "puto", "puta", "putos", "putas", "pto", "pta", "putito", "putita",
    "culero", "culera", "culeros", "culeras", "clro", "clra",
    "maricon", "joto", "jotos", "marica",
    
    # --- Derivados de la palabra con "Ch" ---
    "chingar", "chingadera", "chingaderas", "chingado", "chingada", 
    "chingon", "chingona", "chingo", "chingas", "chingue", "chingues",
    
    # --- Referencias vulgares u ofensivas ---
    "verga", "vrga", "vergas", "vergazo", "vergazos",
    "mamon", "mamona", "mamones", "mamar", "mamada", "mamadas",
    "madrearse", "madreado", "madreada", "putazo", "putazos",
    "baboso", "babosa", "estupido", "estupida", "imbecil", "idiota",
    "mierda", "mrda", "mierdas", "cagar", "cagado", "cagada",
    "cojer", "cojerte", "joder", "jodido", "jodida",
    
    # --- Nombres falsos, de burla o trolleo ---
    "test", "prueba", "pruebas", "asdf", "asdfg", "qwerty",
    "anonimo", "elpepe", "etesech", "chabelo", "goku", "dummy",
    "falso", "falsa", "ninguno", "nadie", "inventado", "ejemplo"
]
profanity.load_censor_words(groserias_mexicanas)

# ___________________Rutas de Inicio de Sesión y Registro________________________

@app.route('/registro', methods=['GET', 'POST'])
def registro_page():
    if request.method == 'POST':
        # Agregamos .strip() para limpiar espacios accidentales que mete el teclado
        username = request.form.get('username', '').strip()
        password_plano = request.form.get('password', '').strip()
        nombre = request.form.get('nombre', '').strip()
        
        if not all([username, password_plano, nombre]):
            flash('Por favor, completa todos los campos', 'warning')
            return render_template('registro.html')

        # Verificación de duplicados antes de insertar
        if db.usuarios.find_one({"username": username}):
            flash('El nombre de usuario ya está registrado', 'warning')
            return redirect(url_for('registro_page'))

        # Cifrado seguro de la contraseña
        password_cifrado = generate_password_hash(password_plano)
        
        nuevo_usuario = {
            "username": username,
            "password": password_cifrado, 
            "nombre": nombre,
            "rol": "medico"
        }
        db.usuarios.insert_one(nuevo_usuario)
        flash('¡Médico registrado con éxito!', 'success')
        return redirect(url_for('login_page'))
        
    return render_template('registro.html')

@app.route('/auth/register', methods=['POST'])
def register_action():
    # Esta es tu segunda ruta de registro por si tus formularios apuntan aquí
    usuario = request.form.get('usuario', '').strip()
    email = request.form.get('email', '').strip()
    cedula = request.form.get('cedula', '').strip()
    password_plano = request.form.get('password', '').strip() 

    if db.usuarios.find_one({"$or": [{"username": usuario}, {"cedula": cedula}]}):
        flash('El usuario o la cédula ya están registrados', 'warning')
        return redirect(url_for('registro_page'))

    if not all([usuario, email, cedula, password_plano]):
        flash('Por favor, completa todos los campos', 'warning')
        return redirect(url_for('registro_page'))

    password_cifrado = generate_password_hash(password_plano)

    db.usuarios.insert_one({
        "username": usuario, 
        "email": email,
        "cedula": cedula,
        "password": password_cifrado,
        "rol": "medico"
    })
    flash('¡Médico registrado con éxito!', 'success')
    return redirect(url_for('login_page'))


@app.route('/', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        # Captura y limpia tanto 'username' como 'usuario' para que sea compatible con cualquier formulario HTML
        username = request.form.get('username') or request.form.get('usuario')
        password_plano = request.form.get('password')
        
        if username:
            username = username.strip()
        if password_plano:
            password_plano = password_plano.strip()
        
        # Buscamos al usuario por su username
        usuario = db.usuarios.find_one({"username": username})
        
        # Comparamos el password escrito con el hash de la BD
        if usuario and check_password_hash(usuario['password'], password_plano):
            session['usuario_id'] = str(usuario['_id'])
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos")
            
    return render_template('login.html')

@app.route('/auth/login', methods=['POST'])
def login_action():
    # Esta es tu segunda ruta de procesamiento por si el formulario de login apunta a /auth/login
    usuario_ingresado = (request.form.get('usuario') or request.form.get('username'))
    password_ingresado = request.form.get('password')
    
    if usuario_ingresado:
        usuario_ingresado = usuario_ingresado.strip()
    if password_ingresado:
        password_ingresado = password_ingresado.strip()
    
    user = db.usuarios.find_one({"username": usuario_ingresado})
    
    if user and check_password_hash(user['password'], password_ingresado):
        session['usuario_id'] = str(user['_id']) 
        return redirect(url_for('dashboard'))
    else:
        flash('Contraseña o usuario incorrectos', 'danger') 
        return redirect(url_for('login_page'))

#_____________________Rutas de Dashboard________________________

@app.route('/dashboard')
def dashboard():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    # Buscamos al médico logueado para mostrar su nombre en el dashboard y evitar errores en la barra superior
    medico_object_id = ObjectId(u_id)
    medico_data = db.usuarios.find_one({"_id": medico_object_id})
    
    # Obtener las citas pendientes de este doctor desde MongoDB
    citas_cursor = db.citas.find({"doctor_id": medico_object_id, "estado": "Pendiente"})
    lista_citas = list(citas_cursor)
    
    # Buscar el nombre real de cada paciente usando su CURP
    for cita in lista_citas:
        curp = cita.get('curp_paciente') or cita.get('curp')
        
        if curp:
            # Buscamos al paciente en la base de datos
            paciente = db.pacientes.find_one({"curp": curp})
            if paciente:
                # Si lo encuentra, le asignamos su nombre real
                cita['nombre_final'] = paciente.get('nombre', 'Paciente sin nombre')
            else:
                cita['nombre_final'] = f"CURP: {curp} (No registrado)"
        else:
            cita['nombre_final'] = "Paciente No Identificado"
            
    # filtramos los pacientes que pertenecen a este médico específico usando $or para compatibilidad con ambos formatos
    query_pacientes = {
        "$or": [
            {"medicos_ids": medico_object_id},  # Nuevo formato (Arreglo de médicos)
            {"medico_id": medico_object_id}    # Formato anterior (Compatibilidad)
        ]
    }
    pacientes_filtrados = list(db.pacientes.find(query_pacientes))
    
    # Indicadores clave para el dashboard
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    # Total de Pacientes pertenecientes a este médico específico
    total_pacientes = len(pacientes_filtrados)
    
    # Consultas registradas el día de hoy en el sistema global (YYYY-MM-DD)
    consultas_hoy = db.consultas.count_documents({"fecha": fecha_hoy})
    
    # Conteo dinámico de documentos adjuntos de los pacientes asignados a este doctor
    documentos_totales = 0
    for p in pacientes_filtrados:
        if 'documentos' in p and isinstance(p['documentos'], list):
            documentos_totales += len(p['documentos'])
            
    #Citas programadas para HOY, filtrando por el MÉDICO actual y estado "Pendiente"
    citas_hoy = db.citas.count_documents({
        "doctor_id": medico_object_id,
        "fecha": fecha_hoy,
        "estado": "Pendiente"
    })
            
    # Pasar las variables procesadas a tu index.html
    return render_template(
        'index.html', 
        citas=lista_citas, 
        pacientes=pacientes_filtrados,
        pacientes_completos=pacientes_filtrados,
        doctor=medico_data,
        total_pacientes=total_pacientes,
        consultas_hoy=consultas_hoy,
        documentos_totales=documentos_totales,
        citas_hoy=citas_hoy
    )

#___________________________Perfil Médico__________________________________

@app.route('/perfil-medico')
def perfil():
    # Buscamos el ID que guardamos en el login_action
    u_id = session.get('usuario_id')
    
    if not u_id:
        print("DEBUG: No se encontró usuario_id en sesión, redirigiendo al login.")
        return redirect(url_for('login_page'))

    try:
        # Buscamos en la base de datos por el _id único
        doctor_data = db.usuarios.find_one({"_id": ObjectId(u_id)})
        
        if not doctor_data:
            print(f"DEBUG: No existe un usuario en la BD con el ID: {u_id}")
            return "Usuario no encontrado en la base de datos. <a href='/'>Regresar</a>"
            
        return render_template('perfil.html', doctor=doctor_data)
        
    except Exception as e:
        print(f"DEBUG Error en perfil: {e}")
        return redirect(url_for('login_page'))
        

@app.route('/actualizar_perfil', methods=['POST'])
def actualizar_perfil():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    # 1. Recorrer los campos de texto del formulario
    especialidad = request.form.get('especialidad')
    cedula_general = request.form.get('cedula_general')
    cedula_especialidad = request.form.get('cedula_especialidad')
    universidad = request.form.get('universidad')
    telefono = request.form.get('telefono')
    direccion = request.form.get('direccion')
    
    update_data = {
        "especialidad": especialidad,
        "cedula_general": cedula_general,
        "cedula_especialidad": cedula_especialidad,
        "universidad": universidad,
        "telefono": telefono,
        "consultorio_direccion": direccion
    }
    
    # Procesar el archivo de la Foto de Perfil
    if 'foto' in request.files:
        foto_file = request.files['foto']
        if foto_file and foto_file.filename != '':
            foto_filename = secure_filename(f"foto_{u_id}_{foto_file.filename}")
            foto_filepath = os.path.join(app.config['UPLOAD_FOLDER'], foto_filename)
            foto_file.save(foto_filepath)
            update_data["foto_url"] = f"/{foto_filepath}"

    # Procesar el archivo de la Firma
    if 'firma' in request.files:
        file = request.files['firma']
        if file and file.filename != '':
            filename = secure_filename(f"firma_{u_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            update_data["firma_url"] = f"/{filepath}"

    # Guardar en MongoDB
    db.usuarios.update_one(
        {"_id": ObjectId(u_id)},
        {"$set": update_data}
    )
    return redirect(url_for('perfil'))

#_________________________________________Pacientes_________________________________________
@app.route('/add_patient', methods=['POST'])
def add_patient():
    # 1. Validar sesión del doctor y obtener su ID
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))

    # ====================================================================
    # FLUJO A: VINCULAR PACIENTE EXISTENTE POR CURP
    # ====================================================================
    curp_buscar = request.form.get('curp_buscar')
    if curp_buscar:
        curp_buscar = curp_buscar.upper().strip()
        
        # Buscamos si el paciente existe globalmente en la base de datos
        paciente_existente = db.pacientes.find_one({"curp": curp_buscar})
        
        if paciente_existente:
            db.pacientes.update_one(
                {"curp": curp_buscar},
                {"$addToSet": {"medicos_ids": ObjectId(u_id)}}
            )
            flash('Paciente vinculado exitosamente a tu directorio', 'success')
        else:
            flash('No se encontró ningún paciente con esa CURP en el sistema global', 'danger')
            
        return redirect(url_for('lista_pacientes'))

    # ====================================================================
    # FLUJO B: REGISTRAR UN PACIENTE NUEVO DESDE CERO
    # ====================================================================
    nombre = request.form.get('nombre', '').strip()
    curp = request.form.get('curp', '').upper().strip()
    nss = request.form.get('nss', '').strip()
    edad = request.form.get('edad', '').strip()

    # 1. Validación de campos vacíos
    if not nombre or not curp:
        flash('El nombre y la CURP son obligatorios para un nuevo registro', 'danger')
        return redirect(url_for('dashboard'))

    # 2. CANDADO DE MODERACIÓN: Evitar groserías o nombres de broma (Súper blindado con acentos)
    # Truco para quitar acentos y normalizar a minúsculas antes de validar
    nombre_sin_acentos = nombre.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    
    # Pasamos la versión en minúsculas y sin acentos por el filtro
    if profanity.contains_profanity(nombre_sin_acentos):
        flash('Error: El nombre del paciente contiene palabras inapropiadas o no permitidas.', 'danger')
        return redirect(url_for('dashboard'))

    # 3. CANDADO CIBERSEGURIDAD: Expresión regular basada en tu esquema oficial de CURP
    patron_curp = r"^[A-Z]{4}[0-9]{6}[HM][A-Z]{5}[A-Z0-9]{2}$"
    if not re.match(patron_curp, curp):
        flash('Error: El formato de la CURP es inválido de acuerdo al esquema oficial (AAMMDD...).', 'danger')
        return redirect(url_for('dashboard'))

    # 4. CANDADO DE INTEGRIDAD: Validar rango de edad (0 a 120 años)
    try:
        edad_int = int(edad)
        if edad_int < 0 or edad_int > 120:
            flash('Error: La edad debe estar en un rango válido entre 0 y 120 años.', 'danger')
            return redirect(url_for('dashboard'))
    except ValueError:
        flash('Error: La edad ingresada debe ser un número válido.', 'danger')
        return redirect(url_for('dashboard'))

    # 5. Validación de duplicados en la base de datos (CURP o NSS ya existentes)
    existente = db.pacientes.find_one({"$or": [{"curp": curp}, {"nss": nss}]})
    if existente:
        flash('Este CURP o NSS ya existe en el sistema', 'danger')
        return redirect(url_for('dashboard'))

    # Si todo pasa los filtros, preparamos el guardado oficial en mayúsculas
    nuevo_paciente = {
        "nombre": nombre.upper(), # Lo guardamos estético y limpio en mayúsculas en MongoDB
        "curp": curp,
        "nss": nss,
        "edad": edad_int,        # Guardado como entero para estadísticas futuras
        "no_expediente": f"2026-{curp[:4]}" if len(curp) >= 4 else "2026-TEMP",
        "ultima_visita": datetime.now().strftime("%d %b %Y - %H:%M"),
        "estado": "Activo",
        "estudios": [],
        "expediente_datos": {},
        "medicos_ids": [ObjectId(u_id)]
    }
    
    db.pacientes.insert_one(nuevo_paciente)
    flash('Paciente registrado y añadido con éxito', 'success')
    return redirect(url_for('dashboard'))

@app.route('/perfil_paciente/<curp>')
@app.route('/paciente/<curp>')   
@app.route('/perfil/<curp>')
def perfil_paciente(curp):
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    medico_object_id = ObjectId(u_id)
    medico_data = db.usuarios.find_one({"_id": medico_object_id})

    # 1. Buscar los datos del paciente
    paciente = db.pacientes.find_one({"curp": curp})
    if not paciente:
        flash("Paciente no encontrado", "danger")
        return redirect(url_for('pacientes'))
    
    # 2. Buscar las consultas del paciente (por si ya lo tenías)
    consultas = list(db.consultas.find({"curp_paciente": curp}))

    
    
    # 3. NUEVO: Buscar los archivos/estudios subidos de este paciente
    archivos = list(db.expedientes_archivos.find({"curp_paciente": curp}))
    
    # Pasamos 'archivos' al render_template
    return render_template('perfil_paciente.html', 
                           paciente=paciente, 
                           consultas=consultas, 
                           archivos=archivos,
                           doctor=medico_data)

@app.route('/buscar_paciente')
def buscar_paciente():
    u_id = session.get('usuario_id')
    if not u_id:
        return jsonify([]), 401 # No autorizado si no hay sesión

    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([]) # No buscar si es un solo caracter

    # Buscamos coincidencias en Nombre, CURP o NSS (ajusta los campos según tu esquema de 'pacientes')
    # Usamos $regex para búsquedas parciales tipo "LIKE"
    criterio = {
        "$or": [
            {"nombre": {"$regex": query, "$options": "i"}},
            {"curp": {"$regex": query, "$options": "i"}},
            {"nss": {"$regex": query, "$options": "i"}}
        ]
    }

    # Traemos un límite de 5 o 6 registros para no saturar el menú desplegable
    pacientes_db = db.pacientes.find(criterio).limit(6)

    resultados = []
    for p in pacientes_db:
        resultados.append({
            "nombre": p.get("nombre", "Sin Nombre"),
            "curp": p.get("curp", ""),
            "nss": p.get("nss", "N/A")
        })

    # Retornamos la lista en formato JSON para que el JS del HTML la procese
    return jsonify(resultados)

@app.route('/pacientes')
def lista_pacientes():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    medico_object_id = ObjectId(u_id)
    medico_data = db.usuarios.find_one({"_id": medico_object_id})

    query_pacientes = {
        "$or": [
            {"medicos_ids": medico_object_id},  # Nuevo formato (Array multilistas)
            {"medico_id": medico_object_id}    # Formato anterior (Compatibilidad)
        ]
    }
    
    # Traemos la lista unificada desde MongoDB
    pacientes_filtrados = list(db.pacientes.find(query_pacientes))
    
    # Renderizamos la plantilla pasando la lista correcta hacia pacientes.html
    return render_template('pacientes.html', pacientes_completos=pacientes_filtrados,doctor=medico_data)

@app.route('/search_patient', methods=['GET'])
def search_patient():
    query = request.args.get('query')
    if not query:
        return redirect(url_for('dashboard'))
    query = query.upper()
    paciente = db.pacientes.find_one({"curp": query})
    if paciente:
        return render_template('expediente.html', paciente=paciente)
    flash('No se encontró ningún paciente con esa CURP', 'warning')
    return redirect(url_for('dashboard'))

@app.route('/api/sugerencias_pacientes')
def sugerencias_pacientes():
    # Validamos que el usuario esté logueado antes de procesar la búsqueda
    query = request.args.get('q', '')
    if len(query) < 2:  # No buscar hasta que escriba al menos 2 letras
        return jsonify([])

    # Buscamos coincidencias en nombre o CURP
    pacientes = db.pacientes.find({
        "$or": [
            {"nombre": {"$regex": query, "$options": "i"}},
            {"curp": {"$regex": query, "$options": "i"}}
        ]
    }).limit(5) # Solo mostramos las primeras 5 sugerencias

    resultados = []
    for p in pacientes:
        resultados.append({
            "nombre": p.get('nombre', 'Sin Nombre'),
            "curp": p.get('curp', 'Sin CURP'),
            "nss": p.get('nss', 'N/A')  # Se añade por si la agenda lo requiere al renderizar la sugerencia
        })
    
    return jsonify(resultados)


#________________________________Agenda_______________________________________________

@app.route('/agendar_cita', methods=['POST'])
def agendar_cita():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))

    # Capturar los datos enviados por el formulario inline
    curp = request.form.get('curp', '')
    fecha = request.form.get('fecha', '') 
    hora = request.form.get('hora', '')   
    motivo = request.form.get('motivo', '')

    # Validación rápida de que los campos obligatorios no vengan vacíos
    if not curp or not fecha or not hora or not motivo:
        flash('Todos los campos son obligatorios para agendar una cita.', 'danger')
        return redirect(url_for('agenda_page'))

    # Buscamos si el doctor ya tiene una cita reservada exactamente ese mismo día y hora
    cita_conflictiva = db.citas.find_one({
        "doctor_id": ObjectId(u_id),
        "fecha": fecha,
        "hora": hora
    })

    if cita_conflictiva:
        flash('Error: Ya tienes una cita programada a esa misma hora. Por favor, selecciona otro horario.', 'danger')
        
        # 💡 TRUCO: Jalamos los datos que la plantilla 'agenda.html' necesita
        # para volver a dibujarse exactamente igual sin perder el contexto.
        doctor_data = db.usuarios.find_one({"_id": ObjectId(u_id)})
        citas_pendientes = list(db.citas.find({
            "doctor_id": ObjectId(u_id), 
            "estado": "Pendiente"
        }).sort([("fecha", 1), ("hora", 1)]))
        
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        citas_hoy = db.citas.count_documents({
            "doctor_id": ObjectId(u_id),
            "fecha": hoy_str, 
            "estado": "Pendiente"
        })
        
        # Renderizamos directamente la plantilla en lugar de redireccionar.
        # Al pasarle 'curp', 'fecha', 'hora' y 'motivo', el formulario puede conservar lo que el doctor escribió.
        return render_template(
            'agenda.html', 
            citas=citas_pendientes, 
            citas_hoy=citas_hoy, 
            doctor=doctor_data,
            curp_error=curp,
            fecha_error=fecha,
            hora_error=hora,
            motivo_error=motivo
        )


    # Si el horario está libre, procedemos a construir el documento y guardarlo
    nueva_cita = {
        "doctor_id": ObjectId(u_id),
        "curp_paciente": curp.upper().strip(), 
        "fecha": fecha,
        "hora": hora,
        "motivo": motivo,
        "estado": "Pendiente"          
    }

    # Insertar en MongoDB
    db.citas.insert_one(nueva_cita)

    flash('Cita agendada exitosamente', 'success')
    return redirect(url_for('agenda_page'))


@app.route('/agenda')
def agenda_page():
    # Validar de inmediato que la sesión esté activa
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page')) # Si no hay sesión, al Login
    
    # Buscar al doctor logueado para que la barra superior no marque error
    doctor_data = db.usuarios.find_one({"_id": ObjectId(u_id)})
    
    # filtamos solo las citas pendientes de ese doctor
    citas = list(db.citas.find({
        "doctor_id": ObjectId(u_id), 
        "estado": "Pendiente"
    }).sort([("fecha", 1), ("hora", 1)]))
    
    # CONTADOR FILTRADO: Contar cuántas citas tiene HOY este doctor específicamente
    hoy = datetime.now().strftime("%Y-%m-%d")
    citas_hoy = db.citas.count_documents({
        "doctor_id": ObjectId(u_id),
        "fecha": hoy, 
        "estado": "Pendiente"
    })
    
    # Enviamos todo limpio al HTML
    return render_template(
        'agenda.html', 
        citas=citas, 
        citas_hoy=citas_hoy, 
        doctor=doctor_data
    )

#______________________________________Consultas________________________________________

@app.route('/consultas')
def consultas():
    # 1. Obtener todas las consultas para la tabla
    todas_consultas = list(db.consultas.find().sort("_id", -1))
    
    # 2. Kpis principales
    hoy_str = datetime.now().strftime("%d/%m/%Y")
    total_hoy = db.consultas.count_documents({"fecha": hoy_str})
    
    
    # 3. Diagnóstico común (CORREGIDO: siempre sobre la colección 'consultas')
    pipeline = [
        {"$group": {"_id": "$diagnostico", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1}
    ]
    
    try:
        # Ejecutamos la agregación directamente sobre la colección de consultas
        res_diag = list(db.consultas.aggregate(pipeline))
        diag_comun = res_diag[0]['_id'] if res_diag else "Sin diagnósticos"
    except Exception as e:
        print(f"Error en agregación: {e}")
        diag_comun = "N/A"

    # 4. Lógica para la Gráfica (Eje X: Días, Eje Y: Pacientes)
    hoy = datetime.now()
    labels_x = []
    datos_y = []

    usuario_id = session.get('usuario_id') # Usamos usuario_id como en el login
    if not usuario_id:
        return redirect(url_for('login_page'))

    # Buscamos al doctor para que el menú no marque error
    from bson.objectid import ObjectId
    doctor_data = db.usuarios.find_one({"_id": ObjectId(usuario_id)})

    for i in range(6, -1, -1):
        dia_temp = hoy - timedelta(days=i)
        fecha_buscar = dia_temp.strftime("%d/%m/%Y")
        
        # Eje X: Día (Lun, Mar, etc.)
        labels_x.append(dia_temp.strftime("%a"))
        
        # Eje Y: Conteo de documentos en esa fecha
        conteo = db.consultas.count_documents({"fecha": fecha_buscar})
        datos_y.append(conteo)

    return render_template('consultas.html', 
                           consultas=todas_consultas,
                            doctor=doctor_data,
                           total_hoy=total_hoy,
                           diag_comun=diag_comun,
                           labels_x=labels_x,
                           datos_y=datos_y)

@app.route('/perfil/<curp>/consultas')
def ver_consultas(curp):
    # Buscamos al paciente por su CURP
    paciente = db.pacientes.find_one({"curp": curp})
    if not paciente:
        flash("Paciente no encontrado", "danger")
        return redirect(url_for('dashboard'))
    
    # Obtenemos todas sus consultas asociadas ordenadas por la más reciente
    consultas = list(db.consultas.find({"curp_paciente": curp}).sort("_id", -1))
    
    # Renderizamos un nuevo template específico para la lista de consultas
    return render_template('historial_consultas.html', paciente=paciente, consultas=consultas)

@app.route('/consulta/<id>')
def detalle_consulta(id):
    from bson.objectid import ObjectId
    consulta = db.consultas.find_one({"_id": ObjectId(id)})
    paciente = db.pacientes.find_one({"curp": consulta['curp_paciente']})
    # Reutilizamos tu template de receta para mostrar el detalle
    return render_template('receta.html', consulta=consulta, paciente=paciente)

@app.route('/guardar_consulta/<curp>', methods=['POST'])
def guardar_consulta(curp):
    ahora = datetime.now()
    
    # 1. Recogemos los campos de texto que queremos proteger
    motivo = request.form.get('motivo', '').strip()
    diagnostico = request.form.get('diagnostico', '').strip()
    tratamiento = request.form.get('tratamiento', '').strip()
    pronostico = request.form.get('pronostico', '').strip()

    # 2. CANDADO DE MODERACIÓN: Unificamos el texto para evaluarlo en un solo paso
    texto_completo = f"{motivo} {diagnostico} {tratamiento} {pronostico}".lower()
    
    # Quitamos los acentos para que no burlen el filtro escribiendo mal adrede
    texto_sin_acentos = (texto_completo
                         .replace('á', 'a')
                         .replace('é', 'e')
                         .replace('í', 'i')
                         .replace('ó', 'o')
                         .replace('ú', 'u'))
    
    # Si el filtro detecta cualquier grosería de la lista mexicana
    if profanity.contains_profanity(texto_sin_acentos):
        flash('Error: El contenido de la nota médica o receta contiene palabras inapropiadas o lenguaje no permitido.', 'danger')
        # Redirigimos de vuelta al dashboard por seguridad
        return redirect(url_for('dashboard'))

    # 3. Si todo está limpio, creamos el documento para guardarlo en MongoDB
    nueva_nota = {
        "curp_paciente": curp,
        "fecha": ahora.strftime("%d/%m/%Y"),
        "hora": ahora.strftime("%H:%M"),
        "peso": request.form.get('peso'),
        "talla": request.form.get('talla'),
        "temp": request.form.get('temp'),
        "presion": request.form.get('presion'),
        "motivo": motivo,
        "diagnostico": diagnostico,
        "pronostico": pronostico,
        "tratamiento": tratamiento
    }
    
    # Guardamos la consulta limpia en la colección de consultas
    db.consultas.insert_one(nueva_nota)
    
    # Usamos el formato para que tu tabla del Dashboard se vea con hora
    fecha_tabla = ahora.strftime("%d %b %Y - %H:%M")
    db.pacientes.update_one(
        {"curp": curp}, 
        {"$set": {"ultima_visita": fecha_tabla}}
    )
    
    # Jalamos los datos del paciente para la receta
    paciente_data = db.pacientes.find_one({"curp": curp})
    
    # Devolvemos 'receta.html' porque ya terminó la consulta de forma segura
    return render_template('receta.html', consulta=nueva_nota, paciente=paciente_data)

@app.route('/preparar_consulta', methods=['POST'])
def preparar_consulta():
    curp = request.form.get('curp').upper()
    paciente = db.pacientes.find_one({"curp": curp})
    if paciente:
        return render_template('nuevaconsulta.html', paciente=paciente)
    else:
        flash('El paciente no está registrado.', 'danger')
        return redirect(url_for('dashboard'))


#__________________________________________Expediente__________________________________________

@app.route('/expediente_paciente/<curp>')
def expediente_paciente(curp):
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    # 1. Obtener datos del paciente
    paciente = db.pacientes.find_one({"curp": curp})
    if not paciente:
        flash("Paciente no encontrado", "danger")
        return redirect(url_for('pacientes'))
        
    # 2. Obtener la lista de archivos de este paciente
    archivos = list(db.expedientes_archivos.find({"curp_paciente": curp}))
    
    return render_template('expediente_archivos.html', paciente=paciente, archivos=archivos)


@app.route('/expediente/<curp>')
def ver_expediente(curp):
    # 1. Buscamos al paciente en la base de datos
    paciente = db.pacientes.find_one({"curp": curp})
    
    if not paciente:
        return "Paciente no encontrado", 404
        
    # 2. CLAVE: Extraemos el progreso clínico previo que guardó tu función 'guardar_expediente'
    # Si no existe todavía la clave 'expediente_datos', le pasamos un diccionario vacío {}
    expediente_guardado = paciente.get('expediente_datos', {})
        
    # 3. Pasamos el objeto 'paciente' Y los datos del 'expediente' al HTML
    return render_template('expediente.html', paciente=paciente, expediente=expediente_guardado)


@app.route('/guardar_expediente', methods=['POST'])
def guardar_expediente():
    try:
        datos = request.json
        curp_paciente = datos.get('curp')

        # Actualizamos el documento
        db.pacientes.update_one(
            {"curp": curp_paciente},
            {"$set": {
                "expediente_datos": datos.get('valores'),
                # CAMBIO: Se actualiza la fecha y hora de la última gestión
                "ultima_visita": datetime.now().strftime("%d %b %Y - %H:%M")
            }},
            upsert=True 
        )
        return jsonify({"status": "success", "message": "Datos guardados"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    
#____________________________Anexos y Archivos____________________________________________


@app.route('/paciente/<curp>/anexos')
def lista_anexos(curp):
    # Buscamos al paciente para mostrar su nombre en el encabezado
    paciente = db.pacientes.find_one({"curp": curp})
    if not paciente:
        return "Paciente no encontrado", 404
        
    # Por ahora solo mostramos Neurología como opción fija
    return render_template('lista_anexos.html', paciente=paciente)

@app.route('/paciente/<curp>/anexo/neurologia')
def anexo_neurologia(curp):
    paciente = db.pacientes.find_one({"curp": curp})
    # CORRECCIÓN: Buscar los datos existentes para cargarlos en los inputs
    datos_neuro = db.anexos.find_one({"curp_paciente": curp, "especialidad": "Neurología"})
    
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    return render_template('anexo_neurologia.html', 
                           paciente=paciente, 
                           anexoneuro=datos_neuro, # Se pasa al HTML
                           fecha_actual=fecha_hoy)

@app.route('/guardar_anexo_neurologia', methods=['POST'])
def guardar_anexo_neurologia():
    datos = request.json
    curp = datos.get('curp')
    # FILTRO DOBLE
    filtro = {"curp_paciente": curp, "especialidad": "Neurología"}
    
    db.anexos.update_one(
        filtro, 
        {"$set": {
            "datos": datos.get('valores'),
            "ultima_modificacion": datetime.now().strftime("%d %b %Y - %H:%M")
        }},
        upsert=True
    )
    return jsonify({"status": "success"})
    

@app.route('/importar_estudio/<curp>', methods=['POST'])
def importar_estudio(curp):
    if 'archivo' not in request.files:
        return redirect(request.referrer)
    
    archivo = request.files['archivo']
    if archivo.filename == '':
        return redirect(request.referrer)

    # Guardar el archivo físicamente (asegúrate de crear la carpeta 'uploads/estudios')
    nombre_seguro = f"{curp}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{archivo.filename}"
    ruta = os.path.join('static/uploads/estudios', nombre_seguro)
    archivo.save(ruta)

    # Guardar la referencia en MongoDB
    db.pacientes.update_one(
        {"curp": curp},
        {"$push": {"estudios": {
            "nombre": archivo.filename,
            "ruta": nombre_seguro,
            "fecha": datetime.now().strftime("%d/%m/%Y")
        }}}
    )
    flash("Estudio importado correctamente", "success")
    return redirect(url_for('perfil_paciente', curp=curp))

@app.route('/subir_archivo_paciente/<curp>', methods=['POST'])
def subir_archivo_paciente(curp):
    if 'estudio_medico' not in request.files:
        flash("No se seleccionó ningún archivo", "danger")
        return redirect(url_for('perfil_paciente', curp=curp))
        
    file = request.files['estudio_medico']
    if file.filename == '':
        flash("Archivo vacío", "danger")
        return redirect(url_for('perfil_paciente', curp=curp))
        
    if file:
        # Renombrar el archivo de forma segura incluyendo la CURP del paciente y la fecha
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = secure_filename(f"{curp}_{timestamp}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_DOCS_FOLDER'], filename)
        file.save(filepath)
        
        # Registrar el documento en MongoDB en una lista o colección dedicada
        nuevo_documento = {
            "curp_paciente": curp,
            "nombre_archivo": file.filename,
            "ruta_archivo": f"/{filepath}",
            "fecha_subida": datetime.now().strftime("%d/%m/%Y - %H:%M")
        }
        
        # Insertamos en una nueva colección del expediente
        db.expedientes_archivos.insert_one(nuevo_documento)
        
    return redirect(url_for('perfil_paciente', curp=curp))


@app.route('/logout')
def logout():
    session.clear() # Borra absolutamente todo el historial de la sesión actual
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login_page'))

@app.after_request
def add_header(response):
    """
    Agrega cabeceras HTTP para evitar que el navegador guarde en caché
    las páginas protegidas y evitar el truco del botón 'Atrás'.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/update_general/<curp>', methods=['POST'])
def update_general(curp):
    antecedentes = request.form.get('antecedentes')
    alergias = request.form.get('alergias')
    db.pacientes.update_one(
        {"curp": curp},
        {"$set": {"general.antecedentes": antecedentes, "general.alergias": alergias}}
    )
    flash('Información actualizada con éxito', 'success')
    return redirect(url_for('ver_expediente', curp=curp))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
