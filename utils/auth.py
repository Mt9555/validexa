from flask_httpauth import HTTPBasicAuth
from flask import jsonify

auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
  #hardcoded value for now... not safe
  if username == 'manhattan' and password == 'associate':
    return True
  return False

@auth.error_handler
def unauthorized():
  return jsonify({'error': 'Unauthorized access'}), 401
