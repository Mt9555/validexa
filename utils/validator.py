import re
from marshmallow import Schema, fields, validate, ValidationError

def validate_postal_code(postal_code):
  regex = re.compile(r'^\d{5}(?:-\d{4})?$')
  if not regex.match(postal_code):
    raise ValidationError('Invalid postal code format')
    
class AddressSchema(Schema):
  addressLine1 = fields.Str(required=True)
  addressLine2 = fields.Str(allow_none=True)
  city = fields.Str(required=True)
  stateProv = fields.Str(required=True)
  referenceId = fields.Int(allow_none=True)
  postalCode = fields.Str(required=True, validate=validate_postal_code)
  country = fields.Str(required=True)

