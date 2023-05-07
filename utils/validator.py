import re
from marshmallow import Schema, fields, validate, ValidationError


def validate_postal_code(postal_code):
    regex = re.compile(r"^\d{5}(?:-\d{4})?$")
    if not regex.match(postal_code):
        raise ValidationError("Invalid postal code format")

def validate_not_empty(value):
    if not value:
        raise ValidationError("Field cannot be empty")

def validate_addressLine_1(value):
    if not value:
        raise ValidationError("Field cannot be empty")
    if len(value.split()) < 2:
        raise ValidationError("Invalid addressLine1")


class AddressSchema(Schema):
    addressLine1 = fields.Str(
        required=True, validate=[validate_not_empty, validate_addressLine_1]
    )
    addressLine2 = fields.Str(allow_none=True)
    city = fields.Str(required=True, validate=validate_not_empty)
    stateProv = fields.Str(required=True, validate=validate_not_empty)
    referenceId = fields.Int(allow_none=True)
    postalCode = fields.Str(required=True, validate=validate_postal_code)
    country = fields.Str(required=True, validate=validate_not_empty)
