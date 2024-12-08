from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file, abort
import pymysql
import os
from werkzeug.utils import secure_filename
from io import BytesIO

app = Flask(__name__)

# Database configuration
server = '34.18.40.72'
database = 'UserFiles'
username = 'sqlserver'
password = '123123123'

# File upload settings
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

app.secret_key = os.urandom(24)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return pymysql.connect(
        host=server,
        database=database,
        user=username,
        password=password,
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO Users (username, password) VALUES (%s, %s)", (username, password))
                conn.commit()
            return redirect(url_for('login'))
        except pymysql.Error as e:
            return f"Registration failed: {str(e)}"
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM Users WHERE username = %s AND password = %s", (username, password))
                    user = cursor.fetchone()

                    if user:
                        session['user_id'] = user['id']
                        return redirect(url_for('upload_file'))
                    else:
                        return "Invalid username or password"
        except pymysql.Error as e:
            return f"Login failed: {str(e)}"
    return render_template('login.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"error": "No file part in the request"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            user_id = session.get('user_id')
            if user_id is None:
                return jsonify({"error": "User not logged in"}), 403

            filename = secure_filename(file.filename)
            file_data = file.read()

            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT * FROM UserFiles WHERE user_id = %s AND file_name = %s", (user_id, filename))
                        existing_file = cursor.fetchone()

                        if existing_file:
                            new_version = existing_file['version'] + 1
                            cursor.execute("UPDATE UserFiles SET file_data = %s, version = %s WHERE id = %s",
                                       (file_data, new_version, existing_file['id']))
                        else:
                            cursor.execute("INSERT INTO UserFiles (user_id, file_name, file_data, version) VALUES (%s, %s, %s, %s)",
                                       (user_id, filename, file_data, 1))

                    conn.commit()
                return redirect(url_for('list_files'))
            except pymysql.Error as e:
                return jsonify({"error": f"Upload failed: {str(e)}"}), 500
        else:
            return jsonify({"error": "File type not allowed"}), 400

    return render_template('upload.html')

@app.route('/files', methods=['GET'])
def list_files():
    user_id = session.get('user_id')
    if user_id is None:
        return jsonify({"error": "User not logged in"}), 403

    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM UserFiles WHERE user_id = %s AND file_name LIKE %s",
                           (user_id, f'%{search_query}%'))
                total_files = cursor.fetchone()['count']

                cursor.execute(
                    "SELECT id, file_name FROM UserFiles WHERE user_id = %s AND file_name LIKE %s ORDER BY id LIMIT %s OFFSET %s",
                    (user_id, f'%{search_query}%', per_page, offset))
                files = cursor.fetchall()

        return render_template('files.html', files=files, total_files=total_files, search_query=search_query)
    except pymysql.Error as e:
        return jsonify({"error": f"Failed to list files: {str(e)}"}), 500

@app.route('/download/<int:file_id>', methods=['GET'])
def download_file(file_id):
    user_id = session.get('user_id')
    if user_id is None:
        return jsonify({"error": "User not logged in"}), 403

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT file_name, file_data FROM UserFiles WHERE id = %s AND user_id = %s", (file_id, user_id))
                user_file = cursor.fetchone()

        if user_file is None:
            abort(404)

        file_name = user_file['file_name']
        file_data = user_file['file_data']

        return send_file(BytesIO(file_data), download_name=file_name, as_attachment=True)
    except pymysql.Error as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=True)
