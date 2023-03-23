### Project 2-Basic Address Verification System

### Contributing
  These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

***

### Prerequisites

What you need
  - Py3
  - pip (a package manager for Python)
  - Virtualenv (for creating isolated Python environments)

### Installation
  Step by step instructions to get the development environment running:

##### Setting up the development environment
  1. Clone the repository
  2. Create a virtual environment: `py -3 -m venv venv`
  3. Activate the virtual environment: `source venv/bin/activate`
      ``` sh
      source venv/Scripts/activate (on Windows)
      source venv/bin/activate (on Mac/Linux)
      ```
  4. Install the dependencies: `pip install -r requirements.txt`
  5. set up .env variables
  6. Run the application- Be sure virtual environment is activated `flask run`
  7. To deactivate the virtual environment, run `deactivate`

&nbsp; &nbsp;

You can use _MAKE_ if you have it installed on your machine
Navigate to the root directory of the project in your terminal and run the following commands:

``` 
make venv: create a virtual environment and install all the project's dependencies in the requirements.txt file.
make run: activate virtual environment and start Flask development server accessible at http://localhost:{PORT}/
make clean: This command will delete the virtual environment and all its dependencies.

```


### Steps
  1. Fork the repository
  2. Create a new branch for your changes
  3. Make your changes
  4. Commit and push your changes to the new branch
  5. Create a pull request

## License
  This project is licensed under the MIT License.


## Project status

  In Progress


## Project Structure

- **controller**: contains the `avs_routes.py` file, which handles requests and, process them, and generates responses.

- **db**: contains the `connection.py` file, which provides configuration details and establishes a connection to a MongoDB Atlas database.

- **Doc**: contains documentation related to the project, including `contributing.md` and other project-related documents.

- **Utils**: contains modules and functions used by other parts of the project, with an `__init__.py` file to make it a package.

- **.gitignore**: specifies which files and folders should be ignored by Git when committing changes.

- **app.py**: the main entry point for the application, which initializes and configures the various components of the system.

- **devstart.sh**: a script that can be used to start the application in a local development environment.

- **LICENSE**: the license file for the project, which specifies the terms and conditions under which the software can be used, modified, and distributed.

- **Makefile**: a file used to automate various build tasks and operations.

- **Prod.sh**: a script that can be used to start the application in a production environment, using Gunicorn as the web server.

- **Readme.md**: the file you're currently reading, which provides an overview of the project and its structure.

- **Requirements.txt**: a file that specifies the external dependencies required by the project, which can be installed using a package manager like pip.