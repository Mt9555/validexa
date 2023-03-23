from dotenv import load_dotenv
load_dotenv()

import os
from flask import Blueprint, request, jsonify
from db.connection import collection
from pymongo.errors import PyMongoError
import random
from utils.limiter import limiter
from marshmallow import Schema, fields, validate
from utils import COUNT, AddressSchema, state_names, misc_abbreviation
from datetime import datetime, timedelta
from bson import ObjectId

avs_routes = Blueprint('avs_routes', __name__)


# TODO: Authentication - Authorization - Features as per instruction

''' --------------------------------------  GET ENDPOINT /api/v1/verify --------------------------------------------- '''

@avs_routes.route('/api/v1/verify', methods=['POST'])
@limiter.limit('30/hour') # limit request to 30 per hr for now
def verify_address():
  try:
    client_data = request.get_json()
    required_address_fields = ['addressLine1', 'addressLine2', 'city', 'stateProv', 'postalCode', 'country']
    for field in required_address_fields:
      if field not in client_data:
        return jsonify({'error': f'Missing required field: {field}'}), 400
    
    db_query = {
      'addressLine1': client_data['addressLine1'],
      'city': client_data['city'],
      'stateProv': client_data['stateProv'],
      'postalCode': client_data['postalCode'],
      'country': client_data['country']
    }
    
    VALID_ADDRESS = collection.find_one(db_query, {'_id': 0})
    if VALID_ADDRESS:
        # dictionary to store recommendations
        recommendations = {}

        reference_id = VALID_ADDRESS['referenceId']
        client_addressLine1 = client_data['addressLine1'].split(' ')

        # Replace address line abbreviations "4500 Due W Rd NW"
        for idx, word in enumerate(client_addressLine1):
          if word.lower() in misc_abbreviation:
            client_addressLine1[idx] = misc_abbreviation[word.lower()]

        client_data['addressLine1'] = ' '.join(client_addressLine1)
        recommendations['addressLine1'] = client_data['addressLine1']

        if len(client_data['postalCode']) == 5:
          # generate random numbers for the last four digits for now
          last_four_digits = str(random.randint(0, 9999)).zfill(4)

          _zip = client_data['postalCode'] + '-' + last_four_digits
          recommendations['postalCode'] = _zip
        else:
          recommendations['postalCode'] = client_data['postalCode']

        if reference_id:
          recommendations['referenceId'] = reference_id

        # Recommend full state name if abbreviated
        if client_data["stateProv"].upper() in state_names:
          recommended_full_state_name = state_names[client_data["stateProv"].upper()]
          recommendations['stateProv'] = recommended_full_state_name
        else:
          recommendations['stateProv'] = client_data['stateProv']

        if client_data["country"].upper() == 'US':
          recommendations['country'] = 'USA'
        else:
          recommendations['country'] = client_data['country']

        recommendations['city'] = client_data['city']
        recommendations['addressLine2'] = client_data['addressLine2']

        response = {
            "avsAddressDetails": {
                "responseStatus": True,
                "addressVerified": True,
                "avsResponseCode": 100,
                "avsResponseDecision": "Success",
                "address": VALID_ADDRESS,
                "recommendedAddresses": {
                    "recommendedAddress": recommendations
                }
            }
        }
    else:
      response = {
        "avsAddressDetails": {
            "responseStatus": True,
            "addressVerified": False,
            "avsResponseCode": 100,
            "avsResponseDecision": "Failure",
            "address": client_data,
        }}
    return jsonify(response), 200
  
  except PyMongoError as e:
    return jsonify({'error': f'Database error: {str(e)}'}), 500
  except Exception as e:
    return jsonify({'error': f'Error: {str(e)}'}), 500


######################################################
#   *    **  * ***  ****  ******  **** * **    **    #
#   ***   **   **  **   **   **   **  ***  **** ******
######################################################

''' --------------------------------------  GET ENDPOINT /api/v1/addresses--------------------------------------------- '''

