from dotenv import load_dotenv
load_dotenv()

import os
from flask import Blueprint, request, Response, jsonify
from db.connection import collection
from pymongo.errors import PyMongoError
from utils import AddressSchema, state_names, misc_abbreviation
from utils.limiter import limiter
from datetime import datetime
from io import StringIO
from bson import ObjectId
import random
import csv
import re

avs_routes = Blueprint('avs_routes', __name__)

# TODO: authentication, and authorization.
# error logs for debugging and troubleshooting.

@avs_routes.route('/api/v1/verify', methods=['POST'])
@limiter.limit('30/hour')
def verify_address():
  """
    Verifies address submitted by the client against the address data stored in the database.
    Returns a response object containing the following fields:
    
    - responseStatus (bool): Indicates whether the verification was successful.
    - addressVerified (bool): Indicates whether the submitted address was found in the database.
    - avsResponseCode (int): A code indicating the result of the verification.
    - avsResponseDecision (str): A string indicating the result of the verification.
    - address (dict): The verified address data retrieved from the database.
    - recommendedAddresses (dict): A dictionary containing recommendations for the address data.
    
    If the verification is successful, the `recommendedAddresses` field contains a dictionary with the following fields:
    - addressLine1 (str)
    - city (str)
    - stateProv (str)
    - postalCode (str)
    - country (str)
    - referenceId (str, optional)
    
    If the verification is unsuccessful, the `address` field contains the original address data submitted by the client.
  """
  try:
    client_data = request.get_json()

    # Validate the address data using Marshmallow library
    address_schema = AddressSchema()
    error = address_schema.validate(client_data)

    # If the address data is invalid, return an error response
    if error:
      return jsonify({'message': 'Invalid address data, please check your input', 'errors': error}), 400

    # handle case sensitivity
    address_line1_pattern = re.compile(re.escape(client_data['addressLine1']), re.IGNORECASE)
    db_query = {
      'addressLine1': {'$regex' : address_line1_pattern},
      'addressLine2': client_data.get('addressLine2', None),
      'city': client_data['city'].title(),
      'stateProv': client_data['stateProv'].upper(),
      '$or': [
        {'postalCode': client_data['postalCode']},
        {'postalCode': {'$regex': client_data['postalCode'][:5]}}
      ],
      'country': client_data['country'].upper()
    }
    
    # query db
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
        recommendations['addressLine1'] = client_data['addressLine1'].title()

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

        # only US addresses in the db for now
        if client_data["country"].upper() == 'US':
          recommendations['country'] = 'USA'
        else:
          recommendations['country'] = client_data['country'].upper()

        recommendations['city'] = client_data['city'].title()
        recommendations['addressLine2'] = client_data.get('addressLine2', None) 

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

# --------------------------------------  Read /api/v1/addresses---------------------------------------------

@avs_routes.route('/api/v1/addresses', methods=['GET'])
@limiter.limit('15/hour') # This limit requests per hour to 15 for now
def get_list_of_addresses():
  """
    retrieves list of addresses from the db based on the query parameters specified in the request. 
    Can filter by city, state/province, postal code, country, address ID, and free-text search. 
    Results can be sorted by city, state/province, postal code, or country. 

    Params:
      city (str): filter addresses by city
      stateProv (str): filter addresses by state/province
      postalCode (str): filter addresses by postal code (supports optional +4 digit extension)
      country (str): filter addresses by country code
      id (str): get a single address by its ID
      ref_id (int): filter addresses by a reference ID
      search (str): filter addresses using free-text search
      sort (str): sort results by city, stateProv, postalCode, or country
      limit (int): limit the number of results returned
      format (str): specify the output format, either JSON or CSV

    Return:
        JSON object containing a list of addresses if the request was successful
        CSV data if the 'format' query parameter was set to 'csv'
    """
  try:
    # get query parameters from request
    city = request.args.get('city')
    stateProv = request.args.get('stateProv')
    postalCode = request.args.get('postalCode')
    country = request.args.get('country')
    limit = request.args.get('limit', type=int)
    address_id = request.args.get('id')
    referenceId = request.args.get('ref_id')
    format = request.args.get('format')
    search = request.args.get('search')
    sort = request.args.get('sort')
    addressLine1 = None

    if request.data:
      client_addressLine1_json_data = request.get_json()
      addressLine1 = client_addressLine1_json_data.get('addressLine1') if client_addressLine1_json_data else None

    # construct query based on parameters
    query = {}

    if addressLine1:
      query['addressLine1'] = addressLine1
    if city:
      query['city'] = city.title()
    if stateProv:
      query['stateProv'] = stateProv.upper()
    if postalCode:
      query['postalCode'] = {"$regex": "^" + postalCode + "(-\d{4})?$"}
    if country:
      query['country'] = country.upper()
    if referenceId:
      query['referenceId'] = int(referenceId)
    if search:
      query['$text'] = {'$search': search}

    # Add sorting if 'sort' query parameter is present
    sort_key = None
    if sort:
      if sort == 'city':
        sort_key = 'city'
      elif sort == 'stateProv':
        sort_key = 'stateProv'
      elif sort == 'postalCode':
        sort_key = 'postalCode'
      elif sort == 'country':
        sort_key = 'country'
      else:
        return jsonify({'Message': 'Invalid sort field'}), 400

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
      if sort_key:
        addresses = list(collection.find(query, {"_id": 0}).sort(sort_key).limit(limit))
      else:
        addresses = list(collection.find(query, {"_id": 0}).limit(limit))
      
    else:
      # If no limit or address ID is specified, return up to 30 addresses
      if sort_key:
        addresses = list(collection.find(query, {"_id": 0}).sort(sort_key).limit(30))
      else:
        addresses = list(collection.find(query, {"_id": 0}).limit(30))

    if format and format.lower() == 'csv':
      output = StringIO()
      writer = csv.DictWriter(output, fieldnames=addresses[0].keys())
      writer.writeheader()
      for address in addresses:
        writer.writerow(address)
      return Response(output.getvalue(), mimetype='text/csv')

    return jsonify(addresses), 200

  except PyMongoError as e:
    return jsonify({'message': 'Database error: {}'.format(str(e))}), 500
  except Exception as e:
    return jsonify({'message': str(e)}), 500


