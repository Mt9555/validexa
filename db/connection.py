from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

DB_PASS = os.getenv('DB_PWD')
DB_USERNAME = os.getenv('DB_USERNAME')

# Atlas connection
client = MongoClient(f"mongodb+srv://{DB_USERNAME}:{DB_PASS}@cluster1.bztqi43.mongodb.net/avs_db?retryWrites=true&w=majority")
db = client['avs_db']
collection = db['addresses']

# text index for search
collection.create_index([('addressLine1', 'text')])

address_schema = {
  'addressLine1': str,
  'addressLine2': str,
  'city': str,
  'stateProv': str,
  'postalCode': str,
  'country': str,
}
