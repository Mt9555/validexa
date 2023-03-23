all: venv run

venv: requirements.txt
	py -3 -m venv venv
	source venv/Scripts/activate && pip install -r requirements.txt

run:
	source venv/Scripts/activate && flask run --host=0.0.0.0
	
clean:
	rm -rf venv