# --------------------------------------  Create /api/v1/address/ ---------------------------------------------

@avs_routes.route('/api/v1/address', methods=['POST'])
@limiter.limit('5/hour')
def create_new_address():
  '''
      POST - Create new address - new resource /api/v1/address

      Uses the 'Marshmallow' library to validate the input. It checks whether the address already exists in the database 
      and inserts the new address into the database. The response includes a newly created address and a timestamp of the creation time. 
      The endpoint is rate-limited to 5 requests per hour for now.
  ''' 
  # Retrieve address from request
  client_data = request.get_json()

  # Check if address already exists in collection
  if collection.count_documents(client_data) > 0:
    return jsonify({
      'message': 'Address already exists',
      'address': client_data,
      'status': 'failure'
    }), 409
  
  try:
    # Validate the address data using Marshmallow library
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
    # Return a generic error response with status code 500 (Internal Server Error)
    return jsonify({'message': 'Internal Server Error', 'error': str(e)}), 500



# --------------------------------------  UPDATE /api/v1/address/:address_id ---------------------------------------------

@avs_routes.route("/api/v1/address/<address_id>", methods=["PUT"])
@limiter.limit('3/hour')
def update_address(address_id):
  """
    Update the existing address resource using PUT method at /api/v1/address/:address_id.
    
    Params:
      - address_id : ReferenceId: The unique reference ID of the address resource to be updated.
      
    Return:
      - If the specified address resource is not found, a 404 error message is returned.
      - If the specified address resource is found, it is updated using the $set operator and a message is returned with the old and new addresses.
  """
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



# --------------------------------------  DEL /api/v1/address/:address_id ---------------------------------------------

@avs_routes.route("/api/v1/address/<address_id>", methods=["DELETE"])
@limiter.limit('3/hour')
def delete_address(address_id):
  """
    delete record (address) - remove existing resource at /api/v1/address/:address_id

    Param: 
      address_id - can be either a valid ObjectId or a ReferenceId

    If the address_id is a valid ObjectId, it deletes the corresponding address document. 
    Otherwise, it deletes the document with the provided ReferenceId.
  """

  successful_deletion_message = {
    'message': 'Address deleted successfully',
    'time_deleted': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    'status': 'success'
  }

  if ObjectId.is_valid(address_id):
    query = {'_id': ObjectId(address_id)}
  else:
    query = {'referenceId': int(address_id)}

  # check if address exists in the database
  if collection.count_documents(query) == 0:
    return jsonify({'message': 'Address not found'}), 404

  # delete document(address)
  try:
    _document = collection.find_one(query)
    successful_deletion_message['deleted_address'] = _document
    successful_deletion_message['deleted_address']['_id'] = str(successful_deletion_message['deleted_address']['_id'])
    db_query_result = collection.delete_one(query)

    if db_query_result.deleted_count == 1:
      return jsonify(successful_deletion_message), 200
    else:
      return jsonify({'message': 'Error deleting address'}), 500

  except PyMongoError as e:
    return jsonify({'message': 'Database error: {}'.format(str(e))}), 500
  except Exception as e:
    return jsonify({'message': 'Error deleting address', 'error': str(e)}), 500
