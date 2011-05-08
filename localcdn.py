#!/usr/bin/env python

'''
This script dynamically combines js and css bundles, and provides a webserver for live dev mode
development. For static builds it combines and compresses the bundles, creating a deploy directory
suitable for creating a tarball and placing on a CDN origin server.

For compression it depends on yuicompressor, which the script will fetch if needed.

To do run the dev server and generate the bundles dynamically:

./localcdn.py -c localcdn.conf

To generate the deploy folder, suitable for placing on a CDN origin server:

./localcdn.py -c localcdn.conf -g

Config File Format:

{
    "srcDir": ".",
    "deployDir": "../cdn-deploy",
    "js": {
        "deps.js": [
            "ext/jquery-1.5.2.js",
            "ext/underscore.js",
            "ext/backbone.js"
        ],
        "appbundle.js": [
            "app.js",
            "model.js"
        ]
    },
    "css": {
        "main.css": ["screen.css", "widgets.css"]
    }
}

Which would correspond to the matching directory structure:

cdn/
    localcdn.conf
    js/
        ext/
            jquery-1.5.2.js
            underscore.js
            backbone.js
        app.js
        model.js
    css/
        screen.css
        widgets.css
    images/
        foo.png
    
Which in 'serve' mode would be accessible with these URLs:

http://localhost:3000/js/deps.js
http://localhost:3000/js/appbundle.js
http://localhost:3000/css/main.css
http://localhost:3000/images/foo.png

And generate this directory structure in 'deploy' mode:

cdn-deploy/
    js/
        deps.js
        appbundle.js
    css/
        main.css
    images/
        foo.png
'''

import os
import sys
import time
import json
import mimetypes
import subprocess
import BaseHTTPServer

from shutil import copy2
from fnmatch import fnmatch
from optparse import OptionParser

conf = {}
yuicompressor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'yuicompressor.jar')

def get_yuicompressor():
    subprocess.call(['wget','http://yui.zenfs.com/releases/yuicompressor/yuicompressor-2.4.6.zip'])
    subprocess.call(['unzip','yuicompressor-2.4.6.zip'])
    subprocess.call(['mv','yuicompressor-2.4.6/build/yuicompressor-2.4.6.jar', yuicompressor_path])
    subprocess.call(['rm','-rf','yuicompressor-2.4.6','yuicompressor-2.4.6.zip'])


def parse_conf(confpath):
    '''Loads the json conf from disk and converts relative paths to absolute paths'''
    
    fullpath = os.path.abspath(confpath)
    root = os.path.dirname(fullpath)
    
    global conf
    
    conf = json.loads(open(fullpath).read())
    conf['srcDir'] = os.path.join(root, conf['srcDir'])
    conf['deployDir'] = os.path.join(root, conf['deployDir'])


def is_bundle(path):
    '''Returns true if the url path represents a bundle'''
    
    parts = path.split('/')
    
    if len(parts) < 3:
        return False
    
    asset_type = parts[1]
    bundle_name = parts[2]
    
    return asset_type in conf and bundle_name in conf[asset_type]


def get_static(path):
    '''Attempts to serve the file from the config srcDir that matches the url path'''
    
    code = 404
    content_type = 'text/plain'
    content = 'File Not Found'
    
    filepath = conf['srcDir'] + path
    
    if os.path.isfile(filepath):
        code = 200
        content_type = mimetypes.guess_type(filepath)[0] or 'text/plain'
        content = open(filepath).read()
    
    return code, content_type, content


def get_bundle(asset_type, bundle_name):
    '''Combines all the resources that represents a bundle and returns them as a single string'''
    
    content_type = 'application/javascript'
    content = []
    
    if asset_type == 'css':
        content_type = 'text/css'
    
    for asset in conf[asset_type][bundle_name]:
        content.append(open(os.path.join(conf['srcDir'], asset_type, asset)).read())
    
    content = ''.join(content)
    
    return 200, content_type, content


def compress_content(content_type, content):
    '''Compresses a js or css string and returns the compressed string'''
    
    command = 'java -jar %s --type=%s' % (yuicompressor_path, content_type)
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdin.write(content)
    p.stdin.close()
    
    compressed = p.stdout.read()
    p.stdout.close()
    
    err = p.stderr.read()
    p.stderr.close()
    
    if p.wait() != 0:
        if not err:
            err = 'Unable to use YUI Compressor'
        
    
    return compressed


def deploy():
    srcdir = conf['srcDir']
    deploydir = conf['deployDir']
    jsdir = os.path.join(conf['deployDir'], 'js')
    cssdir = os.path.join(conf['deployDir'], 'css')
    
    if not os.path.isdir(deploydir):
        os.makedirs(deploydir)
    
    if not os.path.isdir(jsdir):
        os.mkdir(jsdir)
    
    if not os.path.isdir(cssdir):
        os.mkdir(cssdir)
    
    # generate all the bundles and write them to the deploy dir
    for asset_type in ['js','css']:
        for bundle_name in conf[asset_type].iterkeys():
            code, content_type, content = get_bundle(asset_type, bundle_name)
            compressed = compress_content(asset_type, content)
            
            f = open(os.path.join(deploydir, asset_type, bundle_name), 'w')
            f.write(compressed)
            f.close()
        
    
    # now walk the srcDir and copy everything else over that's not part of a bundle
    for (root, dirs, files) in os.walk(srcdir):        
        relpath = root[len(srcdir):]
        
        if not os.path.isdir(deploydir + relpath):
            os.makedirs(deploydir + relpath)
        
        for f in files:
            # skip the localcdn files, just copy actual static assets
            if fnmatch(f, 'localcdn.py') or fnmatch(f, 'yuicompressor*.jar') or fnmatch(f, '*.conf'):
                continue
            
            copy2(os.path.join(root, f), os.path.join(deploydir + relpath, f))
        
    


def start_server(port):
    httpd = BaseHTTPServer.HTTPServer(('', port), DynamicAssetHandler)
    
    print time.asctime(), "Server started - http://%s:%s/" % ('localhost', port)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    
    httpd.server_close()


class DynamicAssetHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    
    def do_HEAD(self):
        self.do_GET(True)
    
    def do_GET(self, headers_only=False):
        if is_bundle(self.path):
            parts = self.path.split('/')
            asset_type = parts[1]
            bundle_name = parts[2]
            
            code, content_type, content = get_bundle(asset_type, bundle_name)
        else:
            code, content_type, content = get_static(self.path)
        
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        
        if headers_only:
            return
        
        self.wfile.write(content)
    


parser = OptionParser("localcdn.py -c CONFIG_FILE [options]")
parser.add_option('-p', '--port', dest='port', type='int', default=3000, help='the port to run the dev server on [defaults to 3000]')
parser.add_option('-c', '--config', dest='config_file', help='the config file path that defines the js/css bundles [required]')
parser.add_option('-g', '--generate', action='store_true', dest='generate', help='generate the deploy package to place on a CDN')
parser.add_option('--minify', action='store_true', dest='minify', help='have the dev server minify the bundles, by default bundles are served unminified')
parser.add_option('--no-minify', action='store_false', dest='no_minify', help="don't minify the bundles when generating the deploy folder, by default bundles are minified")

if __name__ == '__main__':
    (options, args) = parser.parse_args()
    
    if not options.config_file:
        parser.error('No config file specified.')
    
    parse_conf(options.config_file)
    
    if options.generate:
        if not os.path.exists(yuicompressor_path):
            get_yuicompressor()
        
        deploy()
    else:
        start_server(options.port)
    

