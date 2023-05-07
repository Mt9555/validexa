from dotenv import load_dotenv

load_dotenv()

import os
from flask import Blueprint, request, Response, jsonify, abort
from db.connection import collection, api_key_collection
from pymongo.errors import PyMongoError
from utils import AddressSchema, state_names, misc_abbreviation, generate_api_key, auth
from datetime import datetime
from io import StringIO
from utils.limiter import limiter
from bson import ObjectId
from functools import wraps
from fuzzywuzzy import fuzz
import copy
import csv
import re

avs_routes = Blueprint("avs_routes", __name__)


@avs_routes.route("/api/v1/auth", methods=["GET"])
@limiter.limit("15/hour")
def generate_token():
    client_ip = request.remote_addr
    time_generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_key = api_key_collection.find_one({"client_ip": client_ip})

    if existing_key:
        msg = {
            "error": "Key already exist. Please use that instead.",
            "status": "failure",
        }
        return jsonify(msg), 400

    api_key = generate_api_key()

    api_key_collection.insert_one(
        {"api_key": api_key, "client_ip": client_ip, "created": time_generated}
    )

    msg = {"key": api_key, "time_generated": time_generated}
    return jsonify(msg), 200


def require_api_key(func):
    @wraps(func)
    def validate_api_key(*args, **kwargs):
        """
        Functionality:
        Check presence of API KEY in request header before authenticating

        """
        api_key = request.headers.get("Authorization")
        # print('-- API kEY', api_key)

        error_message = {
            "error": "API key is required to access resource - Missing API KEY",
            "fail_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "failure",
        }

        if not api_key:
            return jsonify(error_message), 401

        if not api_key_collection.find_one({"api_key": api_key}):
            error_message = {
                "error": "Invalid API key - Unauthorized access",
                "fail_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "failure",
            }
            return jsonify(error_message), 401
        return func(*args, **kwargs)

    return validate_api_key


