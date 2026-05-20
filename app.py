from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
import os
import random
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secreto_eus_mexico" 

UPLOAD_FOLDER = 'static/firmas'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

UPLOAD_DOCS_FOLDER = 'static/expedientes'
app.config['UPLOAD_DOCS_FOLDER'] = UPLOAD_DOCS_FOLDER
os.makedirs(UPLOAD_DOCS_FOLDER, exist_ok=True)

# !!! CAMBIO 1: CONEXIÓN FLEXIBLE
MONGO_URI = os.getenv("MONGO_URL", "mongodb+srv://PROYECTOEUSMEX:rSIv8WS387liKnY@clustereusmex.gv2jm3t.mongodb.net/?appName=ClusterEUSMEX")
client = MongoClient(MONGO_URI)
db = client['expediente_salud']

# --- RUTAS DE NAVEGACIÓN ---
@app.route('/', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password_plano = request.form.get('password')
        
        # Buscamos al usuario solo por su username
        usuario = db.usuarios.find_one({"username": username})
        
        # CIBERSEGURIDAD: Comparamos el password escrito con el hash de la BD
        if usuario and check_password_hash(usuario['password'], password_plano):
            session['usuario_id'] = str(usuario['_id'])
            return redirect(url_for('dashboard'))
        else:
            # Si falla, vuelve a cargar el login (puedes pasarle un mensaje de error si quieres)
            return render_template('login.html', error="Usuario o contraseña incorrectos")
            
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password_plano = request.form.get('password')
        nombre = request.form.get('nombre')
        
        # CIBERSEGURIDAD: Ciframos la contraseña antes de guardarla en Mongo
        password_cifrado = generate_password_hash(password_plano)
        
        nuevo_usuario = {
            "username": username,
            "password": password_cifrado,  # Guardamos el hash seguro
            "nombre": nombre,
            "rol": "medico"
        }
        db.usuarios.insert_one(nuevo_usuario)
        return redirect(url_for('login_page'))
        
    return render_template('registro.html')

@app.route('/dashboard')
def dashboard():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))
    
    medico_object_id = ObjectId(u_id)
    medico_data = db.usuarios.find_one({"_id": medico_object_id})
    
    # 1. Obtener las citas pendientes de este doctor desde MongoDB
    citas_cursor = db.citas.find({"doctor_id": medico_object_id, "estado": "Pendiente"})
    lista_citas = list(citas_cursor)
    
    # 2. EL CRUCE CLAVE: Buscar el nombre real de cada paciente usando su CURP
    for cita in lista_citas:
        curp = cita.get('curp_paciente') or cita.get('curp') # Soporta ambos nombres por si acaso
        
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
            
    # ====================================================================
    # 3. CONSULTA CORREGIDA: Filtra si el ID está en la lista O en el campo antiguo
    # ====================================================================
    query_pacientes = {
        "$or": [
            {"medicos_ids": medico_object_id},  # Nuevo formato (Arreglo de médicos)
            {"medico_id": medico_object_id}    # Formato anterior (Compatibilidad)
        ]
    }
    pacientes_filtrados = list(db.pacientes.find(query_pacientes))
    
    # ====================================================================
    # NUEVO: CÁLCULO DE INDICADORES SIN ALTERAR TU LÓGICA EXISTENTE
    # ====================================================================
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    
    # Total de Pacientes pertenecientes a este médico específico
    total_pacientes = len(pacientes_filtrados)
    
    # Consultas registradas el día de hoy en el sistema global
    # Nota: Si tu formulario de consultas guarda en formato "dd/mm/yyyy", puedes dejar un find alterno. 
    # Lo ideal es estandarizar a fecha_hoy (YYYY-MM-DD).
    consultas_hoy = db.consultas.count_documents({"fecha": fecha_hoy})
    
    # Conteo dinámico de documentos adjuntos de los pacientes asignados a este doctor
    documentos_totales = 0
    for p in pacientes_filtrados:
        if 'documentos' in p and isinstance(p['documentos'], list):
            documentos_totales += len(p['documentos'])
            
    # CORREGIDO: Citas programadas para HOY, filtrando por el MÉDICO actual y estado "Pendiente"
    citas_hoy = db.citas.count_documents({
        "doctor_id": medico_object_id,
        "fecha": fecha_hoy,
        "estado": "Pendiente"
    })
    # ====================================================================
            
    # 4. Pasar las variables procesadas a tu index.html
    # Enviamos tanto 'pacientes' como 'pacientes_completos' e incluimos los indicadores que tu HTML requiere
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

