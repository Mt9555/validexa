from dotenv import load_dotenv
load_dotenv()

import os
from flask_httpauth import HTTPBasicAuth
from flask import jsonify

auth = HTTPBasicAuth()
adminUser = os.getenv("AUSER")
adminPass = os.getenv("APASS")

@auth.verify_password
def verify_password(username, password):
  #hardcoded value for now... not safe
  if username == adminUser and password == adminPass:
    return True
  return False

@auth.error_handler
def unauthorized():
  return jsonify({'error': 'Unauthorized access'}), 401