@avs_routes.route("/api/v1/verify", methods=["POST"])
@limiter.limit("30/hour")
@require_api_key
def verify_address():
    try:
        client_data = request.get_json()
        client_address_data_response = copy.deepcopy(client_data)
        no_recommendation_q_val = request.args.get("nr")

        if not isinstance(client_data.get("addressLine1"), str):
            return jsonify({"error": "Invalid addressLine1 Input"}), 400

        # Validate
        address_schema = AddressSchema()
        error = address_schema.validate(client_data)

        if error:
            return (
                jsonify(
                    {
                        "message": "Invalid address data, please check your input",
                        "errors": error,
                    }
                ),
                400,
            )

        escaped_address_line1 = re.escape(client_data["addressLine1"])
        address_line1_pattern = re.compile(r"\b[a-zA-Z0-9]+\b", re.IGNORECASE)
        valid_word = address_line1_pattern.findall(escaped_address_line1)
        processed_address_line1 = " ".join(valid_word)
        # print('test-----', processed_address_line1)
        country = client_data["country"].upper()
        possible_ = ["UNITED STATE", "UNITED STATES", "US", "USA"]
        country = "US" if country in possible_ else country

        client_state = client_data["stateProv"]
        state_character_over2 = len(client_state) > 2
        processed_state_prov = (
            state_names.get(client_state.title(), None)
            if state_character_over2
            else client_state.upper()
        )

        db_query = {
            "addressLine1": {"$regex": processed_address_line1, "$options": "i"},
            "addressLine2": client_data.get("addressLine2", None),
            "city": client_data["city"].title(),
            "stateProv": processed_state_prov,
            "$or": [
                {"postalCode": client_data["postalCode"]},
                {"postalCode": {"$regex": client_data["postalCode"][:5]}},
            ],
            "country": country,
        }

        VALID_ADDRESS = collection.find_one(db_query, {"_id": 0})

        if VALID_ADDRESS:
            # dict to store recommendations
            recommendations = {}
            client_addressLine1 = VALID_ADDRESS.get("addressLine1").split(" ")

            # Replace address line abbreviations "4500 Due W Rd NW"
            for idx, word in enumerate(client_addressLine1):
                if word.lower() in misc_abbreviation:
                    client_addressLine1[idx] = misc_abbreviation[word.lower()]

            client_data["addressLine1"] = " ".join(client_addressLine1)
            recommendations["addressLine1"] = client_data["addressLine1"].upper()

            if len(client_data["postalCode"]) == 5:
                # TODO: integrate with postgrid api for the last four
                postal_code = VALID_ADDRESS.get("postalCode")
                if postal_code:
                    last_four_digits = postal_code[-4:]
                    _zip = client_data["postalCode"] + "-" + last_four_digits
                    recommendations["postalCode"] = _zip
            else:
                recommendations["postalCode"] = client_data["postalCode"]

            # Recommend abbreviated state name
            if client_data["stateProv"].title() in state_names:
                recommended_abbreviated_state_name = state_names[
                    client_data["stateProv"].title()
                ]
                recommendations[
                    "stateProv"
                ] = recommended_abbreviated_state_name.upper()
            else:
                recommendations["stateProv"] = client_data["stateProv"].upper()

            # only US addresses
            client_country = client_data["country"].upper()
            recommendations["country"] = (
                "US" if client_country in possible_ else client_country.upper()
            )

            recommendations["city"] = client_data["city"].upper()
            recommendations["addressLine2"] = client_data.get("addressLine2", None)

            response = {
                "avsAddressDetails": {
                    "responseStatus": True,
                    "addressVerified": True,
                    "avsResponseCode": 100,
                    "avsResponseDecision": "Success",
                    "address": client_address_data_response,
                    "recommendedAddresses": {"recommendedAddress": recommendations},
                }
            }
            if no_recommendation_q_val and no_recommendation_q_val.lower() == "f":
                response["avsAddressDetails"].pop("recommendedAddresses")
        else:
            failed_address_recommendation = {}

            db_query = {
                "$text": {"$search": client_data["addressLine1"] or None},
                "country": country,
            }

            near_match_result = collection.find(db_query, {"_id": 0})
            near_match_list = list(near_match_result)
            is_near_match_list = len(near_match_list) > 0

            if is_near_match_list:
                # Sort the results by similarity score
                near_match = [
                    addr
                    for addr in near_match_list
                    if fuzz.partial_ratio(
                        client_data["addressLine1"], addr["addressLine1"]
                    )
                    >= 30
                ]
                near_match = sorted(
                    near_match,
                    key=lambda x: fuzz.partial_ratio(
                        client_data["addressLine1"], x["addressLine1"]
                    ),
                    reverse=True,
                )

                # print('--- near match ------------------', near_match)

                # for address in near_match_list:
                #   similarity_score = fuzz.partial_ratio(client_data['addressLine1'], address['addressLine1'])
                #   print(f"Address: {address['addressLine1']}, Similarity score: {similarity_score}")

                # near_match = fuzz.partial_ratio(client_data['addressLine1'], '2870 Clay Rd')
                # print("--- near_match", near_match)

                # reference_id = near_match[0].get('referenceId')
                # if reference_id is None:
                #   reference_id = None

                address_line_1 = near_match[0]["addressLine1"].split(" ")

                # Replace address line abbreviations "4500 Due W Rd NW"
                for idx, word in enumerate(address_line_1):
                    if word.lower() in misc_abbreviation:
                        address_line_1[idx] = misc_abbreviation[word.lower()]

                clientaddress_line_1 = " ".join(address_line_1)
                failed_address_recommendation[
                    "addressLine1"
                ] = clientaddress_line_1.upper()
                failed_address_recommendation["postalCode"] = near_match[0][
                    "postalCode"
                ]
                stateProv = near_match[0]["stateProv"]
                country_code = near_match[0]["country"]

                if stateProv.title() in state_names:
                    stateProv = state_names[stateProv]

                if country_code == "US":
                    country_code == "US"

                failed_address_recommendation["stateProv"] = stateProv.upper()
                failed_address_recommendation["country"] = country_code.upper()
                failed_address_recommendation["city"] = near_match[0]["city"].upper()
                failed_address_recommendation["addressLine2"] = near_match[0].get(
                    "addressLine2", None
                )

            response = {
                "avsAddressDetails": {
                    "responseStatus": True,
                    "addressVerified": False,
                    "avsResponseCode": 100,
                    "avsResponseDecision": "Failure",
                    "address": client_data,
                    "nearMatchAddressRecommendation": failed_address_recommendation
                    or {"msg": "no recommendation for the address submitted"},
                }
            }

            if no_recommendation_q_val and no_recommendation_q_val.lower() == "f":
                response["avsAddressDetails"].pop("nearMatchAddressRecommendation")

        return jsonify(response), 200
    except PyMongoError as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500


######################################################
#   *    **  * ***  ****  ******  **** * **    **    #
#   ***   **   **  **   **   **   **  ***  **** ******
######################################################


# --------------------------------------  GET /api/v1/addresses---------------------------------------------

"""
    1. query by addressLine1 - request body (JSON)
    2. Created text index for search
    3. Sorting in ascending or descending by postalcode, city, stateProv, country
    4. client can choose to get the response in either CSV or JSON format
    5. Client input: matching input: case sensitivity - verify endpoint

"""