@avs_routes.route('/api/v1/addresses', methods=['GET'])
@limiter.limit('15/hour') # This limit requests per hour to 15 for now
def get_list_of_addresses():
  '''
      Retrieve all address -> GET /api/v1/addresses 
      Retrieve all addresses in a specific city -> GET /api/v1/addresses?city=Antioch 
      Retrieve a single address by its ID -> GET /api/v1/addresses?id=606cc02cfa8ca5b87d145e4a 
      Retrieve a single address by its referenceId -> GET /api/v1/addresses?ref_id=10130 
      Retrieve a limited number of addresses -> GET /api/v1/addresses?limit=10 
      Retrieve all addresses in a specific state -> GET /api/v1/addresses?stateProv=TN 

  '''
  try:
    addressLine1 = request.args.get('addressLine1')
    city = request.args.get('city')
    stateProv = request.args.get('stateProv')
    postalCode = request.args.get('postalCode')
    country = request.args.get('country')
    limit = request.args.get('limit', type=int)
    address_id = request.args.get('id')
    referenceId = request.args.get('ref_id')

    # construct query based on parameters
    query = {}

    if addressLine1:
      query['addressLine1'] = addressLine1
    if city:
      query['city'] = city
    if stateProv:
      query['stateProv'] = stateProv
    if postalCode:
      query['postalCode'] = postalCode
    if country:
      query['country'] = country
    if referenceId:
      query['referenceId'] = int(referenceId)

    if address_id:
      if ObjectId.is_valid(address_id):
        address = collection.find_one({'_id': ObjectId(address_id)}, {"_id": 0})
        if address:
          return jsonify(address), 200
        else:
          return jsonify({'Message': 'Address not found'}), 404
      else:
        return jsonify({'Message': 'Invalid address ID'}), 400
    elif limit:
      addresses = list(collection.find(query, {"_id": 0}).limit(limit))
    else:
      # If no limit or address ID is specified, return up to 30 addresses
      addresses = list(collection.find(query, {"_id": 0}).limit(30))
    return jsonify(addresses), 200

  except PyMongoError as e:
    return jsonify({'message': 'Database error: {}'.format(str(e))}), 500
  except Exception as e:
    return jsonify({'message': str(e)}), 500


''' --------------------------------------  POST ENDPOINT /api/v1/address/ --------------------------------------------- '''

@avs_routes.route('/api/v1/address', methods=['POST'])
@limiter.limit('5/hour')
def create_new_address():
  '''
    @Description POST /api/v1/address
        Validates the input using the 'Marshmallow' library, checks whether the address already exists in the database, 
        and inserts the new address into the database, returns newly created address and a timestamp of creation. 
  '''
  client_data = request.get_json()

  # Check if address already exists in collection
  if collection.count_documents(client_data) > 0:
    return jsonify({
      'message': 'Address already exists',
      'address': client_data,
      'status': 'failure'
    }), 409
  
  try:
    # Validate the address data using Marshmallow (security)
    address_schema = AddressSchema()
    errors = address_schema.validate(client_data)

    if errors:
      return jsonify({'message': 'Invalid address data', 'errors': errors}), 400
    # Insert the new address into the database
    result = collection.insert_one(client_data)

    # Return the response with the new address data and status code 201 (Created)
    new_address = collection.find_one({'_id': result.inserted_id})
    new_address['_id'] = str(new_address['_id'])

    client_success_response = {
      "time_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "newly_created_address": new_address,
      'status': 'success'
    }
    return jsonify(client_success_response), 201

  except PyMongoError as e:
    return jsonify({'message': 'Database error: {}'.format(str(e))}), 500
  except Exception as e:
    return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500


# --------------------------------------  UPDATE ENDPOINT /api/v1/address/<address_id> ---------------------------------------------

@avs_routes.route("/api/v1/address/<address_id>", methods=["PUT"])
@limiter.limit('3/hour')
def update_address(address_id):
  '''
    @Description PUT - update address - modify existing resources /api/v1/address/<address_id>
    @param address_id: reference_id
        If the address is not found, it returns a 404 error message. If the address is found, 
        it updates the fields and returns a message with old and new addresses.
  '''
  client_data = request.get_json()
  query = {'referenceId': int(address_id)}
  # check if address exists in the database
  db_query_result = collection.find_one(query)

  if db_query_result is None:
    return jsonify({
      'message': 'Address not found',
      'address_id': address_id
    }), 404

  try:
    old_address = db_query_result
    # update the address fields
    collection.update_one(query, {'$set': client_data})
    updated_address = collection.find_one(query)

    succesful_update_message = {
      'message': 'Address Updated successfully',
      'time_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      'status': 'success',
      'old_address': old_address,
      'new_address': updated_address
    }
    # ObjectId not serializable: convert the ObjectId to string
    succesful_update_message['old_address']['_id'] = str(succesful_update_message['old_address']['_id'])
    succesful_update_message['new_address']['_id'] = str(succesful_update_message['new_address']['_id'])

    return jsonify(succesful_update_message), 200

  except PyMongoError as e:
    return jsonify({'message': 'Database error: {}'.format(str(e))}), 500
  except Exception as e:
    return jsonify({'message': 'Error updating address', 'error': str(e)}), 500
