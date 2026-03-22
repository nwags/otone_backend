#!/usr/bin/env python

from flask import Flask, request, session, jsonify, redirect, url_for, abort, render_template, flash, Response, make_response
from flask.ext.cache import Cache
#from flask.ext.assets import Environment as Enviro
#from flask.ext.assets import Bundle
#from flask.ext.scss import Scss

#from jinja2 import Environment, PackageLoader, FileSystemLoader
import jinja2
from collections import OrderedDict
import os, json
import uuid


# CONFIG ===================================================================================

app = Flask(__name__) #APPLICATION
app.config.from_object(__name__)

app.secret_key = "opentrons" # encryption key for session variable, security isn't really an issue

# configure Jinja template engine
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.lstrip_blocks = True # strip the whitespace from jinja template lines
app.jinja_env.trim_blocks = True

cache = Cache(app, config={'CACHE_TYPE': 'simple'}) # initialize cache to store objects

# NEW STUFF ================================================================================

directory = os.path.dirname(os.path.realpath(__file__))

tabs_templates = []
tabs_template_paths = []
tabs_template_names = []
tabs_folder_names = []
tabs_json = []
tabs_js = []
tabs_sass = []

prefix = 'templates/'

socketHandler = dict()

#assets = Enviro(app)
#assets.url = app.static_url_path
#sassy = Bundle('../templates/modules/containers_library/sass/test.sass', filters='sass', output='css_all.css')
#assets.register('css_all',sassy)
#
# {% assets "css_all" %}
# <link type="stylesheet" type="text/css" href="{{ ASSET_URL }}">
# {% endassets %}

# Scass(app, static_dir='static', asset_dir='templates', load_paths=[
#	''
#	])


def collect_templates():
	temp_path = os.path.dirname(__file__)
	#os.path.realpath(__file__))
	temp_folder = os.path.join(temp_path, 'tabs')
	for f in os.listdir(temp_folder):
		t_path = os.path.join(temp_folder, f)
		if os.path.isdir(t_path):
			tabs_folder_names.append(f)
			print('template folder name',f)
			process_template_folder(t_path)
			


def process_template_folder(tab_path):
	for f in os.listdir(tab_path):
		t_path = os.path.join(tab_path, f)
		print('t_path: ',t_path)
		if os.path.isdir(t_path) and t_path.endswith('sass'):
			print('sass folder found')
		elif os.path.isdir(t_path) and t_path.endswith('html'):
			print('html folder found')
			tabs_template_paths.append(t_path)
			process_html_folder(t_path)
		elif os.path.isdir(t_path) and t_path.endswith('json'):
			print('json folder found')
			process_json_folder(t_path)
		elif os.path.isdir(t_path) and t_path.endswith('js'):
			print('js folder found')
			process_js_folder(t_path)


def process_sass_folder(sass_path):
	for f in os.listdir(sass_path):
		pass


def process_html_folder(html_path):
	for f in os.listdir(html_path):
		full_relative_path = os.path.join(html_path, f)
		if os.path.isfile(full_relative_path) and full_relative_path.endswith('.html'):
			tabs_templates.append(f)
			tabs_template_names.append(f[:-len('.html')])


def process_json_folder(json_path):
	for f in os.listdir(json_path):
		full_relative_path = os.path.join(json_path, f)
		if os.path.isfile(full_relative_path) and full_relative_path.endswith('.json'):
			tabs_json.append(full_relative_path)


def process_js_folder(js_path):
	for f in os.listdir(js_path):
		full_relative_path = os.path.join(js_path, f)
		if os.path.isfile(full_relative_path) and full_relative_path.endswith('.js'):
			tabs_js.append(full_relative_path)


def get_entries_for_sockethandler(fname):
	print('fname: ', fname)
	entry_dict = None
	try:
		in_file = None
		in_file = open(os.path.join(directory,fname),"r")
		text_of_file = in_file.read().replace('\t','').replace('\n','')
		print('the path: ',os.path.join(directory,fname))
		#print('the beast: ',json.load(in_file,strict=False))
			#,object_pairs_hook=OrderedDict))
		entry_dict = json.loads(text_of_file,strict=False)
			#,object_pairs_hook=OrderedDict)
		print('entry_dict: ',json.dumps(entry_dict,sort_keys=True,indent=4,separators=(',',': ')))
	except EnvironmentError as err:
		print('Error reading json file: ',err)
		raise

	finally:
		if in_file is not None:
			in_file.close()
			if entry_dict is not None:
				return entry_dict
		else:
			return None


def add_entry_to_sockethandler(entries_dict):
	socketHandler.update(entries_dict)


def generate_sockethandler():
	t_dict = dict()
	for j in tabs_json:
		t_dict = get_entries_for_sockethandler(j)
		print("t_dict: ",json.dumps(t_dict,sort_keys=True,indent=4,separators=(',',': ')))
		add_entry_to_sockethandler(t_dict)
	
	sh_file = open('static/js/socketHandler.js',"w")
	filetext = json.dumps(socketHandler,sort_keys=True,indent=4,separators=(',',': '))
	sh_file.write(filetext)
	
	if sh_file is not None:
		sh_file.close()



# ROUTES ===================================================================================

@app.route('/')
def landing_page():
	
	uid = str(uuid.uuid4())
	session['session_id'] = uid

	session_id = session['session_id']
	print('session_id from landing_page:', session_id)
	
	collect_templates()
	
	loader = jinja2.FileSystemLoader(tabs_template_paths)
	my_loader = jinja2.ChoiceLoader([app.jinja_loader,loader])
	app.jinja_loader = my_loader


	# return render_template('body.html', filename='[empty]')	#modified rbw 8/26/15
	print('tabs_template_paths: ',tabs_template_paths)
	print('tabs_templates: ',tabs_templates)
	print('tabs_folder_names: ',tabs_folder_names)
	print('templates: ',app.jinja_env.list_templates())
	print('tabs_js: ',tabs_js)
	print('tabs_json: ',tabs_json)
	generate_sockethandler()
	return render_template('body.html', tabs_templates=tabs_templates, tabs_js=tabs_js, tabs_template_names=tabs_template_names, tabs_folder_names=tabs_folder_names)


if __name__ == '__main__':
	app.run(debug=True)