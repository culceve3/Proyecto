from flask import Flask, render_template, redirect, url_for, session, request
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.secret_key = "clave_secreta_123"

#conexion a base de datos
def get_db():
    conn = sqlite3.connect("Restaurantillo.db")
    conn.row_factory = sqlite3.Row 
    return conn

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['usuario']
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM empleados WHERE nombre_empleado = ? AND contraseña = ?", 
                       (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['usuario'] = user['nombre_empleado']
            session['rol'] = user['puesto'].lower()
            if session['rol'] in ['mesero', 'mesera']:
                return redirect(url_for('mesero'))
            elif session['rol'] in ['cocinero', 'chef']:
                return redirect(url_for('cocinero'))
            elif session['rol'] in ['supervisora', 'gerente']:
                return redirect(url_for('gerente'))
            elif session['rol'] in ['hostess']:
                return redirect(url_for('reservaciones'))
            else:
                return redirect(url_for('index'))
        return render_template('login.html', error="Usuario o contraseña incorrectos")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

from datetime import datetime

@app.route('/gerente')
def gerente():
    if session.get('rol') != 'gerente':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes ORDER BY hora ASC")
    ordenes = cursor.fetchall()

    cursor.execute("SELECT * FROM menu ORDER BY categoria, nombre_platillo")
    menu = cursor.fetchall()

    cursor.execute("SELECT * FROM empleados ORDER BY puesto, nombre_empleado")
    empleados = cursor.fetchall()

    cursor.execute("""
        SELECT SUM(m.precio) AS total
        FROM ordenes o
        JOIN menu m ON o.descripcion = m.nombre_platillo
        WHERE o.estado = 'terminado'
    """)
    ingresos = cursor.fetchone()['total'] or 0

    current_time = datetime.now().strftime("%H:%M")

    conn.close()
    return render_template('gerente.html',
                           ordenes=ordenes,
                           menu=menu,
                           empleados=empleados,
                           ingresos=ingresos,
                           current_time=current_time)

@app.route('/cocinero', methods=['GET'])
def cocinero():
    if session.get('rol') != 'cocinero':
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM ordenes
        WHERE estado != 'pagado'
        ORDER BY id_orden ASC
    """)
    ordenes = cursor.fetchall()

    conn.close()
    return render_template('cocinero.html', ordenes=ordenes)

@app.route('/cocinero/iniciar/<int:id>', methods=['POST'])
def cocinero_iniciar(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ordenes SET estado = 'en_proceso' WHERE id_orden = ?",
        (id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('cocinero'))

@app.route('/cocinero/terminar/<int:id>', methods=['POST'])
def cocinero_terminar(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ordenes SET estado = 'terminado' WHERE id_orden = ?",
        (id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('cocinero'))

@app.route('/mesero')
def mesero():
    if session.get('rol') not in ['mesero', 'mesera']:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ordenes ORDER BY id_orden ASC")
    ordenes = cursor.fetchall()

    cursor.execute("SELECT nombre_platillo FROM menu")
    menu = cursor.fetchall()

    current_time = datetime.now().strftime("%H:%M")

    conn.close()
    return render_template(
        'mesero.html',
        ordenes=ordenes,
        menu=menu,
        current_time=current_time
    )

@app.route('/agregar_orden', methods=['POST'])
def agregar_orden():

    if session.get('rol') not in ['mesero', 'mesera']:
        return redirect(url_for('login'))

    mesa = request.form['mesa']
    descripcion = request.form['descripcion']
    hora = request.form['hora']

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ordenes (mesa, descripcion, estado, hora)
        VALUES (?, ?, 'pendiente', ?)
    """, (mesa, descripcion, hora))

    conn.commit()
    conn.close()

    return redirect(url_for('mesero'))

@app.route('/cuenta_pedido/<mesa>/pagar', methods=['POST'])
def pagar_cuenta(mesa):
    if session.get('rol') not in ['mesero', 'mesera']:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.id_orden, o.descripcion, m.precio
        FROM ordenes o
        JOIN menu m ON o.descripcion = m.nombre_platillo
        WHERE o.mesa = ? AND o.estado = 'terminado'
    """, (mesa,))
    ordenes = cursor.fetchall()

    total = sum([o['precio'] for o in ordenes])
    fecha = datetime.now().strftime("%Y-%m-%d")
    metodo = request.form['metodo_pago']

    cursor.execute("SELECT COUNT(*) FROM pagos")
    count = cursor.fetchone()[0] + 1
    id_venta = f"V{count:04d}"
    id_pago = f"P{count:04d}"

    cursor.execute("""
        INSERT INTO pagos (id_pago, id_venta, metodo_pago, fecha_pago, monto)
        VALUES (?, ?, ?, ?, ?)
    """, (id_pago, id_venta, metodo, fecha, total))

    cursor.execute("UPDATE ordenes SET estado = 'pagado' WHERE mesa = ?", (mesa,))
    conn.commit()
    conn.close()
    return redirect(url_for('mesero'))

@app.route('/reservaciones', methods=['GET', 'POST'])
def reservaciones():
    if session.get('rol') not in ['gerente', 'hostess']:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        id_cliente = request.form['id_cliente']
        id_mesa = request.form['id_mesa']
        fecha = request.form['fecha']
        hora = request.form['hora']
        num_personas = request.form['num_personas']

        cursor.execute("SELECT COUNT(*) FROM reservas")
        count = cursor.fetchone()[0] + 1
        id_reserva = f"R{count:04d}"

        cursor.execute("""
            INSERT INTO reservas (id_reserva, id_cliente, id_mesa, fecha, hora, num_personas)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_reserva, id_cliente, id_mesa, fecha, hora, num_personas))
        conn.commit()

    cursor.execute("SELECT * FROM reservas ORDER BY fecha, hora ASC")
    reservas = cursor.fetchall()
    conn.close()
    return render_template('reservaciones.html', reservas=reservas)

@app.route('/orden_mesa/iniciar/<int:id>', methods=['POST'])
def iniciar_pedido(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET estado = 'en proceso' WHERE id_orden = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('orden_mesa'))

@app.route('/orden_mesa/terminar/<int:id>', methods=['POST'])
def terminar_pedido(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET estado = 'terminado' WHERE id_orden = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('orden_mesa'))


@app.route('/cuenta_pedido/<mesa>', methods=['GET'])
def cuenta_pedido(mesa):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ordenes WHERE mesa = ? AND estado = 'terminado'", (mesa,))
    ordenes = cursor.fetchall()
    cursor.execute("SELECT nombre_platillo, precio FROM menu")
    menu_items = cursor.fetchall()

    precios = {item['nombre_platillo']: item['precio'] for item in menu_items}

    total = 0
    for o in ordenes:
        platillo = o['descripcion']
        total += precios.get(platillo, 0)

    conn.close()
    return render_template('cuenta_pedido.html', mesa=mesa, ordenes=ordenes, precios=precios, total=total)

if __name__ == '__main__':
    app.run(debug=True)