@avs_routes.route("/api/v1/addresses", methods=["GET"])
@limiter.limit("15/hour")  # This limit requests per hour to 15 for now
@auth.login_required
def get_list_of_addresses():
    """
    Retrieves a list of addresses from the database based on the query parameters specified in the request.
    It allows for filtering by city, state/province, postal code, country, address ID, and free-text search.
    Results can be sorted by city, state/province, postal code, or country.
    The endpoint returns up to 30 addresses by default but allows for a customizable limit.
    Results can be returned in JSON format or in CSV format if specified.

    This endpoint is rate-limited to 15 requests per hour.

    Query Parameters:

        city (str): filter addresses by city
        stateprov (str): filter addresses by state/province
        postalcode (str): filter addresses by postal code (supports optional +4 digit extension)
        country (str): filter addresses by country code
        id (str): get a single address by its ID
        ref_id (int): filter addresses by a reference ID
        search (str): filter addresses using free-text search
        sort (str): sort results by city, stateProv, postalCode, or country
        limit (int): limit the number of results returned
        format (str): specify the output format, either JSON or CSV

    Returns:

        JSON object containing a list of addresses if the request was successful
        CSV data if the 'format' query parameter was set to 'csv'
        Error messages if there was an error with the request, such as an invalid query parameter or a database error
    """
    try:
        city = request.args.get("city")
        stateProv = request.args.get("stateprov")
        postalCode = request.args.get("postalcode")
        country = request.args.get("country")
        limit = request.args.get("limit", type=int)
        address_id = request.args.get("id")
        referenceId = request.args.get("ref_id")
        format = request.args.get("format")
        search = request.args.get("search")
        sort = request.args.get("sort")
        addressLine1 = None

        if request.data:
            client_addressLine1_json_data = request.get_json()
            addressLine1 = (
                client_addressLine1_json_data.get("addressLine1")
                if client_addressLine1_json_data
                else None
            )

        # construct query based on parameters
        query = {}

        if addressLine1:
            query["addressLine1"] = addressLine1
        if city:
            query["city"] = city.title()
        if stateProv:
            query["stateProv"] = stateProv.upper()
        if postalCode:
            query["postalCode"] = {"$regex": "^" + postalCode + "(-\d{4})?$"}
        if country:
            query["country"] = country.upper()
        if referenceId:
            p_ref = re.sub("[^0-9]", "", str(referenceId))
            query["referenceId"] = int(p_ref)
        if search:
            query["$text"] = {"$search": search}

        sort_key = None
        if sort:
            if sort.lower() == "city":
                sort_key = "city"
            elif sort.lower() == "stateprov":
                sort_key = "stateProv"
            elif sort.lower() == "postalcode":
                sort_key = "postalCode"
            elif sort.lower() == "country":
                sort_key = "country"
            else:
                return jsonify({"Message": "Invalid sort field"}), 400

        if address_id:
            if ObjectId.is_valid(address_id):
                address = collection.find_one({"_id": ObjectId(address_id)}, {"_id": 0})
                if address:
                    return jsonify(address), 200
                else:
                    return jsonify({"Message": "Address not found"}), 404
            else:
                return jsonify({"Message": "Invalid address ID"}), 400

        elif limit:
            if sort_key:
                addresses = list(
                    collection.find(query, {"_id": 0}).sort(sort_key).limit(limit)
                )
            else:
                addresses = list(collection.find(query, {"_id": 0}).limit(limit))

        else:
            # If no limit or address ID is specified, return up to 30 addresses
            if sort_key:
                addresses = list(
                    collection.find(query, {"_id": 0}).sort(sort_key).limit(30)
                )
            else:
                addresses = list(collection.find(query, {"_id": 0}).limit(30))

        if format and format.lower() == "csv":
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=addresses[0].keys())
            writer.writeheader()
            for address in addresses:
                writer.writerow(address)
            return Response(output.getvalue(), mimetype="text/csv")

        if addresses:
            return jsonify(addresses), 200
        else:
            return jsonify({"Message": "Address not found"}), 404

    except PyMongoError as e:
        return jsonify({"message": "Database error: {}".format(str(e))}), 500
    except Exception as e:
        return jsonify({"message": str(e)}), 500


# --------------------------------------  POST /api/v1/address/ ---------------------------------------------


