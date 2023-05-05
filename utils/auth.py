from dotenv import load_dotenv
load_dotenv()

import os
from flask_httpauth import HTTPBasicAuth
from flask import jsonify

auth = HTTPBasicAuth()
ADMIN_USR = os.getenv('AUSER')
ADMIN_PASS = os.getenv('APASS')

@auth.verify_password
def verify_password(username, password):
  if username == ADMIN_USR and password == ADMIN_PASS:
    return True
  return False

@auth.error_handler
def unauthorized():
  return jsonify({'error': 'Unauthorized access'}), 401
