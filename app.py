import os
import tempfile
import logging
import time
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from ftplib import FTP
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure key for flash messages (use fixed key in production)

# Configuration
STORAGE_MODE = 'local'  # Set to 'ftp' for FTP storage, 'local' for local storage
LOCAL_UPLOAD_DIR = os.path.join(os.getcwd(), 'uploads')  # Local storage directory

# FTP Configuration (optional, used only if STORAGE_MODE = 'ftp')
FTP_HOST = "192.168.100.5"
FTP_PORT = 2221
FTP_USER = "database"
FTP_PASS = "password1599"
FTP_UPLOAD_FOLDER = "/Uploads"

# Function to format file size
def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

# Initialize FTP connection (FTP mode)
def init_ftp():
    ftp = FTP()
    try:
        logging.debug(f"Connecting to FTP: {FTP_HOST}:{FTP_PORT}")
        ftp.connect(FTP_HOST, FTP_PORT, timeout=10)
        ftp.login(FTP_USER, FTP_PASS)
        return ftp
    except Exception as e:
        logging.error(f"FTP connection failed: {e}")
        raise

# Get list of files
def get_file_list():
    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            files = ftp.nlst()
            logging.debug(f"Retrieved FTP file list: {files}")
            ftp.quit()
            return files
        except Exception as e:
            logging.error(f"Error retrieving FTP file list: {e}")
            return []
    else:
        try:
            os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
            files = os.listdir(LOCAL_UPLOAD_DIR)
            logging.debug(f"Retrieved local file list: {files}")
            return files
        except Exception as e:
            logging.error(f"Error retrieving local file list: {e}")
            return []

# Get file size
def get_file_size(filename):
    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            size = ftp.size(filename)
            logging.debug(f"File size for {filename}: {size} bytes")
            ftp.quit()
            return size if size is not None else 0
        except Exception as e:
            logging.error(f"Error getting FTP file size for {filename}: {e}")
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    ftp.retrbinary(f'RETR {filename}', tmp_file.write)
                    size = os.path.getsize(tmp_file.name)
                    os.remove(tmp_file.name)
                    logging.debug(f"Fallback size for {filename}: {size} bytes")
                    ftp.quit()
                    return size
            except Exception as fallback_e:
                logging.error(f"Fallback size retrieval failed for {filename}: {fallback_e}")
                ftp.quit()
                return 0
    else:
        try:
            file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
            size = os.path.getsize(file_path)
            logging.debug(f"Local file size for {filename}: {size} bytes")
            return size
        except Exception as e:
            logging.error(f"Error getting local file size for {filename}: {e}")
            return 0

# Function to read text file
def read_file(filename):
    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                ftp.retrbinary(f'RETR {filename}', tmp_file.write)
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                content = f.read()
            os.remove(tmp_file.name)
            ftp.quit()
            logging.debug(f"Successfully read FTP file: {filename}")
            return content
        except Exception as e:
            logging.error(f"Error reading FTP file {filename}: {e}")
            return None
    else:
        try:
            file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logging.debug(f"Successfully read local file: {filename}")
            return content
        except Exception as e:
            logging.error(f"Error reading local file {filename}: {e}")
            return None

# Main page
@app.route('/')
def index():
    files = get_file_list()
    files_with_sizes = []
    total_size = 0
    for f in files:
        size = get_file_size(f)
        total_size += size
        files_with_sizes.append((f, format_file_size(size)))
    total_size_formatted = format_file_size(total_size)
    logging.debug(f"Total size: {total_size} bytes ({total_size_formatted})")
    return render_template('index.html', files=files_with_sizes, total_size=total_size_formatted)

# File preview page
@app.route('/preview/<filename>')
def preview(filename):
    file_content = None
    file_type = None
    try:
        text_extensions = ('.txt', '.py', '.cpp', '.h', '.json', '.xml')
        if filename.lower().endswith(text_extensions):
            file_content = read_file(filename)
            file_type = 'text'
        elif filename.lower().endswith(('.jpg', '.png')):
            file_type = 'image'
        elif filename.lower().endswith('.mp4'):
            file_type = 'video'
        logging.debug(f"Preview for {filename}: type={file_type}")
    except Exception as e:
        logging.error(f"Error previewing file {filename}: {e}")
        flash(f"Error previewing file: {str(e)}")
    return render_template('preview.html', file=filename, file_content=file_content, file_type=file_type)

# Upload file
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file:
        flash('No file selected for upload.')
        return redirect(url_for('index'))
    
    filename = secure_filename(file.filename)
    if not filename:
        flash('Invalid filename.')
        return redirect(url_for('index'))

    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            ftp.storbinary(f"STOR {filename}", file.stream)
            ftp.quit()
            logging.debug(f"File uploaded to FTP: {filename}")
            flash(f'File {filename} uploaded successfully.')
        except Exception as e:
            logging.error(f"Error uploading file to FTP {filename}: {e}")
            flash(f'Error uploading file to FTP: {str(e)}')
    else:
        try:
            os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
            file.save(file_path)
            logging.debug(f"File uploaded locally: {filename}")
            flash(f'File {filename} uploaded successfully.')
        except Exception as e:
            logging.error(f"Error uploading file locally {filename}: {e}")
            flash(f"Error uploading file locally: {str(e)}")
    return redirect(url_for('index'))

# Download file
@app.route('/download/<filename>')
def download(filename):
    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                ftp.retrbinary(f'RETR {filename}', tmp_file.write)
                tmp_file_path = tmp_file.name
            ftp.quit()
            response = send_file(tmp_file_path, as_attachment=True, download_name=filename)
            @response.call_on_close
            def remove_temp_file():
                try:
                    os.remove(tmp_file_path)
                except Exception as e:
                    logging.error(f"Error removing temp file {tmp_file_path}: {e}")
            logging.debug(f"File downloaded from FTP: {filename}")
            return response
        except Exception as e:
            logging.error(f"Error downloading file from FTP {filename}: {e}")
            flash(f"Error downloading file: {str(e)}")
            return redirect(url_for('index'))
    else:
        try:
            file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
            logging.debug(f"File downloaded locally: {filename}")
            return send_file(file_path, as_attachment=True, download_name=filename)
        except Exception as e:
            logging.error(f"Error downloading file locally {filename}: {e}")
            flash(f"Error downloading file: {str(e)}")
            return redirect(url_for('index'))

# Delete file
@app.route('/delete/<filename>')
def delete(filename):
    if STORAGE_MODE == 'ftp':
        try:
            ftp = init_ftp()
            ftp.cwd(FTP_UPLOAD_FOLDER)
            ftp.delete(filename)
            ftp.quit()
            logging.debug(f"File deleted from FTP: {filename}")
            flash(f'File {filename} deleted successfully.')
        except Exception as e:
            logging.error(f"Error deleting file from FTP {filename}: {e}")
            flash(f"Error deleting file: {str(e)}")
    else:
        try:
            file_path = os.path.join(LOCAL_UPLOAD_DIR, filename)
            os.remove(file_path)
            logging.debug(f"File deleted locally: {filename}")
            flash(f'File {filename} deleted successfully.')
        except Exception as e:
            logging.error(f"Error deleting file locally {filename}: {e}")
            flash(f"Error deleting file: {str(e)}")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)