@app.route('/auth/register', methods=['POST'])
def register_action():
    usuario = request.form.get('usuario')
    email = request.form.get('email')
    cedula = request.form.get('cedula')
    password_plano = request.form.get('password') # Renombrado para mayor claridad
    
    if db.usuarios.find_one({"$or": [{"username": usuario}, {"cedula": cedula}]}):
        flash('El usuario o la cédula ya están registrados', 'warning')
        return redirect(url_for('registro_page'))

    # CIBERSEGURIDAD: Ciframos el password antes de meterlo a la base de datos
    password_cifrado = generate_password_hash(password_plano)

    db.usuarios.insert_one({
        "username": usuario, 
        "email": email,
        "cedula": cedula,
        "password": password_cifrado # <--- ¡Ahora sí viaja ultra seguro!
    })
    flash('¡Médico registrado con éxito!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/auth/login', methods=['POST'])
def login_action():
    usuario_ingresado = request.form.get('usuario')
    password_ingresado = request.form.get('password')
    
    # 1. Buscamos al usuario únicamente por su nombre de usuario
    user = db.usuarios.find_one({"username": usuario_ingresado})
    
    # 2. CIBERSEGURIDAD: Validamos la contraseña usando la función de hash
    if user and check_password_hash(user['password'], password_ingresado):
        # GUARDAMOS EL ID en la sesión como 'usuario_id'
        session['usuario_id'] = str(user['_id']) 
        return redirect(url_for('dashboard'))
    else:
        flash('Contraseña o usuario incorrectos', 'danger') 
        return redirect(url_for('login_page'))

