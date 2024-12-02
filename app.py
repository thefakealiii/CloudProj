from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file, abort
import pyodbc
import os
from werkzeug.utils import secure_filename
from io import BytesIO

app = Flask(__name__)
server = 'DESKTOP-VMJ10VF\\SQLEXPRESS'
database = 'UserFiles'
username = 'zaki'  # Ensure this is correct
password = '12365'  # Ensure this is correct
conn_str = f'DRIVER={{SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'

# File upload settings
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

app.secret_key = os.urandom(24)  # Generate a random secret key for session management

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return pyodbc.connect(conn_str)  # Use conn_str here

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()

            if user:
                session['user_id'] = user[0]  # Assuming the first column is the user ID
                return redirect(url_for('upload_file'))  # Redirect to the upload file page
            else:
                return "Invalid username or password"
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

            # Check if the file already exists for versioning
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM UserFiles WHERE user_id = ? AND file_name = ?", (user_id, filename))
                existing_file = cursor.fetchone()

                if existing_file:
                    # Increment the version number for the new upload
                    new_version = existing_file[3] + 1  # Assuming the fourth column is the version
                    cursor.execute("UPDATE UserFiles SET file_data = ?, version = ? WHERE id = ?",
                                   (file_data, new_version, existing_file[0]))
                else:
                    cursor.execute("INSERT INTO UserFiles (user_id, file_name, file_data, version) VALUES (?, ?, ?, ?)",
                                   (user_id, filename, file_data, 1))

                conn.commit()

            return redirect(url_for('list_files'))  # Redirect to the list of files after upload
        else:
            return jsonify({"error": "File type not allowed"}), 400

    return render_template('upload.html')  # Render upload template for GET request

@app.route('/files', methods=['GET'])
def list_files():
    user_id = session.get('user_id')
    if user_id is None:
        return jsonify({"error": "User not logged in"}), 403

    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Files per page
    offset = (page - 1) * per_page

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM UserFiles WHERE user_id = ? AND file_name LIKE ?",
                       (user_id, f'%{search_query}%'))
        total_files = cursor.fetchone()[0]

        cursor.execute(
            "SELECT id, file_name FROM UserFiles WHERE user_id = ? AND file_name LIKE ? ORDER BY id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            (user_id, f'%{search_query}%', offset, per_page))
        files = cursor.fetchall()

    return render_template('files.html', files=files, total_files=total_files, search_query=search_query)


@app.route('/download/<int:file_id>', methods=['GET'])
def download_file(file_id):
    user_id = session.get('user_id')
    if user_id is None:
        return jsonify({"error": "User not logged in"}), 403

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, file_data FROM UserFiles WHERE id = ? AND user_id = ?", (file_id, user_id))
        user_file = cursor.fetchone()

    if user_file is None:
        abort(404)  # File not found

    file_name = user_file[0]
    file_data = user_file[1]  # Ensure this is bytes

    return send_file(BytesIO(file_data), download_name=file_name, as_attachment=True)  # Updated line

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=True)