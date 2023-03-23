#!/bin/sh

source venv/Scripts/activate
gunicorn -w 4 -b 0.0.0.0:8000 app:app