@app.route('/perfil-medico')
def perfil():
    # Buscamos el ID que guardamos en el login_action
    u_id = session.get('usuario_id')
    
    if not u_id:
        print("DEBUG: No se encontró usuario_id en sesión, redirigiendo al login.")
        return redirect(url_for('login_page'))

    from bson.objectid import ObjectId
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
    
    # 2. PROCESAR LA FOTO DE PERFIL (¡Añade este bloque!)
    if 'foto' in request.files:
        foto_file = request.files['foto']
        if foto_file and foto_file.filename != '':
            foto_filename = secure_filename(f"foto_{u_id}_{foto_file.filename}")
            foto_filepath = os.path.join(app.config['UPLOAD_FOLDER'], foto_filename)
            foto_file.save(foto_filepath)
            update_data["foto_url"] = f"/{foto_filepath}"

    # 3. Procesar el archivo de la Firma
    if 'firma' in request.files:
        file = request.files['firma']
        if file and file.filename != '':
            filename = secure_filename(f"firma_{u_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            update_data["firma_url"] = f"/{filepath}"

    # 4. Guardar en MongoDB
    db.usuarios.update_one(
        {"_id": ObjectId(u_id)},
        {"$set": update_data}
    )
    return redirect(url_for('perfil'))

# --- LÓGICA DE PACIENTES Y EXPEDIENTE ---
@app.route('/add_patient', methods=['POST'])
def add_patient():
    # 1. Validar sesión del doctor y obtener su ID
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))

    # ====================================================================
    # FLUJO A: VINCULAR PACIENTE EXISTENTE POR CURP (DESDE LA BARRA DE IMPORTACIÓN)
    # ====================================================================
    curp_buscar = request.form.get('curp_buscar')
    if curp_buscar:
        curp_buscar = curp_buscar.upper().strip()
        
        # Buscamos si el paciente existe globalmente en la base de datos
        paciente_existente = db.pacientes.find_one({"curp": curp_buscar})
        
        if paciente_existente:
            # CORRECCIÓN CLAVE: Usamos $addToSet en lugar de $set para agregarlo a una lista de médicos
            db.pacientes.update_one(
                {"curp": curp_buscar},
                {"$addToSet": {"medicos_ids": ObjectId(u_id)}} # Guardamos en plural como lista
            )
            flash('Paciente vinculado exitosamente a tu directorio', 'success')
        else:
            flash('No se encontró ningún paciente con esa CURP en el sistema global', 'danger')
            
        return redirect(url_for('lista_pacientes'))

    # ====================================================================
    # FLUJO B: REGISTRAR UN PACIENTE NUEVO DESDE CERO (DESDE EL FORMULARIO ORIGINAL)
    # ====================================================================
    # Recogemos los datos limpios desde el formulario de manera segura
    nombre = request.form.get('nombre', '').upper().strip()
    curp = request.form.get('curp', '').upper().strip()
    nss = request.form.get('nss', '').strip()
    edad = request.form.get('edad', '').strip()

    # Validación de seguridad por si envían el formulario vacío
    if not nombre or not curp:
        flash('El nombre y la CURP son obligatorios para un nuevo registro', 'danger')
        return redirect(url_for('dashboard'))

    # Validación de duplicados en la base de datos
    # Evita que se dupliquen CURP o NSS ya existentes en el sistema global
    existente = db.pacientes.find_one({"$or": [{"curp": curp}, {"nss": nss}]})

    if existente:
        flash('Este CURP o NSS ya existe en el sistema', 'danger')
        return redirect(url_for('dashboard'))

    # Si no existe, creamos un ÚNICO registro completo para el nuevo paciente
    nuevo_paciente = {
        "nombre": nombre,
        "curp": curp,
        "nss": nss,
        "edad": edad,
        "no_expediente": f"2026-{curp[:4]}" if len(curp) >= 4 else "2026-TEMP",
        "ultima_visita": datetime.now().strftime("%d %b %Y - %H:%M"),
        "estado": "Activo",
        "estudios": [],
        "expediente_datos": {},
        # CORRECCIÓN CLAVE: Lo guardamos desde el inicio como una lista con el primer ID
        "medicos_ids": [ObjectId(u_id)]
    }
    
    # Insertamos el nuevo paciente en MongoDB
    db.pacientes.insert_one(nuevo_paciente)
    flash('Paciente registrado y añadido con éxito', 'success')
    return redirect(url_for('dashboard'))

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

@app.route('/perfil_paciente/<curp>')
@app.route('/paciente/<curp>')   # <--- AGREGA ESTA LÍNEA
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

from flask import request, flash # Asegúrate de tener importado 'request' y opcionalmente 'flash'

@app.route('/agendar_cita', methods=['POST'])
def agendar_cita():
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page'))

    # 1. Capturar los datos enviados por el formulario inline
    curp = request.form.get('curp')
    fecha = request.form.get('fecha') # Viene en formato YYYY-MM-DD por el input tipo date
    hora = request.form.get('hora')   # Viene en formato HH:MM por el input tipo time
    motivo = request.form.get('motivo')

    # Validación rápida de que los campos obligatorios no vengan vacíos
    if not curp or not fecha or not hora or not motivo:
        # Puedes usar flash si manejas mensajes en el HTML o solo redirigir
        return redirect(url_for('agenda_page'))

    # 2. Construir el documento para la colección 'citas'
    nueva_cita = {
        "doctor_id": ObjectId(u_id),
        "curp_paciente": curp,         # Guardamos la CURP vinculada
        "fecha": fecha,
        "hora": hora,
        "motivo": motivo,
        "estado": "Pendiente"          # Estado inicial obligatorio para que lo lea tu ruta de /agenda
    }

    # 3. Insertar en MongoDB
    db.citas.insert_one(nueva_cita)

    # 4. Redirigir de vuelta a la agenda para que se refresque y aparezca la nueva cita
    return redirect(url_for('agenda_page'))