@avs_routes.route("/api/v1/address/", methods=["POST"])
@limiter.limit("10/hour")
@auth.login_required
def create_new_address():
    """
    Description:
      POST - Create new address - insert a new resource /api/v1/address

    Functionality:
      This endpoint uses the 'Marshmallow' library to validate the input. It checks whether the address already exists in the database
      and inserts the new address into the database. The response includes a newly created address and a timestamp of the creation time.
      The endpoint is currently rate-limited to 5 requests per hour.
    """
    client_data = request.get_json()
    try:
        address_schema = AddressSchema()
        errors = address_schema.validate(client_data)

        if errors:
            return jsonify({"message": "Invalid address data", "errors": errors}), 400

        if collection.count_documents(client_data) > 0:
            return (
                jsonify(
                    {
                        "message": "Address already exists",
                        "address": client_data,
                        "status": "failure",
                    }
                ),
                409,
            )

        c_state_prov = client_data.get("stateProv")
        if c_state_prov.title() in state_names:
            c_state_prov = state_names.get(c_state_prov.title()).upper()
        else:
            c_state_prov = c_state_prov.upper()

        c_country = client_data.get("country")
        cS = ["us", "united states", "united state"]
        if c_country.lower() in cS:
            c_country = "US"  # only US address
        else:
            c_country = c_country.title()

        data_to_store = {
            "addressLine1": client_data.get("addressLine1").title(),
            "addressLine2": client_data.get("addressLine2", None),
            "city": client_data.get("city", "").title(),
            "country": c_country,
            "postalCode": client_data.get("postalCode", None),
            "referenceId": client_data.get("referenceId"),
            "stateProv": c_state_prov,
        }

        result = collection.insert_one(data_to_store)
        new_address = collection.find_one({"_id": result.inserted_id})
        new_address["_id"] = str(new_address["_id"])

        client_success_response = {
            "time_created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "newly_created_address": new_address,
            "status": "success",
        }

        return jsonify(client_success_response), 201

    except PyMongoError as e:
        return jsonify({"message": "Database error: {}".format(str(e))}), 500
    except Exception as e:
        return jsonify({"message": "Internal Server Error", "error": str(e)}), 500


# --------------------------------------  UPDATE /api/v1/address/:address_id ---------------------------------------------


@avs_routes.route("/api/v1/address/<address_id>", methods=["PUT"])
@limiter.limit("5/hour")
@auth.login_required
def update_address(address_id):
    """
    Update the existing address resource using PUT method at /api/v1/address/:address_id.

    Params:
      - address_id : ReferenceId: The unique reference ID of the address resource to be updated.

    Returns:
      - If the specified address resource is not found, a 404 error message is returned.
      - If the specified address resource is found, it is updated using the $set operator and a message is returned with the old and new addresses.
    """
    client_data = request.get_json()
    address_schema = AddressSchema()
    errors = address_schema.validate(client_data)

    if errors:
        return jsonify({"message": "Invalid address data", "errors": errors}), 400

    query = {"referenceId": int(address_id)}
    db_query_result = collection.find_one(query)

    if db_query_result is None:
        return (
            jsonify({"message": "Address not found", "address_ref_id": address_id}),
            404,
        )

    try:
        old_address = db_query_result
        collection.update_one(query, {"$set": client_data})
        updated_address = collection.find_one(query)

        succesful_update_message = {
            "message": "Address Updated successfully",
            "time_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "success",
            "old_address": old_address,
            "new_address": updated_address,
        }

        # ObjectId not serializable: convert the ObjectId to string
        succesful_update_message["old_address"]["_id"] = str(
            succesful_update_message["old_address"]["_id"]
        )
        succesful_update_message["new_address"]["_id"] = str(
            succesful_update_message["new_address"]["_id"]
        )
        return jsonify(succesful_update_message), 200

    except PyMongoError as e:
        return jsonify({"message": "Database error: {}".format(str(e))}), 500
    except Exception as e:
        return jsonify({"message": "Error updating address", "error": str(e)}), 500


# --------------------------------------  DELETE /api/v1/address/:address_id ---------------------------------------------


@avs_routes.route("/api/v1/addresses/<address_id>", methods=["DELETE"])
@limiter.limit("5/hour")
@auth.login_required
def delete_address(address_id):
    """
    Description: DELETE - delete address - remove existing resources at /api/v1/address/:address_id
    Param: address_id - can be either a valid ObjectId or a ReferenceId
    If the address_id is a valid ObjectId, it deletes the corresponding address document. Otherwise,
    it deletes the document with the provided ReferenceId.
    """

    successful_deletion_message = {
        "message": "Address deleted successfully",
        "time_deleted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
    }

    if ObjectId.is_valid(address_id):
        query = {"_id": ObjectId(address_id)}
    else:
        query = {"referenceId": int(address_id)}

    if collection.count_documents(query) == 0:
        return jsonify({"message": "Address not found"}), 404

    try:
        _document = collection.find_one(query)
        successful_deletion_message["deleted_address"] = _document
        successful_deletion_message["deleted_address"]["_id"] = str(
            successful_deletion_message["deleted_address"]["_id"]
        )
        db_query_result = collection.delete_one(query)

        if db_query_result.deleted_count == 1:
            return jsonify(successful_deletion_message), 200
        else:
            return jsonify({"message": "Error deleting address"}), 500

    except PyMongoError as e:
        return jsonify({"message": "Database error: {}".format(str(e))}), 500
    except Exception as e:
        return jsonify({"message": "Error deleting address", "error": str(e)}), 500