@app.route('/agenda')
def agenda_page():
    # 1. Validar de inmediato que la sesión esté activa
    u_id = session.get('usuario_id')
    if not u_id:
        return redirect(url_for('login_page')) # Si no hay sesión, al Login
    
    # 2. Buscar al doctor logueado para que la barra superior no marque error
    doctor_data = db.usuarios.find_one({"_id": ObjectId(u_id)})
    
    # 3. FILTRAR CITAS POR DOCTOR: Traemos solo las citas pendientes de ESTE doctor
    # Nota: Asegúrate de si tu colección real se llama 'agenda' o 'citas'. 
    # Según tu HTML 'agenda.html', el bucle lee la variable 'citas' para pintar el calendario.
    citas = list(db.citas.find({
        "doctor_id": ObjectId(u_id), 
        "estado": "Pendiente"
    }).sort([("fecha", 1), ("hora", 1)]))
    
    # 4. CONTADOR FILTRADO: Contar cuántas citas tiene HOY este doctor específicamente
    hoy = datetime.now().strftime("%Y-%m-%d")
    citas_hoy = db.citas.count_documents({
        "doctor_id": ObjectId(u_id),
        "fecha": hoy, 
        "estado": "Pendiente"
    })
    
    # 5. Enviamos todo limpio al HTML
    return render_template(
        'agenda.html', 
        citas=citas, 
        citas_hoy=citas_hoy, 
        doctor=doctor_data
    )

import json
from flask import jsonify

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

@app.route('/expediente/<curp>')
def ver_expediente(curp):
    # Buscamos al paciente en la base de datos
    paciente = db.pacientes.find_one({"curp": curp})
    
    if not paciente:
        return "Paciente no encontrado", 404
        
    # Pasamos el objeto 'paciente' completo al HTML
    return render_template('expediente.html', paciente=paciente)

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
    
# --- RUTAS PARA ANEXOS ---


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
    
@app.route('/expediente/<curp>')
def abrir_expediente(curp):
    # Buscamos los datos del paciente para que el asistente ya aparezca con su nombre
    paciente = db.pacientes.find_one({"curp": curp})
    return render_template('expediente.html', paciente=paciente)

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
    # CORRECCIÓN: Quitamos el .upper() para no alterar las cadenas de búsqueda de texto de los nombres
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


# --- LÓGICA DE CONSULTA ---

@app.route('/preparar_consulta', methods=['POST'])
def preparar_consulta():
    curp = request.form.get('curp').upper()
    paciente = db.pacientes.find_one({"curp": curp})
    if paciente:
        return render_template('nuevaconsulta.html', paciente=paciente)
    else:
        flash('El paciente no está registrado.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/guardar_consulta/<curp>', methods=['POST'])
def guardar_consulta(curp):
    ahora = datetime.now()
    
    # Recogemos TODOS los datos del nuevo formulario
    nueva_nota = {
        "curp_paciente": curp,
        "fecha": ahora.strftime("%d/%m/%Y"),
        "hora": ahora.strftime("%H:%M"),
        "peso": request.form.get('peso'),
        "talla": request.form.get('talla'),
        "temp": request.form.get('temp'),
        "presion": request.form.get('presion'),
        "motivo": request.form.get('motivo'),
        "diagnostico": request.form.get('diagnostico'),
        "pronostico": request.form.get('pronostico'),
        "tratamiento": request.form.get('tratamiento')
    }
    
    # 1. Guardamos la consulta en la colección de consultas
    db.consultas.insert_one(nueva_nota)
    
    # 2. Actualizamos la fecha de última visita en la colección de pacientes
    # Usamos el formato para que tu tabla del Dashboard se vea con hora
    fecha_tabla = ahora.strftime("%d %b %Y - %H:%M")
    db.pacientes.update_one(
        {"curp": curp}, 
        {"$set": {"ultima_visita": fecha_tabla}}
    )
    
    # 3. Jalamos los datos del paciente para la receta
    paciente_data = db.pacientes.find_one({"curp": curp})
    
    # 4. IMPORTANTE: Usamos el nombre que elegiste 'nuevaconsulta.html'
    # Pero aquí devolvemos 'receta.html' porque ya terminó la consulta
    return render_template('receta.html', consulta=nueva_nota, paciente=paciente_data)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
